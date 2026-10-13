VERDICT: ALL ADDRESSED

### Finding verdicts
1. ADDRESSED. `deadclock.py:53-57` checks `HTTPError` first, so a 403 keeps its status (`test_fetch_text_keeps_the_http_status_of_a_403`, test_deadclock.py:142). It then catches `(URLError, OSError, http.client.HTTPException, ValueError)` and returns `(0, "")`.
   - `HTTPException` covers IncompleteRead, LineTooLong, BadStatusLine/RemoteDisconnected and InvalidURL. `OSError` covers timeouts and SSL. `ValueError` covers an unknown URL type and SSLCertVerificationError.
   - The `try` wraps the whole `with` block, so the same arm also catches errors raised during `read()`.
   - Tests: the parametrized `test_fetch_text_turns_transport_errors_into_status_zero` (:135) and the no-network `test_an_odd_transport_error_does_not_alert_on_the_first_call` (:151). The second monkeypatches `urlopen`, and the monitor's default `fetch` is used.
   - Mutant M8 (back to `(URLError, OSError)`) turned the predicted 4 tests red.
2. ADDRESSED. `deadclock.py:111-121`: a non-null `error` starts `guard_error_since_us` and alerts `guard-stale` once the error has lasted `>= guard_stale_s`. The message names the error. A non-error cache resets the timer, then the freshness rule runs. Case by case:
   - **error, recovered, error:** the timer restarts. Test :163 asserts `guard_error_since_us == later` and no alert. Mutant M5 (no reset) turned that test red.
   - **error plus a stale evaluation time:** while the error lasts, the cache carries `guard_evaluated_at: null` (publish.py:153-161), so the monitor times only the error. If the guard was already partly stale when hugo's read started failing, the alert is late by at most that earlier staleness: worst case about 2·guard_stale_s, never indefinite. See Minor N1.
   - **error clears but the evaluation is still stale:** the timer resets (:121). The key is present, so the freshness rule (:124-133) alerts at once. No test covers this case. The code path is direct.
   - **can it fire while the guard is genuinely fine?** Yes, when hugo's own R2 read of guard.json fails while the cloud guard is healthy. It cannot fire on a blip:
     - the cache refreshes only every guard_check_minutes, and publish runs before the monitor in the same tick (service.py:232-235);
     - so an alert needs failing refreshes about 0, 15, 30 and 45 minutes in;
     - the message says "state/guard.json has been unreadable", which is accurate;
     - the alert is warranted, because during it hugo publishes nothing (it fails closed).

   Mutant M10 (the timer restarted on every check) turned test :163 red. publish.py is untouched (`git diff 0dc7064 9adbe62 -- publish.py` is empty), so `guard_blocks_publishing` is unchanged.
3. ADDRESSED.
   - The middle read is now `live_playlist(980)`, 204.8 s old, which is genuinely stale (test :63).
   - `test_stale_fresh_stale_fresh_never_alerts` (:116) pins the reset. Mutant M1 (drop `self.stale = 0`) turned exactly that test red.
   - `test_403_while_the_guard_says_blocked_never_alerts_even_past_the_threshold` (:124) runs 20 checks with blocked=True and offair=False. Mutant M3 (drop the `blocked` arm) turned exactly that test red.
4. ADDRESSED. `deadclock.py:122-123` returns when the key is absent. A key that is present but null still alerts (:129-130). Test :185; mutant M6 turned it red.
   - Can a pre-upgrade cache hide a stall indefinitely? No, because the cache is replaced within one refresh:
     - `guard_blocks_publishing` has exactly one writer (`grep guard_cache` in src). It writes `guard_evaluated_at` on both the success and the error branch (publish.py:148-161).
     - `publish_batch` and `prune` call it first, inside the lock, on every tick (publish.py:270, :382).
     - It re-reads whenever the cache is at least guard_check_minutes old, or when its age is negative.
   - So a cache without the key survives at most guard_check_minutes plus one tick. The window is no longer if publish itself keeps failing; it is just the same window every time.
