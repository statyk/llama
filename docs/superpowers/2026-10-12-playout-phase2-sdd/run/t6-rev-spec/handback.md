VERDICT: APPROVED

Task 6 (guardStep), spec-compliance seat. Review package 8a4d652..a6965fa (aba89a5, a6965fa).

### Findings

#### Critical
None.

#### Important
None.

#### Minor
1. **`antenna/src/guard.ts:320-323` (`persist`, deleted-document branch): the retry after a deletion is unconditional (`pre = null`), not create-only.**
   - If a third invocation creates `guard.json` between our re-read and our retry, we overwrite it, and a trip it carried is lost.
   - That needs a manual delete plus two overlapping writers, so the window is tiny.
   - The unconditional fallback has a purpose: if the store answers `etagDoesNotMatch:"*"` on an absent key with null, a create-only retry would never write. But that only applies when the failed write was itself create-only.
   - Fix: `pre = pre === "absent" ? null : "absent"`. A deletion after an etag-conditional write then retries create-only, and the fallback for a store that refuses `*` is kept.
2. **`guard.ts:417` together with Deviation 4 (implementer concern 2): after losing a race to a tripped winner, the kill switch lags by one invocation, and the alerts falsely report a hand toggle.**
   - Our run reconciles the kill switch to our own unblocked decision before `persist` finds the winner's trip.
   - Our stale `prev.waf.enabled` (false) then makes us alert `waf-corrected` ("toggled by hand") while we turn off the winner's enable.
   - The next run alerts `waf-corrected` again: the stored `prev.waf.enabled` is the winner's `true`.
   - The outcome still reports blocked, so ENDLIST and the off-air page apply that minute. Keeping to one Rulesets GET per invocation is the right call under the Global Constraints.
   - So this is not a Stakes breach: the block is loud, cooperative and lasts one minute. It is two misleading alerts on a rare overlap. It could go in the T6 notes for T12 (alerts), or the `waf-corrected` check could be skipped when `stored` differs from `doc`.
3. **`guard.ts:437`: when a corrupt winner is left in place, this run's conditions carry `tripped-spend` but not `guard-state-corrupt`.** The next reader alerts it, so the alert is one minute late. Cosmetic.
4. **Extra files beyond the brief's three:** `bucket.ts`, `support.ts`, `bucket.test.ts`, `conditions.test.ts`.
   - Each is justified. They close the two Task 1 carry-forward minors in the ledger: the `putJson` etag-truthiness first-creation race, and pinning that a corrupt read carries its etag.
   - `conditions.test.ts` pins Deviation 5.
   - Recorded here only so the final reviewer knows the stat goes past the brief.

### ⚠️ Cannot verify from diff
- **Production R2 semantics of `onlyIf: { etagDoesNotMatch: "*" }`.** Verified only against miniflare (`bucket.test.ts`, real binding). I traced every outcome:
  - honoured: correct;
  - `*` treated as a literal etag: the put becomes unconditional, which is the brief's behaviour;
  - a throw: the unconditional fallback at `guard.ts:299-306`;
  - null on an absent key: re-read finds it absent, then an unconditional write.

  None can stop `guard.json` being created, so the worst case is the brief's behaviour. The implementer's suggested check at the operator checkpoint (the first `guard.json` write succeeds) is the right one.
- **Wiring the env vars** (`GUARD_EVAL_SECONDS`, `BLIND_AFTER_SECONDS`, `KILL_SWITCH_DESCRIPTION`, `BILLING_ANNIVERSARY_DAY = "11"` per R12) into `wrangler.jsonc`/`Env`, and calling `guardStep` first in the clock: these are Task 7/8. Not in this diff.
- **Task 8's "a guard that throws is treated as unknown"** is the backstop for any throw left in `guardStep`. Two examples: `guardConditions` on a hand-edited `guard.json` whose `budget_usd` is a string (Task 4 deferred minor: `parseGuardDoc` does not type-check `StoredEvaluation`), and a throw from `shouldEvaluate`. Task 8 has to hold that line.
- **Zone ID in alert text** (Task 5 ledger note). `waf-api`'s message embeds `msg(e)`, which carries the Rulesets request path, so the zone ID will reach ntfy/email once T12 dispatches conditions. It is not a committed file, so it does not breach the public-repo rule, but T12 or the final reviewer should decide whether to redact it.
- **An unreadable or corrupt `state/budget.json` is silently ignored** (`guard.ts:349-355`). This is the brief's own code and it fails closed (the base budget applies, which is stricter). There is no alert, though. While spend-tripped, an operator's mangled raise just doesn't take, and `tripped-spend` keeps repeating. Overlaps the Task 4 deferred minor about malformed raises being silently ignored.

