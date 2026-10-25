# t20-impl handback: `rekey_overrides --restore`

**Status: DONE_WITH_CONCERNS** (the concerns are minor; see the end)
**Commit:** `204bfe1 feat(scripts): rekey_overrides --restore` (on a65daf5, branch held-backlog-junk-filter)
**Files:** `scripts/rekey_overrides.py`, `scripts/test_rekey_overrides.py`
**Full suite:** `./.venv/bin/python -m pytest -q` -> `5372 passed, 1 skipped, 8 deselected` (baseline 5359 + 13 new). Run twice: the second run was on the final committed tree.
`llama.__file__` resolves inside the worktree (`.../junk-filter/packages/llama/src/llama/__init__.py`).

## What was built, against each contract item

- **`restore(root, snap, *, delivery, echo) -> int`** and `main`'s `--restore SNAPSHOT_DIR`, which joins the mutually exclusive group. `delivery` is `config.delivery_path` and may be None. There is no version gate.
- **Gates, in order, each refusing with nothing written** (asserted with `tree_bytes(root)` unchanged):
  1. `_process_gate` (Task 18's, reused).
  2. `verify_snapshot(snap) == []`, else `refusing to restore: <snap>: <problems>`.
  3. The no-uncovered-show gate (`_uncovered_gate`, over `library_shows`, so a `.lock`-only husk is not a show). Each extra show prints `created after the snapshot: <slug>` and then `  route: llama rm <slug> (add --forget if a later get should re-fetch it)`, followed by a `refusing to restore: ...` line.
  4. Then `LOCK` (non-blocking; a held lock refuses), and the uncovered gate runs again under the lock.
- **Per manifest slug, sorted, under `file_lock(ws.lock)`** (`_restore_show`). A slug whose directory is gone is re-created by `file_lock`. A show path that exists but is not a real directory (a symlink, say) raises, and that stops the run.
  1. **Audio first** (`_empty_audio`). The audio is kept only when the snapshot's `package/manifest.json` exists, its sha256 matches the manifest, and it is byte-equal to the current one. Otherwise every entry in `package/audio/` is removed without following a link, and the audio directory is `F_FULLFSYNC`ed before any copy happens. A `package` or `package/audio` that is a symlink is unlinked, never followed.
  2. **Copy back** (`_copy_back`). Each listed file is read from the snapshot and checked against the manifest's sha256 before it is written. It is then written with Task 19's `_durable_write` (temp in the target dir, `_sync_fd`, `os.replace`, dir sync). `_check_inside` refuses to write through a non-directory path component.
  3. **Delete what was written since** (`_delete_unlisted`). Every entry outside `package/audio/` that the manifest does not list is deleted: `.txn/`, `.audio-aside/`, a new `notes.json` or briefing, stray dirs, and symlinks (unlinked, never followed). The top-level `.lock` is kept, empty directories are removed, and the touched dirs are synced.
- **The lists**, printed after every slug is restored. `not reverted: the ledger, runs/, the cache, reapply batch progress` comes first. Then each `<root>/reapply/<batch>/` and `<root>/runs/<run>/` whose `st_birthtime` (else `st_mtime`) is after `created_at`. Then each `<delivery>/<slug>` (dot-prefixed swap siblings skipped) whose `manifest.json` `st_mtime` is after `created_at`, marked `(voiced)` when `dj_audio` is non-null and `(unreadable)` when it cannot be read or parsed. Each list prints `(none)` when empty. The station is only listed and stat'ed: `read_bytes`, never opened for write, never fsynced. With no `delivery_path`, restore prints `station destinations: no delivery_path configured; not listed`.
- **Record rename** (`_rename_record`). Only after every slug is restored, `rekey-applied.json` (if present) is renamed `rekey-applied.restored-<YYYYmmddTHHMMSSZ>.json` (UTC), and the root dir is synced. The rename never overwrites an existing file; if that target exists it is an error and exit 1. A failed restore stops at that show (`error:` / `stopped: ... re-run --restore <snap> to finish`), returns 1 and leaves the record in place.
- **Next steps:** the last line is `next: reinstall v2.17.0 from the release; check llama --version reports 2.17.0; restart the sweep loop`.
- **Carried decisions:**
  - `_hand_restore` is deleted, and `test_apply_after_a_restore_starts_a_fresh_record` now uses the real `--restore`. It also asserts the record was renamed.
  - `test_lock_only_show_dir_is_not_a_show` is extended: `--restore` returns 0, the husk is not named and is left `.lock`-only, and the real show is legacy again.

## Step-1 tests (all in `scripts/test_rekey_overrides.py`)

| test | covers |
|---|---|
| `test_restore_refuses_a_hash_mismatch_and_writes_nothing` | a changed snapshot file, and no manifest at all: refusal, tree unchanged |
| `test_restore_refuses_while_a_show_created_after_the_snapshot_exists` | the listing plus the exact `llama rm` route line; tree unchanged |
| `test_restore_refuses_while_llama_runs` | a sweep-loop shell found, and a failed `ps`; tree unchanged |
| `test_restore_puts_every_file_back_byte_equal_and_deletes_files_written_since` | after restore, the show dir outside audio equals the snapshot (re-keyed overrides, rewritten show.json, new notes.json, briefing.json, `.txn/`, `.audio-aside/`, a stray `package/extra/` all handled); `.lock` kept with its bytes; audio kept (manifest unchanged); no `*.tmp` |
| `test_restore_empties_audio_unless_the_manifest_is_byte_equal` | three shows: unchanged manifest keeps its audio; re-packaged empties it and restores the old manifest; packaged since empties it and removes the manifest |
| `test_crash_after_emptying_then_rerun_leaves_no_audio_beside_the_restored_manifest[overrides.json / show.json]` | `_durable_write` patched to raise before, or after, the package manifest is copied back; the re-run leaves empty audio beside the snapshot's manifest |
| `test_restore_lists_what_it_does_not_revert` | the new batch and run are listed and the old ones are not; S2 is listed `(voiced)`, S3 plain, an unreadable manifest `(unreadable)`, and S1 (delivered before the snapshot) not at all; the station tree is made read-only during the run and its `_tree_state` (bytes and mtimes) is unchanged |
| `test_restore_recreates_a_show_removed_since` | a show dir removed after the snapshot is re-created, equal to the snapshot |
| `test_restore_renames_the_applied_record` | a failed restore leaves the record in place with no `restored-*` file; a successful one renames it with the same bytes; a later restore with no record renames nothing |

I added three tests beyond the brief, each tightening a guard: `test_a_held_migration_lock_refuses_the_restore`, `test_restore_without_a_delivery_path_skips_the_station_list`, and `test_restore_never_follows_a_symlink_out_of_the_show_dir` (strict surface (a): a symlinked `package/audio` and `.txn` pointing at an outside dir leave the outside file intact).

## RED / GREEN

- **RED:** `./.venv/bin/python -m pytest scripts/test_rekey_overrides.py -q -k "restore or lock_only"` gave `15 failed, 81 deselected`. Every failure was `error: unrecognized arguments: --restore` (`SystemExit: 2`), because the option did not exist.
- **GREEN:** `./.venv/bin/python -m pytest scripts/test_rekey_overrides.py -q` gives `96 passed`. The full suite gives `5372 passed, 1 skipped, 8 deselected`.
- Two test bugs of mine were fixed on the way: a generator using an undefined name, and a wrong assumption that `notes.json` did not exist at snapshot time (gather writes one).

## Mutation check

Run in a scratch copy at `.../scratchpad/mut/` (copies of `scripts/`, `packages/llama/{src,tests}` and `pytest.ini`), fresh per mutant. Settings: `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`, llama shadowed via `PYTHONPATH`. A planted `raise SystemExit` sentinel confirmed the copied script is the one imported (a collection error), and the unmutated copy ran 15 passed.

| mutant | predicted red | result |
|---|---|---|
| M1 never empty audio | empties_audio, crash x2, symlink | empties_audio and crash x2 red; **symlink stayed green** (step 3 unlinks a symlinked `package/audio` on its own: prediction miss, not a gap) |
| M2 empty audio after the copy | crash x2 | as predicted |
| M3 no step 3 | puts_back, empties_audio, symlink | as predicted |
| M4 rename the record before the loop | renames_record | renames_record, plus crash x2 (which assert the record survives) |
| M5 no uncovered gate | created_after | as predicted |
| M6 step 3 follows symlinks | symlink | as predicted |
| M7 keep audio when the snapshot has no package manifest | empties_audio | as predicted |
| M8 station mtime test dropped | lists | as predicted |
| M9 runs/reapply birthtime test dropped | lists | as predicted |
| M10 verify gate dropped | hash_mismatch | as predicted |

## Calls beyond the brief, and which way they lean

1. **A file already byte-equal to its snapshot copy is not rewritten** in step 2. The result is identical; this saves about 40k `F_FULLFSYNC`s on a full library. It leans toward speed, and the end state is the same.
2. **The uncovered gate runs twice, before and under `LOCK`.** Each snapshot file's sha256 is re-checked as it is copied, and the snapshot's package manifest is checked before the keep decision. This leans safe.
3. **`restored: <slug> (audio emptied)`** marks only shows where step 1 actually removed something. The summary line counts them and names v2.17.0's `redo --from package`. This is informational.
4. **Listing failures** (an unlistable `reapply/`, `runs/` or delivery dir) print `  warning: cannot list ...`, and the exit stays 0, since the restore itself succeeded. A failed record rename is exit 1.
5. Symlinks and non-directories inside a show dir are unlinked as links. A show path or path component that is not a real directory raises and stops the run, rather than being guessed at. This leans safe.
6. The output wording for the list headers, `created after the snapshot:` and `renamed:` was my choice; the brief fixed only the route text, the not-reverted line and the next-steps text.

## Concerns

- **A restore from another library's snapshot is not refused.** `--restore` accepts any directory, and the gate only checks that the library holds no show the snapshot lacks; it does not check that `snap` lives under `<root>`. A snapshot from a different root would re-create its slugs here. This is low risk (an explicit operator argument) and was not in the brief; adding a "the snapshot must be under `<root>`" refusal is a one-line follow-up if wanted.
- **Directories that existed but were empty at snapshot time** (snapshots record only files) are removed by step 3's empty-dir cleanup, apart from `package/audio`, which is kept. The spec's "exactly as at the snapshot" is stated over files, so this matches it, but it is a reading.
- The station `(voiced)` test uses `st_mtime`, as the brief says. A destination whose manifest was rewritten in place by emcee after the snapshot (voicing alone, no re-delivery) is also listed. That is arguably right, since it differs from the restored library, but the spec's wording is "re-delivered".
