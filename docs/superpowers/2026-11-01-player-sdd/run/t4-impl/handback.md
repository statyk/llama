Status: DONE_WITH_CONCERNS (interpretations only; nothing contradicted, no test loosened)
Commits: 6b73ea69 antenna: recovery decisions as a pure tested module; 676b9a42 antenna: recovery test, a higher first sample that isn't a jump
Tests: `cd antenna && npm test && npm run typecheck`: Test Files 25 passed (25), Tests 511 passed (511), tsc clean. Focused: 51 passed (51).
Mutation: all 5 required mutants plus 6 extras went red on the predicted test. One extra exposed a weak test, now fixed.
Concerns: see "Concerns" below. The one Task 8 must act on is 1. Interpretations for the reviewer are 2-4.
Handback: /Users/shawn/projects/llama/.claude/worktrees/player/.superpowers/sdd/player/t4-impl/handback.md

# Task 4 report

## Implemented

`antenna/public/assets/recovery.js`: everything in the brief's Interfaces.
- `prefersNativeHls` and `classifyProbe` copied unchanged; a test compares their `toString()` with nowplaying.js's. nowplaying.js, player.js and style.css are untouched and not imported by recovery.js.
- `playBlockedNotice` copied with the text "Playback was blocked."
- `immediateOffair`, `pauseMeansStop`.
- `class Recovery` with the constructor's values verbatim.

How it holds together:
- `tick`: sample, then give-up, then (restart asked: none), then failure detection, then delay, then fresh reachable gives restart, else a probe if none is in flight and probeEveryMs has passed.
- One field, `lastAudioMs`, is both the give-up clock and the stall clock; `begin` sets it.
- A sample is a baseline (first after begin/restarted), a jump (rise above wall clock + slack, re-baselines), an advance (rise above zero, within the bound) or frozen (no rise).
- An advance: updates lastAudioMs, zeroes the off-air count, clears any pending failure and join, and grows the continuous run that resets the delay after resetAfterMs. A frozen, jump or baseline sample ends the run.
- The delay index is the number of restarts, incremented in `restarted`, so backoff is between restarts and a self-recovered stall doesn't grow it.

## TDD evidence

RED: `cd antenna && npx vitest run test/recovery.test.ts`
```
FAIL  test/recovery.test.ts [ test/recovery.test.ts ]
Error: Cannot find module '../public/assets/recovery.js' imported from .../antenna/test/recovery.test.ts
Test Files  1 failed (1)
     Tests  no tests
```
First GREEN attempt: 50 passed, 1 failed. It was my own test: it expected a probe 13 s after the previous one, and probes stay spaced across a restart. I fixed the test's timing. That test was not one of the brief's; the rule it hit is the brief's spacing rule.

GREEN, same command:
```
Test Files  1 passed (1)
     Tests  51 passed (51)
```
Full, on the final tree:
```
Test Files  25 passed (25)
     Tests  511 passed (511)
> tsc --noEmit   (no errors)
```
Every sketched test in the brief is written out in full. I added these: jitter range; an advance cancels a failure; a verdict doesn't carry into the next failure; unreachable leaves the delay alone; verdict exactly verdictFreshMs old is stale; 60 s broken by a stall is not 60 s; a real advance ends the join; a retry doesn't move give-up; give-up beats an asked-for restart; begin starts a new session; the slack boundary; no rise is no advance.

## Mutation check

Scratch copy: `git archive` plus a copied node_modules, run from there, never the live tree. Each mutant asserted the pattern matched exactly once, and vite/vitest/wrangler caches were deleted between mutants. The control (unmutated) passed 51/51 in the same harness. Script output is in t4-impl.log.

| Mutant | Predicted red test | Actual |
|---|---|---|
| M1 restart allowed on unreachable | offline for 8 minutes | RED as predicted, 8 failed |
| M2 stale reachable accepted | a reachable verdict goes stale | RED as predicted, 2 failed |
| M3 unreachable counted towards off-air | two off-air verdicts reach off-air across a retry | RED as predicted, 7 failed |
| M4 advance slack bound removed | a jump after a restart is not progress | RED as predicted, 3 failed |
| M5 delay reset on a brief advance | the delay does not reset on brief progress | RED as predicted, 2 failed |
| X1 restart checked before give-up | the give-up check wins over a pending restart | RED as predicted, 2 failed |
| X2 failed() not ignored during a delay | repeated failed() during a delay or join | RED as predicted, 2 failed |
| X3 baseline not cleared on restart | the first sample after a retry is a baseline | RED as predicted, but only 1 failed: see below |
| X4 reachable resets the off-air count | verdictsNeeded off-air verdicts survive a reachable one | RED as predicted, 4 failed |
| X5 no join after a restart | a retry gets joinMs | RED as predicted, 9 failed |
| X6 unreachable moves the delay | at most one probe at a time, spaced | RED as predicted, 1 failed |

