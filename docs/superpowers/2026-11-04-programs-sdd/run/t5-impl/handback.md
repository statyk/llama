# t5-impl handback: Task 5, emcee station lock and `emcee lock show|clear`

Status: DONE_WITH_CONCERNS (minor; see Concerns)
Commit: b0be756a emcee: station lock and emcee lock show/clear

## What was implemented
- `packages/emcee/src/emcee/station_lock.py`: `LOCK_NAME`, `MAGIC`, `StationLocked(EmceeError)` (.path, .holder; message and details exactly per brief), `StationLockReentry(RuntimeError)`, frozen `Held`, `acquire`, `release`, `station_lock` context manager, `read_lock`, `holder_text`, `token_of`.
  - Module-level `_held` re-entry guard checked before any filesystem call.
  - `acquire`: `os.open(O_CREAT|O_EXCL|O_WRONLY, 0o644)`; write loop + fsync; on any write/fsync failure, close + unlink + re-raise. `FileExistsError` -> read the holder -> `StationLocked`. If the file vanished while being read, the holder is `(lock vanished while reading)`, still a refusal, never retried. If it can't be read, the holder is `(cannot read the lock: ...)`. Any other create OSError -> `EmceeError("cannot create the station lock at {path}: [Errno n] strerror")`, raised `from None`.
  - Contents: `lma-station-lock 1 <token_hex(16)>`, then `tool: emcee`, `command:` (whitespace collapsed to one line), `host: socket.gethostname()`, `pid:`, `started: datetime.now().astimezone().isoformat(timespec="seconds")`, with a trailing newline.
  - `release`: re-reads the file and unlinks only on its own token. If the token is foreign or the file is missing, it warns `... was not ours at release ({holder or 'missing'}); writes since {started} ran unguarded`; the holder lines are joined with "; " to keep the warning on one line. A read or unlink OSError gives the `could not remove ... clear it with: emcee lock clear` warning. It never raises and always clears `_held`.
  - `station_lock`: on the main thread it installs SIGTERM/SIGHUP -> `SystemExit(128+signum)`, then acquires at `Path(delivered).absolute() / LOCK_NAME`, both inside one try. The finally releases only if this call acquired, then restores the previous handlers (a `None` previous handler becomes SIG_DFL).
  - `holder_text`: lenient UTF-8 decode (backslashreplace), with control characters escaped so a garbage file can't drive the terminal; `(empty lock file)` for empty contents.
