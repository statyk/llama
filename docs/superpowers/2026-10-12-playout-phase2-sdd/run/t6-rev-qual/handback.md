VERDICT: NEEDS FIXES

Code-quality review of Task 6 (guardStep), range 8a4d652..a6965fa (aba89a5, a6965fa). Read-only. One Important finding, and it is plan-mandated: the brief's own code swallows a budget.json read failure. Everything else is Minor. The core spend paths are well built: guard first, unknown on an unreadable read, fail-closed blind and corrupt handling, a trip-preserving persist, and no network call with an empty secret.

### Findings

#### Critical
None.

#### Important

**I1 (plan-mandated): an unreadable or corrupt `state/budget.json` is swallowed silently, and during an evaluation it causes a sticky, mis-explained spend trip.**
- **Where:** `antenna/src/guard.ts:349-355` (diff lines 349-355):
  ```ts
  try { const b = await readJsonDoc(bucket, BUDGET_KEY); budgetRaw = b.kind === "ok" ? b.value : null; }
  catch { budgetRaw = null; // unreadable raise: the configured budget (stricter) applies }
  ```
  A get that throws, and a `corrupt` read, both become "no raise". No condition is pushed.
- **What happens:** suppose a raise is active (say $40) and usage sits between the base ($15) and the raise. A transient R2 error on the `budget.json` get in an evaluation minute (1 in 15) causes all of this:
  - the guard evaluates against $15, trips **spend** and enables the kill switch;
  - it sends an urgent `tripped-spend` alert that quotes "of $15.00", plus `budget-50`/`budget-80` once-alerts keyed to budget 15;
  - nothing says the raise could not be read.
- **It stays tripped after the read recovers.** `shouldEvaluate` re-evaluates at once only for a raise whose `written_at` is newer than the last attempt, and this one is older. So the station stays off the air until the next 15-minute evaluation.
- **Measured** with probe P2 in a scratch copy. Run 1: `[blocked=true, tripped=true, ["budget-50:2026-10-11:15","budget-80:2026-10-11:15","tripped-spend"]]`. A run 14 minutes later with `budget.json` readable again: still `blocked=true`, with `tripped-spend`.
- **Why it matters:** it is safe for spend (it fails toward blocking). But it is a swallowed error on the strict surface, and it costs a self-inflicted ~15-minute outage with an urgent alert whose figures mislead the operator. That is the "stricter" branch acting on an input the code knows it does not have.
- **Fix:**
  - when the `budget.json` read throws, or comes back `corrupt`, push a condition (say `budget-unreadable`, resolvable);
  - skip the evaluation this invocation, without advancing `evaluated_at`, so the next minute retries;
  - the blind rule, the offair flag, WAF reconciliation and persistence are unaffected;
  - add a test with `failGets.add(BUDGET_KEY)`, an active raise and FLAT14 usage, asserting no trip and the condition.
- **Related, in Task 4's code, outside this diff:** an `ok` but malformed `budget.json` is also ignored silently by `effectiveBudget`.

#### Minor

**M1: a non-evaluating run can turn off a racer's freshly enabled kill switch and report unblocked, and the next run then raises a false "toggled by hand" alert.**
- **Where:** `guard.ts:407-450`.
- **What happens:** the handback's concern covers the variant where our persist loses the race. It misses the variant where we never persist:
  - invocation A reads the old document and does not evaluate (it is under 15 minutes from the last evaluation);
  - B (later, evaluating) trips, enables the switch and writes `guard.json`;
  - A's reconcile then disables the switch;
  - A's `doc.waf` (`{enabled:false}`) equals `prev.waf`, so `JSON.stringify(doc) === JSON.stringify(prev)`, nothing is persisted, the race is never discovered, and the outcome is `blocked:false`.
