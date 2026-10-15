**Task quality: Approved** (no Critical or Important findings; three Minor test-coverage gaps, all shown by surviving mutants)

### Strengths
- `alarm()` (antenna/src/metronome-engine.ts:72-84) keeps the never-throw contract simple. The switch-off delete and `serial(alarmSteps)` both sit inside one try/catch, so a rejection from `alarmSteps` is logged as `metronome-alarm-error` and never reaches the runtime. The `serial` chain swallows the rejection, so later work is not poisoned.
- The steps in `alarmSteps` (engine.ts:184-245) run in the order the spec gives, with a comment at each step. Each step's early exit flushes `tx`, so an invalid-lease deletion and the counted `alarmTimes` persist on every path, the re-arm failure included.
- The spend paths are bounded:
  - the duplicate path (2b) is checked before the alarm counter, never re-arms, and can PUT only through `write()`, which applies the shared PUT cap (engine.ts:165);
  - `capAllows` fails closed on a non-finite clock (core.ts:175);
  - `lastTarget` loads through `numOrNull`/`finite` (core.ts:222,259), so `tickBoundary` and the `Math.max(now, lastTarget)` re-arm cannot see NaN.
- `tickBoundary` (engine.ts:59-60) is the minimal form of the ruling. It reuses `gridOf(...).dMs` rather than adding a constant, gives `now` in every case except the early-tick window, and is shared by both build sites (engine.ts:207, 293), so the duplicate path and renew cannot drift apart.
- The tests check real behaviour against a fake port and record the ops each case performs. The duplicate test's ops filter (alarm.test.ts ~98-109) allows only `save lastAlarmGoodAt`, so it rules out a re-arm, a count and a lastTarget save all at once. Re-arm-first ordering, the off-by-one at the cap (12/13), the rolling window (59_999 / 60_001), the re-arm failure, a failed PUT and the renew/alarm interleave are each tested.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **Nothing tests that a PUT-capped write does not confirm the tick.** The rule is `confirms` at engine.ts:55, used at engine.ts:208 and 242.
   - Mutant M-A adds `|| r === "cap"` to `confirms`. I predicted it would survive; it did, 55/55 green across the alarm and renew tests.
   - Why it matters: if a capped tick counted as alarm-good, the stall count would hide a frozen playlist and cron would not take over. That is a continuity rule, and the spec names only PUT, identical and null as confirmations.
   - Fix: in "the PUT cap holds across alarms and renews" (alarm.test.ts, caps block), assert `port.store.get("lastAlarmGoodAt") ?? null` is null after the capped `deliver`.
2. **Nothing tests that the duplicate path writes when the bytes differ.** The code is at engine.ts:205-210.
   - Mutant M-C replaces the 2b write with a bare `s.lastAlarmGoodAt = now`. I predicted it would survive; it did, 55/55.
   - Why it matters: every duplicate test expects no PUT. The case the write exists for is a retry after a handler that re-armed but died before its PUT (stored `lastTarget` is still the old value, so `tickBoundary` gives `now`). That case is never exercised, so dropping the write would freeze the playlist for one boundary without failing a test.
   - Fix: add one `it` with an unchanged stored `lastTarget`, a pending alarm and `now` a segment later. Expect exactly one PUT and no re-arm.
3. **Nothing tests step 2's "delete any pending alarm".** The code is at engine.ts:194-197.
   - Mutant M-D removes the `await this.disarm()` there. I predicted it would survive; it did, 55/55.
   - Why it survives: every step-2 test sets `alarmAt = null` before calling `alarm()`. The parametrised cases do it explicitly; the carry test does it through `deliver`. So the disarm is never observed against an alarm that is still pending.
   - Impact is small: a surviving pending alarm only fires once more and returns at step 2.
   - Fix: in the parametrised "when it must not tick" cases, use `deliverDuplicate` (the alarm stays set) and assert `alarmAt` is null afterwards.

(Noted, not raised: no engine-level test checks that stored `alarmTimes`/`putTimes` stay at or below their caps. Both call sites pass the cap as `keep`, and both `recordTime` and the `times()` read slice to it (core.ts:223), so a single mutant cannot grow storage.)

### Checks run
- Takeover flags: absent before the scratch copy and before this write.
- Named risk "NaN `lastTarget` reaches `tickBoundary`/re-arm": checked `readState` (core.ts:222,259). It uses `numOrNull`, which keeps only finite values. No issue.
- Mutants, run in a scratch copy (`git archive 72858f6 antenna`, node_modules symlinked), running `npx vitest run test/metronome-alarm.test.ts test/metronome-renew.test.ts` from the scratch cwd. Baseline: 55 passed.
  - M-A (`cap` confirms): predicted to survive; survived.
  - M-B (the duplicate path records `alarmTimes`): predicted to be caught by "duplicates after a completed tick"; caught by exactly that test (1 failed / 54 passed). This also shows the scratch copy ran the mutated source.
  - M-C (the duplicate path never writes): predicted to survive; survived.
  - M-D (step 2 without disarm): predicted to survive; survived.
- Structure: the engine grew 85 lines and the new test file is 327 lines. `tickBoundary` is module-level beside `confirms`. The file layout matches the brief.

**Reasoning:** `alarm()` is correct and bounded on every spend path. The cap, re-arm targeting, duplicate idempotence and the never-throw contract are all tested, and those tests caught the mutant I aimed at them. The remaining gaps are untested continuity rules, not spend defects.
