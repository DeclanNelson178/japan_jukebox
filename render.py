"""ANSI truecolor terminal renderer.

Pure glyph/color math (block ramps, gradients, braille packing) lives here and
is unit tested. The actual screen writing (cursor moves, frame diffing) is a
thin layer on top.

Requires a 24-bit-color terminal (iTerm2, Ghostty, Kitty, WezTerm, ...).
"""

import numpy as np

# Sub-cell vertical block ramp: index 0 (empty) .. 8 (full cell).
BLOCKS = " ▁▂▃▄▅▆▇█"

# Braille dot bit values, indexed [column 0..1][row 0..3]. A braille cell packs
# a 2x4 dot grid, giving 8x the resolution of a normal character cell.
BRAILLE_DOTS = (
    (0x01, 0x02, 0x04, 0x40),
    (0x08, 0x10, 0x20, 0x80),
)

RESET = "\x1b[0m"
HIDE_CURSOR = "\x1b[?25l"
SHOW_CURSOR = "\x1b[?25h"
CLEAR = "\x1b[2J\x1b[H"
HOME = "\x1b[H"

# Synchronized-update (DEC private mode 2026): the terminal buffers everything
# between BSU and ESU and presents it in a single atomic frame. Without it a
# large repaint is shown as it streams in, which reads as tearing / flicker.
SYNC_START = "\x1b[?2026h"
SYNC_END = "\x1b[?2026l"


def frame_payload(lines):
    """One atomic screen repaint from a list of full-width lines.

    Homes the cursor and overwrites in place (no screen clear, which would
    flash). Each line is cleared to end-of-line to erase any ghost, and the
    tail of the screen is cleared for shorter frames. No trailing newline —
    that would scroll the whole frame up on every repaint.
    """
    body = "\x1b[K\n".join(lines)
    return SYNC_START + HOME + body + "\x1b[K\x1b[J" + SYNC_END


def level_to_block(fraction):
    """Map a fractional cell height in [0, 1] to a partial block glyph."""
    if fraction <= 0:
        return BLOCKS[0]
    if fraction >= 1:
        return BLOCKS[8]
    return BLOCKS[round(fraction * 8)]


def column_glyphs(value, rows):
    """Glyphs for a vertical bar of fractional height `value` over `rows` cells.

    Returned bottom-up: full '█' cells, one partial cell, then spaces.
    """
    total = max(0.0, value) * rows
    full = int(total)
    partial = total - full
    cells = []
    for r in range(rows):
        if r < full:
            cells.append(BLOCKS[8])
        elif r == full:
            cells.append(level_to_block(partial))
        else:
            cells.append(BLOCKS[0])
    return cells


def truecolor_fg(rgb):
    """24-bit foreground color escape for an (r, g, b) tuple."""
    r, g, b = rgb
    return f"\x1b[38;2;{int(r)};{int(g)};{int(b)}m"


def lerp_color(c1, c2, t):
    """Linear interpolate between two rgb tuples; returns rounded ints."""
    return tuple(round(a + (b - a) * t) for a, b in zip(c1, c2))


def sample_gradient(stops, t):
    """Sample a multi-stop gradient at t in [0, 1].

    `stops` is an ascending list of (position, (r, g, b)).
    """
    t = min(1.0, max(0.0, t))
    if t <= stops[0][0]:
        return tuple(stops[0][1])
    if t >= stops[-1][0]:
        return tuple(stops[-1][1])
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if p0 <= t <= p1:
            local = (t - p0) / (p1 - p0) if p1 > p0 else 0.0
            return lerp_color(c0, c1, local)
    return tuple(stops[-1][1])


def braille_waveform(samples, width, rows, gain=1.0):
    """Draw a waveform as braille dots: `rows` strings of `width` cells each.

    The samples (expected in ~[-1, 1]) are drawn as a single dot per horizontal
    dot-column around the vertical middle, at 8x the character-cell resolution.
    """
    samples = np.asarray(samples, dtype=float)
    dot_cols = width * 2
    dot_rows = rows * 4
    xs = np.linspace(0, len(samples) - 1, dot_cols)
    ys = np.interp(xs, np.arange(len(samples)), samples)
    mid = (dot_rows - 1) / 2.0

    grid = [[0] * width for _ in range(rows)]
    for i in range(dot_cols):
        val = max(-1.0, min(1.0, ys[i] * gain))
        dot_y = int(round(mid - val * mid))
        dot_y = max(0, min(dot_rows - 1, dot_y))
        cell_col, sub_col = divmod(i, 2)
        cell_row, sub_row = divmod(dot_y, 4)
        grid[cell_row][cell_col] |= BRAILLE_DOTS[sub_col][sub_row]

    return ["".join(chr(0x2800 + bits) for bits in row) for row in grid]
