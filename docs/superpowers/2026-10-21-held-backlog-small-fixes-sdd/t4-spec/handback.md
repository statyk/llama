### Spec Compliance (SPEC role) — ✅ Spec compliant
⚠️ Cannot verify from diff: C1 steps 1-2 as they apply to callers (prompts before the lock, a lock-held inner `_redo_show`, never taking the show lock twice), C3, C4 and C5's command-level tests. These belong to Tasks 5-7, which consume this module.

### Strengths
- Every Interfaces name in the brief is present and spelled as specified: `TXN_DIR = ".txn"`, the frozen `ShowView(provenance, overrides, show)`, `capture_view`, `ShowChanged(LlamaError)`, `take_snapshot`, `restore_snapshot`, `discard_snapshot`, `show_unit(show_ws, expect)`, and `helpers.tree_bytes`.
- Named risk (a), restore order (show_unit.py `restore_snapshot`). The steps run (a), then (b), then (c), matching the brief and C2. `_tracked_files` prunes `.txn` from the walk only at the top level and `audio` only under `package`, and it skips only the top-level `.lock`. Step (a) therefore never touches `.lock`, `.txn/` or audio. Step (b) uses `atomic_write_bytes`, which creates missing parents (focused check: workspace.py:26-38), so it also restores a file whose directory the unit removed. Step (c) only unlinks audio names that are not on the index list.
- Named risk (b), audio. The snapshot never copies `package/audio/*`, because the walk prunes it. Restore never writes audio, because the set of saved files excludes it. `test_existing_audio_is_never_snapshotted_or_rewritten` asserts both properties.
- Named risk (c), the view check and the lock. `capture_view` and the `ShowChanged` raise come before `discard_snapshot` and `take_snapshot`, so nothing is written. The only write is the `.lock` that `file_lock` creates, which is the husk limitation C2 documents. `with file_lock(show_ws.lock)` uses the default `blocking=True` (focused check: locks.py:16) and wraps the whole generator, including the yield and the restore. The test of a held lock, and of a lock released afterwards, pins this.
- The fixed strings match exactly: `"{slug}: changed by another command; run it again"` and `"{slug}: the show was removed; nothing changed"`, with `slug = show_ws.dir.name`. The removed-show condition is `expect.provenance and not now.provenance`, as the brief specifies.
- The error paths follow the brief. A failed `take_snapshot` discards the snapshot and re-raises. The yield is guarded by `except BaseException`, so `KeyboardInterrupt` also triggers the restore and discard. A failed restore leaves `.txn/` in place and carries the original error as its implicit `__context__`. On normal exit the snapshot is discarded, and the next unit deletes a leftover snapshot without restoring it.
- All 11 test functions in the brief (12 cases with the parametrize) are present and match the brief verbatim. The only change is the fixture's dummy `provenance` dict, and the handback discloses it. The module docstring carries the three C2 limitations plus the fourth, `show_ws(prov.performance_id)`, that the brief asks for. The module is new, so every test fails on today's code with `ModuleNotFoundError`, which the implementer reports as the RED result.

### Issues
#### Critical
None.
#### Important
None.
#### Minor
- show_unit.py `discard_snapshot` uses `shutil.rmtree(..., ignore_errors=True)`, and step 4 of `show_unit` uses it to remove a leftover. If the rmtree fails part-way and silently leaves a stale file under `.txn/files/` that the current tree lacks, `take_snapshot` writes over the rest without noticing. A later failed unit's step (b) would then resurrect that stale file, which is a strict-surface outcome. The odds are low, because a filesystem that refuses the delete probably refuses the snapshot writes too. Fix: in the leftover path, either rmtree without `ignore_errors`, or assert that `.txn` is absent before `take_snapshot`. Keep `ignore_errors` only for the post-success and post-restore discards.
- No test drives the branch where `take_snapshot` raises (discard, then re-raise). The brief specifies the behaviour but does not ask for a test, so this is a coverage gap only.

### Assessment
**Task quality:** Approved
**Reasoning:** The diff implements every Interface and Behaviour item in the Task 4 brief and C1 steps 2-5 and C2 of the spec, with the binding strings verbatim, and all three named risks check out. The two Minor items concern a hardening of the leftover-delete path and test coverage, not compliance.
