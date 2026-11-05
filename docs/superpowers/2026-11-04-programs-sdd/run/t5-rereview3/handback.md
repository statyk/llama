### Finding Verdicts

- **RULING R6: SIGTERM/SIGHUP release the lock and `os._exit(128+signum)`; nothing raised into the caller; SIGINT unchanged; signals blocked around acquire and release; SystemExit-only machinery removed; docstring updated.** ADDRESSED.
  - The handler is `_exit_on_signal` (station_lock.py:209-223). It reads `_held`, blocks TERM/HUP, and calls the same token-checked `release`. In a `finally` it flushes stdout and stderr, swallowing `Exception` (a `None` stream's AttributeError is caught too), then calls `os._exit(128 + signum)`. It cannot return or raise into caller code.
  - SIGINT is never touched: `_SIGNALS` at :193 is TERM/HUP only.
  - `_block` sits inside its `try` around both acquire (:249-253) and release (:258-262), so the matching `_unblock` always runs.
  - Removed: `_base_mask`, the SIG_SETMASK restore, the `_held is held` guard and the trailing unconditional `_unblock`. Removing the guard is sound: the handler never returns, so if the `finally` runs, the handler did not fire.
  - The module docstring (:21-28) states the process exit, that caller cleanup is skipped, the atomic-rename constraint and the SIGINT behaviour. The `station_lock` docstring (:229-237) matches.
  - Window checks, reasoned against the code and the 9-mode subprocess test:
    - **after-open, after-close, after-acquire:** the signal is pending under the mask. It fires at `_unblock`'s SIG_UNBLOCK, with `_held` set by acquire:167 (the handler reads the module global, not the local `held`). It releases and exits.
    - **in-release, before-release-block:** pending until :262, by which time `_held` is None and the file is gone. Exit with no lock. A signal tripped just before `_block` is handled inside `pthread_sigmask`'s post-call `PyErr_CheckSignals`, with `_held` still set, so it releases and exits.
    - **double signal:** the handler blocks TERM/HUP before `release` and `os._exit`s, so it is never re-entered on a single thread.
    - **refused acquire:** acquire raises `StationLocked` before setting `_held` (:145). The pending signal fires at :253 with `_held` None and exits without touching the other process's lock.
    - **a signal while handlers are being installed (:247-248)** finds `_held` None and exits. No lock exists yet.
  - `_held` on non-signal paths: acquire's BaseException path never sets it (:156-166), and `release` clears it first (:174-175).
  - A normal exit and a refused acquire both restore the handlers (:263-265) and unblock only the entry-unblocked signals.
  - Off the main thread, `unblock` is None, so nothing is installed or blocked (:239-248, :196-206).
  - **Limit, see New Breakage 1:** "the handler never sees `_held` in flux" holds only while the main thread is the only thread that can take the signal.
- **MINOR (re-review 2): `_unblock` restored the whole entry mask with SIG_SETMASK.** ADDRESSED.
  - Lines 239-242 compute the lock signals that were not blocked at entry. `_unblock` (:202-206) SIG_UNBLOCKs only those.
  - When both signals were already blocked at entry, the tuple is empty: `_block` still blocks (a no-op) and `_unblock` does nothing (`if unblock:`).
  - `test_only_the_lock_signals_are_unblocked` pins it: SIGUSR1 blocked by the body and SIGHUP blocked by the caller both survive.

### New Breakage in the Fix Diff

1. **Minor**, station_lock.py:232-235 (docstring claim) and :174-175 / :137-167. The claim behind the mask design is that the handler never runs while `_held` is in flux. It holds only in a single-threaded process.
   - `pthread_sigmask` blocks the main thread only. A process-directed SIGTERM is then delivered to any live thread that has it unblocked. Its C handler trips the flag, and CPython runs the Python handler on the main thread at the next bytecode boundary, even though the main thread has the signal blocked.
   - Two failing windows follow:
     - **inside `release`:** after `_held = None` and before the unlink, the handler sees None and exits, leaving the lock.
     - **inside `acquire`:** after `os.open` and before `_held` is set, the same happens.
   - Reproduced from a scratch cwd, importing the worktree's emcee (verified path), with one idle daemon thread alive. Both windows gave rc=143 with the lock left behind. The scripts are under the session scratchpad `rr3/` (`t.py`, `r.py`); output is in this task's log.
   - The failure is safe: a stuck lock, recoverable with `emcee lock clear`, never two writers. No lock-holding caller runs threads today, but TTS or HTTP libraries in an `emcee run` process may. The window predates R6 (the mask arrived in fix 1), so it is not a regression.
   - Either fix closes it:
     - make `release` clear `_held` only after the unlink attempt, and have acquire publish the path/token before `os.open` so the handler can release a just-created file;
     - or narrow the docstring to "single-threaded at acquire and release" and add it to the ledger beside the worker-thread constraint for Tasks 6 and 9.
2. **Minor** (test gap, no defect). No test runs the windows with a second thread alive, which is why item 1 is not exercised.

### Out-of-Scope Observations

- SIGINT is still unmasked around acquire and release, as the fix report already ledgers. In particular, a KeyboardInterrupt between `acquire` returning and `held` being assigned (:251) leaves the lock on disk with `_held` set, because the `finally` skips release while `held` is None. `emcee lock clear` recovers it. This is unchanged by this round.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage. One Minor: the mask does not protect against a signal delivered to another thread. Ledger it, or fix it with the `_held`-ordering change above.
