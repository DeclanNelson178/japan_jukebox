# japan_jukebox

A terminal music visualizer. Plays *Trappin in Japan* (or any local wav library)
and paints a live, truecolor spectrum that jumps with the beat.

```
        ▃   ▇  ▆▃▄▅▂  █
  ▆     █  ▇█ ▁█████▄▆█▅   ▔   ▇█
  █ ▂   █▔ ██ ██████████▅▁▆█▆▆▇██▆ ▃▅▆▇
  █ █   ██ ██ ████████████████████▃████▄▂█▆
```

## How it works

- **Real-time engine** (`engine.py`) streams audio and exposes a synchronized
  tap of the samples currently hitting the speakers — the visuals are FFT'd from
  exactly what you hear, so there's no wall-clock drift.
- **Spectral analysis** (`spectrum.py`) maps each window onto log-spaced
  (mel-like) bands, with fast-attack/slow-decay smoothing, floating peak caps,
  and kick-drum beat detection.
- **Renderer** (`render.py` + `visualizer.py`) draws a bottom-anchored spectrum
  with sub-cell block glyphs, 24-bit gradient color, and a beat pulse.

Requires a truecolor terminal (iTerm2, Ghostty, Kitty, WezTerm).

## Setup

```sh
pip install -r requirements.txt
```

Set `HOME_PATH` in `.env` to the repo path (defaults to the driver's directory).
The `audio/wav` library is played directly; on a fresh checkout `driver.py` will
fetch and transcode the playlist first.

```sh
python3 driver.py
```

## Controls

| key | action |
|-----|--------|
| `h` | toggle the on-screen help / controls panel |
| `space` | pause / resume |
| `→` / `n` | skip song |
| `↑` / `↓` | volume |
| `g` | cycle palette (trap · aurora · ice · sunset) |
| `m` | toggle mirror mode (bars radiate from a center line) |
| `w` | toggle the braille oscilloscope strip |
| `q` | quit |

## Command-line options

- `-v INT` — play a specific *Trappin in Japan* volume number (default: random)
- `-r` — repeat one song instead of shuffling (default: off)
- `-p NAME` — start palette: `trap` (default), `aurora`, `ice`, `sunset`

## Other music

Point `START_URL` in `driver.py` at another playlist to build a different
library. (Downloading uses `yt-dlp`; the old `pytube` path is dead.) The `-v`
option is specific to the Trappin numbering.

Playlist: https://www.youtube.com/playlist?list=PL03tCdy8gL5JvpLbxw6SsXaNDBot7b_Ok

## Tests

```sh
pytest
```

The pure DSP/render/engine logic is unit tested without audio hardware.
