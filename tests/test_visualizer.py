import os
import re
import threading

from visualizer import (
    PALETTES,
    parse_input,
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
