# t9-impl handback: `emcee retitle` (Task 9) + R9 writer fixes

Status: DONE_WITH_CONCERNS (one small concern, see below)

## Commits (branch programs-lineup)
- 8570e890 emcee: retitle writer carries on past an SMB fchmod refusal and keeps the cause on a failed temp unlink   (R9 a/b/c)
- 7cc39090 emcee: retitle, the program-title backfill   (Task 9 command, docs, tests)

## What was implemented
### R9 (packages/emcee/src/emcee/retitle.py)
- (a) `os.fchmod` on the temp: an OSError whose errno is in `_FCHMOD_REFUSED` = {EPERM, ENOTSUP, EOPNOTSUPP, EINVAL} is non-fatal, so the temp keeps the server's mode. Every other errno stays fatal (before-rename, "the file is unchanged").
- (b) `_swap`: the cleanup `tmp.unlink(missing_ok=True)` is wrapped. If it fails, the failure is added as a note to the in-flight exception and no longer replaces it. An OSError in flight becomes `_BeforeRename(original)`, with the original as the cause. A non-OSError (KeyboardInterrupt) is re-raised as itself. A failing unlink on the not-unchanged branch therefore surfaces as the before-rename failure, with its own OSError as the cause.
- (c) The write-path `_AfterRename` message now reads: `<slug>: checking the mtime after the title write's rename failed (<err>); manifest.json was replaced with this write's bytes (not verified); its mtime unknown`. The put-back path's message is unchanged, since it was out of scope.
- Tests in test_retitle_writer.py: fchmod refusal parametrized over 4 errnos (succeeds, mtime kept), EACCES/EIO stay fatal, unlink failure on the changed-file branch, cleanup unlink failure keeps the ENOSPC cause, KeyboardInterrupt not replaced, and the message test. The two existing regexes were updated to the new message (`AFTER_RENAME`).

