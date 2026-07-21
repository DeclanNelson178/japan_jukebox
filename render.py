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


def spectrum_frame(values, rows):
    """Bottom-anchored bar spectrum: `rows` strings, top-to-bottom.

    `values` is one fractional height in [0, 1] per column. Each column is a
    stack of sub-cell blocks (see `column_glyphs`); the returned lines read from
    the top of the display down, so the last line is the baseline.
    """
    cols = [column_glyphs(v, rows) for v in values]  # each bottom-up, len == rows
    return ["".join(col[r] for col in cols) for r in range(rows - 1, -1, -1)]


def color_spectrum_frame(values, rows, palette, intensity=1.0):
    """`spectrum_frame` with a vertical palette gradient — one color per row.

    A cell's color depends only on its height, so each output line takes a
    single gradient sample (bottom row = low end, top row = high end) and one
    color escape — cheap to draw. Taller parts of every bar read as the hot end
    of the palette, giving the flame/spectrum look. `intensity` > 1 lifts the
    colors toward white for a beat-pulse flash.
    """
    lines = spectrum_frame(values, rows)
    span = max(1, rows - 1)
    lift = min(1.0, max(0.0, intensity - 1.0))
    out = []
    for r, line in enumerate(lines):
        frac = (rows - 1 - r) / span  # 1.0 at the top row, 0.0 at the baseline
        rgb = sample_gradient(palette, frac)
        if lift:
            rgb = lerp_color(rgb, (255, 255, 255), lift)
        out.append(truecolor_fg(rgb) + line + RESET)
    return out


_BRAILLE_FULL_COL = (
    BRAILLE_DOTS[0][0] | BRAILLE_DOTS[0][1] | BRAILLE_DOTS[0][2] | BRAILLE_DOTS[0][3],
    BRAILLE_DOTS[1][0] | BRAILLE_DOTS[1][1] | BRAILLE_DOTS[1][2] | BRAILLE_DOTS[1][3],
)


def braille_spectrum_frame(values, rows, palette, intensity=1.0):
    """Bottom-anchored spectrum drawn in braille dots for an extra-smooth edge.

    Braille packs a 2x4 dot grid per character cell, so two `values` map to one
    cell and the top edge resolves at 4x the vertical / 2x the horizontal of the
    block bars — the tops read as a fine curve. Same vertical palette gradient
    and `intensity` beat-pulse brightening as `color_spectrum_frame`.
    """
    n = len(values)
    width = (n + 1) // 2
    dot_rows = rows * 4
    grid = [[0] * width for _ in range(rows)]
    for i in range(n):
        v = max(0.0, min(1.0, float(values[i])))
        filled = int(round(v * dot_rows))
        cell_col, sub_col = divmod(i, 2)
        full_cells, rem = divmod(filled, 4)
        for cell in range(full_cells):
            grid[rows - 1 - cell][cell_col] |= _BRAILLE_FULL_COL[sub_col]
        if rem and full_cells < rows:
            top = rows - 1 - full_cells
            for sr in range(rem):                       # fill up from the bottom
                grid[top][cell_col] |= BRAILLE_DOTS[sub_col][3 - sr]

    lift = min(1.0, max(0.0, intensity - 1.0))
    span = max(1, rows - 1)
    lines = []
    for r in range(rows):
        frac = (rows - 1 - r) / span
        rgb = sample_gradient(palette, frac)
        if lift:
            rgb = lerp_color(rgb, (255, 255, 255), lift)
        row = "".join(chr(0x2800 + bits) for bits in grid[r])
        lines.append(truecolor_fg(rgb) + row + RESET)
    return lines


def mirror_spectrum_frame(values, rows, palette, intensity=1.0):
    """Rounded spectrum mirrored around a horizontal center axis (waveform look).

    Each column grows symmetrically out from the middle. The fractional tip is a
    half block that fills toward the center — `▄` above the axis, `▀` below — so
    both edges taper inward; body cells are full blocks. Color is a center-out
    gradient (axis = low end, edges = high end), one sample per row, with the
    same `intensity` beat-pulse brightening as `color_spectrum_frame`.
    """
    half = rows // 2
    has_center = rows % 2 == 1
    cols = []
    for v in values:
        v = max(0.0, min(1.0, float(v)))
        ext = v * half
        full = int(ext)
        tip = (ext - full) >= 0.5
        col = []
        for d in range(half, 0, -1):                     # top: outer -> center
            col.append("█" if d <= full else ("▄" if d == full + 1 and tip else " "))
        if has_center:
            col.append("█" if v > 0 else " ")
        for d in range(1, half + 1):                     # bottom: center -> outer
            col.append("█" if d <= full else ("▀" if d == full + 1 and tip else " "))
        cols.append(col)

    lift = min(1.0, max(0.0, intensity - 1.0))
    center = (rows - 1) / 2.0
    lines = []
    for r in range(rows):
        dist = abs(r - center) / center if center else 0.0  # 0 axis .. 1 edge
        rgb = sample_gradient(palette, dist)
        if lift:
            rgb = lerp_color(rgb, (255, 255, 255), lift)
        row = "".join(col[r] for col in cols)
        lines.append(truecolor_fg(rgb) + row + RESET)
    return lines


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
