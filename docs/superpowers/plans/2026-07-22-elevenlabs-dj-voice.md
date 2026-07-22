# ElevenLabs DJ Voice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Optional text-to-speech of the verbatim DJ script: when voice is active for a show, its package gains a `dj-audio/` directory of per-segment MP3 clips (intro, per-set intros, set-break notes, outro) plus a `dj_audio` manifest block, synthesized via ElevenLabs.

**Architecture:** A new speech-provider abstraction (`src/llama/tts/`) parallel to the LLM layer — `SpeechProvider` protocol, `ElevenLabsProvider`, `FakeSpeechProvider`, `speech_provider_for` factory, no tiers/ladder. TTS is folded into the existing `package` stage (not a new stage): `run_package` synthesizes one MP3 per `DJNotes` segment before the manifest is written, with hash-keyed per-segment caching so repackaging never re-spends on unchanged text. Voice threads through the CLI exactly as `script` does: resolved per run, stamped into `Criteria`/`Provenance`, honored on replay.

**Tech Stack:** Python ≥3.11, httpx (already a dependency — no new deps), pydantic v2, pytest.

**Spec:** `docs/superpowers/specs/2026-07-22-elevenlabs-dj-voice-design.md` — read it before starting.

## Global Constraints

- Launch backend is **ElevenLabs only** (plus `fake` for tests). No local backend, no Kokoro, no voice cloning, no monolith full-read audio, no `profile edit` command — all explicitly out of scope.
- **No tiers.** Unlike the LLM layer's `provider_ladder`, there is no tier/ladder/retry-escalation machinery for TTS. One provider, one voice, one model per run.
- Global `[tts] enabled` defaults to **false** (opt-in). A profile that explicitly names a `voice` is voiced with that voice even when the global flag is off.
- **Voice implies script**: wherever voice resolves active, `script` is forced on for that run.
- **Hard-fail, scoped to the show**: any segment's TTS failure raises `SpeechError`; that show yields no package (no manifest at all), other shows in the batch continue. Never degrade silently — voice active with no resolvable voice id or missing API key is an error.
- **Cache per segment**: key = hash of (segment text + voice + model), stored in a sidecar map beside the clips. Matching keys skip synthesis; `--force` re-renders all.
- API key precedence: `ELEVENLABS_API_KEY` env var wins over `[tts] api_key` config (matching `SETLISTFM_API_KEY` in `src/llama/setlistfm.py:128`).
- All tests are offline and deterministic (`pytest -q`); the one real-ElevenLabs test carries `@pytest.mark.live` (deselected by default) and is keyed off `ELEVENLABS_API_KEY`.
- Keep `DEFAULT_CONFIG_TOML` consistent with `tests/test_config.py::test_default_config_template_matches_defaults` (the seeded file, untouched, must behave exactly like no config file — so the `[tts]` block is fully commented).
- Artifacts are written atomically (temp file + rename); the manifest is the **last** package artifact written so a mid-synthesis failure leaves no manifest.
- Audio files are gitignored; the fake's silent MP3 is a bytes constant in code, never a committed file.
- Commit after every task with conventional prefixes (`feat:`, `test:`). All `pytest` commands assume the venv is active (`source .venv/bin/activate`).

## File Structure

```
src/llama/tts/                 # NEW package, mirrors src/llama/llm/
  __init__.py                  # speech_provider_for factory
  provider.py                  # SpeechProvider protocol + SpeechError
  elevenlabs.py                # ElevenLabsProvider (HTTP)
  fake.py                      # FakeSpeechProvider + SILENT_MP3
src/llama/config.py            # TTSConfig, Config.tts, [tts] block in DEFAULT_CONFIG_TOML
src/llama/profiles.py          # Profile.voice
src/llama/models.py            # Criteria.voice, Provenance.voice, DJAudio, Manifest.dj_audio, SetBreak.audio
src/llama/manifest.py          # build_manifest gains dj_audio
src/llama/stages/package.py    # per-segment synthesis, cache, dj-audio/, manifest-last ordering
src/llama/pipeline.py          # process_show gains voice/speech
src/llama/cli.py               # voice resolution helpers, --voice flags, _execute wiring, except tuple
tests/test_tts.py              # NEW: provider/factory unit tests
tests/test_cli_voice.py        # NEW: resolution helpers + CLI stamping tests
tests/test_voice_pipeline.py   # NEW: end-to-end voiced pipeline over FakeSpeechProvider
tests/{test_config,test_profiles,test_models,test_manifest,test_stage_package,test_pipeline,test_live_smoke}.py  # additions
tests/conftest.py              # delete ambient ELEVENLABS_API_KEY
```

**Task dependency order:** 1 → 2 (factory reads `config.tts`); 3 and 4 are independent of 2 (models only, but both touch `models.py` — run sequentially); 5 needs 2 + 4; 6 needs 5; 7 needs 2 + 3 + 6; 8 needs 7; 9 needs 2 only.

**Model guidance for dispatch:** Tasks 1, 3, 4, 9 are mechanical (well-suited to a cheaper implementer model). Task 2 is mostly mechanical (mirrors the existing `llm/` package shape). Tasks 5 and 7 need design judgment (cache/failure ordering; enable-semantics resolution across five commands). Tasks 6 and 8 are moderate.

---

### Task 1: TTSConfig + `[tts]` config template block

**Files:**
- Modify: `src/llama/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: existing `Config` / `DEFAULT_CONFIG_TOML` in `src/llama/config.py`.
- Produces: `TTSConfig(BaseModel)` with fields `enabled: bool = False`, `backend: str = "elevenlabs"`, `voice: str | None = None`, `model: str = "eleven_multilingual_v2"`, `api_key: str | None = None`; `Config.tts: TTSConfig` (default factory). Later tasks read `config.tts.<field>` exactly by these names.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_tts_defaults():
    cfg = Config()
    assert cfg.tts.enabled is False
    assert cfg.tts.backend == "elevenlabs"
    assert cfg.tts.voice is None
    assert cfg.tts.model == "eleven_multilingual_v2"
    assert cfg.tts.api_key is None


def test_tts_from_toml(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text('[tts]\nenabled = true\nvoice = "v-abc"\n'
                 'model = "eleven_turbo_v2_5"\napi_key = "k1"\n')
    cfg = load_config(p)
    assert cfg.tts.enabled is True
    assert cfg.tts.voice == "v-abc"
    assert cfg.tts.model == "eleven_turbo_v2_5"
    assert cfg.tts.api_key == "k1"


def test_default_config_template_documents_tts():
    # Fully commented: the seeded file must still behave exactly like no config
    # file (test_default_config_template_matches_defaults guards this), and
    # [tts] enabled defaults to false.
    assert "# [tts]" in DEFAULT_CONFIG_TOML
    assert "ELEVENLABS_API_KEY" in DEFAULT_CONFIG_TOML
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -q`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'tts'` (and the template assertion fails)

- [ ] **Step 3: Write the implementation**

In `src/llama/config.py`, add after `SetlistFMConfig`:

```python
class TTSConfig(BaseModel):
    """Spoken DJ patter (text-to-speech of the DJ script). Opt-in."""
    enabled: bool = False               # nothing calls ElevenLabs unless voice is active
    backend: str = "elevenlabs"         # or "fake" for tests
    voice: str | None = None            # station default ElevenLabs voice_id
    model: str = "eleven_multilingual_v2"  # quality default, overridable
    api_key: str | None = None          # ELEVENLABS_API_KEY env takes precedence
```

Add to `Config` beside `setlistfm`:

```python
    tts: TTSConfig = Field(default_factory=TTSConfig)
