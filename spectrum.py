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
    """Magnitude in each log-spaced band for a window of samples."""
    n = len(window)
    windowed = window * np.hanning(n)
    spectrum = np.abs(np.fft.rfft(windowed))
    freqs = np.fft.rfftfreq(n, 1.0 / samplerate)

    bands = np.zeros(len(edges) - 1, dtype=np.float32)
    for i in range(len(edges) - 1):
        mask = (freqs >= edges[i]) & (freqs < edges[i + 1])
        if mask.any():
            bands[i] = spectrum[mask].mean()
    return bands


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
