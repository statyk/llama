### Code Quality (t4-qual): Approved. Two Important test gaps should be closed before Task 8 runs.

### Strengths
- `show_unit.py` matches the brief's contract exactly: blocking lock for the whole context, view check before any write, discard then snapshot, a `BaseException` restore, then discard and re-raise, and `.txn/` left in place when the restore itself fails. The `__context__` chaining works and is tested.
- `_tracked_files` prunes `.txn` only at the top level and `audio` only under `package`, both by mutating `dirnames`. Walking and restoring share one predicate, so snapshot and step (a) cannot disagree about scope. `index.json` is written last.
- I checked the live library read-only (3983 shows). The only subdirectories are `package/` and `package/audio/`, and there are no symlinks and no multi-link files. The largest non-audio file is a 2 MB `reviews.json`. So the "small JSON/Markdown" premise holds and the snapshot cost is trivial.
- None of the do-not-retune names from global-constraints appear in the diff (grepped).
- I ran a mutation check in a scratch copy (`git archive` of 1fe9109, run from an empty cwd with `PYTHONPATH` shadowing, a sentinel confirming the mutant was imported, and bytecode writes off). The existing tests catch these mutants:
  - restore step (a) removed
  - step (c) removed
  - discard-after-restore removed
  - `BaseException` changed to `Exception` around the yield (caught by the KeyboardInterrupt test)
  - `package/audio` snapshotted
  - each half of the view check (overrides, show, provenance)
  - the re-raise
  - restoring a leftover instead of discarding it

### Issues
#### Critical
None.

#### Important
1. **The ".lock untouched" mutant survives every existing test.**
   - Mutant: `if rel != ".lock":` changed to `if True:` (show_unit.py `_tracked_files`). All 12 tests stay green.
   - Under that mutant a failed unit's step (b) `atomic_write_bytes` replaces `.lock` with a new inode while the lock is held. A waiter then locks the new file, which breaks mutual exclusion on the show. My probe (inode before == inode after a failed unit) goes red under the mutant and is green on HEAD.
   - The reason nothing catches it: `test_a_failed_unit_restores_every_file_byte_identical` only asserts `ws.lock.exists()`, and `tree_bytes` excludes `.lock`.
   - Fix: add a test that touches `ws.lock` first, records `st_ino`, runs `_fail_inside(...)`, and asserts the inode is unchanged. Task 8 lists ".lock untouched" as a mutant that must turn a named test red, and today none does.
2. **The "leftover discarded" mutant survives when the initial `discard_snapshot` is deleted outright.**
   - All 12 tests stay green. `test_a_leftover_snapshot_is_deleted_not_restored` plants only `.txn/files/show.json`, a path the new snapshot overwrites, and its unit succeeds. `test_a_failed_restore_…`'s second unit also succeeds.
   - The real hazard is on the strict surface: a leftover holding a file the show no longer has (for example `ghost.json`), followed by a unit that fails. Without the initial discard, `restore_snapshot` resurrects the stale file, so the show is no longer byte-identical after a failed edit. My probe for this goes red under the mutant and is green on HEAD.
   - Fix: plant `.txn/files/<path not in the show>` and run a failing unit. Assert `tree_bytes(ws.dir) == before`, with `before` taken before the plant.

Both are brief-specified test sets, not implementer error (plan-mandated coverage). The code itself is correct.

#### Minor
1. **No test covers the `take_snapshot` failure path** (show_unit.py, the `try: take_snapshot … except BaseException: discard_snapshot; raise` block).
   - Removing the handler, or narrowing it to `Exception`, leaves all tests green. My probe raises KeyboardInterrupt on the second `atomic_write_bytes`; it goes red under both mutants and is green on HEAD.
   - The consequence is benign (a partial `.txn/` that the next unit deletes; the body never runs). But Task 8's "BaseException vs Exception" is ambiguous between the two sites, and this one is unpinned.
2. **`test_existing_audio_is_never_snapshotted_or_rewritten`'s second assertion can never fail** (test_show_unit.py:88). `.txn/` is always gone after the unit exits, so `not (.txn/files/package/audio).exists()` holds even when audio is snapshotted. The audio mutant is caught only by the first assertion (`RETAGGED`). Fix: make the check inside the body, before raising.
3. **Restore can fail on a file that has already vanished, and a failed restore is the one outcome worse than before** (show_unit.py restore steps (a) and (c), bare `.unlink()`).
   - A failed restore leaves `.txn/`, and the next unit deletes it without restoring (spec-documented). So any avoidable restore failure turns a recoverable failure into a half-edited show.
   - Steps (a) and (c) call `.unlink()` without `missing_ok=True`. A file that disappears between the walk and the unlink would raise mid-restore. Nothing that honours the show lock can cause that, but `missing_ok=True` costs nothing.
4. **`discard_snapshot` uses `rmtree(..., ignore_errors=True)` and never checks the result.**
   - If the pre-snapshot discard fails partway (for example a permissions problem), stale `.txn/files/*` survive. They are then indistinguishable from the fresh snapshot, and a failed unit resurrects them (the same harm as Important #2).
   - Suggest checking that `.txn` is gone after the initial discard and raising if it is not, before the body runs.
5. **Symlinks are dereferenced** (snapshot via `read_bytes`; restore via `atomic_write_bytes`).
   - My probe shows a symlink in the show dir becomes a regular file after a failed unit. The bytes are identical, so the brief's `tree_bytes` check still passes, but the file is no longer a symlink.
   - A dangling symlink makes every unit refuse with a raw `FileNotFoundError` from `take_snapshot`. That is harmless: nothing is written.
   - The live library has no symlinks, so this is informational. A docstring line would cover it.
6. **A unit on an already-removed show recreates a `.lock`-only husk.** This happens even without a race, because `file_lock` calls `mkdir(parents=True)` and opens with `O_CREAT`, and the refusal comes after that. My probe left `['.lock']`.
   - It is covered in spirit by documented limitation 2, which the docstring words only as "a racing `rm`".
   - Callers in Tasks 5-8 should resolve the show (provenance present) before entering the unit, or the docstring should say "a unit on a removed show".
7. **Restore rewrites every snapshot file, unchanged ones included.**
   - Content is byte-identical, but mode becomes 0600 (`mkstemp`) and mtime changes. Live files are already 0600, so mode is a non-issue in practice.
   - Writing back only files whose bytes differ would cut restore I/O and its failure surface. Optional.

### Assessment
**Task quality:** Approved (with the two Important test additions recommended before Task 8).
**Reasoning:** The module correctly implements C1 steps 2-5 and C2, and the restore leaves files byte-identical on the realistic library shape. However, two strict-surface invariants Task 8 will mutate (".lock untouched" and "a leftover is discarded, not restored") have no test that goes red, as I confirmed by running the mutants.

Evidence:
- Mutants and probes are in `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-held-backlog-small-fixes/9847639b-42e2-4b9c-a407-cb7d6c8a5ada/scratchpad/t4q/` (`mutate.py`, `probes/test_probe_show_unit.py`).
- Run output is in `.superpowers/sdd/small-fixes/t4-qual/t4-qual.log`.
- Survivors against the 12 existing tests: no initial discard; `.lock` tracked; no `take_snapshot` handler; `take_snapshot` handler narrowed to `Exception`; the removed-message condition (benign).
- On HEAD, all 12 existing tests pass. The probes pass too, except the symlink probe, which deliberately records Minor 5.