```

In `DEFAULT_CONFIG_TOML`, insert after the `[setlistfm]` block (before `[jerrybase]`):

```toml
# [tts]                      # spoken DJ patter: per-segment MP3 clips of the
#                            # DJ script under package/dj-audio/ (ElevenLabs)
# enabled = true             # default false; a profile with an explicit
#                            # `voice` is voiced even when this is off
# voice = "..."              # station default ElevenLabs voice_id
# model = "eleven_multilingual_v2"   # quality default
# api_key = "..."            # or ELEVENLABS_API_KEY env var (env wins)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -q`
Expected: all pass — including the pre-existing `test_default_config_template_matches_defaults` (the block is fully commented, so parsing the template yields defaults).

- [ ] **Step 5: Commit**

```bash
git add src/llama/config.py tests/test_config.py
git commit -m "feat: add [tts] config surface (TTSConfig + commented template block)"
```

---

### Task 2: `src/llama/tts/` speech-provider package

**Files:**
- Create: `src/llama/tts/__init__.py`, `src/llama/tts/provider.py`, `src/llama/tts/fake.py`, `src/llama/tts/elevenlabs.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_tts.py`

**Interfaces:**
- Consumes: `llama.errors.LlamaError`; `Config.tts` from Task 1.
- Produces (later tasks import exactly these):
  - `llama.tts.provider.SpeechError(LlamaError)`; `llama.tts.provider.SpeechProvider` (runtime-checkable Protocol, `synthesize(self, text: str) -> bytes`).
  - `llama.tts.fake.SILENT_MP3: bytes`; `llama.tts.fake.FakeSpeechProvider(fail: bool = False)` with attributes `voice == "fake-voice"`, `model == "fake-model"`, `calls: list[str]`.
  - `llama.tts.elevenlabs.ElevenLabsProvider(voice, model, api_key=None, timeout_s=120, transport=None)` with attributes `voice`, `model`, `api_key`.
  - `llama.tts.speech_provider_for(config: Config, voice: str | None) -> SpeechProvider`.

- [ ] **Step 1: Guard tests from ambient keys**

Append to `tests/conftest.py` (beside the setlistfm fixture):

```python
@pytest.fixture(autouse=True)
def _no_ambient_elevenlabs_key(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
```

- [ ] **Step 2: Write the failing tests**

`tests/test_tts.py`:

```python
import json

import httpx
import pytest

from llama.config import Config
from llama.tts import speech_provider_for
from llama.tts.elevenlabs import ElevenLabsProvider
from llama.tts.fake import SILENT_MP3, FakeSpeechProvider
from llama.tts.provider import SpeechError, SpeechProvider


def test_fake_returns_silent_mp3_and_records_calls():
    fake = FakeSpeechProvider()
    assert isinstance(fake, SpeechProvider)
    assert fake.synthesize("Good evening.") == SILENT_MP3
    assert SILENT_MP3.startswith(b"\xff\xfb")  # a real MPEG frame header
    assert fake.calls == ["Good evening."]
    assert (fake.voice, fake.model) == ("fake-voice", "fake-model")


def test_fake_armed_to_fail():
    fake = FakeSpeechProvider(fail=True)
    with pytest.raises(SpeechError):
        fake.synthesize("x")
    assert fake.calls == ["x"]  # the attempt is still recorded


def make_provider(handler, api_key="k1"):
    return ElevenLabsProvider(voice="v-abc", model="eleven_multilingual_v2",
                              api_key=api_key, transport=httpx.MockTransport(handler))


def test_elevenlabs_request_shape():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers["xi-api-key"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=b"mp3bytes")

    assert make_provider(handler).synthesize("Tonight, the Grateful Dead.") == b"mp3bytes"
    assert seen["url"].endswith("/v1/text-to-speech/v-abc")
    assert seen["key"] == "k1"
    assert seen["body"] == {"text": "Tonight, the Grateful Dead.",
                            "model_id": "eleven_multilingual_v2"}


def test_elevenlabs_env_key_wins_over_config_key(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k-env")
    p = ElevenLabsProvider(voice="v", model="m", api_key="k-config")
    assert p.api_key == "k-env"


def test_elevenlabs_missing_key_raises():
    # conftest guarantees no ambient ELEVENLABS_API_KEY
    with pytest.raises(SpeechError):
        ElevenLabsProvider(voice="v", model="m")


def test_elevenlabs_error_status_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="rate limited")

    with pytest.raises(SpeechError):
        make_provider(handler).synthesize("x")


def test_factory_fake_backend():
    cfg = Config.model_validate({"tts": {"backend": "fake"}})
    assert isinstance(speech_provider_for(cfg, "ignored"), FakeSpeechProvider)


def test_factory_elevenlabs_uses_voice_and_model(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    cfg = Config.model_validate({"tts": {"model": "eleven_turbo_v2_5"}})
    p = speech_provider_for(cfg, "v-abc")
    assert isinstance(p, ElevenLabsProvider)
    assert (p.voice, p.model) == ("v-abc", "eleven_turbo_v2_5")


def test_factory_no_voice_raises(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    with pytest.raises(SpeechError):
        speech_provider_for(Config(), None)


def test_factory_unknown_backend_raises():
    cfg = Config.model_validate({"tts": {"backend": "kokoro"}})
    with pytest.raises(SpeechError):
        speech_provider_for(cfg, "v")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_tts.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'llama.tts'`

- [ ] **Step 4: Write the implementation**

`src/llama/tts/provider.py`:

```python
from typing import Protocol, runtime_checkable

from llama.errors import LlamaError


class SpeechError(LlamaError):
    """A speech backend failed or is unusably configured (missing key/voice)."""


@runtime_checkable
class SpeechProvider(Protocol):
    def synthesize(self, text: str) -> bytes: ...  # encoded MP3 audio bytes
```

`src/llama/tts/fake.py`:

```python
from llama.tts.provider import SpeechError

# One silent 417-byte MPEG-1 Layer III frame (128 kbps, 44.1 kHz): a small but
# structurally valid MP3, so packaged dj-audio files are real audio in tests.
SILENT_MP3 = b"\xff\xfb\x90\x00" + bytes(413)


class FakeSpeechProvider:
    """Test backend: returns SILENT_MP3, records synthesized texts.

    voice/model are fixed placeholders (the factory ignores the resolved voice
    for the fake) so package-stage cache keys are deterministic in tests.
    Arm with fail=True for the hard-fail tests.
    """

    def __init__(self, fail: bool = False):
        self.voice = "fake-voice"
        self.model = "fake-model"
        self.fail = fail
        self.calls: list[str] = []

    def synthesize(self, text: str) -> bytes:
        self.calls.append(text)
        if self.fail:
            raise SpeechError("FakeSpeechProvider armed to fail")
        return SILENT_MP3
```

`src/llama/tts/elevenlabs.py`:

```python
import os

import httpx

from llama.tts.provider import SpeechError

API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


class ElevenLabsProvider:
    def __init__(
        self,
        voice: str,
        model: str,
        api_key: str | None = None,
        timeout_s: int = 120,
        transport: httpx.BaseTransport | None = None,
    ):
        self.voice = voice
        self.model = model
        # Env wins over the config key, matching SETLISTFM_API_KEY handling.
        self.api_key = os.environ.get("ELEVENLABS_API_KEY") or api_key
        if not self.api_key:
            raise SpeechError("ElevenLabs API key missing: "
                              "set ELEVENLABS_API_KEY or [tts] api_key")
        self._client = httpx.Client(timeout=timeout_s, transport=transport)

    def synthesize(self, text: str) -> bytes:
        try:
            resp = self._client.post(
                API_URL.format(voice_id=self.voice),
                json={"text": text, "model_id": self.model},
                headers={"xi-api-key": self.api_key, "accept": "audio/mpeg"},
            )
        except httpx.HTTPError as e:
            raise SpeechError(f"elevenlabs request failed: {e}") from e
        if resp.status_code != 200:
            raise SpeechError(f"elevenlabs returned {resp.status_code}: {resp.text[:500]}")
        if not resp.content:
            raise SpeechError("elevenlabs returned empty audio")
        return resp.content
```

