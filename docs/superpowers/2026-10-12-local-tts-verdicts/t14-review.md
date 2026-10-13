### Spec Compliance
- ✅ Spec compliant. Every brief item and controller ruling is implemented:
  - `presenter add` adds `--voice-clone-text/--tts/--tts-model/--transcribe`, and stores `voice_clone` through `_abs_clip` (cli.py:205-212, diff lines 171-213).
  - `_pin_label` (cli.py diff 145-146). `list` and `show` show the pin only when `p.tts` is set, and `show` prints `transcript:` only when the presenter is pinned and has one (diff 235-252).
  - `say --clone-text` and its three usage errors use the exact brief text. `clone_text` is passed only when `house_mlx` is true (diff 79-95).
  - C2: `presenter_add` reuses `_usage`, `_abs_clip`, `_draft_transcript`, `_read_character_file` and `_build_presenter`, with no inlined try/except. The messages and exit codes match the brief's inlined version: `_build_presenter` (cli.py:819-826) prints `invalid presenter: ...` and exits 1. The placeholder pre-validation also goes through `_build_presenter`.
  - R1 (tts/__init__.py:88-91): keeps the substring "voice cloning is not available on elevenlabs" and reads correctly for a presenter's clip and for `say --clone`. See Important 1 for a third path it now gets wrong.
  - R2 (diff 123-134): the unload is in an inner `finally`, under the same condition and with the same `note:`. On success it still runs before the prompt. A new test checks that a failed transcription with verification off still sends the DELETE (test_presenter_edit.py diff 524-533), with a verification-on companion.
  - R3: the `--transcribe`/`--clear-voice-clone-text` exit-2 case, the empty-transcription test and the unload-failure note test are all present (test_presenter_edit.py diff 499-500, 545-569).
  - R4: all six `!= 0` became `== 1`. No other text changed, and grep finds no `!= 0` left in test_presenter_cmd.py.
  - Commit trailer matches Global Constraints (`git log -1 f57041a`). The diff adds no STT model id and no llama import to src, and every new test sets `EMCEE_ROOT` under tmp_path and uses MockTransport-backed `MlxServer`.
- ⚠️ Cannot verify from the diff alone: that the full suite is green at 2899 passed. I did not re-run it, as instructed.

### Strengths
- `presenter_add` is now a short composition of the Task 13 helpers, with no duplicated validation or character-file logic. The `dest.exists()` refusal runs before any transcription, so a refused overwrite spends no STT call.
- R2 is placed correctly. The inner `try/finally` sits inside the outer `close()` `finally`. An unload `SpeechError` is caught inside the `finally` and printed as a `note:`, so it cannot replace a transcription error. `SttClient.unload` wraps both `httpx.HTTPError` and non-2xx responses as `SpeechError` (verify.py:156-165), so in practice nothing escapes to mask the original error. The empty-transcription check runs after the unload, which is also correct.
- The new list test pins the unpinned list line byte-for-byte (`roy_line == ...`, test_presenter_cmd.py diff 477-478). `test_say_with_no_voice_flags_sends_the_house_transcript` runs the real mlx path through `install_mlx` instead of mocking `ad_hoc_speech`.

### Named-risk checks
1. **R2 ordering and masking.**
   - Success path: transcribe, then unload (inner finally), then `close()`, then the empty check, then the draft is printed, then the prompt. The model is unloaded before the draft is printed, not between the draft and the prompt as the risk statement phrases it. That is the same order as before R2 and meets R2's actual requirement (unload before the prompt).
   - Masking: none, as described under Strengths (verify.py:156-165).
   - Coverage gap: no test pins "unload before the prompt" (Minor 1).
2. **`say --clone` per house backend.** `ad_hoc_speech` (process.py:149-151) sends `--clone` to the HOUSE backend with whatever `clone_text` the CLI passes.
   - voxtral: the clone works, and `--clone-text` is accepted and silently dropped. That matches the brief ("ignored otherwise") and the option's help text.
   - elevenlabs: refused with the R1 `SpeechError` from `speech_provider_for`. The refusal comes after the text file is read (not a spend).
   - fake: passed through, test-only.
   - mlx_audio: `--clone` without non-blank `--clone-text`, and `--voice`, are both usage errors with exit 2. There is no path that silently falls back to another backend, so strict surface 1 holds.