X3 showed "a higher first sample after a retry is a baseline too" passed for the wrong reason: 300 to 310 one second on took the jump path, so it never exercised the baseline rule. Moved that sample to 10 s after the restart, which is not a jump. Re-scored with X3's prediction naming that test: RED, 2 failed (that test and the lower-sample one). Control still 51/51. Commit 676b9a42.

The 11 mutants ran against 6b73ea69's test file. Only that one test changed afterwards, and only X3 was re-run.

## Files changed

- antenna/public/assets/recovery.js (new, 212 lines)
- antenna/test/recovery.test.ts (new, 681 lines)

## Self-review

Read the diff for completeness against the brief, and removed two things I found unnecessary: a guard in `advance` for an outstanding restart, and a `clearAttempt` in `fail` that nothing needed. No fields or options beyond the brief. The test file is long, as the brief's list is long.

## Concerns

1. For Task 8: `verdict` takes no time, per the brief, so a verdict's age counts from the latest time the module saw (a tick, usually). It can only read older than it is, which is the safe direction, and it relies on Task 8's "run tick at once on a verdict". A probe that outlives a frozen page therefore reads stale and gets a new probe. Task 8's session counter must also drop a verdict from before a Stop or a new `begin`; `begin` clears the state but the module cannot tell an old answer from a new one.

2. Interpretation, the stale-verdict test: the sketch says a tick "more than verdictFreshMs later" gets "probe", but the default spacing is 15 s and freshness 10 s, so a tick 10-15 s after the verdict returns "none" and the probe comes at 15 s. I kept the spacing rule: the test asserts "none" at exactly 10 s, "probe" at 15 s. Never a restart in either case. This matters only on a frozen page, where the gap is usually longer.

3. Interpretation, `stalled` on a baseline or jump sample: both read as neither stalled nor advancing, from the instruction about baselines and "re-baselines" in the brief. `noteWaiting` still makes `stalled` true. So a frozen position reads `stalled` from its second sample after a jump, and a `pause` landing on the jump sample itself would read as a Stop. One-sample window.

4. Interpretation, an advance clears a pending failure, including during its delay. The brief implies it ("Recovered means the position advanced again"), and iOS recovering a 5 s stall needs it. The backoff index is not touched by this.

5. The first Play has no join, which the brief's own test requires (failure at 16 s on hls.js). A start on hls.js taking over about 20 s gets one probe and then a restart. Harmless but worth knowing. The stall clock starts at `begin`, not the first sample; the brief's tick times fit both.

6. `failed` during a join is ignored, per the brief, so a native `error` right after a restart waits out the join (up to 25 s) before counting. A real advance ends the join, so this only applies to a retry that never moved.

# Fix report, review round 1

Finding: a native `error` on an element that was playing was swallowed, because the rise before the error read as an advance on the next tick and cancelled the failure.

Change, commit 671d2f14: `failed`, after its guard, sets `this.lastPos = null`, so the next sample is a baseline. Comment added. An ignored `failed` (during a delay or join) changes nothing.

Tests added, recovery.test.ts:
- "a native error survives the position rising between the last sample and the error": error at 2.7 s, tick at 3 s with the position 2.7, flat after that. No advance, none at 7699, probe at 7700.
- "an element still playing after an error recovers on its second sample": same start, then rising from 4 s. Advancing at 4 s, and none for the next 40 s.

Predicted red, named before running: the first test; the second stays green without the fix.
Scratch copy, HEAD 676b9a42 source plus the new tests, caches deleted before each run:
- Without the fix: the first test RED at `expect(r.advancing).toBe(false)` ("expected true to be false"), 1 failed | 52 passed (53). The second test green, as predicted.
- Without the fix, that advancing line removed from the scratch test: RED at the 7700 line (Expected "probe", Received "none"), 1 failed | 52 passed (53). So both assertions bite.
- With the fix, same harness: 53 passed (53).

Live tree:
- `cd antenna && npx vitest run test/recovery.test.ts`: Test Files 1 passed (1), Tests 53 passed (53).
- `npm test`: Test Files 25 passed (25), Tests 513 passed (513).
- `npm run typecheck`: tsc clean.

Side effect: the error's baseline sample ends any advancing run, so an error during playback starts the 60 s reset again, and `stalled` reads false on that one sample. Same one-sample window as concern 3.
