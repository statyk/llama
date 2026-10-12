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
(2) an `mlx_audio` configuration failure (server down, model not loadable,
missing or blank transcript) must be detected **before** any LLM spend,
**before** `_process_one` clears a package's manifest blocks, and **before**
`emcee voice --fresh` deletes the clips it was asked to re-roll, so it can
never take a broadcast-ready package off air or discard its audio (a hosted
pin's configuration errors, such as an invalid API key, keep today's timing);
(3) with no pins set, existing configs and presenter files behave as today,
except: a failed `emcee voice --fresh` keeps its clips; a presenter file with
an unknown key fails to load (no live file has one); `presenter add` stores
`voice_clone` as an absolute path. `presenter list`/`show` and dry-run output
change only for pinned presenters.

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
a downgrade by ear. Every WER-scored take was unseeded (only extra 1.7B/0.6B
takes used seed 42), and each configuration had only 1–3 takes on one
presenter. Phil's evaluated reference was a 12.9 s excerpt; the other
presenters' clips are 21–30 s 48 kHz stereo.

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
- `[tts] model`/`api_key` apply to the house backend only, so the live config
  (`[tts] api_key` set, `backend` unset = voxtral) behaves as today.

**Resolution:** a new pure function resolves `(backend, model)` for a
presenter. The backend is `presenter.tts or config.tts.backend`. For
`mlx_audio` the model is `presenter.tts_model`, else `[tts.mlx_audio] model`,
else a configuration error. For the house backend it is `[tts] model`, else
the provider default; for any other hosted backend, the provider default.

A presenter pinned to a hosted backend that is **not** the house backend takes
its API key from that backend's env var only (`MISTRAL_API_KEY` /
`ELEVENLABS_API_KEY`), never from `[tts] api_key`. A missing key is the
existing "API key missing" error, which fires at provider construction, before
any spend; for such a pin it names only the env var.

`speech_provider_for` takes the resolved backend, model and transcript
(`clone_text`: the presenter's `voice_clone_text`, or `None`) as **required**
arguments with no defaults, instead of reading `config.tts.backend` itself, so
an unmigrated call site fails loudly rather than falling back to `[tts]
backend` or dropping the transcript. `speech_for` (runs/voice) and
`ad_hoc_speech`'s `--presenter` branch (`emcee say --presenter`,
`process.py:139-145`, which today calls `speech_provider_for` directly) both
route through the resolver; the house voice resolves from `[tts]` as today.
The factory's ElevenLabs-clone check applies to **any** clone that resolves to
`elevenlabs`, pinned or inherited. The render cache keys on `speech.voice` and
`speech.model`, so a re-pinned presenter never reuses another backend's clips.

`emcee run --dry-run` prints the resolved backend/model beside **pinned**
presenters only, so pins can be audited before any spend. It loads presenter
files with `_presenter_file_exists`'s case-insensitive lookup
(`cli.py:276-283`); a file that fails to load shows `[invalid
presenters/<id>.toml]` on its row, like `[missing ...]`, and never aborts the
listing. Dry-run does not preflight.

### 2. The `mlx_audio` provider (`tts/mlx_audio.py`)

- **Request:** `POST {url}/v1/audio/speech`, JSON body `model`, `input`,
  `response_format = "wav"`, `max_tokens = 4000`, `ref_audio` (the clip's
  absolute path) and `ref_text`. `max_tokens` is sent explicitly because the
  server's default of 1200 (≈ 96 s) silently truncates long unchunked
  segments; 4000 is the value the bake-off sent. At construction the clip is
  checked readable and a `ref_text` that is empty after `.strip()` is a
  `SpeechError`, so a bad clone fails before synthesis.
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
`phil_ex.wav` is the evaluated 12.9 s 24 kHz mono excerpt (the runbook copies
it from `~/tts-bakeoff/refs/` first).

`emcee presenter add` gains `--tts`, `--tts-model`, `--voice-clone-text` (and
`--transcribe`), stores `voice_clone` as an absolute path the same way, and
`presenter list`/`show` display the pin, so every presenter field is
CLI-editable (`[assign]` stays the only hand-edited emcee config).

**Reference clips:** the server decodes, resamples and down-mixes reference
clips itself (`mlx_audio/utils.py` `load_audio`), so 48 kHz stereo clips such
as `phil.wav` are accepted; emcee does not convert them.

### 4. Docs

