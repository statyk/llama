# emcee: per-presenter TTS pinning + a local `mlx_audio` backend — design

**Date:** 2026-10-12
**Scope:** `packages/emcee` only (llama, herder, transmitter untouched).
**Review mode:** Opus.

## Stakes

Hosted Voxtral spend is the station's main operating bottleneck; this work
exists to move some presenters (or the house voice) onto a free local model
**without** any voice changing underneath it. Nothing here is irreversible:
presenter TOMLs are written atomically and are small, re-creatable files, and
delivered packages are touched only by voicing them exactly as today. **Strict
surfaces:** (1) **never silently fall back to another backend** — an
`mlx_audio` voice (pinned presenter or house) whose server is down must fail,
not be voiced by Voxtral (that would spend money *and* break voice consistency
at once); (2) an `mlx_audio` configuration failure (server down, model
missing, uncalibrated or not loadable, missing or blank transcript, an
unpinned presenter under an `mlx_audio` house) and, when verification applies,
an STT path that cannot correctly transcribe a known clip must be detected
**before** any LLM spend, **before** `_process_one` clears a package's
manifest blocks, and **before** `emcee voice --fresh` deletes the clips it was
asked to re-roll, so it can never take a broadcast-ready package off air or
discard its audio (a hosted pin's configuration errors, such as an invalid API
key, keep today's timing); configured verification is **never silently
skipped**, except that clips already in the render cache (including ones
rendered before verification was enabled) are reused unverified; (3) a
clip that fails the runaway guard or verification twice fails its package and
never airs; (4) with no pins, a hosted house backend and verification off,
existing configs and presenter files behave as today, except: a failed `emcee
voice --fresh` keeps its clips; a presenter file with an unknown key fails to
load (no live file has one); `presenter add` stores `voice_clone` as an
absolute path. `presenter list`/`show` and dry-run output change only for
pinned presenters.

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
| Voxtral (aired baseline) | — | 2.3% | |
| Qwen3-TTS 1.7B Base bf16 | 2.8 | 1.9% | best local; the operator judged it a downgrade worth taking |
| Qwen3-TTS 0.6B Base | 2.4 | 4.2% | |
| Chatterbox | 1.9 | 9.3% | a 4-word sentence became ~10 s of babble |
| F5-TTS (f5-tts-mlx) | 3.35 | 3.7% | pacing stretched ~75%; not servable by mlx-audio |
| Higgs Audio v3 4B | ~12 | 2.3% | swapped the host to ~15/16 GB |

WER (from `~/tts-bakeoff/out/*.asr.json`) measures intelligibility, not
naturalness: Qwen scores better than Voxtral and the operator still judged it
a downgrade by ear. Every scored set2 take in the table was unseeded (the extra 1.7B takes and
the set1 renders, including the 0.6B runaway, used seed 42), and each configuration had only 1–3 takes on one
presenter. Phil's evaluated reference was a 12.9 s excerpt; the other
presenters' clips are 21–30 s 48 kHz stereo.

All were driven over `mlx_audio.server`'s `POST /v1/audio/speech` (except F5)
with `ref_audio` (a **local file path** — the server reads it from disk) and
`ref_text` (a transcript of the reference clip). So the integration surface is
one HTTP dialect, and the model is a request field: the backend must not be
Qwen-specific.

## Design

### 1. Pinning and configuration

**Presenter TOML** (`presenters.py:Presenter`) gains three optional fields:

```toml
tts = "mlx_audio"               # backend pin; absent = [tts] backend
tts_model = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"  # mlx_audio only; absent = [tts.mlx_audio] model
voice_clone_text = "It's the chemistry, basically. ..."    # transcript of voice_clone
```

`Presenter` moves onto emcee's strict base (`_StrictModel`, `extra="forbid"`,
the one `config.py` uses), so a misspelled key (`tts_modle`) is a load error
rather than a pin silently ignored. All five live presenter files use only
known keys.

Validation (model validator, at load and before every save):

- `tts`, when set, must be one of `voxtral`, `elevenlabs`, `mlx_audio`.
  `fake` is not a presenter pin (tests select it through config).
