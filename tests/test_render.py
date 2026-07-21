import re

import numpy as np

from render import (
    BLOCKS,
    RESET,
    braille_waveform,
    column_glyphs,
    frame_payload,
    braille_spectrum_frame,
    color_spectrum_frame,
    lerp_color,
    level_to_block,
    mirror_spectrum_frame,
    sample_gradient,
    spectrum_frame,
    truecolor_fg,
)

_PAL = [(0.0, (0, 0, 0)), (1.0, (255, 0, 0))]

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _strip(s):
    return ANSI.sub("", s)


def test_frame_payload_is_synchronized_and_homed():
    """The anti-flicker contract: one atomic present per frame. The terminal
    must be told to buffer the whole repaint (mode 2026) and the cursor homed,
    with no trailing newline that would scroll the frame up."""
    out = frame_payload(["ab", "cd"])
    assert out.startswith("\x1b[?2026h")   # begin synchronized update
    assert out.endswith("\x1b[?2026l")     # end synchronized update
    assert "\x1b[H" in out                 # cursor homed, not cleared
    assert "ab" in out and "cd" in out
    assert "\n\x1b[?2026l" not in out      # no trailing newline before present


def test_level_to_block_boundaries():
    assert level_to_block(0.0) == " "
    assert level_to_block(-1) == " "
    assert level_to_block(1.0) == "█"
    assert level_to_block(5) == "█"


def test_level_to_block_midpoints():
    assert level_to_block(0.5) == BLOCKS[4]  # ▄
    # a tiny positive fraction rounds to the smallest visible block
    assert level_to_block(0.1) == BLOCKS[1]  # ▁


def test_column_glyphs_full_and_empty():
    assert column_glyphs(1.0, 4) == ["█", "█", "█", "█"]
    assert column_glyphs(0.0, 4) == [" ", " ", " ", " "]


def test_column_glyphs_half_is_two_full_cells():
    # bottom-up: two full cells, then empty
    assert column_glyphs(0.5, 4) == ["█", "█", " ", " "]


def test_column_glyphs_partial_top_cell():
    # 0.3 of 4 rows = 1.2 cells -> one full cell + a small partial
    cells = column_glyphs(0.3, 4)
    assert cells[0] == "█"
    assert cells[1] == level_to_block(0.2)
    assert cells[2] == " " and cells[3] == " "


def test_truecolor_fg_escape():
    assert truecolor_fg((255, 128, 0)) == "\x1b[38;2;255;128;0m"
    assert RESET == "\x1b[0m"


def test_lerp_color_midpoint():
    assert lerp_color((0, 0, 0), (255, 255, 255), 0.5) == (128, 128, 128)


def test_sample_gradient_two_stops():
    stops = [(0.0, (0, 0, 0)), (1.0, (10, 20, 30))]
    assert sample_gradient(stops, 0.0) == (0, 0, 0)
    assert sample_gradient(stops, 1.0) == (10, 20, 30)
    assert sample_gradient(stops, 0.5) == (5, 10, 15)


def test_sample_gradient_multi_stop_picks_right_segment():
    stops = [(0.0, (0, 0, 0)), (0.5, (100, 0, 0)), (1.0, (100, 100, 0))]
    # 0.75 is halfway through the second segment
    assert sample_gradient(stops, 0.75) == (100, 50, 0)


def test_spectrum_frame_dimensions():
    lines = spectrum_frame([0.0, 0.5, 1.0], rows=4)
    assert len(lines) == 4
    for line in lines:
        assert len(line) == 3


def test_spectrum_frame_bottom_anchored():
    # a full column shows a block on every row; an empty column stays blank
    lines = spectrum_frame([1.0, 0.0], rows=3)
    for line in lines:
        assert line[0] == "█"
        assert line[1] == " "


def test_spectrum_frame_partial_column_grows_from_the_bottom():
    lines = spectrum_frame([0.5], rows=4)  # half height => bottom two rows
    assert lines[-1] == "█" and lines[-2] == "█"
    assert lines[0] == " " and lines[1] == " "


def test_color_spectrum_frame_visible_content_matches_plain():
    vals = [0.5, 1.0, 0.0]
    palette = [(0.0, (0, 0, 0)), (1.0, (255, 0, 0))]
    plain = spectrum_frame(vals, 4)
    colored = color_spectrum_frame(vals, 4, palette)
    assert [_strip(line) for line in colored] == plain


