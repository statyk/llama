VERDICT: NEEDS FIXES

### Findings

#### Critical
None.

#### Important

**I1. The scheduled-handler tests run the real `guardStep` with the real global `fetch`. Network isolation depends only on the test env having no CF_* secrets, and wrangler loads secrets into that env from `antenna/.dev.vars`, `.env` or `.env.local`. This is plan-mandated: the test file is the brief's, verbatim.**
`antenna/src/index.ts` (`fetchFn = (input, init) => fetch(input, init)`) together with `antenna/test/clock.test.ts:320ff` ("runs the guard then one clock invocation…" and "emits the per-invocation clock line even when runClock throws").
- **Why it matters:** the Global Constraint says "No test may reach the network; every fetch is injected". These two tests break the letter of that rule today. They also break its intent the moment `antenna/.dev.vars` or `antenna/.env` holds the CF_* secrets, which is a natural step for local `wrangler dev` or for Task 17's live checks.
- **How the env gets the secrets:** `@cloudflare/vitest-plugin` builds the test env through wrangler's `getVarsForDev`. Wrangler 4.149 loads `.dev.vars`, or, when that is absent, `.env`/`.env.local`, because `CLOUDFLARE_LOAD_DEV_VARS_FROM_DOT_ENV` defaults to true. Everything it loads becomes a `secret_text` binding.
- **Proven in a scratch copy:** a `.dev.vars` containing only `CF_ACCOUNT_ID=dummy` made the handler test fail with `expected 'secret CF_ANALYTICS_TOKEN is not set' to match /CF_ACCOUNT_ID/`. So the file reaches `guardStep`'s env.
- **What happens with all four secrets set:** `npm test` would make a real GraphQL POST and a real Rulesets GET. It would then PATCH the production kill switch to match the miniflare bucket's "not blocked" state. That would disable a real block, for up to a minute, until the production clock re-reconciles it. The test's `/CF_ACCOUNT_ID/` assertion fails only after those calls have been made.
- **Not a live problem today:** the main checkout's `antenna/.env` holds `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_ANALYTICS_TOKEN` (names only were inspected). These do not match the `CF_*` names, so nothing is reached now. The protection is one rename away from failing.
- **Fix (either or both):**
  - In both handler tests, pass an env with the four `CF_*` keys forced to `undefined`.
  - In both handler tests, also `vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in tests"))`. This works because `fetchFn` resolves the global `fetch` at call time. Then assert the spy was never called.

**I2. The clock hands the alert sink a partial condition set on every early or failed path, and Task 9's `planAlerts` resolves any absent key aloud at once. The result is a false "resolved" on the spend surface. This is plan-mandated and spans tasks 8 and 9.**
`antenna/src/clock.ts`: the unknown-outcome return (~l.196), the guard-crash path, the `horizon-missing`/`horizon-refused` returns, and any throw from `readInputs`/`gridOf` (all flushed through the `finally` at l.275).
- **Why it matters:** the plan's Task 9 `planAlerts` sends `kind: "resolved"` immediately for every active resolvable key missing from the batch. The 15-minute cooldown only suppresses the re-alert afterwards.
- **Example:** a single transient R2 read failure (guard returns `blocked: null` with only `guard-unknown`), or a single guard throw (only `guard-crashed`), while the station is tripped sends "resolved: Station blocked: spend" (`tripped-spend` is urgent and resolvable). It also sends resolutions for `waf-api`, `lead-low`, `horizon-refused` and `index-write`. When those conditions return within 15 minutes, no new alert goes out, so the operator holds a false all-clear until the 6 h repeat. The station stays blocked, so no money is at risk, but the operator's picture of the spend surface is wrong.
- **Same mechanism in reverse:** after a `readInputs` throw (for example a corrupt `epoch` reaching `gridOf`), the guard's conditions are flushed and every clock condition is resolved.
- **Fix:** give the sink a scope. For example, `alerts(conditions, nowMs, { complete: boolean })`, where `complete` is false on the unknown/crash/throw paths and `planAlerts` skips its resolution pass for an incomplete batch. Alternatively, resolve only after a key has been absent for the cooldown. Settle this with Task 9's design; Task 8 owns the flush contract.

#### Minor

- **M1. Flushing on a throw is unpinned.** `clock.ts:275`. A scratch mutant that suppresses the flush when an exception propagates (`catch (e) { flushed = true; throw e; }`) survived all 24 clock tests. The brief requires the flush "at an early return", and a throw is the path where the guard's conditions matter most (the clock line is the only other trace). Add a test where `failGets` on `state/horizon.json` makes `readInputs` throw, then assert that the guard's conditions still reach the sink and `runClock` rejects.
- **M2. `lead-low` suppression is pinned only against tripped-vs-onAir.** `clock.ts:229`. A mutant `!outcome.blocked` (suppressing during a manual off-air too) would survive, because neither test uses an off-air-but-not-tripped guard. transmitter keeps publishing while off-air (`publish.py:141` stops only on `tripped`), so R6 wants the alert there. Add one `guardSays(true, false)` case to the lead-floor test.
- **M3. `horizon-missing` misnames a corrupt horizon.** `clock.ts:214` says "state/horizon.json is absent … transmitter has not published". `readJson` maps a JSON parse failure to `null`, so a corrupt horizon raises this default-priority message with the wrong cause. Either distinguish absent from unparseable in `readInputs`, or word the message "absent or unreadable".
- **M4. No alert condition for a `readInputs` throw.** As the implementer notes, an R2 get failure on `state/horizon.json` or the fallback index propagates out of `runClock` and shows only as the clock line's `error`. That matches the brief and phase 1, and hugo's dead-clock monitor (R4) backstops a stale `live.m3u8`. It is still the one cloud-side failure with no condition key, and it interacts with I2.
- **M5. Fields missing from the clock line on a throw.** On a `runClock` throw, `index.ts`'s clock line carries no `guardMs`/`blocked`, because `result` is undefined. Amendment A4 adds `guardMs` to the lag analysis. A guard that ran long right before a throw is invisible there.
- **M6. Unannounced change to `worker-configuration.d.ts`.** The regenerated file (deviation 1) is outside the brief's file list. The diff is limited to the six vars and the hash line, which looks right; the orchestrator should know it changed.

