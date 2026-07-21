# Visualizer — current state

Where the cava-recipe rebuild stands (see `VISUALIZER_PLAN.md` for the full plan).
**All phases V0–V5 are built and tested (75 passing).** V0–V3 vetted live; V4 and V5
awaiting a final look.

## Done

| Phase | Commit | What it added |
|-------|--------|---------------|
| V0 | `963741d` | Bare playback: header, progress, controls footer. |
| V1 | `97d8ca4` | Raw log-spaced FFT bands (8192 window), bottom-anchored 1/8-block bars. |
| V1 fix | `599f837` | Interpolate bass bands narrower than the FFT bin spacing (no dead gaps). |
| V1 fix | `ec1ae3e` | Absolute noise-floor gate so the baseline isn't a solid wall. |
| V2 | `52c1dcd` | Temporal smoothing + accelerating "gravity" fall-off (`Gravity`). |
| V2 fix | `dc79432` | Frequency tilt lifts treble (~1/f falloff) so the right side stays alive. |
| Sync fix | `2f017a1` | Latency-compensate the tap; visuals were ~185 ms ahead on Bluetooth. |
| V3 | `1213c4b` | Autosens: adaptive gain (`AutoSens`). |
| V3 fix | `85e35e4` | Gate is absolute (before gain) so a quiet intro's noise isn't amplified. |
| V3 fix | `4d346ea` | `[target, overshoot]` band gives headroom; loudest bar never pegs the top. |
| V3 fix | `a36f9d4` | Proportional fast duck on the unclipped peak; loud sections recover in ~5 frames, not ~15. |
| V4 | `7274974` | Monstercat rounding: neighbor-spread connects bars into rounded hills. |
| V5 | `6513d05` | Gradient color on the bars (vertical, per-palette). |
| V5 | `047cbac` | Beat pulse: kick brightens the frame toward white. |
| V5 | `4b05a00` | Help overlay (`?`). |
| V5 | `afdd3fc` | Centered mirror mode (`m`). |
| V5 | `0073d9f` | Braille top-edge mode (`b`). |
| V5 | _pending_ | Cool palettes (vaporwave/cyber/miami/matrix); vaporwave is the new default. Guard tests on palette structure + order. |

## Architecture

- **`engine.py`** — `AudioEngine`: blocking-write playback (macOS blocks the callback API) + a
  synchronized sample tap. `latest_window(n, delay)` steps back by `delay` samples to line the
  FFT up with what's audible; `latency_samples` is set from the real stream latency on `start()`.
- **`spectrum.py`** — pure DSP, all unit tested:
  - `log_band_edges`, `compute_bands` (interpolates bin-starved bass bands)
  - `frequency_tilt` — per-band power-law gain (unity at `fmin`, lifts treble)
  - `band_heights` — magnitude → [0,1] with sqrt curve + absolute noise gate (pre-gain signal level)
  - `to_display` — `band_heights` × autosens `sens`, clipped
  - `Gravity` — snap-up / accelerating-gravity-fall motion
  - `AutoSens` — one adaptive gain; proportional fast duck, slow accelerating creep-up
  - `monstercat_smooth` — neighbor spread → rounded hills (O(n) two-pass)
  - `BeatPulse` — `BeatDetector` + decaying 0..1 level for the beat flash
  - (`Smoother`, `PeakHold` present; spare)
- **`render.py`** — pure glyph/color: `spectrum_frame` (bottom-anchored blocks),
  `color_spectrum_frame` (gradient + beat intensity), `mirror_spectrum_frame` (centered),
  `braille_spectrum_frame` (braille edge), `column_glyphs`, `frame_payload` (atomic DEC-2026),
  gradients, `braille_waveform`.
- **`visualizer.py`** — I/O shell: raw terminal, non-blocking input, 30 fps loop, `_spectrum_body`
  wires the pipeline (bands → tilt → band_heights → autosens on unclipped peak → clip → gravity →
  frame). Per-band `Gravity` is rebuilt on resize; `AutoSens` persists per song.
- **`driver.py`** — song selection + playback loop; one fresh engine/`AutoSens` per song.

## Pipeline per frame (`_spectrum_body`)

```
window = engine.latest_window(FFT_WINDOW, delay_samples)   # latency-compensated
bands  = compute_bands(window, sr, log_band_edges(width, FMIN, FMAX))
gain   = RAW_GAIN * frequency_tilt(centers, FMIN, TILT_SLOPE)
h      = band_heights(bands, FFT_WINDOW, gain, noise_floor=NOISE_FLOOR)  # pre-gain
autosens.update(h.max() * sens)     # unclipped peak -> adapt gain
disp   = clip(h * autosens.sens)    # then clip for display
disp   = gravity.update(disp)       # temporal smoothing + fall-off
frame  = spectrum_frame(disp, rows)
```

## Controls

`space` pause · `→`/`n` skip · `↑`/`↓` volume · `[` `]` sync trim (±10 ms) · `g` palette ·
`m` mirror/bars · `b` braille/blocks · `?` help overlay · `q` quit.

## Tuning knobs (`visualizer.py` top, and `AutoSens.__init__`)

| knob | value | effect |
|------|-------|--------|
| `FFT_WINDOW` | 8192 | analysis window; larger = better bass resolution |
| `FMIN`/`FMAX` | 40 / 16000 Hz | band range |
| `RAW_GAIN` | 20 | base magnitude→height gain (autosens rides on top) |
| `TILT_SLOPE` | 0.4 | treble lift; higher = hotter highs |
| `NOISE_FLOOR` | 0.08 | absolute gate; higher = more silence trimmed |
| `ATTACK` / `GRAVITY` | 0.6 / 0.0025 | bar rise speed / fall acceleration |
| `MONSTERCAT` | 1.5 | neighbor spread; closer to 1 = rounder |
| `PULSE_AMOUNT` | 0.5 | how much a kick brightens the frame |
| `AutoSens target/overshoot` | 0.6 / 0.8 | where the loudest bar settles (headroom band) |
| `AutoSens down` | 0.5 | max single-frame gain cut (lower = faster recovery, more pump risk) |

## Runtime

Run/test with the conda env python: `/Users/declannelson/miniconda3/envs/jukebox/bin/python3`
(or the `trappin` alias). Tests: `python3 -m pytest -q` (75 passing). User runs in iTerm2.

## Remaining

Nothing on the plan is outstanding — V0–V5 are all built. Left to do is a final live vet of
V4 (rounding) and the V5 look toggles (`m` mirror, `b` braille), and tuning the knobs above to
taste.
