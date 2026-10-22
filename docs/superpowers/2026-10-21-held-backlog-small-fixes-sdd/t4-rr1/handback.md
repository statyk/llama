### Finding Verdicts
1. **`.lock` untouched mutant: ADDRESSED.** `test_the_lock_file_is_never_touched_by_a_failed_unit` (test_show_unit.py, new, after line 128) touches `ws.lock`, records `st_ino`, runs a failing unit and asserts the inode is unchanged. Under the `if True:` mutant, `.lock` gets snapshotted, and restore step (b) `atomic_write_bytes` (temp file plus rename) replaces it with a new inode. The old inode cannot be reused because the flock fd still holds it open, so the test goes red reliably. The implementer reports this mutant red.
2. **Deleting the leftover discard: ADDRESSED.** `test_a_leftover_snapshot_file_is_not_resurrected_by_a_failed_unit` takes `before` first, then plants `.txn/files/ghost.json` (a path the show lacks), runs a failing unit and asserts `tree_bytes == before`. Without the entry discard, `ghost.json` sits in `saved` and step (b) writes it into the show, so the test goes red. A variant mutant that keeps the check but drops the rmtree is also red: the check's LlamaError satisfies `_fail_inside`, but `.txn/files/ghost.json` survives in `tree_bytes`.
3. **take_snapshot failure path: ADDRESSED.** `test_a_failing_take_snapshot_discards_and_re_raises[KeyboardInterrupt|OSError]` patches `show_unit_mod.atomic_write_bytes`, which `take_snapshot` resolves through the module global (show_unit.py:89). It fails on the 2nd write, while 5 tracked files remain, so the snapshot is genuinely partial. The test asserts the re-raise (`pytest.raises(exc)`), that the body never ran, and that `.txn/` is gone, then checks the tree after undo.
   - Handler removed: `.txn` survives, both cases red.
   - Narrowed to `Exception`: the KeyboardInterrupt case is red.
   - Handler swallows the error: the body runs, so red.
4. **Vacuous audio check: ADDRESSED.** test_show_unit.py, `test_existing_audio_is_never_snapshotted_or_rewritten`: the absence assert now runs inside `body()` while `.txn/` exists. If it fails, the AssertionError is not LlamaError, so `_fail_inside`'s `pytest.raises` lets it through and the test goes red.
5. **unlink(missing_ok=True): ADDRESSED.** show_unit.py:102 (step a) and show_unit.py:107 (step c).
6. **Silent leftover-discard failure: ADDRESSED.** `_discard_leftover` (show_unit.py:114-120) runs the discard and raises `LlamaError` if `.txn` still exists. It is called at show_unit.py:134, under the lock, before `take_snapshot` and before the yield. The post-restore and post-success discards (show_unit.py:138, 144, 146) keep `ignore_errors`. `test_a_leftover_that_cannot_be_removed_refuses_before_anything_is_written` makes rmtree a no-op and asserts the LlamaError ("leftover snapshot"), that the body did not run, and that no `.txn/index.json` exists. With the check removed, the body runs and the test is red.
   - **Refusal writes nothing.** Before the raise, the only filesystem effects are a best-effort deletion of the leftover (which is supposed to be deleted anyway) and the pre-existing lock file.
   - **Message and type are sensible.** The text is `"<slug>: cannot remove leftover snapshot <path>"` and the type is plain `LlamaError`, not `ShowChanged`, which is correct because the show did not change. The CLI's existing `except LlamaError` arms render it as an ordinary error.
   - **The brief's fixed `ShowChanged` strings are unchanged** (show_unit.py:132-133).

Evidence check:
- The fix report names every covering test and the mutants run (scratch copy, `llama.__file__` verified). It gives the file count (17 passed) and full-suite output: 4005 passed, 1 skipped, 8 deselected.
- It does not state the exact command; 8 deselected is consistent with `pytest -q` excluding `live`.
- I ran the file once to confirm the new tests are clean: `./.venv/bin/python -m pytest packages/llama/tests/test_show_unit.py -q` gave 17 passed in 0.32s, no warnings. `llama.__file__` resolves inside this worktree.

### New Breakage in the Fix Diff
No Critical or Important issues. Two Minor ones:
- **Minor, test hygiene.** test_show_unit.py `test_a_leftover_that_cannot_be_removed_refuses_before_anything_is_written`: `monkeypatch.setattr(show_unit_mod.shutil, "rmtree", ...)` patches the global `shutil.rmtree` process-wide for the test, not a show_unit-local name. It is harmless today because the patch is undone at teardown and tmp_path cleanup happens later. Patching `show_unit_mod.discard_snapshot` to a no-op would scope the fake to the module; `_discard_leftover` resolves that name through the module global.
- **Minor, docs.** The module docstring's limitation 3 (show_unit.py:12-14) still says the next unit "deletes it WITHOUT restoring". It does not mention the new refusal when the leftover cannot be deleted. One clause would fix it.

### Out-of-Scope Observations
None.

### Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage.