def test_color_spectrum_frame_is_a_vertical_gradient():
    # top row uses the high end of the gradient, bottom row the low end
    palette = [(0.0, (0, 0, 0)), (1.0, (255, 0, 0))]
    colored = color_spectrum_frame([1.0], 3, palette)
    assert "38;2;255;0;0" in colored[0]     # top = hot
    assert "38;2;0;0;0" in colored[-1]       # bottom = cool


def test_color_spectrum_frame_intensity_brightens_toward_white():
    # a beat pulse lifts the colors toward white
    palette = [(0.0, (100, 0, 0)), (1.0, (100, 0, 0))]
    normal = color_spectrum_frame([1.0], 1, palette, intensity=1.0)
    pulsed = color_spectrum_frame([1.0], 1, palette, intensity=1.5)
    assert "38;2;100;0;0" in normal[0]
    assert "38;2;100;0;0" not in pulsed[0]      # shifted brighter
    assert "38;2;178;128;128" in pulsed[0]      # halfway-ish toward white


def test_mirror_spectrum_frame_dimensions():
    lines = mirror_spectrum_frame([0.0, 0.5, 1.0], 6, _PAL)
    assert len(lines) == 6
    for line in lines:
        assert len(_strip(line)) == 3


def test_mirror_full_value_fills_every_cell():
    lines = mirror_spectrum_frame([1.0], 4, _PAL)
    assert all(_strip(line) == "█" for line in lines)


def test_mirror_zero_value_is_blank():
    lines = mirror_spectrum_frame([0.0], 5, _PAL)
    assert all(_strip(line) == " " for line in lines)


def test_mirror_is_vertically_symmetric():
    lines = [_strip(line) for line in mirror_spectrum_frame([0.5], 6, _PAL)]
    filled = [line[0] != " " for line in lines]
    assert filled == filled[::-1]        # top half mirrors the bottom half


def test_mirror_intensity_brightens_toward_white():
    plain = mirror_spectrum_frame([1.0], 2, [(0.0, (100, 0, 0)), (1.0, (100, 0, 0))])
    bright = mirror_spectrum_frame([1.0], 2, [(0.0, (100, 0, 0)), (1.0, (100, 0, 0))],
                                   intensity=1.5)
    assert "38;2;100;0;0" in plain[0]
    assert "38;2;100;0;0" not in bright[0]


def test_braille_spectrum_frame_dimensions_and_charset():
    # two dot-columns per character cell
    lines = braille_spectrum_frame([0.0, 0.5, 1.0, 0.2], 5, _PAL)
    assert len(lines) == 5
    for line in lines:
        vis = _strip(line)
        assert len(vis) == 2                     # 4 dot-columns -> 2 cells
        assert all(0x2800 <= ord(ch) <= 0x28FF for ch in vis)


def test_braille_spectrum_frame_full_column_is_all_dots():
    lines = braille_spectrum_frame([1.0, 1.0], 3, _PAL)
    assert all(_strip(line) == chr(0x28FF) for line in lines)  # every dot set


def test_braille_spectrum_frame_zero_is_blank_braille():
    lines = braille_spectrum_frame([0.0, 0.0], 3, _PAL)
    assert all(_strip(line) == chr(0x2800) for line in lines)


def test_braille_spectrum_frame_fills_from_the_bottom():
    # a half-height column lights the bottom row, not the top
    lines = [_strip(line) for line in braille_spectrum_frame([0.5, 0.5], 4, _PAL)]
    assert ord(lines[-1]) != 0x2800     # bottom row has dots
    assert ord(lines[0]) == 0x2800      # top row empty


def test_braille_waveform_dimensions():
    samples = np.zeros(64, dtype=np.float32)
    rows = braille_waveform(samples, width=20, rows=3)
    assert len(rows) == 3
    for row in rows:
        assert len(row) == 20


def test_braille_waveform_all_chars_are_braille():
    samples = np.sin(np.linspace(0, 6.28, 128)).astype(np.float32)
    rows = braille_waveform(samples, width=16, rows=4)
    for row in rows:
        for ch in row:
            assert 0x2800 <= ord(ch) <= 0x28FF


def test_braille_waveform_flat_signal_lives_on_center_row():
    samples = np.zeros(64, dtype=np.float32)
    rows = braille_waveform(samples, width=12, rows=4)
    # a flat zero signal draws along the vertical middle, not the edges
    assert rows[0] == " " * 12 or all(ord(c) == 0x2800 for c in rows[0])
    middle_has_dots = any(ord(c) != 0x2800 for c in rows[1] + rows[2])
    assert middle_has_dots
