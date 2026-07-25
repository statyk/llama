# Bed music under DJ audio

**Status:** Approved design
**Date:** 2026-07-25

## Problem

Voiced shows emit standalone spoken DJ clips (one per set lead-in, plus the
outro) that play dry — just the host's voice, then straight into the music.
A radio "bed" — low instrumental music playing *under* the host — gives the
talk breaks the feel of a real broadcast. Different formats call for different
beds (a Grateful Dead host, a bluegrass host, a soul/R&B host each want their
own), so it must be customizable, with a station-level default.

## Decisions (owner-approved)

- **Constant-attenuation bed under the standalone DJ clips.** No sidechain
  ducking — the DJ clips have no concurrent music track, so the bed plays at a
  fixed level under the whole clip.
- **Bed source:** station default (`[tts] bed`) with a **per-presenter
  override** (`Presenter.bed`). Practically presenter ≈ profile (≈1:1), so a
  presenter-level override is enough.
- **Format:** beds must be **24 kHz mono 16-bit WAV** (matching the voice PCM);
  a mismatch **hard-fails** the package with a clear error. No resampling.
- **Envelope:** only the gain is configurable (`[tts] bed_gain_db`, default
  −20 dB); pre-roll (~1.5 s), tail (~2 s), and fade lengths (~1 s) are fixed
  sensible defaults.
- **Coverage:** the bed plays under **every** voiced DJ segment (each lead-in
  and the outro), uniformly.
- **Dependency posture:** pure pip wheels, no system binary — `numpy` for PCM
  mixing, stdlib `wave` to read WAV, existing `lameenc` to encode. No `ffmpeg`
  (would break the signed standalone-binary story); `audioop` is unavailable
  (removed in Python 3.13+; the project is on 3.14).

## Envelope, in plain terms

For one DJ clip:

```
      pre-roll (~1.5s)          voice plays               tail (~2s)
     music alone, fading in   bed under voice        music alone, fading out
   |~~~~~~~~~~~~~~~~~~~~~~~|===========================|~~~~~~~~~~~~~~~~~~~~~~~|
```

- **gain_db** — bed loudness relative to the voice; −20 dB ≈ bed at ~1/10 the
  voice amplitude (present but clearly background). The one exposed knob.
- **pre-roll** — music alone before the host starts ("music up, then DJ").
- **tail** — music alone after the host stops, before the next song.
- **fade-in / fade-out** — bed ramps up from silence (during pre-roll) and
  down to silence (during tail), avoiding clicks.
- **looping** — if the bed file is shorter than needed it is tiled seamlessly;
  if longer, only the needed span is used.

## Architecture

### 1. Config & data model

- `TTSConfig` (`src/llama/config.py`): add
  - `bed: str | None = None` — path to a station-default bed WAV.
  - `bed_gain_db: float = -20.0`.
- `Presenter` (`src/llama/presenters.py`): add
  - `bed: str | None = None` — a host's signature bed; omitted from written
    TOML when unset (same `exclude_none` handling as the other optionals). The
    `voice`/`voice_clone` XOR validator is unaffected.

### 2. Bed resolution

`resolve_bed(config, presenter) -> Bed | None` (a small frozen value
`Bed(path: Path, gain_db: float)`):

- Returns `None` when no bed path is configured.
- Precedence: `presenter.bed` if a presenter is present and sets it, else
  `config.tts.bed`.
- `gain_db` is always `config.tts.bed_gain_db` (station-level; a presenter who
  wants a different level normalizes their own bed file).
- A bed is only ever *used* when a show's voice is active (bed with no voice =
  no DJ audio = bed simply unused, no error).

Resolution runs in `cli.py` where both `config` and the loaded `presenter`
exist (alongside voice resolution), and the resolved `Bed | None` threads
through `process_show → run_package → _synthesize_dj_audio`, mirroring how
`chunk` and `lexicon` are passed.

### 3. Mixing module — new `src/llama/tts/bed.py`

Pure functions; the only I/O is reading the bed WAV via stdlib `wave`.

- `load_bed_pcm(path: Path) -> tuple[bytes, int, int, int]` — returns
  `(pcm, framerate, channels, sampwidth)`. Validates **24 kHz mono 16-bit**;
  on mismatch (or a missing/unreadable file) raises
  `llama.tts.provider.SpeechError` with a message naming the required format.
