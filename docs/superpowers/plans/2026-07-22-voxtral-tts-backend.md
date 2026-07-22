# Hosted Voxtral DJ-Voice Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Mistral's hosted Voxtral TTS as a DJ-voice backend and make it the new default over ElevenLabs, with preset voices and station-level voice cloning.

**Architecture:** A new `VoxtralProvider` duck-types the existing `SpeechProvider` protocol (raw `httpx` to `POST /v1/audio/speech`, base64 `audio_data` response), slotting into the `speech_provider_for` factory beside `elevenlabs`/`fake`. All CLI, pipeline, package-stage, cache, and manifest wiring built for the ElevenLabs feature is reused unchanged; only config defaults and the factory change.

**Tech Stack:** Python 3.14, `httpx` (raw REST, no `mistralai` SDK), Pydantic config models, pytest with `httpx.MockTransport`.

## Global Constraints

- **No new runtime dependency.** Call the REST API with `httpx` directly — the same house style as `src/llama/tts/elevenlabs.py` and `src/llama/llm/openrouter.py`. Do NOT add the `mistralai` SDK.
- **Env key wins over config key.** `MISTRAL_API_KEY` env overrides `[tts] api_key`, matching `ELEVENLABS_API_KEY` / `OPENROUTER_API_KEY` / `SETLISTFM_API_KEY`.
- **Never degrade silently.** A missing key, unreadable clone reference, non-200 response, or empty audio when voice is active raises `SpeechError` (hard-fail-scoped-to-show).
- **Endpoint / model:** `https://api.mistral.ai/v1/audio/speech`, model `voxtral-mini-tts-2603`.
- **Offline test suite stays hermetic.** Unit tests use `httpx.MockTransport`; the pipeline suite keeps running on `backend = "fake"`. The only network test is opt-in `pytest -m live`.
- **Cache key is `sha256(text + speech.voice + speech.model)`** (`src/llama/stages/package.py:63`) — do not change `package.py`; make the provider's `.voice`/`.model` attributes carry the right identity instead.

---

### Task 1: `VoxtralProvider` — preset-voice path

**Files:**
- Create: `src/llama/tts/voxtral.py`
- Test: `tests/test_voxtral.py`

**Interfaces:**
- Consumes: `SpeechError` from `src/llama/tts/provider.py`; the `SpeechProvider` protocol (`synthesize(text) -> bytes`, `close()`, context manager).
- Produces: `VoxtralProvider(voice=None, clone_ref=None, model=None, api_key=None, timeout_s=120, transport=None)` with `.voice: str`, `.model: str`, `.api_key: str | None`, `.synthesize(text) -> bytes`, `.close()`. Module constants `API_URL`, `DEFAULT_MODEL = "voxtral-mini-tts-2603"`, `MAX_INPUT_CHARS = 2000`.

- [ ] **Step 1: Write the failing tests (preset path)**

