# Round-1 decisions for 2026-10-12-local-tts-presenter-pinning-design.md

Apply every item. "Remove" means remove every trace (tables, examples, tests list, docs list, out-of-scope).

## A. Preflight (replaces the GET reachability probe)

1. Replace the "Reachability" bullet in §2 with a **preflight**: `preflight()` becomes part of the `SpeechProvider` Protocol and is called **unconditionally** (no `getattr`) — a no-op on voxtral/elevenlabs/fake; test doubles gain the method. For `mlx_audio` it is one tiny real synthesis ("Good evening.") with the resolved model, `ref_audio`/`ref_text` (or `voice`), `fmt="wav"`; the response must parse as WAV with sample width 2 and mono, and preflight returns its sample rate. This catches: server down, wrong/unknown model id (404), model not loadable (500), preset voice on a Base model, a non-WAV/empty body — and absorbs the cold model load. Costs a few seconds per package and nothing in money.
2. `_process_one` calls `speech.preflight()` immediately after `speech_for` and before `rewrite_manifest(pkg, dj_notes=None, dj_audio=None)`. If a bed is active and preflight's rate differs from the bed's rate, fail there with the existing bed-rate message (so that failure also lands before LLM spend).
3. **`emcee voice --fresh`**: today `voice_cmd` unlinks the `--fresh` clips before `_process_one` (`cli.py:448-462`). Move the unlink inside `_process_one`, after assignment + `speech_for` + preflight succeed and before the manifest clear. This also closes the same pre-existing gap for other config-only errors. State it under strict surface 2. Add a test: dead server + `--fresh` → clip still on disk, manifest untouched, no scriptwrite call.
4. Runbook sets `HF_HUB_OFFLINE=1` on the server so a mistyped-but-real model id fails fast instead of starting a multi-GB download.

## B. Pins can never be silently ignored

5. `Presenter` moves onto emcee's strict base (`extra="forbid"`, the same base `config.py` uses). All five live presenter files use only known keys. A typo'd key (`tts_modle`) is then a load error.
6. Runbook rule: **install the new emcee release before pinning any presenter** — an older binary drops `tts`/`tts_model` and would voice the presenter on Voxtral from the newly edited clip.
7. `tts` and `tts_model` reject empty strings. `fake` is **not** an allowed presenter pin (tests select `fake` through config); allowed pins: `voxtral`, `elevenlabs`, `mlx_audio`.
8. `speech_provider_for`'s backend and model parameters are **required, no defaults**, so an unmigrated call site fails loudly rather than falling back to `[tts] backend`.
9. Correct the false claim that `say` honours pins "for free": `ad_hoc_speech`'s `--presenter` branch calls `speech_provider_for` directly (`process.py:139-145`). It must route through the same resolver as `speech_for`. Tests: run, voice, and `say --presenter` each with an mlx pin and a dead server — assert the error and that `VoxtralProvider` was never constructed.
10. The ElevenLabs-clone check in the factory applies to **any** clone that resolves to elevenlabs (pinned or inherited), not only the house voice.

## C. Transcript integrity