- `mix_bed(voice_pcm: bytes, bed_pcm: bytes, framerate: int, *, gain_db: float,
  pre_roll_s: float = 1.5, tail_s: float = 2.0, fade_s: float = 1.0) -> bytes`:
  1. Total length = `pre_roll + voice + tail` (in samples).
  2. Tile `bed_pcm` (numpy) to cover the total length; slice to exact length.
  3. Apply `gain_db` as a linear amplitude factor `10 ** (gain_db / 20)`.
  4. Apply a linear fade-in over the first `fade_s` and fade-out over the last
     `fade_s`.
  5. Overlay the voice onto the bed starting at the `pre_roll` offset (sum).
  6. Clip the sum to the int16 range (`np.clip`) — at −20 dB overlap peaks
     rarely exceed full scale, and hard-clipping there is inaudible.
  7. Return int16 PCM bytes.

  All arithmetic in float32/int32 internally; input and output are int16 PCM.

### 4. Package integration — `src/llama/stages/package.py`

The per-segment synthesis tail becomes three explicit paths so the two
existing ones are preserved byte-for-byte:

- **no bed, no chunk** → `speech.synthesize(spoken)` (MP3, unchanged).
- **no bed, chunk** → `_synthesize_chunked(spoken, speech)` (unchanged).
- **bed active** → obtain the voice as **PCM** — via a factored
  `_segment_pcm(spoken, speech, chunk)` that returns `(pcm, framerate,
  channels)` from either the chunked concat (existing `_synthesize_chunked`
  internals, refactored to expose PCM) or a whole-segment `fmt="wav"` call —
  then `mix_bed(...)`, then encode once via the existing lameenc helper
  (factored out of `_synthesize_chunked` as `_encode_mp3(pcm, framerate,
  channels)`). Bed thus composes with chunked *or* whole-segment voice.

The bed's `framerate` from `load_bed_pcm` must equal the voice PCM's
framerate; a mismatch hard-fails (SpeechError). The bed PCM is loaded once per
package run, not per segment.

**Caching.** The segment cache key appends a bed component **only when a bed is
active**:

- no bed: `sha256(f"{spoken}\n{voice}\n{model}\nchunk={chunk}")` — byte-identical
  to today, so existing cached clips stay valid.
- bed active: the same string plus `f"\nbed={bed_hash}:{gain_db}"`, where
  `bed_hash` is a content hash of the bed PCM (computed once). Editing the bed
  file or the gain re-renders exactly the voiced clips on `redo --from
  package`; unaffected clips stay cached.

### 5. Dependencies, docs, testing

- **New dependency:** `numpy` in `pyproject.toml` `dependencies`. Bundles into
  the PyInstaller binaries; no system binary required.
- **Docs:** `[tts] bed` / `bed_gain_db` and presenter `bed` documented in
  `config init` (DEFAULT_CONFIG_TOML, commented), README, station-brief,
  workflow, and CLAUDE.md — including the "beds must be 24 kHz mono 16-bit WAV"
  requirement and the hard-fail behavior on mismatch.

- **Tests** (offline; the `fake` backend already returns a silent WAV for
  `fmt="wav"`):
  - `tts/bed.py`: `load_bed_pcm` accepts a good WAV and rejects wrong
    rate/channels/sample-width and missing files (SpeechError); `mix_bed`
    output length = pre_roll + voice + tail; the voice region is present
    (non-silent where voice is non-silent); the bed is attenuated by the
    expected factor; fades ramp to ≈0 at both ends; a bed shorter than the
    total is tiled (looping); the clip guard produces no int16 overflow.
  - `stages/package.py`: with `FakeSpeechProvider` + a tiny generated bed WAV
    fixture, a bed-active run produces a valid MP3 for a segment, with `chunk`
    off and on; the cache key includes the bed (changing `bed_gain_db`
    re-renders; a no-bed run's key is unchanged from before this feature);
    a missing/misformatted bed hard-fails the package.
  - `config` / `presenters`: `TTSConfig.bed`/`bed_gain_db` and `Presenter.bed`
    round-trip (presenter TOML omits `bed` when unset); `resolve_bed`
    precedence (presenter over station; None when neither set; gain always
    from station config).

## Non-goals

Ducking / sidechain compression; per-presenter gain; a bed pool or rotation;
auto-resampling or channel down-mixing (hard-fail instead); a `--bed` CLI
flag; a bed under the concert music tracks themselves; loudness normalization
of the bed. All deferred or out of scope.