- `tts` and `tts_model` reject empty strings.
- `tts_model` is allowed only with `tts = "mlx_audio"`.
- `voice_clone` with `tts = "elevenlabs"` is an error.
- `tts = "mlx_audio"` requires `voice_clone` (a preset `voice` is an error)
  and a `voice_clone_text` that is non-empty after stripping whitespace.
  `voice_clone_text` is otherwise allowed and ignored (Voxtral needs none), so
  it can be added ahead of a pin.
- The exactly-one-of `voice`/`voice_clone` rule is unchanged.

**Config** (`config.py`): `[tts]` keeps its meaning — the house voice and
every unpinned presenter, which never inherits `mlx_audio` — and gains
`voice_clone_text` and four subtables:

```toml
[tts]
backend = "voxtral"          # the house voice + every unpinned presenter
voice_clone_text = "..."     # transcript of [tts] voice_clone

[tts.voxtral]                # api_key, model (MISTRAL_API_KEY still wins over api_key)
[tts.elevenlabs]             # api_key, model (ELEVENLABS_API_KEY still wins)

[tts.mlx_audio]
url = "http://127.0.0.1:8000"
model = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"
timeout_s = 600
stt_model = "..."            # speech-to-text model on the same server

[tts.verify]
backends = []                # default off; e.g. ["mlx_audio"] or ["mlx_audio", "voxtral"]
```

- Every subtable is strict (`_StrictModel`). `[tts.mlx_audio] url` defaults
  to `http://127.0.0.1:8000`; `timeout_s` defaults to 600; `stt_model` is
  optional (used by verification and `--transcribe`). `model` has no default
  and is required only when something resolves to `mlx_audio` (checked at
  resolution), so a `[tts.mlx_audio]` with only `stt_model` is valid.
- **House voice on `mlx_audio`:** a presenter never inherits `mlx_audio`
  (resolution, below), so `[tts] backend = "mlx_audio"` voices only packages
  with no presenter and `emcee say` without `--presenter`. When the house
  voice resolves to `mlx_audio`, the factory rejects a `[tts] voice` preset
  (mlx is clone-only), a missing `voice_clone` or a blank `voice_clone_text`,
  naming the `[tts]` key. `voice_clone_text` is otherwise allowed and ignored.
- **Hosted keys and models:** a hosted backend's subtable applies wherever
  that backend is used, as the house backend or as a pin. Legacy `[tts]
  api_key`/`model` remain valid only while `[tts] backend` is a hosted
  backend, and then mean that backend's `api_key`/`model` exactly as today, so
  the live config keeps working unchanged. Setting the same key both in `[tts]`
  and in the house backend's subtable is a config error naming both locations.
  With `[tts] backend = "mlx_audio"`, `[tts] api_key`/`model` are a config
  error whose message names `[tts.voxtral]`/`[tts.elevenlabs]` (for keys) and
  `[tts.mlx_audio] model` (for the model).

**Resolution:** a new pure function resolves `(backend, model, api_key)` for a
presenter or the house voice, before any spend and before the manifest clear.
The house backend is `[tts] backend`. A presenter's is `presenter.tts`; an
unpinned presenter inherits `[tts] backend` unless that is `mlx_audio`, which
is a resolution error (`pin tts explicitly: the house backend is mlx_audio`),
so changing the house voice never moves a presenter. For `mlx_audio` the model
is `presenter.tts_model`, else `[tts.mlx_audio] model`, else a configuration
error; a model outside the runaway guard's calibration table (section 3) is a
configuration error (`model not calibrated for the runaway guard`). For a
hosted backend the model is its subtable's `model`, else (only when it is
`[tts] backend`) `[tts] model`, else the provider default; the key is its
subtable's `api_key`, else (only when it is `[tts] backend`) `[tts] api_key`.
The provider's env var (`MISTRAL_API_KEY` / `ELEVENLABS_API_KEY`) still wins
over both, as today. A missing key is the existing "API key missing" error,
which fires at provider construction, before any spend, and names the env var
and the locations that apply.