- **Measured** with probe P1: `{blocked:false, tripped:false, switch:false, stored guard.json tripped:true}`.
- **The next run** re-enables the switch, which is correct. But `prev.waf.enabled` (B's `true`) equals `r.enabled`, so it emits `waf-corrected` "Kill switch toggled by hand" (P1 next: `["waf-corrected","tripped-spend"]`). The same false alarm follows the disclosed persisted variant, and also a yielded blind trip.
- **Why only Minor:** the trip is not lost from state, the damage is bounded to one minute, and it needs overlapping invocations. Still, it is one minute unblocked while over budget plus a high-priority alert that points the operator at a human who does not exist.
- **Cheap mitigation within the bounds:** when the reconcile turned the switch **off** (`r.changed && !r.enabled`) and nothing was persisted, do one `head(GUARD_KEY)`. If the etag differs from the one read, re-read it and fold `final.tripped` into the outcome. That is a rare Class B read, and no second Rulesets GET. At the least, word `waf-corrected` as "toggled by hand or by an overlapping invocation".

**M2: a document deleted between our read and write is rewritten unconditionally.**
- **Where:** `guard.ts:320-323` (`pre = null`).
- **What happens:** after an etag-conditioned write fails and the re-read finds the key absent, the next attempt is an unconditional put, which can clobber a racer that created the document in that window.
- **Fix:** use create-only (`"absent"`) here. Keep the unconditional step only for "create-only refused, and the key is still absent", the broken-store fallback.
- Needs a hand delete plus an overlapping invocation, so it is very unlikely.

**M3: an exhausted persist leaves the trip out of storage.**
- **Where:** `guard.ts:316-332`.
- **What happens:** after 3 lost races the racer's untripped document stands. A spend trip is then absent from state until the next evaluation (up to 15 minutes; a blind trip re-derives the next minute).
- It is alerted (`guard-write`) and pathological, so this is acceptable. Note it in a comment.
- The last iteration also does one re-read and merge it never uses (one wasted Class B read).

**M4: test gaps on the unknown and budget paths.**
- The only unknown-state test fails `GUARD_KEY`'s get. Nothing pins that a throwing **`offair.json`** get is also unknown: a mutant that moved the offair read out of the `try` would survive.
- Probe P3 shows the current behaviour is right: `[null, ["guard-unknown"], 0 fetch calls, 0 puts]`. Add the one-line test (Review Focus 1).
- The `budget.json` failure path (I1) is untested.

**M5: `guardConditions` can throw after the finally.**
- **Where:** `conditions.ts:117`, `usd()`.
- **What happens:** `parseGuardDoc` (Task 4) checks only the evaluation's three amounts. A parseable document whose `evaluation` lacks `at` while `period` is null, or holds a non-number amount, makes `(…).slice` or `toFixed` throw. guardStep then throws after it has persisted, and Task 8 treats that as unknown until the next evaluation replaces the evaluation (≤15 minutes).
- It only arises from a hand edit, and it fails toward "write nothing". Validate `evaluation.at` in `parseGuardDoc`, or contain the throw.

**M6: test nits.**
- `racerPut` returns `realPut`, and no caller uses it (`guard.test.ts:848-859`).
- The brief's "never loses a trip" test duplicates the racer wrapper inline. It is brief-verbatim, so it is fine to leave.
- `writeRaw2` is referenced before its `const` declaration (`guard.test.ts:919-924`). That works only because the closure runs later; declare it first.

### ⚠️ Cannot verify from diff
- **`onlyIf: { etagDoesNotMatch: "*" }` on production R2.** It is verified only against miniflare.
  - The degradation analysis holds:
    - a store that throws on it falls back to an unconditional put;
    - a store that refuses an absent key finds it absent on re-read and goes unconditional;
    - a store that treats `"*"` as a literal etag just writes.
  - So every failure mode reduces to the brief's unconditional first create, never to "never created".
  - Worth the operator checkpoint the implementer proposes: the first `guard.json` write succeeds.
- **Task 7/8 behaviour, out of scope here:**
  - `guard-state-corrupt` is `resolvable`, so it will "resolve" the minute after the corrupt bytes are overwritten, while the spend trip it caused stands (`tripped-spend` continues). Check the alert wording in Task 7's dispatcher.
  - Task 8 must treat a throwing `guardStep` as unknown, which also covers M5.
- **`WafError` messages put the zone ID into `guard.json` (`waf.error`).** This is acceptable only because `state/` is not on the public allowlist (`docs/playout-setup.md:98`). It is not re-verified against the deployed WAF.

### Strengths
- **Unknown state:** the guard-first structure is exactly right. Both gets sit in one `try`, an unknown outcome returns before any fetch or put (P3 confirms zero calls), and `blocked` starts at `true`.
- **No network call with an empty secret:** both problem lists are thrown before their calls, blank or whitespace secrets count as missing, and tests assert zero fetch calls.
- **The WAF catch** catches any throw (`TypeError`, `DOMException` timeout), keeps the decision, and records the error. It is tested for all three kinds.
- **The persist redesign beats the brief:**
  - a corrupt winner is left for the next reader (fail closed), not overwritten untripped;
  - a deleted document is rewritten;
  - create-only first creation closes the absent-key race;
  - spend replaces blind in `mergeLostRace`, which is the correct stickiness ordering.
- **The outcome folds in the stored document** (`blocked || tripped` from the winner), so a racer's persisted trip blocks this minute's playlist.
- **`conditions.ts` handles null amounts** by alerting at every level instead of coercing to 0, and has its own tests.
- **Tests are offline and hygienic:** `fakeFetch` throws on unmatched calls, and the placeholder IDs and tokens contain no account details.
- **The 13-mutant check** with predictions and a sentinel is good practice.

### Checks run
- **Unknown state (Review Focus 1).** Read `guard.ts:339-348`. Probe P3 in a scratch copy (`git archive a6965fa antenna`, `node_modules` symlinked), with the `offair.json` get failing: outcome `blocked:null`, `["guard-unknown"]`, 0 fetches, 0 puts.
- **Race on `guard.json` (Review Focus 2).**
  - Traced `persist`, `writeGuard` and `mergeLostRace` across the absent, etag, deleted, corrupt-winner and exhausted cases.
  - Probe P1 (a non-evaluating run during a racer's trip) gave `{blocked:false, switch:false, stored tripped:true}`, then the next run gave `["waf-corrected","tripped-spend"]`. That is M1.
- **Kill switch failure (Review Focus 3).** Read the reconcile `try`/`catch` and the `waf.ts` throw sites (`waf.ts:47-87`). No path toggles anything when `wafProblems` is non-empty.
- **Missing secrets (Review Focus 4).** Read `guardConfigFromEnv`, and checked that `meterProblems` is thrown before `billingPeriod` and `readUsage`. An invalid anniversary day throws in `billingPeriod` before any fetch.
- **budget.json failure.** Probe P2 (raise $40, FLAT14 usage, `budget.json` get failing) gave a spend trip quoting $15. A run 14 minutes later with the read healthy was still blocked. That is I1.
- **Public-repo hygiene.** Grepped the `meter.ts`/`waf.ts` error messages, and checked the `docs/playout-setup.md` allowlist note for `state/`.
- **Focused test command** (scratch copy only): `cd <scratch>/antenna && npx vitest run test/probe.test.ts`. The probes were written as deliberately failing assertions to reveal the values quoted above; the output is in `t6-rev-qual.log`. The live worktree was not modified.
