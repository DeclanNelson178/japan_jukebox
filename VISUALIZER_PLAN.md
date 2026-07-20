# Visualizer rebuild plan

## Why this exists

The rebuilt visualizer looked janky — flashing, laggy, shapes that didn't
track the music. Two blind redesigns (bottom bars, then a scrolling envelope)
both missed. So we stop guessing and rebuild the *visual* on the proven recipe
behind **cava**, the terminal spectrum analyzer that everyone copies because it
actually looks good. We keep the parts already vetted as working and rebuild the
DSP + draw in small phases, each one you sign off before we move on.

## What's already working (keep, don't touch)

- **`engine.py`** — audio playback + a synchronized tap of the samples hitting
  the speakers. (Vetted: audio plays clean.)
- **Non-blocking input** (`_read_pending`, raw-fd `os.read`). (Vetted: no more
  freeze on keys/mouse.)
- **`frame_payload`** — atomic synchronized-update present (DEC mode 2026).
  (Vetted: killed the tearing/flicker.)

## The proven recipe (cava, reimplemented in Python)

cava turns audio into smooth bars with a fixed pipeline. The smoothness is the
sum of these steps — skipping any of them is why the old version looked raw:

1. **Log-spaced FFT bands.** Human hearing is logarithmic, so bars are spaced by
   log frequency (bass gets perceptual room). *Requires a large FFT window
   (≥8192 samples); the old 2048 window couldn't resolve sub-200 Hz, so the bass
   bars were literally empty — the #1 reason it "didn't match the bass."*
2. **Autosens.** Automatic gain: back off when bars peak, creep up when quiet, so
   soft intros and loud drops both fill the frame.
3. **Integral (temporal) smoothing.** Weighted average of recent frames — kills
   the frame-to-frame flicker.
4. **Gravity fall-off.** Bars snap up instantly and fall under "gravity" — the
   signature lively-but-smooth motion (not a symmetric EMA).
5. **Monstercat smoothing** *(the rounding)*. Spread each bar into its neighbors
   with a distance falloff so the tops **connect into smooth rounded hills**
   instead of spiky independent bars. This is the ingredient that makes it read
   as a waveform, and the one every previous attempt lacked.
6. **Sub-cell rendering.** 1/8-block glyphs (`▁▂▃▄▅▆▇█`) for 8× vertical
   resolution, drawn as one atomic synchronized frame (already in place).

## Phases

Each phase: TDD (pure DSP unit-tested), a single commit named by its ID, and you
vet it live before we start the next.

### V0 — Bare playback  ← strip down to here first
Rip out *all* visualization. Play the wav; render only a now-playing header, a
progress bar, and a controls footer. Controls: `space` pause, `→`/`n` skip,
`↑`/`↓` volume, `q` quit.
**Vet:** audio clean, keys responsive, no freeze, quits clean. This is the
trusted floor we build back up from.

### V1 — Raw log spectrum
Log-spaced FFT bands (window ≥8192 for real bass), bottom-anchored bars with
1/8-block sub-cell height. No smoothing yet — deliberately raw.
**Vet:** bars move with the music; the bass region on the left actually moves on
the 808s; no dead/empty band ranges.

### V2 — Temporal smoothing + gravity
Add integral smoothing and gravity fall-off.
**Vet:** motion is smooth and alive — fast rise, graceful fall, no flicker, no
snapping.

### V3 — Autosens
Automatic gain normalization.
**Vet:** quiet and loud sections both look right; never flat-clipped, never dead.

### V4 — Monstercat rounding (the look)
Neighbor-spread smoothing → connected rounded hills.
**Vet:** it reads as a smooth rounded waveform; a bass hit makes a big round
swell, not a spike. This is the "looks like it should" moment.

### V5 — Polish
Gradient color + the existing palettes (trap · aurora · ice · sunset), beat
pulse, help overlay. Options to try here: mirror the rounded spectrum around a
center zero axis (the "centered waveform" framing), and/or a braille top edge
for an extra-smooth curve.
**Vet:** it's pretty.

## Tuning knobs (cava defaults as starting points)

| knob | start | notes |
|------|-------|-------|
| framerate | 30–45 | cava's C default is 60; Python + atomic present is smooth at 30–45 |
| FFT window | 8192 | bump `engine.tap_size` to match so the tap can serve it |
| noise_reduction | ~0.77 | drives integral + gravity strength |
| monstercat spread | ~1.5 | higher = rounder/more connected |

## Sources

- [karlstav/cava](https://github.com/karlstav/cava) + CAVACORE.md — the reference
  pipeline (log bands, autosens, integral + gravity noise reduction).
- [cava-monstercat](https://github.com/nikp123/cava-monstercat),
  [Cavalier](https://alternativeto.net/software/cavalier) — precedent for the
  rounded/smooth "monstercat" look and its knobs.
