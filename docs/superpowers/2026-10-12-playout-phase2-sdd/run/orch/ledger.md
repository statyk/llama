# SDD ledger — plan: docs/superpowers/plans/2026-10-11-playout-phase2.md
Orchestrator: peer session 1e675379-4a60-4867-9819-08b2ea8e3082; parent llama-ba. Start 2026-10-12T01:50:54-0400 at ccf0f16.
Spec: docs/superpowers/specs/2026-10-09-playout-design.md (Stakes governs; spend is the strict surface).
Gates: STOP after Task 8 for llama-ba's go; STOP at Task 17 HUMAN CHECKPOINT after final Fable review.
Brakes: 5h 85%, weekly 60%.

## Escapes
(none)

## Log
- 2026-10-12T01:50:54-0400 start; meter 5h 19% (resets 03:19), week 21%.
cron tick 42970d89 armed 13,43

## Pre-flight scan (cross-task interfaces; from each task's Files/Interfaces + targeted greps)
| pair | shared surface | produces → consumes | finding |
|---|---|---|---|
| T1→T8 | clock.ts, clock.test.ts | T1 moves bucket types to bucket.ts + re-exports; T8 replaces clock.ts whole | T8's text keeps `export { BucketLike, r2Bucket, StoredObject } from "./bucket"` — consistent |
| T1→T3 | test/support.ts | T3 appends usageResponse | append-only, ok |
| T2→T3/T4/T6 | pricing.ts | OpCounts/Reading/Evaluation/overThreshold | names agree across Interfaces |
| T4→T6→T12 | GuardDoc (guard.json schema) | T12 reads tripped/reason/period/evaluation/waf/... | field lists agree (snake_case doc) — watch at T12 review |
| T6→T8→T9 | AlertCondition, ClockDeps.alerts | T9 alertSink plugs into T8's alerts seam | agree |
| T8→T9→T10→T18 | wrangler.jsonc, env.ts, index.ts | sequential edits | T8 replaces, T9/T10/T18 modify — sequential, ok |
| T7→T10/T11 | package.json, public/*, pages.ts | T11 edits public/*.js only; pages.ts bundles index.html+offair.html only | T11 cannot stale pages.ts — ok |
| T9 ∥ T11 | same worktree, npm test | T11 independent | if run concurrently: commit by explicit paths only, never `git add -A` (Ruling below) |
| T12→T16 | cli._cloud, cloudstate | T16 reuses | agree |
| T13→T14→T15→T16 | service.py, cli.py, alerts.py | sequential | agree |
| T17 | docs only | consumes all names | checkpoint |
Per-task self-consistency rows: NOT re-derived here — the plan went through two independent reviews (review-A-opus, review-B-fable) + editor pass (docs/superpowers/2026-10-12-playout-phase2-plan-review/); each task reviewer checks its own task's tests-vs-code.
- Ruling: per-task self-consistency taken from the plan review record rather than re-derived by the orchestrator — bounds orchestrator context on a 6.5k-line plan — if wrong, a task-internal contradiction surfaces at implementation as BLOCKED/NEEDS_CONTEXT instead of before dispatch.
- Ruling: separate spec-compliance and code-quality reviewers (both Opus) per task, per llama-ba's brief, rather than the skill's single combined task reviewer — the brief names both — costs one extra Opus review seat per task.
- Ruling: briefs/review packages live in $D/orch/pkg/ (my own dir), not the skill's default workspace — keeps $D the one tree — none.
- Task 0: complete (no commit). Baseline @ ccf0f16: py3.14 2462 passed/7 deselected; py3.11 transmitter 306; antenna 41 tests (3 files) + tsc clean; Debian-12 gate 306. Import paths resolve in worktree (both venvs). .venv311/ exclude line present.
T1 BASE=ccf0f16
- 2026-10-12T01:59:05-0400 T1 implementer dispatched: Sonnet, agent ac9987b12ab454bf3, task dir t1-impl
- 2026-10-12T02:01:05-0400 T1 implementer DONE: f13191c (antenna 51 tests/5 files, tsc clean). Review pkg orch/pkg/t1-review.diff (ccf0f16..f13191c).
- 2026-10-12T02:01:05-0400 T1 spec reviewer: Opus (ae613f6d470db1239, t1-rev-spec); quality reviewer: Opus (afa03793506a238e1, t1-rev-qual)
- 2026-10-12T02:02:13-0400 T1 spec review: APPROVED (0 findings; 2 ⚠️ cross-task notes: MemoryBucket semantics verbatim from brief; miniflare vs prod R2 onlyIf parity = operator checkpoint). sha256 ff4e97854d29f930
- 2026-10-12T02:03:20-0400 T1 quality review: APPROVED, 0 Crit/0 Imp, 7 Minor. sha256 8adad971871a4d66
Task 1: minor (deferred): putJson etag-truthiness → unconditional create when guard.json absent; first-creation race could lose a trip (carry to Task 6 implementer + reviewers)
Task 1: minor (deferred): no test pins that a corrupt read carries the etag (Task 6 relies on it) (carry to Task 6)
Task 1: minor (deferred): billingPeriod(NaN) returns NaN period instead of throwing — latent, could read as "new period" under R3
Task 1: minor (deferred): fakeFetch ignores Request-object input / non-string bodies — latent
Task 1: minor (deferred): MemoryBucket failGets also fails head; puts() counts precondition-failed puts
Task 1: minor (deferred): clock.test.ts playlistPuts duplicates MemoryBucket.puts
Task 1: minor (deferred): period tests lack a leap-year case
Task 1: complete (commits ccf0f16..f13191c, review clean)
- 2026-10-12T02:04:07-0400 T2 BASE=f13191c; implementer: Opus (ac48015c149fa4f35, t2-impl). Meter 5h 20%.
- 2026-10-12T02:05:58-0400 T2 implementer DONE: 2d9c7f2 (antenna 58 tests, tsc clean); concern: NaN in reading/budget makes overThreshold false (relies on T3/T4 validation)
- 2026-10-12T02:06:19-0400 T2 spec reviewer: Opus (ab3d41962668254ee); quality reviewer: Opus (a15f212b0d1b21633)
- 2026-10-12T02:07:39-0400 T2 spec review: APPROVED, 0 findings; ⚠️ NaN fails open in overThreshold (relies on T3/T4 validation — check at T3/T4/T6). sha256 a36aa4bdefb9ea92
- 2026-10-12T02:09:32-0400 T2 quality review: NEEDS FIXES — 1 Important (plan-mandated): Class B + Workers projections untested (mutants M1/M4 survive; fail-open). 5 Minor. sha256 8af1b066c051c750
- Ruling: T2 Important (plan-mandated test gap) enters the fix loop — the plan's test is named "each meter" and the Stakes forbid a silent fail-open on spend; adding assertions changes no plan behaviour — cost if wrong: a few extra test lines.
- Ruling: fold T2 Minors 1 (overThreshold written in negated form so NaN/non-finite trips — fail closed) and 2 (pin the remainingMs clamp with nowMs past period end) into fix round 1 — both are fail-open holes on the strict spend surface and each is one line; deviates from the plan's verbatim code for overThreshold, behaviour identical for finite inputs — cost if wrong: one deviation the final reviewer must re-read.
Task 2: minor (deferred): analytics lag window counted in neither term (~0.01%; projection not a strict upper bound for op counts)
Task 2: minor (deferred): METERS/PRICES exported mutable (not readonly/frozen)
Task 2: minor (deferred): ALERT_LEVELS untested here (consumed by T6)
- 2026-10-12T02:09:46-0400 T2 fix round 1 dispatched: resumed implementer Opus (ac48015c149fa4f35); FIX_BASE=2d9c7f2; sentinel t2-impl/fix1-done
- 2026-10-12T02:12:19-0400 T2 fix1 landed f2ca117 (61 tests; 4 mutants each red on predicted test). Re-review: Opus (a01fc2f27ec6554db, t2-rerev1)
- 2026-10-12T02:14:02-0400 T2 re-review: ALL ADDRESSED (3/3), no new breakage. sha256 38585a797183b1a7
Task 2: fix round 1/5 (3 addressed, 0 open — per-meter projection test; NaN fails closed; clamp pinned; commits 2d9c7f2..f2ca117)
Task 2: minor (deferred): negated overThreshold not fail-closed for +Inf budget / -Inf actual|projected (unreachable: inputs validated finite upstream)
Task 2: complete (commits f13191c..f2ca117, review clean)
- 2026-10-12T02:14:39-0400 T3 BASE=f2ca117; implementer: Opus (a817a244f19f2f4df, t3-impl). Meter 5h 20%, week 22%.
- 2026-10-12T02:18:47-0400 T3 implementer DONE: 5a4ebcf (antenna 69, tsc clean); 3 deviations (malformed errors field fails; null-safe rows; every-field validation test). Concerns: metadataSize ?? 0; empty dataset = zero usage.
- 2026-10-12T02:19:08-0400 T3 spec reviewer: Opus (ad79115168f6f38e9); quality reviewer: Opus (a5756aea82e5ac93b)
- 2026-10-12T02:20:45-0400 T3 spec review: APPROVED, 1 Minor (error fallback text JSON.stringify vs "error"); all 3 deviations accepted. sha256 0268672fb19430ca
Task 3: minor (deferred): errors-without-message fallback prints JSON instead of "error" (undeclared, harmless)
- 2026-10-12T02:20:55-0400 T3 quality review: APPROVED, 0 Crit/0 Imp, 6 Minor. sha256 68ea3abf31189749
Task 3: minor (deferred): 15 s GraphQL timeout unpinned (fakeFetch does not record init.signal) — a hung POST delays the whole invocation
Task 3: minor (deferred): pricing-page-only Class A types (CopyObject, UploadPart, ...) unpinned in class sets
Task 3: minor (deferred): missing actionType reported as "" in unknown_action_types (hard to read)
Task 3: minor (deferred): empty dataset reads as zero usage (storage [] ~45 min after period start; negligible)
Task 3: minor (deferred): metadataSize ?? 0 vs payloadSize throws — asymmetry deserves a comment
Task 3: minor (deferred): brief's five-mode error test lacks per-case labels
Task 3: complete (commits f2ca117..5a4ebcf, review clean)
- 2026-10-12T02:21:11-0400 T4 BASE=5a4ebcf; implementer: Opus (af10cc216c18fd90d, t4-impl)
- 2026-10-12T02:25:38-0400 T4 implementer DONE_WITH_CONCERNS: 52cc6f0 (antenna 88, tsc clean); deviations: finiteOrNull tripped_budget_usd; stricter parseGuardDoc nested fields. Concerns: future written_at → per-minute evaluation; spend trip with null tripped_period_start clears on first under-threshold reading.
- 2026-10-12T02:26:01-0400 T4 spec reviewer: Opus (a4e0b1ceab3a59f77); quality reviewer: Opus (abbf5bbb597f5ef2e)
- 2026-10-12T02:29:17-0400 T4 spec review: APPROVED, 3 Minor (future written_at → per-minute GraphQL POST, breaks 1/15min bound; null tripped_period_start clears weakly in double fault; T6 corrupt-message advice wrong when budget null). Deviations 1+2 accepted. sha256 d49f47c6061e9d5c
- 2026-10-12T02:30:47-0400 T4 quality review: NEEDS FIXES — 1 Important (re-trip re-anchoring to new period unpinned; mutant M1 survives; oscillation on strict surface). 8 Minor. sha256 8a789c37ad4dd833
- Ruling: T4 Minor q1/s2 (spend trip with tripped_period_start null clears on first under reading) fixed in round 1 — when prev is spend-tripped with a null period, adopt the current period and stay tripped — R2 says spend clears only with a raise or a new period — cost if wrong: a double-fault trip lasts until a raise or next period.
- Ruling: T4 Minor q2/s3 (null tripped_budget_usd can never be cleared by a raise, yet T6's alert advises --raise-to) fixed in round 1 — a spend trip with null tripped_budget_usd counts as raised when the effective budget exceeds the attempt's finite baseBudgetUsd (i.e. an honoured raise is present) — keeps the operator's documented recovery working; R11 still blocks evaluation while the base is invalid — cost if wrong: one more clear path, gated on a successful under-threshold reading with an operator raise.
- Ruling: T4 Minor q3/s1 (future written_at → evaluation every minute, breaks the Global Constraint "one GraphQL POST per 15 minutes") fixed in round 1 via shouldEvaluate's raise trigger requiring budgetWrittenAtMs < nowMs (spec reviewer's option a; no GuardDoc schema change) — R1's "at once" holds for any raise written in the past — cost if wrong: a clock-skewed raise waits ≤15 min.
- Ruling: T4 Minor q5 (blind rule: a future last_success/since postpones the blind trip indefinitely — fail-open) fixed in round 1 — a baseline more than 15 min ahead of now is treated as unparseable (blind trips) — cost if wrong: a Worker clock fault >15 min trips blind (loud, fail-closed).
- Ruling: T4 Minors q4 (pin tripped_at reset on re-trip) and q6 (type evaluation actual/projected/budget as number|null to match the parser) folded into round 1 — one assertion and a type change; q6 feeds T6/T12 readers — cost if wrong: none material.
Task 4: minor (deferred): parseGuardDoc returns the raw object — unknown keys carried forever (note for T12)
Task 4: minor (deferred): malformed raise (string budget_usd, bad expires, lowering raise) ignored silently — only "outlives period" sets invalid
- 2026-10-12T02:31:04-0400 T4 fix round 1 dispatched: resumed implementer Opus (af10cc216c18fd90d); FIX_BASE=52cc6f0; sentinel t4-impl/fix1-done; 7 items
- 2026-10-12T02:35:51-0400 llama-ba instruction: Docker is being shut down. Before any Debian-12 gate (Task 12+), check `docker info`; if it fails, STOP and ask llama-ba (do not skip the gate). Implementer dispatches for T12+ must say: check docker info first; if it fails, report BLOCKED (do not skip).
- 2026-10-12T02:35:57-0400 T4 fix1 landed c04c5ab (antenna 94; 8 mutants each red on predicted test)
- 2026-10-12T02:36:16-0400 T4 re-review: Opus (a78fc27713e1bb685, t4-rerev1)
- 2026-10-12T02:40:24-0400 T4 re-review: ALL ADDRESSED (7/7), no new breakage; interaction check: no new unblock-while-over path. sha256 e8da027908e286a7
Task 4: fix round 1/5 (7 addressed, 0 open — re-trip anchoring pinned; null period adopts; null budget raised-clear; future written_at cadence; future blind baseline; tripped_at pinned; number|null types; commits 52cc6f0..c04c5ab)
Task 4: minor (deferred): StoredEvaluation.base_budget_usd typed number but unchecked by parseGuardDoc (T12 readers)
Task 4: minor (deferred, T6 awareness): with a NaN base, effectiveBudget honours any raise even below $5 (usd <= NaN false) — cannot unblock while over
Task 4: minor (deferred): latch.test.ts:213 dead reassignment in loop
Task 4: complete (commits 5a4ebcf..c04c5ab, review clean)
- 2026-10-12T02:40:47-0400 T5 BASE=c04c5ab; implementer: Opus (a1b4ef9d7421976e8, t5-impl). Meter 5h 23%, week 23%.
- 2026-10-12T02:46:13-0400 T5 implementer DONE: 8a4d652 (antenna 102, tsc clean); brief code verbatim + 3 tests (signal, envelope, action_parameters); 10 mutants. Concerns: PATCH omits unlisted rule fields; empty zoneId not refused here (T6).
- 2026-10-12T02:46:36-0400 T5 spec reviewer: Opus (ac8ed2631ce4b3696); quality reviewer: Opus (ad037bef6058a0954)
- 2026-10-12T02:47:48-0400 T5 spec review: APPROVED, 1 Minor (extra tests — accepted, pin prose requirements). ⚠️ for T6: empty token/zoneId refusal before network (Review Focus 4); waf-api alert; waf-corrected. sha256 88f004cf93dadb42
- 2026-10-12T02:48:08-0400 T5 quality review: APPROVED, 0 Crit/0 Imp, 4 Minor. sha256 1537b9f50539a9bc
Task 5: minor (deferred): null envelope / result:null → TypeError not WafError (still fails closed before PATCH)
Task 5: minor (deferred): 5 s timeout value unpinned (only presence of signal asserted)
Task 5: minor (deferred): post-PATCH verify checks only enabled, not action/expression
Task 5: minor (deferred): found-0/found-2 refusal tests don't assert GET-only
Task 5: note (for T6/final): WafError messages carry the request path → zone ID lands in guard.json waf.error and alerts (not public while state/ is off the allowlist)
Task 5: complete (commits c04c5ab..8a4d652, review clean)
- 2026-10-12T02:48:34-0400 T6 BASE=8a4d652; implementer: Opus (a33e3a61556ed6dd8, t6-impl); carried T1 minors 1-2, T4 latch changes, T5 non-WafError throws + empty-secret pre-check
- 2026-10-12T02:59:46-0400 T6 implementer DONE_WITH_CONCERNS: aba89a5, a6965fa (antenna 138/11 files, tsc clean; 13 mutants). 6 deviations (create-only etagDoesNotMatch *; persist retries 3; spend replaces blind in merge; outcome reflects stored; nullable amounts raise both budget alerts; any WAF throw = waf-api). Concerns: '*' unverified on prod R2; kill switch lags ≤1 min after a lost race to a tripped winner.
- 2026-10-12T03:00:10-0400 T6 spec reviewer: Opus (a0b5b6b5c1dfe5c06); quality reviewer: Opus (a9b3145bac89c5b85)
- 2026-10-12T03:03:32-0400 T6 spec review: APPROVED, 4 Minor (deleted-doc retry unconditional not create-only; lost-race-to-tripped-winner → 1-min WAF lag + 2 false waf-corrected alerts; corrupt winner → guard-state-corrupt 1 min late; extra files justified). All 6 deviations accepted. ⚠️ zone ID in waf-api alert text (T9/T12 decide redaction); corrupt budget.json silently ignored. sha256 f3be0b16323bb744
- 2026-10-12T03:05:33-0400 T6 quality review: NEEDS FIXES — 1 Important (plan-mandated I1: unreadable/corrupt budget.json swallowed; transient read error mid-evaluation → sticky ~15-min spend trip with misleading urgent alert). 6 Minor. sha256 f1de81e0706d22d6
- Ruling: T6 I1 enters the fix loop — a budget.json get that THROWS skips this invocation's evaluation (evaluated_at not advanced; next minute retries; blind keeps counting from last success, so a persistent failure still trips blind at 6 h) and raises resolvable 'budget-unreadable'; a CORRUPT budget.json keeps evaluating against the base budget (stricter) and raises the same condition — the plan's silent catch contradicts R13's loud-failure intent; fail-closed is kept — cost if wrong: a persistently throwing budget read delays evaluation until blind (alerted throughout).
- Ruling: T6 quality M1 (non-evaluating run turns off a racer's fresh trip and reports blocked:false) folded into round 1 — when the reconcile turned the switch OFF and nothing was persisted, one head(GUARD_KEY); if the etag differs from the one read, re-read and fold its tripped into the outcome (blocked); and waf-corrected text allows "or an overlapping invocation" — one extra Class B read only on that rare branch, within the guard's read bounds — cost if wrong: one extra HEAD on each un-block minute.
- Ruling: T6 M2 (deleted-doc retry → create-only, keeping the unconditional step only as the refused-create fallback), M3 (comment the exhausted-persist window; drop the unused final re-read), M4 (test: a throwing offair.json get is unknown), M5 (parseGuardDoc validates evaluation.at / amounts so a hand-edited doc becomes corrupt→spend trip instead of guardConditions throwing after persist), M6 (test nits) folded into round 1 — all small, M2/M4/M5 on the strict surface — cost if wrong: minor churn in latch.ts (M5).
Task 6: minor (deferred): corrupt-winner path raises guard-state-corrupt one minute late (spec m3)
Task 6: note (for T9/final): waf-api alert text embeds the zone ID via WafError path → decide redaction before alerts leave the account
Task 6: note (for T9): guard-state-corrupt is resolvable — "resolved" wording must not imply the spend trip it caused is cleared
- 2026-10-12T03:05:49-0400 T6 fix round 1 dispatched: resumed implementer Opus (a33e3a61556ed6dd8); FIX_BASE=a6965fa; sentinel t6-impl/fix1-done; 7 items
- 2026-10-12T03:11:48-0400 T6 fix1 landed 053c5db (antenna 146; 8 mutants caught). Residual: our conditional write succeeds before a racer's trip merges → 1 unblocked minute (trip in state; next run re-blocks).
- 2026-10-12T03:12:07-0400 T6 re-review: Opus (a4752c822d8d499f3, t6-rerev1)
- 2026-10-12T03:15:22-0400 T6 re-review: ALL ADDRESSED (7/7), no new breakage; probe confirms blind still trips at +360 min under a persistently throwing budget read. sha256 b2bb23f5475e5882
Task 6: fix round 1/5 (7 addressed, 0 open — budget-unreadable skip/alert; unblock re-check HEAD; create-only re-create; persist window doc; offair-throw unknown test; evaluation.at validated; test nits; commits a6965fa..053c5db)
- Ruling: T6 residual (our conditional write lands before a racer's merged trip → our minute reported unblocked, trip kept in state, next run re-blocks and alerts) accepted as a known one-minute window — re-reviewer: inherent to lock-free reconcile-then-persist, no in-bounds cheap fix, trip never lost and never silent — cost if wrong: ≤1 minute of listener traffic per overlapping-cron race while over budget.
Task 6: minor (deferred, MUST-FIX in final wave): no committed test pins "blind still trips while budget.json reads keep throwing" — the I1 ruling's cost-if-wrong rests on it (mutant gating applyBlindRule on !budgetReadFailed survives)
Task 6: minor (deferred): M1 fold case emits waf-corrected "…to match blocked=false" while outcome is blocked:true (confusing text)
Task 6: minor (deferred): budget-unreadable is a new condition key not in R13 — T9 dispatch / T17 runbook must list it
Task 6: minor (deferred): ok-but-malformed budget.json still silently ignored by effectiveBudget (T4 code)
Task 6: minor (deferred): corrupt-budget message renders $NaN when base invalid (already alerted via meterProblems)
Task 6: complete (commits 8a4d652..053c5db, review clean)
- 2026-10-12T03:15:47-0400 T7 BASE=053c5db; implementer: Opus (af9a37b3cb51d64c3, t7-impl)
- 2026-10-12T03:17:53-0400 T7 implementer DONE: a424809 (antenna 150/12, tsc clean). Concern: deploy-assets still uploads index.html until T10.
- 2026-10-12T03:18:16-0400 T7 spec reviewer: Opus (a234acb730bf8f754); quality reviewer: Opus (abf2dd3b0068f4774)
- 2026-10-12T03:19:05-0400 T7 spec review: APPROVED, 0 findings. sha256 0502c3f9af50dd05
- 2026-10-12T03:19:41-0400 T7 quality review: APPROVED, 0 Crit/0 Imp, 3 Minor. sha256 23ee35121f04b5c6
Task 7: minor (deferred): "corrects a hand-uploaded index.html" test asserts only the return value, not body/metadata
Task 7: minor (deferred): off-air page negative check covers only player.js (use not.toContain("<script"))
Task 7: minor (deferred): unconditional index PUT race (self-healing ≤1 min) deserves a comment
Task 7: complete (commits 053c5db..a424809, review clean)
- 2026-10-12T03:20:02-0400 T8 BASE=a424809; implementer: Opus (aa93d12d95d3bfdae, t8-impl)
- 2026-10-12T03:24:34-0400 T8 implementer DONE: 4d1858b (antenna 158/12, tsc clean; 6 mutants). Deviations: worker-configuration.d.ts regenerated (wrangler types, local); extra failed-HEAD test. Concern: readInputs throw after guard raises no alert condition.
- 2026-10-12T03:24:59-0400 T8 spec reviewer: Opus (a8df04c2ad29b9a06); quality reviewer: Opus (aa7b15612595f66d4)
- 2026-10-12T03:26:31-0400 T8 spec review: APPROVED, 3 Minor (d.ts regen outside list — correct; extra HEAD test — accepted; readInputs-throw no alert — matches brief, not a spend hole). sha256 8c422d88747100c0
- 2026-10-12T03:30:11-0400 T8 quality review: NEEDS FIXES — 2 Important (both plan-mandated): I1 handler tests run the real guardStep with real global fetch; network isolation rests only on no CF_* secrets in the vitest env, which wrangler loads from antenna/.dev.vars|.env — with all four set, npm test would PATCH the production kill switch; I2 the sink gets a partial condition set on unknown/crash/early-return/throw paths and T9's planAlerts resolves absent keys aloud → false "resolved: Station blocked: spend". 6 Minor. sha256 05bfb0f73f37915a
- Ruling: T8 I1 fixed in round 1 — both scheduled-handler tests pass an env with CF_ACCOUNT_ID/CF_ZONE_ID/CF_ANALYTICS_TOKEN/CF_WAF_TOKEN forced undefined AND spy globalThis.fetch to reject + assert never called — the Global Constraint "no test may reach the network" outranks the plan's verbatim test file; a test that can PATCH the real kill switch is a strict-surface hazard — cost if wrong: none.
- Ruling: T8 I2 fixed in round 1 by extending the flush contract (T8 owns it): ClockDeps.alerts(conditions, nowMs, { complete: boolean }) — complete is true only when runClock reached the end of its normal path with every condition computed; false on unknown, guard crash, horizon-missing/refused early returns and any throw. logAlerts logs the flag. T9's planAlerts MUST skip the resolution pass (no "resolved", no cooldown bookkeeping of absences) for an incomplete batch, while still sending/repeating the conditions present — carried into the T9 dispatch — cost if wrong: a genuine resolution is announced one invocation later.
- Ruling: T8 Minors M1 (pin flush-on-throw), M2 (lead-low test while offair-not-tripped: alert still raised), M3 (horizon-missing message covers absent OR unreadable/corrupt), M4 (new urgent condition 'clock-inputs' when readInputs/gridOf throws — raised before rethrow, flushed incomplete), M5 (clock line on a runClock throw still carries guardMs/blocked) folded into round 1 — small; M4 closes the one cloud-side failure without a condition key; T9/T17 must list 'clock-inputs' — cost if wrong: one extra alert key.
Task 8: minor (deferred): worker-configuration.d.ts regenerated outside the brief's file list (accepted, correct)
- 2026-10-12T03:30:26-0400 T8 fix round 1 dispatched: resumed implementer Opus (aa93d12d95d3bfdae); FIX_BASE=4d1858b; sentinel t8-impl/fix1-done; 7 items
- 2026-10-12T03:34:03-0400 T8 fix1 landed 12f796a (antenna 164; mutants A-E as predicted). Concern: failed playlist bucket.put raises no alert key (batch incomplete, error on clock line).
- 2026-10-12T03:34:21-0400 T8 re-review: Opus (a770582fdbb3a82a4, t8-rerev1)
- 2026-10-12T03:37:27-0400 T8 re-review: ALL ADDRESSED (7/7), no new breakage; spend-bound code+tests untouched. sha256 6b2b0330d7a32637
Task 8: fix round 1/5 (7 addressed, 0 open — no-network handler tests; AlertBatch{complete}; flush-on-throw pinned; lead-low off-air; horizon-missing text; clock-inputs; ClockError partial; commits 4d1858b..12f796a)
- Ruling: correction to the T8 M4 ruling — 'clock-inputs' does NOT close every cloud-side failure without a key: a failed playlist bucket.put still has none (no spend consequence; batch incomplete; error on the clock line; hugo dead-clock backstops). Fix in the final wave (MUST-FIX): the outer catch pushes a catch-all urgent resolvable 'clock-failed' when no more specific key was pushed; T9/T17 list it — cost if wrong: one extra alert key.
- Ruling (carried into the T9 dispatch): scope resolution by key family — AlertBatch gains guardComplete (true whenever the guard returned a known outcome); planAlerts may resolve guard-family keys when guardComplete even if the clock batch is incomplete, and resolves clock keys only when complete — otherwise a persistent horizon-missing/refused would suppress the guard's all-clears (e.g. tripped-spend after --raise-to) for hours — cost if wrong: guard all-clears could be announced while the clock is degraded (still accurate for the guard).
Task 8: minor (deferred): ClockError calls super(message) without { cause } — runtime log shows wrapper stack
Task 8: complete (commits a424809..12f796a, review clean)
- 2026-10-12T03:38:20-0400 GATE after Task 8: report /Users/shawn/projects/llama/.claude/worktrees/playout-phase2/.superpowers/sdd/phase2/orch/gate8-report.md (sha256 4b6fe6d8…); STOPPED — waiting for llama-ba's go before Task 9

- llama-ba (RELAY-NOW, 2026-10-12): Gate 8 PASSED; Task 9 approved for the successor. llama-ba re-verified: 21 sha256 pins match, 13 commits antenna-only, npm test 164/164, tsc clean, no account details, t6-rerev1 read in full. Rulings 1–19 RATIFIED (incl. #14, surfaced to the operator).
- Ruling (llama-ba, ratified, zone-ID redaction): alert text sent off-account (ntfy/email) carries NO account ID, zone ID or ruleset ID — name the rule by its description instead. IDs may still appear in the Worker's own console log lines.

## HANDOFF (written 2026-10-12 on RELAY-NOW by peer 1e675379-4a60-4867-9819-08b2ea8e3082)

### State
- Branch playout-phase2 @ 12f796a (13 commits since ccf0f16), tree clean. Tasks 0–8 COMPLETE and reviewed; GATE after Task 8 PASSED (llama-ba). Next: Task 9 (approved).
- antenna: 164 tests / 12 files, tsc clean (baseline 41). Python baseline (Task 0, unchanged since): py3.14 full 2462 passed/7 deselected; py3.11 transmitter 306; Debian-12 gate 306.
- Gate report: $D/orch/gate8-report.md (sha256 4b6fe6d856b9b7833673d417547a63a87034e945d9725e09c594b2910d709904).
- Nothing in flight. My tick is disarmed at RELAY-READY.

### T9 dispatch requirements (from rulings 16, 19 and the redaction ruling)
1. (Ruling 16) The clock calls `alerts(conditions, nowMs, batch: AlertBatch)` with `batch.complete` (src/clock.ts AlertBatch, doc comment states the sink obligation). planAlerts MUST skip the resolution pass for an incomplete batch — no "resolved", no cooldown bookkeeping of absent keys — while still sending/repeating the conditions present.
2. (Ruling 19) AlertBatch gains `guardComplete` (true whenever the guard returned a known outcome; the clock sets it — T9 touches clock.ts for this). planAlerts may resolve GUARD-family keys when guardComplete even if the clock batch is incomplete; CLOCK keys resolve only when complete. Guard family = keys from src/guard.ts + src/conditions.ts (tripped-*, budget-50/80:*, guard-reading-failing, guard-unknown, offair-corrupt, guard-state-corrupt, waf-api, waf-corrected, budget-file-invalid, guard-write, budget-unreadable); clock family = guard-crashed, index-write, horizon-missing, horizon-refused, lead-low, offair-without-fallback, clock-inputs (and clock-failed once added). Note guard-crashed / guard-unknown arise exactly when the guard did NOT return a known outcome.
3. (Redaction ruling) Off-account alert text (ntfy body/title, email subject/body) must carry no account ID, zone ID or ruleset ID. waf-api's message currently embeds WafError text, which includes the Rulesets request path (/zones/<zone>/rulesets/<rs>/...) — redact at the channel/message boundary or build the waf-api message from the rule description; pin with a test that a WafError carrying ids produces alert text with neither. Console log lines may keep ids.
4. (T6 note) guard-state-corrupt is resolvable — its "resolved" wording must not imply the spend trip it caused is cleared.
5. Keys T9 (and T17's runbook) must list beyond R13's: budget-unreadable, clock-inputs, clock-failed.
6. Brief extraction: `bash <skill>/scripts/task-brief docs/superpowers/plans/2026-10-11-playout-phase2.md 9 $D/orch/pkg/task-9-brief.md` (briefs 1–8 already in orch/pkg/; constraints.md, implementer-common.md, reviewer-common.md, reviewer-spec.md, reviewer-quality.md, rereview-common.md are reusable as-is).

### MUST-FIX list for the final wave
- (T6) Commit a test pinning that blind still trips 6 h after the last successful reading while state/budget.json gets keep throwing (re-reviewer's scratch probe proved it; a mutant gating applyBlindRule on !budgetReadFailed currently survives).
- (Ruling 18) clock.ts outer catch pushes a catch-all urgent resolvable 'clock-failed' when no more specific key was pushed (closes the failed-playlist-PUT gap); T9/T17 list it. If T9 is the natural place (it already touches clock.ts for guardComplete), the successor may fold it into T9 with a ledger ruling.
- Final reviewer should triage every "minor (deferred)" line above. Already resolved later, so skip: Task 1 minors 1–2 (fixed in T6: create-only first write; corrupt-read etag pinned), Task 6 "budget-unreadable not in R13" (covered by item 5 above). Candidates worth fixing (spend-adjacent): T3 15 s GraphQL timeout unpinned; T5 5 s timeout unpinned; T5 post-PATCH verify checks only `enabled`; T1 billingPeriod(NaN) not refused; T6 waf-corrected text in the M1 fold case; T8 ClockError without { cause }.

### Operator-checkpoint items (Task 17)
- Confirm the first state/guard.json write succeeds on production R2 (create-only `onlyIf: { etagDoesNotMatch: "*" }` verified only in miniflare; every fallback degrades to the plan's unconditional create).
- Confirm the kill-switch PATCH keeps the rule whole (it resends only action, expression, description, enabled, ref, action_parameters).
- Ruling 14 (ratified, surfaced by llama-ba): a one-minute unblocked window is possible when overlapping cron runs race (trip never lost; next run re-blocks; alerted).
- Runbook lists the new alert keys budget-unreadable, clock-inputs, clock-failed.
- Before Debian-12 gates (Task 12+): `docker info` must work; if not, STOP and ask llama-ba (never skip).

### Process notes for the successor
- Orchestrator files: $D/orch/pkg/ (briefs, *-common.md, review packages t<N>-review.diff / t<N>-fix1.diff, setflight.py for STATE.md in-flight edits: `python3 $D/orch/pkg/setflight.py $D/STATE.md task=agentId ...`, no args = empty).
- Pattern per task: sdd-dispatch.sh claim → implementer (model per plan hint) → review-package BASE..HEAD → spec + quality reviewers (Opus) in parallel → fix round by SendMessage to the implementer (sentinel fixN-done) → review-package FIX_BASE..HEAD → scoped re-review (Opus, new task dir t<N>-rerevN).
- Implementer prompts carried prior-task interface changes explicitly; reviewers got file paths only (no ledger findings except the "Ruling:" lines for re-reviews).
- 2026-10-12T03:41:12-0400 RELAY-READY: tick 42970d89 deleted; armed-1e675379 removed; nothing running
