### Spec Compliance

- ✅ Spec compliant.
  - R6 semantics are kept and the thread defect is fixed. The handler defers while `_critical` is set (station_lock.py:242-245), and `_unblock` acts on the deferred signal once the lock is fully held or fully released (:228-231). SIGINT is untouched.
  - The tests cover the acquire window (after-open, after-close) and the release window (in-release) with a live second thread (test_station_lock.py:308-311, parametrized at :376). The implementer's RED evidence (4 thread cases failing on pre-fix code) and the two named mutants show the guards are load-bearing.
  - R7 is met. README.md:633-655 no longer says "no lock" and matches packages/emcee/CLAUDE.md:32-50 point by point: per-package hold, never across `Proceed?`, llama refusals, run/voice refusal text, SIGTERM/SIGHUP exit 128+signum, SIGKILL leaves the lock, the exemptions, and "serializes packages, not runs".
- ✅ Departing from the parent's suggested mechanism is correct. On CPython 3.11+ a CALL checks the eval breaker after the C call returns and before the result is stored, so a handler can run between `os.open` returning and `fd` being bound (station_lock.py:137). At that moment the file is empty, and its token cannot be checked. Unlinking without the token check is unsafe in the EEXIST case, where an empty file can be another writer's mid-create. Deferral closes both halves with three globals and two helpers, so it mirrors cleanly. **Task 10 should mirror the deferral design, not publish-before-open.**
- ⚠️ Cannot verify from diff: the implementer's Concern 2 is stale. Root CLAUDE.md:40 in this worktree already says "emcee takes the station lock…", so no change is needed there.

### Answers to the specific checks

- **Lost deferred signal:** none on any non-async path. `_deferred` is set only while `_critical` is True (:242-244). `_critical` is set only in `_block` (:215), and every `_block` sits in a try whose `finally` runs `_unblock` (:285-289, :294-298), which clears the flag and acts (:228-231). A second signal while `_deferred` is already set is dropped, which is correct because the first one acts. The single exception is an async `KeyboardInterrupt` (see Minor 3).
- **`_deferred` on every exit path:** I verified each one with a probe that keeps a live second thread and sends SIGTERM inside the critical section (scratch script, run from an empty cwd against the worktree venv, read-only):
  - refused (EEXIST): rc=143, the other writer's lock is byte-intact, no stdout.
  - create error (EACCES): rc=143, no lock.
  - write error (EIO, cleanup path): rc=143, no lock.
  - release whose warning path runs (foreign lock): rc=143, the warning is printed once, the foreign lock is untouched.
  - Normal acquire and release are covered by the 18 window cases.
- **Refused acquire exits 128+signum without the refusal message:** acceptable. The operator asked the process to terminate, and R6 says no caller code runs after the signal. `_held` is None, so nothing touches the other writer's lock. The `StationLockReentry` variant would release this process's own outer lock, which is correct. Untested; see Minor 1.
- **Re-entry guard consistency:**
  - `_exiting` is set only on the path that always ends in `os._exit` (:246-258), so it is never stale.
  - `_critical` and `_deferred` are reset by every `_unblock`.
  - Non-signal paths leave `_critical=False` and `_deferred=None`.
- **Handler running on main while main is inside `_unblock`:** safe at every boundary.
  - Before :228, it defers, and the same `_unblock` then acts at :229-231.
  - After :228, or after the swap at :229, it acts directly. The lock is fully held or fully released at that point, and the handler exits, so a swapped-out `signum` is moot.
  - A nested signal during the deferred call before `_exiting=True` (:246) runs the whole exit itself, and the outer frame never resumes.
  - A nested signal after :246 is a no-op.
- **Do the 18 cases inject where they claim?** Yes for after-open (between `os.open` returning and the store), after-close (before `_held` is set), after-acquire, in-release (between release's read and unlink, patched inside the body so acquire's path is unaffected), before-*-block and in-body. second-in-release injects at release *entry*, not mid-release (see Minor 2). The 200k-iteration spin keeps the handler inside the window in thread mode, and the RED run confirms that it did.
- **Single-threaded process ending a non-signal path masked or with a stale `_deferred`:** no. `_unblock` always runs from a `finally`, and it unmasks exactly the signals that were unblocked at entry (`unblock` is computed at :277-278; an empty tuple means the caller had them blocked and they stay blocked). `_deferred` cannot be set without a signal. The only way out is an async `KeyboardInterrupt` (Minor 3).

### Strengths

- The diagnosis is precise. The block comment at station_lock.py:195-204 explains why the mask is not enough, which Task 10 needs.
- `_critical` is set *before* the mask (:215), and `_unblock` unmasks *before* clearing it (:226-228). That ordering makes a pending signal released by the unmask defer and then get acted on by the same `_unblock`, with no gap.
- The `_exiting` guard closes a third failure, a nested handler during the handler's own release, that the prior review did not name.
- The test change is minimal. It reuses the existing window harness and doubles it across both thread modes rather than adding a parallel harness. The RED evidence was gathered correctly: a scratch copy, PYTHONPATH-shadowed, with the import path checked.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)

1. **test_station_lock.py:373-376, untested exit paths.** No test covers a deferred signal through a refused acquire, a create or write error, or a release warning. My probe shows all four are correct today. Since Task 10 mirrors this module, pin them cheaply: add a `refused` window (pre-existing foreign lock, kill inside `_read`) asserting rc=143 and a byte-identical foreign lock, and a `warn-release` window asserting rc=143 with the foreign lock intact.
2. **test_station_lock.py:345-350, second-in-release.** The second `kill()` fires at the wrapper's entry, before the real `release` sets `_held = None`. It is labelled "while the first one releases". Because the `_exiting` check is the handler's first statement, every point inside the handler's release is equivalent, so this does not weaken the test. The comment should say "as the first one starts its release".
3. **station_lock.py:226-229, async `KeyboardInterrupt`.** A SIGINT landing between the unmask (:227) and `_critical = False` (:228) leaves `_critical` True and possibly a stale `_deferred`.
   - It cannot leave a stuck lock. On the acquire path with the lock held, the outer `finally` runs the release `_block`/`_unblock`, which resets the state and acts. After `station_lock` returns, the previous handlers are restored, so `_exit_on_signal` is no longer reachable.
   - The worst case is a stale `_deferred` acted on at the next `station_lock` in the same process, which releases and exits 143. It needs SIGINT and SIGTERM within a few bytecodes of each other.
   - Optionally note it in the comment, so Task 10 knows the limit. No fix is required.
4. **README.md:648-649 vs CLAUDE.md:103-104, wording.** README says `lock clear` "removes it (only if that writer is gone…)", which is operator guidance. emcee's CLAUDE.md states the mechanism ("only if it is unchanged"). They don't contradict each other. Fine as is.

⚠️ For the controller (pre-existing R6 behaviour, outside t5b's diff): in the *body*, when another thread takes the signal while the main thread is blocked in a wait that is not interrupted by EINTR, the Python handler runs only once the main thread wakes. An example is a `Condition.wait` on TTS futures. The signal is delayed, not lost, and the lock is released then. Worth one sentence in Task 10's notes. I checked only CPython's documented behaviour and emcee's call sites; I did not measure it.

### Assessment

**Task quality:** Approved

**Reasoning:** Deferral makes acquire and release atomic with respect to the Python handler on any delivering thread. Every exit from the critical sections acts on the deferred signal, which I verified with a live second thread for refused, create-error, write-error and warning-release paths. The design is sound and simple to mirror into llama in Task 10. The remaining items are test pinning and comment wording.
