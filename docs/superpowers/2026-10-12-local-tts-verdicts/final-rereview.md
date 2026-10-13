# final-rereview: fix wave d94cd90..3e84438

### Finding Verdicts

- **F1 (Minor 2, `wav_to_mp3` width/malformed)**: ADDRESSED.
  - `packages/emcee/src/emcee/tts/mlx_audio.py:34-43`: a width other than 2 raises `SpeechError("expected 16-bit PCM WAV, got {8*w}-bit")`. `wave.Error`/`EOFError` become `SpeechError("malformed WAV from the provider: ...")`. `SpeechError` is an `EmceeError`, not an `EOFError`, so the inner raise is not swallowed by the `except`.
  - Tests are at `packages/emcee/tests/test_mlx_audio.py:338-353`. 8-bit and 24-bit are refused with the width in the message, garbage is refused, and 16-bit encodes. `mlx_helpers.wav_bytes` really does write the requested sample width.
  - Other callers: grep shows only two. `quality.py:64` is the target. `mlx_audio.py:90` is the provider path, and there `_read_wav` (`:137-151`) has already rejected width != 2, malformed bodies, non-mono and non-24k audio before `wav_to_mp3` runs. The new checks therefore never fire on that path, and valid 16-bit behaviour is byte-identical.
  - The chunked path (`audio._chunked_pcm`) does not call `wav_to_mp3`.
  - No caller relied on catching `wave.Error`. The only other `wave.Error` catches are in `bed.py:38` (bed files, unrelated) and `_read_wav` itself.
  - The focused files pass (99 passed).
- **F2 (Minor 4, `~` in `_draft_transcript`)**: ADDRESSED.
  - `cli.py:779` now reads `Path(clip).expanduser().read_bytes()`.
  - The test (`test_presenter_edit.py:356`) isolates config with `EMCEE_ROOT` (via `_home`) and points `HOME` at `tmp_path/fakehome`, so the real home is never touched. It calls `_draft_transcript(config, "~/clip.wav")` directly. That is the right level: the add path and the `--voice-clone` edit path already pass through `_abs_clip` (which expands `~`), so the reachable case is a legacy stored `old.voice_clone` (`cli.py:970-974`).
- **F3 (Task 15 rollback docs)**: (a) and (b) are ADDRESSED. (c) is NOT ADDRESSED: its description is correct but its remedy does not work. `README.md:546-551`:
  - (a) "unpin EVERY presenter pinned to mlx_audio, not only Phil, back to a Voxtral-suitable `--voice-clone`" is correct.
  - (b) "move a `[tts.voxtral]`/`[tts.elevenlabs]` `model` back to `[tts] model` too, if one is set" is correct.
  - (c) The facts are right. The old `Presenter` (main checkout `packages/emcee/src/emcee/presenters.py:15`, a plain `BaseModel`, so extra keys are ignored) loads a pinned file and ignores `tts`, so the presenter is voiced on the house backend.
  - **The remedy "clear such pins" does nothing for the old binary**, which already ignores the pin. An elevenlabs-pinned presenter must carry `voice` = an ElevenLabs voice_id (`presenters.py:29,50`: elevenlabs refuses `voice_clone`). Clearing the pin leaves that id in place, and the old binary still sends it to Voxtral and fails after LLM spend.
  - The remedy that works: give that presenter a Voxtral voice (`emcee presenter edit <id> --clear-tts --voice <voxtral preset>` or `--voice-clone <clip>`), or keep the house on elevenlabs.
  - The unedited sentence just above (`README.md:543-544`, "Presenter pins to voxtral/elevenlabs (e.g. roydemure) are harmless") now contradicts (c). It should say "voxtral pins".
  - This is doc-only and Minor: the station has no elevenlabs pins, and the failure is loud and harms no package. The README follows the brief's own wording ("must be cleared"), so the wrong remedy originates in the brief, not the implementer. It still falls short of the "correct" bar F3 set.
- **F4 (exact calibration pins)**: ADDRESSED.
  - `test_calibration_measured.py:150-152` pins `(MISS_FLOOR, MISS_FRACTION, EXTRA_FLOOR, EXTRA_FRACTION) == (2, 0.15, 4, 0.25)`. These equal `verify.py:31-34`.
  - `:157-162` pins `dataclasses.asdict(CAL)` against all 8 fields: 12.5, 5.0, 0.09, 2.0, 0.09, 0.04, 0.5, 1.0. These equal `calibration.py:49-56`. Dict equality also catches an added or removed field.
  - The shared header comment (`:143-146`) cites `docs/superpowers/2026-10-12-mlx-audio-calibration.md` and says "Changing any value means changing its pin in the same commit".
  - `:148` marks MISS_FRACTION 0.15 as "operator-ratification pending". `:155` marks 0.09 as the "operator-approved deviation from the derived 0.08". Both match the doc (lines 164-168, 87 and 272).
  - No source constant changed: the diff touches no src file other than `mlx_audio.py` and `cli.py`.
  - Mutant kill: both tests are exact-equality assertions, so any change to a pinned value turns them red by construction. I did not re-run the mutants. The implementer's note is correct: max_s_per_char at 0.12 alone dies at import on the `cap >= max` invariant, and only max and cap together give a clean red.

### New Breakage in the Fix Diff
- None of Critical or Important severity. The diff is small and correct, apart from the F3(c) remedy wording above.

### Out-of-Scope Observations
- Pre-existing and not introduced here: a WAV whose data chunk is truncated to an odd byte count gets past `wave` and raises `RuntimeError("Input data must be 16-bit PCM data")` from lameenc inside `wav_to_mp3`. This is not a `SpeechError`. Measured: every odd truncation from byte 45 to 9643 of a 0.2 s WAV, 4800 cases.
  - It is reachable from both callers, because `_read_wav` does not check frame-length parity either.
  - It is low-reachability and fails loudly.
  - A one-line `len(pcm) % (2 * channels)` check would close it if the file is touched again.
- Consistency nit: `_read_wav` also catches `struct.error`, while `wav_to_mp3` does not. CPython's `wave` turns struct errors into `EOFError`, and the probe showed no `struct.error` escaping, so this is harmless.

### Verdict
**Fix round:** Findings remain open. Only F3(c) is open: a one- or two-clause README fix (re-voice an elevenlabs presenter for Voxtral instead of only clearing its pin, and narrow "harmless" to voxtral pins). It is Minor, doc-only and does not block merge. F1, F2 and F4 are addressed, and the fix diff adds no Critical or Important breakage.
