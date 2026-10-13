VERDICT: NEEDS FIXES

Scope: Task 2, base f13191c, head 2d9c7f2 (`antenna/src/pricing.ts`, `antenna/test/pricing.test.ts`). Both files are byte-identical to the brief's code blocks, which I checked by diffing them against the brief's extracted fences. So every finding below is plan-mandated. The arithmetic is correct and the trip predicate's boundaries are pinned. The one real gap is in the tests: two of the three per-meter projections can be deleted and the suite stays green.

### Findings
#### Critical
None.

#### Important
1. **Plan-mandated. The Class B and Workers projections are untested, so deleting either one leaves the suite green.** Locations: `antenna/test/pricing.test.ts`, the test "projects each meter from the recent rate through the allowances, not a dollar average" (about lines 30-41), and `antenna/src/pricing.ts:94-96`.
   - The test's name says "each meter", but its `recent` only has Class A traffic (`workersRequests: 0, r2ClassB: 0`). It asserts only `projected.r2ClassA` and `projectedUsd`.
   - Mutants, run in a scratch copy:
     - M4 replaced `r2ClassB: periodToDate.r2ClassB + rate("r2ClassB") * remainingMs` with `r2ClassB: periodToDate.r2ClassB`, so Class B is never projected. Result: 7/7 green.
     - M1 made the Workers projection use `rate("r2ClassA")`. Result: 7/7 green.
   - Why it matters:
     - Both mutants fail open. A regression to either meter's projection quietly removes the `projected >= 100%` trip for that meter, and the guard would then trip only at 90% of actual.
     - Class B is the meter most driven by the listener path (R2 reads on cache misses). A projection under-estimate is the exact silent over-budget mode the stakes paragraph forbids.
     - No later task pins it either. I grepped the Task 3/6/8 briefs for `projected`/`r2ClassB`; Task 6's fixture uses "3M Class A ... none recently".
   - Fix: give `recent` distinct non-zero rates for all three op meters, e.g. Workers 1.2M/3 h and Class B 600k/3 h. Then assert `projected.workersRequests` and `projected.r2ClassB` with `toBeCloseTo`, and push at least one of them past its allowance so `projectedUsd` depends on it. That catches both a dropped term and a swapped rate key.

#### Minor
1. **NaN makes `overThreshold` fail open.** Location: `pricing.ts:110-112`.
   - `NaN >= x` is false, so a NaN `actualUsd`, `projectedUsd` or `budgetUsd` never trips. NaN also flows through `Math.max(0, NaN)` in `priceUsage`.
   - Not reachable under the plan, because inputs are validated upstream (see ⚠️), which is why this is Minor. The implementer flagged it too.
   - Suggested defence in depth on the strict surface: write the predicate in its negated form so any non-finite value trips:
     `return !(e.actualUsd < TRIP_ACTUAL * e.budgetUsd && e.projectedUsd < TRIP_PROJECTED * e.budgetUsd);`
   - Optionally add a test asserting that a NaN budget trips. This is one line and changes no tested behaviour.
2. **The `remainingMs` clamp is unpinned.** Location: `pricing.ts:84`.
   - Mutant M2 removed `Math.max(0, …)` and the tests stayed green. "has nothing left to project at the period's end" uses `nowMs == endMs`, where the difference is already 0.
   - Without the clamp, `nowMs > endMs` would make the projection fall below period-to-date, which fails open.
   - It is unreachable today, because `billingPeriod(nowMs)` always gives `nowMs < endMs`. Fix: use `PERIOD.endMs + DAY` in that test, or add a second case with that value.
3. **Analytics lag is in neither term.** Location: `pricing.ts:83-97`.
   - `recent` and `periodToDate` end "a few minutes ago" (the `Reading` comment), but the projection multiplies by `endMs - nowMs`. Usage inside the lag window is therefore counted nowhere.
   - The error is a few minutes out of about 31 days (~0.01%), so it is negligible. Noting it so nobody later assumes the projection is a strict upper bound for op counts.
   - Storage is a strict upper bound: the peak is held, buckets' maxima are summed, decimal GB is used, and the 31/30 factor applies.
