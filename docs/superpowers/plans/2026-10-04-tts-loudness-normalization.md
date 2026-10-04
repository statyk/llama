# emcee TTS Loudness Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gain every synthesized speech chunk (chunked mode) or segment (unchunked bed mode) to a fixed speech-active level before concatenation and bed mixing, so DJ clips stop swinging in volume chunk to chunk.

**Architecture:** A new pure-numpy module `emcee/tts/loudness.py` (sibling of `tts/bed.py`) exposes `normalize_speech(pcm, framerate) -> bytes`. `emcee/audio.py` calls it in the two places that already hold voice PCM (`_chunked_pcm` per sentence, `_segment_pcm`'s unchunked branch), and adds a `loud=<version>` term to the DJ-clip cache key on those paths only. The unchunked no-bed path stays byte-identical.

**Tech Stack:** Python 3.14, numpy (already a dependency), stdlib `wave`, pytest.

**Spec:** `docs/superpowers/specs/2026-10-04-tts-loudness-normalization-design.md`

## Global Constraints

- Scope: `packages/emcee` only (plus one CLAUDE.md sentence). llama and herder untouched; emcee never imports llama.
- Constants (module-level in `emcee/tts/loudness.py`, NOT config — no knob, no off switch): `TARGET_DB = -20.0`, `CEILING_DB = -1.0`, `MAX_GAIN_DB = 10.0`, `FRAME_S = 0.05`, `GATE_DB = 30.0`, `SILENCE_DB = -60.0`.
- Unchunked + no bed is NOT normalized and its output and cache key stay byte-identical to today.
- Normalization runs on voice-only PCM, after the existing 16-bit sample-width checks and before inter-sentence silence and before `mix_bed`.
- Cache-key term `\nloud=v1` is appended only when `chunk` is true or a bed is active.
- Worktree: `.claude/worktrees/loudness`, with its own `.venv` (`python3 -m venv .venv && ./.venv/bin/pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee`). Always run `./.venv/bin/pytest` from the worktree root; check `./.venv/bin/python -c "import emcee; print(emcee.__file__)"` resolves inside the worktree.
- Commit trailer on every commit:
  ```
  Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01X5uiQcfXG7dM4oKpyCxmr4
  ```

## Review Focus

1. A sentence chunk shorter than one 50 ms measurement frame (a very short Voxtral return) — must measure as one frame and normalize, not crash. → Task 1 `test_input_shorter_than_one_frame_is_normalized`.
2. A mostly-silent chunk carrying one quiet word — boost is clamped at +10 dB rather than pumping it up to target. → Task 1 `test_boost_is_clamped`.
3. A chunk with a near-full-scale click — the ceiling binds; output peak never exceeds −1 dBFS even though the chunk lands short of target. → Task 1 `test_ceiling_binds_on_a_click`.
4. Normalizing the joined clip once instead of each sentence would keep the swings (a −26/−20/−14 clip normalized as a whole lands at about −28/−22/−16). → Task 2 `test_chunked_pcm_normalizes_each_sentence_to_target` uses three different levels so it fails under that placement; `test_chunked_pcm_silence_gaps_stay_digital_zero` additionally pins that the gaps stay exact zeros.
5. A backend returning non-16-bit audio on the unchunked bed path must still raise the existing clear `SpeechError`, not a numpy error from normalization running first. → Task 2 `test_segment_pcm_non_16bit_still_raises_speech_error`.

---

### Task 1: `normalize_speech` — the pure loudness function

**Files:**
- Create: `packages/emcee/src/emcee/tts/loudness.py`
- Test: `packages/emcee/tests/test_loudness.py`

**Interfaces:**
- Consumes: nothing.
- Produces (Task 2 relies on these exact names):
  - `normalize_speech(pcm: bytes, framerate: int) -> bytes` — int16 LE mono PCM in, same-length int16 LE mono PCM out.
  - `active_level_db(pcm: bytes, framerate: int) -> float | None` — the gated speech-active level in dBFS; `None` for empty input or input whose loudest frame is below `SILENCE_DB`.
  - `LOUDNESS_VERSION: str = "v1"` — the cache-key version.
  - Constants `TARGET_DB`, `CEILING_DB`, `MAX_GAIN_DB`, `FRAME_S`, `GATE_DB`, `SILENCE_DB`.

- [ ] **Step 1: Write the failing tests**

Create `packages/emcee/tests/test_loudness.py`:

```python
import math

import numpy as np

from emcee.tts.loudness import (
    CEILING_DB, LOUDNESS_VERSION, MAX_GAIN_DB, TARGET_DB,
    active_level_db, normalize_speech,
)

RATE = 24000
FS = 32768.0


def _sine(rms_db: float, seconds: float = 0.5, freq: float = 220.0) -> np.ndarray:
    """Float sine in int16 units whose RMS is `rms_db` dBFS (peak = RMS + 3.01 dB)."""
    amp = 10 ** (rms_db / 20) * math.sqrt(2) * FS
    t = np.arange(int(seconds * RATE)) / RATE
    return amp * np.sin(2 * math.pi * freq * t)


def _pcm(x: np.ndarray) -> bytes:
    return np.clip(np.rint(x), -32768, 32767).astype("<i2").tobytes()


def _samples(pcm: bytes) -> np.ndarray:
    return np.frombuffer(pcm, dtype="<i2").astype(np.float64)


def _rms_db(x: np.ndarray) -> float:
    return 20 * math.log10(math.sqrt(np.mean((x / FS) ** 2)))


def _peak_db(x: np.ndarray) -> float:
    return 20 * math.log10(np.abs(x).max() / FS)


def test_constants_match_the_spec():
    assert (TARGET_DB, CEILING_DB, MAX_GAIN_DB) == (-20.0, -1.0, 10.0)
    assert LOUDNESS_VERSION == "v1"


def test_quiet_tone_is_raised_to_target():
    out = _samples(normalize_speech(_pcm(_sine(-26.0)), RATE))
    assert abs(_rms_db(out) - TARGET_DB) < 0.1


def test_hot_tone_is_lowered_to_target():
    out = _samples(normalize_speech(_pcm(_sine(-14.0)), RATE))
    assert abs(_rms_db(out) - TARGET_DB) < 0.1


def test_output_length_equals_input_length():
    pcm = _pcm(_sine(-26.0, seconds=0.537))
    assert len(normalize_speech(pcm, RATE)) == len(pcm)


def test_boost_is_clamped():
    # -40 wants +20 dB; the clamp allows +10, so it lands at -30.
    out = _samples(normalize_speech(_pcm(_sine(-40.0)), RATE))
    assert abs(_rms_db(out) - (-40.0 + MAX_GAIN_DB)) < 0.1


def test_ceiling_binds_on_a_click():
    # A -30 dBFS tone with one near-full-scale click: reaching -20 would put the
    # click far above the ceiling, so the gain stops at the ceiling instead.
    x = _sine(-30.0)
    x[len(x) // 2] = 10 ** (-0.5 / 20) * FS
    out = _samples(normalize_speech(_pcm(x), RATE))
    assert np.abs(out).max() <= 10 ** (CEILING_DB / 20) * FS + 1  # +1 LSB rounding
    assert _rms_db(out) < TARGET_DB - 5  # landed well short of target


def test_ceiling_attenuates_a_chunk_already_at_target_with_a_hot_peak():
    x = _sine(-20.0)
    x[100] = 10 ** (-0.2 / 20) * FS
    out = _samples(normalize_speech(_pcm(x), RATE))
    assert _peak_db(out) <= CEILING_DB + 0.01


def test_digital_silence_is_returned_unchanged():
    pcm = bytes(RATE)  # 0.5 s of zeros
    assert normalize_speech(pcm, RATE) == pcm


def test_below_silence_floor_is_returned_unchanged():
    pcm = _pcm(_sine(-66.0))  # loudest frame well below SILENCE_DB
    assert normalize_speech(pcm, RATE) == pcm


def test_empty_input_is_returned_unchanged():
    assert normalize_speech(b"", RATE) == b""


def test_input_shorter_than_one_frame_is_normalized():
    pcm = _pcm(_sine(-26.0, seconds=0.02))  # 480 samples < one 1200-sample frame
    out = normalize_speech(pcm, RATE)
    assert len(out) == len(pcm)
    assert abs(_rms_db(_samples(out)) - TARGET_DB) < 0.2


def test_gate_ignores_leading_and_trailing_silence():
    # 1 s of digital silence either side must not drag the measurement down.
    pad = np.zeros(RATE)
    x = np.concatenate([pad, _sine(-26.0), pad])
    out = _samples(normalize_speech(_pcm(x), RATE))
    voiced = out[RATE:RATE + int(0.5 * RATE)]
    assert abs(_rms_db(voiced) - TARGET_DB) < 0.1
    assert not out[:RATE].any() and not out[-RATE:].any()


def test_gate_ignores_low_noise_more_than_30_db_down():
    # Room noise 40 dB under the speech sits outside the gate.
    rng = np.random.default_rng(0)
    noise = rng.normal(0, 10 ** (-66 / 20) * FS, RATE)
    x = np.concatenate([noise, _sine(-26.0), noise])
    out = _samples(normalize_speech(_pcm(x), RATE))
    voiced = out[RATE:RATE + int(0.5 * RATE)]
    assert abs(_rms_db(voiced) - TARGET_DB) < 0.15


def test_active_level_db_measures_a_tone_and_none_for_silence():
    assert abs(active_level_db(_pcm(_sine(-26.0)), RATE) - (-26.0)) < 0.1
    assert active_level_db(bytes(RATE), RATE) is None
    assert active_level_db(b"", RATE) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/pytest packages/emcee/tests/test_loudness.py -q`
Expected: collection error / FAIL with `ModuleNotFoundError: No module named 'emcee.tts.loudness'`.

- [ ] **Step 3: Write the implementation**

Create `packages/emcee/src/emcee/tts/loudness.py`:

```python
"""Loudness normalization for synthesized speech.

Voxtral returns each call at its own level: the sentence chunks of one DJ clip
can differ by several dB (measured 2026-10-03 -- worst on presenters whose
reference clip is dynamic, but present in every voice as per-call randomness).
`normalize_speech` gains one stretch of voice PCM to a fixed speech-active level
before it is concatenated or mixed under a bed. Pure numpy, no I/O. See
docs/superpowers/specs/2026-10-04-tts-loudness-normalization-design.md.
"""
import numpy as np

TARGET_DB = -20.0    # speech-active RMS target, dBFS: today's on-air voice level
                     # (measured 2026-10-04 over 16 delivered clips, bed excluded)
CEILING_DB = -1.0    # output sample peak never exceeds this, dBFS
MAX_GAIN_DB = 10.0   # gain is clamped to +/- this
FRAME_S = 0.05       # measurement frame length, seconds
GATE_DB = 30.0       # frames more than this below the loudest frame are not "active"
SILENCE_DB = -60.0   # input whose loudest frame is below this is returned unchanged
LOUDNESS_VERSION = "v1"  # in the DJ-clip cache key; bump when anything above changes

_FULL_SCALE = 32768.0
_INT16_MIN, _INT16_MAX = -32768, 32767


def _frame_mean_squares(x: np.ndarray, framerate: int) -> np.ndarray:
    """Mean-square per FRAME_S frame; a trailing partial frame is its own frame."""
    n = max(1, round(framerate * FRAME_S))
    starts = np.arange(0, x.size, n)
    sums = np.add.reduceat(x * x, starts)
    counts = np.diff(np.append(starts, x.size))
    return sums / counts


def active_level_db(pcm: bytes, framerate: int) -> float | None:
    """Speech-active RMS level of int16 mono PCM, in dBFS: the power mean of the
    frames within GATE_DB of the loudest frame. None for empty input or input
    whose loudest frame is below SILENCE_DB."""
    x = np.frombuffer(pcm, dtype="<i2").astype(np.float64) / _FULL_SCALE
    if x.size == 0:
        return None
    ms = _frame_mean_squares(x, framerate)
    loudest = float(ms.max())
    if loudest <= 0.0 or 10.0 * np.log10(loudest) < SILENCE_DB:
        return None
    active = ms[ms >= loudest * 10.0 ** (-GATE_DB / 10.0)]
    return float(10.0 * np.log10(active.mean()))


def normalize_speech(pcm: bytes, framerate: int) -> bytes:
    """Gain one stretch of int16 mono speech PCM to TARGET_DB speech-active level.

    The gain is clamped to +/-MAX_GAIN_DB, then lowered further if needed so the
    output peak stays at or under CEILING_DB -- so a quiet chunk with a sharp
    transient can land short of target (preferred over a limiter, which would
    change the voice). Silent or empty input comes back unchanged. Assumes 16-bit
    mono: callers run it after their sample-width checks.
    """
    level = active_level_db(pcm, framerate)
    if level is None:
        return pcm
    x = np.frombuffer(pcm, dtype="<i2").astype(np.float64)
    gain_db = min(max(TARGET_DB - level, -MAX_GAIN_DB), MAX_GAIN_DB)
    peak_db = 20.0 * np.log10(np.abs(x).max() / _FULL_SCALE)
    gain_db = min(gain_db, CEILING_DB - peak_db)
    y = np.rint(x * 10.0 ** (gain_db / 20.0))
    np.clip(y, _INT16_MIN, _INT16_MAX, out=y)
    return y.astype("<i2").tobytes()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/pytest packages/emcee/tests/test_loudness.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/emcee/src/emcee/tts/loudness.py packages/emcee/tests/test_loudness.py
git commit -m "feat(emcee): normalize_speech -- gain speech PCM to a fixed active level

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01X5uiQcfXG7dM4oKpyCxmr4"
```

---

### Task 2: Wire normalization into the render paths and the cache key

**Files:**
- Modify: `packages/emcee/src/emcee/audio.py` — imports (~line 23), `_chunked_pcm` (~118-145), `_segment_pcm` (~169-181), `_render`/`render_speech_mp3` docstrings (~203-253), `_synthesize_dj_audio` key (~279-320)
- Test: `packages/emcee/tests/test_audio.py` (append)
- Modify: `CLAUDE.md` (repo root) — one sentence in the emcee architecture bullet

**Interfaces:**
- Consumes (from Task 1): `from emcee.tts.loudness import LOUDNESS_VERSION, normalize_speech` and, in tests, `active_level_db`, `TARGET_DB`.
- Produces: no new public names. Behavior: `_chunked_pcm` and `_segment_pcm(..., chunk=False)` return normalized voice PCM; the DJ-clip cache key is
  `sha256(f"{spoken}\n{speech.voice}\n{speech.model}\nchunk={chunk}{bed_key}{loud_key}")` where `loud_key = f"\nloud={LOUDNESS_VERSION}"` when `chunk or bed is not None`, else `""`.

- [ ] **Step 1: Write the failing tests**

Append to `packages/emcee/tests/test_audio.py`:

```python
# --- loudness normalization (chunked + bed paths only) ----------------------

import hashlib as _hashlib
import math as _math

from emcee.audio import _SILENCE_MS, _chunked_pcm, _segment_pcm
from emcee.speech_text import Lexicon, normalize_for_speech
from emcee.tts.loudness import TARGET_DB, active_level_db

_TONE_RATE = 24000
_TONE_S = 0.5


def _tone_wav(rms_db: float) -> bytes:
    amp = 10 ** (rms_db / 20) * _math.sqrt(2) * 32768
    t = np.arange(int(_TONE_S * _TONE_RATE)) / _TONE_RATE
    samples = np.rint(amp * np.sin(2 * _math.pi * 220 * t)).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(_TONE_RATE)
        w.writeframes(samples.tobytes())
    return buf.getvalue()


class _ToneSpeech:
    """Returns, per fmt="wav" call, a 0.5 s sine at the next level in
    `levels_db` (cycling) -- a stand-in for Voxtral's per-call level swings."""
    voice = "tone-voice"
    model = "tone-model"

    def __init__(self, levels_db: list[float]):
        self.levels_db = levels_db
        self.calls: list[str] = []

    def synthesize(self, text: str, fmt: str = "mp3", *,
                   previous_text: str | None = None,
                   next_text: str | None = None) -> bytes:
        self.calls.append(text)
        if fmt != "wav":
            return SILENT_MP3
        return _tone_wav(self.levels_db[(len(self.calls) - 1) % len(self.levels_db)])


_THREE = ("The first sentence is right here. The second sentence follows it now. "
          "The third sentence closes out the set.")


def _regions(pcm: bytes, n_sentences: int) -> tuple[list[bytes], list[bytes]]:
    """Split chunked PCM into (sentence regions, silence gaps)."""
    tone = int(_TONE_S * _TONE_RATE) * 2
    gap = int(_TONE_RATE * (_SILENCE_MS / 1000)) * 2
    voiced, gaps, pos = [], [], 0
    for i in range(n_sentences):
        voiced.append(pcm[pos:pos + tone]); pos += tone
        if i < n_sentences - 1:
            gaps.append(pcm[pos:pos + gap]); pos += gap
    assert pos == len(pcm)
    return voiced, gaps


def test_chunked_pcm_normalizes_each_sentence_to_target():
    speech = _ToneSpeech([-26.0, -20.0, -14.0])
    pcm, rate, _ = _chunked_pcm(_THREE, speech)
    assert len(speech.calls) == 3
    voiced, _ = _regions(pcm, 3)
    for region in voiced:
        assert abs(active_level_db(region, rate) - TARGET_DB) < 0.1


def test_chunked_pcm_silence_gaps_stay_digital_zero():
    pcm, _, _ = _chunked_pcm(_THREE, _ToneSpeech([-26.0, -14.0, -30.0]))
    _, gaps = _regions(pcm, 3)
    assert gaps and all(not any(g) for g in gaps)


def test_segment_pcm_unchunked_normalizes_the_whole_segment():
    pcm, rate, _ = _segment_pcm("One whole segment of speech.", _ToneSpeech([-27.0]),
                                chunk=False)
    assert abs(active_level_db(pcm, rate) - TARGET_DB) < 0.1


def _odd_8bit_wav() -> bytes:
    # Non-silent 8-bit PCM with an odd byte count: reading it as int16 would
    # raise a numpy ValueError, so this only passes if the width check runs first.
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(1); w.setframerate(24000)
        w.writeframes(bytes([200, 50] * 500 + [200]))
    return buf.getvalue()


class _Odd8BitSpeech:
    voice = "x"
    model = "y"

    def synthesize(self, text: str, fmt: str = "mp3", *,
                   previous_text: str | None = None,
                   next_text: str | None = None) -> bytes:
        return _odd_8bit_wav()


def test_segment_pcm_non_16bit_still_raises_speech_error():
    with pytest.raises(SpeechError, match="16-bit"):
        _segment_pcm("One sentence.", _Odd8BitSpeech(), chunk=False)


def test_chunked_pcm_non_16bit_still_raises_speech_error():
    with pytest.raises(SpeechError, match="16-bit"):
        _chunked_pcm("One sentence.", _Odd8BitSpeech())


def test_render_unchunked_no_bed_ships_provider_bytes_untouched():
    speech = _ToneSpeech([-35.0])
    assert render_speech_mp3("Just a line.", speech, chunk=False) == SILENT_MP3


def _expected_key(text: str, chunk: bool, bed_key: str = "", loud: bool = False) -> str:
    spoken = normalize_for_speech(text, Lexicon.empty())
    loud_key = "\nloud=v1" if loud else ""
    return _hashlib.sha256(
        f"{spoken}\nfake-voice\nfake-model\nchunk={chunk}{bed_key}{loud_key}".encode()
    ).hexdigest()


def _sidecar(tmp_path) -> dict:
    return _json.loads((tmp_path / "dj-audio" / "segments.json").read_text())


def test_cache_key_unchunked_no_bed_is_the_pre_feature_formula(tmp_path):
    _synthesize_dj_audio(tmp_path, make_notes(), FakeSpeechProvider(), False, chunk=False)
    assert _sidecar(tmp_path)["99-outro.mp3"] == _expected_key("o", chunk=False)


def test_cache_key_chunked_carries_the_loudness_version(tmp_path):
    _synthesize_dj_audio(tmp_path, make_notes(), FakeSpeechProvider(), False, chunk=True)
    assert _sidecar(tmp_path)["99-outro.mp3"] == _expected_key("o", chunk=True, loud=True)


def test_cache_key_bed_carries_the_loudness_version(tmp_path):
    from emcee.tts.bed import Bed
    bed_path = _bed_file(tmp_path)
    bed_pcm, _, _, _ = load_bed_pcm(bed_path)
    bed_key = f"\nbed={_hashlib.sha256(bed_pcm).hexdigest()[:16]}:-20.0"
    _synthesize_dj_audio(tmp_path, make_notes(), FakeSpeechProvider(), False,
                         chunk=False, bed=Bed(path=bed_path, gain_db=-20.0))
    assert _sidecar(tmp_path)["99-outro.mp3"] == _expected_key(
        "o", chunk=False, bed_key=bed_key, loud=True)
```

- [ ] **Step 2: Run tests to verify the right ones fail**

Run: `./.venv/bin/pytest packages/emcee/tests/test_audio.py -q -k "normalizes or silence_gaps or non_16bit or untouched or cache_key_"`
Expected: FAIL — `test_chunked_pcm_normalizes_each_sentence_to_target`, `test_segment_pcm_unchunked_normalizes_the_whole_segment`, `test_cache_key_chunked_carries_the_loudness_version`, `test_cache_key_bed_carries_the_loudness_version` (no normalization / no `loud=` term yet). PASS already (they pin existing behaviour): `test_chunked_pcm_silence_gaps_stay_digital_zero`, both `non_16bit` tests, `test_render_unchunked_no_bed_ships_provider_bytes_untouched`, `test_cache_key_unchunked_no_bed_is_the_pre_feature_formula`. If any of the expected-FAIL tests passes, stop and report — the test does not bite.

- [ ] **Step 3: Implement**

In `packages/emcee/src/emcee/audio.py`:

(a) Imports — after `from emcee.tts.bed import Bed, load_bed_pcm, mix_bed` add:

```python
from emcee.tts.loudness import LOUDNESS_VERSION, normalize_speech
```

(b) `_chunked_pcm` — replace the line

```python
            frames.append(w.readframes(w.getnframes()))
```

with

```python
            # Each Voxtral call comes back at its own level; even them out
            # here, per sentence and before the silence gap (see tts/loudness).
            frames.append(normalize_speech(w.readframes(w.getnframes()), framerate))
```

and add to its docstring: `Each sentence's PCM is loudness-normalized (normalize_speech) before the silence gap is appended.`

(c) `_segment_pcm` — replace the unchunked branch's

```python
        return w.readframes(w.getnframes()), w.getframerate(), w.getnchannels()
```

with

```python
        rate = w.getframerate()
        return normalize_speech(w.readframes(w.getnframes()), rate), rate, w.getnchannels()
```

(this stays after the existing sample-width check), and add to its docstring: `The voice is loudness-normalized (normalize_speech) before it is returned, so the bed is mixed under an evened voice.`

(d) `render_speech_mp3` docstring — in the bullet list, append to the bed bullet `the voice is loudness-normalized first (tts/loudness.normalize_speech)`, append to the `chunk` bullet `each sentence loudness-normalized`, and to the "neither" bullet append `(not loudness-normalized: this path never holds PCM)`.

(e) `_synthesize_dj_audio` — after the `bed_key` block (just before `for stem, text in _segment_texts(notes):`) add:

```python
    # Paths that hold PCM are loudness-normalized; the plain path ships the
    # provider's MP3 untouched, so its key (and cache) is unchanged.
    loud_key = f"\nloud={LOUDNESS_VERSION}" if (chunk or bed is not None) else ""
```

and change the key line to

```python
            f"{spoken}\n{speech.voice}\n{speech.model}\nchunk={chunk}{bed_key}{loud_key}".encode()
```

Add one paragraph to its docstring after the bed paragraph:

```
    Loudness: chunked and bed-active clips are loudness-normalized
    (tts/loudness), and their key carries `loud=<LOUDNESS_VERSION>` so a change
    to the normalization re-renders them; the plain path's key is unchanged.
```

(f) `CLAUDE.md` (repo root), in the emcee architecture bullet, after the sentence ending `instrumental-bed mixing llama used to have)` insert:

```
Chunked and bed-active clips are loudness-normalized per sentence/segment
before the gap and the bed mix (`tts/loudness.py`: −20 dBFS speech-active,
−1 dBFS peak ceiling, ±10 dB clamp; module constants, no config), because
Voxtral returns every call at its own level; the unchunked no-bed path ships
the provider's MP3 untouched and is not normalized.
```

- [ ] **Step 4: Run the new tests, then the whole suite**

Run: `./.venv/bin/pytest packages/emcee/tests/test_audio.py packages/emcee/tests/test_loudness.py -q`
Expected: all PASS.

Run: `./.venv/bin/pytest -q`
Expected: all PASS (existing tests use `FakeSpeechProvider`'s silent WAV, which `normalize_speech` returns unchanged; existing cache-hit tests run the same config twice, so the new key term matches on both runs).

- [ ] **Step 5: Commit**

```bash
git add packages/emcee/src/emcee/audio.py packages/emcee/tests/test_audio.py CLAUDE.md
git commit -m "feat(emcee): loudness-normalize chunked and bedded TTS before mixing

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01X5uiQcfXG7dM4oKpyCxmr4"
```
