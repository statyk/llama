# t20-rev: review of 204bfe1 `feat(scripts): rekey_overrides --restore` (base a65daf5)

### Spec Compliance

- ✅ Spec compliant (spec 4.3 "`--restore`", "Why audio comes first", "What restore does not revert", "Restore runbook", 6(f) restore items; task-20 brief).
  - No version gate: `restore()` (scripts/rekey_overrides.py:1371) calls only `_process_gate`, `verify_snapshot`, `_uncovered_gate`. Nothing from `llama_versions`/`version_ok`.
  - Gates refuse with nothing written, in the brief's order: process check, then `verify_snapshot == []`, then the uncovered-show gate over `library_shows` (so husks are excluded), then `LOCK` non-blocking, then the uncovered gate again under the lock (:1371-1400, :1403-1414). The route text is exact: `  route: llama rm <slug> (add --forget if a later get should re-fetch it)` (:1146, :1410). The tests assert `tree_bytes(root)` is unchanged on each refusal: hash mismatch and missing manifest, an uncovered show, llama running and a failed `ps`, and a held lock.
  - Lock order: `.rekey.lock` is entered first through an ExitStack (:1388). Each show's `file_lock(ShowWorkspace(d).lock)` is taken inside it (:1269). The slugs are sorted (:1422).
  - Audio first (:1271-1278). The audio is kept only when the snapshot holds `package/manifest.json`, that copy's sha256 matches the manifest, and it is byte-equal to the current regular file. Otherwise `_empty_audio` runs and flushes the audio dir before any copy-back.
  - Copy-back verifies each file's sha256 before writing. It writes with `_durable_write` (temp, `F_FULLFSYNC`, `os.replace`, dir sync) (:1207-1224).
  - Step 3 deletes every unlisted entry outside `package/audio/`, keeping only the top-level `.lock`. It removes empty dirs and syncs the touched dirs (:1227-1258). `.txn/` and `.audio-aside/` are deleted: `_metadata_files` excludes `ASIDE_DIR` from the snapshot (:546-560, checked), so it is never in `wanted`.
  - Lists: `NOT_REVERTED` comes first. Then reapply and runs dirs by `st_birthtime`, else `st_mtime`, after `created_at`. Then station destinations by manifest `st_mtime`, marked `(voiced)` or `(unreadable)` (:1288-1354).
  - The record is renamed `rekey-applied.restored-<UTC>.json` only after every slug is restored and the lists are printed. The root is synced and an existing target is never overwritten (:1357-1368, :1440-1446). A failed restore returns 1 before reaching that code (:1432-1437), so the record stays, as Task 19's `_read_record` requires. This is tested at test_rekey_overrides.py `test_restore_renames_the_applied_record`.
  - The next-steps line is verbatim (:1148-1149).
  - `_hand_restore` is deleted. `test_apply_after_a_restore_starts_a_fresh_record` now uses the real `--restore` and asserts the record is gone. `test_lock_only_show_dir_is_not_a_show` is extended to `--restore`: rc 0, husk unnamed and still `.lock`-only.
  - Every brief-named Step-1 test is present (crash test parametrized at two points).
- ⚠️ Cannot verify from the diff: that Task 19's `_read_record` treats a renamed record as absent and a present record as authoritative. That is consistent with the rename semantics here, but it lives in unchanged code. The controller should confirm it at the whole-branch review.

### Strengths

- **Audio-first is correct, and the crash window is pinned on both sides.** The crash test runs at `overrides.json`, which sorts before `package/manifest.json`, and at `show.json`, which sorts after it. In both cases the re-run leaves empty audio beside the snapshot's manifest. The implementer's M2 mutant (emptying after the copy) turns it red.
- **Symlink discipline is thorough and conservative:**
  - `_unlink_entry` uses lstat.
  - `_empty_audio` unlinks a linked `package` or `package/audio` rather than following it.
  - `_check_inside` refuses to write through any linked parent.
  - Step 3 walks with `follow_symlinks=False`.
  - A non-directory show path stops the run.

  I traced the pathological case of `package` being a symlink to an outside dir whose `manifest.json` equals the snapshot's. That makes keep=True, but step 2's `_check_inside` then raises before anything is written outside, and the run stops with the record intact. The case is safe.
- **Snapshot path traversal is closed upstream.** I checked `verify_snapshot`/`_key_problem` at :698-763. A key with `..`, `.`, an absolute path or a backslash is rejected. A slug containing `/` or `..` can have no valid entry, so it fails "recorded slug has no entry". Every key's slug must be recorded, so the `by_slug[slug]` index at :1420 cannot raise KeyError.
- **The station tree is only read.** `_station_since` calls only `iterdir`, `is_dir`, `os.stat` and `read_bytes`, with no open-for-write and no `_sync_*` (:1297-1318). The test makes the station read-only and compares `_tree_state` (bytes and mtimes).
- **The mutation table names a predicted test per mutant** and records the one prediction miss honestly (M1 against the symlink test).

### Judgement on the calls beyond the brief and the raised concerns

- **The step-2 skip of byte-equal files (:1219-1222) is sound. It cannot leave a file that differs from the snapshot.**
  - It skips only when `dst` exists, is not a symlink, is a regular file, and its bytes equal the sha-verified snapshot bytes.
  - A directory at `dst` raises (:1216-1218). A symlink is replaced by `os.replace`, which renames over the link itself.
  - A hardlinked `dst` still holds equal bytes. Nothing else writes during the run (process gate plus locks), and llama replaces files atomically.
  - The only difference from always writing is that a skipped file is not re-flushed. Its durability is whatever it already had, which is the same state the snapshot read. That is not a correctness gap.