### Task 9 (packages/emcee/src/emcee/cli.py)
- `emcee retitle [--station-root] [--dry-run] [--yes/-y]`. `"retitle"` is inserted before `"lock"` in `_COMMAND_ORDER`.
- The plan lines are on stdout, exactly as in the brief: `would write`, `skip … awaiting fix from llama`, `refused`, the summary, `nothing to write`. There is also the optional `stray temp: <slug>/<name>` listing, which is printed in the plan and does not affect the exit code.
- Order: plan, then the confirm (TTY `Proceed?`; with no TTY and no `--yes`, the brief's error and exit 1; a decline prints `nothing written`), then the ps check before the lock, then `station_lock(root, command="emcee retitle")` around the whole write phase.
- If the ps check cannot run (OSError/SubprocessError), it refuses with exit 1 rather than going ahead: fail closed.
- Under the lock (R2): every write in `plan.writes` is re-read first. Any difference or read error gives `refusing: <n> manifest(s) changed since the plan; nothing written; run again` plus the slugs, exit 1. This happens before the backup directory is created.
- Backup directory: `<config.root>/title-backups/<UTC %Y%m%dT%H%M%SZ>/`. A second run in the same second gets `-2`, `-3` and so on, so two runs never share a directory.
- Per show:
  - stat for the mtime;
  - `_save_backup`: `<slug>.json` opened "xb" with the original bytes, flushed and fsynced; then a `{"slug","before_sha256","mtime_ns"}` line appended to `record.jsonl`, flushed and fsynced. Any OSError gives `error: <slug>: backup failed (<err>); stopping before writing it` and `not attempted: <it and the rest>`, exit 1;
  - `write_title`. ANY exception stops the run: `error: <TitleWriteFailed message>`, or `error: <slug>: <Type: msg>` for anything else, then `not attempted: <rest>` (`(none)` when it was the last show), exit 1;
  - None: `skip <slug>: changed since the plan`, listed at the end on stderr, exit 1;
  - success: prints `<slug>: <old> -> <new>` and appends `{"slug","after_sha256"}`. If that append fails, the run stops with exit 1.
- Exit code: 1 for refused, skipped, drift, ps, a held lock, backup/write/verify failures and the no-TTY refusal; otherwise 0. The rule is the same with `--dry-run`.
- Docs: in packages/emcee/CLAUDE.md, a Commands entry covering everything Step 5 lists. That includes the awaiting-fix/unmark/snapshot rationale, the encoding refusal, the mtime and quiet_minutes 10, the lock and ps refusals, the backups, the hand-restore rule (`after_sha256`), and the agent rule. There is also one sentence in the station-lock paragraph.

## Tests: packages/emcee/tests/test_retitle_cmd.py (24 tests) + test_cli_boundary order
All 17 tests the brief names are there. Also: stray-temp listing, declining, ps not runnable, real-writer backup failure ("xb" collision), RuntimeError escaping write_title (parametrized), last-show failure `(none)`, refused with nothing to write.

## TDD evidence
- R9 RED: `./.venv/bin/pytest packages/emcee/tests/test_retitle_writer.py -q` gave 9 failed / 24 passed. These are the expected failures: fchmod refusals raised, the unlink errors replaced the cause, the KeyboardInterrupt was replaced by an OSError, and the message was old. GREEN: 33 passed.
- Task 9 RED: `./.venv/bin/pytest packages/emcee/tests/test_retitle_cmd.py packages/emcee/tests/test_cli_boundary.py -q` gave 1 failed, 6 passed, 24 errors. The errors come from the autouse fixture: it cannot patch `cli.other_tool_processes`, which did not exist yet. The order test also failed. GREEN: 31 passed.
- Final: `./.venv/bin/pytest packages/emcee -q` gave 1293 passed, 1 deselected. The full suite, `./.venv/bin/pytest -q`, gave 6786 passed, 1 skipped, 8 deselected, 26 warnings, all of them from outside emcee (the emcee run shows none). Both are in the log.

## Mutation check (scratch copy in the session scratchpad, PYTHONPATH-shadowed, with `emcee.__file__` printed per mutant and a sentinel string mutant)
Each mutant was caught by the test predicted for it:
- no drift check: test_plan_drift…;
- no lock (`if True:`): the whole-phase, held-lock and drift tests;
- ps refusal disabled: test_ps_refusal…;
- backup removed: the 4 backup tests;
- a None skip that does not fail: test_changed_before_rename…;
- refused ignored: the 3 exit-code tests;
- continuing after a write failure: the 3 write-failure tests;
- sentinel: 2 plan tests.

## Self-review / concerns
- Concern (small): a backup is `os.fsync`'d per file, but the backup directory itself is never fsynced, and on macOS there is no F_FULLFSYNC. That is enough for the R6 case (os._exit leaves kernel buffers intact). Against power loss, though, the directory entry may not be durable. The backups live on the local emcee root (APFS). Say if you want a dir fsync or F_FULLFSYNC added.
- The plan and per-write lines go to stdout, and errors and refusals to stderr, as `emcee run` does. The `changed since the plan: …` end listing goes to stderr.
- The real `procs.other_tool_processes` is not run by the command tests: they patch it, so the operator's machine cannot make them flaky. Task 8 tests it.
- The command adds a `backups: <dir>` line on stdout, so the operator knows where the backups are. The brief does not mention it.

---
# Fix round 1 (R10), commit b7e137a6

## Changes
1. packages/emcee/CLAUDE.md, hand restore:
   (a) After putting a file back, set its mtime to the record's `mtime_ns` (`os.utime(path, ns=(atime, mtime_ns))`). A plain cp gives a fresh mtime, and hugo then drops those planned shows for `quiet_minutes`.
   (b) A slug with a before line and no after line was one of: skipped as changed, put back after a failed verify, an after-rename failure, a failed after-append, or a kill between rename and append. In the last three the file may hold this run's bytes. The rule leaves every such file alone, so check it by hand: if its sha256 equals `before_sha256` it is the original; otherwise compare it with the backup plus only the new `dj_audio.title`, in emcee's encoding.
   The backup sentence now also says the directory entries are fsynced.
2. cli.py: new `_fsync_dir(path)`, plain fsync on an O_RDONLY fd. It fsyncs:
   - `<emcee root>`, when `title-backups/` is first created;
   - `title-backups/` and the new run dir after the run dir's mkdir;
   - the run dir after each show's `<slug>.json` and its record line, inside `_save_backup`.
   The last one goes beyond "once after mkdir". An fsync of an empty run dir right after mkdir would not make the backup files created later durable, and the ruling's stated goal is that the backup entries survive power loss. It costs one dir fsync per show, on local disk.
   A dir-fsync failure in `_save_backup` is a backup failure (stop before that show). One in `_backup_run_dir` is "cannot create the backup directory" (nothing written).
3. test_plan_drift_under_the_lock_refuses_the_whole_run: `Path.read_bytes` is wrapped so that each manifest read after the plan records whether the lock is held. "Held" means `sl._held` is set and the lock file exists with `command: emcee retitle`. The test asserts `reread == [("a", True), ("b", True), ("c", True)]`; the test's own snapshot reads are excluded.
4. Renamed to test_backup_failure_of_the_real_writer_on_an_existing_backup_file.

New tests:
- test_backup_dirs_and_entries_are_fsynced_before_the_first_write: fsynced fds are matched to dev and inode, and it checks the home, title-backups and run dir fsyncs, plus a run-dir fsync after each show's entries, all before that show's write_title.
- test_a_dir_fsync_failure_is_a_backup_failure.

## Mutants (scratch copy, PYTHONPATH-shadowed, import path printed per mutant)
- Drift re-read moved into retitle_cmd before `station_lock`: caught by the drift test.
- Run-level dir fsyncs removed: caught by the fsync test.
- Root fsync removed: caught by the fsync test.
- Per-show dir fsync removed: caught by the fsync test and the dir-fsync-failure test.
- Baseline: 26 passed.

## Tests
`./.venv/bin/pytest packages/emcee -q`: 1295 passed, 1 deselected.