3. **Unpinned `list`/`show` output is byte-identical.**
   - Code: when `p.tts` is unset, `pin == ""` and the `show` suffix is `""`, so the format strings are unchanged (diff 233-247).
   - Existing tests: `test_presenter_add_and_show` and `test_presenter_list_empty_and_populated` are unchanged, but they only assert substrings, so they would not catch a change in unpinned output.
   - New test: the list line is now pinned exactly. The `show` output for an unpinned presenter is only asserted negatively (`"tts=" not in`, `"transcript:" not in`). See Minor 2.
4. **The R1 message's other call sites.**
   - The message is defined only at tts/__init__.py:88-91.
   - Tests: test_tts.py:237 and :248 match the kept substring with `pytest.raises(match=...)`, so they still pass.
   - Docs: the plan doc (docs/superpowers/plans/...:1826-1827) still quotes the old wording. That is a historical plan, so I am not flagging it.
   - Paths that reach the message: a presenter's clip, `say --clone`, and the house `[tts] voice_clone`. The third case is Important 1.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **packages/emcee/src/emcee/tts/__init__.py:88-91: R1's new wording is wrong for the house `[tts] voice_clone` path, which the old wording described correctly.**
   - Where it fires: `speech_for(config, None)` passes `config.tts.voice_clone` as `clone_ref` (process.py:116). `config.py` has no validator rejecting `backend = "elevenlabs"` together with `[tts] voice_clone`, so `emcee run` and `emcee voice` reach this branch for an unassigned package.
   - Measured message (python -B, config `{'tts': {'backend': 'elevenlabs', 'voice_clone': '/refs/house.wav'}}`):
     `the house voice: voice cloning is not available on elevenlabs: this clone reference (a presenter's voice_clone, or say --clone) resolves to the elevenlabs backend (clone on voxtral or mlx_audio, or use a preset voice)`
   - The parenthetical lists two sources and neither is the real one. An operator is sent looking for a presenter or a `--clone` flag that does not exist, when the fix is `[tts] voice_clone` or `[tts] backend`. The old text ("a voice_clone resolves ...") was accurate here. This is a small regression in an operator-facing error on the strict-surface-1 path, and this diff introduced it.
   - Fix (one line): name all three sources, e.g. `this clone reference ([tts] voice_clone, a presenter's voice_clone, or say --clone)`. Or branch on `resolution.presenter is None` the way `_who` does. Then add a house-path test next to test_tts.py:237 that asserts the message names `[tts] voice_clone`.

#### Minor (Nice to Have)
1. **test_presenter_edit.py:236-244 (`test_transcribe_declined_leaves_the_file_untouched`): no test pins R2's "unload before the prompt" requirement.** If the unload were moved after `typer.confirm`, a declined prompt would raise `typer.Exit` before unloading and leave the STT model loaded, and no test would fail. The confirmed-path test at :235 cannot tell the difference. Fix: add `assert server.deletes == [{"model_name": "stt/test-model"}]` to the declined test, after keeping a handle on its `MlxServer`.
2. **test_presenter_cmd.py diff 482-483: the unpinned `show` output is asserted only negatively.** Strict surface 4 says list/show change only for pinned presenters. `list` is pinned exactly, but `show` is not. Fix: add `assert roy.splitlines()[0] == "Roy  (male)  voice=roy-preset"` and an exact check of the full unpinned `show` output.
3. **`presenter add --transcribe --voice-clone-text X` (cli.py diff 194-195) has no test on the add side.** It is only covered by the edit parametrization (test_presenter_edit.py:498). The code is a one-line `_usage`, so the risk is low.
4. **test_say_cmd.py diff 637-643 (`test_say_ignores_clone_text_under_a_hosted_house`) does not assert the exit code.** If `say` failed after `ad_hoc_speech`, the test would still pass. This came verbatim from the brief. Fix: add `assert result.exit_code == 0, result.output`.
5. **No real-path (unmocked) test for `say --clone X --clone-text Y` under an mlx house.** `test_say_forwards_clone_text_under_an_mlx_house` stubs `ad_hoc_speech`. A test like the house-transcript test, asserting `ref_audio == str(ref)` and `ref_text == "Their words."` in `server.speech_bodies`, would pin the wire contract end to end.

### Assessment
**Task quality:** Needs fixes
**Reasoning:** The task matches the brief and every controller ruling, and it reuses the helpers cleanly. R2's `finally` is correctly ordered and masks nothing. The one fix needed is R1's new error wording, which now misnames the clip's source on the reachable house `[tts] voice_clone` + elevenlabs path that the old wording described correctly. It is a one-line change plus one test.
