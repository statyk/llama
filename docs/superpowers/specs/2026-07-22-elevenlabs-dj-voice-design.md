# llama — ElevenLabs DJ Voice (TTS of the DJ Script)

**Date:** 2026-07-22
**Status:** Approved design, pending implementation plan

## Purpose

The automated in-house radio station wants spoken DJ patter, not just a script
for some other system to read. This feature adds optional text-to-speech
generation of the verbatim DJ script: when voice is active for a show, the
package gains a `dj-audio/` directory of per-segment MP3 clips (intro, per-set
intros, set-break notes, outro) that the automation slots directly into the
broadcast.

Launch backend is **ElevenLabs** only. Local options were A/B'd and lost:
Piper too robotic, XTTS too heavy (2.9 GB), Kokoro merely OK. A local/offline
backend (Kokoro) is deferred to future work; the provider layer is shaped so
it slots in later without pipeline changes.

## Decisions made during brainstorming

- **New capability, not an LLM task.** TTS is deliberately NOT folded into the
  existing `LLMProvider` protocol (`complete`/`research`,
  `src/llama/llm/provider.py`) — it is a parallel speech-provider abstraction
  with its own package, factory, and fake backend.
- **No tiers.** Unlike the LLM layer's `provider_ladder`, there is no
  tier/ladder/retry-escalation machinery for TTS. One provider, one voice, one
  model per run.
- **Folded into `package`, not a new stage.** TTS runs inside `run_package`
  after the text package is built. It consumes the structured `DJNotes` and
  synthesizes per segment.
- **Opt-in, with per-profile voices.** Global `[tts] enabled` defaults to
  false. A profile that explicitly names a `voice` is voiced with that voice
  even when the global flag is off.
- **Hard-fail, scoped to the show.** TTS costs real money and a half-voiced
  package is worse than none: any segment failure fails that show's package.
  Other shows in the same batch are unaffected.
- **Cache per segment.** Re-running `package` must not re-spend on ElevenLabs
  for unchanged text.

## Architecture

### Speech provider abstraction (`src/llama/tts/`)

New package mirroring the LLM layer's structure:

```python
@runtime_checkable
class SpeechProvider(Protocol):
    def synthesize(self, text: str) -> bytes: ...   # encoded MP3 audio bytes
```

- `SpeechError(LlamaError)` in the package for provider failures, parallel to
  `LLMError`.
- **`ElevenLabsProvider`** — HTTP call to the ElevenLabs TTS API. Constructed
  with the resolved `voice_id` and `model`; returns MP3 bytes. API key from
  the `ELEVENLABS_API_KEY` env var or `[tts] api_key` in config — env wins,
  matching `OPENROUTER_API_KEY` (`src/llama/llm/openrouter.py:21`) and
  `SETLISTFM_API_KEY` (`src/llama/setlistfm.py:128`). Missing key when voice
  is active raises `SpeechError`; never degrade silently.
- **`FakeSpeechProvider`** — test backend returning a small valid silent MP3
  (a bytes fixture), so the whole pipeline test suite stays offline and
  hermetic, exactly as `FakeProvider` (`src/llama/llm/fake.py`) does for the
  LLM layer. Records calls for assertions; can be armed to fail for the
  hard-fail tests.
- **`speech_provider_for(config, voice)`** — factory mirroring `provider_for`
  (`src/llama/llm/__init__.py`): maps `config.tts.backend` to a class
  (`elevenlabs`, `fake`), constructs it with the effective voice and
  `config.tts.model`, raises `SpeechError` on an unknown backend. Constructed
  providers expose `voice` and `model` attributes (the fake uses fixed
  placeholders) so the package stage can build cache keys.

Backends duck-type the protocol; adding Kokoro later is one new module plus a
factory entry.

### Config surface — new `[tts]` table

`TTSConfig(BaseModel)` registered as a `tts` field on `Config`
(`src/llama/config.py`, beside `structure`/`selection`/etc.):

```python
class TTSConfig(BaseModel):
    enabled: bool = False              # opt-in; nothing calls ElevenLabs unless true
    backend: str = "elevenlabs"        # or "fake" for tests
    voice: str | None = None           # station default ElevenLabs voice_id
    model: str = "eleven_multilingual_v2"  # quality default, overridable
    api_key: str | None = None         # ELEVENLABS_API_KEY env takes precedence
```

Add a commented `[tts]` block to `DEFAULT_CONFIG_TOML` in the same documented
style as the existing sections, so `llama config init` seeds it. Keep it
consistent with
`tests/test_config.py::test_default_config_template_matches_defaults`.

