# Task 6 (t6-impl) handback: guardStep

**Status: DONE_WITH_CONCERNS.** The concerns are minor and listed at the end.

## Commits
- `aba89a5` feat(antenna): create-only state puts (etagDoesNotMatch "*"); pin that a corrupt read carries its etag
- `a6965fa` feat(antenna): guardStep -- evaluate, blind rule and kill-switch reconciliation in its finally

## Tests
`cd antenna && npm test && npx tsc --noEmit`: **138 passed in 11 files; tsc clean** (was 102 in 9 files). 13 of 13 predicted mutants were caught.

## What was implemented
- `antenna/src/conditions.ts`: implemented as the brief has it, plus null-safety (Deviation 5).
- `antenna/src/guard.ts`: `guardStep`, `guardConfigFromEnv`, `mergeLostRace`, `DEFAULT_BLIND_AFTER_S`. The order is the spec's: read state (an unreadable read is unknown, so nothing is written), evaluate in a `try`, then in the `finally` the blind rule, `blocked = tripped || offair`, the WAF reconcile and the conditional persist.
- `antenna/src/bucket.ts`: new `createJson`, a create-only put using `onlyIf: { etagDoesNotMatch: "*" }`. `PutOptions.onlyIf` is widened to the union. `test/support.ts`'s MemoryBucket honours the new precondition.
- Tests:
  - `antenna/test/guard.test.ts`: the brief's 21 tests verbatim, plus 10 of mine.
  - `antenna/test/conditions.test.ts`: new, 3 tests.
  - `antenna/test/bucket.test.ts`: 2 new tests, plus create-only assertions against the real R2 binding (miniflare).

## Deviations from the brief (each with its reason)
1. **First creation is create-only (the race you flagged).**
   - When `guard.json` is absent, `persist` writes with `createJson`.
   - A failed create goes through the same read-and-merge path as a lost etag race.
   - **Evidence:** miniflare's R2 binding honours it, pinned in `bucket.test.ts` against `env.BUCKET`. It refuses over an existing key and writes an absent one. Miniflare's R2 wire schema carries a `{type:"wildcard"}` etag, and its `_testR2Conditional` implements it.
   - **Not verified on production R2.** Cloudflare's docs say "all conditional headers aside from If-Range are supported" for the binding, and list If-None-Match for S3 PutObject. They do not mention `*` explicitly.
   - **Fallbacks, so production cannot make this worse than an unconditional put:**
     - if `createJson` **throws** (store refuses the precondition), `writeGuard` falls back to an unconditional put. Otherwise guard.json would never be created, every invocation would start fresh, and blind would never trip;
     - if the create is refused (null) but a re-read finds the key **absent**, the next attempt is unconditional.
2. **`persist` is a bounded loop (3 attempts) instead of one merge attempt.**
   - Losing again after merging retries the merge. Exhausting the attempts throws, which raises `guard-write`.
   - A winner whose bytes are **corrupt** is left in place. The next reader turns it into a spend trip with `guard-state-corrupt`, so overwriting it with an untripped doc would unblock.
   - A winner that was **deleted** is rewritten.
   - The brief's version silently dropped our doc in both cases (`latest.kind !== "ok"` returned).
3. **`mergeLostRace`: a spend trip replaces a winner's blind trip.** The brief returned null whenever theirs was tripped. Spend is the stickier latch (R3: only a raise or a new period clears it). Blind clears at any under-threshold reading, and a projected figure can fall back under within a period. So a blind winner would effectively lose our spend trip. A blind trip still never replaces a spend trip. The brief's two `mergeLostRace` tests pass unchanged.
4. **The outcome reflects what stands in state after persist.**
   - `blocked = blocked || final.tripped` and `tripped = doc.tripped || final.tripped`. `doc` and `conditions` come from the stored document: the winner's, or a corrupt placeholder.
   - The brief returned only our pre-race view. If a racer's trip won, the clock would have published an unblocked playlist for that minute.
   - The outcome never reports less blocked than was decided. This includes a blind trip that yielded to a newer success: that run still reports blocked, the safe direction.
