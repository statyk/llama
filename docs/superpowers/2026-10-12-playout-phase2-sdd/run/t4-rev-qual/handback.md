VERDICT: NEEDS FIXES

### Findings

#### Critical
None.

#### Important
1. **The re-anchoring of the latch to a new period on a re-trip is unpinned. The code is right; a mutant survives the suite.** (`antenna/src/latch.ts:130-131`; `antenna/test/latch.test.ts:34-39`.)
   - The over branch of `applyAttempt` writes `tripped_period_start: periodStart`. So a station tripped in P1 that reads over again in P2 is re-anchored to P2. Its later under readings in P2 then stay tripped, as R3 requires.
   - No test checks this. The new-period test at test:36 asserts only `.tripped` after the P2-over reading, and never applies an under reading after it.
   - Mutant M1 (scratch copy) made the over branch keep `prev.tripped_period_start` when the station was already spend-tripped. All 19 latch tests stayed green.
   - Why it matters: under M1, a station tripped in P1 that is still over in P2 unblocks on the first P2 reading that comes in under. Once blocked, the projection falls, so that reading comes almost at once. Spend then resumes until the next 15-minute evaluation trips it again. That is the oscillation the latch exists to prevent, on the strict surface.
   - Fix: add one test. This probe failed under M1 and passed on HEAD:
     ```ts
     let d = applyAttempt(freshGuardDoc(T0), ok(T0, ...OVER));
     d = applyAttempt(d, ok(P2.startMs + H, 5, 15, 15, P2));
     expect(d.tripped_period_start).toBe(new Date(P2.startMs).toISOString());
     expect(applyAttempt(d, ok(P2.startMs + 2 * H, 5, 6, 15, P2)).tripped).toBe(true);
     ```

#### Minor
1. **A spend trip with `tripped_period_start: null` clears on the first under reading** (`latch.ts:136`: `null !== periodStart` counts as a new period). This is the implementer's concern 2, and I confirmed it against the plan's Task 6.
   - `guardStep` calls `corruptGuardDoc(nowMs, periodOrNull(...), ...)`, which records a null period when `BILLING_ANNIVERSARY_DAY` is invalid. The doc is then persisted.
   - Once the operator fixes the var, the first reading under the thresholds clears the trip with no raise and no new period. That breaks R2 ("clears only with a raise or a new period") in this double fault.
   - It is bounded: the clearing reading is under both thresholds, and the next over reading re-trips with a real period. Not a hole while over budget.
   - Fix: when `prev.tripped_period_start === null`, adopt the current period and stay tripped rather than clearing. For example, `newPeriod = prev.tripped_period_start !== null && prev.tripped_period_start !== periodStart`, and store `periodStart` in the stay-tripped branch when the previous value was null.
2. **Corrupt guard.json plus an invalid `MONTHLY_BUDGET_USD` gives a trip that no raise can clear.** Its `tripped_budget_usd` is null (`latch.ts:101`, `finiteOrNull`; `raised` requires non-null at `latch.ts:137`).
   - Task 6's `guard-state-corrupt` alert tells the operator to clear it with `transmitter budget --raise-to`. In this case that does nothing, and the station stays blocked until the next period or until someone deletes guard.json by hand.
   - It fails closed, and the brief's code behaved the same (NaN becomes null on disk). The deviation only makes the in-memory doc match the disk.
   - Fix options: let any honoured raise above the base clear a null `tripped_budget_usd`, or make Task 6's alert text say so. This is the orchestrator's call.
3. **Plan-mandated. A future `written_at` in budget.json forces an evaluation every minute while the skew lasts.** This is the implementer's concern 1.
   - Cause: `effectiveBudget` clamps `written_at` to `now` (`latch.ts:180`), so in `shouldEvaluate` the clamped value is always greater than the last `evaluated_at` (`latch.ts:157`).
   - That breaks the Global Constraints bound of "one GraphQL POST per 15 minutes". The calls are not billed, and NTP skew makes it about one extra call. A hand-typed future year, though, would make it one POST per minute until that date.
   - Fix: record the `written_at` of the raise last evaluated in the guard doc (e.g. `evaluation.budget_written_at`) and evaluate when the file's value differs, not when it is newer than the last attempt.
4. **A re-trip resetting `tripped_at` is unpinned** (`latch.ts:129`). Mutant M4 (always `tripped_at: at`) stayed green.
   - It is informational only (status/alerts), not a spend path.
   - Fix: one assertion after two consecutive over readings.
