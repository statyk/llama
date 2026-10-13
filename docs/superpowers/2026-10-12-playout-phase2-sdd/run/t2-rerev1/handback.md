VERDICT: ALL ADDRESSED

Scope: Task 2, fix round 1. Fix base 2d9c7f2, head f2ca117. Files: `antenna/src/pricing.ts` and `antenna/test/pricing.test.ts`. The worktree is clean at f2ca117.

### Finding verdicts
1. **IMPORTANT, Class B and Workers projections untested: ADDRESSED.** Test at `antenna/test/pricing.test.ts:44-58`.
   - The new test gives each op meter its own non-zero rate: Workers 400k/h, Class A 10k/h, Class B 200k/h. Then:
     - it asserts `projected.workersRequests` = 201.7M, `projected.r2ClassA` = 5.54M and `projected.r2ClassB` = 100.8M;
     - all three meters are past their allowances, so `projectedUsd` depends on each projection.
   - I recomputed the arithmetic in node: 201,700,000 / 5,540,000 / 100,800,000 and $115.628. These match the expected literal.
   - The implementer's mutants were M-B (Class B term dropped) and M-W (Workers uses the Class A rate). Both were predicted red and went red on exactly this test.
   - I ran two further mutants of my own in a scratch copy, each predicted red on this test, and both went red (1 failed, 9 passed):
     - Class B uses the Workers rate key;
     - the Workers projection term is dropped.
   - So the test catches both a dropped term and a swapped rate key, in both directions.
2. **(ruling) overThreshold fails closed on NaN: ADDRESSED.** Code at `antenna/src/pricing.ts:110-115`, test at `antenna/test/pricing.test.ts:95-99`.
   - The predicate is now the negated form `!(actual < 0.9*budget && projected < budget)`, with a comment saying why.
   - The test sets NaN in each of the three operands separately, and each case trips.
   - My partial-reversion mutant reverted only the actual half to `>=` and kept the projected half negated. It went red on "fails closed: any NaN trips", as predicted. So each NaN case pins its own operand rather than the three cases hiding behind one another.
   - The existing boundary test still passes (13.49/14.99 does not trip; 13.5 and 15 do), so behaviour on finite values is unchanged.
   - Residual on "non-finite": see Minor 1 below. It is a property of the ruled form, not of the implementation.
3. **(ruling) remainingMs clamp pinned: ADDRESSED.** Clamp at `antenna/src/pricing.ts:84`, test at `antenna/test/pricing.test.ts:60-71`.
   - The new test uses `nowMs = PERIOD.endMs + DAY` with non-zero recent rates for Workers and Class A.
   - Without the clamp, Workers would project to 11M − 24M = −13M, so the exact `toBe(11_000_000)` fails.
   - The implementer's M-C mutant (clamp removed) went red on exactly this test.
   - The expected total of 9.8 (5 + 0.3 + 4.5) is correct, and `elapsedMs`'s own `min(nowMs, endMs)` keeps actual well defined.

### New breakage in the fix diff
None. One Minor observation:
- **Minor 1: the negated form is fail-closed for NaN but not for every non-finite value.** I checked in node:
  - `budgetUsd = +Infinity` does not trip;
  - `actualUsd` or `projectedUsd` = `-Infinity` does not trip;
  - `+Infinity` actual or projected, and `-Infinity` budget, do trip.
  
  The ruling says "NaN/non-finite" but names the negated form as the mechanism. None of these values is reachable under the plan: the budget is validated as finite and at most 100 upstream (Task 4/6), and op counts as finite and non-negative (Task 3), so a negative-infinite cost cannot arise. Full non-finite coverage would need an explicit `Number.isFinite` check on all three operands, which the orchestrator can choose to request. This does not block.

### Out-of-scope observations
- The implementer explicitly deferred three items from the original review: Minor 3 (analytics lag, negligible), Minor 4 (`METERS`/`PRICES` are mutable) and Minor 5 (`ALERT_LEVELS` is untested here; Task 6 consumes it). None of them was in this round's list.

### Checks run
- I read the fix report, the fix diff and the original quality verdict. HEAD is f2ca117, the tree is clean, and `git diff 2d9c7f2 f2ca117 --stat` matches the package (2 files, +39/−2).
- I recomputed the new test's expected values in node, and checked the negated predicate on ±Infinity in each operand. Output is in t2-rerev1.log.
- Mutants ran in a scratch copy (`git archive HEAD antenna | tar -x` into the scratchpad, node_modules symlinked, vitest run from the scratch dir). I named the expected red test before each run and confirmed by `diff` that each edit hit exactly one line:
  - Baseline: 10 passed.
  - Class B uses the `workersRequests` rate: red on "projects every op meter from its own recent rate" (1 failed, 9 passed).
  - Workers projection term dropped: red on the same test (1 failed, 9 passed).
  - overThreshold's actual half reverted to `>=`: red on "fails closed: any NaN trips" (1 failed, 9 passed).
  - These targeted reds also show that the scratch copy is the code under test.
- I did not re-run the full suite, per the instructions. The implementer reports `npm test` at 61 passed and `tsc --noEmit` clean.
