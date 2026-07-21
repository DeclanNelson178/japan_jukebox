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

    def __init__(self, signal, samplerate, blocksize=1024, tap_size=32768):
        self._signal = np.asarray(signal, dtype=np.float32)
        self.samplerate = int(samplerate)
        self.blocksize = int(blocksize)
        self._cursor = 0
        # The tap must hold the analysis window *plus* enough history to step
        # back by the output latency (Bluetooth can be ~200 ms), so it's much
        # larger than one FFT window.
        self._tap = np.zeros(int(tap_size), dtype=np.float32)
        self._lock = threading.Lock()
        self._stream = None
        self._thread = None
        self._stop_flag = threading.Event()
        self.paused = False
        self.volume = 0.85
        self.latency_samples = 0  # set from the real stream latency in start()

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

    def latest_window(self, n, delay=0):
        """`n` mono samples ending `delay` samples back from the newest.

        `delay=0` is the most recent window (left zero-padded if not enough
        seen yet). A positive `delay` steps back in write-time to line the
        analysis up with what is currently audible, compensating for the output
        buffer latency between `stream.write` and the speakers.
        """
        with self._lock:
            tap = self._tap
        end = len(tap) - int(delay)
        seg = tap[max(0, end - n):max(0, end)]
        if len(seg) < n:
            pad = np.zeros(n - len(seg), dtype=np.float32)
            return np.concatenate([pad, seg])
        return seg.copy()

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
            # Volume is applied after the tap is fed, so the visuals stay
            # stable regardless of listening volume.
            block = self._next_block(self.blocksize)
            self._stream.write((block * self.volume).reshape(-1, 1))

    def nudge_volume(self, delta):  # pragma: no cover
        self.volume = float(min(1.0, max(0.0, self.volume + delta)))

    def start(self):  # pragma: no cover - requires audio hardware
        if sd is None:
            raise RuntimeError("sounddevice unavailable")
        self._stop_flag.clear()
        self._stream = sd.OutputStream(
            samplerate=self.samplerate,
            blocksize=self.blocksize,
            channels=1,
            dtype="float32",
            latency="low",  # don't ask for a big buffer; less audio/visual lag
        )
        self._stream.start()
        # The visuals lead the sound by however much audio sits buffered ahead
        # of the speakers. Record it so the tap can be delayed to match.
        self.latency_samples = int(self._stream.latency * self.samplerate)
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
