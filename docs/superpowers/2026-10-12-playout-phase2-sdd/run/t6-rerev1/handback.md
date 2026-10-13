VERDICT: ALL ADDRESSED

Scoped re-review of Task 6, fix round 1. Range a6965fa..053c5db. Read-only: the worktree is clean, and the one probe ran in a `git archive` scratch copy that has since been deleted.

### Finding verdicts

1. **I1 (`budget.json` failures): ADDRESSED.**
   - `antenna/src/guard.ts:211-227`: a get that throws sets `budgetReadFailed` and pushes `budget-unreadable` (high, resolvable). A `corrupt` read pushes the same condition and keeps `budgetRaw = null`, so the evaluation runs against the base budget.
   - `guard.ts:268`: `!budgetReadFailed && shouldEvaluate(...)`. Skipping happens before `applyAttempt`, so `evaluated_at` is not advanced and the next minute retries.
   - Blind still applies. `applyBlindRule` sits unconditionally in the `finally` (`guard.ts:282`) and counts from `last_success ?? since` (`latch.ts:160-168`). Offair, the reconcile and persist are unaffected.
   - Tests:
     - "a budget.json read that throws skips the evaluation and alerts; the next minute evaluates against the raise" asserts 0 GraphQL calls, `evaluated_at: null`, the condition, and a $40 evaluation the next minute;
     - "a corrupt budget.json evaluates against the base budget and alerts" asserts a trip at $15 and the condition.
   - Both match the ruling.
2. **Ruling M1 (unblock re-check): ADDRESSED.**
   - `guard.ts:321-344`: when the reconcile turned the switch off (`turnedOff`, set at `guard.ts:291`) and nothing was stored, the run does one `head(GUARD_KEY)`. A changed etag triggers a re-read, and a tripped or corrupt winner is folded into `stored`, so `blocked`/`tripped` come out true (`guard.ts:348-351`).
   - A throw from the HEAD or the re-read fails toward blocked (`raceUnknown`, plus `guard-unknown`).
   - The `waf-corrected` wording now says "changed by hand or by an overlapping invocation" (`guard.ts:295-299`).
   - The reviewer's P1 scenario is a test: "a non-evaluating run that turns the kill switch off folds in a racer's newer trip". The no-race case is pinned to exactly one HEAD.
   - `readJsonDoc` and `head` compare the same `etag` field (`bucket.ts:50`, `ObjectInfo.etag`), so the comparison is like-for-like.
3. **Ruling M2 (create-only re-create): ADDRESSED.**
   - `guard.ts:177`: `pre = pre === "absent" ? null : "absent"`. A deletion after an etag write retries create-only. The write is unconditional only after a refused create on a still-absent key.
   - The worst chain (etag, then create, then unconditional) fits inside `PERSIST_ATTEMPTS = 3`.
   - Both new tests pass by trace:
     - the racer-recreates case returns the racer's tripped document;
     - the store-refusing-`*` case ends in an unconditional write with no `guard-write`.
4. **Ruling M3 (exhausted persist): ADDRESSED.**
   - The window is documented at `guard.ts:158-165`.
   - The loop breaks before the last re-read (`guard.ts:168-170`): 3 puts and 2 reads, then a throw, which becomes `guard-write`.
   - The caller's outcome keeps our decision (`final = doc` when `stored` is null), as the comment says.
5. **Ruling M4 (throwing `offair.json` get): ADDRESSED.** New test "a throwing offair.json get is unknown: no fetch, no write" asserts `blocked:null`, exactly `["guard-unknown"]`, 0 fetches and 0 puts. The guard and offair reads share the one try (`guard.ts:196-203`).
6. **Ruling M5 (`evaluation.at`): ADDRESSED.**
   - `latch.ts` `parseGuardDoc` now requires `isStr(ev.at)`.
   - I checked every field `guardConditions` reads (`conditions.ts:39-70`: `period.start`, `e.at`, the three nullable amounts, `tripped_at`, `last_success`, `since`, `last_error`). All are now validated, so a parseable document can no longer make it throw.
   - Tests: two new bad shapes in `latch.test.ts`, plus the guard-level "hand-edited guard.json … is corrupt (a spend trip), not a throw".
7. **Ruling M6 (test nits): ADDRESSED.** `racerPut` no longer returns `realPut`, and `writeRaw2` is declared before the closure that uses it.

