# SDD ledger — plan: docs/superpowers/plans/2026-10-15-antenna-metronome.md
peer session 7c48a24a-b1ba-48f0-8b4d-9a045fdbda5f; worktree /Users/shawn/projects/llama/.claude/worktrees/antenna-metronome; branch antenna-metronome; start 04849bf; started 2026-10-15T01:21:54-0400
SDD workspace (briefs, review packages): /Users/shawn/projects/llama/.claude/worktrees/antenna-metronome/.superpowers/sdd/2026-10-15-antenna-metronome

## Escapes
(none)

## Task 0
Task 0: complete (no commit; baseline npm ci + npm test 236 passed (236) + npm run typecheck clean; worktree pre-created by parent, git worktree add skipped per brief)

## Preflight conflict scan (interfaces read from each task's Files/Interfaces blocks)
| pair / task | produces vs consumes | finding |
|---|---|---|
| T1->T4 | live.ts renderLive | T4 consumes renderLive: matches T1 produce |
| T1->T6 | live.ts putLive(bucket, body, liveMaxAge) | T6 consumes putLive: matches |
| T1->T7 | live.ts offairWithoutFallback | T7 consumes it: matches (spec reading 11) |
| T1/T2/T3/T7 clock.ts | T1 moves LIVE_KEY (re-export), T2 adds ClockEnv.METRONOME, T3 re-exports GRID_D from grid.ts, T7 lease table | sequential edits to one file, no contradiction; core never imports clock.ts (T3), clock imports core (T7): no cycle |
| T2->T6 | ClockEnv.METRONOME; AntennaEnv extends ClockEnv (verified in src/env.ts) | T6 adds METRONOME_DO only: consistent |
| T2->T7 | test/support.ts usageResponse DO defaults | T7 tests run through guard: defaults non-zero so empty-is-zero check passes; consistent |
| T3->T4/T5/T6/T7 | metronome-core exports list | T4 consumes core + clock.ts ClockConfig/MAX_LOOP_MS (both exist in clock.ts at 04849bf); T6 consumes METRONOME_NAME, RENEW_TIMEOUT_MS, STORAGE_KEYS; T7 consumes fallbackReason/holdLease/playLease: all in T3's produce list |
| T4->T5 | engine internals serial/episode/begin/flush/disarm/write; metronome-support.ts | T5 extends both files T4 creates: consistent |
| T4/T5->T6 | MetronomeEngine, MetronomePort | T6 binds port: consistent |
| T6->T7 | metronomeClient; index.ts exports class (T6), wiring (T7) | consistent |
| T1 self | pure refactor; existing clock tests unchanged | ok |
| T2 self | pricing.test.ts rewrite + 5 test files | ok |
| T3..T7 self | per-task counts 240/252/278/304/329/342/364 | will check per task |
| T8 self | docs only | ok |
Ruling: one combined Opus task reviewer per task (the SDD skill's current task-reviewer template returns both a spec-compliance and a code-quality verdict) rather than two separate seats — the installed skill merged the seats and both verdicts are still required — if wrong, a strict-surface task gets one independent seat instead of two; llama-ed can overrule and I re-review that task with a second seat.
Ruling: T0 baseline run by the orchestrator itself (no implementer) — it is verification only, no code — costs nothing if wrong (no commit).

## Tasks
- 2026-10-15T01:22:33-0400 T1 implementer dispatched: sonnet, agent ae870c4b195c672ba, BASE 04849bf
- 2026-10-15T01:22:55-0400 llama-ed override of the review-seat ruling: two separate Opus seats (spec-compliance, then code-quality) on Tasks 2,3,4,5,7; one combined Opus reviewer on 1,6,8.
- 2026-10-15T01:23:53-0400 T1 implementer DONE 0d4d348 (240 passed, typecheck clean; skipped RED); T1 combined reviewer dispatched: opus, agent a1a75d3cfc1109878
- 2026-10-15T01:24:57-0400 T1 review: spec ✅, quality Approved, 0 C/0 I. ⚠️ test count resolved by orch: t1-impl.log shows 240 passed.
Task 1: minor (deferred): live.test.ts:16,22 substring asserts (last segment / MEDIA-SEQUENCE not line-anchored) — plan-mandated text
Task 1: minor (deferred): offairWithoutFallback "has len < 1" branch untested (pre-existing gap, now in live.ts)
Task 1: minor (deferred): live.ts:2 doc comment forward-references metronome-engine.ts (plan-mandated)
Task 1: minor (deferred): RED step skipped by implementer (process)
Task 1: complete (commits 04849bf..0d4d348, review clean)
- 2026-10-15T01:25:24-0400 T2 implementer dispatched: opus, agent a5683fca8c416197f, BASE 0d4d348
- 2026-10-15T01:28:08-0400 T2 implementer DONE 7c6b69b (252 passed per log, typecheck clean); T2 spec reviewer dispatched: opus, agent a8af5dbf6dc871d74
- 2026-10-15T01:30:00-0400 T2 spec review: Pass, 0 C/0 I/0 M; ⚠️ live GraphQL fields (Task 9) and METRONOME var absent from wrangler.jsonc (Task 6) — both cross-task, expected. T2 quality reviewer dispatched: opus, agent a76e1f0fb6fe394e2
- 2026-10-15T01:32:20-0400 T2 quality review: Approved, 0 C/0 I, 3 minors.
Task 2: minor (deferred, CARRY to T4): guard's empty-is-not-zero relies on every renew() writing >=1 row (stalls) in every lease state incl. stalls 0->0, hold, null — T4 must pin it with a test (plan reading 4)
Task 2: minor (deferred, CARRY to T8): long metronome-down with METRONOME=on blind-trips ~9h in; runbook must say flip METRONOME off (plan Review Focus 4 already assigns this to T8 section 9)
Task 2: minor (deferred): latch.ts:204 fractional Set rebuilt per stored() call (plan-verbatim)
Task 2: complete (commits 0d4d348..7c6b69b, review clean)
- 2026-10-15T01:32:49-0400 T3 implementer dispatched: opus, agent ab24741e8e0f0d286, BASE 7c6b69b
- 2026-10-15T01:34:40-0400 T3 implementer DONE fb30bd5 (278 passed per log, typecheck clean; concerns: stalledFor huge if live with playSince+lastAlarmGoodAt null -> engine must keep playSince set (CARRY to T4/T5); validateLease ignores published_at/container; isLive offair:false; NaN expiresAt -> expired). T3 spec reviewer dispatched: opus, agent a1aae0c9954e1a0ee
- 2026-10-15T01:36:46-0400 T3 spec review: Pass, 0 C/0 I, 3 minors. ⚠️ items all cross-task (T4/T5 engine invariants) — carried into T4/T5 dispatches.
Task 3: minor (deferred): parseStoredLease accepts Infinity/far-future expiresAt (storage corruption only; strict surface — final review to triage)
Task 3: minor (deferred): validateLease keeps raw.horizon by reference; extra fields persist in stored lease (size bounded only by cron)
Task 3: minor (deferred): fallbackOrNull requires finite len (stricter than spec; fail-closed)
- 2026-10-15T01:37:04-0400 T3 quality reviewer dispatched: opus, agent a13f3a611051b25e0
- 2026-10-15T01:42:20-0400 T3 quality review: Needs fixes, 0 C / 2 I (both plan-mandated) / 4 minors; 17/20 mutants caught.
Ruling: T3 I-1 (test:199 toEqual({lease: undefined}) pins nothing) — FIX with toStrictEqual: the plan's own contract (removed lease => key deleted) is what T4 consumes, and the assertion as written is vacuous — cost if wrong: none (a stricter assert of the same intended behavior).
Ruling: T3 I-2 (capAllows opens on NaN nowMs) — FIX with a Number.isFinite guard returning false, asserted inside the EXISTING cap test (no new it-block) so the plan's per-task counts 278/304/... stay valid — the global constraint "NaN or missing values trip, never pass" outranks the plan's verbatim code — cost if wrong: a NaN clock would stop the DO writing (cron falls back), which is the intended fail-closed direction.
Task 3: minor (deferred): parseStoredLease/readState don't bound expiresAt on load (Infinity never expires) — dup of spec-seat minor; final review triage
Task 3: minor (deferred): validateLease keeps horizon by reference (dup of spec-seat minor)
Task 3: minor (deferred, FINAL REVIEW ATTENTION): fallbackReason (c) written positively — NaN/undefined stalls never trips; applied "accepted" + lease "none" (cron clock >15 min behind DO) is not a trigger
Task 3: minor (deferred): untested boundaries: inWindow at exactly 60000 ms; readState negative stalls; stalledFor(true,null,null) — T4 must keep playSince set while live
- 2026-10-15T01:42:35-0400 T3 fix round 1 dispatched: resumed implementer ab24741e8e0f0d286 (opus) with I-1, I-2; FIX_BASE fb30bd5
- 2026-10-15T01:44:04-0400 T3 fix round 1 implementer DONE bec70fb (278 passed, RED shown for NaN). T3 re-reviewer dispatched: opus, agent a349806ebdd69559e
- 2026-10-15T01:44:54-0400 T3 re-review r1: both ADDRESSED, no new breakage.
Task 3: fix round 1/5 (2 addressed, 0 open — vacuous removed-lease assert; NaN opens cap; commits fb30bd5..bec70fb)
Task 3: minor (deferred, CARRY to T4): recordTime with NaN nowMs empties history and stores [NaN]; T4 call sites must check capAllows before recordTime with the same clock
Task 3: complete (commits 7c6b69b..bec70fb, review clean)
- 2026-10-15T01:45:18-0400 T4 implementer dispatched: opus, agent ae01433d6b4cb924f, BASE bec70fb; carry-t4.md given
- llama-ed instruction (T3 core fail-open fix round, AFTER T4 committed+reviewed, BEFORE T5, no concurrent writer; Opus implementer + Opus re-review; one test per item; record count shifts):
  (1) stored lease with non-finite expiresAt (Infinity/NaN/missing) loads as invalid: deleted, treated as no lease; on accept expiresAt stays min(validUntil, now+LEASE_MS) on DO clock
  (2) fallbackReason written negated: NaN/non-integer stalls triggers (c)
  (3) cron sent unblocked play, applied "accepted", reply lease != "play" (e.g. "none", cron clock >15 min behind) => trigger (b), fall back + metronome-down (spec decision R1)
- 2026-10-15T01:48:11-0400 T4 implementer DONE_WITH_CONCERNS aeef49d (304 passed, typecheck clean); invariants 1,2,5,6,7 pinned (mutation-checked in scratch); 3 (nextTarget max(now,lastTarget)) unpinned; 4 (recordTime keep) half-pinned; timed-out PUT continues in background (stale overwrite race)
- 2026-10-15T01:48:38-0400 T4 spec reviewer dispatched: opus, agent a6fc4b6b624c38db4
- 2026-10-15T01:51:29-0400 T4 spec review: Pass, 0 C/0 I, 3 minors (coverage). ⚠️ (a) a throw in arm step skips final flush (stalls/lastTarget/lastBody=null not persisted; renew rejects => cron trigger (a); spend bounded) — final review; (b) alarm-side rules are T5.
Task 4: minor (deferred): max(now,lastTarget) unpinned in renew (suggest assert alarmAt === E+1002*D+25 in "a lagging older blocked lease" test)
Task 4: minor (deferred): recordTime keep value unpinned (putTimes <= 10)
Task 4: minor (deferred): cap-skipped renew write then chain re-arms — not asserted
Task 4: minor (deferred): timed-out PUT keeps running; may land after a later PUT (stale playlist briefly) — implementer observation; final review
- 2026-10-15T01:51:47-0400 T4 quality reviewer dispatched: opus, agent a816c813109fcc7db
- 2026-10-15T01:56:01-0400 T4 quality review: Approved, 0 C/0 I, 8 minors.
Task 4: minor (deferred, CARRY to T5): pin invariant 3 max(now,lastTarget) and 4 (keep) in T5 tests if T5's brief allows; else final review
Task 4: minor (FOLDED into core fix round): invalid-lease path flush(tx,true) unpinned — empty-is-not-zero case (invalid lease, empty store, stalls 0->0) — add assertion inside existing test
Task 4: minor (deferred, FINAL REVIEW ATTENTION, flagged to llama-ed): alarm-op failure skips lease persist (engine:205-222) — accepted hold not saved if setAlarm/deleteAlarm throws; old play lease may tick until its own expiry; renew rejects so cron falls back
Task 4: minor (deferred): "logged once" test asserts 1..3 range; dedup in episode() unpinned
Task 4: minor (deferred): LATE_LOG_MS, MAX_ALARMS_PER_MINUTE, confirms unused until T5 (check at T5 review)
Task 4: minor (deferred): timed-out PUT may land after a later PUT (R2 put has no abort) — add a known-limitations line (T8 docs / final review)
Task 4: minor (deferred): renew(undefined) maps to null — T6 RPC must not rely on undefined meaning invalid
Task 4: complete (commits bec70fb..aeef49d, review clean)
Ruling: core fix round (llama-ed's items 1-3) also folds T4 quality minor 3 (pin "save stalls" on the invalid-lease path, as an assertion inside an existing test) — it is the empty-is-not-zero spend/guard case and test-only — cost if wrong: one extra assertion.
Ruling: T4 minor 4 (alarm-op failure skips lease persist) NOT folded — it changes plan code that T5's verbatim engine code builds on; flagged to llama-ed — cost if wrong: on an alarm-op throw an accepted hold is not persisted until the next renew (<=1 min) or old lease expiry (<=15 min), with cron already falling back.
- 2026-10-15T01:56:22-0400 core fix round implementer dispatched: opus, agent a63448bd924fdd4df, FIX_BASE aeef49d; expected 307; later per-task counts become T5 332, T6 345, T7 367 (plan +3)
- 2026-10-15T01:57:09-0400 llama-ed: fix renew step-5 ordering as a SECOND sequential fix (after core-fix commit + re-review pass): flush lease before setAlarm/deleteAlarm; test: alarm op throws on a renew accepting hold/blocked => stored lease is that hold/blocked lease (and next alarm() writes nothing, no re-arm). Opus impl + Opus re-review. Brief T5: renew's flush precedes alarm ops; adapt anchors not behaviour; report real conflicts.
Ruling: the "next alarm() writes nothing and does not re-arm" half of llama-ed's test cannot exist before T5 (alarm() is added in T5) — second fix tests the stored-lease half now (+1 it => 308); the alarm() half is carried into the T5 dispatch as one added test (T5 expected 333, T6 346, T7 368) — cost if wrong: one test lands a task later.
- 2026-10-15T02:00:07-0400 core fix implementer DONE_WITH_CONCERNS 2dfda92 (307 passed, typecheck clean; RED/GREEN each). Departures: (b) reason string gains lease=; existing 'missing expiresAt loads as expired' test rewritten to finite-past expiresAt; item 4 pinned as 'save lease,stalls' in line-64 test; blocked accepted-but-expired gives no (b) (per brief)
- 2026-10-15T02:00:28-0400 core fix re-reviewer dispatched: opus, agent af9c42094348b6b04
- 2026-10-15T02:03:23-0400 core fix re-review: Items 1-4 ADDRESSED, departures (a)-(c) accepted, no new breakage; observation (d): blocked play lease accepted already-expired => neither writer runs, no ENDLIST, no metronome-down (fails toward zero cost).
Core fix round 1/1 (4 addressed, 0 open; commits aeef49d..2dfda92)
Ruling: fold (d) into the second fix round — generalize trigger (b) to s.lease !== (sent.blocked ? "blocked" : "play") (after acceptance, not doing what it was told), fix the existing (b) loop test's impossible blocked reply (lease "play" for a blocked lease), extend the item-3 test with the blocked case (no new it) — same principle llama-ed ruled for item 3 (decision R1), strict surface, tiny — cost if wrong: cron's fallback writes the off-air notice in a >15-min-skew case where it otherwise would not (bounded by cron's MAX_PUTS).
- 2026-10-15T02:03:42-0400 second fix implementer dispatched: opus (resumed a63448bd924fdd4df), task t4fix-impl, FIX_BASE 2dfda92; expected 308
- 2026-10-15T02:06:21-0400 second fix implementer DONE d555ee2 (308 passed, typecheck clean; RED/GREEN both; +1 storage write per accepted renew; FakePort.failDeleteAlarm added)
- 2026-10-15T02:06:41-0400 second fix re-reviewer dispatched: opus, agent a03221a0cb3456978
- 2026-10-15T02:08:52-0400 second fix re-review: A and B ADDRESSED, no new breakage; +1 row/renew worst case (~44k/month vs 50M) — no spend bound change.
Second fix round 1/1 (2 addressed, 0 open; commits 2dfda92..d555ee2)
CORRECTION of expected counts (my arithmetic error earlier): base now 308; T5 = 308 + 25 (plan delta) + 1 (alarm half of llama-ed's step-5 test) = 334; T6 = 334 + 13 = 347; T7 = 347 + 22 = 369.
- 2026-10-15T02:09:12-0400 T5 implementer dispatched: opus, agent aaf15c4a3d86910cf, BASE d555ee2; carry-t5.md; expected 334
- 2026-10-15T02:13:01-0400 T5 implementer DONE 4ecc3c4 (334 passed, typecheck clean; no anchor conflict; added test RED via scratch mutant; max(now,lastTarget) pinned; stored list lengths unpinned at engine level; T4 unused names now used)
- 2026-10-15T02:13:21-0400 T5 spec reviewer dispatched: opus, agent adb1543024eaa725d
- 2026-10-15T02:18:26-0400 T5 spec review: FAIL on 1 Important (plan-mandated): step 2b duplicate builds for now; after an EARLY genuine tick (built for boundary 1001) a pre-boundary duplicate PUTs segment-1000 playlist, MEDIA-SEQUENCE goes backwards (probe: puts 2->3, seq 998->997). Renew has the same sibling (probe: renew at target-35 after early tick, seq 998->997). Spend bounded (capped); continuity + backwards seq. ⚠️ duplicate-detection via getAlarm() pending is T6/T9. Minors: carry test can't tell step-2 return from catch-all (assert no metronome-alarm-error); stored list lengths unpinned at engine level; cap window edge 60000 unpinned.
Ruling: T5 I-1 — fix in this task's fix loop, option A: the duplicate (2b) AND renew's live write build for due = max(now, lastTarget − D − ALARM_SLACK_MS) (the boundary the last genuine tick built for; when lastTarget was set by renew's own arm or is stale/absent this reduces to now) — spec's "a duplicate rebuilds the same bytes and skips the PUT" + Review Focus 5 "MEDIA-SEQUENCE never goes backwards" bind; option B (refuse lower MEDIA-SEQUENCE than lastBody) rejected because the off-air notice is numbered from now+75 s, so a legitimate return-to-live after a block lowers MEDIA-SEQUENCE and B would freeze it — cost if wrong: a write built up to ~one early-delivery margin ahead of now (same bytes as the genuine tick already PUT), never further. Tests: +2 it (alarm early-tick+duplicate; renew early-tick+renew) => T5 336, T6 349, T7 371. Also fold spec-minor 1 (assert no metronome-alarm-error in the carry test; assertion only).
- 2026-10-15T02:18:47-0400 T5 fix round 1 dispatched: resumed implementer aaf15c4a3d86910cf (opus); FIX_BASE 4ecc3c4; expected 336
- 2026-10-15T02:20:36-0400 T5 fix r1 DONE 72858f6 (336 passed; tickBoundary helper using gridOf(...).dMs; 2 tests RED->GREEN)
- 2026-10-15T02:20:54-0400 T5 re-reviewer dispatched: opus, agent a1ab34e18da04bc7b
- 2026-10-15T02:23:04-0400 T5 spec re-review r1: Important ADDRESSED, folded minor ADDRESSED, no new breakage.
Task 5: fix round 1/5 (2 addressed, 0 open — pre-boundary duplicate/renew older playlist; carry test alarm-error assert; commits 4ecc3c4..72858f6)
Task 5: minor (deferred, CARRY to T7/final): theoretical corner — hold/blocked renew disarms pending alarm, play renew arms from stale future lastTarget skipping one boundary; needs 3 renews in one segment
Task 5: minor (deferred): stored putTimes/alarmTimes length unpinned at engine level; alarm-cap window edge 60000 unpinned
- 2026-10-15T02:23:26-0400 T5 quality reviewer dispatched: opus, agent a003f290a61e0a664 (diff d555ee2..72858f6)
- 2026-10-15T02:26:39-0400 T5 quality review: Approved, 0 C/0 I, 3 minors (surviving mutants, scratch-copy verified).
Task 5: minor (deferred, FINAL REVIEW ATTENTION): capped write confirming tick unpinned (mutant confirms||cap survives) — would hide a frozen playlist from cron; fix: assert lastAlarmGoodAt null after capped deliver
Task 5: minor (deferred, FINAL REVIEW ATTENTION): duplicate path's write-when-bytes-differ unpinned (retry after re-armed-but-died handler)
Task 5: minor (deferred): step 2 "delete pending alarm" unpinned (deliverDuplicate in must-not-tick cases)
Task 5: complete (commits d555ee2..72858f6, review clean)
- 2026-10-15T02:27:09-0400 T6 implementer dispatched: sonnet, agent a73a6b94a9e47dd31, BASE 72858f6; carry-t6.md; expected 349
- 2026-10-15T02:28:46-0400 T6 implementer DONE b737d8b (349 passed x2, typecheck clean; dry-run lists METRONOME_DO + METRONOME off; getAlarm-null on genuine delivery shown only indirectly)
- 2026-10-15T02:29:08-0400 T6 combined reviewer dispatched: opus, agent afcdd0235269f5b48
- 2026-10-15T02:33:01-0400 T6 review: spec Pass, quality Approved, 0 C/0 I, 4 minors. Reviewer's scratch probe (real workerd delivery, no runDurableObjectAlarm): getAlarm() null inside alarm(), re-armed, no metronome-duplicate — 1 passed.
Task 6: minor (deferred, FINAL REVIEW ATTENTION): "alarm ticks and re-arms" test credits getAlarm-null to workerd but runDurableObjectAlarm deletes the alarm first; committed evidence for spec reading 9 is indirect — consider committing the reviewer's ~1 s real-delivery probe (scratchpad/t6probe)
Task 6: minor (deferred): real timer port's 5 s bound untested at DO level (engine-level only); R2 PUT not aborted on timeout (counted before issue)
Task 6: minor (deferred): save() put then delete as two awaited ops (atomicity implicit)
Task 6: minor (deferred): ~7 s real alarm in playLease a possible flake under load
Task 6: complete (commits 72858f6..b737d8b, review clean)
- 2026-10-15T02:33:29-0400 T7 implementer dispatched: opus, agent a7fc6bed39d998a8e, BASE b737d8b; carry-t7.md; expected 371
- 2026-10-15T02:33:43-0400 llama-ed: MANDATORY final-fix-wave item: commit the reviewer's real-delivery probe (scratchpad/t6probe) as a test — getAlarm() null inside a genuine workerd delivery, re-armed, no metronome-duplicate log. Put on the final reviewer's list as required, not optional.
- 2026-10-15T02:36:33-0400 T7 implementer DONE_WITH_CONCERNS b54e6e2 (371 passed x2, typecheck clean, dry-run ok). Adaptation: clock-metronome.test.ts:180-186 fake replies lease blocked + not metronome-down. CONCERN: non-object DO reply (undefined/null) makes fallbackReason throw TypeError on the play path before fallback loop: no metronome-down, no fallback write, clock-failed (fail-closed on spend, but no fallback).
- 2026-10-15T02:36:55-0400 T7 spec reviewer dispatched: opus, agent a6cfa03e0acca5550
- 2026-10-15T02:39:02-0400 T7 spec review: Pass, 0 C/0 I, 2 minors. Adaptation (test:180-191) judged valid and minimal.
Task 7: minor (deferred, FINAL REVIEW ATTENTION): non-object DO reply makes renew throw (TypeError in fallbackReason) on play path: no metronome-down, no fallback write, clock-failed raised (fail-closed on spend); "Never throws" doc comment false; fix: in renew treat non-object status as {error} => trigger (a)
Task 7: minor (deferred): two brief tests (clock-metronome.test.ts:130-139, 141-154) feed the default lease:"play" fake to a blocked lease and now take the fallback path silently; assertions still hold
- 2026-10-15T02:39:28-0400 T7 quality reviewer dispatched: opus, agent ab2ef73e3461bf9c6
- 2026-10-15T02:42:05-0400 T7 quality review: Needs fixes, 0 C / 1 I / 3 minors. I-1: renew (clock.ts:242,253) can throw: non-object DO reply => TypeError in fallbackReason outside try; String(e) can throw on Object.create(null) rejection; play path loses fallback + metronome-down; result.metronome stays null (looks like switch off); read-threw/gridOf paths hide clock-inputs behind TypeError.
Ruling: T7 I-1 FIX now (strict surface, false contract): non-object status => r = {error: "renew returned a non-object"} (trigger (a)); error stringification made non-throwing; +1 test (play path, undefined reply => puts 8, metronome-down, r.metronome.fallback set) => T7 count 372 — cost if wrong: none beyond one more fallback path.
Task 7: minor (deferred): clock.ts:246 sent-label duplicates fallbackReason's blocked?"blocked":"play" mapping
Task 7: minor (deferred): switch-off path raises offair-without-fallback before the loop from deps.now() (ms-level departure from "off => exactly as before")
Task 7: minor (deferred): test gaps — non-Error rejection at runClock level; renew timeout after DO accepted; stalls>=2 on renew(null)/hold paths
- 2026-10-15T02:42:24-0400 T7 fix round 1 dispatched: resumed implementer a7fc6bed39d998a8e (opus); FIX_BASE b54e6e2; expected 372
- 2026-10-15T02:43:28-0400 T7 fix r1 DONE 0b59b70 (372 passed, typecheck clean; RED for undefined reply)
- 2026-10-15T02:43:48-0400 T7 re-reviewer dispatched: opus, agent af0bf293c045698aa
- 2026-10-15T02:44:41-0400 T7 re-review r1: ADDRESSED, consequences (1)-(3) resolved, no new breakage.
Task 7: fix round 1/5 (1 addressed, 0 open — renew can throw; commits b54e6e2..0b59b70)
Task 7: minor (deferred): failedInputs and index-write condition still use unguarded String(e) (pre-existing, practically unreachable); shared describeError helper suggested
Task 7: complete (commits b737d8b..0b59b70, review clean)
- 2026-10-15T02:44:59-0400 GATE (after Task 7): orchestrator verified npm test 372 passed (372) (20 files) + typecheck rc=0 at 0b59b70; waiting for llama-ed go before Task 8

## HANDOFF (written 2026-10-15T02:46:36-0400 by peer 7c48a24a-b1ba-48f0-8b4d-9a045fdbda5f on llama-ed's RELAY-NOW)

### State
- Worktree /Users/shawn/projects/llama/.claude/worktrees/antenna-metronome, branch antenna-metronome, HEAD **0b59b70**, tree clean. Tasks 0-7 complete and reviewed; the gate after T7 was verified by me and by llama-ed: `cd antenna && npm test` → **372 passed (372)**, 20 files; `npm run typecheck` rc=0.
- Commits since 04849bf: 0d4d348 (T1), 7c6b69b (T2), fb30bd5+bec70fb (T3), aeef49d (T4), 2dfda92 (core fix round), d555ee2 (second fix), 4ecc3c4+72858f6 (T5), b737d8b (T6), b54e6e2+0b59b70 (T7).
- Count drift vs the plan's 364: +8 from review fixes (core fix +3, second fix +1, T5 carry alarm-half +1, T5 fix +2, T7 fix +1). Task 8 is docs-only: expected count stays **372**.
- Next: **Task 8** (docs: docs/playout-setup.md section 4 step 7, section 7.1 row, new section 9; CLAUDE.md antenna paragraph; parent spec as-built). llama-ed's go for Task 8 goes to the successor. Then the **final whole-branch review on Fable**, then ONE fix wave re-reviewed on Opus, then stop at the finish menu.
- Workspace: briefs/review packages/seat rules in .superpowers/sdd/2026-10-15-antenna-metronome/ (seat-common.md, seat-spec.md, seat-quality.md, seat-rereview.md, impl-common.md, global-constraints.md, carry-t4..t7.md, core-fix-brief.md, order-fix-brief.md, t5-fix1.md, task-N-brief.md). Child handbacks in $D/<task>/handback.md. Used task names (single-use): t1-impl t1-review t2-impl t2-spec t2-quality t3-impl t3-spec t3-quality t3-rr1 t3fix-impl t3fix-rr t4-impl t4-spec t4-quality t4fix-impl t4fix-rr t5-impl t5-spec t5-rr1 t5-quality t6-impl t6-review t7-impl t7-spec t7-quality t7-rr1.

### Model and seat policy (llama-ed's instruction)
- Implementers per the plan's hint (T8: Sonnet); escalate to Opus only on BLOCKED-for-reasoning.
- Strict tasks 2,3,4,5,7: two separate Opus seats (spec-compliance, then code-quality). Tasks 1, 6, **8**: one combined Opus reviewer. Re-reviews: Opus.
- **Final whole-branch reviewer: Fable** (spec review mode; operator confirmed). Fix wave after it: one implementer (Opus), one scoped re-review (Opus).
- Announce the model on every dispatch; list every dispatch with its model in each report to llama-ed.

### Rulings beyond the plan (every Ruling: line, in order, with cost if wrong)
1. One combined reviewer per task — SUPERSEDED by llama-ed: two seats on 2,3,4,5,7; combined on 1,6,8.
2. T0 baseline run by the orchestrator (verification only) — no cost.
3. T3 I-1: removed-lease assert → toStrictEqual — none (stricter assert of intended behaviour).
4. T3 I-2: capAllows returns false on non-finite nowMs (assert inside existing test) — a NaN clock stops DO writes (cron falls back): intended fail-closed.
5. Core fix round (llama-ed items 1-3): non-finite stored expiresAt ⇒ invalid stored lease (deleted); fallbackReason (c) negated; accepted unblocked play whose reply lease ≠ "play" ⇒ trigger (b). Plus my fold: "save lease,stalls" pin on the invalid-lease path (empty-is-not-zero) — one extra assertion.
6. T4 minor 4 (alarm-op failure skips lease persist) initially NOT folded — then ordered by llama-ed as the second fix: renew flushes the accepted lease before any alarm op — +≤1 row/renew (~44k/month vs 50M; guard prices rowsWritten).
7. alarm() half of llama-ed's step-5 test carried to T5 (alarm() did not exist yet) — one test landed a task later (it did, in T5).
8. Trigger (b) generalized to s.lease !== (sent.blocked ? "blocked" : "play") (blocked lease accepted already-expired ⇒ fallback) — cron's fallback writes the off-air notice in a >15-min-skew case, bounded by MAX_PUTS. Reported to llama-ed; not overruled.
9. T5 I-1 (plan-mandated): duplicate (2b) and renew's live write build for tickBoundary = max(now, lastTarget − dMs − ALARM_SLACK_MS); rejected "refuse lower MEDIA-SEQUENCE than lastBody" (would freeze return-to-live after a block, since the notice is numbered from now+75 s) — a write built up to one early-delivery margin ahead of now, never beyond the genuine tick.
10. T7 I-1: renew truly never throws — non-object DO reply ⇒ {error: "renew returned a non-object"} (trigger (a)); non-throwing error stringification — one more fallback path.
Also accepted departures (re-reviewed): (b) reason string gains "lease="; old "missing expiresAt loads as expired" test rewritten to a finite past expiresAt; T7 test clock-metronome.test.ts:180-191 fake replies lease "blocked" for a blocked lease.

### Final-review queue (point the Fable reviewer at the ledger's "minor (deferred" lines; these first)
1. **REQUIRED (llama-ed): commit the T6 reviewer's real-delivery probe as a test** — getAlarm() is null inside a GENUINE workerd delivery (no runDurableObjectAlarm, which deletes the alarm first), the chain re-arms, no metronome-duplicate log. Probe recipe (the scratch file was NOT preserved; the reviewer instrumented a scratch copy's alarm()): $D/t6-review/handback.md, lines ~40 and ~53 — arm a lease whose next boundary is ~0.5-1 s away, record ctx.storage.getAlarm() on alarm() entry (in a test, e.g. via runInDurableObject wrapping/spying the instance's alarm or the engine port's getAlarm), vi.waitFor stored alarmTimes length >= 1, assert the recorded value is null, the re-armed alarm is later, and no metronome-duplicate log; measured 1 passed (2.28 s) at b737d8b. It is the only committed evidence for the premise duplicate detection rests on. Also reword the "alarm ticks and re-arms" comment. +1 test ⇒ 373.
2. T5: a PUT-capped write must not confirm the tick (mutant confirms||"cap" survives) — would hide a frozen playlist from cron's stall trigger.
3. T5: duplicate path's write-when-bytes-differ unpinned (retry after a handler that re-armed but died before its PUT).
4. T7: failedInputs and the index-write condition still use unguarded String(e) (pre-existing; a shared non-throwing describeError helper).
5. T4: a timed-out PUT keeps running and may land after a later PUT (R2 put has no abort) — add a known-limitations line (spec/T8 docs).
6. T4 ⚠️: a throw in renew's arm step skips the final flush (stalls/lastTarget/lastBody=null not persisted; renew rejects ⇒ trigger (a)) — check after the second fix.
7. T2 carry for T8 docs: a long metronome-down with METRONOME=on blind-trips the guard ~9 h in (empty recent DO window); runbook must say roll back with --var METRONOME:off (plan Review Focus 4 / T8 section 9 Rollback).
8. Remaining minors: T1 (substring asserts, len<1 branch), T2 (fractional Set per call), T3 (horizon kept by reference; inWindow 60000 edge; readState negative stalls), T4 ("logged once" range assert; keep unpinned; cap-skipped re-arm), T5 (step-2 delete pending alarm unpinned; stored list lengths; theoretical stale-lastTarget skip corner), T6 (real timer 5 s bound untested at DO level; save put+delete atomicity; ~7 s real-alarm flake risk), T7 (sent-label duplicate mapping; off-path offair-without-fallback raised from deps.now(); test gaps: non-Error rejection, timeout after accept, stalls>=2 on null/hold).

### Not ours
- **Task 9** (deploy and verification day, HUMAN CHECKPOINT) and **merge / push / tag** are llama-ed's. Never deploy, never wrangler without --dry-run, never a Cloudflare API, never touch R2.

### Keepalive
- My tick (cron job d87ba8a2) is disarmed at handoff; my armed-<uuid> flag removed. $D/STATE.md has in-flight: [] and mode idle; the successor re-arms its own tick and becomes STATE.md's one writer.
- 2026-10-15T02:47:19-0400 RELAY-READY: tick d87ba8a2 deleted, armed-7c48a24a removed (armed-global kept: other armed-* flags exist), no children/shells/monitors
