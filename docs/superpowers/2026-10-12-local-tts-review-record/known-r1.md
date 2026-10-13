# Known findings after round 1 (issue → how the spec now handles it)

1. GET reachability probe missed model-id typos, unloadable models, preset-on-Base, non-WAV bodies → replaced by `preflight()`: one tiny real synthesis in the Protocol, called unconditionally in `_process_one` before the manifest clear; returns the rate, checked against an active bed.
2. `emcee voice --fresh` unlinked clips before any check → unlink moved inside `_process_one` after assignment/speech_for/preflight.
3. `Presenter` was a permissive BaseModel; older binaries/typos silently drop pins → strict base; runbook rule "install the release before pinning".
4. `say --presenter` bypassed `speech_for` → routed through the resolver; factory backend/model params required with no defaults; no-Voxtral-constructed tests for run/voice/say.
5. Clip change kept a stale transcript → `--voice-clone` clears `voice_clone_text` unless a new one is given; `--voice` clears both; `--voice` + `--voice-clone` is a usage error.
6. House voice / `say --clone` on mlx had no transcript source → `[tts] backend = "mlx_audio"` is a config error; out of scope.
7. Hosted `[tts.voxtral]`/`[tts.elevenlabs]` subtables + duplicate-key logic over-built → removed; `[tts] model/api_key` = house backend only; a non-house hosted pin uses its env var only.
8. Float/stereo conversion and 24 kHz rejection over-built → removed; provider checks width 2 + mono; rate checked only against a bed in preflight.
9. Streaming errors arrive after a 200 → empty/unparseable 200 is SpeechError pointing at the server log; retry once on connection errors only (not read timeouts, not 5xx).
10. Server default max_tokens 1200 truncates → `max_tokens = 4000` sent explicitly.
11. Dry-run would change unpinned output and abort on a bad file → backend/model shown for pinned presenters only; `[invalid presenters/x.toml]` inline.
12. Empty-string pins fell back silently; `fake` pin put silence on air → rejected.
13. ElevenLabs clone check only on house voice → applies to any clone resolving to elevenlabs.
14. `--transcribe` default ndjson; Whisper stayed resident → `response_format=json`; `DELETE /v1/models` after.
15. Clip path relative to emcee's cwd → stored absolute.
16. Runbook gaps (launchd cwd/PATH/host/HF_HUB_OFFLINE; models resident until restart) → §4.
17. Evidence errors (WER swapped; "every candidate 24 kHz"; clip-format question; example path) → corrected.

## Removed by the revision
GET probe; hosted subtables + duplicate-key rule; float32/stereo conversion; 24 kHz rejection; house voice on mlx; `fake` as a pin; old retry rule (transport/timeout/5xx).
