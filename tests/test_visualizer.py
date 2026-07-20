import re

from visualizer import PALETTES, compose_frame

ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")


def visible(line):
    return ANSI.sub("", line)


def test_frame_has_correct_dimensions():
    pal = PALETTES["trap"]
    lines = compose_frame([0.5] * 16, [0.5] * 16, width=16, height=8, palette=pal)
    assert len(lines) == 8
    for line in lines:
        assert len(visible(line)) == 16


def test_full_values_fill_every_cell():
    pal = PALETTES["trap"]
    lines = compose_frame([1.0] * 10, [1.0] * 10, width=10, height=5, palette=pal)
    for line in lines:
        assert visible(line) == "█" * 10


def test_zero_values_render_blank():
    pal = PALETTES["trap"]
    lines = compose_frame([0.0] * 10, [0.0] * 10, width=10, height=5, palette=pal)
    for line in lines:
        assert visible(line).strip() == ""


def test_bars_grow_from_the_bottom():
    pal = PALETTES["trap"]
    # half height should fill the lower rows, leave the upper rows empty
    lines = compose_frame([0.5] * 8, [0.5] * 8, width=8, height=8, palette=pal)
    assert visible(lines[0]).strip() == ""   # top row empty
    assert visible(lines[-1]) == "█" * 8      # bottom row full


def test_resamples_when_bands_shorter_than_width():
    pal = PALETTES["trap"]
    lines = compose_frame([1.0, 1.0], [1.0, 1.0], width=20, height=4, palette=pal)
    for line in lines:
        assert len(visible(line)) == 20
