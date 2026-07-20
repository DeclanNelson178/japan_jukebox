"""ANSI truecolor terminal renderer.

Pure glyph/color math (block ramps, gradients, braille packing) lives here and
is unit tested. The actual screen writing (cursor moves, frame diffing) is a
thin layer on top.

Requires a 24-bit-color terminal (iTerm2, Ghostty, Kitty, WezTerm, ...).
"""

# Sub-cell vertical block ramp: index 0 (empty) .. 8 (full cell).
BLOCKS = " ▁▂▃▄▅▆▇█"

RESET = "\x1b[0m"
HIDE_CURSOR = "\x1b[?25l"
SHOW_CURSOR = "\x1b[?25h"
CLEAR = "\x1b[2J\x1b[H"


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
