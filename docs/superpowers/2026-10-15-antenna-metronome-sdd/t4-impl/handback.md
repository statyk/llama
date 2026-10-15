# t4-impl handback: Task 4, metronome-engine.ts renew

**Status:** DONE_WITH_CONCERNS (code and tests are verbatim from the brief and everything passes; two carried invariants are not pinned by any test, see below)

## Commit
- `aeef49d` feat(antenna): metronome engine renew: lease apply, capped bounded write, arm while live

## What I implemented
- `antenna/src/metronome-engine.ts`: `MetronomePort`, `MetronomeEngine.renew`, plus private `serial`, `episode`, `begin`, `flush`, `disarm`, `boundedPut`, `write`, `renewSteps`. Copied verbatim from brief Step 4.
- `antenna/test/metronome-support.ts`: verbatim from brief Step 1 (E, D, CFG, HORIZON, FALLBACK, lease, FakePort, engineAt, settle, seqOf, lastListed).
- `antenna/test/metronome-renew.test.ts`: verbatim from brief Step 2 (26 tests).
- I made no deviations from the brief. Before using them I checked that every core export the brief imports exists in metronome-core.ts, and that `MemoryBucket.puts(key)`, `failPuts` and `objects` exist.

## Tests
- RED: `cd antenna && npx vitest run test/metronome-renew.test.ts` gave `FAIL ... Error: Cannot find module '../src/metronome-engine' imported from .../test/metronome-support.ts`, `Tests no tests`. This is the expected failure, because the engine did not exist yet.
- GREEN (focused): same command gave `Test Files 1 passed (1)`, `Tests 26 passed (26)`.
- Full: `cd antenna && npm test` gave `Tests 304 passed (304)`, which matches the plan's 304 (278 + 26). `npm run typecheck` (tsc --noEmit) printed nothing and exited 0. The suite output had no warnings or errors apart from vitest's usual fsModuleCache hint.

## Carried invariants (carry-t4.md)
I checked these by reading the code and with mutants. The mutants ran in a scratch copy (`git archive HEAD antenna | tar -x`, node_modules symlinked, vitest run from the copy). A sentinel mutant M0 (switch inverted) failed 24/26, which shows the copy was the code being tested. I wrote down a prediction for each mutant before running it.
1. **stalls written on every renew**: the code does it. The final `flush(tx, true)` covers every path past the switch, and the invalid-lease path also calls `flush(tx, true)`. Pinned by **"renew: stalls > every renew writes stalls, unchanged or not, so a healthy DO writes a row every minute"**. It covers renew(null) with no lease (0->0, ops `["save stalls"]`) and an expired lease (`["deleteAlarm","save stalls"]`). Mutant M2 (final flush without withStalls) fails exactly that test, as predicted. Hold and blocked go through the same final flush, but no test asserts ops for those two states specifically. The switch-off path writes nothing (the test asserts `store.size 0`), which is consistent with "while METRONOME is on". A load failure throws before any save, which is the fallback (a) path.
2. **playSince set when the lease goes live**: it is set on accepting a lease whose `leaseKind` is "play" when the previous kind was not "play" (none, blocked, hold or expired all reset it). Mutant M7 (never set) fails 4 tests: "accepts, writes ... records playSince", "expiry ... a new lease restarts it", "renew's own write never confirms a tick", "counts from playSince". One gap remains: if storage held a live play lease but no `playSince` (corrupt or missing key), `stalledFor` measures from `lastAlarmGoodAt ?? 0`, a spurious huge stall. The engine's own writes cannot produce that state.
3. **nextTarget called with max(now, lastTarget)**: the code does this (`Math.max(now, s.lastTarget ?? -Infinity)`). **NOT pinned.** Mutant M1 (replace with `now`) passes 26/26, as predicted. No renew test arms an alarm while `lastTarget > now`. Maybe Task 5's alarm tests cover it; otherwise it needs a test.
4. **recordTime keep = cap, capAllows checked first with the same clock**: there is one call site, `recordTime(tx.s.putTimes, now, MAX_DO_PUTS_PER_MINUTE)`, right after `capAllows(tx.s.putTimes, now, MAX_DO_PUTS_PER_MINUTE)`. Both use the single `now = port.now()` read. **The `keep` value is NOT pinned.** Mutant M6 (`keep = cap + 5`) passes 26/26, as predicted. Behaviourally that is near-harmless, because `readState` trims `putTimes` to the last 10 on every load and `capAllows` counts only in-window times. The stored array could still exceed the fixed size within a call.
5. **cap slot reserved and its write awaited before the PUT**: the code does this (`recordTime`, then `await this.flush(tx)`, then `boundedPut`). Pinned by "reserves the cap slot in storage before the PUT is issued". Mutant M5 (flush removed before the PUT) fails exactly that test.
6. **lastBody cleared on a PUT timeout**: the code does this. Pinned by "a PUT that does not settle within 5 s ... clears lastBody". Mutant M4 fails exactly that test.
7. **invalid stored lease deleted; validateLease before decideLease**: `begin()` saves `{lease: undefined}` when `leaseInvalid` is non-null, and in step 3 `validateLease` runs before `decideLease`. Pinned by "an unparseable stored lease is deleted on load". Mutant M9 fails exactly that test.
- Serialization: mutant M8 (calls renewSteps directly, without `serial`) fails "overlapping renews run one after the other".

## Self-review
- The diff is the three brief files, verbatim, with no other changes. The unused imports (`LATE_LOG_MS`, `MAX_ALARMS_PER_MINUTE`, `confirms`, `type MetronomeState` used only in Tx) are deliberate for Task 5, as the brief says. tsc does not flag them.
- At most one PUT per call: renew calls `write` once. The off switch runs inside the serialized section too.

## Concerns
- Invariants 3 (max(now, lastTarget)) and 4 (recordTime keep) are implemented but survive mutation in this task's tests. I did not add tests, because the plan fixes the count at 304 and the carry file says to report. Recommend pinning both, in Task 5 or as a reviewer-driven addition.
- Observation only, no behaviour change: after a 5 s timeout the hung `putLive` keeps running in the background. If it lands after a later PUT, R2 could briefly hold the older body. The spec bounds the wait, not the in-flight request.