`src/llama/tts/__init__.py`:

```python
from llama.config import Config
from llama.tts.elevenlabs import ElevenLabsProvider
from llama.tts.fake import FakeSpeechProvider
from llama.tts.provider import SpeechError, SpeechProvider


def speech_provider_for(config: Config, voice: str | None) -> SpeechProvider:
    """Construct the speech backend for a run's resolved voice.

    Mirrors llm.provider_for: maps config.tts.backend to a class. No tiers,
    no ladder — one provider, one voice, one model per run.
    """
    backend = config.tts.backend
    if backend == "fake":
        return FakeSpeechProvider()
    if backend == "elevenlabs":
        if not voice:
            raise SpeechError("no TTS voice configured: "
                              "set [tts] voice or give the profile a voice")
        return ElevenLabsProvider(voice=voice, model=config.tts.model,
                                  api_key=config.tts.api_key)
    raise SpeechError(f"unknown TTS backend {backend!r}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_tts.py -q`
Expected: 11 passed

- [ ] **Step 6: Commit**

```bash
git add src/llama/tts tests/test_tts.py tests/conftest.py
git commit -m "feat: add speech-provider layer (protocol, ElevenLabs, fake, factory)"
```

---

### Task 3: `Profile.voice`, `Criteria.voice`, `Provenance.voice`

**Files:**
- Modify: `src/llama/profiles.py`, `src/llama/models.py`
- Test: `tests/test_profiles.py`, `tests/test_models.py`

**Interfaces:**
- Consumes: existing `Profile`, `Criteria`, `Provenance`.
- Produces: `Profile.voice: str | None = None`, `Criteria.voice: str | None = None`, `Provenance.voice: str | None = None` — exact field name `voice` in all three; unset profile voice is omitted from the profile TOML (`save_profile` already dumps `exclude_none=True`) and loads back as `None` (that IS "unset ⇒ inherit global").

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_profiles.py`:

```python
def test_profile_voice_roundtrip_and_unset_omitted(tmp_path: Path):
    crit = Criteria(query="q")
    save_profile(tmp_path, Profile(name="voiced", criteria=crit, voice="v-abc"))
    assert load_profile(tmp_path, "voiced").voice == "v-abc"
    path = save_profile(tmp_path, Profile(name="plain", criteria=crit))
    assert "voice" not in path.read_text()  # TOML has no null: unset is omitted
    assert load_profile(tmp_path, "plain").voice is None
```

Append to `tests/test_models.py`:

```python
def test_criteria_and_provenance_voice_default_none():
    from llama.models import Candidate, Criteria, Provenance, RecordingSummary

    assert Criteria(query="q").voice is None
    prov = Provenance(
        performance_id="GratefulDead/1973-06-10", run="r",
        candidate=Candidate(performance_id="GratefulDead/1973-06-10",
                            collection="GratefulDead", date="1973-06-10",
                            recordings=[RecordingSummary(identifier="i")]),
        processed_at="2026-07-22T00:00:00+00:00",
    )
    assert prov.voice is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_profiles.py tests/test_models.py -q`
Expected: FAIL — `Profile` has no field `voice` (validation error on the voiced profile); `Criteria(...).voice` raises `AttributeError`

- [ ] **Step 3: Write the implementation**

`src/llama/profiles.py` — add to `Profile` beside `script`:

```python
    # Explicit ElevenLabs voice_id: voices this profile's runs with it even
    # when the global [tts] enabled flag is false. None = inherit global.
    voice: str | None = None
```

`src/llama/models.py` — add to `Criteria` after `script`:

```python
    # Resolved TTS voice id for this run (None = no voice); stamped like
    # `script` so replays behave the same regardless of later config edits.
    voice: str | None = None
```

Add to `Provenance` beside `script`:

```python
    voice: str | None = None  # voice id this show was processed with (None = no voice)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_profiles.py tests/test_models.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/llama/profiles.py src/llama/models.py tests/test_profiles.py tests/test_models.py
