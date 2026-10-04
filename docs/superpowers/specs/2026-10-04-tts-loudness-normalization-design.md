# emcee: normalize TTS loudness per chunk — design

**Date:** 2026-10-04
**Scope:** `packages/emcee` only (llama and herder untouched).
**Review mode:** Opus.

## Stakes

What is at risk is **on-air audio level**, not data. A wrong gain makes a DJ clip
too quiet, too loud, or clipped; a wrong cache key either re-spends TTS on clips
that didn't need it or fails to re-render clips that did. Nothing here deletes or
overwrites anything that can't be regenerated. **No strict surfaces.** There is
no new cost surface: emcee re-scripts on every call (`process.py`), so a real
LLM's fresh text already changes every clip's cache key, and `emcee run` never
re-voices an already-ready package.

## The problem

Production: large volume swings between sentence chunks of one DJ clip, worst
with the `phil` presenter (`~/.emcee/samples/phil.wav`). Measured 2026-10-03 as
speech-active RMS dB per returned Voxtral chunk:

- **Reference-clip dynamics.** phil.wav LRA 5.4 LU, kurt1.wav 7.4 LU. Evening the
  reference clip (acompressor + loudnorm I=-18 LRA=3) roughly halved the scatter:
  phil SD 2.1→1.1 dB (spread 6.6→3.1 dB, 8 same-sentence calls), kurt SD 2.0→0.9.
- **Per-call randomness, in every voice.** Troy (reference LRA 1.5) had one repeat
  of the same sentence come back 6 dB low. No source-side fix removes this.
- Every voice delivers the opening greeting softer (content-driven).

Mistral publishes no loudness guidance for reference clips. The fix therefore
belongs on emcee's side, on the returned audio.

**Current level, measured 2026-10-04** over 16 delivered clips (8 packages,
voice region only; every presenter is bedded). Read with the gated metric below,
they measure −20.6 to −22.3 dBFS (mean −21.4), but that understates the voice:
the bed sits 25–27 dB below the loudest frame, inside the 30 dB gate, so
bed-only frames between words count as active and pull the mean down. Excluding
frames within 10 dB of each clip's measured bed level (taken from the pre-roll)
gives a voice level of −18.7 to −20.1 dBFS (mean −19.3); that slightly overstates
the voice-only metric, which keeps soft syllable tails. Peaks −0.5 to −3.9 dBFS.
`TARGET_DB = −20` therefore matches today's on-air voice level, so the change
evens chunks out rather than shifting the station's level. (The metric is only
ever applied to voice-only PCM — normalization runs before `mix_bed` — so the
gate never sees the bed.)

## Design

### `emcee/tts/loudness.py` (new, pure numpy, sibling of `tts/bed.py`)

```python
def normalize_speech(pcm: bytes, framerate: int) -> bytes:
    """Gain one stretch of int16 mono speech PCM to TARGET_DB speech-active level."""
```

Module constants (not config — deliberately no knob and no off switch):

| constant | value | meaning |
|---|---|---|
| `TARGET_DB` | −20.0 | speech-active RMS target, dBFS |
| `CEILING_DB` | −1.0 | output sample peak never exceeds this, dBFS |
| `MAX_GAIN_DB` | 10.0 | gain is clamped to ±this |
| `FRAME_S` | 0.05 | measurement frame length |
| `GATE_DB` | 30.0 | frames more than this below the loudest frame are excluded |
| `SILENCE_DB` | −60.0 | input whose loudest frame is below this is returned unchanged |

Algorithm:

1. Decode to float (`/ 32768`). Empty input → return unchanged.
2. Split into `FRAME_S` frames (`round(framerate * FRAME_S)` samples; the trailing
   partial frame is its own frame; input shorter than one frame is one frame).
   Per-frame mean-square → dB.
3. If the loudest frame is below `SILENCE_DB` → return the input bytes unchanged.
4. **Active level** = 10·log10(mean of the mean-squares of frames within
   `GATE_DB` of the loudest frame). (Power-averaged, not dB-averaged.)
5. `gain = clamp(TARGET_DB − active, −MAX_GAIN_DB, +MAX_GAIN_DB)`.
6. **Ceiling:** `gain = min(gain, CEILING_DB − peak_dbfs)`, where `peak_dbfs` is
   the input's absolute sample peak. The invariant is "output peak ≤ CEILING_DB",
   so this can attenuate a chunk that was already at target but peaks above the
   ceiling. A quiet chunk with sharp transients may land short of `TARGET_DB`;
   that is accepted in preference to a limiter, which would change the voice's
   character.
7. Multiply, round to nearest, clip to int16, return little-endian int16 bytes
   of the same length.

