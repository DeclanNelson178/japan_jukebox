import numpy as np

from spectrum import (
    BeatDetector,
    PeakHold,
    Smoother,
    compute_bands,
    log_band_edges,
    to_display,
)


def test_log_band_edges_shape_and_monotonic():
    edges = log_band_edges(16, 40, 16000)
    assert len(edges) == 17
    assert np.all(np.diff(edges) > 0)
    assert np.isclose(edges[0], 40)
    assert np.isclose(edges[-1], 16000)


def test_log_band_edges_are_log_spaced():
    edges = log_band_edges(4, 100, 1600)
    # log-spaced => constant ratio between consecutive edges
    ratios = edges[1:] / edges[:-1]
    assert np.allclose(ratios, ratios[0])


def test_compute_bands_lights_up_band_containing_tone():
    sr = 44100
    n = 4096
    t = np.arange(n) / sr
    tone = np.sin(2 * np.pi * 440 * t).astype(np.float32)
    edges = log_band_edges(24, 40, 16000)
    bands = compute_bands(tone, sr, edges)

    peak = int(np.argmax(bands))
    assert edges[peak] <= 440 < edges[peak + 1]


def test_to_display_zeros_stay_zero():
    # silence must read as empty bars, not floor noise blown up to full height
    out = to_display(np.zeros(4), n=8192)
    assert np.allclose(out, 0.0)


def test_to_display_monotonic_and_clipped():
    bands = np.array([0.0, 1.0, 10.0, 1e6])
    out = to_display(bands, n=8192, gain=20.0)
    assert np.all(np.diff(out) >= 0)     # louder band => taller bar
    assert out[0] == 0.0
    assert np.isclose(out[-1], 1.0)      # a huge magnitude saturates at full


def test_to_display_curve_boosts_quiet_bands():
    # the sub-linear curve lifts a quiet band so it stays visible
    bands = np.array([1.0])
    linear = to_display(bands, n=8192, gain=1.0, curve=1.0)
    boosted = to_display(bands, n=8192, gain=1.0, curve=0.5)
    assert boosted[0] > linear[0]


def test_smoother_attack_then_decay():
    sm = Smoother(size=1, attack=0.5, decay=0.1)
    # rising value uses the fast attack coefficient
    out = sm.update(np.array([1.0]))
    assert np.isclose(out[0], 0.5)
    # falling value uses the slow decay coefficient
    out = sm.update(np.array([0.0]))
    assert np.isclose(out[0], 0.5 - 0.5 * 0.1)


def test_peak_hold_holds_then_decays():
    ph = PeakHold(size=1, decay=0.02)
    assert np.isclose(ph.update(np.array([1.0]))[0], 1.0)
    # a lower value leaves the peak decaying slowly, not snapping down
    assert np.isclose(ph.update(np.array([0.0]))[0], 0.98)


def test_peak_hold_jumps_up_to_new_max():
    ph = PeakHold(size=1, decay=0.02)
    ph.update(np.array([0.3]))
    assert np.isclose(ph.update(np.array([0.9]))[0], 0.9)


def test_beat_detector_fires_on_spike_not_on_steady():
    bd = BeatDetector(sensitivity=1.5, memory=0.8)
    # steady low energy builds an average without firing
    for _ in range(20):
        assert bd.update(1.0) is False
    # a sudden jump well above the running average is a beat
    assert bd.update(5.0) is True