### ⚠️ Cannot verify from diff
- How Task 9 interprets an absent key (I2): the resolution semantics are in the plan's Task 9 code, not in this diff. The Task 9 reviewer should check the partial-batch case.
- Whether `guardStep`'s own `finally` (blind rule and WAF reconciliation) still runs when it throws. That is Task 6 code; this diff only treats a throw as unknown, which is correctly fail-closed for the clock's writes.
- The cost of `reconcileIndex` (one HEAD, at most one PUT per invocation, only on a sha256 mismatch) is Task 7's. Outside `MAX_PUTS`, it is bounded at 1 extra Class A write per invocation.

### Strengths
- **Guard first, structurally.** `deps.guard()` is the first I/O in `runClock`. Only the console-only loop-clamp log precedes it. The test "runs the guard before reading or writing anything" pins both "nothing read before the guard" and "index HEAD/PUT is the first bucket activity".
- **Unknown and crash both fail closed.** A `null` outcome and a throwing guard both write nothing: no index, no playlist. A crash becomes an urgent `guard-crashed`. Both paths are tested with `bucket.puts() === 0`.
- **index.html failures are isolated.** A HEAD or PUT failure is caught, becomes `index: "failed"` plus `index-write`, and the playlist still runs. Both the HEAD and PUT variants are tested; the HEAD one is the implementer's addition.
- **Flush ordering.** The flush is idempotent, in `finally`, after the last boundary write. A failure in the sink itself is logged and does not mask the original exception. The ordering test asserts the sink call is the very last event.
- **`offair.json` read removed from `readInputs`.** The blocked state now has one owner, the guard, which removes a second, inconsistent reader of R2-state.
- **All phase-1 spend bounds are still enforced and pinned:**
  - `MAX_PUTS = 10` and the `putCap` sweep;
  - the `d ≠ 10.24` refusal (zero playlist PUTs, never sleeps, now also an alert);
  - the 75 s clamp (`LOOP_SECONDS=900` → 8 PUTs, ends by +75 s);
  - `max-age ≥ 1`.
  The refusal and missing-horizon tests now count only playlist PUTs, which is correct now that index.html is written before them.
- **Public-repo hygiene.** `wrangler.jsonc` adds only plain vars; the secrets are named in a comment, with no values and no account_id. `BILLING_ANNIVERSARY_DAY` is a var, per R12. No address appears.
- **Implementer process.** They ran mutation checks with a predicted red test for each mutant.

### Checks run
- **Risk: tests reach the network through the handler path (I1).**
  - Read `index.ts` and the handler tests.
  - Inspected the installed wrangler 4.149 `getVarsForDev`: `.dev.vars`, else `.env`/`.env.local`, are loaded when `CLOUDFLARE_LOAD_DEV_VARS_FROM_DOT_ENV` is at its default of true. `@cloudflare/vitest-plugin` 1.4.0's pool uses that path.
  - Scratch mutant M2: added `antenna/.dev.vars` with `CF_ACCOUNT_ID=dummy-not-real`, deliberately without the token pair so no network call was possible. Predicted the handler test would go red; it did: `1 failed | 23 passed`, with `expected 'secret CF_ANALYTICS_TOKEN is not set' to match /CF_ACCOUNT_ID/`.
  - Checked the main checkout's `antenna/.env` key names only (values redacted): `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_ANALYTICS_TOKEN`.
- **Risk: false resolution from partial batches (I2).** Read the plan's Task 9 `planAlerts` (absent active resolvable key → immediate `resolved`). Listed the guard's condition keys in `guard.ts` and `conditions.ts`: `tripped-spend`, `tripped-blind`, `waf-api` and others are resolvable.
- **Risk: the throw path loses the flush (M1).** Scratch mutant M1, `} catch (e) { flushed = true; throw e; } finally {`. Predicted it would survive; it did (24/24 passed).
- **Risk: `guardConfigFromEnv` throws on bad vars, so a guard crash would bypass the blind rule.** Read `guard.ts:67-89`: it collects problems and never throws. No issue.
- **Risk: lead-low suppression scope (M2).** Checked `transmitter/publish.py:141-152`: publishing stops only on `tripped`, and an unreadable guard.json is treated as tripped.
- **Focused test, for output noise:** `cd antenna && npx vitest run test/clock.test.ts` → `Tests 24 passed (24)`, with no stderr noise.
- **Scratch hygiene.** Scratch copies were made by `git archive 4d1858b antenna | tar -x` under the session scratchpad, with node_modules symlinked and vitest run from the scratch dir. The live worktree was not modified (`git status` clean).