`speech_provider_for` takes the resolution and the transcript (`clone_text`)
as **required** arguments with no defaults, instead of reading
`config.tts.backend` itself, so an unmigrated call site fails loudly rather
than falling back to `[tts] backend` or dropping the transcript. `clone_text`
is `[tts] voice_clone_text` (house), the presenter's `voice_clone_text`
(presenter), `say --clone-text` (`say --clone`), or `None`. `speech_for`
(run/voice) and every `ad_hoc_speech` branch (`emcee say`,
`process.py:139-147`, which today calls `speech_provider_for` directly) route
through the resolver, and the factory applies the quality layer (section 3),
so every path gets the guard and verification. The factory's ElevenLabs-clone
check applies to **any** clone that resolves to `elevenlabs`, pinned or
inherited. The render cache keys on `speech.voice` and `speech.model`, so a
re-pinned presenter never reuses another backend's clips.

`emcee run --dry-run` prints the resolved backend/model beside **pinned**
presenters only, so pins can be audited before any spend. It loads presenter
files with `_presenter_file_exists`'s case-insensitive lookup
(`cli.py:276-283`). A file that fails to load shows `[invalid
presenters/<id>.toml]`, and a presenter whose resolution fails (an unpinned
presenter under an `mlx_audio` house, a missing or uncalibrated mlx model)
shows `[unresolved: <message>]`, both on its row like `[missing ...]`;
neither aborts the listing. Dry-run does not preflight.

### 2. The `mlx_audio` provider (`tts/mlx_audio.py`)

- **Request:** `POST {url}/v1/audio/speech`, JSON body `model`, `input`,
  `response_format = "wav"`, `max_tokens` (capped in proportion to the
  text's length, section 3), `ref_audio` (the clip's absolute path) and
  `ref_text`. `max_tokens` is always sent because the server's default of
  1200 (≈ 96 s) silently truncates long unchunked segments. At construction
  the clip is checked readable and a `ref_text` that is empty after
  `.strip()` is a `SpeechError`, so a bad clone fails before synthesis.
- **Identity:** `.voice = "clone:" + sha256(clip bytes + b"\0" +
  transcript)[:16]` (Voxtral's pattern; a corrected transcript invalidates
  cached clips); `.model` is the resolved model id.
- **Audio contract:** the provider always requests WAV. The server writes
  16-bit PCM WAV (`mlx_audio/audio_io.py` `write`), readable by stdlib `wave`;
  the provider checks sample width 2 and mono and raises `SpeechError`
  otherwise. For `fmt="wav"` (chunked and bed paths) it returns the WAV as
  is; for `fmt="mp3"` (unchunked, no bed) it encodes locally with
  `audio._encode_mp3`. Only 24 kHz models are supported (preflight enforces
  it); Qwen3-TTS is 24 kHz (`qwen3_tts/config.py`).
- **Errors:** a non-200 fails at once with the server's text.
  `httpx.ConnectError` is retried once after a short delay, then is a
  `SpeechError`: `mlx-audio server not reachable at <url> (is the launchd
  service running?)`. Generation failures after the 200 arrive as an aborted
  chunked body, so `httpx.RemoteProtocolError`, `ReadError`, `ReadTimeout`
  and a non-WAV or empty body are a `SpeechError` pointing at the server log,
  never retried (a timed-out request keeps running server-side). There is no
  content filter, so `SpeechBlocked` and the `rephrase` path never apply.
- **Preflight:** `preflight() -> None` joins the `SpeechProvider` protocol,
  is called unconditionally, and is a no-op on hosted and fake providers
  (test doubles gain it). For `mlx_audio` it synthesizes one fixed sentence
  of at least 20 characters ("Good evening, and welcome to the show.") with
  `max_tokens = 200` and requires a 16-bit mono 24 kHz WAV, else
  `SpeechError`: a down server, an unknown or unloadable model or a bad
  response fails here, and the cold model load is absorbed, at no cost. House
  beds are always 24 kHz (`tts/bed.py`), so no bed-rate check is needed.
  When verification applies, preflight also checks the STT path (section 3).
  In `_process_one` (`cli.py:226`) the existing `try/finally speech.close()`
  moves up to start right after `speech_for`, and preflight is its first call:
  before the `--fresh` unlink and before `rewrite_manifest(pkg, dj_notes=None,
  dj_audio=None)` (`cli.py:261`), so before any LLM spend. Any failure is a
  per-package error; `emcee run` carries on with other presenters' packages.
  `emcee say` has no LLM spend and no manifest, so it does not preflight.
