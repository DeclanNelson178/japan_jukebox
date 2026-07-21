import os
import re
import threading

from visualizer import (
    PALETTES,
    PALETTE_ORDER,
    parse_input,
    _help_lines,
    _idle_body,
    _read_pending,
)

ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")


def visible(line):
    return ANSI.sub("", line)


# --- input parsing --------------------------------------------------------

def test_parse_input_plain_keys():
    assert parse_input("q") == [("key", "q")]
    assert parse_input(" g") == [("key", " "), ("key", "g")]


def test_parse_input_arrows():
    assert parse_input("\x1b[A") == [("arrow", "A")]
    assert parse_input("\x1b[B\x1b[C") == [("arrow", "B"), ("arrow", "C")]


def test_parse_input_sgr_mouse():
    # ESC [ < button ; x ; y M   (motion at column 42, row 7)
    assert parse_input("\x1b[<35;42;7M") == [("mouse", 42, 7)]


def test_parse_input_mixed_stream():
    evts = parse_input("g\x1b[<35;10;3Mq")
    assert evts == [("key", "g"), ("mouse", 10, 3), ("key", "q")]


# --- V0 playback body -----------------------------------------------------

def test_idle_body_dimensions():
    lines = _idle_body(paused=False, width=30, height=7, palette=PALETTES["trap"])
    assert len(lines) == 7
    for line in lines:
        assert len(visible(line)) == 30


def test_idle_body_shows_play_and_pause_state():
    playing = " ".join(visible(l) for l in
                        _idle_body(False, 30, 7, PALETTES["trap"]))
    paused = " ".join(visible(l) for l in
                      _idle_body(True, 30, 7, PALETTES["trap"]))
    assert "playing" in playing and "paused" not in playing
    assert "paused" in paused and "playing" not in paused


# --- palettes -------------------------------------------------------------

def test_palette_order_matches_palettes():
    # Every cyclable name resolves, and nothing defined is left unreachable.
    assert set(PALETTE_ORDER) == set(PALETTES)
    assert len(PALETTE_ORDER) == len(PALETTES)


def test_new_cool_palettes_present():
    for name in ("vaporwave", "cyber", "miami", "matrix"):
        assert name in PALETTES, f"missing palette: {name}"
        assert name in PALETTE_ORDER


def test_palettes_are_well_formed_gradients():
    for name, stops in PALETTES.items():
        assert len(stops) >= 2, f"{name} needs at least two stops"
        positions = [p for p, _ in stops]
        assert positions[0] == 0.0, f"{name} must start at 0.0"
        assert positions[-1] == 1.0, f"{name} must end at 1.0"
        assert positions == sorted(positions), f"{name} stops must ascend"
        assert len(set(positions)) == len(positions), f"{name} has duplicate stops"
        for _, rgb in stops:
            assert len(rgb) == 3, f"{name} stop is not an rgb triple"
            for c in rgb:
                assert 0 <= c <= 255, f"{name} channel out of range: {c}"


# --- help overlay ---------------------------------------------------------

def test_help_lines_dimensions_and_content():
    lines = _help_lines(60, 12, PALETTES["trap"])
    assert len(lines) == 12
    for line in lines:
        assert len(visible(line)) == 60
    text = " ".join(visible(line) for line in lines).lower()
    for word in ("pause", "skip", "volume", "sync", "palette", "quit"):
        assert word in text


# --- non-blocking input reads ---------------------------------------------

def test_read_pending_returns_available_without_blocking():
    """The freeze bug: a single byte must come back at once, not block waiting
    for a full buffer's worth of input."""
    r, w = os.pipe()
    try:
        os.write(w, b"abc")
        result = {}
        t = threading.Thread(target=lambda: result.setdefault("v", _read_pending(r)))
        t.start()
        t.join(timeout=1.0)
        assert not t.is_alive(), "_read_pending blocked on a partial read"
        assert result["v"] == "abc"
    finally:
        os.close(r)
        os.close(w)


def test_read_pending_empty_when_nothing_available():
    r, w = os.pipe()
    try:
        assert _read_pending(r) == ""
    finally:
        os.close(r)
        os.close(w)
