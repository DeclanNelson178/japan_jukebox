import re

import numpy as np

import os
import threading

from visualizer import (
    PALETTES,
    WaveEnvelope,
    compose_frame,
    compose_wave,
    help_frame,
    parse_input,
    _read_pending,
)

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


# --- mirror mode ----------------------------------------------------------

def test_mirror_frame_dimensions():
    pal = PALETTES["trap"]
    lines = compose_frame([0.5] * 8, [0.5] * 8, 8, 10, pal, mirror=True)
    assert len(lines) == 10
    for line in lines:
        assert len(visible(line)) == 8


def test_mirror_full_values_fill_top_and_bottom():
    pal = PALETTES["trap"]
    lines = compose_frame([1.0] * 6, [1.0] * 6, 6, 8, pal, mirror=True)
    assert visible(lines[0]) == "█" * 6    # topmost row lit
    assert visible(lines[-1]) == "█" * 6   # bottommost row lit


def test_mirror_zero_values_blank():
    pal = PALETTES["trap"]
    lines = compose_frame([0.0] * 6, [0.0] * 6, 6, 8, pal, mirror=True)
    for line in lines:
        assert visible(line).strip() == ""


def test_mirror_energy_radiates_from_center():
    pal = PALETTES["trap"]
    # a small value should light rows near the center, not the edges
    lines = compose_frame([0.25] * 6, [0.0] * 6, 6, 8, pal, mirror=True)
    assert visible(lines[0]).strip() == ""    # top edge empty
    assert visible(lines[-1]).strip() == ""   # bottom edge empty
    mid = "".join(visible(l) for l in lines[3:5])
    assert mid.strip() != ""                   # center lit


# --- help overlay ---------------------------------------------------------

def test_help_frame_dimensions_and_content():
    lines = help_frame(60, 20, PALETTES["trap"])
    assert len(lines) == 20
    for line in lines:
        assert len(visible(line)) == 60
    blob = " ".join(visible(l) for l in lines).lower()
    assert "quit" in blob and "pause" in blob and "palette" in blob


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


# --- wave renderer --------------------------------------------------------

def test_wave_dimensions():
    pal = PALETTES["trap"]
    lines = compose_wave([0.5] * 8, 8, 10, pal)
    assert len(lines) == 10
    for line in lines:
        assert len(visible(line)) == 8


def test_wave_silence_is_blank():
    pal = PALETTES["trap"]
    lines = compose_wave([0.0] * 6, 6, 8, pal)
    for line in lines:
        assert visible(line).strip() == ""


def test_wave_fills_from_center_outward():
    pal = PALETTES["trap"]
    # a small amplitude lights rows near the center axis, not the edges
    lines = compose_wave([0.25] * 6, 6, 8, pal)
    assert visible(lines[0]).strip() == ""     # top edge empty
    assert visible(lines[-1]).strip() == ""    # bottom edge empty
    middle = "".join(visible(l) for l in lines[3:5])
    assert middle.strip() != ""                # axis lit


def test_wave_full_amplitude_reaches_both_edges():
    pal = PALETTES["trap"]
    lines = compose_wave([1.0] * 6, 6, 8, pal)
    assert visible(lines[0]) == "█" * 6
    assert visible(lines[-1]) == "█" * 6


# --- wave envelope --------------------------------------------------------

def test_envelope_silence_is_zero():
    env = WaveEnvelope()
    assert env.update(np.zeros(1024)) == 0.0


def test_envelope_rises_and_normalizes_toward_full():
    env = WaveEnvelope()
    loud = np.full(1024, 0.4, dtype=np.float32)
    out = 0.0
    for _ in range(40):
        out = env.update(loud)
    assert out > 0.9          # a sustained level normalizes to fill the axis


def test_envelope_output_bounded():
    env = WaveEnvelope()
    rng = np.linspace(-1, 1, 1024)
    for _ in range(50):
        v = env.update(rng)
        assert 0.0 <= v <= 1.0


def test_envelope_attack_faster_than_release():
    """A jump up should move more per step than the same-sized drop back."""
    up = WaveEnvelope()
    # prime the running peak so targets are ~1.0 on loud, ~0 on silence
    loud = np.full(1024, 0.5, dtype=np.float32)
    for _ in range(30):
        up.update(loud)
    settled = up.value
    rise_step = up.update(loud) - settled          # already near top, tiny
    # fresh envelope: measure one attack step from rest vs one release step
    env = WaveEnvelope()
    env.peak = 0.5                                   # fixed reference
    a0 = env.value
    env.update(loud)                                 # one attack step
    attack_delta = env.value - a0
    env.value = 1.0
    env.update(np.zeros(1024))                        # one release step
    release_delta = env.value - 1.0                  # negative
    assert attack_delta > abs(release_delta)


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
