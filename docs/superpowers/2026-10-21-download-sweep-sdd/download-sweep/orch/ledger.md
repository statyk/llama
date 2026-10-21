# download-sweep SDD ledger (peer orchestrator cec61fef-ceff-4906-a725-327b45944d5e)

Start: 2026-10-21T01:43:48-04:00, branch download-sweep @ 1609a28. Spec: docs/superpowers/specs/2026-10-21-download-retry-and-run-sweep-design.md (review mode Opus).

## Escapes
(none)

## Log
- 2026-10-21T01:43:48-04:00 ACK sent to llama-db; setup ledger/STATE/tick.
- tick job 95c9ee15 armed (13,43)
- 2026-10-21T01:51:59-04:00 Plan written (312 lines), frozen sha256 bf7c67bb…422e; baseline suite 3811 passed/1 skipped (./.venv/bin/pytest -q). Meter 5h 20% wk 36%.
- 2026-10-21T01:51:59-04:00 Dispatched plan-rev-a (Opus), plan-rev-b (Opus), blind parallel.
- 2026-10-21T01:52:23-0400 llama-db steer: DROP rm tombstone (spec rejected it) unless a reviewer shows a concrete failure -> then report, don't add. Other 3 additions OK. My own scenario to report at triage: resume O_CREATs .lock after rmtree unlinked it but before rmdir -> rm OSError ENOTEMPTY, husk with .lock; no 2 workers.
- 2026-10-21T01:52:36-0400 llama-db: leave rm/.lock husk as known window; add ONE line naming it to spec §4 known windows (+ docs); no retry.
- 2026-10-21T02:04:54-0400 plan-rev-b done: Foundation SOUND; 15 (0C/2I/13m). sha 9f29204c1d83
- 2026-10-21T02:05:34-0400 plan-rev-a done: Foundation SOUND; 10 (0C/2I/8m). sha b08c3e33fefa. plan-rev-b sha 9f29204c1d83.
- 2026-10-21T02:05:34-0400 TRIAGE draft. Spec-decision items -> llama-db: (a) paused runs w/ non-download failures eligible (A-I, LLM spend); (b) aborted interactive get (auto=false, no marker) eligible (B-m); (c) md5 mismatch per-copy once (A+B m); (d) B: blocking get lock on unlinked inode -> 2 workers; fix = inode check in run_lock (plan-level, adopt unless vetoed). Plan-local accepts: last-candidate pin tests (A+B I), HTTPError narrowing (A m, B I), abandon only if another attempt will start + never at full size, continuation only with md5 + Content-Range checks + 206-to-plain rejected, mechanics (write-then-check, offset=st_size), slots= injection, _drive FakeProvider, crash-marker rendering, 416 rationale/interpretation sentence, get --name mkdir(exist_ok=False); doc limitations: slot fairness, sub-stall dribble, permanent download failures loop. Tombstone stays dropped (both reviewers called it warranted; llama-db ruled).
- 2026-10-21T02:08:42-0400 llama-db rulings: (a)(b)(c) YES, (d) adopt; get --name keeps existing-name reuse. Decisions file scratchpad/plan-review/decisions.md (S1-S4, P1-P13). Dispatch plan-edit (Opus editor).
- 2026-10-21T02:15:45-0400 plan-edit done (sha 1bc1b6ef8532); plan 351 lines; spec aligned by me (continuation-only-with-md5, abandonment clauses, --name mkdir) ; committed 3894d24.
- Ruling: one combined Opus task reviewer per task (spec verdict + quality verdict, SDD v7 template) satisfies "spec-compliance and code-quality review on Opus" — both verdicts required — cost if wrong: one extra review seat per task.
- Ruling: SDD progress ledger = this file; briefs/packages in .superpowers/sdd/2026-10-21-download-fallback-and-run-sweep/; implementer report file = $D/<task>/handback.md (mandate 1) — cost if wrong: none (paths only).

