# t6-impl handback: Task 6, run lock and `running` in readers

Status: DONE_WITH_CONCERNS (minor: see Concerns)
Commit: e6e210c feat(runs): run lock on every command that works a run; readers report running
Suite: `./.venv/bin/pytest -q` -> 3902 passed, 1 skipped, 8 deselected (84.65s). No existing test needed adjusting.

## What I implemented
- `locks.RunMissing(Exception)`.
- `locks.run_lock(run_dir, *, blocking)`: opens `run_dir/.lock` with O_CREAT|O_RDWR but never mkdirs. FileNotFoundError or NotADirectoryError from the open raises RunMissing. Non-blocking on a held lock raises `Locked`. After acquiring (blocking or not) it compares `fstat(fd)` with `stat(run_dir/.lock)` on (st_ino, st_dev). A mismatch, or FileNotFoundError from the stat, raises RunMissing. The lock is always released and the fd closed in `finally`. Non-POSIX: RunMissing if the dir is missing, otherwise a no-op (follows file_lock's pattern).
- `locks.run_is_live(run_dir)`: O_RDONLY open of an existing `.lock` only (no O_CREAT). A missing file or dir is False. It tries LOCK_EX|LOCK_NB and releases at once. Only BlockingIOError counts as live; any other OSError propagates rather than reading as "not live".
- `RunWorkspace.lock = dir / ".lock"`.
- `sessions.STATE_RUNNING = "running"`. `iter_sessions(root, *, probe_live=True)` reports `running` for a live run whatever its marker says. `session_state()` never probes (docstring says why). Because of this, `attention_sessions` includes a live run even when its marker is complete.
- `cli._run_locked(ws, *, blocking=False)`: built with an ExitStack so that only the acquisition is wrapped in the except clauses. `Locked` prints `run <id> is in progress in another process` to stderr and raises Exit(1). `RunMissing` prints `run <id> no longer exists` and raises Exit(1).
- Wiring (each lock is taken once at command entry and held to exit; none is inside `_execute`):
  - `get` query form: with no `--name`, `claim_run_dir` creates the dir. With `--name`, `(runs/name).mkdir(parents=True, exist_ok=False)` succeeds (created) or raises FileExistsError (existing). The lock is `_run_locked(ws, blocking=created)`, taken before request.json, the preflight gate and interpret. An existing non-live dir is reused exactly as before.
  - `get --profile`: `claim_run_dir`, then `_run_locked(ws, blocking=True)` before request.json and criteria.json.
  - `run resume`: `_run_locked` right after `_resolve_run`, before any read.
  - `run approve`: `_run_locked` at entry, before the shortlist prints or any prompt.
  - `redo --run X --from search|winnow`: `_run_locked` in `_redo_run_level` before any read. The show-stage `--run` form is unchanged.
  - `run rm`: `_run_locked`, then `session_state`, the prompt, and `shutil.rmtree(ws.dir)`, all while the lock is held.
- Readers:
  - `_ATTENTION_LABELS[STATE_RUNNING] = "running"` and `_NEXT_STEP[STATE_RUNNING] = "in progress"`.
  - `_session_json`'s `next` is None for a running run.
  - `_by_run_rollup` rows gain `"running": run_is_live(d)`.
  - The `status --by-run` text row appends `  [running]` when that is true.

## Tests (packages/llama/tests/test_run_lock.py, 18 tests)
All the tests the brief names are in place:
- test_run_lock_never_creates_a_missing_run_dir
- test_run_is_live_does_not_create_the_lock_file
- test_resume_refuses_a_live_run
- test_approve_refuses_a_live_run_before_prompting
- test_redo_run_level_refuses_a_live_run (search and winnow)
- test_rm_refuses_a_live_run (with and without --yes)
- test_get_takes_a_blocking_lock_on_its_fresh_dir (query and profile)
- test_get_name_creates_and_locks_its_dir (also checks that an existing non-live dir is reused under a non-blocking lock)
- test_get_name_existing_live_run_is_refused
- test_no_self_deadlock_get_to_execute
- test_no_self_deadlock_resume_to_execute
- test_run_list_reports_running
- test_status_by_run_marks_running
- test_lock_on_a_replaced_lock_file_is_run_missing, parametrized over three replacements:
  - lock-file: unlink and recreate `.lock` (the inode-mismatch branch)
  - dir-with-lock: rmtree, mkdir and touch `.lock` (the inode-mismatch branch)
  - dir-only: rmtree and mkdir (the stat FileNotFoundError branch)

Extras:
- test_run_lock_non_blocking_on_a_held_run_is_locked
- test_rm_holds_the_lock_through_rmtree (a wrapped rmtree sees `run_is_live` True)

How the tests are built:
- **Second holder:** a real `fcntl.flock` on another fd.
- **Refusal tests:** they snapshot every file's bytes and mtime_ns under the run dir and assert nothing changed. They also assert that `_execute` was never called.
- **get tests:** they wrap `cli.run_lock` to record `(blocking, request.json existed?)`. A stubbed `_execute` checks that a non-blocking probe raises `Locked`. The recorder asserts `(True, False)`, which pins both "blocking" and "locked before request.json".
- **Replaced-lock test:** deterministic, with no sleeps. `locks.fcntl` is swapped for a proxy whose first LOCK_EX call on the acquirer thread performs the replacement and sets an event before calling the real flock. The main thread waits on the event and then releases the holder. The test asserts that the acquirer raised RunMissing. It also asserts the acquirer holds nothing: the holder's fd can re-take the old inode with LOCK_NB, and `run_is_live` is False.
- **No-self-deadlock tests:** these run the real `_execute` with `run_search`, `run_winnow`, `process_show` and `make_client` stubbed. Each stub records `run_is_live` (True throughout). The command runs in a daemon thread with `join(30)` as a hang detector (not a correctness timer), and the tests assert a complete marker and that the lock is released at exit.

## TDD evidence (all in t6-impl.log)
- RED 1: `./.venv/bin/pytest packages/llama/tests/test_run_lock.py -q`. The collection ImportError `cannot import name 'RunMissing' from 'llama.locks'` was expected because nothing existed yet.
- RED 2: I added stubs to locks.py (RunMissing, plus run_lock and run_is_live raising NotImplementedError) and changed nothing in cli. Result: 18 failed, each for the expected reason:
  - NotImplementedError from run_lock or run_is_live.
  - `cli has no attribute 'run_lock'` for the three get tests.
  - Refusal tests exited 0 ("removed session r1", the approve prompt and the shortlist printed).
  - The status row had no `[running]`.
  - The deadlock tests failed on NotImplementedError('run_is_live') from inside a stage.
- RED 3: the replaced-lock test first failed on a test bug: the holder opened `.lock` without O_CREAT. After the fix it failed as expected, because the event never fired against the stub.
- GREEN: `./.venv/bin/pytest packages/llama/tests/test_run_lock.py -q` gave 18 passed. The full suite gave 3902 passed, 1 skipped.

## Mutation pass (a scratch `git archive` copy run with `python -m pytest`, PYTHONPATH shadowing verified, PYTHONDONTWRITEBYTECODE=1, a fresh copy per mutant)
Each mutant was caught by exactly the predicted tests:

| Mutant | Change | Caught by |
|---|---|---|
| M1 | inode check disabled | replaced[lock-file], replaced[dir-with-lock] (dir-only stays green through the stat branch, as predicted) |
| M2 | run_is_live with O_CREAT | test_run_is_live_does_not_create_the_lock_file |
| M3 | run_lock mkdirs run_dir | test_run_lock_never_creates_a_missing_run_dir |
| M4 | get takes `blocking=False` on a created dir | test_get_takes_a_blocking_lock_on_its_fresh_dir, test_get_name_creates_and_locks_its_dir |
| M5 | no probe in iter_sessions | test_run_list_reports_running |
| M6 | rollup `running` always False | test_status_by_run_marks_running |
| M7 | `next` not None when running | test_run_list_reports_running |
| M8 | request.json written before the lock | the three get tests |

## Files changed
- packages/llama/src/llama/locks.py
- packages/llama/src/llama/sessions.py
- packages/llama/src/llama/workspace.py
- packages/llama/src/llama/cli.py
- packages/llama/tests/test_run_lock.py (new)

## Interpretations / concerns
1. `_run_locked` has the brief's signature plus an optional keyword `blocking=False`, so `_run_locked(ws)` behaves exactly as specified. `get` uses `blocking=created`, which keeps every lock going through `cli.run_lock` (the name the brief's test monkeypatches). If a fresh blocking lock in `get` raises RunMissing (an rm landed in the documented create-to-lock window, or the lock file was replaced), get prints `run <id> no longer exists` and exits 1. The brief and spec do not specify that output.
2. `run list` on a running run still prints the marker's outcome and failure lines from the previous attempt. The spec doesn't say whether to suppress them, so I left them unchanged.
3. No tombstone or retry was added for the documented `.lock`-husk window (operator ruling).
4. The full suite shows 26 DeprecationWarnings ("multi-threaded, use of fork()") from test_atomic_write, test_concurrency, test_ledger_concurrency, test_locks and test_sessions. test_atomic_write runs before test_run_lock, and my threads are all joined, so I believe these predate this task. I did not run a baseline to confirm it.
5. The full suite took 85s, so I ran it in the background teed to the log, as mandate 2 requires.
