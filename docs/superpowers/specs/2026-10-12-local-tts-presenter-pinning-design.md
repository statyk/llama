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
(2) a configuration-only failure (server down, model not loadable, missing
transcript) must be detected **before** any LLM spend, **before**
`_process_one` clears a package's manifest blocks, and **before** `emcee voice
--fresh` deletes the clips it was asked to re-roll, so it can never take a
broadcast-ready package off air or discard its audio; (3) existing configs and
presenter files keep working unchanged — with no pins set, every successful
operation behaves and outputs exactly as today (the one intended difference:
a failed `emcee voice --fresh` no longer deletes the clips, per (2)).

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
a downgrade by ear. The bake-off's server was seeded (production will not be),
and each configuration had only 1–3 takes on one presenter.

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

`Presenter` moves onto emcee's strict base (`_StrictModel`, `extra="forbid"`,
the one `config.py` uses), so a misspelled key (`tts_modle`) is a load error
rather than a pin silently ignored. All five live presenter files use only
known keys.

Validation (model validator, at load and before every save):

- `tts`, when set, must be one of `voxtral`, `elevenlabs`, `mlx_audio`.
  `fake` is not a presenter pin (tests select it through config).
- `tts` and `tts_model` reject empty strings.
- `tts_model` without `tts` is an error (it would silently follow whatever
  `[tts] backend` is).
- `voice_clone` with `tts = "elevenlabs"` is an error.
- `tts = "mlx_audio"` with `voice_clone` requires a non-empty
  `voice_clone_text`. `voice_clone_text` is otherwise allowed and ignored
  (Voxtral needs none), so it can be added ahead of a pin.
- The exactly-one-of `voice`/`voice_clone` rule is unchanged.

**Config** (`config.py`): `[tts]` keeps its meaning — the house voice and
every unpinned presenter — and gains one subtable:

```toml
[tts]
backend = "voxtral"          # the house voice + every unpinned presenter

[tts.mlx_audio]
url = "http://127.0.0.1:8000"
model = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"
timeout_s = 600
stt_model = "mlx-community/whisper-large-v3-turbo"  # only for presenter --transcribe
```

- `[tts.mlx_audio]` is a strict model (`_StrictModel`, `extra="forbid"`).
  `url` defaults to `http://127.0.0.1:8000`; `model` has no default;
  `timeout_s` defaults to 600; `stt_model` is optional.
- **The house voice cannot use `mlx_audio`:** `[tts] backend = "mlx_audio"`
  is a config error whose message says to pin presenters instead. The house
  clip and `emcee say --clone` have no transcript source, and Qwen without
  `ref_text` silently degrades. So `emcee say --clone`/`--voice` (no
  presenter) always use the house hosted backend, as today.
- `[tts] model`/`api_key` apply to the house backend only, exactly as today.
  The live config (`[tts] api_key` set, `backend` unset = voxtral) therefore
  loads and behaves as today.

**Resolution:** a new pure function resolves `(backend, model)` for a
presenter: `presenter.tts or config.tts.backend`; then `presenter.tts_model`,
else that backend's configured model — `[tts.mlx_audio] model` for
`mlx_audio`, `[tts] model` for the house backend — else the provider's own
default (Voxtral/ElevenLabs keep theirs). An `mlx_audio` selection with no
model from either the pin or `[tts.mlx_audio]` is a configuration error.

A presenter pinned to a hosted backend that is **not** the house backend takes
its API key from that backend's env var only (`MISTRAL_API_KEY` /
`ELEVENLABS_API_KEY`), never from `[tts] api_key`, and its model from
`tts_model` or the provider's built-in default. A missing key is the existing
"API key missing" error, which fires at provider construction, before any
spend; for such a pin it names only the env var.

`speech_provider_for` takes the resolved backend and model as **required**
arguments, with no defaults, instead of reading `config.tts.backend` itself —
an unmigrated call site fails loudly rather than falling back to `[tts]
backend`. `speech_for` (runs/voice) and `ad_hoc_speech`'s `--presenter`
branch (`emcee say --presenter`, `process.py:139-145`, which today calls
`speech_provider_for` directly) both route through the resolver. The house
voice (no presenter) resolves from `[tts]` exactly as today.

The factory's ElevenLabs-clone check applies to **any** clone that resolves to
`elevenlabs`, pinned or inherited from `[tts] backend`.

The render cache needs no change: it keys on `speech.voice` and
`speech.model`, so a re-pinned presenter never reuses another backend's clips.

`emcee run --dry-run` prints the resolved backend/model beside **pinned**
presenters only, so pins can be audited before anything is spent and
unpinned output stays byte-identical (`tests/test_run_cmd.py:558`). A
presenter file that fails to load shows `[invalid presenters/<id>.toml]` on
its row, like the existing `[missing ...]` note, and never aborts the listing.
Dry-run does not preflight.

