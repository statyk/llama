# t5b-impl handback

Status: DONE_WITH_CONCERNS (I fixed it a different way from the ruling's suggested mechanism; reason below)

## Commits
- c1d486eb emcee: station lock handler defers inside acquire/release, whatever thread takes the signal
- 6c969f10 README: the station lock replaces "single-writer station, no lock" (R7, separate commit)

## What changed (packages/emcee/src/emcee/station_lock.py)
There are three new module globals: `_critical`, `_deferred` and `_exiting`.
- `_block` sets `_critical = True` before it masks the signals. `_unblock` unmasks, clears `_critical`, then calls `_exit_on_signal(deferred)` if a signal arrived during the critical section.
- `_exit_on_signal`: if `_exiting` is set, it returns, because a second signal during the handler's own release is a no-op. If `_critical` is set, it records the first signum in `_deferred` and returns. Otherwise it sets `_exiting` and does what it did before (block, token-checked release, flush, `os._exit(128+signum)`).
- So acquire and release are atomic with respect to the Python handler on any thread, not just under the main-thread mask. A signal during acquire acts once the lock is fully held; one during release acts once release has finished. That matches the R6 semantics the docstrings already stated. `acquire`/`release` themselves are unchanged. The docstrings and a block comment explain the threading reason.

## Why I did not use the ruling's mechanism (publish before os.open; clear _held after the unlink)
The acquire half cannot meet its own requirement. A handler that fires right after `os.open` returns, before the body is written, finds an EMPTY (or partial) file. The token check then refuses to unlink it, so the lock is left. Unlinking without the token check is unsafe in the EEXIST case: another writer's file can also be empty mid-create, and the handler can run between the failed open and clearing the record. No Python statement after the open closes the gap, because CPython checks for pending signals right after a C call returns, before the result is stored. Deferral avoids both halves. It also covers a third failure I found: a second signal during the handler's own release re-entered the handler and left the lock. Release order was left as it was (`_held = None` first), since the handler can no longer interrupt it. Its "never both unlink / no spurious warning" requirement is met because the handler never runs mid-release.

## Tests (packages/emcee/tests/test_station_lock.py)
The existing `_WINDOW_SCRIPT` takes an optional third arg `thread`. It starts a daemon thread blocked on `threading.Event().wait`. `kill()` now spins 200k bytecode iterations after `os.kill`, so a handler can run while still inside the window. The window test is parametrized `threads in ["main-only", "thread"]`, so all 9 windows run both ways (18 cases). Each case asserts: rc = 128+signum, no lock file, no warning, and no caller code after the signal.

RED, pre-fix code in a scratch copy (git archive HEAD + new test file, PYTHONPATH-shadowed; import path checked as the copy's, `_critical` absent):
  FAILED [after-open-thread] [after-close-thread] [in-release-thread] [second-in-release-thread]; 4 failed, 14 passed. Each one failed on the lock file still existing; rc was 143. after-open/after-close are the acquire window and in-release the release window; second-in-release is the nested-handler case.
GREEN: 42 passed in test_station_lock.py; window tests 15/15 repeat runs green; `./.venv/bin/pytest packages/emcee -q`: 1222 passed, 1 deselected.
Mutants (scratch copies, predictions named first): defer guard removed (`if _critical:` -> `if False:`), predicted after-open/after-close/in-release-thread, got exactly those 3. `_exiting` guard removed, predicted second-in-release-thread, got exactly that 1.
The reviewer's rr3/r.py (release and acquire modes) against the fix: rc=143 and no lock in both.

## README (R7)
I replaced the "Single-writer station, no lock" paragraph (README ~633) with "The station lock, and one `emcee run` at a time". It covers: the lock is per package in run/voice and never held across Proceed?; llama's station writes refuse while it is held; a held lock stops `run` and refuses `voice`; SIGTERM/SIGHUP release it and exit with 128+signal; SIGKILL leaves it; `emcee lock show|clear`, with agents passing `--yes` only after approval; which commands don't take it. It also keeps the warning that two concurrent runs are still unsupported (double spend).

## Concerns
1. The fix departs from the ruling's suggested mechanism (see above). Task 10 should mirror the deferral design into llama, not the publish-before-open design.
2. The root CLAUDE.md still says "Run one `emcee run` at a time against a station root; it takes no lock." That was out of my brief, but it is now stale. Suggest "...; the lock serializes packages, not runs."
3. A deferred signal during an acquire that then fails (StationLocked or a create error) exits 128+signum instead of raising. The other writer's lock is untouched, since `_held` is None. That is intended, but no test covers it.

## Fix round 1 (controller)
Commit: 30f72cff emcee: pin the station lock's signal exit on refused/failed acquires and a warning release. Changes:
1. New window modes in `_WINDOW_SCRIPT` (FOREIGN is now passed into the script) and a new test, `test_signal_in_a_failing_acquire_or_a_warning_release_exits_leaving_no_lock_of_ours`. It is parametrized over modes {refused, warn-release, create-error, write-error} and threads {main-only, thread} (8 cases). Every case asserts rc=143 and that no caller code runs after the signal.
   - refused: a foreign lock exists, and the kill fires inside `_read` during the refused acquire. The foreign lock must be byte-identical and nothing may warn.
   - warn-release: FOREIGN overwrites the lock mid-hold, and the kill fires inside release's `_read`. The foreign lock must be intact and `warning:` must appear exactly once, naming "was not ours at release" and "pid: 4242". The body runs.
   - create-error: `os.open` kills and then raises EACCES. No lock may be left.
   - write-error: `os.write` kills and then raises EIO. Acquire's cleanup unlinks, and no lock may be left.
   Against the pre-fix copy (scratch, PYTHONPATH-shadowed), warn-release-thread and write-error-thread fail. The other 6 pass there; they are pins.
2. The second-in-release comment now reads "a second signal as the first one starts its release".
3. `_unblock` has a comment on the async KeyboardInterrupt limit. SIGINT is not masked or deferred, so a Ctrl-C between the unmask and `_critical = False` can leave `_critical`/`_deferred` stale. It never leaves a stuck lock, because acquire/release have finished and the caller's `finally` releases. A stale `_deferred` would make a later `station_lock` in the same process exit at its first `_unblock`. Task 10 should carry this note.
Results: `./.venv/bin/pytest packages/emcee/tests/test_station_lock.py -q` gives 50 passed. `./.venv/bin/pytest packages/emcee -q` gives 1230 passed, 1 deselected.
