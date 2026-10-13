VERDICT: APPROVED

Task 4 (the latch) spec-compliance review. Base 5a4ebcf, head 52cc6f0. Reviewer: t4-rev-spec (Opus).

### Findings

#### Critical
None.

#### Important
None.

#### Minor

1. **Plan-mandated, needs an orchestrator decision: a `written_at` ahead of the Worker's clock triggers an evaluation every minute, which breaks the Global Constraint "one GraphQL POST per 15 minutes".** This is the implementer's concern 1, and I confirmed it.
   - Where: `antenna/src/latch.ts` `effectiveBudget`, where `writtenAtMs = Math.min(written, nowMs)`, combined with `shouldEvaluate`'s `budgetWrittenAtMs > last`.
   - How it happens: Task 6 calls `shouldEvaluate(prev, nowMs, …, budget.writtenAtMs)`. Each invocation's clamped `writtenAtMs` equals `nowMs`. That is always later than the previous minute's `evaluated_at`, so every invocation evaluates until the real clock passes `written_at`.
   - Who can trigger it: a writer whose clock is ahead, or a hand-written `state/budget.json` with a typo'd future `written_at` (for example the wrong year). The typo case means one POST a minute for as long as the typo lasts, with no alert.
   - Severity: it is not billed spend, and the GraphQL rate limit is far away. Latch correctness is untouched. So it is Minor, not Important. R1 ("a raise newer than the last attempt triggers an evaluation at once") literally asks for this behaviour, so the plan conflicts with itself.
   - Fix options (plan decision, not the implementer's):
     - (a) Use `budgetWrittenAtMs > last && budgetWrittenAtMs < nowMs` in `shouldEvaluate`. A skewed raise then waits at most 15 minutes. The brief's `shouldEvaluate` and clamp tests, and Task 6's raise test (written_at T0+M), still pass.
     - (b) Treat a `written_at` more than a small tolerance ahead of now as invalid, and report it through `invalid`.

2. **Brief-mandated: a spend trip with `tripped_period_start: null` clears on the first reading under the thresholds, because `null !== periodStart` counts as a new period.** This is the implementer's concern 2.
   - Where: `antenna/src/latch.ts` `applyAttempt`, the `newPeriod` line.
   - When it happens: only `corruptGuardDoc(nowMs, null, …)` produces this state. Task 6 makes that call when `periodOrNull` returns null, i.e. `BILLING_ANNIVERSARY_DAY` is invalid, at the same moment `guard.json` is corrupt.
   - Why it is Minor: in that state every evaluation fails, so nothing clears until the day is fixed. Even then the clear needs a successful reading under both thresholds, so the station is never unblocked while over budget. That is consistent with the Stakes paragraph.
   - It still departs from R2's wording ("a corrupt guard.json … clears only with a raise or a new period") in that double fault.
   - Making it stricter (treat a null start as "same period") would need a raise to clear, and combined with deviation 1's null budget it could make the trip permanent. Leave as is unless the orchestrator wants to rule.

3. **Recovery wording (⚠️ for Task 6 / whole branch, not a Task 4 defect).** Suppose `guard.json` is corrupt while `MONTHLY_BUDGET_USD` is invalid and no raise is present.
   - `tripped_budget_usd` is recorded as null. Under the brief's code it would also have become null on disk, since NaN serializes as null.
   - A null budget means no raise can ever clear the trip; only a new period can.
   - Task 6's `guard-state-corrupt` message nevertheless tells the operator to "Clear it with `transmitter budget --raise-to <usd>`". This fails closed (good), but in that double fault the advice does not work.

### Deviations judged

- **Deviation 1 (`finiteOrNull` on `tripped_budget_usd` in `applyAttempt` and `corruptGuardDoc`): accepted.**
  - It behaves the same as the brief.
    - In memory: under the brief's code, `e.budgetUsd > NaN` is false, so a raise could not clear a NaN-budget trip either.
    - On disk: NaN already became `null` through `JSON.stringify`, and `prev.tripped_budget_usd !== null` blocks the raise clear.
  - The change only makes the in-memory doc match what is persisted, which matters for Task 6's `JSON.stringify(doc) !== JSON.stringify(prev)` comparison. That comparison was already equivalent, so nothing changes there.
  - A new period still clears the trip, as R3 and the spec require.
  - Not making `effectiveBudget` throw is correct: a throw outside Task 6's try would become `guard-crashed` → unknown, and the R11 blind trip would never fire.
- **Deviation 2 (`parseGuardDoc` validates `waf`, `period` and `evaluation` shapes): accepted.**
  - It only rejects more documents, and a rejected document becomes a corrupt spend trip, so the change is fail-closed.
  - Every document Task 6 writes passes the stricter check. I traced its writers: `freshGuardDoc`, `applyAttempt`, `applyBlindRule`, `corruptGuardDoc`, `mergeLostRace` (spreads `theirs`), and `waf: { enabled: r.enabled | prev.waf.enabled, error: null | msg }`.
  - A NaN evaluation field serializes to `null` and is allowed, so the code's own writes round-trip. The new test pins this for both the tripped and the fresh doc.
  - Task 6 reads `prev.waf.enabled` and `e.budget_usd` (`task-6-brief.md` around lines 348 and 598), and the stricter check protects exactly those reads.
  - This is not over-engineering: the check stays within the parse function's stated contract ("null when its shape is not one this code wrote").
- **One commit instead of two:** the brief prescribes a single commit (Step 5), so there is no deviation.

### ⚠️ Cannot verify from diff
- Every `corruptGuardDoc`, `shouldEvaluate` and `effectiveBudget` call site lives in Task 6, so the end-to-end behaviour of the R2 corrupt-doc path and of the R1 raise trigger is unverified here.
- The thresholds come from `overThreshold` (actual ≥ 90%, projected ≥ 100%, trips on NaN), which is Task 2's.
- Task 12 (transmitter) reads the `GuardDoc` schema and should be checked against the field list there.

### Strengths
- `antenna/src/latch.ts` is the brief's code verbatim except for the two declared hardenings. I checked this mechanically by diffing the brief's code block against the committed file.
- `antenna/test/latch.test.ts` contains all 15 of the brief's tests verbatim, with the brief's names and assertions (also checked by mechanical diff), plus 4 added tests for the hardenings.
- All exported names, constants and signatures match the brief exactly: `GUARD_KEY`, `BUDGET_KEY`, `OFFAIR_KEY`, `MAX_BUDGET_USD = 100`, `TripReason`, `StoredEvaluation`, the `GuardDoc` fields, `freshGuardDoc`, `parseGuardDoc`, `corruptGuardDoc`, `Attempt`, `applyAttempt`, `applyBlindRule`, `shouldEvaluate`, `EffectiveBudget`, `effectiveBudget`, `validBaseBudget`.
- Only the two listed files are touched.
- Every latch rule holds against the spec "Blocking" text, R1 and R3, and each has a test:
  - set spend;
  - set blind, measured from `last_success`, else `since`; an unparseable baseline trips;
  - clear blind on the first success under the thresholds;
  - clear spend on a new period or an effective budget strictly above `tripped_budget_usd`, and only when that evaluation is under;
  - an over evaluation after a raise consumes it;
  - a failed reading only records `evaluated_at` and `last_error`;
  - blind never downgrades spend.
- R1: the cadence is measured from the last attempt, and a clock stepped back triggers an evaluation.
- R3 and R5: a raise only raises, is capped at `MAX_BUDGET_USD`, and is ignored and reported when it expires after the current period.
- The implementer's concerns were candid and accurate. I reproduced both by reading the code.

### Checks run
- **Brief fidelity.** Extracted the brief's `latch.test.ts` and `latch.ts` code blocks and diffed them against the committed files. The test file differs only by the two appended `describe` blocks. The source differs only by `isObj`/`finiteOrNull`, the nested parse checks and the two `finiteOrNull` call sites.
- **Risk: the stricter parse rejects a doc Task 6 legitimately writes.** I read Task 6's `guardStep`, `persist` and `mergeLostRace` (`task-6-brief.md` lines 495-620): every write is built from latch functions or the `waf` literal above, and all pass. Not a risk.
- **Risk: deviation 1 changes clear semantics.** I traced NaN through `applyAttempt`'s `raised` comparison before and after the change, in memory and through a JSON round-trip. Equivalent.
- **Risk: written_at skew busts the GraphQL cadence bound.** I traced `effectiveBudget`'s clamp and `shouldEvaluate` across consecutive minutes. Confirmed; see Minor 1.
- **Risk: a null tripped period clears weakly.** I traced `periodOrNull` → `corruptGuardDoc` in Task 6. It is reachable only in the double fault; see Minor 2.
- **Spec text.** Read `docs/superpowers/specs/2026-10-09-playout-design.md` lines 487-525 ("Cost guard (phase 2)", Blocking).
- **Focused test:** `cd antenna && npx vitest run test/latch.test.ts` gave `Test Files 1 passed (1)`, `Tests 19 passed (19)`, with no warnings or noise.
- No mutants were run, because the brief's tests are verbatim and the implementer reported RED→GREEN for the hardening tests.