## Pre-flight scan (plan @ 3894d24)
| pair/task | shared | produces vs consumes | finding |
|---|---|---|---|
| T1/T2 | ia_client.py | T1 _attempt, md5-from-disk, schedule, per-copy-once -> T2 extends | consistent (T2 integrity bullet cites T1 copy-once) |
| T1/T3 | ia_client.py | T1 deadline minus post-first-pass slot waits -> T3 supplies wait secs | consistent |
| T2/T3 | ia_client.py | slot held per attempt incl. re-issued no-Range request | ok: one attempt = one slot hold |
| T3/T6/T7 | cli.py _setup | T3 adds slots to IAClient; others don't touch _setup | ok |
| T4/T5 | test_pace_loop.py, cli._execute | T4 uses _drive stub (raises IADownloadError); T5 changes _drive defaults (llm=True) | ok, T4 first; T5 default keeps T4 test behaviour |
| T4/T7 | sessions.py | failure_record(kind=), failure_kind, KIND_* -> sweep_verdict/_resume_run | consistent |
| T6/T7 | cli.run_resume, sessions.iter_sessions, locks | T6 _run_locked in run_resume -> T7 moves into _resume_run; RunMissing/Locked | consistent |
| T6/T7 | _print_sessions | T6 running label; T7 (run) for None show | ok, different lines |
| T1 self | tests vs behavior | test_md5_mismatch_on_one_server_then_success vs copy-once | ok (second copy good) |
| T2 self | tests vs predicate | last-candidate (R trickle, S1 404, S2 trickle): S2 unabandonable since R abandoned & S1 non-retryable | ok |
| T2 self | no-md5 trickle | abandonment discards .part | ok matches spec |
| T5 self | _drive llm default | existing tests untouched | ok |
| T6 self | run rm | rmtree under lock, no tombstone | ok per llama-db |
| T7 self | eligibility incl. no-marker auto | reads request via read_request | ok |
| T8 self | docs limitations | match spec §1/§4 | ok |
Scan clean; no rulings needed beyond the two above.
- 2026-10-21T02:16:21-04:00 Task 1 BASE 3894d24; dispatched t1-impl (Opus implementer), agent a8535ffdfc4956595.
- 2026-10-21T02:24:08-0400 t1-impl DONE 1517fa0 (3840 passed/1 skipped per report). Dispatch t1-rev (Opus).
- 2026-10-21T02:27:53-0400 t1-rev: spec ✅, quality Approved, 0C/0I/6m (sha 81baedfb9592). ⚠️ warnings: baseline also 26 warnings -> resolved. ⚠️ slot_wait sign -> Task 3 test covers.
- Task 1: minor (deferred): deadline lower bound unpinned (scratch mutant >=10.0 survives) — Ruling: fold into Task 2 dispatch (same file/tests) — cost if wrong: a few lines in T2's diff.
- Task 1: minor (deferred): metadata fetch httpx non-transport error can escape download_file (unreachable in prod) — Ruling: fold into Task 2 dispatch.
- Task 1: minor (deferred): DecodingError / non-dict metadata / mid-write OSError untested; 3xx non-retryable (disclosed); test hard-codes 1.0..4.0; rng "or" idiom.
- Task 1: complete (commits 3894d24..1517fa0, review clean)
- 2026-10-21T02:28:22-04:00 Task 2 BASE 1517fa0; dispatched t2-impl (Opus) a78c25a9c611baed1, carrying T1 minors 1-2.
- 2026-10-21T02:46:40-0400 t2-impl DONE_WITH_CONCERNS 6c19958,be153c2,5300f01 (3861 passed). Concern: 'owed' attempt after abandonment skips deadline check (narrow exception to §1). Dispatch t2-rev (Opus).
- 2026-10-21T02:51:00-0400 t2-rev: spec ✅ (one disclosed interpretation), quality Approved, 0C/0I/5m (sha 84d2b85573fd). ⚠️ md5-known = md5 arg: package.py passes metadata md5 -> fine. ⚠️ in-flight slot wait conservative -> told to Task 3.
- Ruling: accept the "owed" attempt after a trickle abandonment (skips the deadline check once) — the literal reading strands a file the abandonment promised to continue; bounded to one post-deadline attempt; spec §1 amended (d0e08c4) — cost if wrong: one extra attempt (~a transfer) past 60 s.
- Task 2: minor (deferred): transport error mid-append discard unpinned (mutant wrote=wrote survives) — Ruling: fold test into Task 3 dispatch (same test file).
- Task 2: minor (deferred): stitched md5 failure excludes only the finisher; if the prefix copy was the corrupt one the good finisher is lost for this call (liveness only; plan-mandated by test) — for final review.
- Task 2: minor (deferred): _continues does not check range end M==size-1 (short 206 appended, md5 catches, server excluded) — for final review.
- Task 2: minor (deferred): no test for '*' total with size known; condition 4 only on first request.
- Task 2: complete (commits 1517fa0..5300f01, review clean)
- 2026-10-21T02:51:29-04:00 Task 3 BASE d0e08c4; dispatched t3-impl (Sonnet) a280bceced5788b2a, carrying T2 minor (append-discard pin).
- 2026-10-21T02:53:17-0400 RELAY-NOW from llama-db: finish Task 3 through review/fix, start nothing new, HANDOFF, disarm, RELAY-READY.
- 2026-10-21T02:55:02-0400 t3-impl DONE_WITH_CONCERNS 4feccc4 (3869 passed); concern: no RED run (impl before tests), mutation-checked .part test. Dispatch t3-rev (Opus).
- 2026-10-21T02:59:37-0400 t3-rev: spec ✅, quality Needs fixes, 0C/1I/6m (sha 9e4740dd0348). I1: download_slots.py:42 except OSError -> persistent flock error = endless wait; fix BlockingIOError.
- Task 3: minor (deferred): _setup slots wiring unpinned (cli.py:125); duplicated _attempt call branches; _throttle sleeps inside slot (comment); non-FIFO polling (documented in T8); in-flight wait disables trickle after long slot wait; cap test detects breakage only after 30 s guard.
- Task 3: fix round 1/5 dispatched (resume t3-impl a280bceced5788b2a, Sonnet) for I1. FIX_BASE 4feccc4.
- 2026-10-21T03:01:40-0400 t3 fix1 2ce8fa9 (3870 passed). Dispatch t3-rerev1 (Opus).
- 2026-10-21T03:04:16-0400 t3-rerev1: finding ADDRESSED; new Minor: fd-close-on-error half unpinned (download_slots.py:46). sha 1b24da575f63.
- Task 3: fix round 1/5 (1 addressed, 0 open; commits 4feccc4..2ce8fa9)
- Task 3: minor (deferred): os.close on the non-BlockingIOError path is unpinned.
- Task 3: complete (commits d0e08c4..2ce8fa9, review clean after 1 fix round)
- 2026-10-21T03:04:16-0400 Root-verified: ./.venv/bin/pytest -q -p no:cacheprovider -> 3870 passed, 1 skipped, 8 deselected, 26 warnings (baseline also 26); llama.__file__ inside worktree; tree clean @ 2ce8fa9.

