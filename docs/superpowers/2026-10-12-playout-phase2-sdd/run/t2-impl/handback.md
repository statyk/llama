# t2-impl handback: Task 2 (price table, spend evaluation, thresholds)

Status: DONE
Commit: 2d9c7f2 feat(antenna): guard price table and per-meter spend projection through the allowances

## Implemented
- antenna/src/pricing.ts: verbatim from the brief. Meter/METERS, PriceTable, PRICES ($5 base; Workers 10M then $0.30/M;
  R2 Class A 1M then $4.50/M; Class B 10M then $0.36/M; storage 10 GB-month then $0.015), Usage, priceUsage,
  OpCounts, Reading, Evaluation, evaluateSpend (per-meter projection from the recent rate x time left, priced through
  the allowances; storage = peak held over elapsed / whole period, /30-day month, decimal GB),
  TRIP_ACTUAL=0.9, TRIP_PROJECTED=1.0, ALERT_LEVELS=[0.5,0.8], overThreshold.
- antenna/test/pricing.test.ts: verbatim from the brief (7 tests).

## Files changed
- antenna/src/pricing.ts (new)
- antenna/test/pricing.test.ts (new)

## Deviations
None.

## TDD evidence
RED: `cd antenna && npx vitest run test/pricing.test.ts`
  FAIL test/pricing.test.ts -- Error: Cannot find module '../src/pricing' imported from .../antenna/test/pricing.test.ts
  Test Files 1 failed (1); Tests no tests
GREEN: `cd antenna && npx vitest run test/pricing.test.ts && npx tsc --noEmit`
  Test Files 1 passed (1); Tests 7 passed (7); tsc clean
Full suite: `cd antenna && npm test` -> Tests 58 passed (58) (51 prior + 7 new); `npx tsc --noEmit` clean.

## Self-review
- Hand-checked the test arithmetic: period Oct 11 -> Nov 11 is 31 days, so 21 d = 504 h left at day 10;
  10k/h * 504 h + 500k = 5.54M Class A; storage 60 GB * 15/30 = 30 and * 31/30 = 62. 0.9 * 15 rounds to exactly
  13.5 in float64, so the boundary case trips as specified (test passes).
- At/after period end remainingMs = 0, so projection = period-to-date; elapsed is clamped to the period length.
- Before period start (clock skew), elapsed clamps to 0 and remaining exceeds the period length (projection is
  then larger, i.e. conservative). Fine for a spend guard.
- recentMs <= 0 gives rate 0 (no division by zero).

## Concerns (minor, for the reviewer)
- NaN fail-open at this layer: a NaN anywhere in a Reading or budget propagates (Math.max(0, NaN) is NaN) and
  `overThreshold` then returns false (NaN >= x is false). This module does not guard it; it relies on upstream
  validation. Task 3's brief rejects non-finite / negative analytics counts (`Number.isFinite(v) && v >= 0`) and
  Task 4 validates the budget, so the path is covered by design -- but if any future caller builds a Reading
  without that validation, the guard would silently not trip. A cheap hardening (treat a non-finite
  actual/projected/budget as over-threshold) was NOT added, to keep the plan's code verbatim; flagging it for
  the orchestrator's call.
- Negative counts are clamped by Math.max in priceUsage (cannot reduce a total below base), also validated upstream.

---

# Fix round 1 (quality review: Important 1, Minor 1, Minor 2)

Status: DONE
Commit: f2ca117 fix(antenna): guard trips on NaN; pin every op meter's projection and the remaining-time clamp

## Changes
1. **New test "projects every op meter from its own recent rate"** (Important 1).
   - Inputs: `recent` = Workers 1.2M, Class A 30k and Class B 600k per 3 h, i.e. distinct rates of 400k, 10k and 200k per hour. 504 h are left.
   - It asserts `projected.workersRequests` = 201.7M, `projected.r2ClassA` = 5.54M and `projected.r2ClassB` = 100.8M.
   - All three meters are past their allowances, so `projectedUsd` (5 + 191.7×0.3 + 4.54×4.5 + 90.8×0.36) depends on each one.
   - The existing Class A test is unchanged.
2. **`overThreshold` is written negated** (Minor 1, orchestrator-authorized deviation from the brief):
   `return !(e.actualUsd < TRIP_ACTUAL * e.budgetUsd && e.projectedUsd < TRIP_PROJECTED * e.budgetUsd);`
   - A comment explains why it is negated: NaN comparisons are false, so the plain `>=` form fails open.
   - New test "fails closed: any NaN trips" covers a NaN budget, a NaN projected and a NaN actual. All three trip.
3. **New test "never projects below period-to-date once the period is over"** (Minor 2).
   - Inputs: `nowMs = PERIOD.endMs + DAY`, period-to-date of 11M Workers and 2M Class A, and non-zero recent rates.
   - It asserts the projections equal period-to-date exactly, `projectedUsd` ≈ `actualUsd`, and the total is 9.8 (5 + 0.3 + 4.5).

## Mutants
- **Setup:** a scratch copy from `git archive HEAD antenna`, overlaid with the two working-tree files and checked with cmp. node_modules is symlinked, and vitest runs from the scratch dir. Each mutation was applied by an exact-one-occurrence replace and diffed.
- **Prediction method:** for each mutant I named the test expected to go red before running it.

| Mutant | Predicted red | Result |
|---|---|---|
| BASELINE (no change) | none | 10 passed |
| SENTINEL `baseUsd: 6` | the price-dependent tests | 7 failed / 3 passed (only the overThreshold tests survived, as expected): scratch is the code under test |
| M-B drop Class B projection term | "projects every op meter from its own recent rate" | exactly that 1 failed, 9 passed |
| M-W Workers uses `rate("r2ClassA")` | "projects every op meter from its own recent rate" | exactly that 1 failed, 9 passed |
| M-C remove the `remainingMs` `Math.max(0, …)` clamp | "never projects below period-to-date once the period is over" | exactly that 1 failed, 9 passed |
| M-T revert overThreshold to the `>=`/`\|\|` form | "fails closed: any NaN trips" | exactly that 1 failed, 9 passed |

Full output, with each mutant's diff, is in t2-impl.log.

## Commands and output
- `cd antenna && npx vitest run test/pricing.test.ts`: 10 passed (10).
- `cd antenna && npm test`: Test Files 6 passed (6), Tests 61 passed (61).
- `npx tsc --noEmit`: clean.

## Not addressed (out of scope for this round, per the coordinator's list)
- **Minor 3** (analytics lag): negligible, as the review notes.
- **Minor 4:** `METERS` and `PRICES` are still mutable.
- **Minor 5:** `ALERT_LEVELS` is still untested here. Task 6 consumes it.