### 2. The `mlx_audio` provider (`tts/mlx_audio.py`)

- **Request:** `POST {url}/v1/audio/speech`, JSON body `model`, `input`,
  `response_format`, `max_tokens = 4000`, and either `ref_audio` (the clip's
  absolute path) + `ref_text`, or `voice` (a preset). `max_tokens` is sent
  explicitly because the server's default of 1200 (≈ 96 s) silently truncates
  long unchunked segments; 4000 is the bake-off's measured value. The clip is
  checked readable at construction, so a bad path fails before synthesis.
- **Identity:** `.voice = "clone:" + sha256(clip bytes + b"\0" +
  transcript)[:16]` (Voxtral's pattern, extended so a corrected transcript
  also invalidates cached clips); preset voices use the name. `.model` is the
  resolved model id.
- **Audio contract:** for `fmt="wav"` (chunked and bed paths) the provider
  returns the server's WAV as is. The server always writes 16-bit PCM WAV
  (`mlx_audio/audio_io.py:532-570`), readable by stdlib `wave`; the provider
  checks sample width 2 and mono and raises `SpeechError` otherwise. The rate
  is checked only against the bed (preflight, below). Qwen3-TTS outputs
  24 kHz per its model config (`qwen3_tts/config.py`); the bake-off resampled
  every output, so other models' native rates were not observed. For
  `fmt="mp3"` (unchunked, no bed) it requests mp3 and passes it through, as
  Voxtral does.
- **Errors:** `/v1/audio/speech` streams, so most generation failures arrive
  after a 200 as an empty or truncated body. A non-200 fails at once with the
  server's error text. An empty or unparseable 200 body is a `SpeechError`
  whose message points at the server log. Retry **once, on connection errors
  only** — not on read timeouts (a timed-out request keeps running
  server-side and a retry queues behind it) and not on 5xx (model-load 500s
  are deterministic). There is no content filter, so `SpeechBlocked` is never
  raised and the `rephrase` path never runs for these presenters.
- **Preflight:** `preflight()` becomes part of the `SpeechProvider` protocol
  and is called unconditionally (no `getattr`); it is a no-op on
  voxtral/elevenlabs/fake, and test doubles gain the method. For `mlx_audio`
  it is one tiny real synthesis ("Good evening.") with the resolved model,
  `ref_audio`/`ref_text` (or `voice`) and `fmt="wav"`; the response must parse
  as WAV with sample width 2 and mono, and preflight returns its sample rate.
  It catches a server that is down, a wrong or unknown model id (404), a model
  that cannot load (500), a preset voice on a Base model, and a non-WAV or
  empty body — and it absorbs the cold model load. It costs a few seconds per
  package and no money.
  `_process_one` (`cli.py:226`) calls `speech.preflight()` **immediately after
  `speech_for` and before `rewrite_manifest(pkg, dj_notes=None,
  dj_audio=None)`** (`cli.py:261`), i.e. before any LLM spend and before the
  package is taken off air. If a bed is active and preflight's rate differs
  from the bed's, it fails there with the existing bed-rate message
  (`audio.py` `_render`). A connection failure reads `mlx-audio server not
  reachable at <url> (is the launchd service running?)`. Any failure is a
  per-package error, and `emcee run` carries on with packages of other
  presenters. `emcee say` has no LLM spend and no manifest, so it does not
  preflight; a dead server fails its first synthesis.
- **`emcee voice --fresh`:** today `voice_cmd` unlinks the `--fresh` clips
  before calling `_process_one` (`cli.py:448-462`). The stem check stays in
  `voice_cmd`; the unlink (and its `re-rolling ...` message) moves inside
  `_process_one`, after assignment, `speech_for` and preflight succeed and
  before the manifest clear. This also stops any other configuration-only
  error from discarding the clips.
- **Timeout:** `[tts.mlx_audio] timeout_s` (default 600) per request;
  requests are per sentence.

