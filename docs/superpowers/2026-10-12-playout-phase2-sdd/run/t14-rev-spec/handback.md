VERDICT: APPROVED

### Findings
#### Critical
None.

#### Important
None.

#### Minor
1. **Spurious guard-stale pair on upgrade** (implementer's own concern, confirmed). `deadclock.py:106-108` alerts `guard-stale` when the cache has no `guard_evaluated_at` and `error is None`. A `guard-cache.json` written by the pre-T14 code has neither new key, and `publish.py:146-147` keeps serving it for up to `guard_check_minutes`, so the first deploy can send one `guard-stale` ("no evaluation time: is the antenna clock deployed?") and then its resolution about 15 minutes later. This is brief-verbatim logic, a one-time event on a level code that resolves aloud. Two fixes: treat a cache missing the `guard_evaluated_at` key (as opposed to a null value) as "unknown, say nothing", or delete the cache on upgrade. Worth a line in the Task 17 checkpoint notes if it is left as is.
2. **"Two consecutive checks" (R4) is looser than written.** `deadclock.py:76-82`: only a fresh 200 resets `stale`. An unexpected 403 or a network error between two stale reads does not, so stale / unreachable / stale alerts as if the stale reads were consecutive. Likewise an unexpected 403 does not reset `unreachable` (`:90-94`). This is the brief's code verbatim (plan-mandated), and it errs toward alerting, not toward silence. Fix if wanted: reset `stale` in the non-200 branches.
3. **The monitor reads offair.json differently from the guard.** `publish.py:155-159`: an `offair.json` that is corrupt (`json.loads` raises, so None) or holds a non-boolean `offair` (so False) counts as "not off the air". antenna (`guard.ts:230-235`) treats both as off the air. Effect: a corrupt flag gives a `dead-clock` "kill switch left on?" alert after 17 minutes, alongside antenna's own `offair-corrupt`. That is noise only, never a gating effect, since `offair` is informational. The brief's code does this.
4. **The dead-clock check is skipped on fail-closed ticks.** `service.py:214-218`: when publish.json is unreadable, `tick` returns before publish, so the monitor does not run either. This is placement per the brief ("after publish"), and `publish-state` alerts on that tick anyway. Noted only.
5. **Unused import.** `test_deadclock.py:1`: `import logging` is unused (brief-verbatim; the implementer flagged it).

### Cannot verify from diff
- Whether the R4 floor/validator (`dead_clock_seconds >= 31`, `guard_stale_minutes >= guard_check_minutes + 16`) is right is Task 13's. I checked only that it exists (`config.py:101,106,126-128`) and that the defaults are 120 s / 45 min / 15 min, which `test_open_monitor_needs_site_url` pins through `open_monitor`.
- The runbook/docs mention of the dead-clock check is not part of this task's file list. The config template already documents `site_url` enabling the check (`config.py:206-207`).

### Strengths
- The code follows the brief nearly line for line: `deadclock.py` (`playlist_age_s`, `fetch_text` with status 0 on no response, `DeadClockMonitor` with the brief's field order and defaults, `STALE_CHECKS=2`, `TROUBLE_CHECKS=10`, `forbidden_checks=17`), the `publish.py` replacement, all five `service.py` edits, and the `cli.py` `run` wiring.
- Every test the brief names exists under the brief's name with the brief's assertions: 8 in `test_deadclock.py`, the 2 appended to `test_service.py`, and the one-line `test_publish.py` log change.
- The extra `test_publish.py` test is welcome, not over-engineering. It pins exactly the three orchestrator constraints on the gate: offair true never gates, an unreadable offair never gates, and an unreadable guard still fails closed with the error recorded.

**Orchestrator directive 1: `guard_blocks_publishing` is equivalent.** Verified against the diff:
- The freshness branch (`publish.py:146-147`) is untouched.
- `blocked` is still `bool(doc and doc.get("tripped"))`.
- The guard-read `except` still sets `blocked=True`. The new `evaluated_at` line sits inside the same `try`, after `blocked` is computed, and cannot raise where `doc.get("tripped")` did not.
- The offair read sits in its own `try` that only sets `offair`, and the function returns `blocked`, unchanged.
- The only behaviour change is one extra Class B GET per cache refresh, which the updated test asserts.

**Directive 2: OFFAIR_KEY.** It is defined once in `publish.py:56`, and `cloudstate.py` now imports it (its local definition was removed, same string). No other Python definition exists (grepped). It matches antenna's `latch.ts:20`.

**Directive 3: `check` resolves on every healthy check.**
- A fresh 200 resolves `dead-clock` (`:83-85`).
- An expected 403 while blocked resolves `dead-clock` (`:86-88`).
- A fresh `guard_evaluated_at` resolves `guard-stale` (`:113-114`).
- `Dispatcher.resolve` returns early when the code is not active (`alerts.py:188-192`), so resolving every minute is cheap and sends nothing.

**R16.** `dead-clock` and `guard-stale` are in `LEVEL_CODES` (`alerts.py:33`) and are resolved only by the monitor. A monitor exception goes through `_step`'s generic arm as `alert("dead-clock", ...)`, which a later healthy check resolves.

### Checks run
- **Risk: the guard cache is not refreshed when there is nothing to publish, so `guard_evaluated_at` would age and false-alarm `guard-stale`.** Checked `publish_batch` (`publish.py:267-272`) and `prune` (`:381-384`). Both call `guard_blocks_publishing` first inside the lock, before any nothing-to-do return, and `publish_all` calls both every tick. Refreshes therefore happen every `guard_check_minutes` whatever the lead. Not an issue.
- **Risk: wrong field names.** antenna's `GuardDoc` has a top-level `evaluated_at: string | null`, updated on every attempt, success or failure (`latch.ts:54,131,135`; R1). So `guard-stale` measures attempt staleness, which is right for a stopped clock. `offair.json` is `{offair: boolean}` (`guard.ts:231`; `playlist.ts:19`). Both match the diff.
- **Risk: the off-air MEDIA-SEQUENCE is not a wall-clock grid index, so a healthy off-air station would age into `dead-clock`.** `playlist.ts:20,54,72`: it is `max(0, indexAt(g, seqMs))` with `seqMs` defaulting to now. It tracks the clock, as the brief and the test comment assume.
- **Risk: `forbidden_checks` is mis-derived.** `open_monitor` uses `ceil(guard_check_minutes) + 2` = 17 at the default 15 (`config.py:87`), as R4 requires. The 403 test arithmetic (1 expected, then 16 silent, then the 17th alerts) matches.
- **Risk: the `fetch_text` exception order.** `HTTPError` (a subclass of `URLError`) is caught first, so a 403 yields its status and not 0. Timeouts during read are `OSError` and yield 0. Correct.
- No tests were re-run: the implementer reports 404 passing on 3.14 and 3.11 plus the Debian-12 gate, and nothing above raised a doubt a focused run would settle.
