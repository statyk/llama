# SDD ledger — plan: docs/superpowers/plans/2026-10-11-playout-phase2.md
Orchestrator: peer session 9d1f2929-5203-43a8-bee6-76d3b1bfec42 (successor to 1e675379; its ledger $D/orch/ledger.md read-only). Parent llama-ba. Start 2026-10-12T03:44:19-0400 at 12f796a.
Spec: docs/superpowers/specs/2026-10-09-playout-design.md (Stakes governs; spend is the strict surface).
Tasks 0–8 complete (predecessor ledger); Gate 8 PASSED; rulings 1–19 + zone-ID redaction RATIFIED.
Gates: STOP at Task 17 HUMAN CHECKPOINT after the final Fable review. Docker check before Task 12+.
Brakes: 5h 85%, weekly 60%.

## Escapes
- 2026-10-12T04:30:16-0400 T10 implementer ran the brief's own verification `ANTENNA_BUCKET=b node scripts/deploy-assets.mjs --dry-run` (plan line 75). Verified in the script: the --dry-run branch only console.logs the would-be `npx wrangler r2 object put` lines and `continue`s — no spawn, no network, fake bucket 'b'. No account contact. It is still a letter-breach of llama-ba's "no --dry-run" rule; my dispatch did not carve it out. Future antenna dispatches: forbid any --dry-run, even local.

