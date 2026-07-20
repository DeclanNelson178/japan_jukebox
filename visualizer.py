"""The visualizer: turns live audio into a mirrored... no — a bottom-anchored
truecolor spectrum with floating peak caps, gradient color, and beat pulse.

`compose_frame` is pure and unit tested. Everything below the PALETTES/compose
line does terminal + keyboard I/O and is exercised live rather than in tests.
"""

import contextlib
import os
import re
import select
import sys
import termios
import time
import tty

import numpy as np

from render import (
    RESET,
    braille_waveform,
    column_glyphs,
    frame_payload,
    sample_gradient,
    truecolor_fg,
)
from spectrum import (
    BeatDetector,
    PeakHold,
    Smoother,
    compute_bands,
    log_band_edges,
)

# Frequency-swept gradients (position 0 = bass/left .. 1 = treble/right).
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

CAP_GLYPH = "▔"

# Vertical flip of the lower-block ramp for the bottom half of the mirror.
# Unicode has no full upper-block ramp, so these are nearest approximations.
_FLIP = {
    " ": " ", "▁": "▔", "▂": "▔", "▃": "▀", "▄": "▀",
    "▅": "▀", "▆": "█", "▇": "█", "█": "█",
}


def _resample(values, width):
    values = np.asarray(values, dtype=float)
    if len(values) == width:
        return values
    xs = np.linspace(0, len(values) - 1, width)
    return np.interp(xs, np.arange(len(values)), values)


def _brighten(rgb, factor):
    return tuple(min(255, int(c * factor)) for c in rgb)


def compose_frame(values, peaks, width, height, palette, beat=0.0, mirror=False):
    """Render a spectrum frame as a list of ANSI lines.

    `values`/`peaks` are per-band levels in [0, 1] (resampled to `width`).
    `mirror` radiates bars symmetrically from a horizontal center line.
    Returns exactly `height` strings, each `width` cells wide.
    """
    if mirror:
        return _compose_mirror(values, width, height, palette, beat)

    vals = _resample(values, width)
    pks = _resample(peaks, width)
    cols = [column_glyphs(v, height) for v in vals]
    # The gradient color depends only on the column, so sample it once per
    # column instead of once per cell (height x cheaper in the hot loop).
    col_base = [sample_gradient(palette, x / max(1, width - 1)) for x in range(width)]
    boost = min(0.6, 0.6 * beat)

    lines = []
    for top in range(height):
        row = height - 1 - top  # cell index counting up from the bottom
        parts = []
        for x in range(width):
            glyph = cols[x][row]
            if glyph == " ":
                peak_cell = min(height - 1, int(pks[x] * height))
                if pks[x] > 0.02 and peak_cell == row:
                    parts.append(truecolor_fg((235, 235, 245)) + CAP_GLYPH)
                else:
                    parts.append(" ")
                continue
            lift = row / height
            parts.append(truecolor_fg(_brighten(col_base[x], 1.0 + 0.4 * lift + boost)) + glyph)
        lines.append("".join(parts) + RESET)
    return lines


def _compose_mirror(values, width, height, palette, beat):
    vals = _resample(values, width)
    top_h = height // 2
    bot_h = height - top_h
    # Each half grows from the center line outward.
    top_cols = [column_glyphs(v, top_h) for v in vals]
    bot_cols = [[_FLIP[g] for g in column_glyphs(v, bot_h)] for v in vals]
    boost = min(0.6, 0.6 * beat)

    lines = []
    for r in range(height):
        in_top = r < top_h
        # distance from center drives which cell of each half we're drawing
        if in_top:
            cell = top_h - 1 - r          # 0 at center, grows toward top edge
        else:
            cell = r - top_h              # 0 at center, grows toward bottom edge
        parts = []
        for x in range(width):
            glyph = top_cols[x][cell] if in_top else bot_cols[x][cell]
            if glyph == " ":
                parts.append(" ")
                continue
            base = sample_gradient(palette, x / max(1, width - 1))
            lift = 1.0 - cell / max(1, top_h)   # brighter toward the center
            parts.append(truecolor_fg(_brighten(base, 1.0 + 0.4 * lift + boost)) + glyph)
        lines.append("".join(parts) + RESET)
    return lines


_HELP_ROWS = [
    ("space", "pause / resume"),
    ("→  n", "skip to next song"),
    ("↑  ↓", "volume up / down"),
    ("g", "cycle color palette"),
    ("m", "toggle mirror mode"),
    ("w", "toggle waveform scope"),
    ("h", "toggle this help"),
    ("q", "quit"),
]


