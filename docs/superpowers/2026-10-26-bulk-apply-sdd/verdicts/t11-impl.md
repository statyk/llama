# Task 11 handback: per-batch snapshots and restore

Status: DONE_WITH_CONCERNS (the concerns are small and listed below)
Commit: ee5dc565 feat(snapshot): per-batch library snapshots with a guarded restore

## What I implemented
New module `packages/llama/src/llama/batch_snapshot.py`, with the brief's interfaces exactly as specified:
- `take(snap, root, slugs, *, station_root)`: for each slug, under its show lock (`file_lock(ShowWorkspace(d).lock)`), it copies every file outside `package/audio/`, `.audio-aside/`, `.txn/` and the top-level `.lock` to `snap/shows/<slug>/<rel>`. Each copy is created exclusively (O_EXCL), flushed with F_FULLFSYNC and read back against the source's sha256, and every directory it creates is synced. It records the station manifest sha256 (None when there is no station copy). `manifest.json` `{created_at, slugs, files, station}` is written last through a temp file and a rename, then the snapshot is verified. On any failure it removes the partial directory (manifest first) and raises `LlamaError("snapshot failed: ...; removed <snap>")`. It refuses an existing `snap` and leaves it untouched. A missing show refuses without creating a directory.
- `verify(snap) -> list[str]`: a port of `verify_snapshot`, plus checks that the slugs are distinct and that `station` maps exactly the recorded slugs to a sha256 or null.
- `record_after(snap, slug, root, *, station_root)`: takes no lock. It appends `{slug, files:{rel:sha}, station, at}` to `snap/after.jsonl` with O_APPEND, F_FULLFSYNC and a directory sync.
- `restore(snap, root, *, station_root, apply, slugs=None, echo)`: refuses outright with LlamaError if the snapshot does not verify or `after.jsonl` has a bad line. Otherwise, per slug under its show lock, it follows the brief's decision table and uses its strings verbatim:
  - no after-record: `untouched`, or `refused: changed, and this batch recorded no write for it`;
  - `refused: library files changed after the batch: <first rel>` (the first rel in sorted order);
  - `refused: station manifest changed after the batch (re-delivered or re-voiced): roll forward instead`;
  - otherwise it rewinds in the brief's order: empty `package/audio/` and flush it, but only when the package manifest sha differs; delete tracked files the snapshot lacks (and prune directories those deletions left empty); write back the snapshot files that differ, each atomic (temp, F_FULLFSYNC, replace), then sync the directories.
  - Every snapshot copy is hash-checked again before the show's first write.
  - Actions returned: `restored` / `restored; package/audio emptied`, or with `apply=False`: `would restore` / `would restore; would empty package/audio`. Each `(slug, action)` is echoed as `<slug>: <action>`.
  - It never writes the station.
- `seal(snap, root, *, station_root)`: runs `record_after` for each recorded slug under its show lock. A show directory that is gone gets no record.

## Beyond the letter of the brief (please check)
1. Refusals are returned as `refused: <verbatim brief text>`, so a caller can tell an action from a refusal.
2. `already restored` is returned when an after-record exists but the current files already equal the snapshot and the station equals the after-record. Without this, a second restore run would refuse with "library files changed after the batch". If the batch's after-record also equals the snapshot (it wrote identical bytes), the action is `untouched` instead.
3. Extra per-slug refusals:
   - `refused: the show directory is gone` (the show lock is not taken, because `file_lock` would recreate the directory);
   - `refused: not in this snapshot` (a `slugs` entry that is not recorded);
   - `refused: <slug>: station manifest unreadable: ...`;
   - `refused: <dir>/<rel>: not a regular file or directory`.
4. Every entry point refuses a `station_root` that is not a directory ("is the station mounted?"). This is so an unmounted station never reads as "no station copy".
5. `record_after` raises LlamaError for a slug the snapshot does not record, or a missing show directory. Under reapply's `after_commit`, that restores the show unit, so no write goes ahead without an undo point.
6. An OSError part-way through a rewind raises LlamaError, saying the show is partly restored, that a re-run will refuse it, and where to copy its files back from.

