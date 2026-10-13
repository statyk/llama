### Spec Compliance
- ✅ Spec compliant. `verify.py` and `test_verify.py` match the brief byte for byte (I diffed them against the brief's code blocks). The edits to `quality.py`, `tts/__init__.py`, `mlx_helpers.py` and `test_mlx_wiring.py` match Steps 1, 5 and 6 (diff lines 52-63, 89-109, 164-213, 371-443, 487-566).
  - No STT model id is hard-coded: grepping `packages/emcee/src` for whisper or parakeet finds nothing. The STT model comes only from `[tts.mlx_audio] stt_model` (`tts/__init__.py` `_quality`, diff line 62).
  - Wire contract: the transcription request uses `clip.wav`, `model`, `language=en` and `response_format=json` (verify.py `transcribe`, diff 301-304). Unload is `DELETE /v1/models?model_name=` (diff 325). Both match global-constraints line 11.
  - Plan review focus (3), an all-numbers sentence: there is no division. With n=0, `n - found = 0` is never greater than `max(2, 0)`, so only the length check can fail it (diff 278-284). It is pinned by `test_all_number_sentence_passes`.
  - "Never silently skipped": both preflight branches (mlx: one `preflight_wav` take under `_retrying`; hosted: the bundled clip) sit in `QualitySpeech.preflight` (diff 179-205). The only call site, `cli._process_one`, calls it before the `--fresh` unlink, the manifest clear and `process_package` (cli.py:248-266, checked because it is the strict-surface-2 ordering). `emcee run` (cli.py:404) and `emcee voice` (cli.py:495) both go through `_process_one`.
  - Config guarantees `stt_model` whenever backends is non-empty (config.py:134), so `_quality` can read `mlx.stt_model` without a check.
  - The controller's addition is present: `_assert_nothing_written_for` in test_quality.py (diff 582-589) is called in both double-failure tests (diff 599, 618).
- ⚠️ Cannot verify from this diff: the bundled clip `emcee/data/preflight_en.wav` (created in Task 12). Packaging will pick it up once it exists: `packaging/emcee.spec:75` collects `emcee.data` and hatchling includes package files. Until then, a hosted backend listed in `[tts.verify]` fails closed at preflight, which is acceptable because verification is off by default.

### Strengths
- The error taxonomy is right:
  - A transcription request that fails (connection error, non-200, non-JSON, missing `text`) is always a plain `SpeechError`, never a pass and never a retried `SpeechDefect` (verify.py diff 305-318).
  - A failed hosted preflight is turned into a `SpeechError` that points at `stt_model` (diff 201-205).
  - `SpeechBlocked` is a sibling of `SpeechDefect`, not a subclass (provider.py:10, :44), so a content-filter block is still never retried identically.
- Wrapping voxtral and elevenlabs in `QualitySpeech` is safe. I checked this because wrapping can break type checks and attribute access: src has no `isinstance(..., <Provider>)` checks, and the only attributes read off a speech provider are `synthesize`, `preflight`, `close`, `voice` and `model`, all of which the wrapper forwards.
- Both hosted backends support `fmt="wav"`. ElevenLabs wraps its PCM as 16-bit mono WAV (elevenlabs.py:76-83). Voxtral passes `response_format` through (voxtral.py:93), and its chunked path already requires 16-bit (audio.py:138).
- `preflight()` on hosted providers does nothing (voxtral.py:148, elevenlabs.py:86), so the hosted verified preflight costs no hosted spend.
- `close()` closes the verifier inside `finally` (diff 209-213).
- The mlx verified preflight reuses the single `preflight_wav` take instead of synthesizing twice. `test_verified_mlx_preflight_transcribes_its_one_take` pins this by checking the exact WAV bytes sent to STT.
- The config-only failure matrix (8 cases × 2 drivers) asserts all four strict-surface-2 effects: no LLM task, no hosted construction, manifest unchanged, `--fresh` clip still present.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **verify.py:58 (diff 281): a 1-2 word sentence can never fail the "too few words heard" check.** `MISS_FLOOR = 2` with `n ≤ 2` means `n - found ≤ 2` always passes. I measured it: `transcript_problem("Thanks.", "")` returns `None`, while the 3-word "Thanks for listening." fails. Chunking is on by default and verifies each sentence, so a silent hosted clip of a short sentence like "Thanks." or "Enjoy." passes verification. mlx is covered separately by the runaway guard, which rejects an empty clip. The thresholds are explicitly INTERIM, so this is input for Task 12 rather than a fix now. Task 12's calibration should decide on short sentences explicitly, for example requiring `found ≥ 1` when `n ≥ 1`. `test_an_empty_transcript_fails_a_real_sentence` only covers a long line.
2. **quality.py `_attempt` (diff 177) feeds a hosted WAV to `mlx_audio.wav_to_mp3` with no bit-depth check and no `wave.Error` handling.** `wav_to_mp3` (mlx_audio.py:34-38) was written for mlx output, which `_read_wav` has already checked is 16-bit. This task extends it to hosted WAVs. A non-16-bit WAV would reach lameenc unchecked: verification would pass on the original WAV, and then the encoded MP3 could be garbage. A malformed WAV would raise a raw `wave.Error` instead of a `SpeechError`. audio.py's own WAV paths do check (audio.py:138, :183). This is latent today, because Voxtral's chunked path in production already shows it returns 16-bit and ElevenLabs is wrapped as 16-bit. Fix: check `getsampwidth() == 2` in `wav_to_mp3` and convert `wave.Error` to `SpeechError`.
3. **test_verify.py `test_hosted_preflight_passes_on_a_good_transcription`: the `server.speech_bodies == []  # no hosted spend` assertion proves nothing.** Hosted traffic never goes through the mock mlx server, so the assertion holds even if Voxtral were asked to synthesize. Today the claim really rests on `VoxtralProvider.preflight` doing nothing. To pin it, patch `VoxtralProvider.synthesize` to raise or count, as `_forbid_hosted` does in test_mlx_wiring. The brief mandated this test verbatim.
4. **test_quality.py:582-589 (diff): the sidecar half of `_assert_nothing_written_for` is mostly skipped.** In both tests the failing segment is `set1-intro`, the first segment of a package with `voiced=False`, so `segments.json` usually does not exist yet and the `if sidecar.exists()` branch never runs. It would still catch code that wrote the sidecar before rendering, as the implementer says. Failing the second segment instead would always exercise the branch: give `set1-intro` a good take and then two defects.
5. **Coverage:** no test lists `elevenlabs` in `[tts.verify]`. The voxtral tests exercise the same `_quality` branch, so the risk is low.

### Assessment
**Task quality:** Approved
**Reasoning:** The implementation matches the brief verbatim and meets the strict surfaces, including STT preflight for both provider kinds before any spend, no hard-coded STT model, and the all-numbers case. The remaining items are a calibration input for Task 12, a latent bit-depth check in a helper this task now uses for hosted audio, and some test assertions that are weaker than their comments claim.