git commit -m "feat: add voice field to Profile, Criteria, Provenance"
```

---

### Task 4: Manifest schema — `DJAudio`, `Manifest.dj_audio`, `SetBreak.audio`

**Files:**
- Modify: `src/llama/models.py`, `src/llama/manifest.py`
- Test: `tests/test_manifest.py`

**Interfaces:**
- Consumes: existing `Manifest`, `SetBreak`, `build_manifest`.
- Produces: `llama.models.DJAudio(BaseModel)` with fields `intro: str`, `set_intros: dict[str, str]`, `set_breaks: list[str]` (default empty), `outro: str`; `Manifest.dj_audio: DJAudio | None = None`; `SetBreak.audio: str | None = None`; `build_manifest(..., dj_audio: DJAudio | None = None)` fills both `Manifest.dj_audio` and each `SetBreak.audio` (break *i* gets `dj_audio.set_breaks[i]`). Task 5 constructs the `DJAudio` and passes it here.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_manifest.py` (reuses the file's `make_show`/`make_notes`/`make_packaged` helpers — the show has `set_breaks=[1, 2]` and the notes two break notes):

```python
def test_build_manifest_with_dj_audio():
    from llama.models import DJAudio

    dj_audio = DJAudio(
        intro="dj-audio/00-intro.mp3",
        set_intros={"1": "dj-audio/set1-intro.mp3", "2": "dj-audio/set2-intro.mp3",
                    "encore": "dj-audio/setencore-intro.mp3"},
        set_breaks=["dj-audio/break1.mp3", "dj-audio/break2.mp3"],
        outro="dj-audio/99-outro.mp3",
    )
    m = build_manifest(make_show(), make_notes(), make_packaged(), dj_audio=dj_audio)
    assert m.dj_audio == dj_audio
    assert [b.audio for b in m.set_breaks] == ["dj-audio/break1.mp3", "dj-audio/break2.mp3"]
    assert [b.note_index for b in m.set_breaks] == [0, 1]  # note wiring unchanged


def test_build_manifest_without_dj_audio():
    m = build_manifest(make_show(), make_notes(), make_packaged())
    assert m.dj_audio is None
    assert all(b.audio is None for b in m.set_breaks)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_manifest.py -q`
Expected: FAIL — `ImportError: cannot import name 'DJAudio'`

- [ ] **Step 3: Write the implementation**

`src/llama/models.py` — add above `Manifest` (near `SetBreak`):

```python
class DJAudio(BaseModel):
    """Per-segment spoken DJ clips, as package-relative paths (dj-audio/...)."""
    intro: str
    set_intros: dict[str, str]  # keyed by set: "1", "2", "encore"
    set_breaks: list[str] = Field(default_factory=list)
    outro: str
```

Extend `SetBreak`:

```python
class SetBreak(BaseModel):
    after_track: int
    note_index: int | None = None  # index into dj_notes.set_break_notes when a script exists
    audio: str | None = None  # dj-audio clip for this break slot, when voiced
```

Extend `Manifest` (after `dj_notes`):

```python
    dj_audio: DJAudio | None = None  # present only when voice audio was generated
```

`src/llama/manifest.py` — new signature and break wiring:

```python
from collections import defaultdict

from llama.models import DJAudio, DJNotes, Manifest, ManifestTrack, SetBreak, Show


def build_manifest(
    show: Show,
    notes: DJNotes | None,
    packaged: list[ManifestTrack],
    context: str = "",
    research: str | None = None,
    reviews: str | None = None,
    research_vetted: bool = False,
    dj_audio: DJAudio | None = None,
) -> Manifest:
    per_set: dict[str, float] = defaultdict(float)
    for t in packaged:
        per_set[t.set] += t.duration_sec or 0.0
    breaks = [
        SetBreak(
            after_track=idx,
            note_index=i if notes is not None else None,
            audio=(dj_audio.set_breaks[i]
                   if dj_audio is not None and i < len(dj_audio.set_breaks) else None),
        )
        for i, idx in enumerate(show.set_breaks)
    ]
    return Manifest(
        show={"artist": show.artist, "date": show.date, "venue": show.venue,
              "city": show.city, "context": context},
        source={"performance_id": show.performance_id, "identifier": show.identifier,
                "url": show.source_url, "lineage": show.lineage},
        tracks=packaged,
        set_breaks=breaks,
        dj_notes=notes,
        dj_audio=dj_audio,
        research=research,
        reviews=reviews,
        research_vetted=research_vetted,
        total_duration_sec=sum(t.duration_sec or 0.0 for t in packaged),
        set_durations_sec=dict(per_set),
    )
```

(`m3u_text` unchanged.)

- [ ] **Step 4: Update existing full-dict set_breaks assertions**

`SetBreak` now dumps an `audio` key, so four existing exact-equality assertions gain `"audio": None`:

`tests/test_pipeline.py:113` and `tests/test_pipeline.py:231` (both currently identical) become:

```python
    assert manifest["set_breaks"] == [{"after_track": 3, "note_index": 0, "audio": None},
                                      {"after_track": 5, "note_index": 1, "audio": None}]
```

`tests/test_stage_package.py:66` becomes:

```python
    assert m["set_breaks"] == [{"after_track": 1, "note_index": 0, "audio": None}]
```

`tests/test_stage_package.py:128` becomes:

```python
    assert m["set_breaks"] == [{"after_track": 1, "note_index": None, "audio": None}]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_manifest.py tests/test_models.py tests/test_pipeline.py tests/test_stage_package.py -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/llama/models.py src/llama/manifest.py tests/test_manifest.py tests/test_pipeline.py tests/test_stage_package.py
git commit -m "feat: add dj_audio manifest block and per-break audio paths"
```

---

### Task 5: Package-stage synthesis, segment cache, manifest-last ordering

**Files:**
- Modify: `src/llama/stages/package.py`
- Test: `tests/test_stage_package.py`

**Interfaces:**
- Consumes: `DJAudio`, `build_manifest(..., dj_audio=...)` (Task 4); `SpeechError`, `FakeSpeechProvider`, `SILENT_MP3` (Task 2); providers expose `.voice`/`.model` for cache keys.
- Produces: `run_package(show_ws, ia, show, notes=None, force=False, speech=None) -> Path` — `speech: SpeechProvider | None` is the new keyword Task 6 forwards. Segment files under `package/dj-audio/`: `00-intro.mp3`, `set<key>-intro.mp3` per `set_intros` key, `break<i+1>.mp3` per break note, `99-outro.mp3`. Sidecar cache map `package/dj-audio/segments.json` (filename → sha256 of text+voice+model). Manifest is the last package artifact written.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_stage_package.py` (reuses the file's `StubIA`, `setup`, `make_notes` — the show has `set_breaks=[1]`, notes have `set_intros={"1","2"}` and one break note, so **5 segments**):

```python
import pytest

from llama.tts.fake import SILENT_MP3, FakeSpeechProvider
from llama.tts.provider import SpeechError


def test_package_synthesizes_dj_audio_and_manifest_block(tmp_path: Path):
    sws, show = setup(tmp_path)
    speech = FakeSpeechProvider()
    notes = make_notes()
    pkg = run_package(sws, StubIA(), show, notes, speech=speech)
    dj = pkg / "dj-audio"
    for name in ["00-intro.mp3", "set1-intro.mp3", "set2-intro.mp3",
                 "break1.mp3", "99-outro.mp3"]:
        assert (dj / name).read_bytes() == SILENT_MP3
    assert speech.calls == [notes.intro, notes.set_intros["1"], notes.set_intros["2"],
                            notes.set_break_notes[0], notes.outro]
    m = json.loads((pkg / "manifest.json").read_text())
    assert m["dj_audio"] == {
        "intro": "dj-audio/00-intro.mp3",
        "set_intros": {"1": "dj-audio/set1-intro.mp3", "2": "dj-audio/set2-intro.mp3"},
        "set_breaks": ["dj-audio/break1.mp3"],
        "outro": "dj-audio/99-outro.mp3",
    }
    assert m["set_breaks"] == [{"after_track": 1, "note_index": 0,
                                "audio": "dj-audio/break1.mp3"}]


def test_package_segment_cache_skips_unchanged(tmp_path: Path):
    sws, show = setup(tmp_path)
    run_package(sws, StubIA(), show, make_notes(), speech=FakeSpeechProvider())
    (sws.package_dir / "manifest.json").unlink()  # what redo --from package does
    second = FakeSpeechProvider()
    run_package(sws, StubIA(), show, make_notes(), speech=second)
    assert second.calls == []  # no re-spend on unchanged text


def test_package_changed_text_resynthesizes_only_that_segment(tmp_path: Path):
    sws, show = setup(tmp_path)
    run_package(sws, StubIA(), show, make_notes(), speech=FakeSpeechProvider())
    (sws.package_dir / "manifest.json").unlink()
    notes = make_notes().model_copy(update={"intro": "a different intro"})
    second = FakeSpeechProvider()
    run_package(sws, StubIA(), show, notes, speech=second)
    assert second.calls == ["a different intro"]


def test_package_different_voice_resynthesizes(tmp_path: Path):
    sws, show = setup(tmp_path)
    run_package(sws, StubIA(), show, make_notes(), speech=FakeSpeechProvider())
    (sws.package_dir / "manifest.json").unlink()
    second = FakeSpeechProvider()
    second.voice = "other-voice"  # cache key includes the voice
    run_package(sws, StubIA(), show, make_notes(), speech=second)
    assert len(second.calls) == 5


def test_package_force_rerenders_all_segments(tmp_path: Path):
    sws, show = setup(tmp_path)
    run_package(sws, StubIA(), show, make_notes(), speech=FakeSpeechProvider())
    second = FakeSpeechProvider()
    run_package(sws, StubIA(), show, make_notes(), force=True, speech=second)
    assert len(second.calls) == 5


def test_package_speech_failure_leaves_no_manifest(tmp_path: Path):
    sws, show = setup(tmp_path)
    with pytest.raises(SpeechError):
        run_package(sws, StubIA(), show, make_notes(),
                    speech=FakeSpeechProvider(fail=True))
    assert not (sws.package_dir / "manifest.json").exists()


def test_package_voice_without_notes_raises(tmp_path: Path):
    sws, show = setup(tmp_path)
    with pytest.raises(SpeechError):
        run_package(sws, StubIA(), show, notes=None, speech=FakeSpeechProvider())
    assert not (sws.package_dir / "manifest.json").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stage_package.py -q`
Expected: new tests FAIL — `run_package() got an unexpected keyword argument 'speech'`; existing tests still pass.

- [ ] **Step 3: Write the implementation**

`src/llama/stages/package.py` — new imports at top:

```python
import hashlib
import json
from pathlib import Path

from llama.audio import packaged_filename, read_duration, tag_audio
from llama.manifest import build_manifest, m3u_text
from llama.models import DJAudio, DJNotes, ManifestTrack, Show, VettingResult
from llama.status import detail
from llama.tts.provider import SpeechError
from llama.util import reviews_digest
from llama.workspace import ShowWorkspace, read_json, read_model, write_artifact
```

Add the two helpers above `run_package`:

```python
def _segment_texts(notes: DJNotes) -> list[tuple[str, str]]:
    """(segment file stem, text) in broadcast order."""
    segs = [("00-intro", notes.intro)]
    segs += [(f"set{key}-intro", text) for key, text in notes.set_intros.items()]
    segs += [(f"break{i + 1}", text) for i, text in enumerate(notes.set_break_notes)]
    segs.append(("99-outro", notes.outro))
    return segs


def _synthesize_dj_audio(pkg: Path, notes: DJNotes, speech, force: bool) -> DJAudio:
    """One MP3 per DJNotes segment under package/dj-audio/.

    Segments are keyed by sha256(text + voice + model) in a sidecar map
    (segments.json) written with the audio; matching keys are skipped so a
    repackage never re-spends on unchanged text. force re-renders everything.
    Any provider failure propagates (SpeechError): the manifest is written
    only after this returns, so a failed run leaves no manifest referencing
    half-rendered audio.
    """
    audio_dir = pkg / "dj-audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    sidecar = audio_dir / "segments.json"
    cached: dict[str, str] = json.loads(sidecar.read_text()) if sidecar.exists() else {}
    keys: dict[str, str] = {}
    for stem, text in _segment_texts(notes):
        filename = f"{stem}.mp3"
        dest = audio_dir / filename
        key = hashlib.sha256(f"{text}\n{speech.voice}\n{speech.model}".encode()).hexdigest()
        keys[filename] = key
        if force or not dest.exists() or cached.get(filename) != key:
            detail(f"synthesizing {filename}")
            data = speech.synthesize(text)
            tmp = dest.with_name(dest.name + ".part")
            tmp.write_bytes(data)
            tmp.replace(dest)
    write_artifact(sidecar, json.dumps(keys, indent=2))
    return DJAudio(
        intro="dj-audio/00-intro.mp3",
        set_intros={key: f"dj-audio/set{key}-intro.mp3" for key in notes.set_intros},
        set_breaks=[f"dj-audio/break{i + 1}.mp3"
                    for i in range(len(notes.set_break_notes))],
        outro="dj-audio/99-outro.mp3",
    )
```

Change `run_package`'s signature and its tail. Signature:

```python
def run_package(show_ws: ShowWorkspace, ia, show: Show, notes: DJNotes | None = None,
                force: bool = False, speech=None) -> Path:
```

Replace everything from the current `write_artifact(manifest_path, ...)` line through the `dj-notes.md` copy (keeping the track loop, context/vetting, research/reviews writes above it unchanged) with — note the manifest write moves **last** so a mid-synthesis failure leaves no manifest:

```python
    dj_audio = None
    if speech is not None:
        if notes is None:
            raise SpeechError("voice is active but this show has no DJ script; "
                              "rerun with the script enabled")
        dj_audio = _synthesize_dj_audio(pkg, notes, speech, force)

    write_artifact(pkg / "playlist.m3u", m3u_text([t.filename for t in packaged]))
    if show_ws.dj_notes_md.exists():
        write_artifact(pkg / "dj-notes.md", show_ws.dj_notes_md.read_text())
    # Manifest last: it is the package's "outputs written only on success" marker.
    write_artifact(manifest_path, build_manifest(
        show, notes, packaged, context=context,
        research=research_name, reviews="reviews.md", research_vetted=vetted,
        dj_audio=dj_audio))
    if flags:
        current = read_model(show_ws.show, Show)
        current.review_flags = current.review_flags + flags
        current.needs_review = True
        write_artifact(show_ws.show, current)
    return pkg
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_stage_package.py tests/test_pipeline.py -q`
Expected: all pass (existing packaging and pipeline tests are unaffected: `speech` defaults to `None`).

- [ ] **Step 5: Commit**

```bash
git add src/llama/stages/package.py tests/test_stage_package.py
git commit -m "feat: synthesize per-segment DJ audio in package with hash-keyed cache"
```

---

### Task 6: `process_show` gains `voice`/`speech`; stamps provenance; forwards to package

**Files:**
- Modify: `src/llama/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `run_package(..., speech=...)` (Task 5); `Provenance.voice` (Task 3).
- Produces: `process_show(..., script: bool = False, voice: str | None = None, speech=None, ...)` — the two new keyword params Task 7's call sites use. `voice` is stamped into `Provenance` beside `script`; `speech` is forwarded to `run_package`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pipeline.py` (reuses the file's `FIXTURE`, `IDENT`, `NOTES`, `VET`, `FakeIA`, and `FakeProvider`):

