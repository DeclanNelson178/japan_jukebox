"""Real-time audio engine.

Plays a mono signal to the default output device and exposes a synchronized
"tap" of the samples currently hitting the speakers, so a visualizer can FFT
exactly what is being heard (no wall-clock drift).

The pure sample-pumping logic (`_next_block`, `latest_window`, position math)
is deliberately separated from the sounddevice stream so it can be unit tested
without audio hardware.
"""

import threading

import numpy as np
import soundfile as sf

try:  # optional at import time so the pure core stays testable without portaudio
    import sounddevice as sd
except (OSError, ImportError):  # pragma: no cover - hardware/lib dependent
    sd = None


def load_wav(path):
    """Load a wav file as (mono float32 signal in [-1, 1], samplerate)."""
    data, samplerate = sf.read(path, dtype="float32", always_2d=False)
    return to_mono(data), samplerate


def to_mono(samples):
    """Collapse an (n, channels) or (n,) array to a 1-D mono float array."""
    samples = np.asarray(samples, dtype=np.float32)
    if samples.ndim == 1:
        return samples
    return samples.mean(axis=1).astype(np.float32)


class AudioEngine:
    """Streams a mono float32 signal and tracks a rolling window for analysis."""

    def __init__(self, signal, samplerate, blocksize=1024, tap_size=4096):
        self._signal = np.asarray(signal, dtype=np.float32)
        self.samplerate = int(samplerate)
        self.blocksize = int(blocksize)
        self._cursor = 0
        self._tap = np.zeros(int(tap_size), dtype=np.float32)
        self._lock = threading.Lock()
        self._stream = None
        self._thread = None
        self._stop_flag = threading.Event()
        self.paused = False

    # --- pure, hardware-free core -----------------------------------------
    def _next_block(self, frames):
        """Return the next `frames` samples, advancing the cursor.

        Zero-pads the final block and feeds the tap ring buffer.
        """
        start = self._cursor
        chunk = self._signal[start:start + frames]
        if len(chunk) < frames:
            chunk = np.concatenate(
                [chunk, np.zeros(frames - len(chunk), dtype=np.float32)]
            )
        self._cursor = min(start + frames, len(self._signal))

        # roll the tap: drop oldest `frames`, append newest
        with self._lock:
            self._tap = np.concatenate([self._tap[frames:], chunk])
        return chunk

    def latest_window(self, n):
        """Most recent `n` mono samples (left zero-padded if not enough yet)."""
        with self._lock:
            tap = self._tap
        if n <= len(tap):
            return tap[-n:].copy()
        pad = np.zeros(n - len(tap), dtype=np.float32)
        return np.concatenate([pad, tap])

    @property
    def position_seconds(self):
        return self._cursor / self.samplerate

    @property
    def duration_seconds(self):
        return len(self._signal) / self.samplerate

    @property
    def finished(self):
        return self._cursor >= len(self._signal)

    # --- sounddevice stream (not unit tested against hardware) ------------
    # A blocking writer thread is used instead of a callback: macOS hardened
    # runtime blocks cffi's write+execute callback trampolines, so the
    # callback API raises MemoryError. stream.write() has no such issue and
    # its backpressure keeps us synced to the hardware clock.
    def _writer_loop(self):  # pragma: no cover - requires audio hardware
        while not self._stop_flag.is_set() and not self.finished:
            if self.paused:
                self._stream.write(np.zeros((self.blocksize, 1), dtype=np.float32))
                continue
            block = self._next_block(self.blocksize)
            self._stream.write(block.reshape(-1, 1))

    def start(self):  # pragma: no cover - requires audio hardware
        if sd is None:
            raise RuntimeError("sounddevice unavailable")
        self._stop_flag.clear()
        self._stream = sd.OutputStream(
            samplerate=self.samplerate,
            blocksize=self.blocksize,
            channels=1,
            dtype="float32",
        )
        self._stream.start()
        self._thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._thread.start()

    def toggle_pause(self):  # pragma: no cover
        self.paused = not self.paused

    def stop(self):  # pragma: no cover
        self._stop_flag.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
