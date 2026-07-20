import numpy as np
import pytest

from engine import AudioEngine, to_mono


def test_to_mono_passes_through_1d():
    sig = np.array([1.0, -1.0, 0.5], dtype=np.float32)
    assert np.allclose(to_mono(sig), sig)


def test_to_mono_averages_stereo():
    stereo = np.array([[1.0, 0.0], [0.0, 1.0], [-1.0, 1.0]], dtype=np.float32)
    assert np.allclose(to_mono(stereo), [0.5, 0.5, 0.0])


def test_next_block_advances_cursor_and_returns_samples():
    signal = np.arange(10, dtype=np.float32)
    eng = AudioEngine(signal, samplerate=10, blocksize=4)

    first = eng._next_block(4)
    assert np.allclose(first, [0, 1, 2, 3])
    assert np.isclose(eng.position_seconds, 0.4)

    second = eng._next_block(4)
    assert np.allclose(second, [4, 5, 6, 7])


def test_next_block_zero_pads_and_marks_finished_at_end():
    signal = np.arange(6, dtype=np.float32)
    eng = AudioEngine(signal, samplerate=6, blocksize=4)

    eng._next_block(4)  # consumes 0..3
    assert not eng.finished

    tail = eng._next_block(4)  # only 4,5 remain -> pad two zeros
    assert np.allclose(tail, [4, 5, 0, 0])
    assert eng.finished


def test_duration_seconds():
    signal = np.zeros(44100, dtype=np.float32)
    eng = AudioEngine(signal, samplerate=22050, blocksize=1024)
    assert np.isclose(eng.duration_seconds, 2.0)


def test_latest_window_left_pads_when_short():
    signal = np.arange(10, dtype=np.float32)
    eng = AudioEngine(signal, samplerate=10, blocksize=4)

    eng._next_block(4)  # feed 0,1,2,3 into the tap
    win = eng.latest_window(6)
    assert win.shape == (6,)
    # only 4 samples seen so far -> two leading zeros
    assert np.allclose(win, [0, 0, 0, 1, 2, 3])


def test_latest_window_returns_most_recent_when_full():
    signal = np.arange(20, dtype=np.float32)
    eng = AudioEngine(signal, samplerate=20, blocksize=8)

    eng._next_block(8)  # 0..7
    eng._next_block(8)  # 8..15
    win = eng.latest_window(4)
    assert np.allclose(win, [12, 13, 14, 15])