```python
def test_process_show_stamps_voice_and_forwards_speech(tmp_path: Path):
    from llama.ledger import Ledger
    from llama.models import (Candidate, Provenance, QualityAssessment,
                              RecordingSummary, ShortlistEntry)
    from llama.pipeline import process_show
    from llama.tts.fake import FakeSpeechProvider
    from llama.workspace import RunWorkspace, read_model

    fixture = json.loads(FIXTURE.read_text())
    cand = Candidate(
        performance_id="GratefulDead/1973-06-10", collection="GratefulDead",
        date="1973-06-10", venue="RFK Stadium", city="Washington, DC",
        recordings=[RecordingSummary(identifier=IDENT, avg_rating=4.8, num_reviews=40,
                                     description=fixture["metadata"]["description"])],
    )
    entry = ShortlistEntry(
        rank=1, candidate=cand,
        assessment=QualityAssessment(performance_id=cand.performance_id,
                                     quality_score=9.5, rationale="monumental"))
    providers = {
        "extract_setlist": FakeProvider(),
        "align_structure": FakeProvider(),
        "deep_research": FakeProvider(researches=["## Reputation\nLegendary.\n"]),
        "vet_research": FakeProvider(completes=[VET]),
        "synthesize": FakeProvider(completes=[NOTES]),
    }
    speech = FakeSpeechProvider()
    ws = RunWorkspace(tmp_path, "voicerun")
    pkg = process_show(ws, FakeIA(), Ledger(tmp_path / "ledger.jsonl"), entry,
                       providers, "voicerun", script=True, voice="v-abc",
                       speech=speech, jerrybase_enabled=False)
    assert pkg is not None
    prov = read_model(tmp_path / "shows" / "gratefuldead-1973-06-10" / "provenance.json",
                      Provenance)
    assert prov.voice == "v-abc"
    assert prov.script is True
    assert len(speech.calls) > 0                      # speech reached run_package
    assert (pkg / "dj-audio" / "00-intro.mp3").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pipeline.py::test_process_show_stamps_voice_and_forwards_speech -q`
Expected: FAIL — `process_show() got an unexpected keyword argument 'voice'`

- [ ] **Step 3: Write the implementation**

In `src/llama/pipeline.py`, extend `process_show`'s signature (after `script`):

```python
    script: bool = False,
    voice: str | None = None,
    speech=None,
```

Stamp the provenance (the existing `write_artifact(show_ws.provenance, Provenance(...))` call gains one kwarg):

```python
        script=script, voice=voice,
        processed_at=datetime.now(timezone.utc).isoformat(),
```

Forward speech at the package step:

```python
    with step(f"[{pid}] packaging"):
        pkg = run_package(show_ws, ia, show, notes, force=force, speech=speech)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pipeline.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/llama/pipeline.py tests/test_pipeline.py
git commit -m "feat: thread voice/speech through process_show and provenance"
```

---

### Task 7: CLI threading — resolution, stamping, flags, provider construction, except tuple

**Files:**
- Modify: `src/llama/cli.py`
- Test: `tests/test_cli_voice.py` (new)

**Interfaces:**
- Consumes: `speech_provider_for`, `SpeechError` (Task 2); `Criteria.voice`, `Profile.voice`, `Provenance.voice` (Task 3); `process_show(voice=..., speech=...)` (Task 6).
- Produces:
  - `cli._resolve_voice(config: Config, want: bool | None, profile_voice: str | None = None) -> str | None` — the run's resolved voice id (`None` = no voice). `want=False` always wins; explicit `profile_voice` opts in even when `[tts] enabled` is false; otherwise `want=True` or the global flag activates `config.tts.voice`; **active with no voice id raises `SpeechError`**.
  - `cli._replay_voice(config: Config, stamped: str | None, override: bool | None) -> str | None` — replay idiom: defer to the stamped value when the flag is unset.
  - `--voice/--no-voice` tri-state on `find`, `run`, `review`, `redo`; `--voice VOICE_ID` (string) on `profile add`.
  - `_execute(..., voice: str | None = None)` constructs the provider once via `speech_provider_for(config, voice)`; per-show except tuple becomes `(TaskFailed, LLMError, IAError, SpeechError)`.
  - Voice implies script at every resolution site (`script or voice_id is not None`).