## HANDOFF (2026-10-21T03:04:16-0400)
State: Tasks 1-3 COMPLETE and reviewed (Opus). Tasks 4-8 NOT STARTED. Branch download-sweep @ 2ce8fa9, tree clean, suite 3870 passed/1 skipped.
Commits: 3894d24 plan+spec rulings; 1517fa0 T1; 6c19958/be153c2/5300f01 T2; d0e08c4 spec (owed attempt); 4feccc4/2ce8fa9 T3.
Next: Task 4 (failure kind/at, Sonnet), BASE 2ce8fa9. Then T5 (Sonnet), T6 (Opus), T7 (Opus), T8 (Sonnet), final whole-branch review (Opus), finish menu (merge/push reserved to llama-db).
Artifacts:
- Plan: docs/superpowers/plans/2026-10-21-download-fallback-and-run-sweep.md (351 lines); spec amended per llama-db rulings (a)-(d) + owed-attempt sentence.
- Briefs (global constraints + review focus prepended): .superpowers/sdd/2026-10-21-download-fallback-and-run-sweep/task-N-brief.md (all 8 pre-generated at 3894d24; T1-T3's are consumed; T4-T8 still match the committed plan).
- Review packages in the same dir. Reports: $D/<task>/handback.md. Implementer report file convention = $D/<task>/handback.md; fix rounds touch $D/<task>/done-fixN.
- Task names used (single-use): plan-rev-a, plan-rev-b, plan-edit, t1-impl, t1-rev, t2-impl, t2-rev, t3-impl, t3-rev, t3-rerev1.
Rulings so far (also above): combined Opus task reviewer; report path; T1 minors 1-2 folded into T2; owed attempt accepted + spec amended; T2 append-discard pin folded into T3; tombstone dropped (llama-db); llama-db rulings (a) paused failure-kind test, (b) no-marker auto=false needs attention, (c) md5 copy checked once, (d) inode check.
Deferred minors for the final review: see "minor (deferred)" lines (T1 x4, T2 x4 incl. stitched-blame and range-end, T3 x7).
Carry-forward notes for later tasks:
- T5 _drive harness: default llm=True keeps existing pacing tests unchanged.
- T7 must use failure_record(kind=KIND_OTHER) and "exit <code>" for typer.Exit (click Exit str() is empty/'1').
- T8 docs must include the non-FIFO slot limitation, the dribble limitation, permanent-download-failure limitation, rm husk window, inode-check statement.
- 2026-10-21T03:04:21-0400 Disarmed: CronDelete 95c9ee15, removed armed-cec61fef…; armed-global kept (other armed-* present: see ls).
