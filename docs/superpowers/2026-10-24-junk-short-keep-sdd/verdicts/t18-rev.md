### Spec Compliance

- ✅ Spec compliant (spec 4.3 "`--snapshot`", "The process check", 6(f) snapshot items, 8 premise 9; brief Task 18), with one brief item deferred, noted under ⚠️:
  - Process check first, refusal lists every process, and a failing `ps` refuses too: diff 129-142, tested 686-708.
  - Filename/mixed form gate, with nothing created (the lock file included): 207-224, tested 664-683 via `_tree_state`.
  - Migration lock, non-blocking, outermost: 226-232. Each show lock: 258. Tested 720-750 (thread waits on the held show lock while `.rekey.lock` is held, with no manifest yet).
  - Directory named by the UTC start, an existing one refused and left untouched: 236-244. `mkdir` sits outside the `try`, so the cleanup can never rmtree a pre-existing dir. Tested 560-572.
  - Slugs recorded under the lock, husks left out: 249, 86-107.
  - Copy set is every file outside `package/audio/` and top-level `.audio-aside/`, with the top-level `.lock` aside: 171-192 (`ASIDE_DIR == ".audio-aside"`, checked in `audio_reuse.py:35`). Each copy is sha256-checked against its source and flushed with `_sync_fd` before the manifest: 267-274, 145-156.
  - Manifest shape `{created_at, slugs, files}` is written temp, flushed, renamed, then the directory is flushed: 289-293.
  - Any failure removes manifest.json first, then the directory, and exits 1: 298-321, tested 622-661.
  - `verify_snapshot` reports a missing or unreadable manifest, a missing or changed entry, and a slug with no entry; unlisted files are ignored: 332-388, tested 833-891.
  - `find_snapshot` returns the lexically newest dir holding a manifest: 391-396, tested 803-820.
  - The elapsed time is printed for premise 9: 308-309.
  - The dry-run path in `main` is unchanged (`--snapshot` branches off before `dry_run`): 432-441.
  - `main` gains an exclusive mode group, ready for `--apply`/`--restore`: 420-422.
- ⚠️ Cannot verify from diff:
  - The brief has `test_lock_only_show_dir_is_not_a_show` also assert that "`--apply` and `--restore` do not refuse on it". Those commands do not exist yet (diff 575-590 covers only snapshot and verify). The controller should make Tasks 19 and 20 extend this test and use `library_shows(root)` in both coverage gates.
  - The `--restore` deletion step (spec 4.3 restore step 3) will delete a leftover `.audio-aside/` the snapshot never captured. That is consistent with show_unit's own "leftover aside is deleted at entry", but it is Task 20's to confirm.

### Strengths

- The snapshot can never delete a snapshot it did not create: the FileExistsError is raised before the cleanup `try` (diff 241-244), and the test checks that the existing tree stays byte-identical (568-571).
- Verification is two layers, each pinned by a different test, so a single mutant cannot hide behind the other:
  - the per-copy compare (271-274), whose test asserts its own message (636);
  - a final `verify_snapshot` over the written snapshot (294-297).
- Cleanup removes `manifest.json` before the rmtree (316-320), so a half-removed directory is never mistaken for a snapshot. It also runs on BaseException, and a KeyboardInterrupt is re-raised (298-301, tested 652-661).
- The form check is repeated under the show lock on the exact bytes copied (275-279, tested 762-781). This closes the gap between the pre-check and the copy.
- `verify_snapshot` adds two checks: every key must be a `<slug>/<path>` inside the snapshot (`..`, absolute and backslash keys are refused), and must belong to a recorded slug (324-329, 365-373). `--restore` copies back by key, so this is the right place to refuse a tampered manifest.
- The judgment calls beyond the brief all lean toward refusing, and each one holds up:
  - Unreadable overrides.json blocks the snapshot. Such a file cannot be shown free of filename values, and the runbook requires a dry run with 0 refused first.
  - A non-husk dir with nothing to copy fails. Otherwise a recorded slug would have no entry, and the snapshot would never verify for `--apply`.
  - Symlinks and non-regular entries fail.
  - A root without `shows/` fails, so a mistyped config root gives no empty "rollback point".
  - The flush happens before the re-read. Both precede the manifest, so durability is the same, and this order avoids the documented read-only-fd EACCES.
  - A present `.txn/` is copied. The spec says "every file outside `package/audio/`", and copying it is what lets restore reproduce the show exactly, after which the next unit deletes the stale `.txn/`.