- **`emcee voice --fresh`:** today `voice_cmd` unlinks the `--fresh` clips
  before calling `_process_one` (`cli.py:448-462`). The stem check stays in
  `voice_cmd`; the unlink (and its `re-rolling ...` message) moves inside
  `_process_one`, after preflight and before the manifest clear, so no
  configuration-only error discards the clips.
- **Timeout:** `[tts.mlx_audio] timeout_s` (default 600) per sentence request.

### 3. Runaway guard, quality layer and transcript verification

**Runaway guard** (always on for `mlx_audio`, inside the provider). Each
request's `max_tokens` is capped in proportion to the text's length, and the
returned audio's duration is checked against that length: a clip implausibly
long or short for its text, or within a small margin of the cap's own duration
(a capped runaway would otherwise pass), raises `SpeechDefect` (a
`SpeechError` subclass) that the provider never retries. The cap becomes seconds
through the model's codec frame rate, so the constants are per model: emcee
carries a table of calibrated mlx models, initially only Qwen3-TTS-12Hz 1.7B
Base (12.5 frames/s, `qwen3_tts/config.py`), and resolving to any other model
is a configuration error (section 1). That is the cost of a safe guard; adding
a model means a calibration run. Evidence: the bake-off's Qwen 0.6B turned one
set1 sentence into 320 s of babble (clip 432 s instead of ~120 s, WER 52%);
Chatterbox turned "Here is Morning Dew." into ~10 s.

**Quality layer** (sole owner of the quality retry). `speech_provider_for`
wraps every `mlx_audio` provider (guard only, when verification is off) and
every provider whose backend is listed in `[tts.verify] backends`. Per
`synthesize` call it makes at most two attempts: a guard or verification
failure re-synthesizes once (output is non-deterministic), and a second
failure of either check raises `SpeechDefect` naming the text and, for
verification, the transcript; `_synthesize_dj_audio` annotates it with
`.segment` as it does `SpeechBlocked` (`audio.py:342-344`), and the package
fails rather than airing it. The retried unit is the sentence when chunked,
the whole segment otherwise; for Voxtral a retry costs one extra call for that
unit. The layer passes `SpeechBlocked` through, delegates `preflight()` and
`close()`, and keeps the inner `.voice`/`.model`, so cached clips are not
re-verified and enabling verification does not invalidate the cache.
`_locate_block`'s probes go through the layer too; limitation: with Voxtral
listed, an unchunked segment and a content block, a probe that fails
verification twice surfaces as `SpeechDefect` instead of the located block.