### Strengths
- **The brief's test file is verbatim.** Lines 1-271 of `antenna/test/guard.test.ts` are byte-identical to the brief (checked by diff). All 21 brief tests are present under the brief's names, including every Review Focus test this task owns (1, 2, 3 and 4).
- **The order inside `guardStep` matches spec and brief:**
  - read `guard.json` and `offair.json` in one try, and a throw returns `blocked: null` with exactly `guard-unknown`: no evaluation, fetch or write (R2);
  - evaluate in a `try`, with `meterProblems` thrown before any network call (R11, Focus 4);
  - in the `finally`: the blind rule, then `blocked = tripped || offair`, then the WAF reconcile (any throw becomes `waf-api`, and a block stays cooperative), then the conditional persist.
- **Values match the brief:**
  - `DEFAULT_BLIND_AFTER_S = 21600`;
  - `READING_WARN_MS = 3_600_000`;
  - clamps 60-900 s and 900-21,600 s, defaulting to the strictest values (R11);
  - default kill-switch description `"station: kill switch"`;
  - every condition key in the brief is present with the brief's priority, `resolvable` and `once` flags: `budget-50/80:<period>:<budget>` once, `tripped-spend`, `tripped-blind`, `guard-reading-failing`, `guard-unknown`, `offair-corrupt`, `guard-state-corrupt`, `waf-api`, `waf-corrected`, `budget-file-invalid` once, `guard-write`;
  - a corrupt `offair.json` fails closed (R2);
  - a corrupt `guard.json` becomes a spend trip, overwritten over its own etag.
- **Deviations judged against the spec and Stakes:**
  - **D1 (create-only first write):** closes the Task 1 deferred first-creation race. It serves "a lost race never loses a trip", and every fallback degrades to the brief's behaviour, never below it.
  - **D2 (bounded merge loop; corrupt winner left; deleted winner rewritten):** strictly safer than the brief, which silently dropped our document on any non-ok re-read. Leaving corrupt bytes is right, because R2 turns them into a spend trip. Overwriting them with an untripped document would unblock.
  - **D3 (spend replaces a blind winner):** the brief's prose says "only a blind trip yields", but its code let a spend trip yield to a blind winner. A blind latch clears at the first under-threshold reading, while R3 makes spend clear only with a raise or a new period. The deviation follows the prose and the Stakes, and a blind trip still never replaces a spend trip. Correct.
  - **D4 (outcome reflects stored state, never less blocked):** fail-closed for the clock that minute. Its only cost is Minor 2.
  - **D5 (null-safe conditions, alerting toward unknown):** needed by Task 4's `number|null` StoredEvaluation change. Without it the brief's `usd(null)` crashes, and `Math.max(null, …)` coerces null to 0 and could silence an alert.
  - **D6:** wiring only.
- **Ledger carry-forwards handled:**
  - Task 1's two Task-6 minors are fixed and pinned;
  - Task 4's NaN-base note is neutralised by the `meterProblems` throw ahead of `applyAttempt`;
  - Task 4's `tripped_budget_usd` null-raise ruling is reachable through `baseBudgetUsd` in the attempt.

### Checks run
- **Is the test file verbatim from the brief?** I extracted the brief's ```ts block and diffed it against `antenna/test/guard.test.ts`. The only difference is the implementer's appended blocks from line 272 on. I did the same for `conditions.ts`: the only difference is the null-safe `usd`/`peakFraction` (D5).
- **R11: does a missing `BILLING_ANNIVERSARY_DAY` fail loudly, given the Task 1 minor about `billingPeriod(NaN)`?** I read `antenna/src/period.ts`. `Number(undefined)` is NaN, and `Number.isInteger(NaN)` is false, so it throws. The Task 1 minor concerns `nowMs`, not `day`. `periodOrNull` then returns null, which `effectiveBudget` and `corruptGuardDoc` both accept.
- **Can the blind rule override or downgrade a spend trip, given D3 merges spend onto a blind winner's old `last_success`?** I read `latch.ts` `applyBlindRule` (it returns early when `doc.tripped`) and `applyAttempt` (spend clears only on a new period or a raise). The merged document stays spend-tripped across an under-threshold evaluation.
- **First-run `waf-corrected` spuriousness:** `freshGuardDoc` has `waf.enabled: null` (`latch.ts:68`), so neither the first run nor a corrupt-derived `prev` can alert `waf-corrected`.
- **Production `etagDoesNotMatch:"*"` failure modes:** traced through `writeGuard` and `persist` (`guard.ts:296-333`); see ⚠️ above.
- **Takeover flags:** absent before writing.

No tests were run. No reading raised a doubt that the implementer's reported run (138 passed, tsc clean) and the 13 predicted-and-caught mutants leave open.