5. **`conditions.ts` handles the nullable `StoredEvaluation` amounts (from Task 4's fix round).**
   - The brief's `Math.max(e.actual_usd, …)` coerces null to 0, which could silence an alert, and `usd(null)` would crash.
   - Now any null amount or budget, or a budget that is not positive, counts as **over every level**, so both `budget-50` and `budget-80` alert. The amount is rendered "an unknown amount".
   - The key carries `null` for a null budget.
6. **Small wiring adaptations to the current code:**
   - the period is computed once (`periodOrNull`) and shared by `effectiveBudget` and `corruptGuardDoc`;
   - the evaluation's local variable is renamed `p`;
   - the WAF catch is commented as catching any throw (WafError, a DOMException timeout, a TypeError);
   - the meterProblems check stays first in the attempt (Task 4's requirement), so an invalid base budget never reaches a successful `applyAttempt`.

## Review Focus coverage
1. Unreadable state: unknown, no evaluation, no WAF call, no write. Covered by the brief's test. A failed `offair.json` read takes the same path.
2. Overlapping invocations racing: covered by the brief's test plus:
   - the first-creation race, both directions;
   - a deleted doc;
   - a corrupt winner;
   - exhausted retries;
   - spend over blind.
3. A WAF refusal or API failure while blocked: covered by the brief's 403 test, plus a new test for a network `TypeError` and a timeout `DOMException`.
4. Missing secrets:
   - absent secrets: the brief's test;
   - blank or whitespace secrets: new test, zero fetch calls;
   - an invalid budget: new test, zero GraphQL calls;
   - blind after 6 h: the brief's test.

## TDD evidence (full output is in t6-impl.log)
- **RED** `npx vitest run test/bucket.test.ts`: 2 failed, `TypeError: createJson is not a function`. The corrupt-etag pin passed at once: it pins existing behaviour.
- **GREEN** same command: 6 passed.
- **RED** `npx vitest run test/guard.test.ts`: `Cannot find module '../src/guard'`.
- **GREEN** same command: 21 passed. With my tests added (`test/guard.test.ts test/conditions.test.ts`): 34 passed. tsc clean.
- **Full suite** `npm test`: `Test Files 11 passed (11) / Tests 138 passed (138)`. `npx tsc --noEmit`: clean.

## Mutation check
- Run in a `git archive` scratch copy with `node_modules` symlinked, using `python3 -I` with a per-mutant pristine restore.
- A planted SENTINEL throw failed 26 tests, which proves the copy's source was the one under test.
- Each mutant names its predicted test in advance. **All 13 were CAUGHT by the predicted test.**
- M1–M10 cover the deviations: unconditional first create, no spend-over-blind, outcome ignoring stored state, a deleted doc dropped, no create fallback, the brief's null-as-zero conditions, wafProblems ignored, a single persist attempt, a corrupt winner reported untripped, and the WAF catch narrowed to WafError.
- M11–M13 cover core paths: offair dropped from blocked, meterProblems ignored, and a corrupt doc written create-only.

## Self-review and concerns
- **Production behaviour of `etagDoesNotMatch: "*"` is unverified.** It is verified against miniflare's binding. Worth one check at the operator checkpoint: the first guard.json write should succeed. The fallbacks mean a mismatch can only fall back to the brief's unconditional behaviour, never fail to create the document.
- **After a lost race to a tripped winner, the kill switch may lag by up to a minute.** Our run has already reconciled the switch to our (unblocked) decision when the merge reveals the winner's trip. The outcome reports blocked, so the cooperative block (ENDLIST and off-air page) applies that minute, and the next invocation enables the switch. This only happens with overlapping cron invocations. I chose not to add a second Rulesets GET for it, to respect the "one GET per invocation" bound.
- **Persistent write failure (pre-existing behaviour, not changed).** If `guard.json` can never be written while reads succeed and find it absent:
  - every minute starts from a fresh doc, so it evaluates every minute and the blind baseline resets;
  - `guard-write` alerts loudly every run.

  This is a double fault: a failing reading plus failing writes. A successful over-threshold reading still trips and blocks in the same run.
- `WafError` messages carry the zone ID into guard.json's `waf.error` (state/ is private, as you noted). No token is written anywhere.

## Files
- /Users/shawn/projects/llama/.claude/worktrees/playout-phase2/antenna/src/guard.ts (new)
- /Users/shawn/projects/llama/.claude/worktrees/playout-phase2/antenna/src/conditions.ts (new)
- /Users/shawn/projects/llama/.claude/worktrees/playout-phase2/antenna/src/bucket.ts (createJson, onlyIf union)
- /Users/shawn/projects/llama/.claude/worktrees/playout-phase2/antenna/test/guard.test.ts (new)
- /Users/shawn/projects/llama/.claude/worktrees/playout-phase2/antenna/test/conditions.test.ts (new)
- /Users/shawn/projects/llama/.claude/worktrees/playout-phase2/antenna/test/bucket.test.ts, test/support.ts

---

# Fix round 1

**Status: DONE.** Commit `053c5db` fix(antenna): guard review fixes -- budget.json failures alerted, unblock re-check, create-only re-create.

**Tests:** `cd antenna && npm test && npx tsc --noEmit` gives **146 passed in 11 files** (was 138), tsc clean.

## What changed
1. **I1: `budget.json` failures are no longer silent** (`guard.ts`).
   - A get that **throws**:
     - sets `budgetReadFailed`, so `shouldEvaluate` is skipped (`evaluated_at` is not advanced, and the next minute retries);
     - the blind rule, offair, the WAF reconcile and persistence still run;
     - pushes `budget-unreadable` (high, resolvable).
   - A **corrupt** read still evaluates against the base and pushes the same condition.
   - Tests:
     - "a budget.json read that throws skips the evaluation and alerts; the next minute evaluates against the raise". With a $40 raise and FLAT14 usage it does not trip, records `evaluated_at: null`, makes 0 GraphQL calls and raises the condition. The next minute, with the read healthy, it evaluates at $40 without the condition.
     - "a corrupt budget.json evaluates against the base budget and alerts".
   - An `ok` but malformed `budget.json` is still ignored silently by `effectiveBudget` (Task 4 code). This is outside the ruling and unchanged.
2. **M1: a non-evaluating run that turns the switch off now re-checks for a racer.**
   - When the reconcile turned the switch **off** and nothing was persisted, the run does one `head(GUARD_KEY)`. This includes a persist that threw.
   - If the head's etag differs from the one this run read, it re-reads the document. A tripped document, or corrupt bytes as a corrupt placeholder, is folded into the outcome (`blocked: true`).
   - If the head or re-read throws, this minute is reported blocked (`raceUnknown`) and `guard-unknown` is pushed.
   - `waf-corrected` now reads "Kill switch corrected" / "...changed by hand or by an overlapping invocation since the guard last saw it...". The phrase the brief's test checks is kept.
   - Tests:
     - P1 scenario: "a non-evaluating run that turns the kill switch off folds in a racer's newer trip (blocked this minute)". The next run re-enables the switch and its notice carries the new wording.
     - "an unblocking run with nothing newer in state does not fold anything in": a genuine hand toggle, exactly one HEAD, outcome unblocked.
3. **M2: the deleted-document retry is now create-only.** `pre = pre === "absent" ? null : "absent"`: the write is unconditional only after a refused create-only write on a key that is still absent. Tests:
   - "a document deleted between read and write is re-created create-only: a racer that creates it first stands";
   - "only a refused create-only write on a still-absent key falls back to an unconditional write" (a store that returns null for `*`).
4. **M3:** the exhausted-persist window is documented on `persist`. The loop breaks before the final iteration's unused re-read, so exhausting it costs 3 puts and 2 reads.
5. **M4:** test "a throwing offair.json get is unknown: no fetch, no write" (blocked:null, ["guard-unknown"], 0 fetches, 0 puts).
6. **M5:** `parseGuardDoc` (`latch.ts`) now requires `evaluation.at` to be a string (the amounts were already number|null). That covers everything `guardConditions` reads. Tests:
   - `latch.test.ts`: two new bad shapes (`at` missing, `at: 5`);
   - `guard.test.ts`: "a hand-edited guard.json the alert conditions cannot read is corrupt (a spend trip), not a throw".
7. **M6:** removed `racerPut`'s unused `realPut` return, and declared `writeRaw2` before use.

## Mutation proof
- Run in a fresh scratch copy (`git archive HEAD antenna`, HEAD = 053c5db, `node_modules` symlinked), with vitest run from the scratch dir via `python3 -I`. Full output is in t6-impl.log.
- **Sentinel throw:** 34 failing, so the copy's source was the one under test.

| Mutant | Predicted red test | Result |
|---|---|---|
| F1a: a budget throw no longer skips evaluation | "a budget.json read that throws skips…" | CAUGHT (predicted) |
| F1b: corrupt budget pushes no condition | "a corrupt budget.json evaluates against the base budget and alerts" | CAUGHT (predicted) |
| F1c: budget throw pushes no condition | "a budget.json read that throws skips…" | CAUGHT (predicted) |
| F2a: no unblock re-check | "a non-evaluating run that turns the kill switch off folds…" | CAUGHT (predicted); also fails the one-HEAD test |
| F2b: old waf-corrected wording | same test | CAUGHT (predicted) |
| F5: offair get failure swallowed as absent | "a throwing offair.json get is unknown" | CAUGHT (predicted) |
| FM2: deleted document re-created unconditionally | "…re-created create-only…" | CAUGHT (predicted) |
| FM5: `evaluation.at` unchecked | "a hand-edited guard.json…" | CAUGHT (predicted); also fails the latch nested-shapes test |

## Residual (noted, not fixed)
M1's re-check only runs when nothing was persisted. The residual case:
1. A racer enables the switch before our reconcile, and our reconcile turns it off.
2. Our etag-conditional write still succeeds, because the racer has not written yet.
3. The racer then writes. Its write loses the etag race to ours and merges its trip.

Our outcome is then unblocked for that minute. The trip is in state and the next run re-blocks. Closing this would need our own written etag (`putJson` returns a boolean) or a HEAD on every unblocking write. It is narrower than P1 and bounded to one minute.
