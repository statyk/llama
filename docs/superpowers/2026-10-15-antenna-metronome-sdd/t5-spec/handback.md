### Verdict
**Spec compliance:** Fail, on one plan-mandated item only. The implementation is the brief verbatim, and every strict-surface requirement passes: the alarm cap, the PUT cap, re-arm targeting, never-throws and fail-closed. The one failure is the brief's own step-2b rule ("build for `now`"), which breaks the spec's duplicate idempotence ("rebuilds the same bytes and skips the PUT") in a pre-boundary window. A probe confirmed it. Fixing it needs a ruling on the plan; the implementer did nothing wrong.

### Spec Compliance
- ✅ Verbatim against the brief, checked programmatically. I extracted the brief's `alarm()` block, its `alarmSteps()` block and its `deliver`/`deliverDuplicate` block, and each is a substring of the committed `antenna/src/metronome-engine.ts` and `antenna/test/metronome-support.ts`. A `diff` of the brief's test file against `antenna/test/metronome-alarm.test.ts` shows exactly one addition, the carry test (lines 152-171). All three files the brief lists have their hunks, and nothing extra was added.
- ✅ Carry item 1: the diff does not touch `renewSteps`, so renew's early lease `flush` from d555ee2 is preserved. Both insertion anchors (before `serial`, before `renewSteps`) were used as the brief says.
- ✅ Spec `alarm()` steps 1-6 (metronome-engine.ts, alarm() and alarmSteps()):
  - Step 1: the switch is checked before `serial`, and the spec puts the serialized section after the env check. When it is off, the alarm is deleted and nothing is written.
  - Step 2: `currentLease` is the negated-expiry check. None, a hold, a blocked lease or an expired lease each go to `disarm()` + `flush`, with no re-arm. A NaN `now` reads as expired, so it fails closed.
  - Step 3: `capAllows(alarmTimes, now, 12)` is checked before `recordTime`. At the cap it does not re-arm, logs `metronome-alarm-cap` and returns, and a non-finite clock trips the cap.
  - Step 4: the re-arm is guarded by `isLive` and targets `nextTarget(grid, max(now, prevTarget))`. I checked `nextTarget` in core: it gives the first `b_n + 25` strictly greater than its argument. The re-arm has its own try/catch that logs `metronome-rearm-failed` and returns without writing, and `lastTarget` is persisted only after `setAlarm` succeeds.
  - Step 5: `due = max(now, prevTarget − 25)` uses the pre-step-4 `lastTarget`. There is a single `write()` call per path, so at most one PUT per alarm. The write is capped, its slot is reserved before the PUT, and the PUT has the 5 s bound.
  - Step 6: `lastAlarmGoodAt` advances only on put, identical or null, never on cap or failed.
  - The whole body is in a try/catch that logs `metronome-alarm-error`, so `alarm()` never rejects.
