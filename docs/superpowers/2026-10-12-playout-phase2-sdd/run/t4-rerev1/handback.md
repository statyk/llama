VERDICT: ALL ADDRESSED

Scoped re-review of Task 4 (the latch), fix round 1, by t4-rerev1 (Opus). Fix base 52cc6f0, head c04c5ab. Files: antenna/src/latch.ts, antenna/test/latch.test.ts.

### Finding verdicts
1. IMPORTANT, re-trip re-anchoring: **ADDRESSED.** latch.ts:138 writes `tripped_period_start: periodStart` on the over branch. The new test at latch.test.ts:182 runs P1 over, then P2 over, checks the anchor is P2, and checks that a later under reading in P2 stays tripped. Mutant M1 ("over branch keeps prev.tripped_period_start when already spend-tripped") failed exactly that one test, as I predicted. I re-ran it myself.
2. (ruling) null tripped_period_start: **ADDRESSED.** latch.ts:144 (`!== null &&`) and :150 (`?? periodStart`). In the test at latch.test.ts:195:
   - an under reading adopts P1 and stays tripped;
   - a second under reading in P1 stays tripped;
   - an under reading in P2 clears.
   Two mutants each failed exactly that test: M2 (null counts as a new period) and M7 (drop `?? periodStart`).
3. (ruling) null tripped_budget_usd: **ADDRESSED.** latch.ts:146-148. With a null budget, the trip counts as raised only when the budget and the base are both finite and the budget is strictly above the base. Otherwise it stays tripped. The test at latch.test.ts:203 covers these cases:
   - a budget equal to the base stays tripped;
   - 20 and under clears;
   - 20 and over re-trips, with `tripped_budget_usd: 20` (the raise is used up);
   - a NaN base stays tripped.
   Two round-0 assertions that said "no raise can clear" were rewritten to match the ruling, and still assert that an unraised reading stays tripped. M3 (the null-budget branch made `false`) failed the 2 tests I predicted. M3c (`>` changed to `>=`) failed those 2 plus "a corrupt document under a non-finite budget …" (latch.test.ts, its UNDER reading is at budget 15 = base). I had left that third test out of my prediction, so M3c is caught but not "as predicted". The extra red test also pins the strict `>`.
4. (ruling) shouldEvaluate future written_at: **ADDRESSED.** latch.ts:177 adds `&& budgetWrittenAtMs < nowMs`. The test at latch.test.ts:213 feeds a 2027 written_at through effectiveBudget's clamp for 14 consecutive minutes and gets no evaluation. It also checks that a past raise newer than the last attempt still triggers at once. The brief's +30 s raise test still stands. M4b (`<` changed to `<=`) failed exactly that test.
5. (ruling) applyBlindRule future baseline: **ADDRESSED.** BLIND_FUTURE_TOLERANCE_MS = 15 min (latch.ts:26), applied at latch.ts:161. The test at latch.test.ts:228 checks four cases:
   - 5 s ahead: no trip;
   - exactly the tolerance ahead: no trip;
   - tolerance + 1 ms ahead: blind;
   - a future `since` with no success: blind.
   M5b (`<=` changed to `<`, the boundary) failed exactly that test.
6. (ruling) tripped_at on a re-trip: **ADDRESSED.** latch.ts:137 keeps the original tripped_at while the station is already spend-tripped. The test at latch.test.ts:189 pins it, and M6 (always `tripped_at: at`) failed exactly that test.
7. (ruling) StoredEvaluation `actual_usd`/`projected_usd`/`budget_usd` are now typed `number | null` (latch.ts:33-35), with a comment. This matches parseGuardDoc's `isNumOrNull` checks. **ADDRESSED.**

Interaction check. Can the new clear path (item 3) or the adoption (item 2) unblock the station while it is over budget? **No.**
- Both sit after the `overThreshold(e)` early return (latch.ts:136). So each needs a successful reading under the thresholds at the evaluation's own effective budget.
- The adoption makes the latch stricter, never looser. The worst case is a trip that lasts one extra period, which is fail-closed.
- In Task 6's guardStep (task-6-brief.md:580-586), an `ok: true` attempt is only built after a `meterProblems` check that would throw on an invalid base. So `baseBudgetUsd` is always valid there, and `e.budgetUsd > base` holds only when effectiveBudget has honoured a raise from state/budget.json. That is an operator action.
- In that flow, a null tripped budget only arises when no raise was honoured at trip time: with a NaN base, effectiveBudget honours any raise, so it would have been recorded. So the new path cannot be satisfied by a raise that was already present when the trip happened.
- Blind vs spend:
  - applyBlindRule still returns early on any trip (latch.ts:159), so it never downgrades spend;
  - a null-period or null-budget spend trip under failed readings stays spend;
  - a blind trip still clears on the first under reading, before the newPeriod/raised logic (`prev.reason === "blind"` → cleared).
- The future-baseline rule only adds trips. A Worker clock stepped back still evaluates first (shouldEvaluate treats a negative age as old), and a success re-bases `last_success`. So it trips only when that evaluation also fails, which is loud and fail-closed, as the ruling accepts.
- The guard-state-corrupt advice ("--raise-to or wait for the next period") now holds in both double faults.

### New breakage in the fix diff
None.

### Out-of-scope observations
- The isFinite(base) guard at latch.ts:148 is a no-op for NaN (`x > NaN` is already false); it only matters for ±Infinity. Harmless, and good as documentation.
- The test at latch.test.ts:213 has a dead `d = at(T0)` reassignment inside its loop. Cosmetic.
- `StoredEvaluation.base_budget_usd` is still typed `number` and parseGuardDoc does not check it. It can only be null on disk if a successful attempt carried a NaN base, which Task 6's meterProblems gate prevents. This was already in the earlier review (qual Minor 6), and only matters to T12 readers.
- Pre-existing, not in the diff: with a NaN base, effectiveBudget honours any raise, even one below the $5 floor, because `usd <= NaN` is false. That reaches corruptGuardDoc's recorded budget. It cannot unblock while over budget: a later valid base counts as "raised" only for an under reading at the real budget. For T6 awareness only.

### Checks run
- Read the brief, constraints R1/R2/R3/R11, the fix report, the fix diff, both original verdicts, and the T4 rulings at ledger.md:81-85. Read the Task 6 guardStep excerpt (task-6-brief.md:440-600) for call-site interactions.
- The implementer's report gives the command (`cd antenna && npm test && npx tsc --noEmit`), the result (94 passed in 8 files; latch file 25 tests; tsc clean), RED evidence, and an 8-mutant table. These match the diff. I did not re-run the full suite.
- Scratch copy (`git archive HEAD antenna | tar -x` into the scratchpad, node_modules symlinked), run from the scratch dir:
  - baseline: 25/25;
  - 8 mutants, each with its red set fixed in the script before running;
  - M1, M2, M3, M4b, M5b, M6 and M7 failed exactly the predicted set;
  - M3c was caught with one extra red test beyond my prediction (see item 3).
  - Afterwards I confirmed the scratch file was restored, then deleted the scratch copy. The live worktree `git status --short` is empty. Output is in t4-rerev1.log.
