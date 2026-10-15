# t4-spec: Task 4 spec-compliance review (bec70fb..aeef49d)

### Verdict
**Spec compliance: Pass.** I found no Critical or Important issues. There are three Minor test-coverage gaps (the brief's tests leave some spec rules unpinned) and two cannot-verify items.

### Spec Compliance
- ✅ **Spec compliant.** All three brief files are present, and each is byte-identical to the brief's code block. I checked this by extracting the brief's three ```ts blocks and diffing them against `git show aeef49d:<file>`: all three IDENTICAL. The change has no other files and no extra features. Test count: `grep -c it(` on `antenna/test/metronome-renew.test.ts` = 26, which matches 278 + 26 = 304.
- ✅ **Produced interfaces match the brief.**
  - `MetronomePort` has `now`, `switchOn`, `config`, `load`, `save`, `getAlarm`, `setAlarm`, `deleteAlarm`, `putLive`, `timer` and `log` (`antenna/src/metronome-engine.ts:24-43`).
  - `MetronomeEngine` has `constructor(port)` and `renew(lease: unknown): Promise<MetronomeStatus>` (`:67-69`).
  - `test/metronome-support.ts` exports `E`, `D`, `CFG`, `HORIZON`, `FALLBACK`, `lease`, `FakePort`, `engineAt`, `settle`, `seqOf` and `lastListed`.
- ✅ **Spec renew step 1, the switch.** It is checked first and inside the serialized section. When off, it calls `deleteAlarm`, writes no storage and returns `applied: "off"` (`metronome-engine.ts:165-169`). Pinned by "renew: the switch".
- ✅ **Step 2, load and stalls.**
  - `begin()` validates through `readState`. An invalid stored lease is logged with `source: storage` and deleted.
  - `stalledMs` is computed from the stored lease's `isLive` before apply, as now − max(lastAlarmGoodAt, playSince).
  - `nextStalls` is `> METRONOME_STALE_MS` (30_000) ? +1 : 0. I checked this in core:193.
- ✅ **Step 3, apply.**
  - `validateLease` runs before `decideLease`. The invalid path logs `metronome-lease-invalid` with `source: renew`, nulls the lease, flushes with stalls and disarms.
  - `decideLease` accepts blocked leases and holds unconditionally, and an unblocked lease only when there is no current lease or when its `verdictAt` is strictly greater (core:146-150).
  - `storedLease` sets `expiresAt = min(validUntil, now + 15 min)` (core:122). Expiry is written negated (core:127).
  - `playSince` is set when an accepted lease is "play" and the previous kind was not "play".
- ✅ **Step 4, write.**
  - The write runs only under an unexpired "play" lease, blocked or not. It builds through `renderLive`, with the off-air notice numbered from `now + MAX_LOOP_MS`; `MAX_LOOP_MS` = 75_000 (clock.ts:126).
  - The identical-body check against `lastBody` comes before the cap check, so an identical body uses no cap slot.
  - The cap is `capAllows(putTimes, now, 10)` and is then reserved via `recordTime(..., now, 10)`. Both use the same single `now`.
  - The reserve flush is awaited before `boundedPut`.
  - `boundedPut` races the PUT against a `DO_PUT_TIMEOUT_MS` (5_000) timer and clears the timer in `finally`.
  - A failed PUT (timeout or throw) clears `lastBody`.
  - `wrote` maps put→true, failed→false, and identical/cap/null→null.
- ✅ **Step 5, arm.** It arms only when `isLive` and no alarm is pending, with `nextTarget(gridOf(horizon), max(now, lastTarget))`, and persists `lastTarget`. In every other case it deletes any pending alarm. Blocked, hold, expired and absent leases never re-arm. A cap-skipped write still falls through to arming.
- ✅ **Step 6, return.** The `MetronomeStatus` fields match the spec: `lease` after the call, `stalledMs` from before the call, and `leaseVerdictAt` from the current lease.
- ✅ **Serialization.** `serial()` wraps the whole of `renewSteps`, the switch check included, in one promise chain that runs after both resolve and reject. Pinned by "overlapping renews run one after the other".
- ✅ **Spend bounds that apply to renew.** At most one PUT per call, because `write` is called once. The cap is 10 per rolling 60 s with the slot reserved first. The PUT is bounded at 5 s. A blocked lease writes once per call and nothing ticks. Hold, expired and no lease write nothing. A NaN clock fails closed: `expired()` is true, so there is no current lease and therefore no write, and `capAllows` returns false.
- ✅ **Log event names** match the spec's vocabulary: `metronome-lease-invalid`, `-lease-superseded`, `-cap`, `-put-failed`, `-hold`, `-expired`, and `offair-without-fallback`. `metronome-null-build` is engine-local. The spec says "logged once per lease" without naming the event.
- ✅ **Carried invariants (carry-t4.md).** Each one below is done in code, and I note which test pins it.
  1. `stalls` is saved on every renew past the switch: the final `flush(tx, true)` and the invalid path's `flush(tx, true)`. Pinned by "every renew writes stalls, unchanged or not, so a healthy DO writes a row every minute", which covers renew(null) with no lease and an expired lease.
  2. `playSince` is set on the first accepted unblocked play lease. Pinned by "accepts…records playSince", "expiry…a new lease restarts it" and "counts from playSince".
  3. `nextTarget` is called with max(now, lastTarget). In code only, not pinned (see Minor 1).
  4. `recordTime` keep = cap, with `capAllows` checked first with the same `now`. In code only; the keep value is not pinned (see Minor 2).
  5. The cap slot is reserved before the PUT. Pinned by "reserves the cap slot in storage before the PUT is issued".
  6. `lastBody` is cleared on a timeout. Pinned by "a PUT that does not settle within 5 s…".
  7. An invalid stored lease is deleted, and validation runs before ordering. Pinned by "an unparseable stored lease is deleted on load" and by the "after a deploy" test.

- ⚠️ **Cannot verify from this diff:**
  - **(a) A throw in step 5 skips the final flush.** If `port.setAlarm` throws (or `getAlarm` does, or the reserve or final `save` does), `renew` rejects before the final `flush`. Nothing persists this call's `stalls`, its `lastTarget`, or a `lastBody = null` set by a timed-out PUT in the same call. The spec treats a throwing renew as fallback trigger (a), so this matches the spec's error model. `putTimes` was already reserved and persisted, so spend stays bounded. The only literal gap is "a PUT timeout sets lastBody to null" in this compound-failure case, and it is practically harmless because a later build differs from the old body. Whether cron fully handles a rejection is Task 7/8.
  - **(b) The `max(now, lastTarget)` hot-loop rule and the 12-per-60 s alarm cap live in `alarm()`.** Task 5's tests must pin them. The `MetronomePort` binding, including timer clearing and `env.METRONOME === "on"`, is Task 6.

### Issues
#### Critical (Must Fix)
None.
#### Important (Should Fix)
None.
#### Minor (Nice to Have)
1. **`max(now, lastTarget)` is unpinned in renew.** See `antenna/src/metronome-engine.ts:214`. No renew test arms while `lastTarget > now`. The one test that comes close is "a lagging older blocked lease…", whose third renew arms at T, which is less than the stored lastTarget E+1001D+25. That test asserts only `alarmAt` not null, so replacing the argument with `now` survives; the implementer's mutant M1 agrees with my reading. Recommend that Task 5, or a review-driven addition, assert `alarmAt === E + 1_002*D + ALARM_SLACK_MS` there.
2. **`recordTime`'s `keep` value is unpinned.** See `metronome-engine.ts:149`. Its behavioural impact is minimal, because `readState` trims on load and `capAllows` counts only in-window entries. Still, nothing pins that the stored `putTimes` never exceeds 10 entries.
3. **"A cap-skipped renew write… and the chain re-arms" is not asserted by any renew test.** This rule is from the spec's test list. In the flap test the capped 11th lease is blocked (`i % 2 === 0`), so it disarms. Hold and blocked renews also have no ops-level assertion of the `save stalls` row; they share the final flush with the tested paths. The code does both, so this is a coverage gap only.