- ✅ Spend bounds: at most one PUT per `alarm()`. The PUT cap is shared with renew through `putTimes`. Duplicates (2b) are not counted against the 12-alarm cap, but they never re-arm and every PUT they make is under the PUT cap. The spec's alarm bound is defined by "not re-armed", so this complies.
- ✅ The Produces interfaces exist with the stated shapes: `alarm(): Promise<void>`, `deliver(port, engine, t = port.alarmAt!)` and `deliverDuplicate(port, engine, t)`.
- ✅ Carry item 3: the added test is present (metronome-alarm.test.ts:152-171). It covers a hold and a blocked lease accepted over a live play lease, with `failDeleteAlarm` making renew reject. Then, on delivery, there is no PUT, the body is unchanged, there is no re-arm and the alarm is null. The implementer's reason for using only `failDeleteAlarm` is correct: for a hold or blocked lease, `isLive` is false, so renew calls `disarm()` and `setAlarm` is unreachable.
- ✅ Carry item 5: `LATE_LOG_MS`, `MAX_ALARMS_PER_MINUTE` and `confirms` are all used now (the late episode, the cap and `recordTime` keep, and steps 2b/6).
- ⚠️ Cannot verify from the diff: the rule that a pending alarm marks a duplicate (plan reading 9) rests on `getAlarm()` returning null during a genuine handler. The plan assigns that check to Task 6 (workerd) and Task 9 (the real runtime). If it is wrong, every genuine tick is taken for a duplicate and the chain stops re-arming.
- ⚠️ Cannot verify from the diff (Task 4's surface): renew has the same pre-boundary regression as the Important item below. I ran a probe with an early genuine tick at `target(1001)−40`, then `renew` at `target(1001)−35`. Result: `wrote: true`, puts 2→3, MEDIA-SEQUENCE 998→997. The plan's invariant 5 ("MEDIA-SEQUENCE never goes backwards") is pinned only for a renew after the boundary.
- ⚠️ Not re-run: the 334-pass count and the implementer's M1/M2 mutation results (the M2 result shows `max(now, lastTarget)` is pinned by the early-alarm test). I take them as reported.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
- **Plan-mandated: a duplicate that arrives after an early genuine tick, still before the boundary, PUTs an older playlist and MEDIA-SEQUENCE goes backwards** (metronome-engine.ts, alarmSteps step 2b: `this.write(tx, cur, now, now, cfg, "alarm")`).
  - Spec: "A duplicate or retried alarm rebuilds the same bytes and skips the PUT: the handler is idempotent." The spec also explicitly covers alarms delivered before the DO's clock passes the boundary.
  - Why it happens: the genuine early tick builds for `max(now, lastTarget − 25)`, which is boundary 1001. The duplicate builds for `now`, which is still in segment 1000.
  - Probe, in a scratch copy at 4ecc3c4 (`git archive`, run from the scratchpad): `deliver` at `target(1001)−40`, then `deliverDuplicate` at `target(1001)−35`. Result: puts 2→3, MEDIA-SEQUENCE 998→997.
  - Effect: one extra PUT (it is capped, so spend stays bounded), and R2 holds the previous step's playlist until boundary 1002. That is a ~20 s gap between advances instead of 10 s, plus a backwards sequence for any player that fetched in the window.
  - Likelihood: low. It needs an early delivery and then a redelivery within the slack.
  - Fix options, for the plan owner to choose:
    - in 2b, build for the boundary the last genuine tick built for, e.g. `max(now, lastTarget − D − ALARM_SLACK_MS)` on the current grid (check what happens across an epoch change);
    - or refuse any DO write whose MEDIA-SEQUENCE is below `lastBody`'s. That would also close the renew sibling noted above.
  - In either case, add the probe as a pinning test: an early tick, then a pre-boundary duplicate, giving no PUT and the same bytes.

#### Minor (Nice to Have)
- The carry test cannot tell the step-2 return apart from the catch-all path (metronome-alarm.test.ts:152-171). `failDeleteAlarm` stays true during `deliver`. Today `disarm()` sees `getAlarm() === null` and never calls `deleteAlarm`, so step 2 returns cleanly. But an exception would also produce "no put, no setAlarm" and the test would still pass. Adding `expect(port.events("metronome-alarm-error")).toEqual([])`, or resetting `failDeleteAlarm` before `deliver`, would pin the intended path.
- Carry item 5: no engine-level test asserts that the stored `putTimes`/`alarmTimes` stay at or below their caps. It is pinned only at core level (`recordTime`'s keep, and `readState`'s `times(..., cap)` trim), and both engine call sites pass the cap as `keep`. A coverage gap only.
- The alarm-cap window edge at exactly 60 000 ms is unpinned. `inWindow` treats it as outside, i.e. allowed. The spec defines only "just over" and "just under", and both are tested.

### Checks run
- Programmatic substring and `diff` comparison of the brief's code blocks against HEAD.
- Read `disarm`, `begin`, `flush`, `write` (engine), plus `currentLease`, `isLive`, `nextTarget`, `capAllows`, `recordTime` and `readState` (core). Named risks: NaN or malformed state passing the caps or the targeting, and the carry test's delivery path.
- Two focused probe tests in the scratch copy `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-antenna-metronome/7c48a24a-b1ba-48f0-8b4d-9a045fdbda5f/scratchpad/t5spec/tree/antenna/test/probe-dup.test.ts` and `.../probe-renew.test.ts`. Output is in `$D/t5-spec/t5-spec.log`. The live worktree was not modified.