- A runbook section:
  - **Install the new emcee release before pinning any presenter** — an older
    binary drops `tts`/`tts_model` and would voice the presenter on Voxtral
    from the newly edited clip.
  - A launchd agent running `mlx_audio.server` from a dedicated venv with
    `mlx-audio` pinned to the evaluated 0.5.8 (its server-side sampling
    defaults — temperature, top_k, top_p — define the evaluated voice, and
    emcee does not send them), bound to `127.0.0.1`, with a working directory
    that works under launchd, and `HF_HUB_OFFLINE=1` so a mistyped model id
    fails fast instead of starting a download; how to stop/start it.
  - Memory: the server keeps every model it has served resident until restart,
    so presenters pinned to different mlx models hold all of them.
  - Before moving Phil: copy `phil_ex.wav` (section 3) and pass the
    ~50-sentence quality check (Unverified premises).
  - Rollback: to unpin Phil, `emcee presenter edit phil --clear-tts
    --clear-tts-model --voice-clone ~/.emcee/samples/phil.wav` (his aired
    Voxtral reference); unpin before downgrading the binary.
- `emcee config init`'s template gains `[tts.mlx_audio]`, commented.
- CLAUDE.md: the emcee paragraph (backends, pinning, `presenter edit`, the
  house voice staying hosted), and the "presenter voice clones are
  Voxtral-only" statement, which becomes false.

### 5. Testing (offline, deterministic)

- Provider against `httpx.MockTransport`: request body (`ref_audio`,
  `ref_text`, `response_format = "wav"`, `max_tokens = 4000`); a non-200
  failing at once with the server's text; a `RemoteProtocolError` from the
  transport as a `SpeechError`, not retried; one retry on `ConnectError`,
  none on `ReadTimeout`; a blank `ref_text`, a non-16-bit or a stereo WAV
  rejected; local mp3 encoding for `fmt="mp3"`.
- Preflight: a no-op on the hosted and fake providers; a non-24 kHz WAV
  rejected. Strict surface 2, on an already-voiced package with a dead
  server: `_process_one` and `emcee voice --fresh` raise with no scriptwrite
  call, the manifest's bytes unchanged, and the `--fresh` clip still on disk.
- `run`, `voice` and `say --presenter` each send `ref_text`; with house
  backend `voxtral` (env key set, a transport that fails the test if called),
  an `mlx_audio` pin and a dead server, each raises and constructs or calls no
  provider but the mlx one (strict surface 1).
- Config: `[tts] backend = "mlx_audio"` rejected; `[tts.mlx_audio]` strict
  with its defaults; a missing mlx model an error; the live config loads.
- Presenter validation matrix (the rules in section 1), including strictness
  (an unknown key is a load error), and rejection of empty-string
  `tts`/`tts_model`, a `fake` pin, `tts_model` on a hosted pin, a preset
  `voice` with an `mlx_audio` pin, and a whitespace-only transcript.
- Resolution: presenter pin > house; mlx model pin > `[tts.mlx_audio] model`;
  a hosted pin uses `[tts] model` only when it is the house backend; a
  non-house hosted pin ignores `[tts] api_key`; an ElevenLabs clone is
  rejected whether pinned or inherited.
- A two-presenter `emcee run` with different backends gets one provider per
  package and distinct cache keys.
- `emcee run --dry-run`: unpinned output unchanged; a pin shows its
  backend/model; an invalid file shows `[invalid ...]` and the listing
  completes; a case-mismatched file name still loads (the empty `BILLYG.toml`
  in `tests/test_run_cmd.py:545-558` becomes a valid file).
- `presenter edit`: each flag, set/clear conflicts, `--voice` with
  `--voice-clone` rejected, `--voice` clearing the clip and transcript, a
  changed clip clearing the transcript, `--transcribe` confirm/decline (with
  `response_format=json` and the Whisper unload), absolute clip path stored,
  and file-untouched-on-reject.
- One opt-in `live` test against a running server.

## Out of scope

Managing the server process; resampling, and non-24 kHz mlx models; preset
voices or the house voice on `mlx_audio` (needs `[tts] voice_clone_text` and
`say --clone-text`); recording backend/model in the manifest's `dj_audio`
block (the presenter file already says, unless re-pinned later); concurrent
mlx models; F5-TTS (not servable by mlx-audio); any llama change; cutting the
release.

## Unverified premises

- **Memory headroom** of a resident Qwen 1.7B on the 16 GB mini in a real run:
  the bake-off's `peak_rss_gb` of 12.0 looks capped. Test: `footprint`.
- **Unseeded production quality:** the babble/truncation rate is unknown.
  Test, gating Phil going live: ~50 unseeded sentences, flagging
  duration-per-character outliers.
- **Presenters other than Phil:** unmeasured. Test: one `say` each.
- **Live server responses:** stdlib `wave` was checked against mlx-audio's
  WAV writer (`audio_io.write`: 24000 Hz, mono, 16-bit), not a live response;
  a mistyped model id under `HF_HUB_OFFLINE=1` should be a non-200 before
  streaming. Test: one request each at implementation.
