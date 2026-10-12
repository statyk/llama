# Editor handback: phase-2 plan, review decisions applied

Plan edited in place: /Users/shawn/projects/llama/docs/superpowers/plans/2026-10-11-playout-phase2.md (not committed). Line count went from **7517 to 6569**. Backup of the pre-edit plan: scratchpad/plan-review/plan-before-edit.md.

I rebuilt the plan's end state in scratch and ran it. Every whole-file code block in the plan is byte-identical to that build. Results:
- **antenna:** 13 files, 137 tests, `tsc` clean.
- **transmitter:** 346 tests on both 3.11 and 3.14.
- **Task 18 variant:** 139 tests. Mutation-checked: the late-invocation test fails without the new `max(...)`.

The scratch trees are scratchpad/edit/repo and edit/la. The plan's self-review section now states these numbers.

## Not applied cleanly (needs your call)

1. **C-12, the `lead-low` half: not implemented.** The rule wanted is "stay quiet until the lead has reached the floor once in this run". The reviewer's proxy for that was "the horizon's span `last − first` is below the floor". That proxy fails because prune moves `horizon.first` to about 10–20 min behind now while transmitter runs, so the span is always about the lead plus 20 min:
   - **On a fresh start** it would still alert briefly, and then send a "resolved".
   - **On a running hugo whose lead drains** (render slower than real time) it would fire for about 15 min, then suppress itself and send "resolved".

   No stateless rule can tell a fresh run from a draining one using the horizon. The fix needs persisted state, which is a design decision. Two options:
   - accept the fresh-start alerts and say so in the runbook;
   - persist a per-run "floor reached" marker, for example in `guard.json`, reset when `first` jumps past the last-seen `last` + 1.

   R6 and `lead-low` are unchanged. The other half of C-12 is applied: the runbook says a `guard-stale` alert is expected if transmitter is upgraded first.
