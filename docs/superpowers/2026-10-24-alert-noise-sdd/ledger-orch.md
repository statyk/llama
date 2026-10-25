# SDD ledger — plan: docs/superpowers/plans/2026-10-24-alert-noise-and-hugo-fixes.md
# orchestrator: peer da9a8ced-993b-44c5-a994-b7a9f91a3802, parent llama-69; base df17931
# Spec: docs/superpowers/specs/2026-10-24-alert-noise-and-hugo-fixes-design.md (reachable)

## Escapes
(none)

## Log
2026-10-24T12:58:19-0400 setup: started; read spec + plan in full

## Pre-flight scan (plan vs itself and spec)
| rows | produces → consumes | found |
|---|---|---|
| T1→T2 (alerts.ts) | planAlerts/GATED_KEYS/AlertEntry.streak,pending → dispatchAlerts relay | T1 test R names "the relay write failing" but no relay exists until T2 → ruling R1 |
| T1→T2 (alerts.test.ts alertSink test) | T1 Step 7 substitutes offair-corrupt → T2 rewrites same test against the relay ring | consistent |
| T2→T5 (RelayDoc contract) | RELAY_KEY, ring/stream/seq, relayDocProblem → relay.doc_problem, test_relay_key_matches_antenna reads alerts.ts | consistent (T5 after T2) |
| T3→T4b (service.tick) | interim end_observation(MONITOR) in tick → removed in 4b | consistent |
| T3→T4b/T5 (alerts.py) | MONITOR, end_observation, GATED_CODES, _lock → monitor.run_pass | consistent |
| T4a→T4b | guard_view, make_client kw, check(now, callable) → MonitorLoop, make_reader_client | consistent |
| T4a→T4b (test_service fake monitors) | 4a renames params → 4b replaces both tests | consistent |
| T4b→T5 | open_monitor(st) → open_monitor(st, env=os.environ); MonitorLoop(relay=) | consistent |
| T4b→T6 (test_systemd watchdog count 5) | 4b removes in-tick monitor → T6 asserts 5+len(analyzed) | T6 implementer must re-derive the base count on the post-4b tree; noted in dispatch |
| T1..T6→T7 | names/constants → docs | consistent |
| T1 self | test B counts `immediate: true` literals; doc comment forbidden to contain it | consistent |
| T1 self | tests H, I, M walk-through against Step 6 algorithm | consistent (checked by hand) |
| T2 self | hung write test uses timeout 5 ms; Step 3 withTimeout | consistent |
| T3 self | tests vs Step 4 algorithm (undelivered first message resent) | consistent |
| T4a, T4b, T5, T6, T7 self | tests vs steps | consistent |
| Global "one commit per task" vs brief mandate 4 (commit incrementally) | — | ruling R2 |
| Workspace path: skill's sdd-workspace prints .superpowers/sdd/2026-10-24-alert-noise-and-hugo-fixes; brief names $D=.superpowers/sdd/alert-noise | — | ruling R3 |
| Final gate: docker not running at 12:58 (DOCKER-NOT-RUNNING) | — | reported to llama-69 in first report; STOP at gate if still down (brief) |

