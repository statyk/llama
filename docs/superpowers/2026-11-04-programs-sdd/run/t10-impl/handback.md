# t10-impl handback: llama station lock helper

Status: DONE_WITH_CONCERNS (minor; see Concerns)
Commit: 259fd05c llama: station lock helper (shared contract with emcee)

## What was implemented
- `packages/llama/src/llama/station_lock.py`: generated from `packages/emcee/src/emcee/station_lock.py` at HEAD by a scripted text substitution, then a hand edit of `StationLocked`. The algorithm is identical: O_CREAT|O_EXCL|O_WRONLY 0644, write, fsync, close with the fd_open guard, unlink on any BaseException, release only on our own token, warnings that never raise. Signal handling follows R6 and t5b: `_exit_on_signal` releases (token-checked, both signals blocked), flushes, then `os._exit(128+signum)`. `_critical`/`_deferred` defer the signal during acquire and release, `_unblock` acts on it, the `_exiting` guard is there, and only the lock signals that were not blocked at entry get unblocked. The KeyboardInterrupt-limit comment is kept. Nothing imports emcee.
- `for_package(out, *, command) -> AbstractContextManager[Held]` = `station_lock(Path(out).absolute().parent, command=command)`.
- `packages/llama/tests/test_station_lock.py`: emcee's test file, name for name. That includes both subprocess window matrices in both thread modes (9 windows x 2, then refused / warn-release / create-error / write-error x 2), the flush-warning test, the mask tests and the read_lock tests. It also adds `test_for_package_locks_the_parent_folder`, which covers an absolute path and a relative `Path("slug")` after chdir, and `test_refusal_names_holder_and_emcee_commands`.

## Differences from emcee (the full structural diff is `diff packages/emcee/src/emcee/station_lock.py packages/llama/src/llama/station_lock.py`)
1. `LlamaError` in place of `EmceeError`: the import, the StationLocked base, and the read_lock / create errors.
2. `tool: llama` in the holder body.
3. `StationLocked` message: all of it is in `str(exc)` as three parts, `the station is locked by another writer ({path}):`, then the holder lines each indented two spaces, then `  <_CLEAR_HINT>`. `details` is `[]`. emcee puts the holder and the hint in `details`. The brief's 3-line message and `test_refusal_names_holder_and_emcee_commands` (which asserts on str(exc)) require this. A docstring explains why: batch callers that report only the message still name the holder. llama's main_cli prints `error: {exc}`, so the CLI output has the same content as emcee's. `_CLEAR_HINT` text is copied verbatim.
4. Added `for_package` and the `AbstractContextManager` import. The brief says `ContextManager[Held]`; I used the non-deprecated `contextlib.AbstractContextManager`.
5. Comment and docstring wording: the twin reference, the "who acquires" sentence (bulk_apply per-show step, all through for_package), the example of another thread (llama's status heartbeat instead of emcee run's TTS workers), and the KeyboardInterrupt-limit parenthetical (llama's lock-taking commands exit on Ctrl-C).
6. Kept `read_lock` although llama has no caller for it. Its only purpose is to keep the module and the tests diffable name for name (`test_read_lock`, `test_read_lock_error_other_than_missing_is_a_refusal`). Drop it if the reviewer prefers YAGNI.
Test-file differences: imports; FOREIGN is an emcee holder (`tool: emcee`, `command: voice x`); command strings say `deliver`; the refusal assertions follow difference 3; `EmceeError` becomes `LlamaError`; there is one comment in the window script; and the two added tests.

## TDD evidence
RED: `./.venv/bin/pytest packages/llama/tests/test_station_lock.py -q` -> `E   ModuleNotFoundError: No module named 'llama.station_lock'` / `1 error during collection`. This was expected because the module did not exist yet.
GREEN: same command -> `52 passed in 1.43s`.
Full: `./.venv/bin/pytest packages/llama -q` -> `3915 passed, 7 deselected, 24 warnings in 21.73s`. The 24 warnings are fork/multithread DeprecationWarnings from elsewhere; the station-lock file alone runs warning-free.
`./.venv/bin/python -c "import llama; print(llama.__file__)"` resolves inside the worktree, so the subprocess tests (sys.executable) import the worktree's llama.

## Self-review
- Diff is minimal and confined to the listed points; algorithm lines are byte-identical to emcee's.
- No mutation pass was run. The tests are emcee's heavily reviewed suite, ported directly. They all exercise llama's module, including the subprocess scripts, which import `llama.station_lock`.

## Concerns
- No `test_no_emcee_imports` exists in packages/llama/tests (emcee has `test_no_llama_imports.py`, transmitter has its own). The module imports nothing from emcee (grep-checked). I did not add a guard test because it is outside the brief. The controller may want one.
- Difference 3 (message vs details) departs from emcee's shape on purpose, as the brief asks. A reviewer comparing CLI output should know about it.
