### Finding Verdicts

- **Important 1: an operator's own restart logged RECOVERED and left Wait able to tear down their Start** — ADDRESSED. `waitManual` (probe.js:232-240) logs `wait: manual restart <label> <state>`, aborts any fetch, ends the stall, sets `waitManualRestart` and sets `waitRestartAt = now`, which the 30 s gate at probe.js:313 uses in place of the stale `movedAt`. An in-flight response can no longer restart after it, because probe.js:276 checks `signal.aborted`. The advance logs `wait: recovered after manual restart` at probe.js:306, and because `waitClearStall` nulls `waitLastRestart`, RECOVERED is unreachable unless the script itself restarts later. The only callers are the Start click (probe.js:374) and the media-session play handler (probe.js:358). `waitRestart` calls `restart()` directly, so its own path cannot reach it. A first Start (`wanted` false) returns early. Harness logs confirm the lines in `manual_after_fail`, `manual_session` and `manual_loading`.

- **Important 2: RECOVERED did not say whether the restart was made while locked** — ADDRESSED. Saved at restart (probe.js:246), cleared with the stall (probe.js:213), emitted at probe.js:304. Harness line: `wait: RECOVERED after restart 1 form=full restart_vis=hidden in=10s ct=9.36 ... vis=` (`vis_hidden`), matching the required shape, with `<state>` still carrying `vis=`.

- **Minor 1: a fetch whose abort never settles blocked later fetches silently** — ADDRESSED. probe.js:324-328 logs `wait: fetch hung <state>`, aborts and clears when older than 16 s, and the next fetch runs on the same tick. A late settle cannot restart (probe.js:276) or clear the replacement (probe.js:267). `never_settles` shows hung at +20 s, fetch 2 at once, and fetch 1's late status=200 restarting nothing. The check sits below the stuck gate and the give-up return. Neither hides a hang: no fetch can be in flight at give-up, and one left over from an earlier stall is cleared on reaching this line because `waitFetchAt` is 0. The `done()` controller compare was not mutated, as the report says; by reading it is correct.

- **Minor 2: exact float comparison** — ADDRESSED. probe.js:278 is the required expression. `waitCt` cannot be null there: every path that nulls it during a flight (`stopWait`, `waitManual`) also aborts, and probe.js:276 returns first; `waitRestart` runs only from the single live fetch.

### Test 9 check (operator-probe-test.md)

Each quoted form matches the code: `wait: fetch ... status=200` (probe.js:275), `wait: restart ... REJECTED` (probe.js:143, with the `wait: restart N form=F stuck=Ns vis=V` label from probe.js:245-247), `wait: RECOVERED`, `restart_vis=`, `vis=` (probe.js:304, 66), `wait: recovered after manual restart` (probe.js:306), `wait: recovered alone` (probe.js:308), `STALL` (probe.js:110), `event waiting` (probe.js:337). Button labels match probe.html:24-25.

One sentence states the meaning wrongly, though the form is exact. See the first Minor below.

### New Breakage in the Fix Diff

No Critical or Important.

- **Minor (doc, operator-probe-test.md:47):** "`wait: restart ... REJECTED` means iOS refused it" is too broad. If restart 1's play() is still pending when restart 2 runs, the page's own teardown (full) or load() (gentle) rejects it, giving `wait: restart 1 ...: play() REJECTED AbortError`. This shows in r2 `two_full` and `two_gentle`, and is likely on a locked iPhone if the first restart never loads. It predates this fix but falls in the check requested. Test 3 also read `NotSupportedError` as the network, not permission. Suggested wording: only `NotAllowedError` means iOS refused; `AbortError` right after the next restart's `teardown` is the page's own.
- **Minor (probe.js:306):** `waitManualRestart` survives into the next stall. If a manual Start stays stuck past 30 s, a `wait: stall` line follows, no restart lands (fetches failing), and iOS then resumes alone, the line reads `recovered after manual restart`, not `recovered alone`. Test 9 tells the operator not to press anything, and the `wait: manual restart` line is above it in the log, so it cannot mislead an answer to D6.
- **Minor, mandated by the ruling (probe.js:278):** the tolerance reopens a window of under 1 s. If the position starts moving just before or after the tick that fetches, by less than 1 s when the answer lands, the restart hits resumed audio and a false RECOVERED follows. Exact compare closed the post-tick half. It needs iOS resuming alone at that instant, and test 2 shows it doing nothing for minutes. No change asked.

Claims checked: the report names its scenarios and mutants; harness logs for the scenarios above exist and match it. r2 has one failing json (`full`), r3 `full` passes, as reported. No test run by me; no doubt required one.

### Out-of-Scope Observations

- The report's `stuckSeconds` note (probe.js:72): an upward creep keeps stuck=0 and Wait never stalls. Pre-existing, no iOS evidence, shows in the log.
- Test 9 treats `vis=hidden` as the marker of locked, but the results summary (probe-results-safari-1.md) records no vis value for a locked page and no raw log with `vis=hidden` was found in that scratchpad. Likely true, but unverified here. The operator's "did audio come back while locked" column and the `visibilitychange` lines cover it.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage. Open for the controller's call: the one-sentence Test 9 correction on REJECTED before the operator runs it.
