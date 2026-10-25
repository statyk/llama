# Task 18 (`--snapshot`) implementer handback

Status: DONE. Commit `73a0f61` feat(scripts): rekey_overrides --snapshot (on c95c5cd, branch held-backlog-junk-filter).
Files: scripts/rekey_overrides.py, scripts/test_rekey_overrides.py.

## Built, per contract item
- `snapshot(root, *, echo, now=None) -> Path`. In order:
  1. Refuses when `<root>/shows` is not a directory.
  2. Process gate: `llama_processes(_ps_lines(), self_pid=os.getpid())`, Task 17's function, not re-implemented. If it finds anything, every line is echoed and the snapshot refuses. If the check itself raises, it refuses with `process check failed: ...`. Otherwise it prints `none` plus PROCESS_NOTE.
  3. Form gate over `library_shows(root)`: any overrides.json that `classify` reads as `filename` or `mixed` is listed with its `filename_values` and refused. Nothing is created by a refusal at this point, `.rekey.lock` included (tests compare the whole tree state).
  4. Takes `<root>/.rekey.lock` (`file_lock`, non-blocking; held elsewhere means refuse).
  5. Names the dir `rekey-snapshot-<now UTC %Y%m%dT%H%M%SZ>` and refuses if it already exists. An existing dir is left untouched (tested). A naive `now` raises ValueError.
  6. Records `slugs = library_shows(root)`, taken under the lock.
  7. Per show, under `file_lock(ws.lock)` (blocking): copies every file outside `package/audio/` and `.audio-aside/`, with the top-level `.lock` set aside. Each copy is written with O_EXCL and flushed with `catalog._sync_fd` (F_FULLFSYNC) on the write fd. It is then re-read and its sha256 compared with the source bytes' sha256. Every directory the copy created is then flushed.
  8. `manifest.json` = {created_at (UTC ISO of start), slugs, files {"<slug>/<rel>": sha256}}. It is written as `.manifest.json.tmp`, flushed, renamed, and the snapshot dir is flushed.
  9. Finally `verify_snapshot(snap)` runs over the written snapshot. Any problem fails it.
  10. Any exception, BaseException included, unlinks manifest.json first and then rmtrees the partial dir. An Exception becomes `_Refused("snapshot failed: ...; removed <snap>")`. KeyboardInterrupt is re-raised after the cleanup.
  11. Success echoes `snapshot: <snap> (N shows, M files, <size>, <secs> s)`. The timing is there for premise 9. A progress line prints every 100 shows.
- `main`: a mutually exclusive group with `--snapshot`, so Tasks 19 and 20 add `--apply`/`--restore` to it. The identity check and config load are unchanged. A `_Refused` message from the snapshot is printed to stdout and exits 1.
- `.lock`-only husk: `_is_husk` means no entry other than the top-level `.lock`, at any depth. A file, symlink or other non-directory counts as content.
  - `library_shows(root)` = `_show_dirs` minus husks. It is a shared helper for the coverage checks in Tasks 19 and 20.
  - A husk is not recorded and not copied, and the snapshot verifies.
- `verify_snapshot(snap) -> list[str]` reports these problems:
  - no manifest.json, or one that cannot be read;
  - a manifest that is not an object;
  - a `created_at` that is not a UTC-offset ISO string;
  - `slugs` that is not a list of non-empty strings;
  - `files` that is not str -> str;
  - an entry whose file is missing (a symlink counts as missing) or whose sha256 differs;
  - a recorded slug with no entry.

  Two problems go beyond the brief: an entry whose slug is not recorded, and a key that is not `<slug>/<path>` inside the snapshot (absolute, `..`, `.`, empty part, backslash). Both lean toward refusing, and both matter because `--restore` copies entries back by key. Unlisted files (`.DS_Store`) are no problem.
- `find_snapshot(root)`: the lexically newest `rekey-snapshot-*` *directory* holding a `manifest.json` (a file). It does not verify.

## Judgment calls (beyond the brief, all toward refusing; flag if unwanted)
1. **An unreadable overrides.json also blocks `--snapshot`.** This covers invalid JSON, a non-object, or an OSError. Such a file cannot be shown not to hold a filename value. The runbook needs the dry run at 0 refused first anyway, and the dry run refuses `unreadable`.
2. **The form check is repeated under each show lock,** on the bytes actually copied. An overrides.json rewritten to the filename form between the pre-check and the copy fails the snapshot.
3. **A show dir that is not a husk but has nothing to copy fails the snapshot**, naming the dir. An example is a dir holding only `package/audio/*`. Otherwise its recorded slug would have no entry and the snapshot would never verify.
4. **A symlink, fifo or other non-regular entry in a show dir fails the snapshot.** It cannot be copied faithfully. So does a show dir that is itself a symlink.
5. **`--snapshot` refuses a root with no `shows/` dir.** This guards against a mistyped config root producing an empty "rollback point".
6. **The flush happens before the re-read.** The copy is flushed on its write fd, then re-read and hashed; the brief's order is re-read, then flush. Both happen before the manifest. The order avoids the SMB read-only-fd EACCES that `_flush_to_disk` documents.
7. **A `.txn/` present at snapshot time is copied.** The brief excludes only `package/audio/` and `.audio-aside/`.