## Log
- 2026-10-12T03:44:19-0400 start; meter 5h 4% (resets 08:19), week 25%; docker info OK.
- Ruling: Task 9 implementer on Opus, not the plan's Sonnet hint — T9 now carries rulings 16/19, the redaction ruling and (below) clock-failed, and touches clock.ts on the spend/blocking path where every implementer so far was Opus — cost if wrong: one Opus implementer seat instead of Sonnet.
- Ruling: fold the MUST-FIX 'clock-failed' catch-all (ruling 18) into Task 9 — T9 already edits clock.ts for guardComplete and owns the alert key list — cost if wrong: T9's diff grows by one clock.ts branch + test.
- Ruling: planAlerts/dispatchAlerts take a trailing batch argument defaulting to {complete:true, guardComplete:true} so the brief's verbatim tests run unchanged; family membership is an explicit CLOCK key set, and any key NOT in either known set is treated as clock-family (resolved only on a complete batch — the conservative side) — cost if wrong: an unlisted guard key's all-clear waits for a complete batch.
- Ruling: Task 11 (Sonnet) runs alongside Task 9 — files disjoint (public/*.js, test/nowplaying.test.ts vs src/alerts.ts etc.); both commit by explicit paths only — cost if wrong: a transient red in one task's npm test from the other's uncommitted edits.
T9 BASE=12f796a
- 2026-10-12T03:45:12-0400 T9 implementer dispatched: Opus (a2c136c4e5606de5d, t9-impl). T11 BASE=12f796a; implementer: Sonnet (ae2a0aa53e16b6aad, t11-impl). Tick 9cfe425a armed 13,43.
- 2026-10-12T03:47:10-0400 T11 implementer DONE: 826a07a (antenna 170/12, tsc clean; no deviations). Review pkg orch-r1/pkg/t11-review.diff (12f796a..826a07a).
- 2026-10-12T03:47:10-0400 T11 spec reviewer: Opus (a03a4af18d8d1d65b, t11-rev-spec); quality reviewer: Opus (a753db9c526bc6726, t11-rev-qual)
- 2026-10-12T03:48:06-0400 T11 spec review: APPROVED, 0 findings (files byte-identical to brief). ⚠️ RF5 "~45 s" end-to-end includes ~30 s player buffer + 25 s StallWatch → may exceed 45 s; operator verification at T17. ⚠️ A2 no-billing rests on edge cache (operator-measured). sha256 6569c805f0dd9eb3
Task 11: note (for T17 runbook/checklist): end-to-end kill-switch latency on an already-playing page ≈ buffer (~30 s) + 25 s; verify live against RF5's ~45 s
- 2026-10-12T03:50:05-0400 T11 quality review: NEEDS FIXES — 1 Important (plan-mandated: RF5 blip test never checks progress resets offairCount; mutant survives). 6 Minor. sha256 f45e866bb36f9a93
- Ruling: T11 I1 enters the fix loop — extend the blip test (stall again after progress; first offair verdict must not go off-air) — the test is the one Review Focus 5 names and its claim is unpinned — cost if wrong: three test lines.
- Ruling: T11 Minors M1 (session counter so a probe from a previous Play session cannot feed the new StallWatch / break one-in-flight), M2 (AbortSignal.timeout(8000) on the probe so a black-holed fetch cannot stall the 10 s cadence) and M4 (wrap the 124-char line) folded into round 1 — small, each restores a documented property; deviates from the brief's verbatim player.js — cost if wrong: two small deviations the final reviewer re-reads.
Task 11: minor (deferred): backwards currentTime jump stops progress registering until the old high-water mark (shows Reconnecting…, probes return unknown; never off-air)
Task 11: minor (deferred): permanent stall with a healthy station probes every 10 s and shows Reconnecting… forever (phase-4 player UX)
Task 11: minor (deferred): player.js has no tests of its own (DOM wiring; matches phase-1 pattern)
Task 11: minor (deferred): networkDetails.status presence in vendored hls.min.js unverified
- 2026-10-12T03:50:05-0400 T11 fix round 1 dispatched: resumed implementer Sonnet (ae2a0aa53e16b6aad); FIX_BASE=826a07a; sentinel t11-impl/fix1-done; 4 items
- 2026-10-12T03:52:41-0400 T11 fix1 landed b19dccf (blip mutant now red on the predicted test). Re-review: Opus (a0ef5757e46724e62, t11-rerev1); pkg orch-r1/pkg/t11-fix1.diff (path-limited to T11 files)
- 2026-10-12T03:54:31-0400 T11 re-review: ALL ADDRESSED (4/4); blip mutant independently red at test line 156. sha256 e0a22c1cb1bff30f
Task 11: fix round 1/5 (4 addressed, 0 open — blip progress-reset pinned; session counter; 8 s probe timeout; line wrap; commits 826a07a..b19dccf)
Task 11: minor (deferred, recommend fix in final wave — introduced by my M2 ruling): AbortSignal.timeout throws on pre-2022 browsers (iOS 15 WebKit) → every probe "unknown" → mid-play detection silently never fires there; guard with typeof AbortSignal.timeout === "function"
Task 11: complete (commits 12f796a..b19dccf, review clean)
- 2026-10-12T03:56:23-0400 llama-ba: AbortSignal.timeout typeof guard is MUST-FIX in the final wave (not optional); mid-play latency note goes on T17's checklist.
## MUST-FIX for the final wave (carried from predecessor HANDOFF + additions)
- (T6) commit a test pinning blind still trips 6 h after last success while budget.json gets keep throwing
- (T11, llama-ba) guard AbortSignal.timeout with typeof check in player.js probe
- (Ruling 18) clock-failed — folded into T9 (733439f); final reviewer confirms
- final reviewer triages every "minor (deferred)" line in both ledgers
- 2026-10-12T03:56:23-0400 T9 implementer DONE_WITH_CONCERNS: 733439f (antenna 197/13, tsc clean; 11 mutants). Deviations: failed new alert retried next minute (last_sent_at null); failed resolved restored; optional params (Message ctor, secrets list). Concerns: guard-unknown also arises on a known outcome (raceUnknown) — runbook must not say "exactly when unknown"; guard-crashed clock-family stays active until a complete batch; alerts.json unreadable → nothing sent that minute (hugo dead-clock backstops); redaction pattern+configured values only.
- 2026-10-12T03:56:23-0400 T9 review pkg orch-r1/pkg/t9-review.diff (12f796a..733439f, T9 paths only) + rulings orch-r1/pkg/task-9-rulings.md. Spec reviewer: Opus (a1ed0973e98db31e4); quality reviewer: Opus (af11b75d9634fb247)
- 2026-10-12T03:56:23-0400 T12 BASE=733439f; docker info OK; implementer: Opus (a099370eab1cc0688, t12-impl). Ruling: T12 runs alongside T9's review — no T9 dependency per the plan (12–16 depend only on each other); still ≤2 implementers — cost if wrong: none (disjoint packages). Fleet fit: 6% + 3×8×1.5 = 42 < 100.
- 2026-10-12T03:58:58-0400 T9 spec review: APPROVED, 4 Minor (alerts@lma-radio.com in alerts.test.ts:232 — constraints allow it only in plan/runbook; 2 retry deviations justified — brief's code broke its own retry rule; additive params; d.ts regen). ⚠️ guard-family keys recomputed each known-outcome invocation (T6 design); guard-unknown in guardComplete batch (runbook wording); R2 outage silences cloud alerts. sha256 2904384af68ab6ca
- Ruling: T9 retry deviations (failed new alert → last_sent_at null; failed resolved restores active entry) accepted — the brief's code violated its own "next invocation retries it" rule; each pinned — cost if wrong: a retried message labelled kind "repeat".
- 2026-10-12T04:01:26-0400 T9 quality review: NEEDS FIXES — 1 Important (plan-mandated: resolved sent on first absent minute + cooldown treats a return within 15 min as continuing → after a delivered "resolved" a returning condition is silent up to ~6 h; probe: clock-failed alert@0, resolved@1, then active 5..299 unannounced). 8 Minor. sha256 ba24525211f1706a
- Ruling: T9 I1 → option (a): a resolvable key's "resolved" is sent only once it has stayed absent for COOLDOWN_MS (entry stays active with a clearing timestamp; a return inside the window just clears the timestamp and continues, repeat clock unchanged); clearing time only starts/advances on batches allowed to resolve that key (A/B), an incomplete batch copies the entry unchanged — reads R13's "cooldown: returns within 15 min = continuing" and "resolved when it clears" together without contradiction, and kills resolved/alert flapping; brief test 1's timing changes accordingly — cost if wrong: every all-clear (incl. tripped-spend after a raise) arrives 15 min later than the plan's text.
- Ruling: T9 Minors folded into round 1 — q-M1 (drop non-object entries when building prev: a hand-edited null entry otherwise wedges every cloud alert incl. tripped-spend), q-M3 (first write create-only, guard idiom), q-M4 (an alert never delivered that clears gets no "resolved"; entry dropped), q-M5 (timeout around the email binding send), q-M7 (make the account-ID redaction assertion able to fail), spec-M1 (alerts@lma-radio.com → example.org address in the test) — small; q-M1/M5 keep alerts flowing on the strict surface — cost if wrong: churn in alerts.ts.
Task 9: minor (deferred): trailing batch default COMPLETE fails open for a future caller (alertSink passes it; production safe)
Task 9: minor (deferred → T17 runbook): STATION_NAME must be ASCII/Latin-1 (raw ntfy Title header) — document
Task 9: minor (deferred, final): budget-file-invalid is once with a constant key → a second invalid raise within 35 days unalerted (safe direction; T6 design)
Task 9: note (T17 runbook): guard-unknown can arise on a known outcome (raceUnknown); R2 outage reading alerts.json silences cloud alerts (hugo dead-clock is the cover — verify at T14)
- 2026-10-12T04:01:26-0400 T9 fix round 1 dispatched: resumed implementer Opus (a2c136c4e5606de5d); FIX_BASE=733439f; sentinel t9-impl/fix1-done; 7 items
- 2026-10-12T04:05:13-0400 T12 implementer DONE_WITH_CONCERNS: 8da34f0 (transmitter 332 py3.14/py3.11/Debian-12; llama full 2488 passed/7 deselected; 8 mutants). Deviations: 3-way raise floor (evaluation.budget_usd, tripped_budget_usd on spend trip, honoured pending raise); null amounts fail closed; corrupt budget.json overwritten, unreadable refuses; rounded comparison; view tolerant. Concern: corrupt guard.json + failing reading → raise refused while guard-state-corrupt alert recommends --raise-to (safe).
- 2026-10-12T04:05:13-0400 T12 review pkg orch-r1/pkg/t12-review.diff (733439f..8da34f0, packages/). Spec reviewer: Opus (a283244d24d21af52); quality reviewer: Opus (a723c49363b46407b)
- 2026-10-12T04:08:03-0400 T12 spec review: APPROVED, 4 Minor (budget view: failed budget.json read exits 0; offair off: unreadable guard.json → exit 1 after a successful write (brief verbatim); cap checked after rounding (100.004 accepted, clock caps anyway); corrupt-guard window message mismatch). Three-way floor ACCEPTED against latch.ts applyAttempt/effectiveBudget. sha256 faf8a186bbafdeba
- Ruling: T12 three-way raise floor accepted — reviewer traced it to latch.ts applyAttempt (clears only when effective > tripped_budget_usd) and effectiveBudget; the brief's single field is not the Worker's comparison — cost if wrong: an over-strict refusal the operator can see.
- 2026-10-12T04:09:01-0400 T12 quality review: NEEDS FIXES — 1 Important (plan-mandated: R7 PUT-budget half can't fail — puts.json day stale vs real publish._utc_today so count resets; PutBudget mutant survives). 7 Minor. sha256 0d213195a1304b53
- Ruling: T12 I1 enters the fix loop — pin publish._utc_today (or write today's UTC day) so the over-budget fixture holds; add the same fixture to budget --raise-to (R7 covers both) — R7 is the takedown lever — cost if wrong: test lines.
- Ruling: T12 Minors folded into round 1 — q-M1/s-M2 offair off prints a note (station may stay blocked) and exits 0 when guard.json is unreadable/corrupt after a successful write; q-M2 budget view prints a guard <error> line and carries on; s-M1 budget view exits 1 after printing when either read failed; q-M3 raise line says whether the Worker honours it (via _pending_raise_usd); q-M4 raise_budget refuses a guard.json parseGuardDoc would reject (minimal mirror: schema==1, tripped bool, tripped_budget_usd number|null, …) — else the Worker's corruptGuardDoc swallows the raise; s-M3 cap checked on the raw value too; q-M6 put_state does not retry publish.NON_RETRYABLE codes; q-M5 reuse publish._error_code/GUARD_KEY; q-M7 top-level import — q-M4 is on the strict surface, rest small — cost if wrong: churn in cloudstate.py/cli.py.
Task 12: note (T17 runbook): guard-state-corrupt alert says --raise-to but while readings fail the raise is refused (no period) — runbook: wait for the next successful evaluation
- 2026-10-12T04:09:01-0400 T12 fix round 1 dispatched: resumed implementer Opus (a099370eab1cc0688); FIX_BASE=8da34f0; sentinel t12-impl/fix1-done; 9 items
- 2026-10-12T04:10:17-0400 T9 fix1 landed 9664254 (antenna 207/13, tsc clean; 9 mutants as predicted). Re-review: Opus (a0c06f3f96ebc336b, t9-rerev1); pkg orch-r1/pkg/t9-fix1.diff
- 2026-10-12T04:15:20-0400 T9 re-review: OPEN FINDINGS — 7/7 ADDRESSED; NEW Important: undelivered REPEAT sets last_sent_at null → item-4 drop rule deletes a delivered alert's entry → its "resolved" never sent (probe P1: tripped-spend). Minor: clearing window measured wall-clock across incomplete batches; comment overstates. sha256 2aecd890b3511da5
Task 9: fix round 1/5 (7 addressed, 1 new open — undelivered repeat loses resolved; commits 733439f..9664254)
- Ruling: clearing window measured in wall-clock from the first allowed absence is accepted (a resolved at an allowed absent batch ≥15 min later is true); fix the alerts.ts:133-134 comment to say so — cost if wrong: an all-clear can land sooner than 15 allowed-batch minutes after the first absence.
- 2026-10-12T04:15:20-0400 T9 fix round 2 dispatched: resumed implementer Opus (a2c136c4e5606de5d); FIX_BASE=9664254; sentinel t9-impl/fix2-done; explicit delivered flag + comment
- 2026-10-12T04:17:43-0400 T12 fix1 landed 67c9247 (transmitter 372 ×3 gates; llama 2528/7; 7 mutants). R7 fixture uses today's real UTC day (default-arg binding defeats monkeypatch); brief GUARD fixture gained 5 Worker-written fields for the shape mirror. Re-review: Opus (a08d6bbd47a8a6441, t12-rerev1)
- 2026-10-12T04:18:47-0400 T9 fix2 landed 24bb50b (antenna 210/13; 4 mutants). Re-review: Opus (a688a8babdafbd4d4, t9-rerev2)
- 2026-10-12T04:21:42-0400 T12 re-review: ALL ADDRESSED (9/9); R7 mutant independently red; shape mirror matches latch.ts on every Worker-written doc. sha256 712a499fc8589194
Task 12: fix round 1/5 (9 addressed, 0 open — R7 really spent; offair off note; view tolerant + exit 1; honoured label; shape mirror; raw cap; non-retryable; reuse; import; commits 8da34f0..67c9247)
Task 12: minor (deferred): _iso_ok vs JS Date.parse differ on hand-edited since (stricter on naive/date-only → permanent refusal with untrue "retry" advice; looser on basic-format)
Task 12: minor (deferred): json.loads accepts NaN/Infinity tokens JS rejects → mirror passes a doc the Worker deems corrupt (parse_constant raise)
Task 12: minor (deferred): wording — offair off shape note "until it rewrites it" (rewrite is a spend trip); view "(honoured)" with a malformed guard
Task 12: minor (deferred): get_json catches only ValueError around body read (botocore streaming error → traceback after offair off's write); _finite OverflowError on huge ints (pre-existing)
Task 12: minor (deferred): R7 test midnight window lets a mutant escape (correct code never flakes); optional: monkeypatch publish.datetime
Task 12: complete (commits 733439f..67c9247, review clean)
T13 BASE=24bb50b
- 2026-10-12T04:22:13-0400 T13 implementer: Sonnet (a0fd708d15e4881c8, t13-impl); docker info OK
- 2026-10-12T04:23:04-0400 T9 re-review 2: OPEN FINDINGS — 2/2 ADDRESSED; NEW (labelled Critical per my brief's "lost message" rule; fail-safe): a failed fresh "alert" over a still-active delivered episode (after a failed resolved, or clearing elapsed across unknown batches) is stamped delivered:false → re-clear drops the resolved (probes P6/P7; predates fix 2). Validated one-line fix: failed alert inherits wasDelivered(prev) when prev is active. sha256 f614c7aaed83cca4
Task 9: fix round 2/5 (2 addressed, 1 new open — failed re-alert over active delivered episode loses resolved; commits 9664254..24bb50b)
- Ruling: P6/P7 severity treated as Important (not Critical) — fails toward "still blocked", never a false resolved or hidden trip; needs every channel down across resolve/return/re-clear — but it is fixed now in round 3 with the reviewer's validated line + P6/P7 tests — cost if wrong: none (fixed either way).
- 2026-10-12T04:23:04-0400 T9 fix round 3 dispatched: resumed implementer Opus (a2c136c4e5606de5d); FIX_BASE=24bb50b; sentinel t9-impl/fix3-done
- 2026-10-12T04:26:00-0400 T9 fix3 landed 7f30c7b (antenna 213/13; P6/P7 pinned; mutants H1/H2). Re-review: Opus (a9541b8b6c4dd8b48, t9-rerev3)
- 2026-10-12T04:27:03-0400 T13 implementer DONE_WITH_CONCERNS: 6f52067 (transmitter 384 ×3 gates; llama 2540/7). Deviations: corrupt alerts.json → fresh start; null/odd entries tolerated; failed resolved keeps code active for retry. Concerns: no separate RED captured; down channel blocks loop ≤~30 s per call, retried each occurrence; SMTP timeout per socket op.
- 2026-10-12T04:27:03-0400 T13 review pkg orch-r1/pkg/t13-review.diff (24bb50b..6f52067, packages/). Spec: Opus (a6ec0ac12b0d24ab4); quality: Opus (a1106adbc745f0546)
- 2026-10-12T04:28:24-0400 T9 re-review 3: ALL ADDRESSED; no new breakage (probes P10–P13 green). Minor: the "active never-delivered prev stays false" arm unpinned (mutant M1 survives all committed tests; would send resolved for an undelivered tripped-spend). sha256 b1328479717c7126
Task 9: fix round 3/5 (1 addressed, 0 open — failed re-alert over active delivered episode keeps delivery; commits 24bb50b..7f30c7b)
Task 9: minor (deferred, MUST-FIX in final wave — spend surface): add P10 test pinning that a failed re-alert over an active NEVER-delivered episode stays delivered:false (reviewer's sequence in t9-rerev3/handback.md)
Task 9: minor (deferred): prev.active truthiness on hand-editable JSON ("active":"no" reads active; conservative side)
Task 9: complete (commits 12f796a..7f30c7b, T9 paths; 3 fix rounds; review clean)
T10 BASE=6f52067
- 2026-10-12T04:28:52-0400 T10 implementer: Sonnet (ab7e2bae24eb7b3a2, t10-impl). Ruling: T10 runs alongside T13's review — antenna vs transmitter, disjoint — cost if wrong: none.
- 2026-10-12T04:29:28-0400 T13 spec review: APPROVED, 3 Minor (corrupt-state test doesn't pin non-dict-entry hardening; channel-timeout test weak — ntfy timeout never asserted; resolve-retry side effect needs a comment). All 3 deviations judged within R16. ⚠️ [alerts] docs → T17; plan/render alarm can stay stale while filling=False (R16 as written — final review). sha256 d34fc8a85d1cbd80
Task 13: note (T17): docs for [alerts] keys (Global Constraint: model + template + docs)
Task 13: note (final review): plan/render codes resolve only while filling — a persisting plan failure can leave 'plan' active after render refills the lead (R16 as written)
- 2026-10-12T04:30:16-0400 T10 implementer DONE: 1556760 (antenna 215/14, tsc clean; d.ts regen offline). noSecrets() already unsets ALERT_EMAIL. Escape logged (local deploy-assets --dry-run print).
- 2026-10-12T04:30:45-0400 T10 spec reviewer: Opus (afde4e6baf1322b99); quality: Opus (a8b2e221953911db7); both told no --dry-run of any kind
- 2026-10-12T04:31:22-0400 llama-ba: T10 escape reviewed — the no-dry-run rule targets wrangler deploy --dry-run; the plan's local deploy-assets print check is allowed; T9 Critical→Important downgrade accepted.
- 2026-10-12T04:32:16-0400 T10 spec review: APPROVED, 1 Minor (d.ts regen outside file list — justified). ⚠️ docs/playout-setup.md:195 still says deploy:assets uploads the player page (T17 runbook). sha256 a7d96f2daffdf3a7
Task 10: note (T17): playout-setup.md:195 — deploy:assets no longer uploads index.html (R8)
- 2026-10-12T04:35:03-0400 T13 quality review: NEEDS FIXES — 1 Important (R16 resolve wiring in service.tick and the dispatcher install in cli.run are unpinned: both mutants survive the full suite). 7 Minor. sha256 2a9560bb41294e14
- Ruling: T13 I1 enters the fix loop — tests for station-root/render resolve via a Recorder-channel Dispatcher, and that run --once installs then clears the dispatcher — R16 is binding and these lines are its only implementation — cost if wrong: test lines.
- Ruling: T13 Minors folded into round 1 — M2 per-channel failure cool-down (skip a channel ~5 min after it fails; bounds loop blocking regardless of DNS/address count; skipped = not delivered = retried), M3 in-memory last_sent_at/count so an unwritable alerts.json cannot turn dedupe into a storm, M4/s-M1 corrupt-state test asserts exact sends or no swallowed-warning, M5 suppressed note when last_sent_at is None, M6 RFC 2047-encode the ntfy Title (non-latin-1 station names), M7/s-M2 assert ntfy timeout reaches urlopen + pin partial-success, M8/s-M3 docstring/comment for resolve-retry and status lag — M2/M3 keep alerts flowing in an outage; rest small — cost if wrong: alerts.py grows a cool-down map.
- 2026-10-12T04:35:03-0400 T13 fix round 1 dispatched: resumed implementer Sonnet (a0fd708d15e4881c8); FIX_BASE=6f52067; sentinel t13-impl/fix1-done
- 2026-10-12T04:35:23-0400 T10 quality review: NEEDS FIXES — 1 Important (plan-mandated: "no account details" test misses zone_id, nested account_id, 32-hex var values; mutants M2-M4 survive; verified 3-line hardening). 3 Minor. sha256 77a9c22644e605df
- Ruling: T10 I1 enters the fix loop with the reviewer's verified three assertions (no "account_id"/"zone_id" key at any depth; no 32-hex token; no routes) — public repo, the test is the one guard — cost if wrong: a future legit 32-hex value in wrangler.jsonc must be re-justified.
- Ruling: T10 M3 (JSONC parse failure gets a hint) folded into round 1; M2 (vite as explicit devDependency) deferred — needs npm install, which implementers may not run — cost if wrong: tsc breaks if npm stops hoisting vite.
Task 10: minor (deferred): vite/client widens ambient types project-wide (src/ could import ?raw and pass tsc but fail bundling) — brief chose it
Task 10: minor (deferred): vite not an explicit devDependency (hoisted via vitest)
Task 10: note (T17 runbook): deploy:assets before/alongside the Worker deploy on a fresh bucket (index.html from the clock references player.js/style.css/hls)
- 2026-10-12T04:35:23-0400 T10 fix round 1 dispatched: resumed implementer Sonnet (ab7e2bae24eb7b3a2); FIX_BASE=1556760; sentinel t10-impl/fix1-done
- 2026-10-12T04:36:33-0400 T10 fix1 landed 0ee1206 (antenna 215, tsc clean; zone_id mutant red). Re-review: Opus (a2de28aff910edf75, t10-rerev1)
- 2026-10-12T04:38:35-0400 T10 re-review: ALL ADDRESSED (2/2); nested account_id, 32-hex and routes mutants each red. sha256 4feb9b591232311e
Task 10: fix round 1/5 (2 addressed, 0 open — account-detail test hardened; parse hint; commits 1556760..0ee1206)
Task 10: minor (deferred): 32-hex regex will reject a future KV namespace id (intended for a public repo; that task edits the test)
Task 10: complete (commits 6f52067..0ee1206, review clean)
- 2026-10-12T04:40:50-0400 T13 fix1 landed b5543e4 (transmitter 393 ×3; llama 2549/7; 3 mutants red). Re-review: Opus (ad5ca1b6a1d70af28, t13-rerev1)
- 2026-10-12T04:45:48-0400 T13 re-review: ALL ADDRESSED (8/8); cool-down cannot suppress forever; merge cannot resurrect in-process. sha256 7edcada9515b177e
Task 13: fix round 1/5 (8 addressed, 0 open — R16 wiring pinned; cool-down; in-memory dedupe; exact corrupt-state test; suppressed note; RFC 2047 title; timeouts/partial pinned; docstring; commits 6f52067..b5543e4)
Task 13: minor (deferred, recommend final wave): ntfy Title predicate should be isascii (latin-1 non-ASCII "café" arrives as invalid UTF-8 at ntfy) + Header.encode(maxlinelen=0) to avoid obs-fold
Task 13: minor (deferred): plan step's "plan" resolve unpinned (mutant A); newer-wins merge comparison unpinned (mutant D → resolved re-sent each tick after a failed write)
Task 13: minor (deferred): cool-down uses wall clock (time.monotonic); one-shot event alert during a full cool-down is logged only
Task 13: complete (commits 24bb50b..b5543e4, packages/; review clean)
T14 BASE=b5543e4
- 2026-10-12T04:46:13-0400 T14 implementer: Sonnet (adfb6d1e862ca9de9, t14-impl); docker OK. Ruling: Sonnet per plan hint despite touching publish.guard_blocks_publishing — plan code is complete and the gate must stay equivalent (stated in dispatch); Opus reviewers check it — cost if wrong: a fix round, escalate to Opus if BLOCKED.
- 2026-10-12T04:52:13-0400 T14 implementer DONE_WITH_CONCERNS: 0dc7064 (transmitter 404 ×3; llama 2560/7). Deviations: OFFAIR_KEY single-sourced in publish.py (cloudstate imports it); extra publish test (gate unchanged, offair read swallowed). Concerns: old guard-cache.json without guard_evaluated_at → spurious guard-stale ≤15 min after upgrade; unused import.
- 2026-10-12T04:52:44-0400 T14 review pkg orch-r1/pkg/t14-review.diff (b5543e4..0dc7064). Spec: Opus (a2c63b1f5ed5f8e0a); quality: Opus (a3ac611423fc144ed)
- 2026-10-12T04:54:34-0400 llama-ba RELAY-NOW: finish T14 through review/fix rounds, start nothing new, write HANDOFF (MUST-FIX, deferred final-wave items, operator checkpoints, alert keys, no --dry-run of any kind), then RELAY-READY.
- 2026-10-12T04:54:51-0400 T14 spec review: APPROVED, 5 Minor (spurious guard-stale pair on upgrade; R4 "two consecutive" looser — only a fresh 200 resets stale; monitor reads corrupt/non-bool offair.json as on-air vs antenna off-air → noise dead-clock alert; dead-clock skipped on fail-closed ticks; unused import). Gate equivalence, OFFAIR_KEY single-source, resolve-every-check all verified. sha256 8d4e4d9680de05bd
- 2026-10-12T05:02:26-0400 T14 quality review: NEEDS FIXES — 3 Important: I1 fetch_text lets IncompleteRead/BadStatusLine/ValueError escape → _step alerts dead-clock at once, bypassing R4 thresholds; I2 an unreadable guard.json is never alerted (monitor ignores cache error; guard_evaluated_at overwritten None → guard-stale and 403 alarm both disabled); I3 R4 consecutive-stale reset and trip-makes-403-expected unpinned (mutants M1/M3 survive). 7 Minor. sha256 c1344a9ce9673f57
- Ruling: T14 I1/I3 enter the fix loop as the reviewer proposes (catch HTTPException+ValueError → (0,""); genuinely stale middle read + stale/fresh/stale sequence; blocked=True offair=False 403 run ≥17 checks).
- Ruling: T14 I2 fixed in the MONITOR (reviewer option b), not in guard_blocks_publishing — the monitor records when the cache's guard error was first seen and alerts guard-stale once it has persisted ≥ guard_stale_s (resolved when the error clears and evaluation is fresh) — keeps the strict-surface gate function untouched — cost if wrong: alert lands 45 min after the first failed read rather than 45 min after the last evaluation.
- Ruling: T14 Minors folded — M-a (cache without the guard_evaluated_at KEY = unknown, say nothing; present-null still alerts), M-b part (monitor gets wall-clock now at check time, not tick start; thresholds stay counts per plan), M-c/s-M2 comment that counters reset only on a good read (intended), M-d resp.read cap 1 MiB, M-e unused import, M-f test cli passes monitor=open_monitor(st), M-g message wording — small — cost if wrong: churn in deadclock.py.
Task 14: minor (deferred): corrupt/non-bool offair.json reads as on-air in the cache (antenna reads off-air) → possible noise dead-clock alert after 17 min (spec M3)
Task 14: minor (deferred): dead-clock check skipped on fail-closed ticks (publish-state alerts instead); 403/unreachable thresholds are tick counts, can stretch during long renders (plan wording)
Task 14: note (T17): confirm site_url serves live.m3u8 at root; confirm the WAF block answers 403 on the R2 custom domain (else counted unreachable → alarm after 10 checks)
- 2026-10-12T05:02:26-0400 T14 fix round 1 dispatched: resumed implementer Sonnet (adfb6d1e862ca9de9); FIX_BASE=0dc7064; sentinel t14-impl/fix1-done
- 2026-10-12T05:08:20-0400 T14 fix1 landed 9adbe62 (transmitter 415 ×3; llama 2571/7; M1/M3 red; publish.py untouched)
- 2026-10-12T05:08:44-0400 T14 re-review: Opus (ae7ad3238e459b42b, t14-rerev1)
- 2026-10-12T05:16:52-0400 T14 re-review: ALL ADDRESSED (10/10); 8 mutants each red on the predicted test; publish.py untouched. sha256 78fb04d0406463f4
Task 14: fix round 1/5 (10 addressed, 0 open — transport errors; unreadable-guard timer; R4 pins; absent-key unknown; wall-clock now; comment; read cap; import; cli monitor test; wording; commits 0dc7064..9adbe62)
Task 14: minor (deferred): while guard.json reads fail the monitor times only the failure, so a pre-existing stall is reported ≤guard_stale_s late; in-memory timer restarts with the service (optional: keep last good guard_evaluated_at monitor-side)
Task 14: minor (deferred): empty str(exc) leaves "…: " in the message; test-style nits (__import__ in parametrize, late-bound m_clock); error-clears-but-still-stale case untested
Task 14: complete (commits b5543e4..9adbe62, review clean)

## HANDOFF (written on RELAY-NOW by peer 9d1f2929-5203-43a8-bee6-76d3b1bfec42, orch-r1)

### State
- Branch playout-phase2 @ 9adbe62, tree clean. Tasks 0–14 COMPLETE and reviewed, except 12–16, which run in sequence: 12, 13 and 14 are done, and 15 is NEXT.
  - Task 9: 12f796a..7f30c7b (T9 paths), 3 fix rounds.
  - Task 10: 6f52067..0ee1206.
  - Task 11: 12f796a..b19dccf.
  - Task 12: 733439f..67c9247.
  - Task 13: 24bb50b..b5543e4.
  - Task 14: b5543e4..9adbe62.
- Counts at the last runs: antenna 215 tests in 14 files, tsc clean. Transmitter 415 on py3.14, py3.11 and Debian-12. Full llama 2571 passed, 7 deselected.
- Ledgers: predecessor $D/orch/ledger.md (Tasks 0–8, rulings 1–19). Mine: $D/orch-r1/ledger.md (Tasks 9–14). Briefs, review packages and common prompt files are in $D/orch-r1/pkg/; the T9 rulings A–F are in pkg/task-9-rulings.md.
- Docker was up at the last check. Check `docker info` before every Debian-12 gate, and STOP if it fails.
- Nothing is in flight at RELAY-READY, and my tick is disarmed.

### Next: Task 15, then 16 (Sonnet hints; reviewers on Opus), then 17 (docs only), then the final whole-branch review on Fable, then STOP at Task 17's HUMAN CHECKPOINT.
- Task 15 (sd_notify, watchdog, systemd unit). Task 13's quality review measured that a down alert channel blocks the loop for up to one timeout per channel per 5-min cool-down (CHANNEL_COOLDOWN_S). The dead-clock fetch is capped at 10 s per socket operation. Check where the watchdog pings sit relative to these blocking calls (R15).
- Task 16 (`status`). Use `alerts.active_codes(state, now, repeat_hours*3600)`. LEVEL_CODES = dead-clock, guard-stale, station-root, plan, render. Reuse `cli._cloud` and `cloudstate.guard_summary`, whose null amounts print "unknown".

### RULE: no --dry-run of any kind
No `--dry-run` of anything: not `wrangler deploy --dry-run`, and not the local `deploy-assets.mjs --dry-run` print either (llama-ba, RELAY-NOW). No wrangler command that touches an account. No `secret put` or `deploy:assets`. No call to the real Cloudflare account, R2, ntfy or SMTP. No test may reach the network. One escape is on record: T10's implementer ran the plan's local deploy-assets --dry-run print. It had no account contact and llama-ba reviewed it. Every dispatch since then forbids it.

### MUST-FIX for the final wave (the final reviewer confirms each)
1. (T6, predecessor) Commit a test pinning that blind still trips 6 h after the last successful reading while the state/budget.json get keeps throwing. A mutant gating applyBlindRule on !budgetReadFailed currently survives.
2. (T11, llama-ba) player.js probe: guard `AbortSignal.timeout` with `typeof AbortSignal.timeout === "function"`. Without it, on pre-2022 browsers (iOS 15) every probe reads "unknown" and mid-play detection never fires.
3. (T9, spend surface) Add test P10: a failed re-alert over an active NEVER-delivered episode stays delivered:false and sends no "resolved" on re-clear. The sequence is in $D/t9-rerev3/handback.md. Mutant M1 (force delivered:true for any active prev) survives every committed test today. The code is correct.
4. (Ruling 18) clock-failed was folded into T9 at 733439f. The final reviewer confirms it covers a failed playlist PUT and is not double-raised after clock-inputs.
5. The final reviewer triages EVERY "minor (deferred)" line in BOTH ledgers: $D/orch/ledger.md (predecessor; skip T1 minors 1–2 and the T6 "budget-unreadable not in R13" line, already resolved) and $D/orch-r1/ledger.md.

### Deferred final-wave candidates (my recommendation: fix; cheap and outward-facing)
- T13: the ntfy Title predicate should be `isascii()`, not latin-1. Today "café" reaches ntfy as invalid UTF-8. Also use `Header(...).encode(maxlinelen=0)`, so long titles are not obs-folded.
- T13: pin the plan step's "plan" resolve (mutant A) and the newer-wins memory/disk merge (mutant D; otherwise "resolved" is re-sent every tick after a failed write).
- T14: a corrupt or non-bool offair.json reads as on-air in the guard cache (antenna reads it as off-air), which gives a possible noise dead-clock alert after 17 min.
- Predecessor's spend-adjacent candidates: T3 15 s GraphQL timeout unpinned; T5 5 s timeout unpinned; T5 post-PATCH verify checks only `enabled`; T1 billingPeriod(NaN) not refused; T6 waf-corrected text in the M1 fold case; T8 ClockError without { cause }.
- All other deferred minors: see both ledgers (24 in mine, 39 in the predecessor's).

### Operator-checkpoint items (Task 17 runbook/checklist must include)
- Predecessor's:
  - Confirm the first state/guard.json write succeeds on production R2. The create-only `onlyIf: { etagDoesNotMatch: "*" }` was verified only in miniflare.
  - Confirm the kill-switch PATCH keeps the rule whole.
  - Ruling 14: a one-minute unblocked window is possible when overlapping cron runs race.
- T11: end-to-end kill-switch latency on an already-playing page ≈ the player buffer (~30 s) + 25 s StallWatch, and may exceed RF5's "~45 s". Verify live (llama-ba: on the checklist).
- T9 alerts:
  - Every all-clear (tripped-spend after --raise-to included) arrives 15 min after the condition clears (R13 reading, ruled).
  - guard-unknown can also appear on a known outcome (raceUnknown), so never word it as "unknown outcome only".
  - An R2 outage reading state/alerts.json silences cloud alerts that minute; hugo's dead-clock monitor is the cover.
  - STATION_NAME must be ASCII.
- T10: on a fresh bucket, run deploy:assets before or alongside the Worker deploy (the clock's index.html references player.js, style.css and hls). Fix docs/playout-setup.md:195, which still says deploy:assets uploads the player page.
- T12: while guard.json is corrupt and readings fail, `budget --raise-to` refuses (no period) although the guard-state-corrupt alert recommends it. Wait for the next successful evaluation.
- T13: document the [alerts] keys (Global Constraint: model + template + docs) and the env-file secrets SMTP_USERNAME, SMTP_PASSWORD (a Gmail App Password) and NTFY_TOKEN.
- T14:
  - Confirm `[antenna] site_url` serves live.m3u8 at its root.
  - Confirm the WAF block answers 403 on the R2 custom domain; any other status counts as unreachable and alarms after 10 checks.
  - A pre-upgrade guard-cache.json without the guard_evaluated_at key is treated as unknown (no false alert).
- Docker must be running before any Debian-12 gate.

### Alert keys (runbook)
Cloud (antenna, state/alerts.json; family per ruling 19):

| key | family | priority | kind |
|---|---|---|---|
| tripped-spend | guard | urgent | resolvable |
| tripped-blind | guard | urgent | resolvable |
| budget-50:<period>:<budget> | guard | default | once |
| budget-80:<period>:<budget> | guard | high | once |
| guard-reading-failing | guard | high | resolvable |
| guard-unknown | guard | high | resolvable |
| budget-unreadable | guard | high | resolvable |
| offair-corrupt | guard | high | resolvable |
| budget-file-invalid | guard | high | once |
| guard-state-corrupt | guard | urgent | resolvable; its resolved text says the spend trip stays |
| waf-api | guard | high | resolvable (ids redacted off-account) |
| waf-corrected | guard | high | sent on appearance, never "resolved" |
| guard-write | guard | high | resolvable |
| guard-crashed | clock | urgent | resolvable |
| index-write | clock | high | resolvable |
| clock-inputs | clock | urgent | resolvable |
| horizon-missing | clock | default | resolvable |
| horizon-refused | clock | urgent | resolvable |
| lead-low | clock | high | resolvable |
| offair-without-fallback | clock | high | resolvable |
| clock-failed | clock | urgent | resolvable |

New beyond R13: budget-unreadable, clock-inputs, clock-failed. A key in neither family is treated as clock (resolved only on a complete batch).

hugo (transmitter, ~/.transmitter/alerts.json, R16):
- Level codes (active until resolved): dead-clock, guard-stale, station-root, plan, render.
- Event codes (active until repeat_hours pass without a new fire): publish, prune (step names via _step), publish-state, put-budget, horizon-held, frame-count-drift.
- 2026-10-12T05:17:03-0400 RELAY-READY: tick 9cfe425a deleted; armed-9d1f2929 removed (armed-global kept: other sessions armed); nothing running; STATE.md mode done
