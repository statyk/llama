# t4fix-impl handback: second fix round (items A, B)

**Status:** DONE

Commit: `d555ee2` fix(antenna): renew stores an accepted lease before any alarm op; trigger (b) covers blocked leases (on top of 2dfda92)

## What was implemented
- **Item A** (antenna/src/metronome-engine.ts, renew step 3): inside `if (applied === "accepted")`, right after `s.lease`/`s.playSince` are set, I added `await this.flush(tx);`, so the accepted lease is stored before any `disarm`/`setAlarm` on every path (play, blocked, hold). The other paths need nothing new: the invalid path already flushes before `disarm`, a superseded or null lease changes no lease state, and an invalid stored lease is deleted in `begin()`. The PUT reservation flush, the final `flush(tx, true)` (stalls, lastTarget) and the order of lastTarget after arming are unchanged. Every renew still ends with the stalls row. I flush only on accept, so a renew(null) does not save stalls twice. The cost is that an accepted renew now makes one more `save` call: the lease and playSince (plus stalls if it changed) go in an earlier row write.
- **Item B** (antenna/src/metronome-core.ts, `fallbackReason`): the disjunct is now `s.lease !== (sent.blocked ? "blocked" : "play")`, still inside the existing `sent?.kind === "play" && s.applied !== "superseded"` guard. The doc comment is updated and the reason string is unchanged.
- Tests:
  - antenna/test/metronome-support.ts: `FakePort.failDeleteAlarm` (throws `injected deleteAlarm failure` before recording the op), modelled on `failSetAlarm`.
  - antenna/test/metronome-renew.test.ts: one new `it`, "an accepted hold or blocked lease is stored before any alarm op, so a failing alarm op cannot lose it". (1) Hold over a live play lease with an alarm pending, and deleteAlarm throws: renew rejects with /deleteAlarm/ and the stored lease is the hold (verdictAt T+1000). (2) A blocked lease at T is followed by a newer blocked lease at the same instant. Its body is identical, so there is no PUT and no reservation flush. An alarm is pending and deleteAlarm throws: renew rejects, puts stays at 1, and the stored lease is the newer blocked one (verdictAt T+1). How the engine surfaces the error is unchanged: renew rejects.
  - antenna/test/metronome-core.test.ts: the (b) loop test now feeds `b` the reply `lease: "blocked"` (`told`), and `p` the reply `lease: "play"`. The accepted-not-doing test gains b/none → (b) "...to a blocked play lease" and b/blocked → null. No new `it` for B.

## TDD evidence
RED, both items (new and edited tests, old source): `npx vitest run test/metronome-core.test.ts test/metronome-renew.test.ts`
```
× (b) an accepted play lease the DO is not doing (accepted already expired)
  TypeError: .toMatch() expects to receive a string, but got object      (b/none returned null)
× an accepted hold or blocked lease is stored before any alarm op, so a failing alarm op cannot lose it
  AssertionError: expected { kind: 'play', …(6) } to match object { kind: 'hold', …(1) }   (hold lost; play still stored)
Tests  2 failed | 54 passed (56)
```
RED, the blocked half alone. I used a scratch copy with the HEAD (old) engine and the hold half of the test removed, run from the copy's cwd. The fix comment is absent there (grep count 0), confirming the old engine ran:
```
× an accepted hold or blocked lease is stored before any alarm op, ...
AssertionError: expected { kind: 'play', …(6) } to match object { kind: 'play', blocked: true, …(1) }   (old verdictAt T still stored)
Tests  1 failed | 26 passed (27)
```
GREEN: same focused command, `Tests 56 passed (56)`.

## Full verification
- `cd antenna && npm test`: `Test Files 17 passed (17)`, `Tests 308 passed (308)` (expected 308)
- `cd antenna && npm run typecheck`: `tsc --noEmit`, exit 0

## Files changed
antenna/src/metronome-engine.ts, antenna/src/metronome-core.ts, antenna/test/metronome-core.test.ts, antenna/test/metronome-renew.test.ts, antenna/test/metronome-support.ts

## Self-review
The change is minimal (two source lines in the engine, one condition in core) and matches the brief. One test comment was moved to its own line to stay near the file's width. The existing ops-pinning tests (`["save stalls"]`, `["deleteAlarm","save stalls"]`, save-putTimes-before-put) pass unchanged.

## Concerns
- Only the row-count note above: an accepted renew now issues one extra `save` call. Per the brief, correctness wins over row count. The guard's "at least one row per renew" still holds.
- The alarm() half of item A belongs to Task 5, as the brief says. Not written here.
