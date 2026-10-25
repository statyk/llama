# t12-fix1 handback: Task 12 fix round 1

**Status: DONE.** Commit `ba4e10a`, on top of `5a89be0`.

## Important 1: the aside is now single-use
- **`set_aside` refuses an existing aside.** If `ASIDE_DIR` already exists, `audio_reuse.set_aside` raises `LlamaError` before it moves anything. The message is `<slug>: an audio aside already exists at <path>; re-packaging twice in one unit is not supported`. The original aside stays intact, so the unit's restore followed by `put_back` brings back the correct audio.
- **`build_package` reads the aside only if it made it.** It passes aside (library) candidates to `reuse_into` only when this same call ran `set_aside`. Otherwise it uses `dataclasses.replace(reuse, library={})`. This also closes my earlier concern 2 (a stale aside being read in the keep-in-place branch).
- **New tests:**
  - `test_show_unit.py::test_two_repackagings_in_one_unit_restore_the_original_audio` reproduces the reviewer's probe. It packages [A(a), Jam(j1), Jam(j2)], then inside one unit runs pass 1 (inserts Crowd) and pass 2 (drops it again), then raises. It asserts the show tree is byte-equal to before and no aside is left.
  - `test_audio_reuse.py::test_set_aside_refuses_when_an_aside_already_exists`
  - `test_stage_package.py::test_an_aside_this_call_did_not_make_is_never_read`: a stale aside holds `02 - B.mp3` with another file's audio of matching length. In the keep-in-place branch, `b.mp3` is downloaded instead.

## Minor 1: keep-in-place also checks the source file
- **The rule.** Files stay in place only when the names match AND `reuse.library.get(t.filename) == name` holds for every new track.
- **New test:** `test_stage_package.py::test_a_new_source_under_an_unchanged_name_is_not_kept_in_place`. Old [A(a), Jam(j1), B(b)] becomes new [A(a), Jam(j0), B(b)]. Only j0 is downloaded, `02 - Jam.mp3` holds j0, and A and B are reused from the aside.

## Minor 2: show_unit limitation 5 docstring
- **Part-way `put_back` failure.** The docstring now says such a failure leaves `.txn/` and a partial aside. The next unit's entry deletes both, and the files not yet moved back are lost the same way.
- **Masked exception.** The `put_back` exception masks the original one, which survives as its `__context__`.
- **Single use.** It also notes that a second set-aside in one unit refuses.

## Red, then green
- **Before the fix,** all 4 new tests failed on assertions:
  - DID NOT RAISE LlamaError;
  - `[] == ['j0.mp3']`;
  - `[] == ['b.mp3']`;
  - the tree differed after the two-pass failure.
- **After the fix,** the three task files pass. Command: `./.venv/bin/python -m pytest -q -p no:cacheprovider packages/llama/tests/test_audio_reuse.py packages/llama/tests/test_stage_package.py packages/llama/tests/test_show_unit.py`. Result: `59 passed in 0.79s`.
- **Full suite:** `./.venv/bin/python -m pytest -q -p no:cacheprovider` (background, teed into `t12-fix1.log`). Result: `5049 passed, 1 skipped, 8 deselected, 26 warnings in 77.63s`, rc 0. That is the earlier 5045 plus the 4 new tests.
- **No existing expectation changed.** `test_unchanged_list_and_matching_manifest_keeps_files_in_place` (pin) still passes.

## Behaviour note
A second re-packaging inside one unit now fails that unit and restores the show. Today this is unreachable: the only double redo, `fix --untitled`, runs its second pass `--from brief` with show.json unchanged, so the files stay in place and `set_aside` never runs a second time. Task 13 should keep it that way.
