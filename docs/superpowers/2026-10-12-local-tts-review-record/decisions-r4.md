# Round-3 review decisions

Apply every item; remove every trace of what is removed. Keep it tight — several items REPLACE text rather than add.

## Verification transport

1. **Verification always works on WAV.** The verification layer always asks its inner provider for `fmt="wav"`, verifies the PCM, and if the caller asked for mp3 encodes it locally with `audio._encode_mp3`. Delete the claim that the server decodes MP3 (its byte-sniffer does not recognise lameenc's 24 kHz `\xff\xf3` header — measured on delivered clips). Note: this changes the Voxtral unchunked-no-bed path only when Voxtral is listed (verification on), so strict surface "unchanged when verification off" holds.
2. Uploads to `/v1/audio/transcriptions` always use multipart filename `clip.wav` (the server picks its temp-file format from the suffix and needs ffmpeg for `.mp3`; httpx's default name `upload` maps to `.mp3`). Always send `language = "en"`. Test the request shape (filename, language, `response_format=json`).
3. The comparison drops number-bearing tokens (digits, and spelled-out number words) from both sides before comparing — the check is for gross mismatch, and number formatting is open-ended. Remove the "numbers and ordinals in either form" normalization.

## One retry owner, one wrapper location

4. The mlx provider's runaway guard raises a typed `SpeechDefect` (a `SpeechError` subclass) and **never retries itself**. One **quality layer** owns the single retry for both the guard and verification: it wraps every `mlx_audio` provider (guard only, when verification is off) and every provider whose backend is listed in `[tts.verify] backends`. Per `synthesize` call: at most two synthesis attempts; any second failure of either check raises `SpeechDefect`. On the unchunked path the retried unit is the whole segment — correct "for the failed sentence only" accordingly.
5. The quality layer is applied **inside `speech_provider_for`** — the single construction point every path uses (`speech_for`, and every `ad_hoc_speech` branch). It delegates `preflight()` and `close()` and passes `SpeechBlocked` through unchanged. Tests: `say` with no flags, `say --clone` and `say --presenter` each return a wrapped provider when the backend is listed.
6. `_synthesize_dj_audio` annotates a `SpeechDefect` with `.segment`, as it already does for `SpeechBlocked` (`audio.py:342-344`).
7. `_locate_block`'s throwaway probes go through the layer like any synthesis. Document as a limitation: on the rare path (Voxtral listed + unchunked + a content block), a probe that double-fails verification surfaces as `SpeechDefect` instead of the located block.

## Runaway guard correctness

8. Add the invariant: **audio whose duration is within a small margin of the cap's duration is always a guard failure** (a capped runaway can otherwise pass the long-duration check). Calibration asserts it on a synthetic cap-length clip and includes Chatterbox's short-babble case ("Here is Morning Dew." → ~10 s) alongside the Qwen 0.6B set1 runaway.
9. The cap converts tokens to seconds via the model's codec frame rate, so guard constants are **per model**. emcee carries a small table of calibrated mlx models (initially Qwen3-TTS-12Hz 1.7B Base: frame rate 12.5, plus the calibrated constants). Resolving `mlx_audio` to a model not in the table is a configuration error ("model not calibrated for the runaway guard"), detected at resolution, before spend. State it as the cost of a safe guard; adding a model means a calibration run.
10. Calibration population additionally includes ~10 Voxtral sentences (if `"voxtral"` may be listed) and a few whole segments (unchunked path), and records Whisper repetition-loop occurrences in the evidence doc.

## House on mlx must not move presenters

11. A presenter **never inherits `mlx_audio`**: with `[tts] backend = "mlx_audio"`, an unpinned presenter is a resolution error ("pin `tts` explicitly: the house backend is mlx_audio") raised before spend. The house mlx voice therefore only affects packages with no presenter and `emcee say` without `--presenter`. Runbook: "to move the house voice to mlx, first pin every presenter (e.g. `--tts voxtral`)". The live config's `[assign] default = "roydemure"` means moving Roy is a presenter pin, not a house change — say so. Factory checks for a resolved-mlx house: preset voice or blank transcript → error naming `[tts] voice`/`voice_clone_text`.
12. Dry-run: a presenter whose resolution fails (including item 11 and a missing mlx model) shows `[unresolved: <message>]` inline and never aborts the listing.

## Preflight of the STT path

13. When verification applies: for an mlx inner provider, preflight runs its own synthesized sentence through the **full verification comparison** (it must pass, not merely return 200). For a hosted inner provider, preflight transcribes a small bundled speech clip (a ~2 s WAV of a fixed sentence, shipped as an emcee package resource) and requires it to pass the comparison against that sentence. Replace "only a successful response is required".

## Smaller

14. Stakes: state the cache exception explicitly — clips already in the render cache (including ones rendered before verification was enabled) are reused unverified.
15. `[tts.mlx_audio] model` is required only when something resolves to `mlx_audio`, checked at resolution (before the manifest clear); a `[tts.mlx_audio]` holding only `stt_model` (Voxtral-only verification) is valid.
16. `presenter edit` merges with `Presenter.model_validate({**old.model_dump(), **changes})` (never `model_copy(update=…)`, which skips validators — an idiom emcee already uses elsewhere, `process.py:184`). Test that an invalid merged edit leaves the file untouched via the merge path.
17. `--transcribe` sends `DELETE /v1/models?model_name=<stt_model>` afterwards **only when `[tts.verify] backends` is empty** (otherwise the STT model is expected resident).
18. Phil's go-live uses the evaluated transcript: the runbook copies `~/tts-bakeoff/refs/phil_ex.wav` and `phil_ex.txt` into `~/.emcee/samples/` and runs `emcee presenter edit phil --tts mlx_audio --voice-clone ~/.emcee/samples/phil_ex.wav --voice-clone-text "$(cat ~/.emcee/samples/phil_ex.txt)"`. `--transcribe` remains for new presenters.
19. Runbook: download the TTS and STT models once while online, before enabling `HF_HUB_OFFLINE=1`.
20. Unverified premises: update — a loadable `stt_model` returning non-empty json text (test: one request with filename `clip.wav`, `language=en`); Whisper on short clips with foreign venue names (test: the De Doelen sentence with `language=en`); memory with TTS + STT + `claude -p` resident. Remove "mistyped model id is a non-200 before streaming" (settled by source: `_preflight_model_load` runs before the `StreamingResponse`, `server.py:244-279`).