4. **Exported tables are mutable.** Location: `pricing.ts:10, 17-25`. `METERS` is `Meter[]` and `PRICES` is a plain mutable object, while `ALERT_LEVELS` is `as const`. Any importer could alter the price table at runtime. Make them `readonly`/`as const`, or `Object.freeze` them. This is a consistency and hardening point, not a bug.
5. **`ALERT_LEVELS` has no test in this task.** That is acceptable since Task 6 consumes it, but the brief lists it among this task's outputs.

### ⚠️ Cannot verify from diff
- **NaN and negative input validation is upstream.** Task 3's `count()` rejects non-finite or negative analytics values and `RECENT_MS` is a constant. Task 6 checks `MONTHLY_BUDGET_USD` with `validBaseBudget` (finite, above 5, at most 100) and puts it in `meterProblems`. Task 4's `effectiveBudget` needs `Number.isFinite(usd)`. I read these in the briefs, not in code; confirm them when those tasks land.
- **R10, unknown R2 action types priced as Class A,** happens in Task 3's `r2Counts`. This module only passes `unknownActionTypes` through.
- **Whether the prices match Cloudflare's current published rates** (Workers Paid $0.30/M over 10M; R2 Class A $4.50/M over 1M, Class B $0.36/M over 10M, storage $0.015/GB-month over 10). The values match the brief and spec, but I did not check them against Cloudflare.

### Strengths
- The projection is done per meter and priced through the allowances, never as a linear dollar average. The Class A test genuinely tells the two apart (a dollar average would give $15.50 against the expected ~$25.43).
- The trip boundaries are pinned tightly:
  - 13.49 does not trip and 13.5 does, which pins `>=` and TRIP_ACTUAL to (~0.8993, 0.9]. Mutant M3 (`>`) went red as predicted.
  - 14.99 does not trip and 15 does, which pins TRIP_PROJECTED.
  - 0.9 × 15 is exactly 13.5 in float64, so the boundary test is not flaky.
- Storage is handled conservatively: decimal GB, the peak held over the whole period, and a 30-day month divisor, so a 31-day period gives a 31/30 upper bound. The comment documents the choice.
- Edge handling is sensible: `recentMs <= 0` gives a rate of 0 (no division by zero), elapsed is clamped at both ends, and a budget of 0 or less always trips (fail closed).
- Hygiene: no secrets or account details, no network use, a single responsibility, clean exported interfaces, and a correct type-only import of `Period`.

### Checks run
- **Is the code verbatim from the brief?** I extracted both fenced blocks from `task-2-brief.md` and diffed them against `git show 2d9c7f2:<file>`. Both are identical.
- **Can NaN or bad input reach `overThreshold`?** I grepped the Task 3/4/6 briefs for `isFinite`, `validBaseBudget` and the `evaluateSpend` call site. Inputs are validated upstream, so the finding stays Minor.
- **Do the tests pin the per-meter projection, the clamp and the predicate?** I ran mutants on a `git archive 2d9c7f2 antenna` scratch copy, with node_modules symlinked, running `npx vitest run test/pricing.test.ts` from the scratch dir. Output is in the log.
  - Baseline: 7 passed.
  - Sentinel (`baseUsd: 6`): 5 failed. This proves the scratch copy is the code under test.
  - M1 (Workers projection uses the Class A rate): predicted to survive. It survived, 7 passed.
  - M2 (`remainingMs` clamp removed): predicted to survive. It survived, 7 passed.
  - M3 (`actualUsd >` instead of `>=`): predicted red on "trips at actual >= 90%...". It went red: 1 failed, 6 passed.
  - M4 (Class B never projected): predicted to survive. It survived, 7 passed.
  - I confirmed by diff that each mutation applied to exactly the intended line.
- **Do later tasks pin the Class B or Workers projection?** I grepped the Task 3/6/8 briefs for `projected`/`r2ClassB`. None do.
