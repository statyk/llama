# emcee: per-presenter TTS pinning + a local `mlx_audio` backend — design

**Date:** 2026-10-12
**Scope:** `packages/emcee` only (llama, herder, transmitter untouched).
**Review mode:** Opus.

## Stakes

Hosted Voxtral spend is the station's main operating bottleneck; this work
exists to move some presenters onto a free local model **without** any
presenter's voice changing underneath it. Nothing here is irreversible:
presenter TOMLs are written atomically and are small, re-creatable files, and
delivered packages are touched only by voicing them exactly as today.
**Strict surfaces:** (1) **never silently fall back to another backend** — a
presenter pinned to `mlx_audio` whose server is down must fail, not be voiced
by Voxtral (that would spend money *and* break voice consistency at once);
(2) a configuration-only failure (unreachable server, missing transcript)
must be detected **before** any LLM spend and **before** `_process_one`
clears a package's manifest blocks, so it can never take a broadcast-ready
package off air; (3) existing configs and presenter files keep working
unchanged — with no pins set, behaviour is byte-for-byte today's.

## Background and evidence

The `SpeechProvider` protocol (`tts/provider.py`) is `synthesize(text, fmt,
*, previous_text, next_text) -> bytes` plus `.voice`/`.model` strings that
feed the render-cache key (`audio.py:333`). Today one backend serves the whole
station: `speech_provider_for` (`tts/__init__.py`) reads `config.tts.backend`,
and `[tts] model`/`api_key` are that backend's settings.

A bake-off on 2026-10-12 (artifacts and scripts in `~/tts-bakeoff/`, not in
the repo) rendered the Set 2 lead-in of `gratefuldead-1972-05-11` in presenter
Phil's cloned voice through emcee's own `render_speech_mp3` (chunked, bedded,
loudness-normalized), on the station's M4 Mac mini (16 GB):

| model | RTF | WER (Whisper) | note |
|---|---|---|---|
| Voxtral (aired baseline) | — | 1.9% | |
| Qwen3-TTS 1.7B Base bf16 | 2.8 | 2.3% | best local; the operator judged it a downgrade worth taking |
| Qwen3-TTS 0.6B Base | 2.4 | 4.2% | |
| Chatterbox | 1.9 | 9.3% | a 4-word sentence became ~10 s of babble |
| F5-TTS (f5-tts-mlx) | 3.35 | 3.7% | pacing stretched ~75%; not servable by mlx-audio |
| Higgs Audio v3 4B | ~12 | 2.3% | swapped the host to ~15/16 GB |

All were driven over `mlx_audio.server`'s `POST /v1/audio/speech` (except F5)
with `ref_audio` (a **local file path** — the server reads it from disk) and
`ref_text` (a transcript of the reference clip). So the integration surface is
one HTTP dialect, and the model is a request field: the backend must not be
Qwen-specific.

## Design

### 1. Pinning

**Presenter TOML** (`presenters.py:Presenter`) gains three optional fields:

```toml
tts = "mlx_audio"               # backend pin; absent = [tts] backend
tts_model = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"  # model pin; absent = that backend's default
voice_clone_text = "It's the chemistry, basically. ..."    # transcript of voice_clone
```

Validation (model validator, at load and before every save):

- `tts`, when set, must name a known backend (`voxtral`, `elevenlabs`,
  `mlx_audio`, `fake`).
- `tts_model` without `tts` is an error (it would silently follow whatever
  `[tts] backend` is).
- `voice_clone` with `tts = "elevenlabs"` is an error (moved here from the
  factory; the factory keeps its own check for the house voice).
- `tts = "mlx_audio"` with `voice_clone` requires `voice_clone_text`.
  `voice_clone_text` is otherwise allowed and ignored (Voxtral needs none), so
  it can be added ahead of a pin.
- The exactly-one-of `voice`/`voice_clone` rule is unchanged.

**Config** (`config.py`): per-backend settings move into per-backend
subtables, because one `[tts] model`/`api_key` cannot serve a mixed station:

```toml
[tts]
backend = "voxtral"          # the house voice + every unpinned presenter

[tts.voxtral]                # model, api_key   (MISTRAL_API_KEY env wins)
[tts.elevenlabs]             # model, api_key   (ELEVENLABS_API_KEY env wins)
[tts.mlx_audio]
url = "http://127.0.0.1:8000"
model = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"
timeout_s = 600
```

- Each subtable is a strict model (`_StrictModel`, `extra="forbid"`).
- **Legacy keys stay valid:** `[tts] model`/`api_key` apply to the backend
  named by `[tts] backend` only. Setting the same key in both `[tts]` and that
  backend's subtable is a config error naming both locations — never a silent
  winner. The live config (`[tts] api_key` set, `backend` unset = voxtral)
  therefore loads and behaves exactly as today.
- `[tts.mlx_audio] model` has no baked-in default: an `mlx_audio` selection
  with no model from either the presenter pin or the subtable is a
  configuration error.

**Resolution:** a new pure function resolves `(backend, model)` for a
presenter: `presenter.tts or config.tts.backend`, then `presenter.tts_model or`
that backend's configured model (or the provider's own default where one
exists — Voxtral/ElevenLabs keep theirs). `speech_provider_for` takes the
resolved backend and model as arguments instead of reading `config.tts.backend`
itself. `speech_for` (runs/voice) and `ad_hoc_speech` (`emcee say
--presenter`) both route through it, so `say` honours pins for free. The house
voice (no presenter) resolves from `[tts]` exactly as today.

The render cache needs no change: it keys on `speech.voice` and
`speech.model`, so a re-pinned presenter never reuses another backend's clips.

`emcee run --dry-run` prints the resolved backend/model beside each package's
presenter, so pins can be audited before anything is spent.