Ruling R1: Task 1 test R uses broken email channels only (no relay sink exists yet); Task 2 extends it so both email and the relay fail — the plan's Review Focus #2 names Task 2's own test for the both-fail case — cost if wrong: test R under-covers until Task 2, caught there.
Ruling R2: implementers may make several incremental green commits per task (brief mandate 4 outranks the plan's "one commit per task"); reviewers get BASE..HEAD — cost if wrong: a few more commits in history.
Ruling R3: ledger/log/now in $D/orch; children's dirs and handbacks in $D/<task>/; task briefs and review packages in the skill's plan workspace (.superpowers/sdd/2026-10-24-alert-noise-and-hugo-fixes), also git-ignored — cost if wrong: two scratch dirs instead of one.
Ruling R4: brief order "spec-compliance review (Opus), then code-quality review (Opus)" → two separate reviewer seats per task, spec first, quality after spec passes — cost if wrong: one extra reviewer seat per task.
2026-10-24T13:01:09-0400 baseline: transmitter 459 passed 1 skipped; antenna 385 passed; tsc clean (venv resolves in worktree)
2026-10-24T13:01:09-0400 Task 1: BASE df17931; implementer t1-impl dispatched on Opus (agent a7691716141326fa4), budget 75 min
2026-10-24T13:08:39-0400 Task 1: implementer DONE_WITH_CONCERNS, commit ab72bb0, antenna 401 passed, tsc clean. Concern: gate note only when the send passed the gate (test R vs Step 6 noted(c)); a retried first message after a reset loses the note (cosmetic). Left to the spec reviewer, no pre-judgement.
2026-10-24T13:08:39-0400 Task 1: spec reviewer t1-spec dispatched on Opus (a397e35f50c03c7e9)
2026-10-24T13:11:28-0400 Task 1: spec review ✅ compliant (no Critical/Important). ⚠️ resolved by orchestrator: the "undelivered first message resent, never re-gated" rule is plan text (df17931, plan Review Focus #2, from llama-69's planning round), not spec text; it only makes sending more eager — accepted.
Task 1: minor (deferred): rule-7 edge — a gated-start episode whose first send failed, then a clean-minute reset, retries at streak 1 WITHOUT the gate note (wording only; a fix needs a stored marker not in Interfaces) (alerts.ts:166-168,191)
Task 1: minor (deferred): rule-3 edge — a pending streak over a kept inactive entry is lost when keep() ages it out (7 d) on an incomplete batch; can delay a send ≤2 min, never silences (alerts.ts:212-213, plan-mandated)
Task 1: minor (deferred): test N's equivalence loop is tautological since fallbackReason wraps fallbackCause (metronome-core.test.ts:829-831, plan-mandated); literal-string tests still pin reasons
2026-10-24T13:11:53-0400 Task 1: quality reviewer t1-quality dispatched on Opus (aaa82a04c266fcab9)
2026-10-24T13:15:37-0400 Task 1: quality review Approved (no Critical/Important).
Task 1: minor (deferred): Q1 test N loop tautological (plan-mandated) — same as spec minor 3
Task 1: minor (deferred→T2): Q2 no antenna test for (a) a gated first alert failing at GATE retried next minute WITH the note, (b) storedStreak defensive reads
Task 1: minor (deferred→T2): Q3 header comment says "the one exception" while immediate is a second exception
Task 1: minor (deferred→T2): Q4 never-re-gated ruling fails on one path: a GATE alert replacing a still-active entry whose clearing elapsed, all channels failing -> delivered inherits wasDelivered(prev)=true -> retry has no note, and after a clean minute is re-gated (≤2 min delay)
Task 1: minor (deferred): Q5 "resolves nothing that is absent" adaptation reads less realistically (comment only)
Ruling R5: fold T1 minors Q2, Q3, Q4 into Task 2's dispatch — Task 2 rewrites dispatchAlerts' delivered computation and the header comment, the same code; Q4 is the plan's Review Focus #2 (llama-69's ruling) failing on one path — cost if wrong: Task 2's diff is a little larger.
Task 1: complete (commits df17931..ab72bb0, review clean)
2026-10-24T13:16:09-0400 Task 2: BASE ab72bb0; implementer t2-impl dispatched on Opus (aed3a152f997fda3d), budget 75, with T1 Q2/Q3/Q4 folded in (R5)
2026-10-24T13:24:06-0400 Task 2: implementer DONE_WITH_CONCERNS, commit 16891ae, antenna 425 passed, tsc clean, dry-run builds; Q4 fixed with a stored first_undelivered mark; concerns: seq from max not last (same on a well-formed ring), no note after clean-minute resend (T1 rule), timed-out relay write may land later -> duplicate never loss, docs NTFY left to Task 7
2026-10-24T13:24:33-0400 Task 2: spec reviewer t2-spec dispatched on Opus (afa36b17bb5322759)
2026-10-24T13:27:29-0400 Task 2: spec review ✅ compliant (no Critical/Important).
Task 2: minor (deferred): rule-7 note dropped on the clean-minute resend path (alerts.ts:160-161,180-181; test U(b)); a fix needs a stored "began gated" bit; same class as T1 minor — for the final review / operator
Task 2: minor (deferred): msgs(start).slice(-RELAY_RING) — >50 messages in one invocation would start a new stream above seq 1 (unreachable: key inventory <50)
Task 2: minor (deferred): next seq continues after the ring's max seq, not its last (identical on ascending rings; safer on hand edits) — accepted deviation
Task 2: carry→T5: Python doc_problem must reject seq 1.0 (float) and bool (bool ⊂ int) to mirror relayDocProblem
2026-10-24T13:27:55-0400 Task 2: quality reviewer t2-quality dispatched on Opus (ae264cddf2b95512e)
2026-10-24T13:31:27-0400 Task 2: quality review Needs fixes — 1 Important: I1 the failed-repeat restore arm of first_undelivered (alerts.ts:555) is unpinned (mutant M1 survives 78/78); a second failed resend loses the mark and a later presence is re-gated. Test-only fix.
Task 2: minor (deferred): QM1 relayDocProblem called twice (alerts.ts:471/479); redundant doc.ring[0].at assertion
Task 2: minor (deferred): QM2 alert-relay-failed logs carry no keys/count (alerts.ts:485,498)
Task 2: minor (deferred): QM3 inner .slice(-RELAY_RING) in msgs() untested (mutant M3 survives); seqs start at N-49 past it (theoretical)
Task 2: minor (deferred): QM4 no test for an R2 read failure inside the relay
Task 2: minor (deferred): QM5 a contrived 3-PUT path (race + delete + create throw -> fallback put); fallback could overwrite a racer's ring; spec-mandated pattern from createAlerts; comment worth adding
Task 2: minor (deferred): QM6 alerts.ts now 578 lines; relay block could be relay.ts
Task 2: minor (deferred): QM7 on the Q4 path the old episode's "resolved" says "active since" the failed new episode's first_at (cosmetic)
2026-10-24T13:31:27-0400 Task 2: fix round 1 started — resuming implementer aed3a152f997fda3d (Opus) with I1; FIX_BASE 16891ae
2026-10-24T13:33:06-0400 Task 2: fix round 1 implementer DONE, c5b519a (test-only, mutant proof in scratch), 426 passed, tsc clean; re-reviewer t2-rr1 dispatched on Opus (a4c79b488c86763e9)
Task 2: fix round 1/5 (1 addressed, 0 open — I1 failed-resend mark test; commits 16891ae..c5b519a). Re-reviewer verified the mutant kill in its own scratch copy. Nit: minute-3 kind not observable (non-blocking).
Task 2: complete (commits ab72bb0..c5b519a, review clean after 1 fix round)
2026-10-24T13:34:54-0400 GATE (a): antenna half complete. Orchestrator re-ran: antenna 426 passed (21 files), tsc clean, tree clean. Meter 5h 48%, week 9%. Waiting for llama-69's go.
2026-10-24T13:35:23-0400 GATE (a): GO from llama-69 (commits checked on disk).
Ruling (llama-69, verbatim in substance): the missing "3 consecutive" note on a first message resent after a clean minute is ACCEPTED as is — wording only; no stored "began gated" bit.

## Accepted limitations (for the final review)
- AL1: an undelivered first message resent after a clean minute goes out at once WITHOUT the "3 consecutive" note (antenna alerts.ts noted rule; same on transmitter if mirrored) — llama-69 ruling at gate (a).
2026-10-24T13:35:52-0400 Task 3: BASE c5b519a; implementer t3-impl dispatched on Opus (a8791ec789acafe5c), budget 75
2026-10-24T13:45:34-0400 Task 3: implementer DONE, 103f7d0, transmitter 489 passed 1 skipped (459 before), 13 tests adapted, 9 mutants caught in scratch. Carry→T4b: remove test_the_interim_in_tick_monitor_ends_its_own_observation with the interim call.
2026-10-24T13:46:02-0400 Task 3: spec reviewer t3-spec dispatched on Opus (a7436fc1b00f23d8f)
2026-10-24T13:48:38-0400 Task 3: spec review ✅ compliant, no findings (note → T4b: remove the interim-monitor test)
2026-10-24T13:49:03-0400 Task 3: quality reviewer t3-quality dispatched on Opus (afe0709dfbc8b933d)
2026-10-24T13:52:26-0400 Task 3: quality review Approved, no Critical/Important.
Task 3: minor (deferred→T4b): TM1 observer routing hard-coded (alerts.py:150), not derived from OBSERVER_STEPS
Task 3: minor (deferred→T4b): TM2 lock tests would hang, not fail, on a deadlock (non-daemon threads; release without finally)
Task 3: minor (deferred): TM3 wrappers test asserts one log for two calls; no test that a refused end_observation leaves state unchanged
Task 3: minor (deferred→T4b): TM4 docstring/_lock comment say "the monitor thread" before 4b makes one
Task 3: minor (deferred): TM5 test_a_publish_locked_step_neither_advances_nor_resets over-claims in its name
Task 3: note→T4b: TM6 the lock is held across _send (~30 s worst case); 4b must add no network I/O under the lock
Ruling R6: fold T3 minors TM1, TM2, TM4 and note TM6 into Task 4b's dispatch (4b creates the monitor thread these concern) — cost if wrong: 4b slightly larger.
Task 3: complete (commits c5b519a..103f7d0, review clean)
2026-10-24T13:53:51-0400 Task 4a: BASE 103f7d0; implementer t4a-impl dispatched on Sonnet (a60ba188c796fc060), budget 60. Meter 5h 58%.
2026-10-24T13:56:16-0400 Task 4a: implementer DONE, 4309df6, 494 passed 1 skipped; concern: empty list [] for GUARD_KEY gives blocked False (pre-existing behaviour)
2026-10-24T13:56:41-0400 Task 4a: spec reviewer t4a-spec dispatched on Opus (a6b675ee7e7e4cc8f)
2026-10-24T13:57:35-0400 Task 4a: spec review ✅ compliant, no Critical/Important.
Task 4a: minor (deferred): guard_view test is sequential asserts, brief said parametrized
Task 4a: note (final review): a guard doc of [] (falsy) reads blocked=False — fail-open, PRE-EXISTING at 103f7d0, preserved per spec ("exactly as today"); flag to operator, not this branch's scope
2026-10-24T13:57:58-0400 Task 4a: quality reviewer t4a-quality dispatched on Opus (a27a63c94fd5aff86)
2026-10-24T14:00:11-0400 Task 4a: quality review Approved, no Critical/Important.
Task 4a: minor (deferred→T4b): AM1 check()'s comment promises a raising/hanging guard read cannot stop the playlist check; true only because guard_view never raises — wrap guard_view() in check() so any callable fails closed (spec Part 3 "no guard-read outcome can stop the playlist check")
Task 4a: minor (deferred→T4b): AM2 the single-writer text pin misses atomic_write_text / .write_text / a variable path; widen the regex cheaply
Task 4a: minor (deferred): AM3 cache-content assertion compares guard_view to itself (values pinned elsewhere)
Task 4a: minor (deferred): AM4 test_a_failing_guard_read_cannot_stop_the_playlist_check name over-claims (passes a failed-closed dict, not a raising callable)
Task 4a: note (final review): AM5 = the pre-existing falsy guard.json fail-open (publish.py:79), already noted
Task 4a: minor (deferred): AM6 str(exc) may be "" (bare TimeoutError) -> guard-stale message ends ": " (pre-existing, cosmetic)
Ruling R7: fold AM1 and AM2 into Task 4b (4b passes guard_view into check from the monitor thread and owns the monitor-only-reads strict test) — cost if wrong: 4b slightly larger.
Task 4a: complete (commits 103f7d0..4309df6, review clean)
2026-10-24T14:01:49-0400 Task 4b: BASE 4309df6; implementer t4b-impl dispatched on Opus (a0b8b309e749a6b3d), budget 80, with R6/R7 folds. Meter 5h 62%.
2026-10-24T14:02:03-0400 Ruling (llama-69): falsy non-dict guard.json reads not-tripped (publish.py:79) is OUT OF SCOPE — pre-existing, spec keeps "exactly as today", only the Worker writes it. Filed follow-up, not an accepted limitation; 4b does not change it.

## Filed follow-ups (out of scope for this branch)
- FU1: publish.py:79 `bool(doc and ...)` — a falsy non-dict guard.json ([], "", 0) reads as not tripped instead of failing closed (llama-69 ruling 14:02).
2026-10-24T14:15:19-0400 Task 4b: implementer DONE_WITH_CONCERNS, 26cd106..fe6ee81 (3 commits), 518 passed 1 skipped (5 runs), 9 mutants (M8 survived -> new test 519bc73). Concerns: private publish._error_code reuse; no e2e Runner.run with real MonitorLoop; BaseException kills thread (-> monitor-stalled by design); --once docs to T7.
2026-10-24T14:16:39-0400 Task 4b: spec reviewer t4b-spec dispatched on Opus (a3cb52d384e2fc323). Meter 5h 71%, week 12%.
2026-10-24T14:18:35-0400 Task 4b: spec review ✅ compliant, no Critical/Important.
Task 4b: minor (deferred): a raising monitor.stalled() propagates out of tick (after end_observation) and would end run(); theoretical (real stalled() reads monotonic/is_alive); pinned by test with pytest.raises — passed to quality reviewer
Task 4b: minor (deferred): code_observers also refuses a gated code declared by no step (a strengthening)
2026-10-24T14:20:22-0400 Task 4b: quality reviewer t4b-quality dispatched on Opus (ab472c6bf4454c7ee). Meter 5h 72%.
2026-10-24T14:22:41-0400 Task 4b: quality review Approved, no Critical/Important.
Task 4b: minor (deferred→T5): BM1 _check_monitor is the only tick step that can raise out of tick (a raising stalled() ends run(); Restart=always -> restart loop); test pins propagation with pytest.raises — make it non-raising (fail toward alerting) and re-pin
Task 4b: minor (deferred→T5): BM2 MonitorLoop.start() assigns _thread before Thread.start(); a failed start makes stop()'s join raise and mask the error
Task 4b: minor (deferred→T5): BM3 monitor.R2Reader imports private publish._error_code — make a public helper
Task 4b: minor (deferred): BM4 guard-cache half of the strict-surface test near vacuous (MonitorLoop has no workspace); an AST pin would be sharper
Task 4b: minor (deferred): BM5 redundant assertion test_service.py:1230
Task 4b: minor (deferred): BM6 service imports both monitor module and MonitorLoop; Runner.__init__ param shadows module
Task 4b: minor (deferred): BM7 stop() leaves started True (means "was ever started")
Ruling R8: fold BM1, BM2, BM3 into Task 5 (Task 5 edits service.open_monitor and uses R2Reader for the relay; BM1 is stake (b)) — cost if wrong: Task 5 slightly larger.
Task 4b: complete (commits 4309df6..fe6ee81, review clean)
2026-10-24T14:23:57-0400 Task 5: BASE fe6ee81; implementer t5-impl dispatched on Opus (a0f48dccda35c22aa), budget 75, with R8 folds + doc_problem bool/float carry. Meter 5h 75%.
2026-10-24T14:24:14-0400 RELAY-NOW received from llama-69: finish Task 5 through reviews/fix rounds (unless the 85% brake trips: then let in-flight finish, dispatch nothing more), write HANDOFF, disarm tick, report RELAY-READY.
2026-10-24T14:35:36-0400 Task 5: implementer DONE, 7d70486 (BM3) 59bad2f (BM1+BM2) 1f2f779 (relay); 567 passed 1 skipped (518 before); 9 targeted mutants caught. Concerns: debian12 not run (3.11.15 parse + smoke, fromisoformat accepts Z); duplicate seqs in one ring would each send (antenna never writes them); relay-only config now builds the reader client (needs R2 keys, which run already needs). Meter 5h 79%.
Ruling R9: under RELAY-NOW and the 85% brake, Task 5's spec and quality reviewers run concurrently (both Opus) instead of sequentially (R4) — cost if wrong: the quality reviewer may review code the spec review sends back.
2026-10-24T14:36:26-0400 Task 5: spec reviewer t5-spec (a5424db9c8194efeb) and quality reviewer t5-quality (a110bb8649d0b3014) dispatched concurrently on Opus
2026-10-24T14:38:47-0400 Task 5: spec review ✅ compliant, no Critical/Important (⚠️ debian12 not run — final gate).
Task 5: minor (deferred): relayed body marker "({key}, {at})" vs brief literal "({at})" — builder's call per spec; accepted
Task 5: minor (deferred): cursor written only on change, a failed write retried only when it next moves (brief-mandated; covered by spec Limits)
Task 5: minor (deferred): 4b's monitor strict-surface test builds MonitorLoop without a relay (no-put holds by construction)
2026-10-24T14:40:22-0400 Task 5: quality review Needs fixes — 1 Important: I1 a message ntfy can never accept (newline in Title header -> ValueError; lone surrogate -> UnicodeEncodeError) stops the relay at that seq every pass, so every later relayed alert (incl. tripped-spend) waits up to 1 h for ntfy (email unaffected). Reviewer measured it.
Task 5: minor (deferred): QM1 a same-stream cursor above the ring's max relays nothing silently (hand-edit/backup restore only)
Task 5: minor (deferred): QM2 a 401/403 from ntfy (bad NTFY_TOKEN) skips every message with one WARNING each, spec-mandated; suggest clearer log / spec follow-up
Task 5: minor (deferred): QM3 test_monitor.py monkeypatch.undo() mid-test also reverts the fired fixture
Task 5: minor (deferred): QM4 urllib follows 301/302 on POST as a body-less GET, so the OSError("ntfy: HTTP 302") branch is unreachable and a redirected POST can "succeed" — pre-existing NtfyChannel behaviour shared with the Dispatcher (out of scope)
Task 5: minor (deferred): QM5 cloudstate imports error_code as _code (cosmetic)
Ruling R10: fix I1 with both (a) relay-side sanitising in format_message (CR/LF -> space in the subject; lone surrogates made encodable) and (b) a ValueError from send treated as a per-message skip with a WARNING — (a) delivers the alert, (b) keeps "a bad entry always advances" for any other deterministic local failure — cost if wrong: one more except arm.
2026-10-24T14:40:22-0400 Task 5: fix round 1 started — resumed implementer a0f48dccda35c22aa (Opus); FIX_BASE 1f2f779. Meter 5h 83%.
Task 5: fix round 1 implementer DONE, b9967b0 (relay.py only: (a) subject CR/LF -> space, lone surrogates -> "?"; (b) ValueError/UnicodeError from send = per-message skip + WARNING); 572 passed 1 skipped; 5 new tests incl. real NtfyChannel over a 127.0.0.1 server; both halves mutant-proven in scratch.
2026-10-24T14:44:12-0400 BRAKE: meter 5h 85% at 14:43 (week 14%) — treated as tripped (1-pt quantization); no further dispatches. Task 5 fix round 1 re-review NOT run.

## HANDOFF (2026-10-24T14:44:12-0400)

**State.** Branch alert-noise, worktree /Users/shawn/projects/llama/.claude/worktrees/alert-noise, HEAD b9967b0, tree clean. Orchestrator re-ran at handoff: transmitter `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q` = 572 passed, 1 skipped; antenna `npm test` = 426 passed; `npx tsc --noEmit` clean. `transmitter.__file__` resolves inside the worktree (worktree .venv exists; antenna node_modules installed).
Baselines at df17931: transmitter 459 passed 1 skipped; antenna 385.

**Tasks.** 1 complete (df17931..ab72bb0). 2 complete (ab72bb0..c5b519a, 1 fix round). 3 complete (c5b519a..103f7d0). 4a complete (103f7d0..4309df6). 4b complete (4309df6..fe6ee81). Gate (a) passed (llama-69 GO 13:35).
**Task 5: IN FIX LOOP.** Implementer commits fe6ee81..1f2f779 (7d70486 BM3, 59bad2f BM1+BM2, 1f2f779 relay). Spec review ✅ (t5-spec). Quality review Needs fixes, 1 Important I1 (t5-quality/handback.md). Fix round 1 done: b9967b0 (t5-impl/handback.md "Fix round 1", sentinel done-fix1).
**NEXT ACTION:** the scoped re-review of Task 5 fix round 1 (Opus): `bash <sdd skill>/scripts/review-package docs/superpowers/plans/2026-10-24-alert-noise-and-hugo-fixes.md 1f2f779 b9967b0`, re-review-prompt with finding I1 verbatim from t5-quality/handback.md, brief .superpowers/sdd/2026-10-24-alert-noise-and-hugo-fixes/task-5-brief.md, report t5-impl/handback.md. Use a NEW task name (e.g. t5-rr1). If addressed → ledger "Task 5: fix round 1/5 ..." + "Task 5: complete (commits fe6ee81..b9967b0, ...)" → GATE (b): stop and report to llama-69 for go. Then Task 6 (implementer Sonnet), Task 7 (Sonnet), final gate, final whole-branch review (Opus), finish menu.
Implementer model assignments (llama-69): Opus for 1, 2, 3, 4b, 5; Sonnet for 4a, 6, 7. Every reviewer Opus.

**Carry into Task 6:** test_systemd.py's watchdog count — after 4b the in-tick monitor is gone; re-derive the base count on the current tree before asserting `5 + len(st.engine.analyzed)` (pre-flight scan row).
**Carry into Task 7 (docs):** `--once` wording (runs one check on the main thread, no relay, no thread); the relayed body marker "-- relayed from antenna (<key>, <at>)"; R2 error helper is `r2.error_code`; cursor file `~/.transmitter/alert-relay-cursor.json`.

**Rulings (all in the Log above, with costs):**
- R1 Task 1 test R used broken email only; Task 2 extended it with a failing relay.
- R2 incremental commits allowed per task.
- R3 ledger in $D/orch; briefs/review packages in .superpowers/sdd/2026-10-24-alert-noise-and-hugo-fixes.
- R4 spec then quality as two sequential Opus seats (R9 overrode it for Task 5 only: concurrent, under RELAY-NOW).
- R5 T1 minors Q2/Q3/Q4 folded into T2 (Q4 = never-re-gated rule's failing path; fixed with a stored first_undelivered mark).
- R6 T3 minors TM1/TM2/TM4/TM6 folded into T4b.
- R7 T4a minors AM1/AM2 folded into T4b (check() wraps guard_view() fail-closed; widened single-writer regex).
- R8 T4b minors BM1/BM2/BM3 folded into T5 (_check_monitor never raises; start() safe; public r2.error_code).
- R9 Task 5 reviewers concurrent.
- R10 Task 5 I1 fixed with both relay-side sanitising and a ValueError-skip arm.
- llama-69 rulings: gate (a) GO; AL1 accepted; FU1 out of scope.

**Accepted limitations:** AL1 — an undelivered first message resent after a clean minute goes out at once WITHOUT the "3 consecutive" note (antenna; wording only) — llama-69 ruling at gate (a).
**Filed follow-ups (out of scope):** FU1 — publish.py:79 a falsy non-dict guard.json ([], "", 0) reads not-tripped instead of failing closed (pre-existing; llama-69 ruling 14:02).
**Deferred minors:** every "minor (deferred)" line in the Log above — point the final whole-branch review at them.

**Docker:** daemon NOT running (12:58, `docker info` failed). The final gate's `packages/transmitter/scripts/test-in-debian12.sh` needs it; per the brief, STOP and report at the final gate if still down. Partial 3.11 evidence: T3/T5 implementers and the T5 spec reviewer parsed touched files under a real Python 3.11.15; `fromisoformat` accepts "Z" on 3.11.15.

**Children:** none running. Last dispatches: t5-impl (Opus, fix round 1 done), t5-spec (Opus, done), t5-quality (Opus, done). Names used so far (single-use): t1-impl t1-spec t1-quality t2-impl t2-spec t2-quality t2-rr1 t3-impl t3-spec t3-quality t4a-impl t4a-spec t4a-quality t4b-impl t4b-spec t4b-quality t5-impl t5-spec t5-quality.
2026-10-24T14:44:22-0400 tick caa994f8 deleted; armed-da9a8ced removed; armed-global kept (other armed-* flags present). No children, shells or Monitors running. RELAY-READY.