```python
# tests/test_voxtral.py
import base64
import json

import httpx
import pytest

from llama.tts.provider import SpeechError, SpeechProvider
from llama.tts.voxtral import DEFAULT_MODEL, VoxtralProvider


def _ok_audio(payload=b"mp3bytes"):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"audio_data": base64.b64encode(payload).decode()})
    return handler


def make_preset(handler, *, voice="british-narrator", model=None, api_key="k1"):
    return VoxtralProvider(voice=voice, model=model, api_key=api_key,
                           transport=httpx.MockTransport(handler))


def test_is_a_speech_provider():
    assert isinstance(make_preset(_ok_audio()), SpeechProvider)


def test_preset_request_shape_and_base64_decode():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"audio_data": base64.b64encode(b"MP3!").decode()})

    assert make_preset(handler).synthesize("Tonight, the Dead.") == b"MP3!"
    assert seen["url"] == "https://api.mistral.ai/v1/audio/speech"
    assert seen["auth"] == "Bearer k1"
    assert seen["body"] == {"model": DEFAULT_MODEL, "input": "Tonight, the Dead.",
                            "response_format": "mp3", "voice_id": "british-narrator"}
    assert "ref_audio" not in seen["body"]


def test_preset_voice_and_model_attributes():
    p = make_preset(_ok_audio(), voice="american-dj", model="voxtral-mini-tts-2603")
    assert (p.voice, p.model) == ("american-dj", "voxtral-mini-tts-2603")


def test_model_defaults_when_none():
    assert make_preset(_ok_audio(), model=None).model == DEFAULT_MODEL


def test_env_key_wins_over_config_key(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k-env")
    p = VoxtralProvider(voice="v", api_key="k-config", transport=httpx.MockTransport(_ok_audio()))
    assert p.api_key == "k-env"


def test_missing_key_raises():
    # conftest guarantees no ambient MISTRAL_API_KEY
    with pytest.raises(SpeechError):
        VoxtralProvider(voice="v")


def test_no_voice_and_no_clone_raises():
    with pytest.raises(SpeechError):
        VoxtralProvider(api_key="k")


def test_error_status_raises():
    def handler(request):
        return httpx.Response(429, text="rate limited")
    with pytest.raises(SpeechError):
        make_preset(handler).synthesize("x")


def test_empty_audio_data_raises():
    def handler(request):
        return httpx.Response(200, json={"audio_data": ""})
    with pytest.raises(SpeechError):
        make_preset(handler).synthesize("x")


def test_missing_audio_data_raises():
    def handler(request):
        return httpx.Response(200, json={"nope": 1})
    with pytest.raises(SpeechError):
        make_preset(handler).synthesize("x")


def test_close_and_context_manager():
    p = make_preset(_ok_audio())
    assert p._client.is_closed is False
    p.close()
    assert p._client.is_closed is True
    with make_preset(_ok_audio()) as q:
        assert q._client.is_closed is False
    assert q._client.is_closed is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_voxtral.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'llama.tts.voxtral'`

- [ ] **Step 3: Write the provider (preset path)**

```python
# src/llama/tts/voxtral.py
import base64
import hashlib
import os
from pathlib import Path

import httpx

from llama.tts.provider import SpeechError

API_URL = "https://api.mistral.ai/v1/audio/speech"
DEFAULT_MODEL = "voxtral-mini-tts-2603"
# Mistral recommends <=~300 words / 2 min audio per request. Conservative
# char guard; chunk-and-concatenate is deliberately out of scope (see spec).
MAX_INPUT_CHARS = 2000


class VoxtralProvider:
    def __init__(
        self,
        voice: str | None = None,
        clone_ref: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout_s: int = 120,
        transport: httpx.BaseTransport | None = None,
    ):
        if not voice and not clone_ref:
            raise SpeechError("Voxtral needs a preset voice or a clone reference: "
                              "set [tts] voice or [tts] voice_clone")
        self.model = model or DEFAULT_MODEL
        # Env wins over the config key, matching ELEVENLABS_API_KEY handling.
        self.api_key = os.environ.get("MISTRAL_API_KEY") or api_key
        if not self.api_key:
            raise SpeechError("Mistral API key missing: "
                              "set MISTRAL_API_KEY or [tts] api_key")
        self._ref_b64: str | None = None
        self._preset: str | None = voice
        # Clone reference handling is added in Task 2.
        self.voice = voice
        self._client = httpx.Client(timeout=timeout_s, transport=transport)

    def _body(self, text: str) -> dict:
        body = {"model": self.model, "input": text, "response_format": "mp3"}
        if self._ref_b64 is not None:
            body["ref_audio"] = self._ref_b64
        else:
            body["voice_id"] = self._preset
        return body

    def synthesize(self, text: str) -> bytes:
        if len(text) > MAX_INPUT_CHARS:
            raise SpeechError(f"DJ segment too long for Voxtral "
                              f"({len(text)} > {MAX_INPUT_CHARS} chars)")
        try:
            resp = self._client.post(
                API_URL, json=self._body(text),
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        except httpx.HTTPError as e:
            raise SpeechError(f"voxtral request failed: {e}") from e
        if resp.status_code != 200:
            raise SpeechError(f"voxtral returned {resp.status_code}: {resp.text[:500]}")
        try:
            audio_b64 = resp.json().get("audio_data")
        except ValueError as e:
            raise SpeechError(f"voxtral returned non-JSON: {resp.text[:200]}") from e
        if not audio_b64:
            raise SpeechError("voxtral returned no audio_data")
        return base64.b64decode(audio_b64)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "VoxtralProvider":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_voxtral.py -q`
Expected: PASS (all preset-path tests)

