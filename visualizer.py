"""The visualizer: turns live audio into a mirrored... no — a bottom-anchored
truecolor spectrum with floating peak caps, gradient color, and beat pulse.

`compose_frame` is pure and unit tested. Everything below the PALETTES/compose
line does terminal + keyboard I/O and is exercised live rather than in tests.
"""

import contextlib
import os
import select
import sys
import termios
import time
import tty

import numpy as np

from render import RESET, column_glyphs, sample_gradient, truecolor_fg
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


def _resample(values, width):
    values = np.asarray(values, dtype=float)
    if len(values) == width:
        return values
    xs = np.linspace(0, len(values) - 1, width)
    return np.interp(xs, np.arange(len(values)), values)


def _brighten(rgb, factor):
    return tuple(min(255, int(c * factor)) for c in rgb)


def compose_frame(values, peaks, width, height, palette, beat=0.0):
    """Render a bottom-anchored spectrum frame as a list of ANSI lines.

    `values`/`peaks` are per-band levels in [0, 1] (resampled to `width`).
    Returns exactly `height` strings, each `width` cells wide.
    """
    vals = _resample(values, width)
    pks = _resample(peaks, width)
    cols = [column_glyphs(v, height) for v in vals]
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
            base = sample_gradient(palette, x / max(1, width - 1))
            lift = row / height
            parts.append(truecolor_fg(_brighten(base, 1.0 + 0.4 * lift + boost)) + glyph)
        lines.append("".join(parts) + RESET)
    return lines


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
    keys = "space pause · → skip · ↑↓ vol · g palette · q quit"
    return f"\x1b[2m{keys}   [{palette_name}]{RESET}"


def _visible(s):
    import re
    return re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", s)


class Screen:
    def size(self):
        cols, rows = os.get_terminal_size()
        return cols, rows

    def draw(self, lines):
        # Home the cursor and repaint. Clear each line to EOL to avoid ghosts,
        # and join with newlines *between* lines only — a trailing newline on
        # the bottom row would scroll the whole frame up every repaint.
        body = "\x1b[K\n".join(lines)
        sys.stdout.write("\x1b[H" + body + "\x1b[K\x1b[J")
        sys.stdout.flush()


@contextlib.contextmanager
def _raw_terminal():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        sys.stdout.write("\x1b[?25l\x1b[2J")  # hide cursor, clear
        sys.stdout.flush()
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write("\x1b[?25h\x1b[0m\x1b[2J\x1b[H")  # restore
        sys.stdout.flush()


def _getch():
    """Non-blocking single-key read; returns '' if nothing pending."""
    if select.select([sys.stdin], [], [], 0)[0]:
        ch = sys.stdin.read(1)
        if ch == "\x1b" and select.select([sys.stdin], [], [], 0)[0]:
            ch += sys.stdin.read(2)  # arrow keys: ESC [ A/B/C/D
        return ch
    return ""


def run(engine, title, palette_name="trap", n_bins=72, fps=60):
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
    frame_dt = 1.0 / fps
    with _raw_terminal():
        while not engine.finished:
            frame_start = time.time()
            window = engine.latest_window(2048)
            norm = gain(compute_bands(window, engine.samplerate, edges))
            level = smoother.update(norm)
            cap = peaks.update(level)
            is_beat = beat.update(float(norm[: n_bins // 6].mean()))

            width, rows = screen.size()
            spectrum = compose_frame(
                level, cap, width, rows - 2,
                PALETTES[PALETTE_ORDER[pal_idx]],
                beat=1.0 if is_beat else 0.0,
            )
            frame = (
                [_header(title, engine.position_seconds, engine.duration_seconds,
                         width, PALETTES[PALETTE_ORDER[pal_idx]])]
                + spectrum
                + [_footer(width, PALETTE_ORDER[pal_idx])]
            )
            screen.draw(frame)

            key = _getch()
            if key in ("q", "\x03"):  # q or Ctrl-C
                quit_session = True
                break
            elif key == " ":
                engine.toggle_pause()
            elif key in ("\x1b[C", "n"):  # right arrow / n -> skip
                break
            elif key == "\x1b[A":  # up arrow -> louder
                engine.nudge_volume(0.05)
            elif key == "\x1b[B":  # down arrow -> quieter
                engine.nudge_volume(-0.05)
            elif key == "g":
                pal_idx = (pal_idx + 1) % len(PALETTE_ORDER)

            elapsed = time.time() - frame_start
            if elapsed < frame_dt:
                time.sleep(frame_dt - elapsed)

    engine.stop()
    return quit_session
