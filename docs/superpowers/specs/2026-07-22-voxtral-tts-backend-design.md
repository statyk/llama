# llama — Hosted Voxtral DJ-Voice Backend

**Date:** 2026-07-22
**Status:** Approved design, pending implementation plan

## Purpose

Add Mistral's **hosted Voxtral TTS** (`voxtral-mini-tts-2603`, La Plateforme
`/v1/audio/speech`) as a speech backend for the DJ-voice feature, and make it
the **new default** over ElevenLabs. Motivation: Mistral's own human eval
prefers Voxtral's naturalness to ElevenLabs Flash v2.5, it is far cheaper
(~$0.016 / 1k input characters), and it supports both preset voices and
zero-shot voice cloning from a short reference clip — letting the station mint
a custom DJ voice. The project is strictly non-commercial, so nothing here is
gated by the CC BY-NC weights license (that clause governs self-hosting, not
the paid API).

This is deliberately a **small, well-bounded addition**: it reuses the entire
`SpeechProvider` abstraction, per-segment cache, hard-fail-scoped-to-show
behavior, `dj_audio` manifest block, and `speech_provider_for` factory built
for the ElevenLabs feature
(`docs/superpowers/specs/2026-07-22-elevenlabs-dj-voice-design.md`). It is a
new backend module plus config plumbing — no pipeline, CLI, or manifest
changes.

## Decisions made during brainstorming

- **Hosted, not self-hosted.** Ship the hosted Mistral API path first. It is a
  near-drop-in peer to `ElevenLabsProvider` (hosted HTTP + key), needs no GPU,
  and is the cheapest way to A/B the voice against ElevenLabs before any
  offline investment. Self-hosting (MLX on Apple Silicon, or vLLM Omni on an
  NVIDIA ≥16 GB card) is explicitly deferred — see Out of scope. Because
  hosted Voxtral is not local, it does not even trigger the standing "local
  backend must be a shell-out add-on" rule; it is simply a second hosted
  provider.
- **New default over ElevenLabs.** `[tts] backend` default flips
  `"elevenlabs"` → `"voxtral"`. ElevenLabs remains a first-class opt-in
  backend, unchanged.
- **Preset + cloning from day one.** A show's voice is either a named Mistral
  preset (`voice` = preset name → `voice_id`) or a cloned voice from a
  station-level reference clip (`voice_clone` = path to a WAV → `ref_audio`).
- **Raw httpx, no SDK.** Match the house style — `ElevenLabsProvider` and
  `openrouter.py` both call the REST API directly with `httpx`. Do **not** add
  the `mistralai` SDK dependency.
- **Reuse the cache verbatim.** The package stage keys segments on
  `sha256(text + speech.voice + speech.model)`
  (`src/llama/stages/package.py:63`). The new provider exposes `.voice` and
  `.model` such that this key already does the right thing — including
  invalidating when a clone reference changes — with **zero change to
  `package.py`**.

## Architecture

### New backend — `src/llama/tts/voxtral.py`

`VoxtralProvider`, modeled on `ElevenLabsProvider`
(`src/llama/tts/elevenlabs.py`), duck-typing the existing `SpeechProvider`
protocol (`synthesize(text) -> bytes`, `close()`, context manager):

- **Endpoint:** `POST https://api.mistral.ai/v1/audio/speech`.
- **Auth:** `Authorization: Bearer <key>`. Key from **`MISTRAL_API_KEY`** env
  (wins) or `[tts] api_key`, mirroring the env-wins idiom of
  `ELEVENLABS_API_KEY` / `OPENROUTER_API_KEY` / `SETLISTFM_API_KEY`. Missing
  key when voice is active raises `SpeechError`; never degrade silently.
- **Request body:** `{"model": <model>, "input": text,
  "response_format": "mp3", <voice selector>}` where the selector is:
  - preset: `"voice_id": "<preset name>"`, or
  - clone: `"ref_audio": "<base64-encoded reference clip>"`.
- **Response:** JSON with a base64 **`audio_data`** field; decode to MP3 bytes
  before returning. This is the one real behavioral difference from
  `ElevenLabsProvider` (which returns raw audio bytes). Empty/absent
  `audio_data` or a non-200 status raises `SpeechError` with a truncated body,
  exactly as the ElevenLabs backend does.
- **Model default:** falls back to `voxtral-mini-tts-2603` when
  `config.tts.model` is `None` (see config change below).

**Cache identity (`.voice` / `.model` attributes):**