5. ADDRESSED. service.py:235 passes `self.clock()` at check time. The test injects a clock and expects `NOW+7` (test_service.py:361). Mutant M7 (back to `t_us`) turned it red.
6. ADDRESSED. The comment at deadclock.py:71-73 says the counters count consecutive bad checks and reset only on a good read, and that this is intended.
7. ADDRESSED. deadclock.py:53 calls `resp.read(1 << 20)`.
8. ADDRESSED. `import logging` is removed from test_deadclock.py.
9. ADDRESSED. `test_run_hands_the_runner_the_dead_clock_monitor` (test_cli.py:205) monkeypatches `service.open_monitor` and `service.Runner`. cli.py:224 calls both through the `service.` module, so the patches take effect. Mutant M9 (drop `monitor=`) turned exactly that test red.
10. ADDRESSED. deadclock.py:87 reads "the antenna clock may have stopped or be writing nothing", which is M-g's suggested wording.

### New breakage in the fix diff
None blocking. Minor only:
- **N1 (Minor), deadclock.py:111-120.** While hugo's read of guard.json is failing, the monitor discards the last known evaluation time and times only the failure. A guard that stalled before the failure began is therefore reported up to guard_stale_s late. The in-memory timer also restarts whenever the service restarts. Both delays are bounded and never silent:
  - the dead-clock check on live.m3u8 runs independently;
  - publishing is fail-closed throughout, so no spend is at risk.

  Optional hardening: keep the last good `guard_evaluated_at` in the monitor and alert on whichever is older. This is the reviewer's option (a), done monitor-side, so publish.py stays untouched.
- **N2 (Minor), deadclock.py:119.** When `str(exc)` is empty, the message ends in ": ". This is cosmetic. The `is not None` test correctly still treats an empty error as an error.
- **N3 (Minor), test style.** test_deadclock.py:135 uses `__import__("http.client").client...` in the parametrize. In test :163, the fetch lambda closes over `m_clock`, which is defined after it (this works through late binding). Both work, but they are awkward to read.

### Out-of-scope observations
- If `read_json(guard_cache_path)` raised on a corrupt cache, `_step` would alert `dead-clock` with the exception text at once (service.py:202-204). This predates the fix. It is unlikely, because `write_json` is atomic.
- No test pins the case where the error clears while the evaluation is still stale (item 2, third case). The code path is direct and correct.

### Checks run
- Read the brief, the round-1 reviews (M-c, M-d, M-f, M-g wording), the implementer report and the fix diff. Inspected `publish.guard_blocks_publishing` and its call sites, `service._step`/`tick`, and the `cli run` wiring.
- Scratch copy made with `git archive HEAD packages/transmitter antenna/templates`, outside the worktree. Shadowing proven: `transmitter.__file__` resolved in the scratch copy for the base and for every mutant. Each mutant ran with `python -m pytest -p no:cacheprovider`, its own `PYTHONPYCACHEPREFIX` and `PYTHONDONTWRITEBYTECODE`.
- Baseline: test_deadclock, test_service and test_cli gave 60 passed.
- Mutants, each with its red test named in advance, all caught by exactly the predicted test(s):

| Mutant | Change | Result |
|---|---|---|
| M1 | stale reset dropped | 1 red, the stale/fresh test |
| M3 | blocked arm dropped | 1 red, the blocked-403 test |
| M5 | error timer not reset on recovery | 1 red, the unreadable-guard test |
| M6 | absent key treated as null | 1 red, the key-absent test |
| M7 | `t_us` instead of `clock()` | 1 red, the runner test |
| M8 | narrow `except` | 4 red: the 3 transport parametrizations plus the first-call test |
| M9 | `cli` drops `monitor=` | 1 red, the cli test |
| M10 | timer restarted on every check | 1 red, the unreadable-guard test |

- The full suite was not re-run. The fix report cites 415 passed on py3.14, py3.11 and Debian 12.
- Read-only: no commits and no stash. The live worktree is unchanged.