- Refusal tests compare the whole tree state (`_tree_state`), not just the absence of one directory.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
- **No `--snapshot` timing evidence on a real-sized library.** Spec premise 9 is the operator's measurement (Task 22 / runbook), and only the printed elapsed time supports it.
  - Each copied file and each created directory gets its own `F_FULLFSYNC` (diff 154, 287), roughly 600 shows × ~12 entries.
  - On macOS each `F_FULLFSYNC` flushes the whole drive cache, so the cost grows with the count; it may run to minutes.
  - This is acceptable as spec-mandated per-copy flushing. If premise 9 fails, the fallback is one `F_FULLFSYNC` per show (or one before the manifest), which gives the same "flushed before the manifest" guarantee.
- **diff 289-293: the root directory is never flushed.** The snapshot dir's own entry in `<root>` is therefore not explicitly durable after `mkdir`. `snap`, `snap/shows` and every per-show directory are synced, but `root` is not.
  - On APFS a full fsync very likely commits the mkdir anyway.
  - `_sync_dir(root)` after line 293 makes the guarantee explicit.
- **diff 391-396: `find_snapshot` takes any `rekey-snapshot-*` name (as the brief says), not just the stamp form.**
  - A hand-renamed `rekey-snapshot-old` holding a manifest sorts after every real stamp (`o` > `2`), so it would become the "newest" snapshot.
  - `--apply`'s byte-equality re-check and coverage gate bound the harm: a stale snapshot refuses rather than mis-applies.
  - Matching `^rekey-snapshot-\d{8}T\d{6}Z$` removes the surprise.
- **diff 226-231: an `OSError` from opening `<root>/.rekey.lock` (permissions, read-only root) is not caught.** Only `Locked` is. Such an error escapes `main` as a traceback rather than a one-line refusal. Nothing is created, so this is cosmetic.
- **diff 256-257: misleading message for a symlinked show dir.**
  - `_show_dirs` (`rekey_overrides.py:118-120`, checked) uses `is_dir()`, which follows symlinks, so a symlinked show dir is listed.
  - It then fails with "`<slug>: no longer a show directory`", although it was a symlink all along.
  - The refusal itself is right; the wording could say "is a symlink".
- **diff 355-356: duplicate slugs in a hand-edited manifest are not reported.** The cost is nothing; mentioned only for completeness.

Checks run (one per named risk):
- Risk: the `.audio-aside` exclusion compares against the wrong path form. Checked `audio_reuse.py:35`: `ASIDE_DIR = ".audio-aside"` is top-level, which matches diff 183.
- Risk: `classify` raises on malformed positional keys and crashes the gate. Checked `override_keys.py` `_entries`: non-Mapping titles and non-list set_breaks are ignored. Under the lock, any exception becomes a refusal (298-307).
- Risk: something in llama scans `<root>` and would trip over `rekey-snapshot-*/shows/`. Grepped `packages/llama/src/llama/` for `rglob`, `root.iterdir` and `root.glob`. The only hit is `show_unit.py:110`, scoped to `.txn`.
- Risk: the reported 26 warnings are new noise. The SDD logs show 26 warnings at the Task 0 baseline (4788 passed) and in every task since, so this task adds none.
- No test or mutant was re-run. Reading the code answered every doubt. The implementer's 12 mutants match the spec 6 requirement that a mutation of the snapshot's hash verification turn a named test red (M1, M2).

### Assessment

**Task quality:** Approved

**Reasoning:** The snapshot cannot report success unless every copied file is hash-verified and flushed, and the written snapshot re-verifies. Every failure path leaves no `manifest.json` and never touches a pre-existing snapshot. The extra refusals are sound and tested. The remaining items are durability and robustness polish, plus the premise-9 timing the operator still has to measure.
