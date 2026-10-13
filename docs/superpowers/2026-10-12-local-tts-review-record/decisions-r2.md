# Round-2 decisions (circuit-breaker: preflight drew Important findings twice → simplify)

Apply every item; remove every trace of removed items. Do NOT touch `--transcribe`/`stt_model` in this pass (pending the operator's decision) except item 14.

## Narrow the mlx surface (removals)

1. **`mlx_audio` is clone-only.** `tts = "mlx_audio"` requires `voice_clone` (and its transcript); a preset `voice` with an mlx pin is a validation error. Remove the preset branch from the request body, from preflight's "catches a preset voice on a Base model" claim (false: the server's continuous-batch path returns 200 in an unconditioned voice), and from tests.
2. **The mlx provider always requests WAV from the server.** For `fmt="mp3"` it encodes locally with emcee's existing `_encode_mp3` (`audio.py`). Remove the mp3 passthrough and every mention of the server needing ffmpeg (runbook `PATH (ffmpeg)` item included); the server then needs no ffmpeg at all.
3. **`tts_model` is allowed only with `tts = "mlx_audio"`.** Hosted pins (`voxtral`/`elevenlabs`) pin the backend only; their model is the provider default (or `[tts] model` when the pinned backend is the house backend). Remove the hosted-model branch of the resolver and its tests. Reword Stakes (2): it covers mlx-specific configuration failures (server down, model unloadable, missing/blank transcript); a hosted pin's configuration errors (e.g. a bad env key) keep today's timing — state that as a limitation.

## Preflight — the simplest rule

4. Replace the Preflight bullet with exactly this rule: `preflight() -> None` is on the `SpeechProvider` protocol, called unconditionally; a no-op on hosted and fake providers. For `mlx_audio` it synthesizes one fixed sentence of at least 20 characters (e.g. "Good evening, and welcome to the show.") with `max_tokens = 200`, and requires the response to be a 16-bit mono **24 kHz** WAV, else `SpeechError`. Rationale for 24 kHz: house beds are always 24 kHz (`tts/bed.py`), so this replaces the bed-rate comparison and needs no bed loading; a non-24 kHz model is unsupported (document it as a limitation). Remove "preflight returns its sample rate" and the bed-rate comparison.
5. Placement: in `_process_one`, preflight runs right after `speech_for` **inside** the existing `try/finally speech.close()` (move the `try` up), before the `--fresh` unlink and before `rewrite_manifest(..., None, None)`. Keep the existing `--fresh` move.

## Errors — name the classes

6. `httpx.ConnectError`: one retry after a short delay, then `SpeechError` "mlx-audio server not reachable at <url> (is the launchd service running?)". `httpx.RemoteProtocolError`, `httpx.ReadError`, `httpx.ReadTimeout`, a non-WAV or empty body: `SpeechError` pointing at the server log, **no retry** (generation failures after the 200 arrive as an aborted chunked body). Non-200: fail at once with the server's text. Fix the §5 test to raise `RemoteProtocolError` from the transport rather than modelling an "empty 200".

## Transcript integrity

7. The transcript is a **required** factory argument (`clone_text`, no default), like backend/model. The mlx provider raises `SpeechError` on a clone whose `ref_text` is empty after `.strip()`. Presenter validation strips whitespace before its non-empty check. Test that `ref_text` reaches the request body on run, voice and `say --presenter`.

## Tests that can actually fail

8. The no-fallback tests (strict surface 1) run with house backend `voxtral` (env key set, a transport that fails the test if called), an mlx pin and a dead server, and assert no provider other than the mlx one is constructed or called. The strict-surface-2 tests use an already-voiced package and compare the manifest's bytes and the `--fresh` clip's presence before/after.

## Dry-run and strict surface 3

9. `tests/test_run_cmd.py:545-558` writes an empty case-mismatched `BILLYG.toml`; under the new loading it would show `[invalid …]`. Decision: that test is updated to a valid file; dry-run's presenter loading uses the same case-insensitive lookup as `_presenter_file_exists` (`cli.py:276-283`). Drop the citation as proof of byte-identity.
10. Stakes (3): list the intended differences for an unpinned station explicitly — a failed `voice --fresh` keeps clips; a presenter file with an unknown key now fails to load (no live file has one); `presenter add` stores `voice_clone` as an absolute path. `presenter list`/`show`/dry-run output changes only for pinned presenters.

## Runbook and evidence

11. Runbook rollback line: to unpin Phil, `emcee presenter edit phil --clear-tts --clear-tts-model --voice-clone ~/.emcee/samples/phil.wav` (his aired Voxtral reference); unpin before downgrading the binary.
12. Runbook pins the evaluated `mlx-audio` version (0.5.8): its server-side sampling defaults (temperature, top_k, top_p) define the evaluated voice and emcee does not send them.
13. Evidence fixes: every WER-scored take was **unseeded** (only extra 1.7B/0.6B takes used seed 42) — correct the "server was seeded" sentence; `max_tokens = 4000` is the value the bake-off sent, not a measurement. Note other presenters' clips are 21–30 s 48 kHz stereo, while Phil's evaluated reference was a 12.9 s excerpt.
14. Unverified premises: add — the ~50-sentence unseeded quality check is a **gate before Phil goes live** (runbook step), not just a note; stdlib `wave` was verified against mlx-audio's own WAV writer (`audio_io.write`, 24000 Hz/mono/16-bit) but not yet against a live server response (one-request test at implementation); a mistyped model id under `HF_HUB_OFFLINE=1` should come back as a non-200 before streaming (one-request test).