- `.model` = the resolved Voxtral model id.
- `.voice` = the preset name in preset mode, or `"clone:<sha256(clip
  bytes)[:16]>"` in clone mode. Because the package cache key is
  `sha256(text + voice + model)`, swapping the reference clip changes `.voice`
  and correctly invalidates cached segments — no touch to `package.py`.

**Clone reference handling:** in clone mode the reference clip is read from
disk **once at construction**, validated (exists; non-empty), base64-encoded
once, and reused for every segment. Its byte-hash seeds `.voice` (above).

**Per-request length guard:** Mistral recommends ≤ ~300 words / 2 min audio
per request. For MVP, a segment whose text exceeds a conservative character
threshold raises `SpeechError` with a clear message (consistent with
hard-fail-scoped-to-show) rather than silently truncating. Chunk-and-
concatenate is deferred (YAGNI) unless real DJ segments overflow.

### `VERIFY-during-implementation` — confirm before finalizing request/response code

The exact field names below are taken from Mistral docs + community sources
and must be confirmed against the live API (one throwaway call) before the
request/response code is locked:

1. Clone reference field name and encoding — `ref_audio`, and raw base64 vs a
   `data:audio/wav;base64,` URI; accepted reference audio format(s).
2. Preset selection field — `voice_id` vs `voice`, and the exact preset names
   (American / British / French dialects).
3. Whether the REST response is JSON `{"audio_data": <base64>}` (as the SDK
   surfaces) or raw audio bytes; and `response_format` value for MP3.

The live check belongs to the implementation task that writes the provider;
the design (module boundary, cache identity, config surface, factory wiring)
is unaffected by which of these turns out true — only the ~10 lines that build
the request dict and read the response change.

### Config surface — `[tts]` changes (`src/llama/config.py`)

`TTSConfig` currently:

```python
class TTSConfig(BaseModel):
    enabled: bool = False
    backend: str = "elevenlabs"
    voice: str | None = None
    model: str = "eleven_multilingual_v2"
    api_key: str | None = None
```

becomes:

```python
class TTSConfig(BaseModel):
    enabled: bool = False
    backend: str = "voxtral"            # was "elevenlabs"; ElevenLabs now opt-in
    voice: str | None = None            # preset name (voxtral) / voice_id (elevenlabs)
    voice_clone: str | None = None      # path to a reference WAV; when set, clone mode
    model: str | None = None            # was "eleven_multilingual_v2"; per-backend default
    api_key: str | None = None          # MISTRAL_API_KEY / ELEVENLABS_API_KEY env wins
```

- **`model` becomes backend-aware.** Its default drops from the
  ElevenLabs-specific `"eleven_multilingual_v2"` to `None`; each provider
  supplies its own default when `model is None` (`ElevenLabsProvider` →
  `eleven_multilingual_v2`, `VoxtralProvider` → `voxtral-mini-tts-2603`). This
  prevents an ElevenLabs model id leaking into Voxtral calls. `ElevenLabsProvider`
  gains the same `model or <default>` fallback so an unset `model` keeps
  working for it.
- **`voice_clone`** is new. When set, `VoxtralProvider` runs in clone mode and
  `voice` (preset) is ignored. When unset, preset mode via `voice`.
- Update the commented `[tts]` block in `DEFAULT_CONFIG_TOML`: new default
  backend, `MISTRAL_API_KEY`, preset-name semantics of `voice`, and
  `voice_clone`. Keep
  `tests/test_config.py::test_default_config_template_matches_defaults` green.

### Factory — `speech_provider_for` (`src/llama/tts/__init__.py`)

Add a `"voxtral"` branch beside the existing `elevenlabs`/`fake` branches:

```python
if backend == "voxtral":
    if not (voice or config.tts.voice_clone):
        raise SpeechError("no Voxtral voice configured: set [tts] voice "
                          "(preset) or [tts] voice_clone (reference clip)")
    return VoxtralProvider(voice=voice, clone_ref=config.tts.voice_clone,
                           model=config.tts.model, api_key=config.tts.api_key)
```

The existing `elevenlabs` branch keeps its `if not voice` guard; only its
`model=` argument changes to pass the possibly-`None` value through.

### Everything else is unchanged

The DJ-voice plumbing already merged carries this backend with no edits:

- **CLI / pipeline / stamping:** `--voice/--no-voice`, `Criteria.voice`,
  `Provenance.voice`, voice-implies-script, per-show `SpeechError` handling,
  and provider construction in `_execute` are all backend-agnostic — they
  resolve a `voice` string and call `speech_provider_for`. The `voice` string
  is now a Voxtral preset name instead of an ElevenLabs voice_id; nothing in
  the plumbing cares.