### Per-profile voice override

- `Profile` (`src/llama/profiles.py`) gains a top-level field beside `script`:
  `voice: str | None = None`. `save_profile` already dumps with
  `exclude_none=True`, so an unset voice is omitted from the profile TOML and
  loads back as `None` — that IS the "unset ⇒ inherit global" behavior.
- **Resolution rule:** `effective_voice = profile.voice or config.tts.voice`.
- **Enable semantics (precise):**
  - A profile that explicitly names a `voice` is voiced with that voice —
    explicit profile voice is opt-in for that profile, even when the global
    `[tts] enabled` is false.
  - Profiles that do NOT set a voice, and one-off `find` runs, follow the
    global `[tts] enabled` flag and use `config.tts.voice`.
- Voice active with no usable configuration (no resolvable voice id, or a
  missing API key) is a hard failure for that show, not a silent skip.

### Threading through the CLI and pipeline

`profile.voice` threads through exactly as `script` does:

- `Criteria` (`src/llama/models.py`) gains `voice: str | None = None` beside
  `script` — the run's resolved voice id (`None` = no voice), stamped so
  replays behave the same regardless of later config edits.
- `profile_run` (`src/llama/cli.py:681`) resolves the effective voice per the
  rules above, stamps it into the run `Criteria` via `model_copy(update=...)`
  alongside `count`/`script`, and passes it as a kwarg into `_execute`.
- `find` resolves against `config.tts` (subject to its flag, below), stamps,
  and passes the same way.
- `_execute` (`cli.py:122`) gains `voice: str | None = None`, constructs the
  speech provider once via `speech_provider_for(config, voice)` when voice is
  active, and passes both down to the `process_show` call site (`cli.py:184`).
- `process_show` (`src/llama/pipeline.py:44`) gains
  `voice: str | None = None` and `speech: SpeechProvider | None = None`,
  stamps `voice` into `Provenance` beside `script`, and passes `speech` into
  `run_package`.
- Replay paths (`run`, `review`, `redo`) honor the stored value via the
  existing replay-override idiom `x if override is None else override`
  (`cli.py:326,365,517`): a tri-state `--voice/--no-voice` override beside
  their existing `--script/--no-script`, deferring to the stamped
  `criteria.voice` / `prov.voice` when unset. `redo --from package` therefore
  re-voices with the show's original voice by default.
- **Voice implies script.** The pipeline gates `synthesize` on `script`
  (`pipeline.py:92-104`) and `run_package` receives the resulting `DJNotes`;
  voice cannot work without them. Wherever voice is resolved active, `script`
  is forced on for that run (`script or voice is not None`).

CLI surface:

- `llama profile add` gains `--voice VOICE_ID` (populated like the other
  optional fields at `cli.py:631-678`). Existing profiles pick up a voice by
  adding `voice = "..."` to their TOML — profiles are plain hand-editable
  files; there is no `profile edit` command to extend.
- `llama find` gains a tri-state `--voice/--no-voice` flag mirroring the
  existing `--script/--no-script` (`cli.py:208`): default follows
  `[tts] enabled`; `--voice` opts the run in (using `config.tts.voice`);
  `--no-voice` opts out even when globally enabled.

### Package integration — per-segment audio

Inside `run_package` (`src/llama/stages/package.py`), when a speech provider
was passed, per-segment audio is synthesized **before the manifest is
finalized**, so the segment→file mapping flows into a single `build_manifest`
call and the `dj_audio` block plus per-break `audio` paths land in the one
manifest write. The other text artifacts (m3u, `dj-notes.md`, research.md,
reviews.md) are built as today; the manifest is the last thing written, so a
mid-synthesis failure leaves no manifest at all (see Failure handling). When a
speech provider is present, synthesize one MP3 per `DJNotes` segment
(`src/llama/models.py:178-184`) into `package/dj-audio/`:

| Segment | File |
|---|---|
| `intro` | `00-intro.mp3` |
| `set_intros[key]` (keys `"1"`, `"2"`, `"encore"`, …) | `set<key>-intro.mp3` (e.g. `set1-intro.mp3`, `setencore-intro.mp3`) |
| `set_break_notes[i]` | `break<i+1>.mp3` (`break1.mp3`, …) |
| `outro` | `99-outro.mp3` |

The automation system slots each clip at its spot: intro before the show,
break clips between sets, outro after the encore.

### Caching / idempotency