## RED / GREEN
- RED: I wrote the tests first.

  `./.venv/bin/python -m pytest scripts/test_rekey_overrides.py -q` gave `20 failed, 34 passed`. The failures were:
  - SystemExit 2 (`unrecognized arguments: --snapshot`) x11;
  - AttributeError: no `snapshot` x2, no `_write_copy` x2, no `find_snapshot`, no `library_shows`;
  - 2 lock-thread waits timing out.
- GREEN: `./.venv/bin/python -m pytest scripts/test_rekey_overrides.py -q` gives `54 passed`.
- Full suite: `./.venv/bin/python -m pytest -q` gives `5330 passed, 1 skipped, 8 deselected, 26 warnings in 42.34s`. `llama.__file__` resolves inside this worktree.

Tests added (20, one parametrized x3):
- the ones the brief names:
  - snapshot_copies_every_metadata_file_and_no_audio_or_lock
  - lock_only_show_dir_is_not_a_show
  - snapshot_hashes_verify
  - a_copy_that_differs_from_its_source_fails_the_snapshot (asserts the per-copy message)
  - snapshot_refuses_a_library_holding_a_filename_value[filename|mixed|unreadable]
  - snapshot_refuses_while_llama_runs (also a failing ps)
  - snapshot_takes_the_migration_lock_and_each_show_lock (thread: waits on a held show lock while holding `.rekey.lock`, no manifest yet, then completes and releases)
  - directory_without_manifest_is_no_snapshot
  - verify_snapshot_problems
  - verify_snapshot_ignores_unlisted_files
- extra ones:
  - names_its_directory_by_the_utc_start_and_refuses_an_existing_one
  - a_show_dir_holding_only_audio_fails_the_snapshot
  - a_failure_after_the_manifest_is_written_removes_it
  - an_interrupt_removes_the_partial_snapshot
  - a_held_migration_lock_refuses_the_snapshot
  - an_overrides_json_rewritten_before_its_show_lock_fails_the_snapshot
  - a_symlink_in_a_show_dir_fails_the_snapshot
  - snapshot_refuses_a_root_without_shows

## Mutation check (scratch copy only)
Setup:
- The copy was made with `git ls-files | tar` into the scratchpad.
- Tests ran from an empty cwd with `PYTHONPATH=<copy>/packages/{llama,herder,emcee}/src`, `PYTHONDONTWRITEBYTECODE=1` and `-p no:cacheprovider`.
- Shadowing was checked first: `llama.__file__` and `rekey_overrides.__file__` both resolved in the copy, and the copy's baseline was 54 green.

The red test for each mutant was named before it ran. All 12 were CAUGHT by their named test:

| Mutant | Named red test |
|---|---|
| M1: verify skips the sha compare | verify_snapshot_problems |
| M2: no per-copy compare | a_copy_that_differs... |
| M3: no re-check under the lock | an_overrides_json_rewritten... |
| M4: husk counted | lock_only_show_dir... |
| M5: package/audio copied | snapshot_copies... |
| M6: verify skips the slug coverage | verify_snapshot_problems |
| M7: partial not removed | a_copy_that_differs... |
| M8: pre-lock form gate off | refuses_a_library...[x3] |
| M9: no show lock | takes_the_migration_lock... |
| M10: no process gate | refuses_while_llama_runs |
| M11: find_snapshot ignores the manifest | directory_without_manifest... |
| M12: husk ignores nested content | a_show_dir_holding_only_audio... |

## Concerns
- **Speed (premise 9).** One F_FULLFSYNC per copied file plus one per directory, over about 600 shows x about 10 files. That could take tens of seconds or more on the real disk. The success line prints the elapsed time, so the operator's premise-9 timing reads it directly.
- **What the re-read proves.** The re-read hash catches write-path corruption. It reads from the page cache, not the medium, so it does not prove what is on the platter.
- **Brief tests left for later tasks.** `test_lock_only_show_dir_is_not_a_show` covers only the snapshot and verify parts. "--apply and --restore do not refuse on it" belongs to Tasks 19 and 20, which should use `library_shows` for their coverage checks.
- **One touch outside the library rules, for full disclosure.** While checking that F_FULLFSYNC works on a directory fd, I opened `~/.llama` read-only and issued F_FULLFSYNC on it once. That flushed the drive cache and wrote nothing. The script was never run against ~/.llama.
