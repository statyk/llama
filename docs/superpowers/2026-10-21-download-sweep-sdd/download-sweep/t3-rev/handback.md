### Spec Compliance
- ✅ Spec compliant (spec §2, §1's deadline sentence, brief Task 3). Each requirement checked:
  - Constants `DOWNLOAD_SLOTS = 8`, `SLOT_POLL_MIN_S = 0.5`, `SLOT_POLL_MAX_S = 1.0`: download_slots.py:20-22.
  - The `acquire` contract: it polls `0.lock..{n-1}.lock` in order with non-blocking flock (download_slots.py:37-46). It calls `on_wait` on the first miss only (:58-62) and then sleeps `rng.uniform(MIN, MAX)` (:63). It creates the dir (:53), yields the wait measured on `clock` (:57, :65), and releases on exit and on exceptions (:64-71, try/finally around the yield). Crash safety comes from flock.
  - `IAClient(..., slots: DownloadSlots | None = None)`, with `None` meaning no cap: ia_client.py:119, :133.
  - The slot covers exactly one `_attempt` (ia_client.py:399-404) and is released before both `_pause` call sites (:418, :431).
  - `waiting for a download slot` prints at most once per `download_file` call, through the `announced` closure (ia_client.py:373-379), copy exact.
  - Deadline accounting matches the decision. First-pass waits are dropped by the reset at ia_client.py:426. Waits of later attempts are added at :405 and subtracted in `expired()` at :382, which is otherwise unchanged.
  - `_setup` wires `DownloadSlots(config.root / ".download-slots")`: cli.py:125. It is the only `IAClient(` construction in `packages/llama/src` and `scripts`. I grepped this to check for a download path that bypasses the cap; there is none.
  - All five brief tests are present, plus the Task 2 carry-over test `test_transport_error_mid_continuation_discards_the_part` (test_ia_client.py:1147).
- ⚠️ Cannot verify from the diff: the full-suite count the implementer reported (3869 passed). I did not re-run it, per the brief.

### Strengths
- I checked the tests by mutation, in a scratch `git archive` copy. I confirmed PYTHONPATH shadowing by asserting `llama.__file__` sat inside each copy, used `PYTHONDONTWRITEBYTECODE` and `-p no:cacheprovider`, and named the expected red test before each run. All five predictions hit:
  - **Baseline:** 8/8 green, no warnings.
  - **m1:** drop `replace(outcome, slot_wait_s=waited)`. Only `test_slot_wait_does_not_count_toward_deadline` went red.
  - **m2:** `if not announced` changed to `if True`. Only `test_waiting_line_prints_at_most_once_per_download` went red.
  - **m3:** `if not waited_once` changed to `if True`. Only `test_on_wait_called_once_per_acquire` went red.
  - **m4:** `self._pause()` placed inside the slot `with`. Only `test_slot_released_before_sleep_between_attempts` went red.
  - **m5:** `range(self.n + 1)`. `test_never_more_than_n_holders` went red, as predicted, and so did the dead-holder and on_wait tests.
- The concurrency test uses real flock across 12 threads. It synchronises on a Condition and Event (`polls >= total - n` is exact, because a waiter's `sleep` blocks), with no correctness sleeps. The dead-holder test uses a real subprocess plus `kill()`, so it pins flock-on-death specifically.
- The deadline test compares runs with and without a wait under the same RNG seed. That also catches a mutant that stops resetting first-pass waits (it would extend the deadline).
- I found no deadlock path. A slot holder waits on nothing but the network, and `_attempt` takes no locks: `_attempt` calls `self._throttle()`, never `self.sleep`. The slot is innermost and short-lived, beneath show ⊃ ledger.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **download_slots.py:42: any flock error is treated as "slot held", so it becomes an endless wait.**
   - `except OSError:` swallows every flock failure, for example `ENOLCK` or `EOPNOTSUPP` on a filesystem without flock support, and treats it as a busy slot.
   - A persistent error then puts `acquire` into an infinite 0.5-1 s poll. The operator sees one `waiting for a download slot` line and nothing else. That is the spec's anti-goal ("a download cap that deadlocks or starves").
   - It also breaks the codebase convention: locks.py:32 catches only `BlockingIOError` and lets every other error raise.
   - Exposure is low in practice: the show lock on the same filesystem would probably fail first. The fix is still one word: `except BlockingIOError:`, with the comment changed to match.

#### Minor (Nice to Have)
1. **cli.py:125: nothing pins the production wiring.** No test references `.download-slots` or checks that `_setup` passes `slots=`. Reverting that line would leave the suite green while removing the cap in production. A one-line assertion on `_setup()[1].slots` would fix it.
2. **ia_client.py:399-404: duplicated `self._attempt(...)` call.** The two branches repeat the same call. `cm = self.slots.acquire(on_wait=on_wait) if self.slots else contextlib.nullcontext(0.0)` would reduce it to a single call site.
3. **ia_client.py:274: `_throttle()` sleeps inside the slot.** It calls `time.sleep` for up to `rate_limit_s` (0.5 s) inside `_attempt`, so the slot is held during it. This is not a sleep between attempts, so §2 is not violated, and it is harmless. It is worth a comment so nobody "fixes" the wrong thing.
4. **Unfair polling (observation, mechanism mandated by the spec).** Polling is not FIFO. A process downloading sequentially (stages/package.py:52) re-takes a slot milliseconds after releasing it between files. A 9th process mostly gets in during a holder's 1-4 s `_pause`, or when a holder's show finishes downloading. The wait is bounded by that, so this is not starvation. No action needed beyond knowing it.
5. **ia_client.py:382, :391: the in-flight wait is not subtracted mid-attempt (the decision as given).** After a long slot wait in a repeat attempt, `may_abandon` reads the deadline as passed. That disables the trickle switch for that attempt. Download integrity is unaffected, and this is the stated conservative choice; it is recorded here only so the effect is known.
6. **test_download_slots.py:46: a broken cap is detected only after a 30 s timeout.** The `wait_for(..., 30)` guard means a broken cap fails after 30 s (m5 took 30.56 s). Exceptions in worker threads show up as `PytestUnhandledThreadExceptionWarning` (12 warnings in m5), not as failures. The `done == total` and `max == n` counters still catch it. This is acceptable as a failure guard; the baseline run is warning-free.

### Assessment
**Task quality:** Needs fixes
**Reasoning:** The implementation matches spec §2 and the deadline decision, and every test I mutated fails when its code is broken. One Important fix remains: `except OSError` at download_slots.py:42 turns a persistent flock error into a silent endless wait. It is a one-word change to `BlockingIOError`, which matches locks.py.