Each segment's audio is keyed by a hash of (segment text + voice_id + model).
The keys live in a small sidecar map alongside the clips (filename → hash),
written with the audio. On `redo --from package`, segments whose key matches
are skipped — no re-spend on ElevenLabs; only missing or changed segments
re-synthesize. `--force` re-renders all segments. This matters because
`package` is deliberately re-runnable and TTS costs real money per character.

### Failure handling — hard-fail, scoped to the show

Any segment's TTS failure (API error, rate limit, missing key when voice is
active) raises `SpeechError` out of `run_package`. That rides the existing
exception path out of `process_show` (`src/llama/pipeline.py:44-117`): the
show yields no package, and package's "write outputs only on success" rule
means a failed run leaves no half-written `dj-audio/` referenced by a
manifest (the manifest with `dj_audio` is written only after all segments
succeed).

**Scoping:** the hard-fail is per show, never the batch. The per-show loop in
`_execute` (`cli.py:182-199`) already catches `(TaskFailed, LLMError,
IAError)` for each shortlist entry, echoes `FAILED <id>`, and `continue`s;
`SpeechError` joins that tuple. In a multi-show `--auto` run, one show's TTS
failure does not abort shows that already succeeded — the batch continues,
and the failed show simply produces nothing until retried via
`redo --from package` (where the segment cache makes the retry cheap).

### Manifest schema

`Manifest` (`src/llama/models.py:215`) gains a `dj_audio` block, present only
when voice audio was generated:

```json
"dj_audio": {
  "intro": "dj-audio/00-intro.mp3",
  "set_intros": {"1": "dj-audio/set1-intro.mp3", "encore": "dj-audio/setencore-intro.mp3"},
  "set_breaks": ["dj-audio/break1.mp3"],
  "outro": "dj-audio/99-outro.mp3"
}
```

Each `SetBreak` entry already carries a `note_index` into
`dj_notes.set_break_notes` (`models.py:210-212`, `manifest.py:24`); it gains
an `audio: str | None` path so the automation ties a break clip directly to
its slot. `build_manifest` (`src/llama/manifest.py`) takes the segment→file
mapping and fills both.

## Components / files touched

- **New:** `src/llama/tts/` — `provider.py` (`SpeechProvider`, `SpeechError`),
  `elevenlabs.py`, `fake.py`, `__init__.py` (`speech_provider_for`).
- `src/llama/config.py` — `TTSConfig`, `Config.tts`, `[tts]` block in
  `DEFAULT_CONFIG_TOML`.
- `src/llama/profiles.py` — `Profile.voice`.
- `src/llama/models.py` — `Criteria.voice`, `Provenance.voice`,
  `SetBreak.audio`, `Manifest.dj_audio` (+ its small model).
- `src/llama/cli.py` — `--voice` options on `find`/`profile add` and the
  replay commands; voice resolution + stamping; provider construction in
  `_execute`; `SpeechError` in the per-show except tuple.
- `src/llama/pipeline.py` — `process_show` gains `voice`/`speech`, stamps
  provenance, forwards to package.
- `src/llama/stages/package.py` — per-segment synthesis, cache, `dj-audio/`
  output.
- `src/llama/manifest.py` — `dj_audio` wiring, per-break `audio` paths.
- **Tests:** unit tests for the tts package (factory, key precedence,
  ElevenLabs request shape mocked), config/template sync, profile round-trip,
  pipeline tests over `FakeSpeechProvider`, one live test.

## Testing strategy

1. **Pipeline tests, fake speech backend:** `backend = "fake"` +
   `FakeSpeechProvider`'s silent-MP3 bytes let the full voiced path run
   offline — segment files written under `dj-audio/`, manifest `dj_audio` and
   per-break `audio` populated, voice-implies-script, and the enable-semantics
   matrix (profile voice with global off; global on without profile voice;
   `--no-voice`).
2. **Failure and idempotency:** a fake armed to raise proves the hard-fail
   (no package, no manifest `dj_audio`, batch continues past the failed
   show); a second `redo --from package` proves unchanged segments are
   skipped (fake records zero new calls) and `--force` re-renders.
3. **Live test (opt-in):** one `pytest -m live` test hits the real ElevenLabs
   API with a short line and asserts playable MP3 bytes, mirroring the
   existing live-test convention. Requires `ELEVENLABS_API_KEY`; not in CI.

## Out of scope / future work

- **Local/offline TTS backend (Kokoro):** deferred. The `SpeechProvider`
  protocol and factory are the seam; no design here.
- **Monolith full-read audio:** a single continuous narration file is not
  produced; segments only.
- **Voice cloning:** out of scope.