### 3. Operator commands

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
- **`--transcribe`** drafts `voice_clone_text` by posting the (resulting)
  clip to the server's `/v1/audio/transcriptions` with
  `response_format=json` (the server's default is ndjson), prints the draft,
  and writes it only on confirmation; mutually exclusive with
  `--voice-clone-text`. The transcription model is `[tts.mlx_audio]
  stt_model` (a Whisper model id; required only when `--transcribe` is used).
  After transcribing it sends `DELETE /v1/models?model_name=<stt_model>` so
  Whisper does not stay resident beside the TTS model.
- `voice_clone` is stored as an absolute, resolved path (the server reads it
  from its own working directory).
- The merged result is validated as a whole **before** an atomic save; any
  rejection — validation, a declined transcript, an unreachable server —
  leaves the file untouched.

Moving Phil is then one command:
`emcee presenter edit phil --tts mlx_audio --voice-clone ~/.emcee/samples/phil_ex.wav --transcribe`.
`phil_ex.wav` is the evaluated 12.9 s 24 kHz mono excerpt, which the runbook
copies from `~/tts-bakeoff/refs/phil_ex.wav` into `~/.emcee/samples/` first.

`emcee presenter add` gains `--tts`, `--tts-model`, `--voice-clone-text` (and
`--transcribe`), stores `voice_clone` as an absolute path the same way, and
`presenter list`/`show` display the pin. Every presenter field is thereby
CLI-editable, consistent with presenters being app-managed and `[assign]` the
only hand-edited emcee config.

**Reference clips:** the server decodes, resamples and down-mixes reference
clips itself (`mlx_audio/utils.py` `load_audio`), so 48 kHz stereo clips such
as `phil.wav` are accepted; emcee does not convert them.

### 4. Docs

- A runbook section:
  - **Install the new emcee release before pinning any presenter** — an older
    binary drops `tts`/`tts_model` and would voice the presenter on Voxtral
    from the newly edited clip.
  - A launchd agent running `mlx_audio.server` from a dedicated venv, bound to
    `127.0.0.1`, with a working directory and `PATH` (ffmpeg) that work under
    launchd, and `HF_HUB_OFFLINE=1` so a mistyped model id fails fast instead
    of starting a download; how to stop/start it.
  - Memory: the server keeps every model it has served resident until restart,
    so presenters pinned to different mlx models hold all of them.
  - Copying `phil_ex.wav` into `~/.emcee/samples/` before moving Phil.
- `emcee config init`'s template gains `[tts.mlx_audio]`, commented.
- CLAUDE.md: the emcee paragraph (backends, pinning, `presenter edit`, the
  house voice staying hosted), and the "presenter voice clones are
  Voxtral-only" statement, which becomes false.

### 5. Testing (offline, deterministic)

- Provider against `httpx.MockTransport`: request body (clone and preset,
  `max_tokens = 4000`), a non-200 failing at once with the server's text, an
  empty 200 body as `SpeechError`, retry once on a connection error and never
  on a read timeout or 5xx, rejection of a non-16-bit or stereo WAV, mp3
  passthrough.
- Preflight: returns the rate; a no-op on the hosted and fake providers;
  `_process_one` with a dead server raises with **no scriptwrite call and
  manifest blocks untouched** (strict surface 2); a bed whose rate differs
  from preflight's fails there with the bed-rate message, also before spend.
- `emcee voice --fresh` with a dead server: the clip is still on disk, the
  manifest untouched, no scriptwrite call.
- No fallback (strict surface 1): `run`, `voice` and `say --presenter`, each
  with an `mlx_audio` pin and a dead server, raise the error and never
  construct `VoxtralProvider`.
- Config: `[tts] backend = "mlx_audio"` is rejected; `[tts.mlx_audio]` is
  strict and its defaults hold; a missing mlx model is an error; the live
  config shape loads unchanged.
- Presenter validation matrix (the rules in section 1), including strictness
  (an unknown key is a load error), empty-string `tts`/`tts_model` and a
  `fake` pin rejected.
- Resolution: presenter pin > house; model pin > configured model > provider
  default; a non-house hosted pin ignores `[tts] api_key`; an ElevenLabs
  clone is rejected whether pinned or inherited.
- A two-presenter `emcee run` with different backends gets one provider per
  package and distinct cache keys.
- `emcee run --dry-run`: unpinned output byte-identical; a pinned presenter
  shows its backend/model; an invalid presenter file shows `[invalid ...]`
  and the listing completes.
- `presenter edit`: each flag, set/clear conflicts, `--voice` with
  `--voice-clone` rejected, `--voice` clearing the clip and transcript, a
  changed clip clearing the transcript, `--transcribe` confirm/decline (with
  `response_format=json` and the Whisper unload), absolute clip path stored,
  and file-untouched-on-reject.
- One opt-in `live` test against a running server.

## Out of scope

Managing the server process; resampling; house voice on `mlx_audio` (needs
`[tts] voice_clone_text` and `say --clone-text`); recording backend/model in
the manifest's `dj_audio` block (the presenter file already says, unless
re-pinned later); running multiple mlx models concurrently; F5-TTS (not
servable by mlx-audio); any llama change; cutting the release.

## Unverified premises

- **Memory headroom** of a resident Qwen 1.7B on the 16 GB mini during a real
  run: the bake-off's `peak_rss_gb` of 12.0 looks capped. Test with
  `footprint` on the warm server.
- **Unseeded production quality:** the babble/truncation rate is unknown.
  Test: ~50 unseeded sentences, flagging duration-per-character outliers.
- **Presenters other than Phil:** quality is unmeasured. Test: one `say` per
  presenter.