11. In `presenter edit`, changing `voice_clone` clears `voice_clone_text` unless a new one (`--voice-clone-text` or `--transcribe`) is given in the same command; setting `--voice` clears both `voice_clone` and `voice_clone_text`; `--voice` together with `--voice-clone` is a usage error. Validation then forces a fresh transcript for mlx pins.
12. `--transcribe`: specify `response_format=json` on `/v1/audio/transcriptions` (the server's default is ndjson), and after transcribing send `DELETE /v1/models?model_name=<stt_model>` so Whisper does not stay resident beside the TTS model. Keep `[tts.mlx_audio] stt_model`.
13. `presenter add`/`edit` store `voice_clone` as an absolute, resolved path (the server reads it with its own working directory).

## D. Narrowing: house voice and config subtables

14. **The house voice cannot use `mlx_audio` in this work.** `[tts] backend = "mlx_audio"` is a config error with a message saying to pin presenters instead. Reason: the house clip and `say --clone` have no transcript source, and Qwen without `ref_text` silently degrades. Add to Out of scope: "house voice on mlx_audio (needs `[tts] voice_clone_text` and `say --clone-text`)". Consequently `emcee say --clone`/`--voice` (no presenter) always use the house hosted backend, as today.
15. **Remove the `[tts.voxtral]` and `[tts.elevenlabs]` subtables and the duplicate-key error logic.** New rule: `[tts] model`/`api_key` apply to the house backend only (which is always hosted, per 14), exactly as today. A presenter pinned to a hosted backend that is NOT the house backend takes its key from that backend's env var only (`MISTRAL_API_KEY` / `ELEVENLABS_API_KEY`) — never from `[tts] api_key` — and its model from `tts_model` or the provider's built-in default. Missing key → the existing "API key missing" error, which fires at provider construction (before spend). Only `[tts.mlx_audio]` is added.
16. `[tts.mlx_audio]`: `url` defaults to `http://127.0.0.1:8000` (state it); `model` has no default (unchanged); `timeout_s` default 600; `stt_model` optional.

## E. Provider simplifications and error model

17. Audio contract: **remove** the float32→int16 and stereo→mono conversion and the provider's 24 kHz rejection. The server always writes 16-bit PCM WAV (`mlx_audio/audio_io.py:532-570`), verified readable by stdlib `wave` (24000 Hz, mono, width 2). The provider checks sample width 2 and mono and raises `SpeechError` otherwise; rate is checked only against the bed (item 2). Remove the "To confirm at implementation: the server's WAV encoding" item.
18. Errors: `/v1/audio/speech` streams, so most generation failures arrive after a 200 as an empty/truncated body. Rules: a non-200 fails at once with the server's error text; an empty or unparseable 200 body is a `SpeechError` whose message points at the server log; retry **once on connection errors only** — not on read timeouts, not on 5xx (a timed-out request keeps running server-side and a retry queues behind it; model-load 500s are deterministic).
19. The request sends `max_tokens = 4000` explicitly (the bake-off's measured value; the server default 1200 ≈ 96 s silently truncates long unchunked segments).

## F. Dry-run

20. `emcee run --dry-run`: print backend/model only beside **pinned** presenters, so unpinned output stays byte-identical (`tests/test_run_cmd.py:558`). An invalid presenter file shows `[invalid presenters/<id>.toml]` on its row like the existing `[missing ...]` note, never aborting the listing. Dry-run does not preflight.

## G. Runbook, evidence, examples

21. Runbook (launchd plist): `WorkingDirectory` (or `--log-dir`; the server's startup `mkdir("logs")` is cwd-relative and launchd's cwd is `/`), PATH including `/opt/homebrew/bin` (ffmpeg, needed for mp3 responses), `--host 127.0.0.1`, a restrictive `--allowed-origins` (default is `*`), `HF_HUB_OFFLINE=1`. Memory: the server caches every model it has served **until restart** (or `DELETE /v1/models`), not just for one run.
22. Correct the evidence table: Whisper WER is **Voxtral 2.3%, Qwen3-TTS 1.7B 1.9%** (`~/tts-bakeoff/out/*.asr.json`). Add one sentence: WER measures intelligibility, not naturalness — the operator judged Qwen a downgrade by ear. Note the bake-off's server was seeded (production will not be) and that each configuration had only 1–3 takes on one presenter.
23. Replace "every candidate measured is 24 kHz" with: Qwen3-TTS outputs 24 kHz per its model config (`qwen3_tts/config.py`); the bake-off resampled every output, so other models' native rates were not observed.
24. Reference clips: remove the "measured at implementation" paragraph; state that the server decodes, resamples and down-mixes reference clips itself (`mlx_audio/utils.py` `load_audio`), so 48 kHz stereo clips such as `phil.wav` are accepted. The worked example uses the evaluated 12.9 s 24 kHz mono excerpt, which the runbook copies from `~/tts-bakeoff/refs/phil_ex.wav` into `~/.emcee/samples/phil_ex.wav` first.
25. Testing section: update to match all of the above (preflight incl. bed-rate mismatch and `--fresh`; strict Presenter; empty-string/`fake` pins rejected; no-Voxtral-constructed assertions for run/voice/say; transcript cleared on clip change; empty-200 and connection-only retry; max_tokens in body; dry-run byte-identical unpinned; house `mlx_audio` rejected; non-house hosted pin ignores `[tts] api_key`). Remove tests for removed mechanisms (subtable duplicate-key, float/stereo conversion, 24 kHz rejection).
26. Unverified premises — add a short closing section listing: memory headroom of a resident Qwen 1.7B on the 16 GB mini during a real run (bake-off `peak_rss_gb` 12.0 looks capped; test with `footprint` on the warm server); unseeded production quality (babble/truncation rate unknown; test: ~50 unseeded sentences, flag duration-per-character outliers); quality on presenters other than Phil (test: one `say` per presenter).
