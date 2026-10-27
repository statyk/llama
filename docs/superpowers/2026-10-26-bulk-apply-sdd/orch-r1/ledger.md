# SDD ledger — plan: docs/superpowers/plans/2026-10-26-bulk-apply.md
Successor peer orchestrator orch-r1, session 14e1d77c-a4c4-4f81-b326-ae4463a500c5; parent llama-redo. Worktree /Users/shawn/projects/llama/.claude/worktrees/bulk-apply, branch bulk-apply, start 9be72bde.
Predecessor ledger: $D/orch/ledger.md (read-only; Tasks 0-10, T4b, T9b complete; its POINTER/Ruling lines carry forward).
Commit trailer: Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>

## Escapes
(none)

## Log
2026-10-27T01:10:56-0400 orch-r1 start: HEAD 9be72bde clean; meter 5h 50% (resets 01:29) wk 81% (brake 85%).
2026-10-27T01:11:37-0400 tick 4d35002d armed (13,43); flags touched. Task 11: dispatched t11-impl (Opus), BASE 9be72bde, budget 45m
2026-10-27T01:20:12-0400 Task 11: impl DONE_WITH_CONCERNS ee5dc565 (6210 passed, 1 skipped, 8 deselected; 10 new tests RED live; 10 mutants in scratch, all caught after one added case). Concerns: extras beyond brief (refused: prefix, 'already restored', extra refusals, non-dir station root refused, record_after unknown slug), part-way restore failure stops with hand-recovery text; process slip: a temp file briefly in $D (removed). Dispatched t11-review (Opus).
2026-10-27T01:23:10-0400 Task 11: review ✅ spec, quality approved (t11-review, Opus); extras beyond brief judged fail-closed and justified.
Task 11: minor (deferred): part-way rewind not resumable (_rewind/_restore_one); KeyboardInterrupt there gets no message
Task 11: minor (deferred): _restore_one catches only _Unfit — an OSError from _file_shas aborts the whole restore loop (catch OSError, refuse per show)
Task 11: minor (deferred): torn final after.jsonl line blocks every restore with no repair route
Task 11: minor (deferred): write-all loop x3; _durable_replace overlaps workspace.atomic_write_bytes; imports private catalog._sync_fd
Task 11: minor (deferred): untested: _check_station_root, 'show directory is gone', 'not in this snapshot', malformed after.jsonl, part-way rewind message
Task 11: minor (deferred): library-restored-but-station-changed refused as 'library files changed' (wrong cause named)
POINTER T13: (a) a resumed batch reuses the existing snapshot + after.jsonl, never re-takes (take refuses an existing snap); (b) record_after raises on a non-directory station root under after_commit → treat as retryable row failure and count toward the three-unreadable-station stop.
POINTER T14: the backfill's per-show unit writes no tracked file after record_after (after-record must be the final state).
POINTER T15: runbook — restoring the backfill after marking refuses every marked delivered show (station manifest changed) until marking is reversed: reverse marking first.
Task 11: complete (commits 9be72bd..ee5dc56, review clean)
2026-10-27T01:24:04-0400 Task 12: dispatched t12-impl (Sonnet), BASE ee5dc565, budget 40m; carries CAMPAIGN_MIN_VERSION 2.20.0 ruling. Meter 5h 53% (reset 01:30) wk 82%.
2026-10-27T01:27:31-0400 Task 12: impl DONE 84e014fd (6219 passed, 1 skipped, 8 deselected; 9 new tests RED live). Note: restore exits 1 on any refused row (dry run incl.), 2 on gate/LlamaError. Dispatched t12-review (Opus).
2026-10-27T01:28:57-0400 Ruling (parent, Shawn): weekly brake raised to 90% (was 85%); 5h brake stays 85%; checkpoints A/B/C still stop for parent go regardless of meter — cost if wrong: up to 5 more weekly points spent before stopping.
2026-10-27T01:30:21-0400 Task 12: review spec ❌ / Needs fixes (t12-review, Opus): Critical 1 pin version = llama.__version__ (0.1.0 in the worktree) → newer-installed gate refuses every arm; Important 1 _write_json skips the dir sync (retire not durable). Fix loop round 1 → resume t12-impl (Sonnet). FIX_BASE 84e014fd.
Task 12: minor (deferred): retire writer treats "retired" key presence as retired; reader requires non-null
Task 12: minor (deferred): retire_rekey_restore returns False for unreadable/non-dict record, same as absent; untested branch
Task 12: minor (deferred): cmd_pin does not call replay_holds._check_identity (recorded worktree may not be the tree checked)
Task 12: minor (deferred): bulk_apply main lets OSError (missing --slugs file) / replay_holds.Refusal outside arm escape as tracebacks
Task 12: minor (deferred): restore exit 1 path undocumented in docstring and untested
Task 12: minor (deferred): version rule duplicates rekey_overrides.py:779-830 (acceptable per brief; note for final review)
Task 12: minor (deferred): style — mid-file imports in test_campaign_gate.py; split Path imports; bulk_apply._config re-implements replay_holds config resolution
2026-10-27T01:30:36-0400 Task 12: fix round 1 sent to t12-impl (Sonnet, resumed)
2026-10-27T01:32:44-0400 Task 12: fix round 1 DONE c32f71de (6224 passed; 5 new tests RED). Dispatched t12-rereview (Opus).
2026-10-27T01:33:57-0400 Task 12: fix round 1/5 (2 addressed, 0 open — pin version from tag + write_pin refuses malformed; dir sync after _write_json; commits 84e014f..c32f71d); re-review t12-rereview (Opus) clean.
Task 12: minor (deferred): bulk_apply.py keeps unused 'import llama' as a test patch seam (patch llama module directly instead)
Task 12: minor (deferred): first pin creating root/campaign does not sync root (entry for campaign/); safe failure (no pin)
Task 12: minor (deferred): bulk_apply imports private campaign_gate._VERSION
Task 12: complete (commits ee5dc56..c32f71d, 1 fix round, review clean)
2026-10-27T01:34:14-0400 Ruling (parent, Shawn away until ~09:30): proceed within brakes (5h 85%, wk 90%). CHECKPOINT A: run the read-only backfill dry run, write $D/orch-r1/checkpoint-a.md (totals, both lists, the two questions), send a ≤10-line summary, CONTINUE to Task 15; Shawn's A rulings become follow-up T14b; do not guess his answers or change Task 14's rule. CHECKPOINT B: same pattern ($D/orch-r1/checkpoint-b.md), CONTINUE to Tasks 16-17; B rulings → follow-up. STOP before Task 18 (or at a brake): nothing in flight, HANDOFF, report. Other stop points stand.
2026-10-27T01:34:24-0400 Ruling: T13 carries the predecessor's 'mount check per wave' pointer as a pre-flight: a non-dry --from-list run with a configured delivery path refuses before the first show (exit 1, nothing written) when the station root is not a directory — record_after/strict reuse would otherwise fail rows after LLM spend (T8 M7) — cost if wrong: one extra refusal path to remove.
2026-10-27T01:34:59-0400 Task 13: dispatched t13-impl (Sonnet), BASE c32f71de, budget 60m; carries rulings (resume reuses snapshot; station pre-flight; record_after mount drop → StationUnreadable; ladder-form tests). Meter 5h 2% (reset 06:29) wk 82%.
2026-10-27T01:39:34-0400 Task 13: impl DONE f3954e0e (6249 passed; 15 RED/18 pass-by-design incl. PIN; both ruling tests present). Note: resume line omits --seven-day-ceiling/--stop-at-points (brief fixes its text). Dispatched t13-review (Opus).
2026-10-27T01:44:27-0400 Task 13: review spec ❌ / Needs fixes (t13-review, Opus): Important 1 resume line drops --seven-day-ceiling (+ --with-gather-llm, --allow-structure-change, --stop-at-points) → resuming a ceiling pause runs on to the config ceiling (spec anti-goal); spec item: needs-llm retryable even with --with-gather-llm (brief: only without). Fix loop round 1 → resume t13-impl (Sonnet). FIX_BASE f3954e0e.
Task 13: Ruling: the trial stop exits 1 when an earlier row in the run failed (brief says exit 0) — accepted deviation, consistent with the pause path, so an operator sees failures — cost if wrong: a wrapper treating exit 1 as abnormal after a successful trial block.
Task 13: minor (deferred, RECOMMEND-FIX): trial n counts zero-spend skips and excludes failed rows; failure rows carry no meter → biases the per-show cost the trial measures
Task 13: minor (deferred, RECOMMEND-FIX): a non-fresh batch whose snapshot/ lacks manifest.json → every write's record_after raises, unit restores after the brief spend, no stop; verify the snapshot once before the first show
Task 13: minor (deferred): --stop-at-points/--seven-day-ceiling silently inert when the meter does not apply (refuse up front)
Task 13: minor (deferred): EIO/ETIMEDOUT station read via _station_sha (_Unfit) or is_dir() OSError in the hook not counted toward the unreadable streak
Task 13: minor (deferred): names-form refusal of --seven-day-ceiling/--stop-at-points untested
Task 13: minor (deferred): test hygiene (unused 'real', unasserted comment, float|None annotations)
Task 13: minor (deferred): retire_rekey_restore OSError escapes _reapply_list as a traceback
2026-10-27T01:44:40-0400 Task 13: fix round 1 sent to t13-impl (Sonnet, resumed)
2026-10-27T01:46:57-0400 Task 13: fix round 1 DONE 5192e02b (6251 passed; 3 tests RED first). Dispatched t13-rereview (Opus).
2026-10-27T01:47:48-0400 Task 13: fix round 1/5 (2 addressed, 0 open — resume line carries the run's options; needs-llm retryable only without --with-gather-llm; commits f3954e0..5192e02); re-review t13-rereview (Opus) clean.
Task 13: minor (deferred): test_retryability_per_outcome lost its ("cleared", False) row in the fix (behaviour unchanged)
Task 13: minor (deferred): resume line's {path} unquoted
POINTER T18: runbook — after a trial stop the resume line repeats --stop-at-points; drop it once the trial is accepted.
Task 13: complete (commits c32f71d..5192e02, 1 fix round, review clean)
2026-10-27T01:48:36-0400 Task 14: dispatched t14-impl (Opus), BASE 5192e02b, budget 60m; carries T1 titles-subject pointer and T11 no-write-after-record_after pointer; rehold-verdicts excluded pending Shawn. Meter 5h 6% wk 83%.
2026-10-27T01:49:06-0400 Ruling (parent-directed): T13b after Task 14 (not concurrent — one worktree, one writer at a time), before Checkpoint A's dry run: (1) the trial's per-show cost counts only shows that actually invoked an LLM provider (pacing's boundary rule); (2) a non-fresh batch whose snapshot/ lacks a usable manifest.json refuses before any spend — never rolls back show after show after paying for briefs. Each pinned by a test shown RED first. Implementer Sonnet; reviewers Opus. Trial-stop exit-1 deviation accepted (parent). Cost if wrong: the trial measures fewer shows than ran.
2026-10-27T01:57:57-0400 Task 14: impl DONE_WITH_CONCERNS da32e253 (6260 passed; 9 RED live; 6/7 mutants caught, survivor = in-lock dup check, race-only). Base-arm cross-check reproduces planning numbers 195/15/316/62/141-of-180 (56 never-ruled = 54 + 2 other_flags-only). Concerns: extra list reasons (no show.json, unreadable); multi-ruled flag needs all-spurious; corrupt verdict exits 2; failure between overrides write and after-record. Dispatched t14-review (Opus).
2026-10-27T02:02:05-0400 Task 14: review ✅ rules / Needs fixes (t14-review, Opus): Important 1 per-show unit has no rollback — a record_after failure (mount drop, Ctrl-C) leaves overrides.json written with no after-record; restore refuses it and a re-run reports clean. Fix: run the unit inside show_unit. Fix loop round 1 → resume t14-impl (Opus). FIX_BASE da32e253.
Task 14: minor (deferred → CHECKPOINT A question): verdict rulings on flags the base arm did not raise are neither recorded nor listed — 174 (slug, flag) pairs over 36 shows; none raised by migration-post.json
Task 14: minor (deferred): _append_jsonl duplicates record_after's durable-append loop; imports private catalog._sync_fd / batch_snapshot._sync_dir
Task 14: minor (deferred): dry run prints 'record: unresolved track titles' without its subject
Task 14: minor (deferred): retire_rekey_restore return ignored (no note when nothing retired)
Task 14: minor (deferred): a corrupt verdict file aborts the dry run (exit 2) rather than listing that show
2026-10-27T02:02:22-0400 Task 14: fix round 1 sent to t14-impl (Opus, resumed)
2026-10-27T02:06:39-0400 Task 14: fix round 1/5 (1 addressed, 0 open — per-show unit inside show_unit, rolls back a write it cannot record; commits da32e25..884dd4a); re-review t14-rereview (Opus) clean.
Task 14: minor (deferred): show_unit's own restore failing leaves overrides rewritten; a re-run reports nothing to record (pre-existing unit limitation)
Task 14: complete (commits 5192e02..884dd4a, 1 fix round, review clean)
2026-10-27T02:06:39-0400 CHECKPOINT A dry run run (read-only, at 884dd4ad): rc 0, totals identical to planning (195/15/316/62/141 of 180); nothing written under ~/.llama. Report being written to $D/orch-r1/checkpoint-a.md.
2026-10-27T02:07:06-0400 Task 13b: dispatched t13b-impl (Sonnet), BASE 884dd4ad, budget 40m.
2026-10-27T02:07:35-0400 CHECKPOINT A report written: $D/orch-r1/checkpoint-a.md (questions: listed flags; rehold-verdicts; observation: 174 non-base rulings). Continuing per parent ruling.
2026-10-27T02:10:14-0400 Task 13b: impl DONE 51fb6a13 (6263 passed; 1 moved test test_stop_at_points_ends_the_block under brief clause 1). Process slip: implemented before tests; RED shown by reverting cli.py. Meter 5h 12% wk 83% (measured 02:1x; my CP-A report said ~10%, unmeasured).
2026-10-27T02:10:34-0400 Task 13b: dispatched t13b-review (Opus).
2026-10-27T02:13:03-0400 Task 13b: review ✅ behaviour / Needs fixes (t13b-review, Opus): Important 1 progress rows record no spend marker, so progress.jsonl cannot reproduce the trial n (brief's stated purpose). Fix round 1 → resume t13b-impl (Sonnet): add llm_calls to extra on both paths + a zero-spend failed row in the test. FIX_BASE 51fb6a13.
Task 13b: minor (deferred): trial test asserts neither exit code nor that the block's last slug was never processed
Task 13b: minor (deferred): _spend test helper swallows AssertionError from FakeProvider (couples to an empty queue)
Task 13b: minor (deferred): snapshot refusal names only problems[0] (no count of the rest)
Task 13b: minor (deferred): block[1] += spent adds a bool (int(spent))
2026-10-27T02:13:15-0400 Task 13b: fix round 1 sent to t13b-impl (Sonnet, resumed)
2026-10-27T02:15:29-0400 Task 13b: fix round 1 DONE 0295d3d7 (6263 passed; new assertions RED first: KeyError llm_calls). Dispatched t13b-rereview (Opus).
2026-10-27T02:16:07-0400 Task 13b: fix round 1/5 (1 addressed, 0 open — llm_calls on every progress row; commits 51fb6a1..0295d3d); re-review t13b-rereview (Opus) clean.
Task 13b: minor (deferred): 'skipped: missing' progress row carries neither llm_calls nor meter (zero-spend by construction)
Task 13b: complete (commits 884dd4a..0295d3d, 1 fix round, review clean)
2026-10-27T02:16:56-0400 Task 15: dispatched t15-impl (Opus), BASE 0295d3d7, budget 75m; carries pointers (a) held-only guard reason, (b) emcee_running per write_mark, (c) OSError per show, (d) outcome before row_visible_changes. Meter 5h 14% wk 84%.
2026-10-27T02:17:24-0400 RELAY-NOW received: finish Task 15 through review/fix rounds + CHECKPOINT B dry run, checkpoint-b.md and summary; then start nothing (no Task 16), write HANDOFF (incl. overnight gate ruling), disarm, RELAY-READY.
2026-10-27T02:32:27-0400 Task 15: impl DONE_WITH_CONCERNS 5fb225b6 (6288 passed; 25 new RED vs NotImplementedError stubs; 14 scratch mutants caught incl. pointers a-d). Concerns: plain show lock not show_unit (refused station write keeps library mark); delivered+no station copy counts ok; missing station root exit 2; delivered from ledger; mark_added semantics; frozen-without-reasons reason text; reselect-check exit 2 on unreadable show; unmark checks emcee. Dispatching t15-review (Opus).
2026-10-27T02:33:05-0400 Task 15: dispatched t15-review (Opus). CHECKPOINT B arm started in background (read-only replay_holds run --all → ~/.llama-harness/bulk/checkpoint-arm.json at 5fb225b6; discarded if T15 needs a fix round).
2026-10-27T02:33:54-0400 CHECKPOINT B arm done: rc 0 in ~50 s at 5fb225b6; 3983 shows: clean 1252, clean-changed 1709, needs-brief 3, needs-llm 654, newly-held 220, still-held 135, still-held-package 1, structure-changed 9.
2026-10-27T02:39:38-0400 Task 15: review spec ❌ / Needs fixes (t15-review, Opus): Important I1 'no station copy' derived from error-swallowing is_dir() (any OSError → False), counted OK for exit, terminal on re-run → a flaky SMB stat can leave a delivered show unmarked in an exit-0 batch, and the runbook then permits emcee run. Interpretations #1 (plain lock; library-mark-without-station-mark is the spec's intended intermediate state), #4, #6, #7 judged correct.
Task 15: Ruling: I1 — 'no station copy' only on FileNotFoundError from os.stat; any other OSError → 'refused: station copy unreadable (...)' (listed, retried); and follow the brief's exit rule literally: a delivered 'no station copy' item is listed and the batch exits 1, the exit code computed over the batch's whole record (last line per slug) so a re-run still reports it — the spec is binding and the batch's exit 0 is the runbook's emcee gate — cost if wrong: an operator sees exit 1 for shows whose station copy was deliberately removed and must check them by hand.
Task 15: minor (deferred, RECOMMEND-FIX): M1 station mark written without its record line (crash after rename, or before-copy write failing) → re-run records 'already marked', unmark removes the library mark and reports success, station keeps the batch's mark
Task 15: minor (deferred, RECOMMEND-FIX): M2 missing show dir / unreadable show.json silently drops a row from the mark plan (unsafe direction)
Task 15: minor (deferred, RECOMMEND-FIX): M3 --campaign-dir with --apply splits campaign state (campaign.frozen_slugs reads <root>/campaign) → refuse the combination
Task 15: minor (deferred): M4 FROZEN_NAME duplicates campaign.FROZEN_FILE; reselect assessment copies cli.py:3087-3090 verbatim (drift)
Task 15: minor (deferred): M5 six more private cross-module imports
Task 15: minor (deferred): M6 broad except Exception in _guard_holds/_plan_state
Task 15: minor (deferred): M7 test gaps (missing-pin refusal, resume after emcee stop, unmark emcee refusal)
Task 15: minor (deferred): M8 freeze takes any arm (no sha/fingerprint/coverage check; write-once)
POINTER T18: M9 runbook — reverse only the latest marking batch, or re-derive with a fresh batch afterwards; plus (e) reverse marking before restoring the backfill.
Task 15: fix round 1 → resume t15-impl (Opus). FIX_BASE 5fb225b6. CP-B arm at 5fb225b6 will be re-run at the fix head.
2026-10-27T02:39:54-0400 Task 15: fix round 1 sent to t15-impl (Opus, resumed)
2026-10-27T02:46:12-0400 Task 15: fix round 1/5 (1 addressed, 0 open — stat-based station decision, brief's exit rule literal, whole-record exit; commits 5fb225b..d1bb012); re-review t15-rereview (Opus) clean.
Task 15: minor (deferred): dead 'copy_problem = None' assignment (bulk_apply.py:756)
Task 15: minor (deferred): a recorded 'no station copy' can never clear within its batch, yet the listing says re-run until exit 0 — runbook must say what clears it (re-deliver, or accept by hand) → POINTER T18
Task 15: minor (deferred): dry-run stat-error branch of _station_state untested
Task 15: complete (commits 0295d3d..d1bb012, 1 fix round, review clean)
2026-10-27T02:46:51-0400 CHECKPOINT B dry runs done at d1bb0127 (read-only; nothing written under ~/.llama or the station): arm 3983 (newly-held 220), freeze 654, reselect 17/20 (3 absent all voiced), mark plan 2551 (1878 changed, 652 needs-LLM, 4 guard, 17 re-selection), voiced 136, unreadable 0. Report $D/orch-r1/checkpoint-b.md.

## HANDOFF (2026-10-27T02:47:25-0400)
State: Tasks 0-15 complete, plus parent-directed T4b, T9b, T13b. HEAD d1bb0127 on bulk-apply, tree clean. Suite: 6291 passed, 1 skipped, 8 deselected (./.venv/bin/python -m pytest -q, run by t15-impl at d1bb0127).
Commits this orchestrator (orch-r1): T11 ee5dc565; T12 84e014fd + c32f71de; T13 f3954e0e + 5192e02b; T14 da32e253 + 884dd4ad; T13b 51fb6a13 + 0295d3d7; T15 5fb225b6 + d1bb0127.
Checkpoints: A report $D/orch-r1/checkpoint-a.md (dry run at 884dd4ad: 195/15/316/62/141-of-180, identical to planning); B report $D/orch-r1/checkpoint-b.md (at d1bb0127: arm 3983, freeze 654, reselect 17/20, mark plan 2551, voiced 136, unreadable 0). Both summaries sent to llama-redo. Scratch campaign dir ~/.llama-harness/bulk/campaign (freeze + reselections written there, NOT under ~/.llama).
Open operator questions: A — (1) the 62 listed flags + 15 no-verdict shows; (2) rehold-verdicts/ (34 files; read or list?); observation: 174 non-base-arm rulings dropped. B — confirm the marking rule. Any ruling at A → follow-up T14b; at B → follow-up; Task 14's/15's rules unchanged until then.
Overnight gate ruling (parent, Shawn away until ~09:30): continue past B to Tasks 16 and 17; STOP before Task 18 (whole-branch review + Checkpoint C wait for the A/B rulings and their follow-ups) or at a brake (5h 85%, weekly 90% — raised from 85% by Shawn). Meter at handoff: 5h 23%, weekly 85%.
Next: Task 16 (wave lists, wave check, spot checks, famous-shows packet), then Task 17 (ranked re-voice list, trial report). Then stop before 18.
Nothing in flight: no children, no background shells, no Monitors. Tick 4d35002d deleted at this handoff; STATE.md mode done.
RECOMMEND-FIX candidates for a follow-up (parent call; T13b precedent): T15 M1 (station mark without record line not reversible), M2 (missing show dir / unreadable show.json silently dropped from mark plan), M3 (refuse --campaign-dir with --apply). Earlier deferred minors are per task above and in $D/orch/ledger.md.
Carry into later dispatches:
- T16: check the row outcome before row_visible_changes (needs-llm/unreplayable → ["files"]) — predecessor POINTER.
- T18 runbook/CLAUDE.md: reverse marking before restoring the backfill (T11/T15 e); reverse only the latest marking batch or re-derive (T15 M9); what clears a recorded 'no station copy' (re-deliver or accept by hand); drop --stop-at-points from the resume line once the trial is accepted (T13); CLAUDE.md stale on purged-show re-download and reapply held-only (predecessor); all new commands (pin/arm/snapshot/seal/restore/backfill/freeze/reselect-check/mark/unmark, reapply --seven-day-ceiling/--stop-at-points/--with-gather-llm).
- Final review: deferred minors listed per task in both ledgers.
Process notes: reviewer-common.md in $D/orch-r1/ holds the shared reviewer brief (constraints, contracts, review focus, format) — reuse it. Implementers must show RED for every new test before implementing (T13b slipped: implemented first, RED by revert). Stub ps/emcee_running() in tests. Production providers are ladders; tests use the list form. Checkpoint B's arm takes ~50 s; mark's gate needs arm sha == HEAD, so re-run the arm after any commit.
Rulings I made (orch-r1): T13 mount pre-flight + record_after mount drop → StationUnreadable + resume reuses snapshot; T13 trial exit-1 deviation accepted (parent confirmed); T15 I1 stat-based station decision + literal exit rule + whole-record exit. Parent rulings: weekly brake 90%; overnight gates; T13b; RELAY-NOW.
2026-10-27T02:47:32-0400 RELAY: tick 4d35002d deleted; armed-14e1d77c removed; armed-global kept (other armed-* present); STATE.md mode done, in-flight empty. No children, background shells or Monitors. RELAY-READY.