- [ ] **Step 1: Write the failing tests**

`tests/test_cli_voice.py`:

```python
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import llama.cli as cli
from llama.config import Config
from llama.llm.fake import FakeProvider
from llama.tts.provider import SpeechError

runner = CliRunner()

CRITERIA = json.dumps({
    "query": "x", "collection": "GratefulDead", "artist": "Grateful Dead",
    "date_from": "1973-01-01", "date_to": "1973-12-31",
    "setlist_constraints": [], "soft_preferences": None,
    "min_avg_rating": 3.5, "min_reviews": 2, "count": 1,
})


def test_resolve_voice_matrix():
    on = Config.model_validate({"tts": {"enabled": True, "voice": "v-global"}})
    off = Config.model_validate({"tts": {"voice": "v-global"}})
    # global flag decides when nothing explicit
    assert cli._resolve_voice(on, None) == "v-global"
    assert cli._resolve_voice(off, None) is None
    # explicit opt-in / opt-out
    assert cli._resolve_voice(off, True) == "v-global"
    assert cli._resolve_voice(on, False) is None
    # explicit profile voice wins — even when globally disabled
    assert cli._resolve_voice(off, None, "v-profile") == "v-profile"
    assert cli._resolve_voice(on, None, "v-profile") == "v-profile"


def test_resolve_voice_active_without_voice_id_raises():
    with pytest.raises(SpeechError):
        cli._resolve_voice(Config.model_validate({"tts": {"enabled": True}}), None)
    with pytest.raises(SpeechError):
        cli._resolve_voice(Config(), True)


def test_replay_voice_defers_to_stamp():
    cfg = Config.model_validate({"tts": {"voice": "v-global"}})
    assert cli._replay_voice(cfg, "v-stamped", None) == "v-stamped"
    assert cli._replay_voice(cfg, "v-stamped", False) is None
    assert cli._replay_voice(cfg, "v-stamped", True) == "v-stamped"
    assert cli._replay_voice(cfg, None, True) == "v-global"  # re-voice from config
    assert cli._replay_voice(cfg, None, None) is None


def test_find_voice_stamps_criteria_and_forces_script(tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(
        f'root = "{tmp_path}"\n[tts]\nbackend = "fake"\nvoice = "v-abc"\n')
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[CRITERIA])})
    seen = {}
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: seen.update(k))
    result = runner.invoke(cli.app, [
        "find", "GD 1973", "--voice", "--no-script", "--run-name", "vstamp",
        "--config", str(tmp_path / "config.toml"),
    ])
    assert result.exit_code == 0, result.output
    saved = json.loads((tmp_path / "runs" / "vstamp" / "criteria.json").read_text())
    assert saved["voice"] == "v-abc"
    assert saved["script"] is True          # voice implies script, despite --no-script
    assert seen["voice"] == "v-abc" and seen["script"] is True


def test_find_no_voice_overrides_global_enable(tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(
        f'root = "{tmp_path}"\n[tts]\nbackend = "fake"\nenabled = true\nvoice = "v-abc"\n')
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[CRITERIA])})
    seen = {}
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: seen.update(k))
    result = runner.invoke(cli.app, [
        "find", "GD 1973", "--no-voice", "--run-name", "novoice",
        "--config", str(tmp_path / "config.toml"),
    ])
    assert result.exit_code == 0, result.output
    saved = json.loads((tmp_path / "runs" / "novoice" / "criteria.json").read_text())
    assert saved["voice"] is None
    assert seen["voice"] is None


def test_profile_add_voice(tmp_path: Path, monkeypatch):
    from llama.profiles import load_profile

    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[CRITERIA])})
    result = runner.invoke(cli.app, [
        "profile", "add", "gdhour", "GD 1973", "--voice", "v-abc",
        "--config", str(tmp_path / "config.toml"),
    ])
    assert result.exit_code == 0, result.output
    assert load_profile(tmp_path, "gdhour").voice == "v-abc"


def test_profile_run_explicit_voice_opts_in_when_globally_disabled(
        tmp_path: Path, monkeypatch):
    from llama.models import Criteria
    from llama.profiles import Profile, save_profile

    (tmp_path / "config.toml").write_text(
        f'root = "{tmp_path}"\n[tts]\nbackend = "fake"\n')  # enabled = false
    save_profile(tmp_path, Profile(name="voiced",
                                   criteria=Criteria.model_validate_json(CRITERIA),
                                   script=False, voice="v-profile"))
    seen = {}
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: seen.update(k))
    result = runner.invoke(cli.app, [
        "profile", "run", "voiced", "--config", str(tmp_path / "config.toml"),
    ])
    assert result.exit_code == 0, result.output
    run_dir = next((tmp_path / "runs").glob("*-voiced"))  # named <today>-voiced
    saved = json.loads((run_dir / "criteria.json").read_text())
    assert saved["voice"] == "v-profile"
    assert saved["script"] is True          # voice implies script (profile had script=False)
    assert seen["voice"] == "v-profile" and seen["script"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli_voice.py -q`
Expected: FAIL — `AttributeError: module 'llama.cli' has no attribute '_resolve_voice'`

- [ ] **Step 3: Write the implementation**

In `src/llama/cli.py`:

**Imports** (with the other `llama.*` imports):

```python
from llama.tts import speech_provider_for
from llama.tts.provider import SpeechError
```

**Helpers** (near `_parse_ranks`):

```python
def _resolve_voice(config: Config, want: bool | None,
                   profile_voice: str | None = None) -> str | None:
    """Resolve the run's voice id (None = voice off for this run).

    --no-voice (want=False) always wins. An explicit profile voice opts in
    even when [tts] enabled is false. Otherwise --voice (want=True) or the
    global flag activates the station default. Voice active with no voice id
    is an error, never a silent skip.
    """
    if want is False:
        return None
    if profile_voice:
        return profile_voice
    if want is True or config.tts.enabled:
        if not config.tts.voice:
            raise SpeechError("voice is active but no voice id is configured: "
                              "set [tts] voice or give the profile a voice")
        return config.tts.voice
    return None


def _replay_voice(config: Config, stamped: str | None,
                  override: bool | None) -> str | None:
    """Replay idiom: defer to the voice stamped at process time when unset."""
    if override is None:
        return stamped
    return _resolve_voice(config, override, stamped)
```

**`_execute`** — signature gains `voice: str | None = None` (after `script`); before the per-show loop:

```python
    speech = speech_provider_for(config, voice) if voice is not None else None
```

The `process_show` call gains `voice=voice, speech=speech`, and the except tuple becomes:

```python
        except (TaskFailed, LLMError, IAError, SpeechError) as exc:
```

**`find`** — add the tri-state option after `script`:

```python
    voice: bool = typer.Option(None, "--voice/--no-voice",
                               help="Per-segment spoken DJ audio (ElevenLabs); default "
                                    "follows [tts] enabled; --voice uses [tts] voice; "
                                    "voice implies --script"),
```

Resolve right after `config, ia, ledger = _setup(config_path)` (fail fast, before the interpret LLM call):

```python
    voice_id = _resolve_voice(config, voice)
    if voice_id is not None:
        script = True  # voice cannot work without the script
```

In the stamping block, add:

```python
    if voice_id is not None:
        updates["voice"] = voice_id
```

And pass it down: `_execute(..., script=script, voice=voice_id, full_rationale=full_rationale)`.

**`profile add`** — add the option after `script`:

