"""Playback shell — V0 of the visualizer rebuild (see VISUALIZER_PLAN.md).

Right now this only plays audio and draws a now-playing header, a play/pause
body, and a controls footer. All the spectrum DSP and composition was stripped
out; it comes back one vetted phase at a time (V1: raw log spectrum, ...).

The pure input parsing (`parse_input`) is unit tested. Everything that touches
the real terminal or audio hardware is exercised live rather than in tests.
"""

import contextlib
import os
import re
import select
import sys
import termios
import time
import tty

from render import RESET, frame_payload, sample_gradient, spectrum_frame, truecolor_fg
from spectrum import compute_bands, log_band_edges, to_display

# V1 spectrum tuning (see VISUALIZER_PLAN.md). A large window is required to
# resolve real bass; RAW_GAIN is the eyeball knob for overall bar height until
# autosens lands.
FFT_WINDOW = 8192
FMIN = 40.0
FMAX = 16000.0
RAW_GAIN = 20.0

# Header accent gradients (kept from the old visual; only the header uses them
# in V0, but the palette machinery returns in the polish phase).
PALETTES = {
    "trap": [
        (0.0, (123, 31, 162)),   # deep purple
        (0.4, (233, 30, 99)),    # pink
        (0.7, (255, 111, 0)),    # orange
        (1.0, (255, 214, 0)),    # gold
    ],
    "aurora": [
        (0.0, (170, 0, 255)),
        (0.4, (0, 120, 255)),
        (0.7, (0, 230, 200)),
        (1.0, (120, 255, 120)),
    ],
    "ice": [
        (0.0, (0, 80, 200)),
        (0.5, (0, 200, 255)),
        (1.0, (230, 255, 255)),
    ],
    "sunset": [
        (0.0, (40, 20, 90)),
        (0.4, (200, 30, 70)),
        (0.7, (255, 120, 20)),
        (1.0, (255, 220, 90)),
    ],
}
PALETTE_ORDER = ["trap", "aurora", "ice", "sunset"]


# --------------------------------------------------------------------------
# Input parsing (pure, unit tested)
# --------------------------------------------------------------------------

_MOUSE_RE = re.compile(r"\x1b\[<(\d+);(\d+);(\d+)([Mm])")
_ARROWS = {"\x1b[A": "A", "\x1b[B": "B", "\x1b[C": "C", "\x1b[D": "D"}


def parse_input(buf):
    """Parse a raw input buffer into ('key'|'arrow'|'mouse', ...) events."""
    events = []
    i = 0
    while i < len(buf):
        if buf[i] == "\x1b":
            m = _MOUSE_RE.match(buf, i)
            if m:
                events.append(("mouse", int(m.group(2)), int(m.group(3))))
                i = m.end()
                continue
            three = buf[i:i + 3]
            if three in _ARROWS:
                events.append(("arrow", _ARROWS[three]))
                i += 3
                continue
            events.append(("key", "\x1b"))
            i += 1
        else:
            events.append(("key", buf[i]))
            i += 1
    return events


# --------------------------------------------------------------------------
# Live I/O shell (not unit tested — needs a real terminal + audio).
# --------------------------------------------------------------------------

