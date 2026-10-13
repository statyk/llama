### Spec Compliance
- ✅ Spec compliant. `packages/emcee/tests/test_presenter_edit.py` is byte-identical to the brief's Step 1 block (I extracted the block and ran `diff`: no output). In `presenter_edit` (cli.py:833-931), every option, every one of the brief's eight exact usage messages, the set/clear merge, the voice/clip/transcript coupling, the "draft" pre-validation and the save-last ordering match the brief. The only differences are the ones ruling R1 asked for.
- ✅ R1 helpers. `_read_character_file` (cli.py:784-790) and `_build_presenter` (cli.py:793-800) both exist, and `presenter_add` calls them (cli.py:820, 825-826).
- ✅ R1 equivalence, `try/except ValidationError` replaced by `_build_presenter`. It is equivalent:
  - In the brief, the try block wrapped `_usage`, `_draft_transcript` and the two `merged()` calls. Of those, only `Presenter.model_validate` can raise `ValidationError`.
  - The `Presenter` validators raise only `ValueError` (presenters.py:37-58), and pydantic wraps that in `ValidationError`. `extra="forbid"` also raises `ValidationError`.
  - The catch in `_build_presenter` now surrounds only `model_validate` (cli.py:797-800). So the `typer.Exit(2)` from `_usage` (cli.py:925, 758) and the `typer.Exit(1)`, `EmceeError` and `SpeechError` from `_draft_transcript` (cli.py:762, 772, 777) are raised outside any handler and are never swallowed. That holds even though `_build_presenter` catches `Exception`, which `typer.Exit` subclasses.
  - Output is unchanged: `invalid presenter: {exc}` on stderr, exit 1.
- ✅ Global constraints:
  - Usage errors go through `_usage`: `error: ` prefix, stderr, exit 2 (cli.py:740-742).
  - No STT model id is hard-coded in src. It comes from `mlx.stt_model` (cli.py:764). `"stt/test-model"` appears only in the test file.
  - Every test sets `EMCEE_ROOT` to a tmp dir through `_home`.
  - The commit trailer matches Global Constraints (`git log -1 798849e`).
- ⚠️ Cannot verify from this diff: that `save_presenter` is atomic. The docstring at cli.py:850-853 claims it, and it is Task 2 code.

### Strengths
- The R1 extraction is minimal and correct. `presenter_add` keeps its own exit-1 "give exactly one of" check (cli.py:812-814) and delegates only the file read and the validation. The duplicated read/validate blocks from the brief's verbatim code are gone.
- Every way `edit` can fail exits before the only write, `save_presenter` (cli.py:931): usage errors, validation, a declined transcript, an STT failure and an empty transcription. The "draft" pre-validation (cli.py:926) means an invalid edit never spends a transcription. `test_an_invalid_edit_fails_before_transcribing` pins this.
- The tests check behaviour, not mocks. The file is compared byte-for-byte after each rejection, the multipart content and the DELETE body are asserted against an in-process transport, and absolute-path storage is checked through both a relative path and `~`.

### Named-risk checks
1. **`presenter_add` regressions.** Checked: the call sites at cli.py:812-827 against the removed lines, and the add tests at `test_presenter_cmd.py:47-96`, which this commit does not touch (the diff stat lists only 2 files).
   - The four messages and their exit codes are the same: "give exactly one of --character / --character-file" exit 1, `cannot read --character-file …` exit 1, `presenter … exists … (use --force to overwrite)` exit 1, and `invalid presenter: …` exit 1.
   - The order of checks is unchanged: character check, character-file read, exists check, validate, save.
   - `Presenter(**kw)` became `model_validate(dict)`. That runs the same validation, and the old code already used `except Exception`.
   - One weakness, which predates this branch: the add tests assert `exit_code != 0`, not `== 1`. The unchanged exit codes therefore rest on reading the code, not on a test (see Minor 4).
2. **Edit writes only after every validation and an accepted transcript.** Checked: `save_presenter` is called only at cli.py:931, after `merged()`. A declined transcript raises `Exit(1)` (cli.py:777), an STT failure propagates `SpeechError` (cli.py:766, after `close()` in the `finally`), and an invalid merge exits through `_build_presenter`. Each of these paths has a test asserting the file is byte-identical: `test_transcribe_declined…`, `…unreachable_server…`, `…invalid_merged_edit…`, `…mlx_pin_forces_a_fresh_transcript`, and the parametrized usage errors.
3. **STT unload exactly when `[tts.verify] backends` is empty.** Checked cli.py:767: `if not config.tts.verify.backends: stt.unload()`. It runs before the confirmation, so a declined draft also unloads, and an unload failure is only a `note:`. Both branches are tested (`deletes == [{"model_name": …}]` and `deletes == []`). One gap is Minor 1: a failed transcription skips the unload.
4. **Does the diff reach outside cli.py and the new test file?** No. The diff stat shows exactly those 2 files.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **cli.py:765-771: a failed transcription skips the unload.** `stt.unload()` sits inside the `try`, after `stt.transcribe()`. When transcription raises (a timeout, a 5xx after the model has loaded), the STT model stays resident on the server even with `[tts.verify] backends` empty. That runs against the reason the unload exists: the server keeps every model resident, and memory is a gate. The code follows the brief verbatim. Fix: move the unload into the `finally`, guarded by the same condition and the same `except SpeechError` note.
2. **test_presenter_edit.py:124-133: three named behaviours have no tests** (the test file is brief-verbatim):
   - The brief's exact message `--transcribe and --clear-voice-clone-text are mutually exclusive` (cli.py:880-881) is missing from the parametrized usage-error table.
   - The empty-transcription `EmceeError` (cli.py:771-772) is untested.
   - The `note:` printed on an unload failure (cli.py:769-770) is untested.
   Each needs one test.
3. **cli.py:795-799: `_build_presenter` catches `Exception` where the brief named `ValidationError`.** This is equivalent today; see the R1 equivalence check above. But it would also turn a future validator bug, such as a `TypeError`, into "invalid presenter" instead of a traceback. Narrowing to `pydantic.ValidationError` changes nothing observable for either `add` or `edit`, because `Presenter(...)` and `model_validate` raise only that. Optional.
4. **`test_presenter_cmd.py:51, 59, 66, 72, 82, 94` (predates this branch): add tests assert `exit_code != 0`, not `== 1`.** They pin the messages but not the exit codes R1 required to stay unchanged. Tightening them to `== 1` would make the add path's exit codes regression-proof against Task 14's further reuse of these helpers.
5. **cli.py:865 (brief-verbatim): `load_presenter` runs before the flag-conflict checks.** An unknown id combined with conflicting flags therefore exits 1 (`PresenterError`) rather than 2. This is harmless ordering. It is noted only because the usage-error contract is otherwise "exit 2 first".

### Assessment
**Task quality:** Approved
**Reasoning:** `edit` matches the brief exactly, and the R1 helper extraction leaves every message and exit code of `add` unchanged. Moving the brief's `except ValidationError` into `_build_presenter` is provably equivalent and never swallows a `typer.Exit`. The remaining items are coverage polish and one brief-verbatim unload-on-failure gap.