- **A listing failure only warns, with exit 0 (:1335, :1349).** This is acceptable but weak; see Minor 1.
- **No check that the snapshot lies under `<root>`.** This is low risk. A foreign snapshot would have to record every current slug to pass the uncovered gate. Even then the audio-first rule empties every show whose manifest differs, so no wrong audio can result, only foreign metadata. See Minor 2.
- **Directories empty at snapshot time are removed.** This is acceptable. The snapshot records files, and the spec defines "exactly as at the snapshot" over files. `package/audio` is kept when it is a real dir (:1243-1245), so `package/` survives too.
- **A station manifest voiced in place since the snapshot is listed by mtime.** This matches the spec's own definition ("a destination manifest newer than the snapshot"), but it over-lists. See Minor 3.

### Issues

#### Critical (Must Fix)
None.

I checked every strict-surface (a) path the prompt names:
- old-numbered audio beside a restored manifest: prevented by audio-first plus the re-verified keep rule;
- deletion outside the restored show dirs, or through a symlink: none found;
- any write to or fsync of the station tree: none;
- any write on a gate refusal: none, apart from `.rekey.lock` being created under the lock before the second uncovered gate, which is the spec's own order ("runs the process check and takes the migration lock. It refuses…").

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **scripts/rekey_overrides.py:1335, :1349: a station or runs/reapply listing failure is one indented `warning:` line among the lists, and the exit is still 0.** The station list is the operator's only pointer to destinations that keep new-rule packages (the 37 re-voiced shows) after a library rollback. If an unmounted NAS makes it fail, the line is easy to miss before the operator restarts the sweep loop. This is not wrong audio, since each station package is self-consistent, but the list is lost silently in practice. Fix: repeat the warning just before the `next:` line, for example `warning: station destinations NOT listed (<error>); list them by hand before re-delivering`, or use a distinct exit code.
2. **scripts/rekey_overrides.py:1371/:1532: `--restore` accepts any directory.** Consider refusing unless `snap.resolve().parent == root.resolve()` and `snap.name.startswith(SNAPSHOT_PREFIX)`. Consider also printing a note when `rekey-applied.json` names a different snapshot than the one being restored: restoring an older pre-migration snapshot silently discards v2.17.0 edits made between the two snapshots. Neither check is in the spec. Both are one-liners that only refuse or inform.
3. **scripts/rekey_overrides.py:1312: the mtime test also lists destinations emcee re-voiced in place after the snapshot, without re-delivery.** Their package is still the old-rule one. The header's advice to re-deliver from the restored library could lead the operator into an unnecessary `--replace-voiced`, which discards the DJ audio and costs a re-voice. The spec defines the list by mtime, so this conforms. A cheaper discriminator would add a marker when the station manifest's `tracks` equal the restored library manifest's (already consistent). Raise it with the operator rather than changing it unilaterally.
4. **scripts/test_rekey_overrides.py:1483-1484: `import os`/`import re` sit at module level in the middle of the file.** Move them to the top import block.
5. **scripts/test_rekey_overrides.py:1739-1741: the "not listed" assertions for `oldbatch`/`old-run`/S1 are hard to read.** It is two `any(...)` forms with an `endswith`. Asserting that the exact lines `f"  {root/'reapply'/'oldbatch'}"`, `f"  {root/'runs'/'old-run'}"` and `f"  {station/S1}"` (and S1 with a suffix) are absent would be clearer. The current form is correct; I checked it.
6. **These guards have no test:**
   - the `_copy_back` raise when there is a directory where the snapshot holds a file (:1216-1218);
   - the `_check_inside` refusal (:1196-1204);
   - the `_rename_record` collision branch (:1364-1365).

   Each is a refuse-and-stop path, so a missing test is low risk.

Checks run (no test or suite runs; reading only, plus these focused reads outside the diff, one per named risk):
- **Path traversal through manifest keys or slugs into `_restore_locked`:** I read `_key_problem`/`verify_snapshot` (:698-763). It is closed.
- **`.audio-aside/` restored from the snapshot instead of deleted:** I read `_metadata_files` (:546-560). The snapshot excludes `ASIDE_DIR`.
- **Flaky or false "created since" listing if `created_at` were truncated to seconds:** I read `_take_snapshot` (:610-614). `created_at` is `datetime.now(timezone.utc).isoformat()` and keeps microseconds, so the 0.05 s sleeps in the test are sufficient.
- **A removed show dir not re-created under its lock:** `locks.file_lock` calls `path.parent.mkdir(parents=True, exist_ok=True)` (packages/llama/src/llama/locks.py:23).
- **Husk handling in the uncovered gate:** I read `library_shows`/`_is_husk` (:460-482). A `.lock`-only dir is excluded.

### Assessment

**Task quality:** Approved

**Reasoning:** Every brief and spec item for `--restore` is implemented and tested. The strict-surface properties hold under tracing:
- audio is emptied before any manifest returns;
- nothing is followed or deleted outside the recorded show dirs;
- the station is only read;
- gates write nothing;
- the record is renamed only after a full restore.

The findings are operator-facing polish and missing tests on refuse-only branches.
