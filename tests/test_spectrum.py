import numpy as np

from spectrum import (
    AutoSens,
    BeatDetector,
    Gravity,
    PeakHold,
    Smoother,
    compute_bands,
    frequency_tilt,
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


def test_compute_bands_fills_bands_narrower_than_bin_spacing():
    # 8192 @ 44.1k => ~5.4 Hz bins; many 40-120 Hz log bands are narrower than
    # that and contain no bin. They must be interpolated, not left dead at 0.
    sr = 44100
    n = 8192
    t = np.arange(n) / sr
    sig = np.sin(2 * np.pi * 60 * t).astype(np.float32)
    edges = log_band_edges(40, 40, 120)
    bands = compute_bands(sig, sr, edges)
    assert not np.any(bands == 0.0)


def test_frequency_tilt_boosts_highs_and_is_unity_at_fmin():
    # music falls off ~1/f; the tilt lifts high bands so treble stays visible
    # above the noise floor. Unity at fmin keeps the bass level unchanged.
    centers = np.array([40.0, 400.0, 4000.0])
    tilt = frequency_tilt(centers, fmin=40.0, slope=0.5)
    assert np.isclose(tilt[0], 1.0)
    assert np.all(np.diff(tilt) > 0)
    assert np.isclose(tilt[2], 100.0 ** 0.5)  # 4000/40 = 100x up


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
    linear = to_display(bands, n=8192, gain=1.0, curve=1.0, noise_floor=0.0)
    boosted = to_display(bands, n=8192, gain=1.0, curve=0.5, noise_floor=0.0)
    assert boosted[0] > linear[0]


def test_noise_floor_is_absolute_autosens_cannot_amplify_subfloor():
    # a band below the floor stays gated out no matter how high autosens drives
    # sens — otherwise a quiet intro's noise gets amplified off the top.
    bands = np.array([1.0])  # tiny magnitude, well below the floor
    out = to_display(bands, n=8192, gain=20.0, noise_floor=0.2, sens=50.0)
    assert out[0] == 0.0


def test_to_display_noise_floor_gates_quiet_to_zero():
    # below the floor reads as empty (no permanent solid baseline); a loud band
    # still saturates at full height.
    quiet = to_display(np.array([1.0]), n=8192, gain=20.0, noise_floor=0.1)
    assert quiet[0] == 0.0
    loud = to_display(np.array([1e6]), n=8192, gain=20.0, noise_floor=0.1)
    assert np.isclose(loud[0], 1.0)


def test_gravity_rises_fast_but_not_instant():
    # a rising bar eases up toward the new height (temporal smoothing on rise)
    g = Gravity(size=1, attack=0.5, gravity=0.1)
    assert np.isclose(g.update(np.array([1.0]))[0], 0.5)


def test_gravity_fall_accelerates():
    # once falling, each frame drops further than the last (parabolic gravity)
    g = Gravity(size=1, attack=1.0, gravity=0.1)
    assert np.isclose(g.update(np.array([1.0]))[0], 1.0)   # snaps up instantly
    assert np.isclose(g.update(np.array([0.0]))[0], 0.9)   # fall step 1: -0.1*1
    assert np.isclose(g.update(np.array([0.0]))[0], 0.5)   # fall step 2: -0.1*4


def test_gravity_snap_up_resets_fall():
    g = Gravity(size=1, attack=1.0, gravity=0.1)
    g.update(np.array([1.0]))
    g.update(np.array([0.0]))                               # now 0.9, fall=1
    assert np.isclose(g.update(np.array([1.0]))[0], 1.0)    # a rise resets fall
    assert np.isclose(g.update(np.array([0.0]))[0], 0.9)    # fall restarts at 1


def test_gravity_never_goes_negative():
    g = Gravity(size=1, attack=1.0, gravity=0.5)
    g.update(np.array([1.0]))
    for _ in range(10):
        out = g.update(np.array([0.0]))
    assert out[0] == 0.0


def test_autosens_backs_off_fast_when_clipping():
    a = AutoSens(up=1.02, down=0.9)
    start = a.sens
    a.update(1.0)                       # a bar hit the ceiling -> reduce gain
    assert a.sens == start * 0.9


def test_autosens_settles_with_headroom_never_pegs_ceiling():
    # feed the unclipped loudest-bar level; sens must settle so the shown peak
    # sits below 1.0 (rounded top, never flat-clipped) but still fills.
    a = AutoSens()
    level = 0.5
    for _ in range(600):
        a.update(level * a.sens)      # unclipped, as the live path feeds it
    final = min(1.0, level * a.sens)
    assert final < 0.85           # real headroom: not jammed against the top
    assert final > 0.4            # but still filled, not dead


def test_autosens_ducks_fast_on_sudden_loud_section():
    # gain ramped up during a quiet intro; a sustained loud drop must recover
    # in a few frames, not crawl down leaving the frame pegged for a second.
    a = AutoSens()
    a.sens = 10.0                     # as if ramped up over a quiet intro
    for _ in range(6):                # sustained loud section: raw peak ~0.5
        a.update(0.5 * a.sens)
    shown = 0.5 * a.sens
    assert shown < a.overshoot + 0.02  # back within the headroom band, quickly

    # a much slower old-style 0.9 nudge would still be pegged after 6 frames
    slow = 10.0
    for _ in range(6):
        slow *= 0.9
    assert 0.5 * slow >= 1.0


def test_autosens_creeps_up_when_there_is_headroom():
    a = AutoSens(up=1.02, down=0.9, target=0.9)
    start = a.sens
    a.update(0.4)                       # frame is quiet -> raise gain slowly
    assert a.sens == start * 1.02


def test_autosens_up_is_slower_than_down():
    # asymmetric so it ducks loud drops instantly but swells quiet parts gently
    a = AutoSens()
    assert (1 - a.down) > (a.up - 1)


def test_autosens_holds_on_silence():
    a = AutoSens()
    start = a.sens
    a.update(0.0)                       # don't amplify a silent intro's noise
    assert a.sens == start


def test_autosens_clamped_to_bounds():
    hi = AutoSens(up=2.0, max_sens=1.5)
    for _ in range(10):
        hi.update(0.1)
    assert hi.sens <= 1.5
    lo = AutoSens(down=0.1, min_sens=0.5)
    for _ in range(10):
        lo.update(1.0)
    assert lo.sens >= 0.5


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