```python
    voice: str = typer.Option(None, "--voice",
                              help="ElevenLabs voice_id; voices this profile even when "
                                   "[tts] enabled is false"),
```

and construct `Profile(..., script=script, voice=voice)`. (Existing profiles pick up a voice by adding `voice = "..."` to their TOML — there is deliberately no `profile edit` command.)

**`profile run`** — replace the stamping block:

```python
    voice_id = _resolve_voice(config, None, profile.voice)
    script = profile.script or voice_id is not None  # voice implies script
    # Stamp count/script/voice into the run's criteria: a later `llama run` on
    # this dir must behave like the profile, not like the interpreted defaults.
    criteria = profile.criteria.model_copy(update={"count": profile.count,
                                                   "script": script,
                                                   "voice": voice_id})
    write_artifact(ws.criteria, criteria)
    _execute(config, ia, ledger, ws, criteria, profile.count, auto,
             human_gate=profile.human_gate, script=script, voice=voice_id,
             full_rationale=full_rationale)
```

**`run`, `review`, `redo`** — each gains this tri-state option (beside their existing `--script/--no-script`):

```python
    voice: bool = typer.Option(None, "--voice/--no-voice",
                               help="Override the voice recorded at process time "
                                    "(--voice re-voices, --no-voice strips voice)"),
```

**`run`** — then before `_execute`:

```python
    effective_voice = _replay_voice(config, criteria.voice, voice)
    effective_script = criteria.script if script is None else script
    _execute(config, ia, ledger, ws, criteria, criteria.count, auto,
             human_gate=False, force=force and stage is None,
             script=effective_script or stage == "synthesize" or effective_voice is not None,
             voice=effective_voice,
             force_stage=stage if (force and stage not in (None, *RUN_LEVEL_STAGES)) else None,
             full_rationale=full_rationale)
```

**`review`** — in the process-now branch:

```python
        criteria = read_model(ws.criteria, Criteria)
        effective_voice = _replay_voice(config, criteria.voice, voice)
        effective_script = criteria.script if script is None else script
        _execute(config, ia, ledger, ws, criteria, criteria.count, auto=True,
                 human_gate=False,
                 script=effective_script or effective_voice is not None,
                 voice=effective_voice,
                 full_rationale=full_rationale)
```

**`redo`** — `redo` calls `process_show` directly (not `_execute`), so it constructs the provider itself:

```python
    effective_voice = _replay_voice(config, prov.voice, voice)
    effective_script = (prov.script if script is None else script) or effective_voice is not None
    speech = speech_provider_for(config, effective_voice) if effective_voice is not None else None
    pkg = process_show(ws, ia, ledger, shortlist_entry, make_providers(config),
                       prov.run, config.audio_format, script=effective_script,
                       voice=effective_voice, speech=speech,
                       setlistfm=make_client(config), structure_cfg=config.structure,
                       jerrybase_enabled=config.jerrybase.enabled,
                       selection_cfg=config.selection)
```

(`redo --from package` therefore re-voices with the show's original voice by default; a `SpeechError` outside the `_execute` loop is a `LlamaError`, so `main_cli` prints a clean `error:` line.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli_voice.py tests/test_pipeline.py tests/test_cli_commands.py -q`
Expected: all pass (voiceless runs stamp `voice: null` / omit it and behave exactly as before).

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/llama/cli.py tests/test_cli_voice.py
git commit -m "feat: thread voice through find/profile/replay CLI with tri-state flags"
```

---

### Task 8: Voiced-pipeline integration tests (fake speech backend)

**Files:**
- Test: `tests/test_voice_pipeline.py` (new)

**Interfaces:**
- Consumes: everything from Tasks 1–7. No production code changes — this task proves the assembled feature end-to-end and pins the enable-semantics matrix at the CLI level. If a test exposes a wiring bug, fix it in the task that owns that file.

- [ ] **Step 1: Write the tests**

`tests/test_voice_pipeline.py` (the `FakeIA`/provider scaffolding is copied from `tests/test_pipeline.py` so this file stands alone):

```python
import json
from pathlib import Path

from typer.testing import CliRunner

import llama.cli as cli
from llama.llm.fake import FakeProvider
from llama.tts.fake import SILENT_MP3, FakeSpeechProvider

runner = CliRunner()
FIXTURE = Path(__file__).parent / "fixtures" / "gd73_metadata.json"
IDENT = "gd73-06-10.sbd.hollister.174.sbeok.shnf"
SHOW_DIR = "gratefuldead-1973-06-10"

# jerrybase off: same isolation rationale as tests/test_pipeline.py (the
# synthesized candidate's venue differs from the dataset's).
VOICED_CFG = ('{root}\n[jerrybase]\nenabled = false\n'
              '[tts]\nbackend = "fake"\nenabled = true\nvoice = "v-abc"\n')
UNVOICED_CFG = ('{root}\n[jerrybase]\nenabled = false\n'
                '[tts]\nbackend = "fake"\nvoice = "v-abc"\n')  # enabled = false

CRITERIA = json.dumps({
    "query": "x", "collection": "GratefulDead", "artist": "Grateful Dead",
    "date_from": "1973-01-01", "date_to": "1973-12-31",
    "setlist_constraints": [], "soft_preferences": None,
    "min_avg_rating": 3.5, "min_reviews": 2, "count": 1,
})

ASSESSMENTS = json.dumps({"assessments": [{
    "performance_id": "GratefulDead/1973-06-10", "quality_score": 9.5,
    "non_attendee_evidence": "couchtaper praises the tape",
    "recording_complaints": [], "rationale": "monumental Dark Star",
}]})

NOTES = json.dumps({
    "context": "Peak 1973",
    "intro": "Tonight, the Grateful Dead at RFK Stadium.",
    "set_intros": {"1": "Morning Dew opens.", "2": "A monumental Dark Star.",
                   "encore": "Johnny B. Goode."},
    "set_break_notes": ["End of set one.", "End of set two."],
    "outro": "From the hollister soundboard.",
    "mentioned_songs": ["Morning Dew", "Dark Star", "Johnny B. Goode"],
})

VET = json.dumps({
    "asserted_songs": ["Morning Dew", "Dark Star"],
    "asserted_dates": ["1973-06-10"],
    "context": "Peak 1973, RFK Stadium",
})


class FakeIA:
    def __init__(self, *args, **kwargs):
        self.fixture = json.loads(FIXTURE.read_text())

    def scrape(self, query, fields, count=10000):
        return [{"identifier": IDENT, "date": "1973-06-10T00:00:00Z",
                 "venue": "RFK Stadium", "coverage": "Washington, DC",
                 "avg_rating": 4.8, "num_reviews": 40,
                 "description": self.fixture["metadata"]["description"]}]

    def metadata(self, identifier):
        return self.fixture

    def download_file(self, identifier, filename, dest, md5=None):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"\x00" * 64)
        return dest


def fake_providers(config):
    return {
        "interpret": FakeProvider(completes=[CRITERIA]),
        "score_reviews": FakeProvider(completes=[ASSESSMENTS]),
        "light_research": FakeProvider(researches=["Widely ranked top-5 1973 (example.org)"]),
        "extract_setlist": FakeProvider(),
        "deep_research": FakeProvider(researches=[
            "## Reputation\nLegendary RFK show.\n## Performance highlights\nDark Star.\n"
            "## Context\nPeak 73 tour.\n## Recording notes\nHollister SBD."]),
        "synthesize": FakeProvider(completes=[NOTES]),
        "align_structure": FakeProvider(),
        "vet_research": FakeProvider(completes=[VET]),
    }


def voiced_setup(tmp_path, monkeypatch, cfg_template=VOICED_CFG):
    (tmp_path / "config.toml").write_text(
        cfg_template.format(root=f'root = "{tmp_path}"'))
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    return str(tmp_path / "config.toml")