5. **The blind rule's handling of the clock is asymmetric** (`latch.ts:145-146`).
   - `shouldEvaluate` treats a negative age (a clock step back) as old and fails safe.
   - `applyBlindRule` does the opposite: a `last_success` or `since` in the future gives a negative age, which is "< blindAfterMs", so blind never trips until the clock passes that timestamp plus 6 h.
   - It is reachable only through a Worker clock fault or a hand-edited guard.json, which `parseGuardDoc` accepts (it does not bound timestamps).
   - Fix: clamp the baseline to `nowMs`, or reject future timestamps in `parseGuardDoc` (a rejected doc becomes a corrupt spend trip).
6. **The parser is laxer than the type.** `parseGuardDoc` accepts `null` for `evaluation.actual_usd/projected_usd/budget_usd` (`latch.ts:86-87`), but `StoredEvaluation` types them as `number`.
   - It also does not check `base_budget_usd`, `period_to_date`, `projected` or `unknown_action_types`, or that `tripped_at`/`last_success`/`evaluated_at`/`period.*` parse as dates.
   - Any consumer reading `prev.evaluation.*` as a number gets `null` (comparisons are silently false).
   - Fix: type those fields `number | null`, or note the gap where the parser is used.
7. **`parseGuardDoc` returns the raw object** (`latch.ts:91`), so unknown keys are carried and re-written forever. This is harmless, and noted only for transmitter's reader (Task 12).
8. **A malformed raise is ignored silently** (a string `budget_usd`, an unparseable `expires`, a lowering raise: `latch.ts:181-183`). Only the "outlives the period" case sets `invalid`. This fails closed and is what R13 defines, but an operator whose hand-written raise is malformed gets no signal.

### ⚠️ Cannot verify from diff
- R11 ("an invalid `MONTHLY_BUDGET_USD` fails every evaluation") depends on Task 6 routing `meterProblems` before `applyAttempt`. With a NaN base and a valid raise, `effectiveBudget` honours the raise, because `usd <= NaN` is false. The plan's `guardStep` does throw on `meterProblems` first, but that is Task 6 code, not yet built.
- transmitter's `budget --raise-to` (Task 12/13) must compute `expires` equal to the antenna period end exactly, or `effectiveBudget` reports `budget-file-invalid`. The two period computations must agree.
- Whether Task 6 reads `prev.evaluation.*` numerically (see Minor 6).

### Strengths
- The latch rules are small, pure and readable. The docstring states the set/clear rules exactly as R1/R3 put them, and the code follows them line for line.
- The fail-closed defaults are consistent:
  - an unparseable `last_success`/`since` trips blind;
  - an unparseable `evaluated_at` evaluates;
  - a NaN budget trips (via `overThreshold`) and can never be "raised past".
- The implementer's two hardenings are sound and well judged:
  - nested validation of `waf`/`period`/`evaluation`, since Task 6 reads `prev.waf.enabled`;
  - `finiteOrNull` to make memory match disk.
  - Their reasoning for not throwing on a NaN base is correct: a throw would become `guard-crashed`, then "unknown", and the R11 blind trip would never happen.
- The tests are concrete and cover each rule's boundaries (`six - 1` vs `six`, `m15 - 1` vs `m15`, expiry exactly at the period end). Mutant M2 (`>` to `>=` on the raise) went red in 3 tests.
- Hygiene: no account/zone IDs, tokens or addresses in either file, and no IO or fetch at all in the module.

### Checks run
- **Risk: a latch rule is unpinned (spend).** Scratch copy via `git archive HEAD antenna | tar -x`, with `node_modules` symlinked, run from the scratch dir. The baseline there was 19/19 green.
  - M1: the re-trip keeps the old period. Predicted to survive; it did, 19 passed. A scratch-only probe test failed under M1 (`expected '2026-10-11T00:00:00.000Z' to be '2026-11-11T00:00:00.000Z'`) and passed on the original, which proves the mutant was live. This is Important 1.
  - M4: the re-trip resets `tripped_at`. It survived, 19 passed. This is Minor 4.
  - M2: `e.budgetUsd > prev.tripped_budget_usd` changed to `>=`. Predicted red: "does not clear spend ... same budget" and "consumes the raise". Actual: those two plus the corrupt-doc test failed (3 failed, 16 passed). Pinned.
  - The scratch copy was deleted afterwards. The live worktree stayed clean (`git status --short` empty).
- **Risk: the implementer's concerns 1/2 are real in the integrated flow.** I read the plan's Task 6 `guardStep` (plan lines ~2215-2400). It confirms `corruptGuardDoc` is called with `periodOrNull(...)`, which can be null, and with `budget.budgetUsd`, which is NaN for an invalid base. It also confirms that `shouldEvaluate` gets the clamped `budget.writtenAtMs`. These are Minors 1-3.
- **Risk: NaN handling in `overThreshold`.** I read `pricing.ts:113-115`: it is the negated `<` form, so NaN trips. The latch relies on this, correctly.
- **Risk: public-repo hygiene.** A grep for 32-hex IDs and email addresses in both files found nothing.