The function assumes 16-bit mono and does not inspect the format. Call it only
**after** the existing sample-width checks (`_chunked_pcm` checks the first
sentence's width; `_segment_pcm` checks before returning), so a non-16-bit
backend still fails with the existing `SpeechError` rather than a numpy error.
Mono is checked by `_render` after `_segment_pcm` returns, i.e. after
normalization — harmless, since non-mono input still raises there.

### Where it is applied (`emcee/audio.py`)

Only on render paths that already hold PCM — **option (b)**, chosen 2026-10-04:

- `_chunked_pcm`: on each sentence's PCM, after `readframes` (and the
  first-sentence width check) and **before** the inter-sentence silence is
  appended. Covers chunked clips with
  and without a bed (both `_synthesize_chunked` and the bed path go through it).
- `_segment_pcm`, unchunked branch: on the whole segment's PCM. Only the bed path
  reaches this branch.

Both happen **before** `mix_bed`, so the voice-to-bed ratio becomes consistent
too (the bed's level is fixed by `bed_gain_db`; today a quiet chunk also sits
lower relative to the bed).

Applies to every speech backend alike. On ElevenLabs, per-chunk normalization
overrides the level shape its `previous_text`/`next_text` conditioning gives
across chunk boundaries — accepted; ElevenLabs is opt-in and not production.

**Unchunked, no bed** — the one path that ships the provider's own MP3 untouched
— is **not** normalized and stays byte-identical. Known gap, accepted: it is the
shipped default config (`chunk = False`, no bed) and `emcee say --no-chunk`
without a bed, but not the production config (global `chunk = true`, every
presenter has a bed). Within one unchunked clip there are no chunk-to-chunk
swings; clip-to-clip variation from per-call randomness remains on that path.
Normalizing it would mean requesting WAV and re-encoding where today the bytes
pass through — judged not worth the extra surface.

`emcee say` shares `render_speech_mp3`, so it picks this up automatically on the
same paths.

### Cache key (`_synthesize_dj_audio`)

The `segments.json` key gains a `\nloud=v1` term **only when the clip's render
path normalizes** (`chunk` or bed active), and the unchunked no-bed key is
unchanged. Since emcee re-scripts on every call, a cross-call cache hit only
happens with a deterministic LLM (the fake backend, tests); in production the
term matters within one `process_package` call (the content-filter repair loop
reuses its `rendered` clips) and for correctness of the key's meaning: a clip's
key must describe how it was rendered. Bump `v1` when the constants or the
algorithm change.

## Testing (offline)

The fake provider returns silent WAV, which `normalize_speech` passes through
unchanged — so existing byte-level tests are unaffected. New tests:

- **Unit (`tests/test_loudness.py`)**, synthesized tones/noise at known levels:
  a tone at −30 lands at −20 (±0.1 dB); a hot tone is attenuated to −20; the
  ceiling binds (high-crest input lands short of target, output peak ≤ −1 dBFS);
  the ±10 dB clamp binds on a very quiet input; digital silence and
  below-`SILENCE_DB` input return identical bytes; empty input; input shorter than
  one frame; leading/trailing silence does not drag the measurement (gate works);
  output length equals input length.
- **Integration (`test_audio.py`)**: a fake provider variant returning per-call
  tones at different amplitudes; on the chunked path every sentence's region of
  the output PCM measures at target; on the unchunked bed path the voice is
  normalized before the mix (compare against mixing a pre-normalized voice);
  the unchunked no-bed path returns the provider's bytes unchanged.
- **Cache key**: normalizing paths' keys contain `loud=v1` and differ from the
  pre-change key; the unchunked no-bed key is byte-identical to the pre-change
  formula.

## Owner validation (live, after merge)

Re-voice `gratefuldead-1971-08-06` (phil; the package deferred until this ships)
and judge it with a measure **independent of the one the algorithm sets** —
per-chunk RMS spread is ~0 by construction and proves nothing. Use ffmpeg's
`ebur128` momentary/short-term loudness across the voice region (K-weighted),
before vs after, plus a listening pass; expect some chunks up to ~1–2 dB short
of target where the −1 dBFS ceiling binds (today's clips show a 16–19 dB
crest factor against a 19 dB allowance). Optional: compare
`phil_even.wav` + normalization against `phil.wav` + normalization (the evened
clips are preserved in `~/.emcee/samples/` but no presenter uses them).

## Out of scope

- Normalizing the unchunked no-bed path (see above).
- Any config knob, per-presenter target, or off switch.
- True LUFS/K-weighting, or a limiter.
- Repointing presenters at the evened reference clips.