- [ ] **Step 5: Commit**

```bash
git add src/llama/tts/voxtral.py tests/test_voxtral.py
git commit -m "feat: VoxtralProvider preset-voice TTS backend"
```

---

### Task 2: `VoxtralProvider` — clone mode, cache identity, length guard

**Files:**
- Modify: `src/llama/tts/voxtral.py`
- Test: `tests/test_voxtral.py`

**Interfaces:**
- Consumes: `VoxtralProvider` from Task 1.
- Produces: clone mode — when `clone_ref` (a filesystem path) is given, the reference bytes are read once, base64-encoded, sent as `ref_audio`, and `.voice == "clone:" + sha256(bytes)[:16]`. Over-`MAX_INPUT_CHARS` input raises `SpeechError`.

- [ ] **Step 1: Write the failing tests (clone + length guard)**

```python
# append to tests/test_voxtral.py
import hashlib


def make_clone(handler, ref_path, *, api_key="k1"):
    return VoxtralProvider(clone_ref=str(ref_path), api_key=api_key,
                           transport=httpx.MockTransport(handler))


def test_clone_request_uses_ref_audio_not_voice_id(tmp_path):
    ref = tmp_path / "dj.wav"
    ref.write_bytes(b"REFERENCE-AUDIO-BYTES")
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"audio_data": base64.b64encode(b"x").decode()})

    make_clone(handler, ref).synthesize("hi")
    assert seen["body"]["ref_audio"] == base64.b64encode(b"REFERENCE-AUDIO-BYTES").decode()
    assert "voice_id" not in seen["body"]


def test_clone_voice_identity_is_clip_hash(tmp_path):
    ref = tmp_path / "dj.wav"
    ref.write_bytes(b"REFERENCE-AUDIO-BYTES")
    p = make_clone(_ok_audio(), ref)
    expected = "clone:" + hashlib.sha256(b"REFERENCE-AUDIO-BYTES").hexdigest()[:16]
    assert p.voice == expected


def test_clone_identity_changes_when_clip_changes(tmp_path):
    a = tmp_path / "a.wav"; a.write_bytes(b"AAAA")
    b = tmp_path / "b.wav"; b.write_bytes(b"BBBB")
    assert make_clone(_ok_audio(), a).voice != make_clone(_ok_audio(), b).voice


def test_clone_missing_file_raises(tmp_path):
    with pytest.raises(SpeechError):
        make_clone(_ok_audio(), tmp_path / "nope.wav")


def test_clone_empty_file_raises(tmp_path):
    ref = tmp_path / "empty.wav"; ref.write_bytes(b"")
    with pytest.raises(SpeechError):
        make_clone(_ok_audio(), ref)


def test_over_long_segment_raises():
    from llama.tts.voxtral import MAX_INPUT_CHARS
    with pytest.raises(SpeechError):
        make_preset(_ok_audio()).synthesize("x" * (MAX_INPUT_CHARS + 1))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_voxtral.py -k "clone or over_long" -q`
Expected: FAIL — clone tests fail (`ref_audio` absent / `.voice` is `None`), `test_over_long_segment_raises` already passes (guard was added in Task 1).

- [ ] **Step 3: Add clone handling in `__init__`**

Replace the three lines in `__init__` from `self._ref_b64: str | None = None` through `self.voice = voice` with:

```python
        if clone_ref:
            try:
                ref_bytes = Path(clone_ref).read_bytes()
            except OSError as e:
                raise SpeechError(f"voice_clone reference unreadable: {e}") from e
            if not ref_bytes:
                raise SpeechError(f"voice_clone reference is empty: {clone_ref}")
            self._ref_b64 = base64.b64encode(ref_bytes).decode()
            self._preset = None
            self.voice = "clone:" + hashlib.sha256(ref_bytes).hexdigest()[:16]
        else:
            self._ref_b64 = None
            self._preset = voice
            self.voice = voice
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_voxtral.py -q`
Expected: PASS (all preset + clone + guard tests)

- [ ] **Step 5: Commit**

```bash
git add src/llama/tts/voxtral.py tests/test_voxtral.py
git commit -m "feat: Voxtral clone mode via voice_clone reference clip"
```

---

### Task 3: ElevenLabs backend accepts `model = None`

