"""Real-time spectral analysis for the visualizer.

Turns a window of audio samples into a set of log-spaced frequency bands, then
shapes them for display: exponential smoothing (fast attack / slow decay),
floating peak-hold caps, and kick-drum beat detection.

All pure and unit tested — no audio hardware involved.
"""

import numpy as np


def log_band_edges(n_bins, fmin, fmax):
    """`n_bins + 1` logarithmically spaced band edge frequencies.

    Log spacing matches human pitch perception, so bass doesn't visually
    swamp the display the way linear FFT bins do.
    """
    return np.exp(np.linspace(np.log(fmin), np.log(fmax), n_bins + 1))


def compute_bands(window, samplerate, edges):
    """Magnitude in each log-spaced band for a window of samples.

    Bands wide enough to contain FFT bins take the mean of those bins. Bands
    narrower than the bin spacing (common in the bass, where log spacing packs
    many bands into a few Hz) contain no bin, so they're interpolated from the
    spectrum at the band's center frequency instead of being left dead at 0.
    """
    n = len(window)
    windowed = window * np.hanning(n)
    spectrum = np.abs(np.fft.rfft(windowed))
    freqs = np.fft.rfftfreq(n, 1.0 / samplerate)
    centers = np.sqrt(edges[:-1] * edges[1:])  # geometric center of each band

    bands = np.zeros(len(edges) - 1, dtype=np.float32)
    for i in range(len(edges) - 1):
        mask = (freqs >= edges[i]) & (freqs < edges[i + 1])
        if mask.any():
            bands[i] = spectrum[mask].mean()
        else:
            bands[i] = np.interp(centers[i], freqs, spectrum)
    return bands


def frequency_tilt(centers, fmin, slope=0.4):
    """Per-band gain that rises with frequency to counter music's ~1/f falloff.

    Bass swamps treble in raw magnitude, so without this the high bands sit
    below the noise floor and the right side of the display goes dead. The tilt
    is a power law of frequency, unity at `fmin` (bass unchanged) and larger
    toward the top; `slope` sets how much treble is lifted.
    """
    return (np.asarray(centers, dtype=np.float32) / fmin) ** slope


def to_display(bands, n, gain=20.0, curve=0.5, noise_floor=0.12):
    """Map raw band magnitudes to display heights in [0, 1] — no smoothing.

    Normalizing by the FFT size `n` makes the scale independent of the window
    length. The sub-linear `curve` (sqrt by default) lifts quiet bands so they
    stay visible without blowing silence up to full height. `noise_floor` then
    gates out everything below that height and rescales what remains, so the
    ever-present noise floor doesn't light every column's bottom cell into a
    permanent solid baseline. Raw V1 mapping; autosens replaces `gain` later.
    """
    x = np.maximum(np.asarray(bands, dtype=np.float32), 0.0) / n * gain
    height = np.clip(x ** curve, 0.0, 1.0)
    if noise_floor > 0.0:
        height = np.clip((height - noise_floor) / (1.0 - noise_floor), 0.0, 1.0)
    return height


class Gravity:
    """cava-style asymmetric motion: snap up, fall under accelerating gravity.

    Rising bars ease toward the new height at `attack` (temporal smoothing that
    kills frame-to-frame flicker). Falling bars ignore the noisy instantaneous
    value and drop from their last height under gravity — the fall distance
    grows with the square of how long the bar has been falling, so it starts
    gentle and accelerates. That parabolic fall is the lively-but-smooth look a
    symmetric EMA can't produce.
    """

    def __init__(self, size, attack=0.6, gravity=0.0025):
        self.value = np.zeros(size, dtype=np.float32)
        self.fall = np.zeros(size, dtype=np.float32)
        self.attack = attack
        self.gravity = gravity

    def update(self, x):
        x = np.asarray(x, dtype=np.float32)
        rising = x >= self.value
        self.fall = np.where(rising, 0.0, self.fall + 1.0)
        up = self.value + (x - self.value) * self.attack
        down = np.maximum(self.value - self.gravity * self.fall ** 2, 0.0)
        self.value = np.where(rising, up, down).astype(np.float32)
        return self.value.copy()


class Smoother:
    """Per-band exponential smoothing: snappy on the way up, graceful down."""

    def __init__(self, size, attack=0.6, decay=0.15):
        self.value = np.zeros(size, dtype=np.float32)
        self.attack = attack
        self.decay = decay

    def update(self, x):
        x = np.asarray(x, dtype=np.float32)
        coef = np.where(x > self.value, self.attack, self.decay)
        self.value = self.value + (x - self.value) * coef
        return self.value.copy()


class PeakHold:
    """Floating peak caps that jump to new maxima and drift down slowly."""

    def __init__(self, size, decay=0.02):
        self.peak = np.zeros(size, dtype=np.float32)
        self.decay = decay

    def update(self, x):
        x = np.asarray(x, dtype=np.float32)
        self.peak = np.maximum(x, self.peak - self.decay)
        return self.peak.copy()


class BeatDetector:
    """Fire when instantaneous energy spikes above its running average."""

    def __init__(self, sensitivity=1.4, memory=0.85, warmup=10):
        self.sensitivity = sensitivity
        self.memory = memory
        self.warmup = warmup
        self.avg = 0.0
        self._seen = 0

    def update(self, energy):
        energy = float(energy)
        # Don't fire while the running average is still catching up from
        # silence, otherwise the ramp-up transient reads as a false beat.
        ready = self._seen >= self.warmup
        beat = ready and self.avg > 0 and energy > self.avg * self.sensitivity
        self.avg = self.memory * self.avg + (1 - self.memory) * energy
        self._seen += 1
        return beat
