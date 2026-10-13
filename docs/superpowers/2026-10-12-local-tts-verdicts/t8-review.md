### Spec Compliance
- ✅ Spec compliant. `mlx_audio.py`, the guard math, `SpeechDefect`, the helpers and the test file all match the brief verbatim. The one deviation is helper imports hoisted into the top import block of `tests/mlx_helpers.py:8-12`, and it changes nothing.
  - Before-coding gate checked against the probe doc's Result table (`docs/superpowers/2026-10-12-mlx-audio-probe.md:14-18`):
    - `wave_reads_server_wav` = yes.
    - `nframes_header_matches` = yes, both online and offline.
    - Truncation = 2.0 s at max_tokens 25, which is exactly 25/12.5.
    - `midstream_exception` = `httpx.RemoteProtocolError`, already in `_GENERATION_FAILURES` (`mlx_audio.py:31`).
    - So no STOP condition applies and the tuple needs no change.
  - Wire contract: the body is exactly the six fields (`mlx_audio.py:108-110`), with no sampling params, and `test_context_arguments_are_accepted_and_not_sent` pins it.
  - Identity: `.voice` hashes the stripped transcript (`mlx_audio.py:52,65-66`), which matches the global constraint. Review Focus (2) holds: `test_voice_identity_ignores_surrounding_whitespace_in_transcript` also asserts that the stripped `ref_text` goes on the wire.
  - Absolute ref_audio: `Path(clone_ref).expanduser().resolve()` (`mlx_audio.py:56`). Review Focus (1) holds: `test_ref_audio_is_sent_as_an_absolute_path` uses chdir plus a relative path.
  - Unknown model: there is no 404 keying. Any non-200 raises `mlx-audio returned <status>: <text>` (`mlx_audio.py:125-126`), so the online 404 and the offline 500 are handled identically.
  - No generation retry: only `ConnectError` is retried (`mlx_audio.py:113-118`). `_GENERATION_FAILURES`, any other `HTTPError` and non-200 responses all raise at once. The parametrized test asserts one call and no sleeps.
  - Preflight: the fixed sentence, `max_tokens=200`, and the format and non-empty checks are at `mlx_audio.py:93-101`.
  - `CALIBRATED_MODELS` is still `{}` (`calibration.py:46`, untouched context).
  - Not wired into the factory, which is correct per the controller (Task 9).
- ⚠️ Cannot verify from the diff: that the quality layer (Task 10/11) re-synthesizes `SpeechDefect` once and no more; that `preflight()` runs before the `--fresh` unlink and the manifest clear (Task 9 / cli wiring); that the factory passes `[tts.mlx_audio] timeout_s` through.

### Strengths
- The error taxonomy follows the probe evidence. ConnectError is the only retried class, since nothing reached the server. Mid-stream and timeout failures are never retried because a timed-out request keeps generating server-side. The `except` order is correct: `ConnectError`, then the generation tuple, then a generic `HTTPError` catch-all, so `ConnectTimeout`, `WriteError` and `UnsupportedProtocol` fail closed and are not retried.
- The guard puts the cap check first (`calibration.py:69`), so a capped runaway cannot be mistaken for "long" or pass. The `ModelCalibration` validators (`calibration.py:36-39`) guarantee that `cap - margin > longest`, so the long band always exists.
- Construction rejects a blank transcript and an unreadable or empty clip before any request is made, which keeps them pre-spend.
- The tests exercise real behaviour through `httpx.MockTransport`: the request body, URL normalisation, retry counts and sleep values, and both the WAV and the locally encoded MP3 path. The `_encode_mp3` monkeypatch target matches the real signature at `emcee/audio.py:108` (`(pcm, framerate, channels)`), which I checked because the test's fake would otherwise hide a mismatch.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **The guard accepts a zero-length clip for short text** (`calibration.py:75-77`; plan-mandated math). `shortest = max(0.0, min_s_per_char*n - min_slack_s)` is 0 for any n <= min_slack_s/min_s_per_char, and `seconds < 0` never fires. I ran a focused check with TEST_CAL: `guard_problem(TEST_CAL, "Here is Morning Dew.", 0.0, ...)` returns `None`, so every sentence of 33 characters or fewer accepts silence. "Here is Morning Dew." is the spec's own example of a failure text. A 200 with a valid but zero-frame WAV in `synthesize` would therefore pass. On the chunked path that silently drops a sentence; the unchunked path hands empty PCM to lameenc. Only preflight checks for zero frames (`mlx_audio.py:98`). Nobody has observed this failure mode, and Task 12 measures the real constants, so this is Minor. The fix is a one-line floor in `guard_problem` (for example `if seconds <= 0: return "clip is empty"`), or an explicit Task 12 check that the measured minimum is above 0 for short sentences. Cosmetic in the same spot: for n=34 the reason reads "minimum 0.0s" because 0.02 s rounds to one decimal.
2. **No test sends a `~` clip path** (`test_mlx_audio.py`, Review Focus 1). `expanduser()` is in the code (`mlx_audio.py:56`), but only the relative-path half is pinned. Removing `.expanduser()` would leave the suite green while `~/x.wav` resolves to `<cwd>/~/x.wav` and the server returns a 400. A `monkeypatch.setenv("HOME", tmp_path)` variant would close this.
3. **Implementer concern 1 (ReadError after a prior 500 labelled "generation failed mid-response")**: I agree it is wording only. Named risk: a provider reused across packages, so one package's unhandled 500 poisons the next package's first request. I checked `process.py:122,150,153`: `speech_provider_for` builds a provider per package and the caller closes it, so the stale connection never outlives the package that already failed. Not retrying is still correct, because a reset connection cannot be told apart from a real mid-generation failure. No change needed.
4. **Implementer concern 2 (a float or other non-PCM WAV is reported as "non-WAV body (unknown format: 3)")**: wording only. It fails closed before spend, includes wave's own reason, and the probe confirms the server writes 16-bit PCM. You could tune it by catching `wave.Error` messages that start with "unknown format" and naming 16-bit PCM, but it is not worth a change now.
5. The `_read_wav` docstring (`mlx_audio.py:130-131`) says "counted from the frames actually read, not the header". Because `readframes(getnframes())` is bounded by the header, the claim holds only while the probe's `nframes_header_matches = yes` stands. That is the brief's stated assumption and the probe confirms it, so this is accurate as shipped and worth knowing if the server version changes.

The implementer's reported output is clean: 2741 passed, and the 26 warnings are the pre-existing fork() DeprecationWarnings. The RED step differed from the predicted error only because an earlier import line failed first, so it has the same cause and is acceptable.

### Assessment
**Task quality:** Approved
**Reasoning:** The implementation matches the brief, the wire contract, the identity rule and the probe-derived retry policy exactly, and its tests pin the behaviour that matters, including both Review Focus items. The remaining items are Minor. The zero-length-clip gap in the guard's lower bound is worth carrying into Task 12's calibration.
