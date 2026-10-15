### Spec Compliance
- ✅ Spec compliant. All 14 `src/clock.ts` edits, the `src/index.ts` switch, the `CLOCK_KEYS` line and the alerts test line match the brief word for word (diff lines 46-370). The new test file is the brief's file with one adaptation, and that adaptation is valid (see below). 22 new tests (6 + 6 + 7 + 3), which gives the expected 349 + 22 = 371.
- Lease table, path by path (clock.ts, checked against the diff plus src/clock.ts:382-400 for the loop tail):
  - guard unknown or crashed: `renew(null)` then return (diff 222). A crash becomes `blocked: null` first, so it takes the same branch.
  - known verdict, `readInputs` threw: `renew(unusable())` then throw (diff 250).
  - horizon missing or unreadable: `renew(unusable())` (diff 258).
  - `gridOf` threw (bad epoch): `renew(unusable())` (diff 274).
  - In all three, `unusable()` gives a hold when blocked and null when unblocked (diff 238), as the table's rows 2 and 3 require.
  - horizon refused: `renew(hold)` whatever the verdict (diff 267).
  - accepted: `renew(playLease(startedMs, now, blocked, horizon, inputs.fallback))` (diff 300).
  - Every path renews exactly once. After the play renew, a throw from the loop goes to the catch, which never renews. `reconcileIndex` failures are caught and fall through. Between the guard and the play renew, the code that is not covered by a renew'd catch (`startMs` arithmetic, `offairWithoutFallback`) is pure and does not throw.
- The fallback loop runs only on the last row, and only when `renew` returns non-null (diff 300-303). Every earlier row returns or throws before `cap`/`write` exist, so cron can never write without a known verdict and an accepted horizon. Spend-strict: OK.
- Triggers (a), (b) and (c) come from `fallbackReason` (metronome-core.ts:300-313). That includes carry-t7's lease-mismatch arm of (b) and the negated stalls check of (c).
- `metronome-down` is raised inside `renew`, so it is raised on every trigger, including guard-unknown with a renew that throws and an unanswered hold (plan reading 6). Tests: clock-metronome.test.ts:75-84 and :234-241.
- `complete`:
  - It is set only on a healthy play renew (diff 301) or at the end of a finished loop (clock.ts:391). Every early return leaves it false, which matches the spec's `runClock` contract.
  - `metronome-down` is in `CLOCK_KEYS`, so on guard-unknown it never resolves on the incomplete batch.
- `offairWithoutFallback` is computed from cron's own inputs before the lease (diff 297), with the once-per-invocation guard kept (plan reading 11).
- Rollback switch: `env.METRONOME === "on" ? metronomeClient(env.METRONOME_DO) : undefined` (diff 369). When it is off, `renew` returns null without making any call, and the `deps.metronome &&` test skips the lease branch. The loop is then unchanged, and the pre-existing clock tests are untouched by this diff.
- Clock line: `...result` already spreads into the clock line (index.ts:38-39), so it carries `metronome`, with `MetronomeLine` exactly in the shape the brief gives. A `ClockError`'s `partial` is the same `result` object, so a failed run also logs its `metronome`.
- Plan reading 12 / Review Focus 4: the stub is built inside `metronomeClient.renew` (metronome.ts:72-90), so a missing binding rejects into trigger (a) after the guard has run.
- The test adaptation (clock-metronome.test.ts:180-191) is valid and minimal:
  - In the brief's version, the default fake answers `lease: "play"` to a blocked play lease. Under carry-t7's revised (b), that is a trigger, so the "no cron PUT" expectation fails.
  - Changing the fake's answer to what a healthy DO actually returns (`lease: "blocked"`) keeps the test's stated intent ("even though the DO writes"). The other option, flipping the expectation to 1 PUT, would test a different scenario.
  - The one assertion added (`not.toContain("metronome-down")`) makes the fixture prove it is healthy. It is acceptable.
- ⚠️ Cannot verify from diff: the implementer's runs (371 passing twice, the typecheck, the dry run listing `env.METRONOME_DO`). I did not re-run them, per the seat rules, because nothing I read raised a specific doubt.
- ⚠️ Report-only check 4 (the Task 5 corner): the wiring adds exactly one renew per invocation, and a healthy run returns right after it. Three renews inside one 10.24 s segment would need three cron fires within 10.24 s, which this wiring cannot produce on its own. I agree with the implementer's assessment.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **The implementer's concern: a non-object DO reply makes `renew` throw** (clock.ts diff 188-192 with metronome-core.ts:303-304).
   - My ruling: a spec gap, not a Task 7 miss.
   - The spec's "Fallback (new)" names three triggers: (a) `renew` throws or times out, (b) a play answer that is not accepted/wrote/lease-matched, and (c) stalls. It is silent on a reply that resolves to something that is not an object.
   - Reading 6 is about raising `metronome-down` on every *trigger*. Reading 12 is about a missing binding rejecting *inside* the client rather than before `runClock`. Neither covers a resolved `undefined` or `null`.
   - The failure is fail-closed on spend: nothing is written, and the urgent `clock-failed` alert is raised, so it is not silent. Continuity is lost for that minute, and `metronome-down` is not raised.
   - Reaching it in practice requires the DO's `renew` to resolve to a non-object. The DO class ships in the same bundle as the cron code, and any object reply (even `{}`) trips (b) or (c).
   - The doc comment's "Never throws" (diff 181) is brief-mandated text that is false in this one case.
   - Recommendation, for the final branch review or the quality seat, not a blocker: in `renew`, treat a non-object `status` as `{ error: "renew returned a non-object" }`, which is trigger (a). That makes the doc comment true and keeps the fallback available. The alternative is to validate the reply in `metronomeClient` (Task 6's file).
2. **Two brief tests now take the fallback path without saying so.** In clock-metronome.test.ts:130-139 (the `blocked: true` pass) and :141-154 (the `guardSays(true, true)` case), the default fake answers `lease: "play"` to a blocked play lease. Under the revised (b) that is now a trigger, so these tests run cron's fallback loop. Their assertions (`m.sent` content and length) still hold and are still meaningful. The loop on the blocked path still renews exactly once, which is a bonus. A reader may assume a healthy DO, though. No change is required under the carry rule, since no expectation was altered.

### Verdict
**Spec compliance:** Pass
