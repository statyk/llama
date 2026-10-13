# Task 4 handback (t4-impl): the latch

Status: DONE_WITH_CONCERNS (only minor concerns; nothing blocks)
Commit: 52cc6f0 feat(antenna): the tripped latch (spend/blind), state/guard.json schema, budget raises
Tests: `cd antenna && npm test && npx tsc --noEmit`: 88 passed in 8 files (was 69 in 7), tsc clean.

## What was implemented
- `antenna/src/latch.ts`: the brief's code verbatim (GUARD_KEY/BUDGET_KEY/OFFAIR_KEY, MAX_BUDGET_USD = 100,
  GuardDoc/StoredEvaluation, freshGuardDoc, parseGuardDoc, corruptGuardDoc, Attempt, applyAttempt, applyBlindRule,
  shouldEvaluate, EffectiveBudget, effectiveBudget, validBaseBudget), plus the two hardenings listed under Deviations.
- `antenna/test/latch.test.ts`: the brief's 15 tests verbatim, plus 4 more for the hardenings.

## TDD evidence
- RED (the brief's tests): `npx vitest run test/latch.test.ts` failed with "Cannot find module '../src/latch'".
- GREEN (the brief's code verbatim): 15 passed, `npx tsc --noEmit` clean.
- RED (the hardening tests): 3 failed and 16 passed. Failures: a NaN tripped_budget_usd where null was expected,
  and parseGuardDoc accepting `{ ...d, waf: {} }`. (The NaN raise test already passed on the brief's code.)
- GREEN after hardening: 19 passed, tsc clean. Full suite: 88 passed.

## Deviations
1. **A non-finite budget is recorded as `tripped_budget_usd: null`** (in applyAttempt's spend trip and in
   corruptGuardDoc). The helper is `finiteOrNull`.
   - The path: `guardConfigFromEnv` passes `Number(env.MONTHLY_BUDGET_USD)` straight to `effectiveBudget`, even when
     `validBaseBudget` rejects it. With no valid raise present, `budgetUsd` comes back NaN.
   - Task 6 passes that to `corruptGuardDoc` when guard.json is corrupt. The brief stored the NaN in memory, and it
     became `null` on disk.
   - The behaviour was already fail-closed: `overThreshold` trips on NaN, and `e.budgetUsd > NaN` is false, so no
     raise clears the trip. A new period still does, and the base deliberately stays a pass-through.
   - The change only makes the in-memory doc match what is written to disk, and pins that with tests: no NaN
     reaches a stored budget, and a raise cannot clear a trip whose budget was never valid.
   - I did not make effectiveBudget throw on a non-finite base. guardStep calls it outside any try, so a throw
     would become `guard-crashed`, which Task 8 treats as "unknown, write nothing". Then the blind trip
     (R11) would never happen.
   - effectiveBudget already rejects a non-finite or non-number raise (`Number.isFinite(usd)`). Pinned for
     NaN/±Infinity. validBaseBudget rejects non-finite values (the brief's test already covers NaN).
2. **parseGuardDoc validates the nested shapes too.**
   - `waf.enabled` must be boolean|null and `waf.error` string|null.
   - `period` must be null or `{start: string, end: string}`.
   - `evaluation` must be null or an object whose `actual_usd`, `projected_usd` and `budget_usd` are finite or
     null. null is allowed because NaN serializes as null.
   - The brief's version accepted `waf: {}` and any `period`/`evaluation`. Task 6 reads `prev.waf.enabled` to
     detect a hand toggle, and `e.budget_usd` etc. for the alert levels.
   - Anything rejected becomes a corrupt spend trip, which fails closed. The round-trip tests (tripped doc and
     fresh doc) show this code's own writes still parse.

## Self-review
- I checked each latch rule against R1/R3 and the tests: set spend, set blind, clear blind, clear spend (new
  period, or effective budget strictly above `tripped_budget_usd`), a failed reading is a no-op except
  `evaluated_at`/`last_error`, and blind never downgrades spend (applyBlindRule returns early when tripped). Each
  is pinned by a test.
- When an evaluation is still over after a raise, it moves `tripped_budget_usd` up to the new budget, so the raise
  is used up (R3). Pinned.
- When `last_success`/`since` won't parse, applyBlindRule trips blind (fail closed). When `evaluated_at` won't
  parse, shouldEvaluate evaluates.

## Concerns (not changed; for the orchestrator)
1. **A future `written_at` re-evaluates every minute for as long as the writer's clock is ahead.**
   - effectiveBudget clamps `written_at` to `now`, so each minute `writtenAtMs = now > evaluated_at` (the previous
     minute), and shouldEvaluate returns true each time.
   - Cost: one GraphQL POST per minute instead of one per 15 min (the constraint's bound). It stops once the real
     clock passes `written_at`. This is not billed spend.
   - With NTP on hugo and the Mac the skew is seconds, so the cost is at most one extra evaluation.
   - A fix would be to require `budgetWrittenAtMs < nowMs` in shouldEvaluate. Task 6's raise test (written_at
     T0+M, evaluated at T0+2M) would still pass. But a skewed raise would then wait for the 15-min cadence instead
     of being evaluated at once (R1). That is a plan decision, so I left the brief's behaviour.
2. **A spend trip with `tripped_period_start: null` clears on the first reading under the thresholds**, because
   `null !== periodStart` counts as a new period.
   - This only happens when corruptGuardDoc ran without a billing period (invalid BILLING_ANNIVERSARY_DAY, under
     which every evaluation fails), or when someone edits guard.json by hand.
   - The clear needs a successful reading under both thresholds, so it never unblocks while over budget. It is
     strictly weaker than "only a raise or a new period" for that double fault.
3. One commit instead of two: the plan's code and the hardening landed together in 52cc6f0, and the suite was
   green at each step.

## Files
- /Users/shawn/projects/llama/.claude/worktrees/playout-phase2/antenna/src/latch.ts
- /Users/shawn/projects/llama/.claude/worktrees/playout-phase2/antenna/test/latch.test.ts

---

# Fix round 1

Status: DONE. Commit: c04c5ab fix(antenna): latch review fixes — re-trip anchoring pinned, null period/budget, cadence, future baseline
Tests: `cd antenna && npm test && npx tsc --noEmit` → 8 files, 94 passed (was 88), tsc clean. Latch file: 25 tests.

## Changes, by ruling (all in antenna/src/latch.ts plus tests in antenna/test/latch.test.ts)
1. **Re-anchoring a re-trip to the new period.** Tests only; the code was already correct. New test "re-anchors a
   spend trip to the new period when that period reads over too, so its under readings stay tripped". It is the
   reviewer's probe: P1 over, then P2 over, gives `tripped_period_start` = P2's start, and a later under reading in
   P2 stays tripped.
2. **A spend trip whose period is null adopts the current period.**
   - `newPeriod = prev.tripped_period_start !== null && prev.tripped_period_start !== periodStart`.
   - The stay-tripped branch stores `prev.tripped_period_start ?? periodStart`.
   - Test "a spend trip with no recorded period adopts the current one and stays tripped" (built from
     `corruptGuardDoc(T0, null, 15)`):
     - an under reading in P1 stays tripped and records P1;
     - a second under reading in P1 still stays tripped;
     - an under reading in P2 clears.
3. **A spend trip whose budget is null counts as raised** when `e.budgetUsd` and `a.baseBudgetUsd` are both finite
   and `e.budgetUsd > a.baseBudgetUsd`. A non-null tripped budget is handled as before.
   - Test "a spend trip with no recorded budget clears only with an honoured raise above the base" (built from
     `corruptGuardDoc(T0, P1, NaN)`):
     - budget 15 = base → stays tripped;
     - 20 and under → clears;
     - 20 and over → stays tripped with `tripped_budget_usd: 20` (the raise is used up);
     - a NaN base → stays tripped.
   - Two round-0 tests asserted "no raise can clear" a null budget. Ruling 3 reverses that, so I rewrote them. They
     now assert an unraised under reading stays tripped, and the NaN-trip test also asserts that a raise to 50
     clears.
   - The `finiteOrNull` comment is updated to match.
4. **shouldEvaluate's raise trigger now also requires `budgetWrittenAtMs < nowMs`.** The docstring explains why.
   - Test "a written_at clamped to now never forces an evaluation inside the interval; a past raise still does":
     - for 14 consecutive minutes, a written_at of 2027 is clamped by effectiveBudget to now, and no evaluation
       triggers;
     - a raise written at T0+59.999 s, with the last attempt at T0 and now at T0+60 s, still triggers.
   - The brief's existing raise test (+30 s) still passes.
5. **`BLIND_FUTURE_TOLERANCE_MS = 15 * 60_000` (exported).**
   - applyBlindRule keeps the doc only if the baseline parses, is at most the tolerance ahead of nowMs, and is less
     than blindAfterMs old. Otherwise it trips blind.
   - Test "trips blind when the blindness baseline is more than the tolerance ahead of the clock, not a few seconds":
     - `last_success` 5 s ahead → no trip;
     - exactly the tolerance ahead → no trip;
     - tolerance + 1 ms ahead → blind;
     - a `since` (no success) beyond the tolerance → blind.
6. **tripped_at on a re-trip.** The brief's code keeps the ORIGINAL `tripped_at` when the station is already
   spend-tripped (`prev.tripped && prev.reason === "spend" ? prev.tripped_at : at`). I pinned that: test "keeps the
   first tripped_at across consecutive over readings".
7. **StoredEvaluation's `actual_usd`, `projected_usd` and `budget_usd` are now `number | null`,** with a comment.
   There was no type fallout: tsc is clean, and nothing in src reads them yet.

## TDD evidence
- RED: `npx vitest run test/latch.test.ts` → 4 failed, 21 passed. The failures were the tests for items 2, 3, 4 and
  5. The tests for items 1 and 6 passed on HEAD, as expected, because that code was already right but unpinned.
- After implementing: 2 failed (the two superseded round-0 assertions, see item 3). After rewriting them:
  25 passed, tsc clean.
- Full suite: `npm test` gave 94 passed in 8 files; `npx tsc --noEmit` clean.

## Mutation proof (scratch copy only)
- Setup: `git archive HEAD antenna | tar -x` into the scratchpad, overlaid with the uncommitted latch.ts and
  latch.test.ts, `node_modules` symlinked. vitest ran from the scratch antenna dir via a script that applies one
  mutant at a time.
- Each prediction was fixed in the script before its run. A verdict counts only if the red set equals the
  prediction exactly.
- After restoring the original, the baseline was 25 passed. The scratch copy was then deleted, and the live
  worktree was untouched.

| Mutant | Predicted red | Actual red | Verdict |
|---|---|---|---|
| M1: over branch keeps `prev.tripped_period_start` when already spend-tripped | re-anchors… | re-anchors… (1 failed) | CAUGHT as predicted |
| M2a: `newPeriod = prev.tripped_period_start !== periodStart` (null counts as new) | no recorded period adopts… | same (1 failed) | CAUGHT as predicted |
| M2b: stay-tripped branch drops `?? periodStart` | no recorded period adopts… | same (1 failed) | CAUGHT as predicted |
| M3: null-budget raise branch → `false` | NaN budget trips spend…; no recorded budget clears only… | both (2 failed) | CAUGHT as predicted |
| M4: drop `&& budgetWrittenAtMs < nowMs` | written_at clamped to now… | same (1 failed) | CAUGHT as predicted |
| M5a: drop the future-tolerance clause | trips blind when the baseline… | same (1 failed) | CAUGHT as predicted |
| M5b: tolerance `<=` → `<` (boundary) | trips blind when the baseline… | same (1 failed) | CAUGHT as predicted |
| M6: over branch always `tripped_at: at` | keeps the first tripped_at… | same (1 failed) | CAUGHT as predicted |

The full output is in t4-impl.log.

## Remaining notes
- With item 4, a raise whose writer's clock runs ahead is no longer evaluated at once. It waits for the 15-minute
  cadence, which ruling 4 accepts.
- Item 5's `since` is written by the Worker's own clock. So this only fires on a hand edit or a Worker clock fault,
  not on hugo's skew.