2. **C-6, the `written_at` clamp: applied as written, but it does not fix what it targets.** `effectiveBudget` now clamps `writtenAtMs` to now, and a test pins that. But `shouldEvaluate` checks `writtenAtMs > evaluated_at`. A future-dated `written_at` clamps to now each minute, which is always later than the previous minute's evaluation. So the guard still evaluates every minute until `written_at` passes. That costs only unbilled GraphQL calls. A real fix would be, for example, to ignore a future `written_at` (the raise then waits for the normal 15-min cadence). The `blind` merge half of C-6 is applied properly: `mergeLostRace` is pure and exported, with two tests.
3. **C-1 is moot.** The fallback-length lookup existed only for A1 (Task 12's `_fallback_len` and `next_horizon_disc`). Nothing in the remaining plan looks up a fallback that can fail after a PUT; the existing `fallback_version is None` refusal is untouched.

## Contradictions resolved (my choice; easy to revert)

- **C-5 vs A4's ordering: I moved a task.**
  - **The problem:** the lookahead trigger is now `lagMs + guardMs`. `guardMs` exists only once phase 2 is deployed, but the lookahead task ran before the deploy checkpoint.
  - **What I did:** the conditional lookahead now runs after the deploy (old 19 is new 18; old 20 is new 17).
  - **Its checkpoint now asks for:** a day of phase-2 clock lines.
  - **New final step:** a human checkpoint where you deploy it (`npx wrangler deploy`).
  - **Runbook checklist:** keeps the phase-1 lag row and adds a "lag + guard time" row.
- **A-4 ("the sender may be a committed var") vs A-2 ("keep a test that wrangler.jsonc contains no email address").** I kept `ALERT_EMAIL_FROM` as a Worker secret holding `alerts@lma-radio.com`, so the strict no-address test holds. The address now appears in the plan and the runbook. Stakes gained one sentence allowing it there, and the runbook's address-grep step allows it.
- **A-2 removes `raw.d.ts` but keeps the test that reads `wrangler.jsonc`.** The test still uses the `?raw` import. `tsc` now learns that import from `"vite/client"` added to `tsconfig.json` `types`. No declaration file is needed; I verified `tsc` is clean.

## Each decision and where it went (new task numbers)

- **A-1:**
  - The A1 amendment became a one-paragraph documented limitation.
  - Old Tasks 11 and 12 are removed entirely: horizon `disc`, `disc.py`, the vectors file, the fallback `len`, `next_horizon_disc`, and the A1 tests.
  - The transmitter-first deploy order is gone (section 6 now says either order).
  - The runbook's section 7 lists the VLC limitation.
  - The A1 checklist item and the "horizon carries disc" step are removed.
  - Task 19 writes the limitation as a spec note and in CLAUDE.md.
  - Deferred items Minor 6 and D5 moved to "left deferred", with reasons.
  - The File Structure, model-hint table, dependencies, self-review and type-consistency sections are updated.
- **A-2:**
  - A3 is rewritten: an unrestricted binding, with the destination only in the `ALERT_EMAIL_TO` secret, and the rationale stated.
  - Task 10 is rewritten: the binding, `vite/client` types, `deploy-assets` without `index.html`, and a new `test/wrangler-config.test.ts` (no address, no `account_id`, binding unrestricted and bound).
  - Removed: `deploy.mjs`, `deploy-config.mjs`, `raw.d.ts`, `wrangler.deploy.json`, the `.gitignore` entry and every `npm run deploy`/`.env ALERT_EMAIL_TO` mention.
  - The runbook and checklist use `npx wrangler deploy [--dry-run|--var]`.
  - The "binding is pinned" checklist item is removed.
- **A-3:** the amendments and rulings headings now say "approved by the operator 2026-10-12".
- **A-4:** the sender is in Operator inputs, A3, the runbook (6.2, 6.3) and Stakes.
- **A-5:** the alert defaults are in Operator inputs, referencing R4, R6, R13 and R16.
- **B-1:** a comment above `USAGE_QUERY` gives the measured limits, plus an A5 bullet and a Task 3 note.
- **B-2:** the two new names are added to `CLASS_B`, with a test covering all 12 measured names. The action-type list is in A5. Unknown types are still priced as Class A.
- **B-3:** the wording in A2, Task 11 and `player.js`, and Task 14 and `deadclock.py`, now says "a cache hit; the edge refetches at most every 5 s, whoever asks". The measurement is in A5.
- **B-4:** the plan had no git-broken caveat and no "unverified" list, so nothing needed dropping.
- **C-2:**
  - Runbook section 4 step 4: the Mac-side `state/offair.json` lever, honoured within a minute.
  - The emergency order for a broken Worker: remove the cron trigger, then enable the kill switch by hand.
  - Section 7 points to both.
  - The guard raises a `waf-corrected` alert when a change undoes a hand toggle (`r.changed && prev.waf.enabled === r.enabled`), deduped as usual, with one test.
  - Checklist: a "Mac-side repeat" and a "dashboard toggle undone and alerted" item.
  - R13 and R14 are updated.
- **C-3:** `guard_stale_minutes` defaults to 45. A `TransmitterConfig` validator requires at least `guard_check_minutes + 16`. Tests cover both bounds, and the template is updated.
- **C-4:** a separate unexpected-403 counter with `forbidden_checks = ceil(guard_check_minutes) + 2` (17), set in `open_monitor`. Tests are updated, and R4 is updated.
- **C-5:**
  - `flush` moved to the `finally`, after the loop, and the test now asserts "after the last write".
  - `ClockResult.guardMs` is on the clock line, with tests.
  - The WAF timeout is now 5 s.
  - The A4 trigger is `lagMs + guardMs`, and the off-air `offairSeqMs = max(scheduled + loopMs, startedMs + lookahead·d)` in Task 18.
- **C-6:** see "Not applied cleanly" above.
- **C-7:** `effectiveBudget(..., periodEndMs)` ignores a raise that outlives the period and reports it in `invalid`. The guard alerts `budget-file-invalid`, with tests. The runbook says to raise above the projected figure.
- **C-8:** a new `once` flag on alert conditions, honoured by `planAlerts`. The budget alert keys become `budget-50:<period>:<budget>`, never repeated or resolved, and remembered for 35 days. A once alert that fails to send is retried. Tests cover this.
- **C-9:** `alerts.LEVEL_CODES` holds R16's five codes. Any other code expires from `active` once `repeat_s` passes with no new alert. `status` uses `alerts.active_codes`. Tests cover this, and R16 is updated.
- **C-10:** `publish_all(..., notify)` pings `WATCHDOG=1` after each batch, and the runner passes its notifier. There is a test with a fake notifier, and the runner's ping count is updated to 4. R15, the unit comment and the `sdnotify` docstring are updated.
- **C-11:** `BILLING_ANNIVERSARY_DAY = "11"` is a committed var in `wrangler.jsonc`. It is removed from the secrets lists, `GuardEnv` comments and the explicit problem check. A bad value still fails every evaluation through `billingPeriod`, with a test. R11 and R12 are rewritten.
- **C-12:** the runbook half only; see "Not applied cleanly" above.
- **C-13:** runbook section 7 has the (a) and (b) limitations as written.
- **D-1:** no change.
- **E-1:** a scan finds only `example.*` placeholders and `alerts@lma-radio.com`: no IDs, tokens or real addresses.

## Removed, and the renumbering

Old Tasks 11 (antenna discontinuity numbering) and 12 (transmitter horizon `disc`) are deleted. Old Task 10 is replaced in content but keeps its number.

| Old | New |
|---|---|
| 0–10 | unchanged |
| 13 | 11 |
| 14 | 12 |
| 15 | 13 |
| 16 | 14 |
| 17 | 15 |
| 18 | 16 |
| 20 | 17 (runbook/deploy checkpoint) |
| 19 | 18 (conditional lookahead, moved after the deploy) |
| 21 | 19 |

Every cross-reference is updated: amendments, rulings, Review Focus, File Structure tags, the model-hint table, dependencies, interfaces, checkpoints, deferred items and self-review. The review gate after Task 8 is unchanged.

## Gaps filled (my choices)

- **Budget-level key includes the budget**, not just the period. Without it, the checklist's $5.50 test trip would use up the period's real 50% and 80% alerts.
- **`budget-file-invalid` uses a plain key with `once`.**
- **The `once` memory is 35 days**, longer than a billing period.
- **Event codes expire on strict `>` `repeat_s`**, which keeps the existing repeat test passing.
- **Two checklist items added:** the Mac-side off-air write and the dashboard toggle.
- **Dead-clock `guard-stale` timing in the checklist** is now "within about an hour".
- **Task 18's Step 2 states the truth:** the late-invocation test passes until the lookahead is implemented, and then it guards against the regression.

## Task boundaries reshaped beyond the A1 removal

- **The conditional lookahead now follows the deploy checkpoint** and gains its own deploy step (C-5).
- **Task 10 is a different task:** binding plus test plus `deploy-assets`, with no deploy script.
- **Small scope additions inside existing tasks:**
  - Task 4: `effectiveBudget` signature;
  - Task 6: `mergeLostRace`, `waf-corrected`, `budget-file-invalid`;
  - Task 8: `guardMs` and flush placement;
  - Task 9: `once`;
  - Task 13: validator and `active_codes`;
  - Task 14: 403 counter;
  - Task 15: `publish_all` ping;
  - Task 16: `active_codes`.

## Scratch hygiene note

`proto/repo/antenna` is a symlink to `proto/antenna`, and my first copy followed it. That briefly modified `proto/antenna` in place. I restored it from `proto/antenna-la` and from the plan's original code text, and verified the result: 13 files, 132 tests, `tsc` clean, the same as before. The repo's `node_modules` and `git status` were not touched; only the plan file changed.