def help_frame(width, height, palette):
    """A full-screen, centered help panel; `height` lines of `width` cells."""
    title = "J U K E B O X   —   C O N T R O L S"
    body = [title, ""]
    for key, desc in _HELP_ROWS:
        body.append(f"{key:>7}   {desc}")
    body.append("")

    accent = truecolor_fg(sample_gradient(palette, 0.5))
    dim = "\x1b[2m"
    start = max(0, (height - len(body)) // 2)
    lines = []
    for r in range(height):
        i = r - start
        if 0 <= i < len(body):
            text = body[i]
            pad_l = (width - len(text)) // 2
            pad_r = width - len(text) - pad_l
            color = accent if i == 0 else dim
            lines.append(" " * pad_l + color + text + RESET + " " * pad_r)
        else:
            lines.append(" " * width)
    return lines


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

class AutoGain:
    """Log-compress magnitudes and normalize by a slowly decaying running max,
    so quiet and loud passages both fill the display."""

    def __init__(self, decay=0.9995, floor=1e-6):
        self.decay = decay
        self.floor = floor
        self.peak = 1.0

    def __call__(self, bands):
        mag = np.log1p(bands)
        top = mag.max()
        self.peak = max(self.peak * self.decay, top, self.floor)
        return np.clip(mag / self.peak, 0.0, 1.0)


def _fmt_time(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def _header(title, pos, dur, width, palette):
    color = truecolor_fg(sample_gradient(palette, 0.6))
    left = f"♪ {title}"
    right = f"{_fmt_time(pos)} / {_fmt_time(dur)}"
    bar_w = max(4, width - len(_visible(left)) - len(right) - 3)
    filled = int(bar_w * (pos / dur)) if dur else 0
    bar = "━" * filled + "╸" + "─" * max(0, bar_w - filled - 1)
    line = f"{color}{left}{RESET} {bar} {right}"
    return line


def _footer(width, palette_name):
    keys = "h help · space pause · → skip · ↑↓ vol · g palette · m mirror · w scope · q quit"
    return f"\x1b[2m{keys}   [{palette_name}]{RESET}"


def _visible(s):
    import re
    return re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", s)


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


def run(engine, title, palette_name="trap", n_bins=72, fps=30):
    """Play `engine` and paint the spectrum until the song ends or the user
    quits/skips. Returns True if the user asked to quit the whole session."""
    edges = log_band_edges(n_bins, 40, 16000)
    gain = AutoGain()
    smoother = Smoother(n_bins, attack=0.55, decay=0.16)
    peaks = PeakHold(n_bins, decay=0.012)
    beat = BeatDetector(sensitivity=1.35)
    screen = Screen()
    pal_idx = PALETTE_ORDER.index(palette_name) if palette_name in PALETTE_ORDER else 0

    engine.start()
    quit_session = False
    skip = False
    mirror = False
    show_scope = False
    show_help = False
    frame_dt = 1.0 / fps
    scope_rows = 3

    with _raw_terminal():
        while not engine.finished and not skip and not quit_session:
            frame_start = time.time()
            width, rows = screen.size()

            window = engine.latest_window(2048)
            norm = gain(compute_bands(window, engine.samplerate, edges))
            level = smoother.update(norm)

            # --- input: keys, arrows -----------------------------------
            for event in parse_input(_read_pending()):
                kind = event[0]
                if kind == "arrow":
                    a = event[1]
                    if a == "A":
                        engine.nudge_volume(0.05)
                    elif a == "B":
                        engine.nudge_volume(-0.05)
                    elif a == "C":
                        skip = True
                else:  # key
                    k = event[1]
                    if k in ("q", "\x03"):
                        quit_session = True
                    elif k == " ":
                        engine.toggle_pause()
                    elif k == "n":
                        skip = True
                    elif k == "g":
                        pal_idx = (pal_idx + 1) % len(PALETTE_ORDER)
                    elif k == "m":
                        mirror = not mirror
                    elif k == "w":
                        show_scope = not show_scope
                    elif k == "h":
                        show_help = not show_help

            display = level
            cap = peaks.update(display)
            is_beat = beat.update(float(norm[: n_bins // 6].mean()))
            palette = PALETTES[PALETTE_ORDER[pal_idx]]

            # --- compose the frame -------------------------------------
            body_rows = rows - 2
            if show_help:
                body = help_frame(width, body_rows, palette)
            else:
                spec_rows = body_rows - (scope_rows if show_scope else 0)
                body = compose_frame(
                    display, cap, width, spec_rows, palette,
                    beat=1.0 if is_beat else 0.0, mirror=mirror,
                )
                if show_scope:
                    body += braille_waveform(window, width, scope_rows, gain=3.0)

            frame = (
                [_header(title, engine.position_seconds, engine.duration_seconds,
                         width, palette)]
                + body
                + [_footer(width, PALETTE_ORDER[pal_idx])]
            )
            screen.draw(frame)

            elapsed = time.time() - frame_start
            if elapsed < frame_dt:
                time.sleep(frame_dt - elapsed)

    engine.stop()
    return quit_session