**Disclosed residual: acceptable under the Stakes, and no cheap fix closes it.**
- **What happens:** our etag-conditional write lands, and then a racer's merge lands its trip. Our minute is reported unblocked, the switch is off, and the trip stands in state.
- **Why it is in bounds:**
  - "a lost race never loses a trip" holds: the trip is persisted by the racer's merge;
  - it is not silent: the racer's own outcome is blocked and alerts `tripped-spend`, and the next run re-enables the switch and alerts `waf-corrected`;
  - it lasts at most one minute and needs overlapping cron invocations.
- **Why no cheap fix closes it:** the window is inherent to lock-free reconcile-then-persist.
  - The racer only writes its merged trip after its first put has failed against ours and it has done a GET. A re-read right after our own successful put will usually come before that, so a GET (or a HEAD against our written etag) on every unblocking write mostly misses it.
  - The fixed M1 path has the same irreducible window: a racer whose reconcile comes before ours and whose persist comes after our HEAD.
  - Narrowing it would mean changing `putJson`'s return type, for little gain.
- **Verdict:** accept as disclosed. Record it as a known one-minute window in the T6 notes.

**Can a persistently throwing budget read postpone blind? No.**
- `applyBlindRule` runs unconditionally, with the baseline at `last_success ?? since`.
- Probe in a scratch copy: success at T0, then `budget.json` gets fail.
  - T0+359 min: unblocked, with `budget-unreadable`.
  - T0+360 min: `blocked:true, tripped:true`, `reason:"blind"`, switch enabled, still exactly 1 GraphQL call, conditions include `budget-unreadable` and `tripped-blind`.
  - Passed (40/40 in the scratch `guard.test.ts`, the probe included).

### New breakage in the fix diff
None. Two non-blocking notes:
- **Minor:** no committed test pins "blind still trips while the budget read keeps throwing". The ruling's "cost if wrong" depends on that property. A mutant that guarded `applyBlindRule` with `!budgetReadFailed` would survive the suite. The probe above (about 15 lines, using the existing `cloud`/`step` helpers) could be added as a test.
- **Minor, cosmetic:** in the M1 fold case (`guard.ts:292-299` together with `321-336`), the same run still emits `waf-corrected` "…set to off to match blocked=false" while its outcome is `blocked:true`. The message describes what the reconcile did, not the final outcome. It is harmless, but confusing next to `tripped-spend`.
- During a persistent `budget.json` throw, `guard-reading-failing` never fires, because no attempt is made and so `last_error` is not set. `budget-unreadable` is the early warning instead, and its message says the blind rule keeps counting. That is acceptable.

### Out-of-scope observations
- `budget-unreadable` is a new condition key that is not in R13's list. Task 7/12 (alert dispatch) and the Task 17 runbook should list it alongside the others.
- An `ok` but malformed `budget.json` (for example `{}` or `budget_usd: "40"`) is still ignored silently by `effectiveBudget` (`latch.ts:197-208`, Task 4 code). The implementer disclosed this and it is outside the ruling.
- The `$${cfg.baseBudgetUsd}` in the corrupt-budget message renders `$NaN` when the base is invalid. That case is already alerted through `meterProblems`, so this is cosmetic.

### Checks run
- Read: `rereview-common.md`, the Task 6 brief, `constraints.md` (Stakes, R1/R2/R11/R13, Review Focus 1–4), the implementer handback including "Fix round 1", `t6-fix1.diff`, both original verdicts, and the three "Ruling: T6" ledger lines.
- Read the current `antenna/src/guard.ts` (lines 100-352) at HEAD 053c5db, plus `bucket.ts` (`readJsonDoc`/`putJson`/`createJson`), `latch.ts` (`applyBlindRule`, `shouldEvaluate`, `effectiveBudget`), the fields `conditions.ts` reads, and `test/support.ts` (MemoryBucket `head`/`log`/precondition semantics).
- Traced each new test against the code: the throwing and corrupt budget cases, P1 fold, one-HEAD, offair-throw, deleted-then-recreated, refused-`*` fallback, hand-edited `evaluation.at`.
- Focused probe, scratch only. `git archive 053c5db antenna | tar -x` into the session scratchpad, with `node_modules` symlinked, then `npx vitest run test/guard.test.ts` from the scratch dir. Result: `Tests 40 passed (40)`, the persistent-budget-throw blind probe included. Output is in `t6-rerev1.log`. The scratch copy was deleted afterwards.
- I did not re-run the full suite. The implementer reports `npm test && npx tsc --noEmit` at 146 passed in 11 files with tsc clean, and 8 predicted-and-caught fix mutants with a sentinel. That is consistent with the diff.
- Takeover flags were absent before writing. The worktree is clean.
