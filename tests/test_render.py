import numpy as np

from render import (
    BLOCKS,
    RESET,
    braille_waveform,
    column_glyphs,
    lerp_color,
    level_to_block,
    sample_gradient,
    truecolor_fg,
)


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
