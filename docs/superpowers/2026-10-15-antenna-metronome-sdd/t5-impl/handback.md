# t5-impl handback: Task 5, metronome-engine.ts alarm()

**Status:** DONE
**Commit:** 4ecc3c4 feat(antenna): metronome engine alarm: re-arm first, rolling caps, never throws (on d555ee2)

## What I implemented
- `antenna/src/metronome-engine.ts`: `alarm()` (inserted before `serial`) and `alarmSteps()` (inserted before `renewSteps`), the brief's code verbatim (extracted programmatically from the brief). Both anchors were still present unchanged; renew's new early `await this.flush(tx)` (d555ee2) is untouched. No conflict with the carry changes.
- `antenna/test/metronome-support.ts`: `deliver` and `deliverDuplicate`, verbatim, before the `settle` doc comment.
- `antenna/test/metronome-alarm.test.ts`: the brief's 25 tests verbatim, plus the carry's added test (in "alarm: when it must not tick"):
  "a renew that stored a hold or a block, then threw on its alarm op: the still-pending alarm writes nothing and does not re-arm". It loops over a hold lease and a blocked play lease (verdictAt T+1000) accepted over the live play lease from `playing()` with its alarm pending at target(1001). `failDeleteAlarm` makes renew reject (`/deleteAlarm/`). It asserts the stored lease is the new hold/blocked lease and the alarm is still pending. Then `deliver(...)` runs and it asserts: no new PUT, the body unchanged (for blocked that is the renew's off-air body), the alarm null, and no `setAlarm`/`put` op.
  I used only `failDeleteAlarm`. For a hold or blocked lease, renew's alarm op is `disarm()` → `deleteAlarm`; `setAlarm` is never reached (`isLive` is false for both), so `failSetAlarm` cannot make those renews throw.

## Tests
- `cd antenna && npm test` → `Tests  334 passed (334)` (308 + 25 brief + 1 carry = 334, as expected)
- `cd antenna && npm run typecheck` → tsc silent, exit 0
- No stderr/warnings in the alarm test file's output.

## TDD evidence
- RED: `npx vitest run test/metronome-alarm.test.ts` → `Tests  26 failed (26)`, `TypeError: engine.alarm is not a function`; `npm run typecheck` → `TS2339: Property 'alarm' does not exist on type 'MetronomeEngine'` (5 sites). Expected: alarm() not yet written.
- GREEN: same command → `Tests  26 passed (26)`; full suite 334 passed.
- RED for the added test (scratch copies via `git archive HEAD antenna | tar -x` in the scratchpad, run from the scratch cwd; predictions written before running):
  - M1, renew's early "stored before any alarm op" flush deleted. Predicted: the new test + the renew pin fail. Actual: exactly those 2 failed, 332 passed. The new test fails first on its stored-lease assertion (received kind 'play'). I then removed that one assertion in the scratch copy to check the alarm-side half: it fails at `expect(port.puts()).toBe(puts)` (2 vs 1), because alarm() sees the surviving live play lease and writes. So the alarm-side assertions are live too.

## Report-only checks (carry item 5)
- **Re-arm from `max(now, lastTarget)` pinned?** Yes. M2 (scratch, `Math.max(now, prevTarget ?? -Inf)` → `now` in alarmSteps). Predicted: only the early-alarm test fails. Actual: exactly "an alarm delivered before the DO's clock passes its boundary builds for that boundary and moves on" failed, 333 passed.
- **Stored `putTimes`/`alarmTimes` never exceed their caps?** Only at the core level: metronome-core.test.ts "records into a fixed-size list" pins `recordTime` to length 12 over 30 records. No engine-level test asserts the stored arrays' length stays ≤ the cap. The nearest is the interleave test's `putTimes.length === 2`, and the alarm-cap test makes only 14 deliveries without checking `alarmTimes` length. Both engine call sites pass the cap as `keep`.
- **Previously unused imports now used?** Yes: `LATE_LOG_MS` (metronome-late episode), `MAX_ALARMS_PER_MINUTE` (alarm cap and its `recordTime` keep), `confirms` (steps 2b and 6). typecheck is clean.

## Files changed
- /Users/shawn/projects/llama/.claude/worktrees/antenna-metronome/antenna/src/metronome-engine.ts
- /Users/shawn/projects/llama/.claude/worktrees/antenna-metronome/antenna/test/metronome-support.ts
- /Users/shawn/projects/llama/.claude/worktrees/antenna-metronome/antenna/test/metronome-alarm.test.ts (new)

## Self-review
- Diff is the brief verbatim plus the one carry test. Names follow the existing episode/flush patterns, nothing extra.
- Step 2b (duplicate) is not counted against the alarm cap and never re-arms. It can PUT only when the bytes differ, and then still under the shared PUT cap. This is the spec's intent (reading 9) and is noted here only as the spend reasoning.

## Concerns
- None blocking. Small gaps: no engine-level pin on stored cap-array length (above), and `failSetAlarm` is not exercised by the carry test (not reachable for hold/blocked).
- Scratch copies left at the scratchpad `m1/`, `m2/` (and older `mut4`, `mutA`, `t4spec` from earlier tasks). Nothing in the live worktree was mutated. I did not delete the scratch dirs: an `rm -rf` on a variable path was blocked by a safety check, and the dirs were fresh anyway.

## Fix round 1 (t5-fix1.md, controller ruling)
**Commit:** 72858f6 fix(antenna): a duplicate alarm or a renew after an early tick never builds an older playlist

### Changes
- `antenna/src/metronome-engine.ts`: a new module-level helper `tickBoundary(lease, lastTarget, now) = Math.max(now, (lastTarget ?? now) - gridOf(lease.horizon).dMs - ALARM_SLACK_MS)`. `dMs` comes from the engine's existing `gridOf` helper, so no new constant was added. Two build sites use it:
  - the 2b duplicate path: `this.write(tx, cur, tickBoundary(cur, s.lastTarget, now), now, ...)`;
  - renew step 4's live write: the same expression.
  `s.lastTarget` is the value as loaded at both sites. 2b never re-arms, and renew arms only in step 5, after the write. The off-air numbering argument (`now + MAX_LOOP_MS`) is unchanged. The genuine tick's step 5 is unchanged. I updated the comments at both sites. Nothing like "refuse a lower MEDIA-SEQUENCE" was added.
- `antenna/test/metronome-alarm.test.ts`: two new `it`s in "alarm: the tick", both in the alarm file because they need `deliver`:
  1. "an early tick, then a duplicate still before its boundary: the same bytes, no PUT, no re-arm". It runs `deliver` at target(1001)−40, then `deliverDuplicate` at target(1001)−35. It asserts: the PUT count is unchanged, the body is identical, MEDIA-SEQUENCE is unchanged, alarmAt and the stored lastTarget are still target(1002), and there is no setAlarm/deleteAlarm op.
  2. "an early tick, then a renew still before its boundary: the same body, no PUT, MEDIA-SEQUENCE never goes backwards". It runs `deliver` at target(1001)−40, then `renew(lease(t))` at target(1001)−35. It asserts: `{applied: "accepted", wrote: null}`, the PUT count is unchanged, MEDIA-SEQUENCE is ≥ the previous value, the body is identical, and alarmAt is target(1002).
  - The carry test gains `expect(port.events("metronome-alarm-error")).toEqual([])` after `deliver`.

### RED (current code, before the src change)
`npx vitest run test/metronome-alarm.test.ts` → `Tests  2 failed | 26 passed (28)`:
- test 1: `expected 3 to be 2` at the PUT-count assertion (the duplicate PUT the older playlist, as in the reviewer's probe);
- test 2: `"wrote": null` expected, `"wrote": true` received (renew PUT the older playlist).
The carry test's new assertion passed on the current code, as expected: it pins existing behaviour.

### GREEN
`cd antenna && npm test` → `Tests  336 passed (336)`. `npm run typecheck` → tsc silent, exit 0. The existing tests ran unmodified and pass: the epoch change, duplicates after a completed tick, and a duplicate then a renew in the same segment. The only edits to existing tests are the one added assertion.

### Notes
- The scratch copies m1/ and m2/ are left in place, as asked.