def find(cfg, *extra):
    return runner.invoke(cli.app, ["find", "GD 1973", "--auto",
                                   "--run-name", "voicerun", "--config", cfg, *extra])


def test_voiced_find_end_to_end(tmp_path: Path, monkeypatch):
    cfg = voiced_setup(tmp_path, monkeypatch)
    result = find(cfg)
    assert result.exit_code == 0, result.output
    pkg = tmp_path / "shows" / SHOW_DIR / "package"
    dj = pkg / "dj-audio"
    for name in ["00-intro.mp3", "set1-intro.mp3", "set2-intro.mp3",
                 "setencore-intro.mp3", "break1.mp3", "break2.mp3", "99-outro.mp3"]:
        assert (dj / name).read_bytes() == SILENT_MP3
    manifest = json.loads((pkg / "manifest.json").read_text())
    assert manifest["dj_audio"] == {
        "intro": "dj-audio/00-intro.mp3",
        "set_intros": {"1": "dj-audio/set1-intro.mp3", "2": "dj-audio/set2-intro.mp3",
                       "encore": "dj-audio/setencore-intro.mp3"},
        "set_breaks": ["dj-audio/break1.mp3", "dj-audio/break2.mp3"],
        "outro": "dj-audio/99-outro.mp3",
    }
    assert manifest["set_breaks"] == [
        {"after_track": 3, "note_index": 0, "audio": "dj-audio/break1.mp3"},
        {"after_track": 5, "note_index": 1, "audio": "dj-audio/break2.mp3"}]
    assert manifest["dj_notes"] is not None
    # run intent + provenance are stamped for replays
    criteria = json.loads((tmp_path / "runs" / "voicerun" / "criteria.json").read_text())
    assert criteria["voice"] == "v-abc"
    prov = json.loads((tmp_path / "shows" / SHOW_DIR / "provenance.json").read_text())
    assert prov["voice"] == "v-abc"


def test_globally_disabled_run_is_unvoiced(tmp_path: Path, monkeypatch):
    cfg = voiced_setup(tmp_path, monkeypatch, cfg_template=UNVOICED_CFG)
    result = find(cfg)
    assert result.exit_code == 0, result.output
    pkg = tmp_path / "shows" / SHOW_DIR / "package"
    assert not (pkg / "dj-audio").exists()
    assert json.loads((pkg / "manifest.json").read_text())["dj_audio"] is None


def test_explicit_voice_flag_opts_in_when_globally_disabled(tmp_path: Path, monkeypatch):
    cfg = voiced_setup(tmp_path, monkeypatch, cfg_template=UNVOICED_CFG)
    result = find(cfg, "--voice")
    assert result.exit_code == 0, result.output
    assert (tmp_path / "shows" / SHOW_DIR / "package" / "dj-audio" / "00-intro.mp3").exists()


def test_no_voice_flag_opts_out_when_globally_enabled(tmp_path: Path, monkeypatch):
    cfg = voiced_setup(tmp_path, monkeypatch)
    result = find(cfg, "--no-voice")
    assert result.exit_code == 0, result.output
    pkg = tmp_path / "shows" / SHOW_DIR / "package"
    assert not (pkg / "dj-audio").exists()
    assert json.loads((pkg / "manifest.json").read_text())["dj_audio"] is None


def test_voice_implies_script_despite_no_script(tmp_path: Path, monkeypatch):
    cfg = voiced_setup(tmp_path, monkeypatch)
    result = find(cfg, "--no-script")
    assert result.exit_code == 0, result.output
    pkg = tmp_path / "shows" / SHOW_DIR / "package"
    manifest = json.loads((pkg / "manifest.json").read_text())
    assert manifest["dj_notes"] is not None       # script was forced on
    assert manifest["dj_audio"] is not None
    assert (pkg / "dj-notes.md").exists()


def test_speech_failure_fails_show_but_not_batch(tmp_path: Path, monkeypatch):
    cfg = voiced_setup(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "speech_provider_for",
                        lambda config, voice: FakeSpeechProvider(fail=True))
    result = find(cfg)
    assert result.exit_code == 0, result.output   # batch loop continues; run exits clean
    assert "FAILED GratefulDead/1973-06-10" in result.output
    show_dir = tmp_path / "shows" / SHOW_DIR
    assert not (show_dir / "package" / "manifest.json").exists()  # no half-voiced package
    assert not (tmp_path / "ledger.jsonl").exists()


def test_redo_from_package_reuses_cached_segments(tmp_path: Path, monkeypatch):
    cfg = voiced_setup(tmp_path, monkeypatch)
    assert find(cfg).exit_code == 0
    second = FakeSpeechProvider()  # same fixed fake voice/model -> same cache keys
    monkeypatch.setattr(cli, "speech_provider_for", lambda config, voice: second)
    redo = runner.invoke(cli.app, ["redo", "gratefuldead", "--from", "package",
                                   "--config", cfg])
    assert redo.exit_code == 0, redo.output
    assert "packaged" in redo.output              # re-voiced with the original voice
    assert second.calls == []                     # unchanged segments skipped, no re-spend
```

(`--force` re-rendering is pinned at the `run_package` level in Task 5's `test_package_force_rerenders_all_segments`; at the CLI it rides `llama run <run> --force`.)

- [ ] **Step 2: Run the tests**

Run: `pytest tests/test_voice_pipeline.py -q`
Expected: 7 passed. Any failure here is a wiring bug in Tasks 5–7 — fix it in the owning file, do not weaken the assertions.

- [ ] **Step 3: Run the full suite**

Run: `pytest -q`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_voice_pipeline.py
git commit -m "test: end-to-end voiced pipeline over the fake speech backend"
```

---

### Task 9: Opt-in live ElevenLabs test

**Files:**
- Test: `tests/test_live_smoke.py`

**Interfaces:**
- Consumes: `ElevenLabsProvider` (Task 2).
- Produces: one `@pytest.mark.live` test, deselected by default (`addopts = "-m 'not live'"`), keyed off `ELEVENLABS_API_KEY`. Not in CI.

- [ ] **Step 1: Write the test**

Append to `tests/test_live_smoke.py` (beside `SETLISTFM_KEY`, add the module-level key read — it must happen at import time because the autouse conftest fixture deletes the env var before each test):

```python
ELEVENLABS_KEY = os.environ.get("ELEVENLABS_API_KEY")  # read at import: see tests/conftest.py
```

and the test:

```python
@pytest.mark.live
@pytest.mark.skipif(not ELEVENLABS_KEY, reason="needs ELEVENLABS_API_KEY")
def test_elevenlabs_synthesize_real():
    from llama.tts.elevenlabs import ElevenLabsProvider

    p = ElevenLabsProvider(voice="21m00Tcm4TlvDq8ikWAM",  # "Rachel", a stock voice
                           model="eleven_multilingual_v2", api_key=ELEVENLABS_KEY)
    audio = p.synthesize("Tonight: the Grateful Dead, live at RFK Stadium.")
    assert len(audio) > 10_000                     # a real clip, not an error body
    assert audio[:3] == b"ID3" or audio[:1] == b"\xff"  # playable MP3 framing
```

- [ ] **Step 2: Verify it is deselected by default and collectable**

Run: `pytest tests/test_live_smoke.py -q`
Expected: the new test is deselected (0 selected from it). Then confirm collection: `pytest -m live --collect-only -q tests/test_live_smoke.py` lists `test_elevenlabs_synthesize_real`. (Actually hitting the API is a manual, keyed run: `ELEVENLABS_API_KEY=... pytest -m live tests/test_live_smoke.py::test_elevenlabs_synthesize_real -q` — costs money, not part of this task's gate.)

- [ ] **Step 3: Run the full suite**

Run: `pytest -q`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_live_smoke.py
git commit -m "test: opt-in live ElevenLabs synthesis smoke test"
```