**Files:**
- Modify: `src/llama/tts/elevenlabs.py`
- Test: `tests/test_tts.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `ElevenLabsProvider(model=None)` resolves `.model` to `"eleven_multilingual_v2"`. Module constant `DEFAULT_MODEL = "eleven_multilingual_v2"`. (Required because Task 4 changes the config `model` default to `None`.)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_tts.py
def test_elevenlabs_model_defaults_when_none():
    from llama.tts.elevenlabs import DEFAULT_MODEL
    p = ElevenLabsProvider(voice="v", model=None, api_key="k")
    assert p.model == DEFAULT_MODEL == "eleven_multilingual_v2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tts.py::test_elevenlabs_model_defaults_when_none -q`
Expected: FAIL — `.model` is `None`

- [ ] **Step 3: Add the default**

In `src/llama/tts/elevenlabs.py`, add the constant below `API_URL`:

```python
DEFAULT_MODEL = "eleven_multilingual_v2"
```

Change the `__init__` signature `model: str,` to `model: str | None = None,` and the assignment `self.model = model` to:

```python
        self.model = model or DEFAULT_MODEL
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tts.py -q`
Expected: PASS (new test plus all existing ElevenLabs tests)

- [ ] **Step 5: Commit**

```bash
git add src/llama/tts/elevenlabs.py tests/test_tts.py
git commit -m "feat: ElevenLabs backend defaults model when None"
```

---

### Task 4: Config defaults, template, and factory wiring

**Files:**
- Modify: `src/llama/config.py` (`TTSConfig`, `DEFAULT_CONFIG_TOML`)
- Modify: `src/llama/tts/__init__.py` (`speech_provider_for`)
- Test: `tests/test_tts.py`, `tests/test_config.py`

**Interfaces:**
- Consumes: `VoxtralProvider` (Tasks 1-2), `ElevenLabsProvider` with `model=None` support (Task 3).
- Produces: `TTSConfig` with `backend="voxtral"` default, new `voice_clone: str | None = None`, `model: str | None = None`. `speech_provider_for` gains a `"voxtral"` branch. ElevenLabs remains available via explicit `backend = "elevenlabs"`.

- [ ] **Step 1: Update the factory and config tests to the new defaults**

Edit `tests/test_config.py::test_tts_defaults` (currently asserts `backend == "elevenlabs"` and `model == "eleven_multilingual_v2"`) to:

```python
def test_tts_defaults():
    cfg = Config()
    assert cfg.tts.enabled is False
    assert cfg.tts.backend == "voxtral"
    assert cfg.tts.voice is None
    assert cfg.tts.voice_clone is None
    assert cfg.tts.model is None
```

In `tests/test_tts.py`, pin the backend on the ElevenLabs factory test (it currently relies on the default backend). Change `test_factory_elevenlabs_uses_voice_and_model`:

```python
def test_factory_elevenlabs_uses_voice_and_model(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    cfg = Config.model_validate({"tts": {"backend": "elevenlabs", "model": "eleven_turbo_v2_5"}})
    p = speech_provider_for(cfg, "v-abc")
    assert isinstance(p, ElevenLabsProvider)
    assert (p.voice, p.model) == ("v-abc", "eleven_turbo_v2_5")
```

Then add new Voxtral factory tests:

```python
def test_factory_voxtral_is_default_preset(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    from llama.tts.voxtral import VoxtralProvider
    p = speech_provider_for(Config.model_validate({"tts": {"voice": "british-dj"}}), "british-dj")
    assert isinstance(p, VoxtralProvider)
    assert p.voice == "british-dj"


def test_factory_voxtral_clone_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    from llama.tts.voxtral import VoxtralProvider
    ref = tmp_path / "dj.wav"; ref.write_bytes(b"REF")
    cfg = Config.model_validate({"tts": {"voice_clone": str(ref)}})
    p = speech_provider_for(cfg, None)
    assert isinstance(p, VoxtralProvider)
    assert p.voice.startswith("clone:")


def test_factory_voxtral_no_voice_no_clone_raises(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    with pytest.raises(SpeechError):
        speech_provider_for(Config(), None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tts.py tests/test_config.py -q`
Expected: FAIL — `voice_clone` not a field / default still `"elevenlabs"` / no `"voxtral"` factory branch.

- [ ] **Step 3: Update `TTSConfig`**

