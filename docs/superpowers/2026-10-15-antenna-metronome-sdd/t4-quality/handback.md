**Task quality: Approved** (Minor findings only; Task 5 should pin carried invariants 3 and 4)

### Strengths
- `antenna/src/metronome-engine.ts:110-123`: `boundedPut` never throws. A synchronous throw from `putLive` is caught, because it is built inside the `try`. `Promise.race` subscribes to the losing PUT, so a PUT that rejects after the timeout is not an unhandled rejection.
- `metronome-engine.ts:144-151`: the identical-body skip runs before the cap check, so an unchanged playlist never consumes a slot or logs a false `metronome-cap`. The slot is reserved, and `flush` awaited, before `boundedPut`. That pre-PUT flush also persists an accepted lease and `playSince` before any spend.
- `metronome-engine.ts:69-73`: `serial` uses `then(fn, fn)` and a `catch` on the stored chain, so one rejected renew cannot poison the calls after it. Pinned by "overlapping renews run one after the other" (test:309).
- NaN and missing values fail closed through core. `capAllows` refuses a non-finite clock (core:175). `numOrNull` and `times` drop non-finite stored values, so `Math.max(now, lastTarget)` (engine:215) cannot see a stored NaN. A NaN `now` makes `currentLease` null, so there is no write and no arm.
- The tests check real behaviour through a `MemoryBucket` and an ordered `ops` log. They cover the cap at 59 999 and 60 001 ms, the timeout clearing `lastBody` and the re-write that follows, a `validUntil` far in the future, and `renew(null)` or a superseded lease never extending the lease.
- Plausible mutants that tests catch, by my reading: arming whenever `cur.kind === "play"` without `isLive` (caught by "blocked … leaves no alarm pending", test:144). Dropping `!wasPlay` at engine:196 (caught by "two renews over a dead chain count 1 then 2": the second stalledMs would be 40 000, not 80 000). Skipping the `lastBody = null` on timeout (caught, test:282).

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **Carried invariant 3 is not pinned** (engine:215). No renew test arms while `lastTarget > now` and no alarm is pending. In every re-arm test, the stored `lastTarget` (≈T+7.3 s) is below the new `now` (T+40 s or later), so the mutant `max(now, lastTarget)` → `now` survives. This matches the implementer's M1. In renew the mutant is nearly harmless: the case only arises after a disarm, and re-arming the same deleted boundary is not a double fire. The real risk is `alarm()` firing early, which is in Task 5. Fix: pin it in Task 5's alarm tests, or add one renew test (hold-disarm then play-accept inside one segment, asserting `alarmAt === lastTarget + D`).
2. **Carried invariant 4 (`keep`) is not pinned** (engine:150). The mutant `keep = cap + 5` survives. That matches M6, and it is behaviourally inert, because `readState` trims `putTimes` to 10 on load (core:258) and `inWindow` filters. Fix: a core-level `recordTime` test, or assert `putTimes.length <= 10` after the 11-write cap test (test:254).
3. **Carried invariant 1 is pinned only on the absent and expired paths** (test:233). The invalid-lease path's `flush(tx, true)` (engine:188) is unpinned. The mutant `flush(tx)` there writes zero rows when no lease was stored (invalid lease, no stored lease, stalls 0→0), which is the empty-is-not-zero case. Fix: in the test at test:64 (or a fresh engine), assert that `ops` contains `"save stalls"` after an invalid lease on an empty store.
4. **Alarm-op failure skips the lease persist** (engine:205-222). On the hold path, and on a blocked or play path whose write was identical or cap-skipped, nothing is saved before `disarm()`/`setAlarm()`. If that alarm op throws, the newly accepted lease and `stalls` are never written. An accepted hold could then leave the old play lease stored while a still-pending alarm ticks the live playlist. The impact is bounded: renew rejects, so cron falls back. A failing alarm op also breaks `alarm()`'s own re-arm. The next renew retries within a minute, and the old lease expires on its own 15 min clock. `failSetAlarm` exists in support (support:38) but no renew test uses it. Fix (it changes plan code, so it is the controller's call): call `flush(tx)` after step 3, before any alarm op, or move the final `flush(tx, true)` ahead of step 5 and save `lastTarget` separately.
5. **The "logged once" test asserts a range** (test:105-113). The test name says "logged once", but the assertion is 1..3. The three superseded verdicts (T-1, T, T-2) are distinct episode ids, so the code logs 3, and removing the dedup in `episode` (engine:76-84) also gives 3, so the test passes. Fix: re-send the same older `verdictAt` twice and assert exactly one log per distinct `verdictAt`, or rename the test.
6. **Dead code ahead of Task 5** (plan-mandated): `LATE_LOG_MS` and `MAX_ALARMS_PER_MINUTE` are imported (engine:19-20) and `confirms` is declared (engine:55), all unused. tsc is silent only because `noUnusedLocals` is off. Fix: none needed if Task 5 uses them. Confirm at the Task 5 review.
7. **Implementer's observation, confirmed as inherent** (engine:110-123). After a 5 s timeout, the abandoned `putLive` can land after a later PUT and leave an older body in R2. In the worst order, a live playlist lands over a blocked notice. That lasts until the next differing write, at most about a minute while blocked, because the notice's sequence number moves every renew. R2 `put` takes no abort signal, so this cannot be fixed here. Fix: one line in the spec's known-limitations section.
8. `renew(undefined)` is mapped to `null`, a health check (engine:68). This is safe: `null` never extends a lease (pinned at test:186). Noted only so that Task 6's RPC binding does not rely on `undefined` meaning "invalid".

### Checks run
- Read the diff in full: engine, 26 tests and support.
- Named risk "NaN or non-finite stored values reach `nextTarget` or the cap": read core `capAllows`, `numOrNull`, `times` and `readState` (core:174-182, 222-264). They fail closed.
- Named risk "the off path diverges from the spec": spec step 1 (spec:240) says "delete the alarm, return applied off". It matches engine:179-183, and that path writing no storage is consistent with the spec.
- Mutation verdicts in items 1-5 come from reading the test data against the code, not from runs. They agree with the implementer's M1, M2 and M6.
- Tests were not re-run, per the seat rules. The implementer's report (304 passed, tsc silent) has no warnings beyond vitest's fsModuleCache hint.

### Assessment
**Task quality:** Approved
**Reasoning:** The spend bounds are implemented correctly and pinned: the cap reserved before the PUT, the 5 s bound clearing `lastBody`, the identical skip, one PUT per call and the serialized section. NaN fails closed. The gaps are unpinned or benign mutants, plus one narrow failure-path ordering whose spend is bounded. Pin carried invariants 3 and 4 in Task 5.
