# Phase 3 — Spotify integration

Goal: type `jukebox <playlist name>` in the terminal and have it play from
Spotify (no clicking the desktop app), with the same live visualizer reacting
to the audio.

## The key constraint

Spotify's Web API can *control* playback and read metadata, but it **never
exposes the raw audio stream** — so we cannot FFT Spotify audio directly the way
we FFT our own wav files. To visualize it we capture **system audio** through a
virtual loopback device and analyze that instead.

This is why the real-time engine rewrite matters: the visualizer already reads
from an audio source. Point that source at the loopback device and the entire
existing pipeline (bands → smoothing → peak-hold → beat → render) works
unchanged.

## Architecture

```
  Spotify (Premium)
        │  played by
        ▼
  spotify_player  ──audio──▶  BlackHole (virtual output)  ──▶  speakers (multi-output)
        ▲                              │
        │ CLI control                  │ captured as input
  driver.py  ◀───────────── sounddevice InputStream ──▶ compute_bands → visualizer
```

- **Playback + control:** `spotify_player` (Rust, actively maintained) runs a
  headless Spotify Connect device via librespot and exposes a CLI:
  `spotify_player playback start playlist --name "<name>"`. Requires **Spotify
  Premium**.
- **Audio capture:** **BlackHole** (free, `brew install blackhole-2ch`) is a
  virtual audio device. A macOS *Multi-Output Device* (Audio MIDI Setup) sends
  Spotify's audio to both the speakers and BlackHole at once, so we hear it and
  can analyze it.
- **Visualization:** a new `InputEngine` mirrors `AudioEngine`'s interface but
  fills `latest_window()` from a `sounddevice.InputStream` on the BlackHole
  device instead of decoding a wav. `run()` in `visualizer.py` is unchanged.

## Work breakdown

1. **`InputEngine`** (`engine.py`, TDD)
   - Same public surface as `AudioEngine`: `latest_window(n)`, `samplerate`,
     `finished`, `start()`, `stop()`.
   - Backed by `sd.InputStream` on a named device; a ring buffer collects the
     most recent samples (blocking read loop, consistent with the macOS
     write-callback constraint).
   - `finished` is driven by an external stop signal (there is no song length
     in capture mode) — the visualizer loops until the user quits/skips.
   - Pure ring-buffer logic unit tested without hardware.

2. **Device discovery** (`engine.py`)
   - Helper to find the BlackHole input device by name from
     `sd.query_devices()`; clear error if it isn't installed/configured.

3. **Spotify control** (`spotify.py`, new)
   - Thin wrapper shelling out to the `spotify_player` CLI: resolve a playlist
     by name, start playback, next/prev, play/pause.
   - Fetch now-playing metadata (title/artist) for the header.
   - Graceful errors if `spotify_player` isn't installed or not authenticated.

4. **CLI + launcher**
   - `driver.py`: add a `spotify` subcommand / `--source spotify` flag.
     `jukebox <playlist>` → start `spotify_player`, open `InputEngine` on
     BlackHole, run the visualizer.
   - Map skip/pause keys through to `spotify_player` instead of the local
     engine.
   - New `~/scripts/jukebox/jukebox.sh` alias (or extend `trappin.sh`).

5. **Metadata sync**
   - Poll `spotify_player` for the current track so the header shows the real
     song, and re-fetch on skip.

6. **Docs**
   - README: prerequisites (Premium, `brew install blackhole-2ch`,
     `spotify_player`), the Multi-Output Device setup, and the new command.

## Prerequisites (user, one-time)

- Spotify **Premium**.
- `brew install blackhole-2ch`
- `brew install spotify_player` (or `cargo install spotify_player`), then
  authenticate it once.
- Create a **Multi-Output Device** in Audio MIDI Setup combining the speakers
  and BlackHole; select it as Spotify's / the system output.

## Open questions

- Header progress bar in capture mode: use `spotify_player`'s reported
  position/duration, or drop the bar when capturing.
- Whether to also offer a generic "visualize whatever is playing" mode (any
  system audio via BlackHole), independent of Spotify — falls out of
  `InputEngine` almost for free.