In `src/llama/config.py`, replace the `TTSConfig` body:

```python
class TTSConfig(BaseModel):
    """Spoken DJ patter (text-to-speech of the DJ script). Opt-in."""
    enabled: bool = False               # nothing calls a TTS API unless voice is active
    backend: str = "voxtral"            # or "elevenlabs" / "fake"
    voice: str | None = None            # voxtral preset name / elevenlabs voice_id
    voice_clone: str | None = None      # path to a reference WAV; when set, voxtral clones it
    model: str | None = None            # per-backend default when unset
    api_key: str | None = None          # MISTRAL_API_KEY / ELEVENLABS_API_KEY env wins
```

- [ ] **Step 4: Update `DEFAULT_CONFIG_TOML` `[tts]` block**

In `src/llama/config.py`, replace the commented `[tts]` lines (the `backend`, `voice`, `model`, `api_key` comment lines) with:

```python
# backend = "voxtral"        # hosted Mistral Voxtral TTS (default); or
#                            # "elevenlabs"; or "fake" for tests
# voice = "..."              # voxtral preset name (or elevenlabs voice_id); a
#                            # profile can set its own `voice` to override this
# voice_clone = "..."        # path to a 3-25s reference WAV; when set, voxtral
#                            # clones that voice (ignores `voice`)
# model = "..."              # per-backend default when unset
#                            # (voxtral-mini-tts-2603 / eleven_multilingual_v2)
# api_key = "..."            # MISTRAL_API_KEY / ELEVENLABS_API_KEY env (env wins)
```

- [ ] **Step 5: Add the `"voxtral"` factory branch**

In `src/llama/tts/__init__.py`, add the import and branch. Add to imports:

```python
from llama.tts.voxtral import VoxtralProvider
```

Insert before the `elevenlabs` branch in `speech_provider_for`:

```python
    if backend == "voxtral":
        if not (voice or config.tts.voice_clone):
            raise SpeechError("no Voxtral voice configured: set [tts] voice "
                              "(preset) or [tts] voice_clone (reference clip)")
        return VoxtralProvider(voice=voice, clone_ref=config.tts.voice_clone,
                               model=config.tts.model, api_key=config.tts.api_key)
```

And in the existing `elevenlabs` branch, the `model=config.tts.model` argument now passes a possibly-`None` value — no code change needed there since Task 3 made `ElevenLabsProvider` accept `None`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_tts.py tests/test_config.py -q`
Expected: PASS

- [ ] **Step 7: Run the full suite for regressions**

Run: `pytest -q`
Expected: PASS (pipeline/voice tests unaffected — they pin `backend = "fake"`)

- [ ] **Step 8: Commit**

```bash
git add src/llama/config.py src/llama/tts/__init__.py tests/test_tts.py tests/test_config.py
git commit -m "feat: default TTS to hosted Voxtral; add voice_clone config + factory branch"
```

---

### Task 5: Documentation

**Files:**
- Modify: `README.md`, `docs/station-brief.md`, `docs/workflow.md`, `CLAUDE.md`

**Interfaces:**
- Consumes: the shipped behavior from Tasks 1-4.
- Produces: docs describing Voxtral as the default DJ-voice backend.

- [ ] **Step 1: Find every DJ-voice / ElevenLabs mention**

Run: `grep -rn -i "elevenlabs\|ELEVENLABS_API_KEY\|\[tts\]\|text-to-speech\|DJ.voice" README.md docs/station-brief.md docs/workflow.md CLAUDE.md`
Read each hit in context before editing.

- [ ] **Step 2: Update the prose**

For each file, make these edits (adapt wording to the surrounding sentence; keep each file's voice):
- State the default backend is **hosted Voxtral** (Mistral `voxtral-mini-tts-2603`, `/v1/audio/speech`), with **ElevenLabs** as an opt-in alternative (`backend = "elevenlabs"`).
- Key env var for the default path is **`MISTRAL_API_KEY`** (ElevenLabs still uses `ELEVENLABS_API_KEY`).
- `[tts] voice` is a **preset name** for Voxtral; **`[tts] voice_clone`** points at a 3-25s reference WAV to clone a custom station DJ voice (clone ignores `voice`).
- Note the project is non-commercial, so the CC BY-NC weights license is irrelevant to the hosted API path.
- In `CLAUDE.md`, update the "Voice (opt-in TTS)" architecture paragraph so it lists `voxtral` (default) + `elevenlabs` + `fake` backends and the `voice_clone` option, and note self-hosting is deferred.

- [ ] **Step 3: Verify no stale "default is ElevenLabs" claims remain**

Run: `grep -rn -i "elevenlabs" README.md docs/station-brief.md docs/workflow.md CLAUDE.md`
Expected: every remaining mention frames ElevenLabs as the opt-in alternative, not the default.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/station-brief.md docs/workflow.md CLAUDE.md
git commit -m "docs: hosted Voxtral is the default DJ-voice backend"
```