**Transcript verification** (optional, any backend listed in `[tts.verify]
backends`). The layer always asks its inner provider for `fmt="wav"`,
transcribes it via the server's `POST /v1/audio/transcriptions` (multipart
filename `clip.wav`, since the server picks its temp-file format from the
suffix and httpx's default maps to `.mp3`, which needs ffmpeg; `model =
stt_model`, `language = "en"`, `response_format=json`), compares it with the
text sent, and encodes mp3 locally with `audio._encode_mp3` if the caller
asked for it. So a hosted backend's unchunked output changes only when it is
listed.

- The comparison normalizes both sides (case, punctuation), drops
  number-bearing tokens (digits and spelled-out number words) from both, since
  number formatting is open-ended, and fails only on **gross** mismatch: too
  few of the script's words recovered, or a transcript far longer than the
  script. It tolerates a wrong word or two per sentence: ASR misrenders proper
  nouns ("De Doelen" fails on Voxtral too), and the lexicon's respellings
  (`Shugaree`) are sent as spelled.
- A failed transcription request is a `SpeechError`, never a pass. A non-empty
  `backends` requires `[tts.mlx_audio] stt_model`; a name other than
  `mlx_audio`, `voxtral`, `elevenlabs` is a config error.
- **Never silently skipped:** when a package's resolved backend is listed,
  preflight checks the STT path end to end, before LLM spend and before the
  manifest clear: an mlx inner provider's preflight sentence must pass the
  full comparison (with the quality layer's single retry, since synthesis is
  non-deterministic); for a hosted one, a bundled ~2 s WAV of a fixed sentence
  (an emcee package resource, rendered once with an Apache-2.0 preset-voice
  model such as Kokoro, provenance recorded in the evidence doc) must
  transcribe to a pass against that sentence.
  A Voxtral presenter therefore depends on the local server whenever
  `"voxtral"` is listed. `emcee say` verifies too, without preflight (a dead
  server fails its first check).

**Constants are measured, not guessed.** The guard's cap and duration
constants and the verification thresholds are set by a measurement task in the
implementation plan: render ~50 unseeded sentences (several presenters' clips,
Phil included) and a few whole segments (the unchunked path) through the real
server, plus ~10 Voxtral sentences if `"voxtral"` may be listed; record
per-unit duration, character count and transcript match, and any Whisper
repetition loops; pick constants that pass every clean unit with margin and
fail the bake-off's known runaways (Qwen 0.6B set1 and Chatterbox's "Here is
Morning Dew."); and assert the cap-margin rule on a synthetic cap-length clip.
The data and the chosen constants go in an in-repo evidence doc that the
constants cite.

### 4. Operator commands

**`emcee presenter edit <id>`** — edits any subset of fields; unspecified
fields keep their values:

- `--name`, `--sex`, `--character` / `--character-file`, `--voice`,
  `--voice-clone`, `--bed`, `--tts`, `--tts-model`, `--voice-clone-text`;
- `--clear-tts`, `--clear-tts-model`, `--clear-bed`,
  `--clear-voice-clone-text` (set/clear pattern as in `llama fix`); a set and
  its clear together is a usage error;
- `--voice` together with `--voice-clone` is a usage error. Setting `--voice`
  clears `voice_clone` and `voice_clone_text`. Setting `--voice-clone` clears
  `voice` and also clears `voice_clone_text` unless a new one
  (`--voice-clone-text` or `--transcribe`) is given in the same command, so
  validation forces a fresh transcript for an `mlx_audio` pin;
- **`--transcribe`** drafts `voice_clone_text` by transcribing the (resulting)
  clip with verification's STT client and `[tts.mlx_audio] stt_model`
  (required only when `--transcribe` is used), prints the draft, and writes it
  only on confirmation; mutually exclusive with `--voice-clone-text`. When
  `[tts.verify] backends` is empty it then unloads the STT model (`DELETE
  /v1/models?model_name=<stt_model>`).
- `voice_clone` is stored as an absolute, resolved path (the server reads it
  from its own working directory).
- The edit is `Presenter.model_validate({**old.model_dump(), **changes})`,
  never `model_copy(update=…)`, which skips validators (the idiom at
  `process.py:184`), and is validated whole **before** an atomic save; any
  rejection — validation, a declined transcript, an unreachable server —
  leaves the file untouched.

Moving Phil uses his evaluated transcript: the runbook copies
`~/tts-bakeoff/refs/phil_ex.wav` (the evaluated 12.9 s 24 kHz mono excerpt)
and `phil_ex.txt` into `~/.emcee/samples/` and runs
`emcee presenter edit phil --tts mlx_audio --voice-clone ~/.emcee/samples/phil_ex.wav --voice-clone-text "$(cat ~/.emcee/samples/phil_ex.txt)"`.
`--transcribe` is for new presenters.

`emcee presenter add` gains `--tts`, `--tts-model`, `--voice-clone-text` (and
`--transcribe`), stores `voice_clone` as an absolute path the same way, and
`presenter list`/`show` display the pin, so every presenter field is
CLI-editable (`[assign]` stays the only hand-edited emcee config).

**`emcee say`:** with no voice flags it uses the house voice, including its
transcript. `--clone PATH` gains `--clone-text TEXT`, required (non-blank)
when the house backend is `mlx_audio` and ignored otherwise; `--clone-text`
without `--clone` is a usage error. `--voice` with an `mlx_audio` house is a
usage error. `--presenter` resolves as in `run` (section 1).

**Reference clips:** the server decodes, resamples and down-mixes reference
clips itself (`mlx_audio/utils.py` `load_audio`), so 48 kHz stereo clips such
as `phil.wav` are accepted; emcee does not convert them.

### 5. Docs

- A runbook section:
  - **Install the new emcee release before pinning any presenter** — an older
    binary drops `tts`/`tts_model` and would voice the presenter on Voxtral
    from the newly edited clip.
  - A launchd agent running `mlx_audio.server` from a dedicated venv with
    `mlx-audio` pinned to the evaluated 0.5.8 (its server-side sampling
    defaults — temperature, top_k, top_p — define the evaluated voice, and
    emcee does not send them), bound to `127.0.0.1`, with a working directory
    that works under launchd, and `HF_HUB_OFFLINE=1` so a mistyped model id
    fails fast instead of starting a download (download the TTS and STT models
    once while online, before enabling it); how to stop/start it.
  - Memory: the server keeps every model it has served resident until restart,
    so presenters pinned to different mlx models hold all of them, and with
    verification on it also holds the STT model.
  - Drafting a transcript by hand: `mlx_whisper` on the CLI, when no
    server-loadable `stt_model` is configured.
  - Moving the house voice to `mlx_audio`: pin every presenter first (e.g.
    `--tts voxtral`). With the live `[assign] default = "roydemure"` every
    package has a presenter, so moving the default voice means pinning Roy,
    not a house change.
  - Before moving Phil: copy `phil_ex.wav` and `phil_ex.txt` (section 4); the
    calibration task (section 3) must have set the constants; then a go-live
    listen.
  - Rollback: to unpin Phil, `emcee presenter edit phil --clear-tts
    --clear-tts-model --voice-clone ~/.emcee/samples/phil.wav` (his aired
    Voxtral reference); unpin before downgrading the binary.
- `emcee config init`'s template gains `[tts] voice_clone_text`,
  `[tts.voxtral]`, `[tts.elevenlabs]`, `[tts.mlx_audio]` and `[tts.verify]`,
  commented.
- The evidence doc for the measured constants (section 3).
- CLAUDE.md: the emcee paragraph (backends, pinning, the house voice on
  `mlx_audio`, per-backend key subtables, the runaway guard and quality layer,
  verification, `presenter edit`), and the "presenter voice clones are
  Voxtral-only" statement, which becomes false.

### 6. Testing (offline, deterministic)

- Provider against `httpx.MockTransport`: request body (`ref_audio`,
  `ref_text`, `response_format = "wav"`, `max_tokens` proportional to the
  text); a non-200 failing at once with the server's text; a
  `RemoteProtocolError` from the transport as a `SpeechError`, not retried;
  one retry on `ConnectError`, none on `ReadTimeout`; a blank `ref_text`, a
  non-16-bit or a stereo WAV rejected; local mp3 encoding for `fmt="mp3"`.
- Runaway guard: a long, short or cap-length clip raises `SpeechDefect`,
  unretried by the provider. Quality layer: one retry, a pass on the retry
  succeeding, a double failure a `SpeechDefect` carrying `.segment`;
  `SpeechBlocked` passed through; `preflight()`/`close()` delegated; `say`
  with no flags, `--clone` and `--presenter` each wrapped when the backend is
  listed.
- Preflight: a no-op on the hosted and fake providers; a non-24 kHz WAV
  rejected. Strict surface 2, on an already-voiced package with a dead
  server: `_process_one` and `emcee voice --fresh` raise with no scriptwrite
  call, the manifest's bytes unchanged, and the `--fresh` clip still on disk.
- `run`, `voice` and `say --presenter` each send `ref_text`; with house
  backend `voxtral` (env key set, a transport that fails the test if called),
  an `mlx_audio` pin and a dead server, each raises and constructs or calls no
  provider but the mlx one (strict surface 1).
- Config: `[tts.mlx_audio]` with its defaults, and holding only `stt_model`,
  valid; every subtable strict; the live config loads. House `mlx_audio`
  rejects `[tts] api_key`/`model` with a message naming the subtables.
  Legacy `[tts] api_key`/`model` valid under a hosted house; the same key in
  `[tts]` and the house subtable an error naming both. `[tts.verify]`: an
  unknown backend name, and a non-empty list without `stt_model`, rejected.
- Presenter validation matrix (the rules in section 1), including strictness
  (an unknown key is a load error), and rejection of empty-string
  `tts`/`tts_model`, a `fake` pin, `tts_model` on a hosted pin, a preset
  `voice` with an `mlx_audio` pin, and a whitespace-only transcript.
- Resolution: presenter pin > house; an unpinned presenter under an
  `mlx_audio` house an error; mlx model pin > `[tts.mlx_audio] model`, a
  missing or uncalibrated mlx model an error; a resolved-mlx house voice with
  a `voice` preset, no clip or a blank transcript rejected; a hosted model and
  key from the subtable, else from legacy `[tts]` only for the house backend,
  else the default (model) or "API key missing" (key); env wins over both; an
  ElevenLabs clone rejected whether pinned or inherited.
- `say`: `--clone` without `--clone-text` rejected under an `mlx_audio`
  house, `--clone-text` without `--clone` rejected, `--voice` rejected under
  an `mlx_audio` house, and no voice flags sending the house transcript.
- Verification: the upload's filename `clip.wav`, `language = "en"` and
  `response_format=json`; WAV requested from the inner provider and mp3
  encoded locally; a pass, a fail-then-pass, and a double fail with both
  texts; number-bearing tokens ignored; a wrong word or two passing; a failed
  transcription request a `SpeechError`; preflight failing the package (no
  scriptwrite call, manifest bytes unchanged) on an unreachable STT server or
  a failed comparison, for an mlx and a hosted (bundled clip) inner provider;
  cache hits not re-verified; Voxtral verified only when listed.
- A two-presenter `emcee run` with different backends gets one provider per
  package and distinct cache keys.
- `emcee run --dry-run`: unpinned output unchanged; a pin shows its
  backend/model; an invalid file shows `[invalid ...]`, a failed resolution
  `[unresolved: ...]`, and the listing completes; a case-mismatched file name
  still loads (the empty `BILLYG.toml` in `tests/test_run_cmd.py:545-558`
  becomes a valid file).
- `presenter edit`: each flag, set/clear conflicts, `--voice` with
  `--voice-clone` rejected, `--voice` clearing the clip and transcript, a
  changed clip clearing the transcript, `--transcribe` confirm/decline (with
  `response_format=json`) and its `DELETE` only when verification is off,
  absolute clip path stored, and an invalid merged edit leaving the file
  untouched via the merge path.
- One opt-in `live` test against a running server.

## Out of scope

Managing the server process; resampling, and non-24 kHz mlx models; preset
voices on `mlx_audio`; recording backend/model in the manifest's `dj_audio`
block (the presenter file already says, unless re-pinned later); concurrent
mlx models; F5-TTS (not servable by mlx-audio); any llama change; cutting the
release.

## Unverified premises

- **Memory headroom** on the 16 GB mini in a real run with the TTS model, the
  STT model (verification on) and `claude -p` resident: the bake-off's
  `peak_rss_gb` of 12.0 looks capped. Test: `footprint`.
- **Unseeded production quality:** the babble/truncation rate is unknown.
  Test, gating Phil going live: the calibration task (section 3), then a
  go-live listen.
- **Presenters other than Phil:** unmeasured beyond the calibration sample.
  Test: one `say` each.
- **A loadable `stt_model` returning non-empty `json` text:**
  `mlx-community/whisper-large-v3-turbo` (mlx_whisper format) does not load in
  mlx-audio's server, whose Whisper loader needs processor files; the server
  supports other STT families (Whisper with processor files, Parakeet,
  Qwen3-ASR, …). Whisper's handling of short clips with foreign venue names is
  also untested. Test: the plan's first task confirms a model by a live
  request with filename `clip.wav` and `language=en`, including the De Doelen
  sentence.
- **Live server responses:** stdlib `wave` was checked against mlx-audio's
  WAV writer (`audio_io.write`: 24000 Hz, mono, 16-bit), not a live response.
  Test: one request at implementation.