- `cli.py`: `lock` sub-app with `show [--station-root]` and `clear [--station-root] [--yes/-y]`. `_COMMAND_ORDER` gains "lock" after "say". `clear` never acquires the lock. It prints the path and holder; with no TTY and no `--yes` it exits 1 (`pass --yes`); the prompt is `Remove this lock? [y/N]` (on stderr, like `run`'s). It re-reads and compares bytes (a changed or vanished lock prints `the lock changed since it was shown; run again` and exits 1), unlinks, then prints `station lock removed`. With no lock it prints `no station lock at {path}` and exits 0.

## Tests
- `test_station_lock.py` (18): every test listed in the brief. Extras: lock vanished while reading, release read-error warns, read_lock/token_of edge cases. The signal tests share the helper `_signal_releases_the_lock`.
- `test_lock_cmd.py` (11): every test listed in the brief. Extras: `--station-root`, confirm-at-prompt, declined, vanished-after-display, clear with no lock.
- `test_cli_boundary.py`: the expected order now has "lock" after "say".

## TDD evidence
- RED: `./.venv/bin/pytest packages/emcee/tests/test_station_lock.py packages/emcee/tests/test_lock_cmd.py packages/emcee/tests/test_cli_boundary.py -q` -> `ModuleNotFoundError: No module named 'emcee.station_lock'`, 2 collection errors. Expected, because the module did not exist yet.
- GREEN: same command -> `36 passed in 3.50s`. `./.venv/bin/pytest packages/emcee -q` -> `1185 passed, 1 deselected`. Full suite `./.venv/bin/pytest -q` -> `6675 passed, 1 skipped, 8 deselected, 26 warnings`. The warnings come from elsewhere: the new test files pass under `-W error`.
- Mutation run in a scratch copy (git archive in the scratchpad; `python -m pytest` with PYTHONPATH shadowing, no bytecode). A planted sentinel was caught, which proves the copy was the code under test. The predicted test caught each mutant:
  - token check removed in release: caught by test_release_unlinks_only_its_own_token
  - re-entry guard disabled: caught by test_second_acquire_in_one_process_raises_reentry
  - no unlink after a failed write: caught by test_write_failure_after_create_removes_the_file
  - handlers not restored: caught by test_previous_signal_handlers_are_restored
  - signal handler a no-op: caught by test_sigterm and test_sighup

## Self-review / concerns
1. `Held` has a third field, `started: str = "?"`. The brief lists only `path` and `token`, but the release warning needs `{started}`, and a default keeps `Held(path, token)` constructible. Task 10 may mirror or drop it.
2. Declining at the `Remove this lock?` prompt prints `station lock kept` and exits 0, matching `run`'s decline. The brief didn't specify this.
3. Mode 0o644 is passed to os.open, so it is subject to umask (no fchmod; fchmod might fail over SMB).
4. The CLAUDE.md docs were not touched (that's Task 6's job).
5. I ran a read-only `git stash list` once by accident. It changed nothing, but the mandate says never run git stash in any form.

---

# Fix round 1 (review: $D/t5-review/handback.md)

Commit: 395e6455 emcee: station lock leaves no lock on a signal or close error in acquire/release

## Changes
- **Important 1(a)**: `acquire` now calls `os.close(fd)` inside the protected try. A `fd_open` flag is cleared just before the close, so the cleanup never closes the fd twice; the fd is released even when close reports an error. The cleanup's own close is non-fatal (OSError ignored), so the unlink always runs.
- **Important 1(b)**: on the main thread, `station_lock` blocks SIGTERM and SIGHUP with `signal.pthread_sigmask(SIG_BLOCK, ...)` around `held = acquire(...)` and around `release(held)`, and restores the previous mask with SIG_SETMASK. The unblock sits in the `finally` right after the assignment, so a pending signal fires only once `held` is set (and the outer finally releases), or once release has finished. The helpers are `_block`/`_unblock` with `_SIGNALS`. The docstring now states that off the main thread no handlers are installed and nothing is blocked.
- **Minor 2**: `read_lock` turns any non-ENOENT OSError into `EmceeError("cannot read the station lock at {path}: [Errno n] strerror")`; this covers `lock show` and both reads in `lock clear`. `lock clear`'s unlink turns a non-ENOENT OSError into `EmceeError("cannot remove the station lock at {path}: [Errno n] strerror")`. A shared `_reason(exc)` helper formats the errno.
- **Minor 3**: `release` now handles FileNotFoundError from either the read or the unlink with one handler, which gives the "not ours at release (missing)" warning.
- Not done: review Minor 1 (the TOCTOU in `lock clear`) and Minor 4 (fsync); the controller didn't ask for them.

## Covering tests (new)
- `test_station_lock.py`:
  - `test_close_error_after_write_removes_the_file`: close does the real close, then raises EIO once. The OSError propagates, close is called exactly once, no file remains, and `_held` is None.
  - `test_sigterm_in_acquire_or_release_leaves_no_lock[after-open|after-close|after-acquire|in-release]`: each runs in a subprocess that sends itself SIGTERM in that window. Each must exit 143 with no lock file. For the acquire windows the body never runs; for `in-release` the body has run.
  - `test_release_warns_missing_when_the_lock_vanishes_before_unlink`
  - `test_read_lock_error_other_than_missing_is_a_refusal` (a directory at the lock path)
- `test_lock_cmd.py`:
  - `test_lock_show_unreadable_lock_is_an_error_not_a_traceback` (chmod 0, EACCES)
  - `test_lock_clear_directory_at_the_lock_path_is_an_error`
  - `test_lock_clear_unlink_error_is_an_error_not_a_traceback` (`Path.unlink` raises PermissionError)

## Commands and output
- `./.venv/bin/pytest packages/emcee/tests/test_station_lock.py packages/emcee/tests/test_lock_cmd.py packages/emcee/tests/test_cli_boundary.py -q -W error`: 46 passed
- `./.venv/bin/pytest packages/emcee -q`: 1195 passed, 1 deselected
- Mutants of the fixes were run in a scratch copy (cp to the scratchpad, `python -m pytest` with PYTHONPATH shadowing and no bytecode). The planted sentinel was caught. Each mutant was caught by the predicted tests:
  - mask disabled: caught by after-open, after-acquire and in-release
  - close moved back out of the try: caught by close_error and after-close
  - cleanup always closes: caught by close_error (the double close)
  - unlink's FileNotFoundError warning "could not remove": caught by vanishes_before_unlink. My first try at this mutant was equivalent: `OSError(ENOENT)` constructs a FileNotFoundError. I replaced it with a faithful mutant.
  - the CLI unlink handler removed: caught by unlink_error
  - the read_lock handler removed: caught by read_lock_error, show_unreadable and clear_directory

## Note for Task 10
The mask must be applied in the context manager itself, not inside a helper that returns: if `held = helper(...)` unblocks inside the helper, the signal fires before the assignment. `pthread_sigmask` runs `PyErr_CheckSignals` on return, so the handler raises out of the unblock call itself.

---

# Fix round 2 (re-review: $D/t5-rereview1/handback.md)

Commit: (see the reply; the fix-2 commit on programs-lineup, "emcee: a signal anywhere around the station lock's hold releases it")

## Shape chosen
I chose neither (a) nor (b) exactly. Both still leave the first signal's own window open: an exception raised at the `finally` entry, or inside contextlib's `__exit__` before the generator resumes, happens before any try that could catch it. Instead, **the handler itself releases.**

- `_raise_exit(signum)`: if `_held` is set, it blocks both signals, calls `release(_held)`, restores the mask, then raises `SystemExit(128+signum)`. Wherever the signal lands (in the body, at the finally entry, in contextlib's exit, or just before the release-side block), the lock is released before the exception propagates.
- The `finally` releases only `if held is not None and _held is held`, so a lock the handler already released is not released twice and gives no spurious "missing" warning.
- Acquire and release still run with both signals blocked. The handler then never runs while `acquire` is half-way (the lock not yet recorded in `_held`) or while `release` is half-way.
- **Minor (mask):** `station_lock` reads the main thread's mask once at entry (`pthread_sigmask(SIG_BLOCK, [])`) into the module's `_base_mask`. `_unblock` always restores that mask and never a value returned by `_block`, so a `_block` that raises after blocking can't leave the signals blocked. The outer `finally` also restores it unconditionally, after restoring the handlers.
- The structure is still small for Task 10: `_block`/`_unblock`/`_raise_exit`, and one `try/finally` each for acquire and release.

## Trade-off for the controller to judge
A signal inside the body now releases the lock as the signal is handled, before the body's own `except`/`finally` clauses unwind. Before this round, the release came after the body unwound. A body whose cleanup writes to the station could therefore do that cleanup unguarded for a moment. Station writes are temp-plus-rename, so their cleanup is removing their own uniquely named temp file, which is harmless. Task 6 and Task 9 callers should not put station writes in `finally`/`except` clauses inside the `with`. This was the only shape I found that closes the window that opens once the body has ended.

## Tests
- The window test, renamed `test_sigterm_in_any_window_leaves_no_lock_and_no_blocked_signals`, now has 8 modes. Each runs in a subprocess, catches the exit, and checks that SIGTERM/SIGHUP are not blocked afterwards. Each must exit 143, leave no lock file and print no warning:
  - the 4 from round 1: after-open, after-close, after-acquire, in-release;
  - `before-acquire-block` and `before-release-block` (the reviewer's injection);
  - `second-in-release` (a second SIGTERM while the handler releases);
  - `second-in-unwind` (a second SIGTERM in the body's finally while the first unwinds).
- `test_signal_mask_is_restored`: the mask is unchanged inside the body, after a normal exit, and after a refused acquire.
- The reviewer's script `rr1/gap.py` against the worktree: `pre-release-block` gives rc=143, no lock, `mask-has-TERM False`. `pre-acquire-block` gives the same.

## Commands and output
- `./.venv/bin/pytest packages/emcee/tests/test_station_lock.py packages/emcee/tests/test_lock_cmd.py -q -W error`: 44 passed
- `./.venv/bin/pytest packages/emcee -q`: 1200 passed, 1 deselected
- Mutants run in a scratch copy, with a planted sentinel that was caught:
  - the handler no longer releases: caught by `[before-release-block]`, as predicted;
  - the handler's mask restore removed: caught by `[second-in-release]` and `[second-in-unwind]`;
  - the outer finally's final `_unblock` removed: **not caught**. It is defence in depth for a pending signal raised out of `signal.signal` while the handlers are restored, and I found no reliable way to inject it.

---

# Fix round 3 (Ruling R6; re-review 2: $D/t5-rereview2/handback.md)

Commit: 56df66a0 emcee: SIGTERM/SIGHUP release the station lock and exit the process

## Changes (station_lock.py)
- **Handler** `_exit_on_signal` replaces `_raise_exit`. If `_held` is set, it blocks TERM/HUP and calls the same token-checked `release`. In a `finally` it then flushes sys.stdout and sys.stderr (errors swallowed) and calls `os._exit(128 + signum)`. It never returns or raises, so no caller `except`/`finally` runs after the signal. SIGINT is untouched.
- **Removed** (it existed only to survive a SystemExit unwinding):
  - the module `_base_mask` snapshot and SIG_SETMASK restore;
  - the `_held is held` guard in the `finally` (the handler never returns, so if the `finally` runs the handler did not fire);
  - the final unconditional `_unblock`.
- **Kept:** TERM/HUP blocked around `acquire` and around `release`. Each `_block` is now *inside* its `try`, so the matching `_unblock` always runs. The handler's release guard (`if held is not None`) is also kept.
- **Re-review 2 Minor 1:** `station_lock` computes, at entry, `unblock`: the lock signals that were not blocked then (None off the main thread). `_unblock` uses `SIG_UNBLOCK` on just those. A mask change the body makes, or a lock signal the caller had already blocked, is left alone.
- **Re-review 2 Minor 2** (the handler releasing a worker thread's lock in the re-entry-bug window) is moot now: the handler ends the whole process, so no worker keeps writing.
- **Module docstring:** the handler exits the process, callers' cleanup does not run on TERM/HUP, and station writes must stay atomic renames. SIGINT unwinds normally. The `station_lock` docstring is updated to match.

## Tests
- `test_signal_in_any_window_releases_and_exits_without_running_caller_code` has 9 modes, each in a subprocess:
  - after-open, after-close, after-acquire, in-release;
  - before-acquire-block and before-release-block;
  - second-in-release;
  - in-body;
  - in-body-hup (the SIGHUP case, exit 129).

  Each asserts:
  - exit 128+signum, no lock file, no warning;
  - "after" and the caller's `finally` marker are never printed;
  - the body's `finally` marker prints only when the body had already finished before the signal (in-release, before-release-block);
  - an unflushed print before the signal still reaches stdout.
- The round-2 `second-in-unwind` mode was dropped: there is no longer an unwind for a second signal to land in.
- `test_signal_exit_flushes_the_release_warning`: a foreign lock mid-hold followed by SIGTERM gives exit 143, the "not ours at release" warning reaches stderr, and the foreign lock is left.
- `test_only_the_lock_signals_are_unblocked`: SIGUSR1 blocked by the body stays blocked, SIGHUP blocked by the caller before entry stays blocked, and SIGTERM is unblocked.
- `test_signal_mask_is_restored`, and the sleep-based `test_sigterm`/`test_sighup_releases_the_lock`: unchanged, still pass.

## Commands and output
- `./.venv/bin/pytest packages/emcee/tests/test_station_lock.py packages/emcee/tests/test_lock_cmd.py -q -W error`: 47 passed
- `./.venv/bin/pytest packages/emcee -q`: 1203 passed, 1 deselected
- Mutants run in a scratch copy, with a planted sentinel that was caught:

| Mutant | Caught by |
|---|---|
| `os._exit` replaced by `raise SystemExit` | all 9 window modes |
| no flush | in-body, in-body-hup, second-in-release |
| handler doesn't release | 10 tests |
| unblock all lock signals | only_the_lock_signals |
| SIG_SETMASK to empty | only_the_lock_signals |
| no mask around acquire | after-open, after-close, in-release |

  On the last row I had predicted after-acquire. It now passes without the mask, which is correct: the handler reads `_held`, not the context manager's local `held`.

## Remaining (ledgered by the reviewers, out of scope)
SIGINT is still not masked around acquire and release. A KeyboardInterrupt landing exactly inside release can leave the lock, which `emcee lock clear` recovers. Because `_block` is now inside each `try`, such a KeyboardInterrupt no longer leaves TERM/HUP blocked.