---

### Task 6: Opt-in live test (settles the API-contract unknowns)

**Files:**
- Modify: `tests/test_live_smoke.py` (or wherever `pytest -m live` tests live — confirm with `grep -rn "mark.live" tests/`)

**Interfaces:**
- Consumes: `VoxtralProvider`.
- Produces: one `@pytest.mark.live` test that hits the real Mistral API. Running it confirms the three field-name assumptions from the spec's `VERIFY-during-implementation` section (`ref_audio` encoding, `voice_id` preset field, JSON `audio_data` response). If the live call reveals different field names, fix `src/llama/tts/voxtral.py` AND the Task 1/2 mock tests to match, then re-run both.

- [ ] **Step 1: Add the live test**

```python
# in the live-marked test module
import os

import pytest

from llama.tts.voxtral import VoxtralProvider


@pytest.mark.live
def test_voxtral_live_preset_returns_mp3():
    if not os.environ.get("MISTRAL_API_KEY"):
        pytest.skip("MISTRAL_API_KEY not set")
    with VoxtralProvider(voice="british-dj") as p:  # adjust to a real preset name
        audio = p.synthesize("Good evening from the archive.")
    assert audio[:3] == b"ID3" or audio[:2] == b"\xff\xfb"  # MP3 header
    assert len(audio) > 1000
```

- [ ] **Step 2: Run it (manual / opt-in) and reconcile field names**

Run: `MISTRAL_API_KEY=... pytest -m live -k voxtral -q`
Expected: PASS. If it fails on request/response shape, correct `voxtral.py` and the mock-based tests in `tests/test_voxtral.py` to the real contract, re-run `pytest tests/test_voxtral.py -q` (must stay green), then re-run the live test.

- [ ] **Step 3: Commit**

```bash
git add tests/test_live_smoke.py
git commit -m "test: opt-in live Voxtral TTS smoke test"
```

---

## Self-Review

**Spec coverage:**
- New `VoxtralProvider` module (endpoint, auth, preset/clone request, base64 response, errors, length guard) → Tasks 1-2. ✓
- Cache identity via `.voice`/`.model`, no `package.py` change → Task 2 (clone hash) + Task 1 (`.model`). ✓
- `model` backend-aware (`None` default; per-provider fallback) → Task 3 (elevenlabs) + Task 1 (voxtral) + Task 4 (config). ✓
- Config: `backend` default flip, `voice_clone`, `DEFAULT_CONFIG_TOML` → Task 4. ✓
- Factory `"voxtral"` branch → Task 4. ✓
- Default-switch impact (existing tests pinning backend) → Task 4 Step 1. ✓
- Docs (README/station-brief/workflow/CLAUDE.md) → Task 5. ✓
- Testing strategy (mock unit tests, config/factory, hermetic pipeline, opt-in live) → Tasks 1,2,4,6. ✓
- VERIFY-during-implementation field questions → Task 6. ✓
- Out-of-scope items (self-hosting, per-profile clone, chunking, streaming) → correctly absent from tasks. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code; error paths are concrete `SpeechError` raises, not "add error handling."

**Type consistency:** `VoxtralProvider(voice, clone_ref, model, api_key, timeout_s, transport)` and attrs `.voice`/`.model`/`.api_key` used consistently across Tasks 1, 2, 4, 6. Factory passes `clone_ref=config.tts.voice_clone` matching the `clone_ref` param name. `DEFAULT_MODEL` names distinct per module (`voxtral.py` and `elevenlabs.py`), each imported locally in its own test. `MAX_INPUT_CHARS` defined Task 1, referenced Task 2 test.