- **Package stage:** `_synthesize_dj_audio` calls `speech.synthesize(text)`
  and keys on `speech.voice` / `speech.model`. Unchanged.
- **Manifest:** `dj_audio` block and per-break `audio` paths. Unchanged.

**Scope limit (deliberate):** the clone reference is **station-level**
(`[tts] voice_clone`). A profile can still override the preset `voice`
(existing `Profile.voice`), but per-profile cloning is deferred. No new CLI
flags: `voice_clone` is a config-file value (a hand-edited path), like other
non-flag config.

### Default-switch impact

Because TTS is opt-in (`enabled = false`, and a voice must be set), the blast
radius of flipping the default backend is small. The only affected setup is a
config that (a) relies on the default backend rather than naming it, and (b)
has ElevenLabs credentials but no Mistral key — that config now needs an
explicit `backend = "elevenlabs"`. This is the intended consequence of making
Voxtral the default and is documented in the config template and release note.
There is no migration; existing configs that name `backend = "elevenlabs"`
explicitly are unaffected.

## Components / files touched

- **New:** `src/llama/tts/voxtral.py` — `VoxtralProvider`.
- `src/llama/tts/__init__.py` — `"voxtral"` factory branch; pass through
  `model=None`.
- `src/llama/tts/elevenlabs.py` — accept `model: str | None`, default to
  `eleven_multilingual_v2` when `None`.
- `src/llama/config.py` — `TTSConfig` (`backend` default, `voice_clone`,
  `model` → `None`); `[tts]` block in `DEFAULT_CONFIG_TOML`.
- **Docs:** README, station-brief, workflow, CLAUDE.md — Voxtral as default
  DJ-voice backend, `MISTRAL_API_KEY`, presets vs `voice_clone`, ElevenLabs
  now opt-in.
- **Tests:** `VoxtralProvider` unit tests (mocked `httpx.MockTransport`);
  config default + template-sync; factory branch; one opt-in live test.

## Testing strategy

1. **`VoxtralProvider` unit tests (offline, `httpx.MockTransport`)**, mirroring
   the ElevenLabs backend tests:
   - preset request shape: endpoint, `Bearer` auth header, `input`,
     `response_format: "mp3"`, `voice_id` present / `ref_audio` absent, model
     defaulting when `None`;
   - clone request shape: `ref_audio` present (base64 of the reference bytes),
     `voice_id` absent; `.voice` == `clone:<hash>` and changes when the clip
     changes;
   - response handling: base64 `audio_data` decoded to the expected bytes;
   - error paths: non-200 → `SpeechError`; empty/missing `audio_data` →
     `SpeechError`; missing key (no env, no config) → `SpeechError`;
   - length guard: an over-long segment → `SpeechError`.
2. **Config / factory:** `[tts] backend` defaults to `"voxtral"`; template
   round-trips (`test_default_config_template_matches_defaults`);
   `speech_provider_for` builds a `VoxtralProvider` for preset and for clone,
   and raises when neither `voice` nor `voice_clone` is set; ElevenLabs branch
   still builds with `model = None`.
3. **Pipeline tests unchanged.** They run on `backend = "fake"` /
   `FakeSpeechProvider`; the new backend does not touch the hermetic offline
   suite.
4. **Live test (opt-in, `pytest -m live`):** one call to the real Mistral API
   with a short line asserting playable MP3 bytes; requires `MISTRAL_API_KEY`;
   not in CI. This is also where the three `VERIFY-during-implementation`
   field questions are settled.

## Out of scope / future work

- **Self-hosted Voxtral (offline / zero-cost):** deferred. Two viable paths
  exist for later — MLX quantized build on Apple Silicon (~2.5 GB, e.g. a
  `voxtral-cli` shell-out, matching the "local backend = optional shell-out
  add-on" rule), or vLLM Omni on an NVIDIA ≥16 GB card. Whichever lands would
  be a third `speech_provider_for` branch reusing the same request semantics
  at a local endpoint. Note: some MLX ports expose presets but not
  reference-clip cloning — verify before relying on offline cloning.
- **Per-profile voice cloning:** deferred; cloning is station-level for now.
- **Chunk-and-concatenate for over-long segments:** deferred behind the
  length guard.
- **Streaming / non-MP3 formats:** not needed; per-segment MP3 only.