def _fmt_time(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def _visible(s):
    return re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", s)


def _header(title, pos, dur, width, palette):
    color = truecolor_fg(sample_gradient(palette, 0.6))
    left = f"♪ {title}"
    right = f"{_fmt_time(pos)} / {_fmt_time(dur)}"
    bar_w = max(4, width - len(_visible(left)) - len(right) - 3)
    filled = int(bar_w * (pos / dur)) if dur else 0
    bar = "━" * filled + "╸" + "─" * max(0, bar_w - filled - 1)
    return f"{color}{left}{RESET} {bar} {right}"


def _footer(width, palette_name):
    keys = "space pause · → skip · ↑↓ vol · g palette · q quit"
    return f"\x1b[2m{keys}   [{palette_name}]{RESET}"


def _idle_body(paused, width, height, palette):
    """The body area for V0: a centered play/pause indicator on blank rows."""
    state = "⏸  paused" if paused else "▶  playing"
    color = truecolor_fg(sample_gradient(palette, 0.5))
    mid = height // 2
    lines = []
    for r in range(height):
        if r == mid:
            pad = max(0, (width - len(state)) // 2)
            tail = max(0, width - pad - len(state))
            lines.append(" " * pad + color + state + RESET + " " * tail)
        else:
            lines.append(" " * width)
    return lines


def _spectrum_body(engine, width, height):
    """The V1 body: raw log-spaced spectrum bars, one band per column."""
    n_bands = max(1, width)
    edges = log_band_edges(n_bands, FMIN, min(FMAX, engine.samplerate / 2.0))
    window = engine.latest_window(FFT_WINDOW)
    bands = compute_bands(window, engine.samplerate, edges)
    disp = to_display(bands, FFT_WINDOW, gain=RAW_GAIN)
    return spectrum_frame(disp, height)


class Screen:
    def size(self):
        cols, rows = os.get_terminal_size()
        return cols, rows

    def draw(self, lines):
        # One synchronized, atomic repaint — see render.frame_payload.
        sys.stdout.write(frame_payload(lines))
        sys.stdout.flush()


@contextlib.contextmanager
def _raw_terminal():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        # hide cursor, clear
        sys.stdout.write("\x1b[?25l\x1b[2J")
        sys.stdout.flush()
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        # show cursor, reset, clear
        sys.stdout.write("\x1b[?25h\x1b[0m\x1b[2J\x1b[H")
        sys.stdout.flush()


def _read_pending(fd=None):
    """Read all bytes currently available on `fd` (default: stdin), non-blocking.

    Reads straight from the file descriptor with os.read, not sys.stdin.read:
    a buffered text read blocks until it has the *full* requested count, so a
    single keypress or mouse-motion byte would hang the whole loop. os.read
    returns whatever is ready right now.
    """
    if fd is None:
        fd = sys.stdin.fileno()
    chunks = []
    while select.select([fd], [], [], 0)[0]:
        data = os.read(fd, 4096)
        if not data:  # EOF
            break
        chunks.append(data)
        if len(data) < 4096:
            break
    return b"".join(chunks).decode("utf-8", "ignore")


def run(engine, title, palette_name="trap", fps=30):
    """Play `engine` and draw the playback UI until the song ends or the user
    quits/skips. Returns True if the user asked to quit the whole session."""
    screen = Screen()
    pal_idx = PALETTE_ORDER.index(palette_name) if palette_name in PALETTE_ORDER else 0

    engine.start()
    quit_session = False
    skip = False
    frame_dt = 1.0 / fps

    with _raw_terminal():
        while not engine.finished and not skip and not quit_session:
            frame_start = time.time()
            width, rows = screen.size()

            for event in parse_input(_read_pending()):
                if event[0] == "arrow":
                    a = event[1]
                    if a == "A":
                        engine.nudge_volume(0.05)
                    elif a == "B":
                        engine.nudge_volume(-0.05)
                    elif a == "C":
                        skip = True
                elif event[0] == "key":
                    k = event[1]
                    if k in ("q", "\x03"):
                        quit_session = True
                    elif k == " ":
                        engine.toggle_pause()
                    elif k == "n":
                        skip = True
                    elif k == "g":
                        pal_idx = (pal_idx + 1) % len(PALETTE_ORDER)

            palette = PALETTES[PALETTE_ORDER[pal_idx]]
            body_rows = max(1, rows - 2)
            frame = (
                [_header(title, engine.position_seconds, engine.duration_seconds,
                         width, palette)]
                + _spectrum_body(engine, width, body_rows)
                + [_footer(width, PALETTE_ORDER[pal_idx])]
            )
            screen.draw(frame)

            elapsed = time.time() - frame_start
            if elapsed < frame_dt:
                time.sleep(frame_dt - elapsed)

    engine.stop()
    return quit_session