### 2. The `mlx_audio` provider (`tts/mlx_audio.py`)

- **Request:** `POST {url}/v1/audio/speech`, JSON body `model`, `input`,
  `response_format`, and either `ref_audio` (the clip's absolute path) +
  `ref_text`, or `voice` (a preset). The clip is checked readable at
  construction, so a bad path fails before synthesis.
- **Identity:** `.voice = "clone:" + sha256(clip bytes + b"\0" +
  transcript)[:16]` (Voxtral's pattern, extended so a corrected transcript
  also invalidates cached clips); preset voices use the name. `.model` is the
  resolved model id.
- **Audio contract:** for `fmt="wav"` (chunked and bed paths) the provider
  returns 16-bit PCM mono WAV. It converts **sample format and channel count**
  with the stdlib (float32 or int16 in; stereo down-mixed to mono), and **does
  not resample** — a rate other than 24000 Hz is a `SpeechError` naming the
  rate and model (every candidate measured is 24 kHz; emcee does not resample,
  and `audioop` is gone from the stdlib). For `fmt="mp3"` (unchunked, no bed)
  it requests mp3 and passes it through, as Voxtral does. **To confirm at
  implementation:** the server's actual WAV encoding (sample format, header),
  measured against a live server — the bake-off normalized through ffmpeg and
  so never observed it.
- **Errors:** one retry on transport error/timeout/5xx (Voxtral's rule); any
  4xx fails at once with the server's error text. There is no content filter,
  so `SpeechBlocked` is never raised and the `rephrase` path never runs for
  these presenters.
- **Reachability:** a cheap probe (a GET on an endpoint the server answers
  without loading a model — which one is confirmed at implementation).
  `_process_one` (`cli.py:225`) calls it **immediately after `speech_for`
  and before `rewrite_manifest(..., None, None)`**, i.e. before any LLM spend
  and before the package is taken off air. Failure is a per-package error —
  `mlx-audio server not reachable at <url> (is the launchd service
  running?)` — and `emcee run` carries on with packages of other presenters.
  The probe is a method on the provider so `fake`/Voxtral providers are no-ops.
- **Timeout:** `[tts.mlx_audio] timeout_s` (default 600) per request; requests
  are per sentence, but a cold server's first request includes the model load.

### 3. Operator commands

**`emcee presenter edit <id>`** — edits any subset of fields; unspecified
fields keep their values:

- `--name`, `--sex`, `--character` / `--character-file`, `--voice`,
  `--voice-clone`, `--bed`, `--tts`, `--tts-model`, `--voice-clone-text`;
- `--clear-tts`, `--clear-tts-model`, `--clear-bed`,
  `--clear-voice-clone-text` (set/clear pattern as in `llama fix`); a set and
  its clear together is a usage error;
- setting `--voice` clears `voice_clone` and vice versa, preserving
  exactly-one-voice;
- **`--transcribe`** drafts `voice_clone_text` by posting the (resulting)
  clip to the server's `/v1/audio/transcriptions`, prints the draft, and
  writes it only on confirmation; mutually exclusive with
  `--voice-clone-text`. The transcription model is `[tts.mlx_audio]
  stt_model` (a Whisper model id; required only when `--transcribe` is used).
- The merged result is validated as a whole **before** an atomic save; any
  rejection — validation, a declined transcript, an unreachable server —
  leaves the file untouched.

Moving Phil is then one command:
`emcee presenter edit phil --tts mlx_audio --voice-clone ~/.emcee/samples/phil_ex.wav --transcribe`.

`emcee presenter add` gains `--tts`, `--tts-model`, `--voice-clone-text` (and
`--transcribe`), and `presenter list`/`show` display the pin. Every presenter
field is thereby CLI-editable, consistent with presenters being app-managed
and `[assign]` the only hand-edited emcee config.

**Reference-clip format:** whether the server accepts 48 kHz stereo clips like
`phil.wav` is measured at implementation. If it requires 24 kHz mono, emcee
does not convert it — the docs give the ffmpeg one-liner, as for beds.

### 4. Docs

- A runbook section: a launchd agent plist running `mlx_audio.server` from a
  dedicated venv, how to stop/start it, memory notes (one resident model;
  presenters pinned to *different* mlx models in one run may hold both).
- `emcee config init`'s template gains the subtables, commented.
- CLAUDE.md: the emcee paragraph (backends, pinning, `presenter edit`), and
  the "presenter voice clones are Voxtral-only" statement, which becomes false.

### 5. Testing (offline, deterministic)

- Provider against `httpx.MockTransport`: request body (clone and preset),
  retry/4xx rules, float32→int16 and stereo→mono conversion, rejection of a
  non-24 kHz response, mp3 passthrough, reachability probe.
- Config: legacy keys apply to the house backend only; duplicate key across
  `[tts]` and subtable is an error; subtables are strict; missing mlx model
  is an error; the live config shape loads unchanged.
- Presenter validation matrix (the rules in section 1).
- Resolution: presenter pin > house; model pin > subtable > provider default.
- A two-presenter `emcee run` with different backends gets one provider per
  package and distinct cache keys.
- `_process_one` with an unreachable server: error raised, **no scriptwrite
  call, manifest blocks untouched** (strict surface 2).
- `presenter edit`: each flag, set/clear conflicts, voice/voice_clone
  exclusivity, `--transcribe` confirm/decline, and file-untouched-on-reject.
- One opt-in `live` test against a running server.

## Out of scope

Managing the server process; resampling; recording backend/model in the
manifest's `dj_audio` block (the presenter file already says, unless re-pinned
later); running multiple mlx models concurrently; F5-TTS (not servable by
mlx-audio); any llama change; cutting the release.