## Tests and results
New file `packages/llama/tests/test_batch_snapshot.py`, 10 tests:
- the seven the brief names: `test_take_copies_metadata_only_and_verifies`, `test_partial_snapshot_is_removed_on_failure`, `test_restore_rewinds_a_batch_write`, `test_restore_refuses_a_later_library_change`, `test_restore_refuses_a_changed_station_manifest`, `test_restore_dry_run_writes_nothing`, `test_untouched_show_is_left_alone`;
- three more: `test_restore_keeps_audio_when_the_package_manifest_is_unchanged`, `test_seal_records_every_show_and_record_after_needs_a_snapshot_slug`, `test_restore_refuses_a_snapshot_that_does_not_verify`.

No test touches emcee_running or ps. No existing test expectation was moved.

Full suite: `./.venv/bin/python -m pytest -q -p no:cacheprovider` gives **6210 passed, 1 skipped, 8 deselected, 26 warnings**. That is the baseline 6200 plus my 10. None of the warnings mention batch_snapshot.

## TDD evidence
RED 1: `./.venv/bin/python -m pytest packages/llama/tests/test_batch_snapshot.py -q` failed at collection with `ImportError: cannot import name 'batch_snapshot' from 'llama'`.

RED 2: with a stub module whose every function raises NotImplementedError, the same command gave `10 failed in 0.38s`. All 10 failed with `E NotImplementedError` (each listed FAILED in the log). This is the expected reason: the feature was absent.

GREEN, first run: 9 passed, 1 failed. The failure was `test_seal_records_...`, and the cause was my own expectation, not the code: the sealed, unchanged show B had been asserted `restored`, but by design it is `untouched`. I corrected the new test's assertion. GREEN then gave `10 passed`.

Mutation check: run in a scratch `git archive` copy, from the scratch cwd, with PYTHONPATH shadowing (proven with a planted sentinel) and PYTHONDONTWRITEBYTECODE=1. The red test was predicted for each mutant before it ran.
- M1 (station check removed): the station test caught it.
- M2 (library check removed): the later-change test caught it.
- M3 (`empty = False`): rewinds, dry_run, untouched and seal caught it.
- M4 (no-write branch returns untouched): the untouched test caught it.
- M5 (package/audio not excluded): take_copies and others caught it.
- M6 (partial dir not removed): the partial test caught it.
- M7 (no deletion of created files): rewinds caught it.
- M8 (`apply` ignored): dry_run caught it.
- M9 (verify sha check removed): take_copies and the not-verify test caught it.
- M10 (station ignored for a show with no after-record): **this mutant survived at first**. I added a case to `test_untouched_show_is_left_alone` where a station copy appears after the batch with no recorded write, and M10 is now caught. The unmutated scratch copy passes 10/10.

## Files changed
- /Users/shawn/projects/llama/.claude/worktrees/bulk-apply/packages/llama/src/llama/batch_snapshot.py (new)
- /Users/shawn/projects/llama/.claude/worktrees/bulk-apply/packages/llama/tests/test_batch_snapshot.py (new)

## Self-review
- Every interface and every refusal string is present verbatim, all seven named tests exist, and the copy/flush/verify pattern is ported without importing `scripts/rekey_overrides.py`, which is unchanged.
- No untouched constant or module was edited.
- The Manifest model is unchanged, and nothing imports emcee.
- Locks: `take`, `restore` and `seal` lock per slug; `record_after` takes no lock, and `seal` calls it inside its own lock (no nesting of the same lock).

## Concerns
- `already restored` and the extra refusals (listed above) are my additions; the controller should confirm them.
- A rewind that crashes part-way leaves the show refusing on re-run, with a message saying how to recover by hand. That seemed safer than guessing.
- `record_after` reads the snapshot manifest on every call. That is fine at wave size (a few hundred KB of JSON per show).
- Process slip: I briefly wrote a temp file of full-suite output to the parent `.superpowers/sdd/bulk-apply/` directory (outside `t11-impl/`) and removed it at once. The `suite.rc` file from the background run was in `t11-impl/` and has been removed.
