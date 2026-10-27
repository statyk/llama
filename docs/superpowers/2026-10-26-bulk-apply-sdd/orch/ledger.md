# SDD ledger — plan: docs/superpowers/plans/2026-10-26-bulk-apply.md
Peer orchestrator session 829c3eab-317d-4890-b354-066008e43de7; parent llama-redo. Worktree /Users/shawn/projects/llama/.claude/worktrees/bulk-apply, branch bulk-apply, start 3a2c1352.
Spec: docs/superpowers/specs/2026-10-25-bulk-apply-design.md (approved, review mode Opus).
Briefs/review packages: /Users/shawn/projects/llama/.claude/worktrees/bulk-apply/.superpowers/sdd/2026-10-26-bulk-apply/ (sdd-workspace output); child dirs under $D.

## Escapes
(none)

## Log
2026-10-26T22:40:16-0400 Task 0: worktree pre-existed (parent); Step 0 ok (plan+spec tracked, tree clean); venv created + installed; llama/emcee resolve under worktree.
2026-10-26T22:40:16-0400 Ruling (parent-directed plan correction): CAMPAIGN_MIN_VERSION = "2.20.0" not "2.19.0" (v2.19.0 already released = paragraph chunking). Task 12 tests shift one minor: 2.20.0 ok; 2.19.0/0.1.0/2.20.0rc1 refused; pin 2.20.0 + installed 2.21.0 refused. — cost if wrong: one-line constant change at release.

## Pre-flight scan (plan read once; spec is the authority, reviewers read it per task)
| pair / task | produces → consumes | finding |
|---|---|---|
| T1→T2 | overrules.split_overruled/records_for/merge_rules, Overrides.overrules | consistent |
| T2↔T10 | both edit gather.compute_gather + replay.compute_legs | T10 must keep T2's split_overruled at compute_gather's end; carry pointer |
| T2↔T9 | T2 edits reapply fresh brief (overrule split); T9 rewrites reapply_show into show_unit | T9 must keep the split; carry pointer |
| T3↔T8 | both edit cli._redo_show_locked and build_package tail (after_package; T8 adds drop_anchor before it) | order matches plan text (drop_anchor then after_package) |
| T3→T4 | campaign.read_record/awaiting_fix/last_mark → status/deliver | consistent; CampaignUnreadable → awaiting (RF5) |
| T4↔T15 | frozen_slugs reads <root>/campaign/needs-llm-frozen.json; freeze writes <campaign-dir>/needs-llm-frozen.json | consistent (default campaign-dir = <root>/campaign) |
| T4↔T5 | both edit _deliver_one/_deliver_batch; T4's awaiting check first under lock, before voiced; T5 marked-destination route | consistent ordering |
| T5→T8/T9/T13 | station_mark.StationUnreadable (one class) | consistent |
| T5→T12 | campaign_gate.tool_processes/ps_lines; T12 adds the rest | consistent |
| T9→T13 | reapply_show(after_commit=) ← record_after | consistent |
| T11→T13/T14 | batch_snapshot.take/record_after | consistent |
| T12 self | CAMPAIGN_MIN_VERSION "2.19.0" | RULED (parent): "2.20.0", tests shift one minor |
| T12→T13/T14/T15 | retire_rekey_restore, require_pinned_code, require_tools | consistent |
| T15→T16 | reselections.json, marks, row_visible_changes/row_label_only (T3) | consistent |
| T10 self | "gather.py" = stages/gather.py | path nit only |
| T18 | docs + orchestrator acceptance | — |
Per-task self-consistency: each task's tests reference only interfaces it or earlier tasks produce; no test mandated that asserts nothing found. Clean apart from the T12 ruling.
2026-10-26T22:41:26-0400 Task 0: baseline 6000 passed, 1 skipped, 8 deselected (73.9s), cmd ./.venv/bin/python -m pytest -q
2026-10-26T22:41:26-0400 Task 1: dispatched t1-impl (Sonnet), BASE 3a2c1352
2026-10-26T22:46:52-0400 Task 1: impl DONE 11a22de3 (6008 passed); dispatched t1-review (Opus)
2026-10-26T22:50:27-0400 Task 1: review ✅ spec, quality approved (t1-review, Opus). ⚠️1 trailer = parent-specified, confirmed. ⚠️2 records_for on today's show.json gives an empty titles subject; Task 14 derives the titles subject from base title_sources itself. POINTER for T14 dispatch: build the titles subject explicitly, never via records_for(show) on today's show.json.
Task 1: minor (deferred): overrules.py:26-51 duplicates replay.py:153-167 flag classification (drift risk)
Task 1: minor (deferred): no test that merge_rules keeps the same kind/subject on another identifier, or dedupes within new
Task 1: minor (deferred): overrules.py:80-81 empty titles subject matches any rule; comment it
Task 1: minor (deferred): Overrides docstring (models.py:221-224) omits overrules
Task 1: complete (commits 3a2c135..11a22de, review clean)
2026-10-26T22:50:51-0400 Task 2: dispatched t2-impl (Opus), BASE 11a22de3; meter 5h 10% wk 76%
2026-10-26T23:02:49-0400 Task 2: impl DONE_WITH_CONCERNS 16cf2b3d (6027 passed; 1 changed expectation test_show_cmd notes brief:[]; concerns: overruled guard problem still triggers 2nd brief attempt; briefing_reusable untouched so overruled stored brief never reused; show prints brief notes; legacy overrides refuse triage [o]); dispatched t2-review (Opus)

2026-10-26T23:05:55-0400 Task 2: review ✅ spec, quality approved (t2-review, Opus); ⚠️ trailer = parent-specified, confirmed.
Task 2: Ruling: the overrule split in run_brief stays after generate_briefing returns (the plan's Step 3 order), so an overruled guard problem still pays the feedback retry (2nd brief call, prompt asks the model to fix an accepted problem) — the population is shows with an overruled briefing-* rule only; passing rules into generate_briefing is a small follow-up — cost if wrong: one extra brief call per such show per fresh brief; relayed to Shawn as a spend question.
Task 2: minor (deferred): no test pins "vet splits only its own flags" (vet_research.py:321)
Task 2: minor (deferred): typing.Sequence vs collections.abc in vet_research.py:3; gather.py:2236 rules unannotated
Task 2: minor (deferred): llama show prints notes.brief (unasked, small, tested)
Task 2: complete (commits 11a22de..16cf2b3, review clean)
2026-10-26T23:06:05-0400 Task 3: dispatched t3-impl (Sonnet), BASE 16cf2b3d
2026-10-26T23:10:23-0400 Task 3: impl DONE 79049ca6 (6038 passed; tests written after impl, RED shown in scratch copy); dispatched t3-review (Opus)

## T4b (parent-directed addition, Shawn-approved 2026-10-26; runs after Task 4, before Task 5)
Ruling (parent-directed): brief overrules act inside the guard path. Semantics, binding for T4b:
1. `generate_briefing` takes the show's recorded overrules (`read_overrides(ws).overrules`; default `()` keeps every other caller unchanged). After each guard run, its problems are split with `overrules.split_overruled(problems, rules, show)`. Only the HELD problems decide: they alone trigger the feedback retry, appear in the retry feedback, and become hold flags. Overruled problems never trigger a retry or a hold; they go to `ShowNotes.brief` as `overruled: <flag>` (Task 2's note format). A first attempt whose only problems are overruled is accepted at once (one LLM call).
2. Every fresh-brief caller passes the rules: run_brief and reapply's fresh brief. Task 2's post-hoc split in those callers either stays as a harmless no-op or is folded into the new path. The reviewer checks that no caller double-notes.
3. `briefing_reusable`: a stored briefing that fails today's guard is reusable when every guard problem is overruled for the show (same `split_overruled`, against the show's identifier). Overrules may only make it accept MORE, never less. Every other refusal stays exactly as it is (inputs/digest mismatch, Task 15a restored-file wording `_RESTORED_WORDING`, short_kept handling). On reuse the overruled problems are noted in `ShowNotes.brief` wherever the reuse path writes notes (reapply/replay). This change to `briefing_reusable` is authorised by the parent, and only this change.
4. Before any edit, list the tests whose expectations move. Implementer on Opus; reviewers on Opus. Global Constraints otherwise unchanged.
Cost if wrong: brief spend estimates for overruled shows; a wrong (too-broad) reuse would ship a stored briefing with an unaccepted problem — so the reviewer must pin "only accepts more".

2026-10-26T23:14:02-0400 Task 3: review ✅ spec, quality approved (t3-review, Opus). ⚠️ Task 4 unreadable→awaiting: covered by T4's RF5 test. ⚠️ Task 9 ordering: pointer below.
Task 3: minor (deferred): campaign.py:40 manifest_sha256 defaults None though contract requires the key (missing reads as held, not malformed)
Task 3: minor (deferred): replay.py:258-261 row_visible_changes on needs-llm/unreplayable rows returns ["files"] — POINTER T15/T16: check outcome before row_visible_changes (plan T15 already says needs-llm/unreplayable never get the visible-change reason)
Task 3: minor (deferred): package.py:140 after_package can raise CampaignUnreadable after the manifest write (outside show_unit: get/run resume) — POINTER T8: consider reading the record at the top of build_package
Task 3: minor (deferred): cli.py:2817 no test pins manifest sha after redo (held=pkg is None)
Task 3: minor (deferred): replay.py:236 spec lists source.identifier as visible; plan's VISIBLE_FIELDS omits it (re-selections marked by their own rule)
Task 3: minor (deferred): campaign.py:77-81 file flushed, dir not fsynced (brief-mandated mechanism)
POINTER T9: reapply.py:191 already triggers after_package via build_package; mark_processed must come after show.json commit per T9 flow step 7.
Task 3: complete (commits 16cf2b3..79049ca, review clean)
2026-10-26T23:14:02-0400 Task 4: dispatched t4-impl (Sonnet), BASE 79049ca6
2026-10-26T23:17:18-0400 Task 4: impl DONE c45936ff (6045 passed); dispatched t4-review (Opus)

2026-10-26T23:19:47-0400 Task 4: review ✅ spec, quality approved (t4-review, Opus).
Task 4: minor (deferred): cli.py:2713-2720 batch re-check duplicates _deliver_one's first check (double lock; a show processed after the scan prints refused yet delivers)
Task 4: minor (deferred): no test pins awaiting-before-voiced order (cli.py:2623)
Task 4: minor (deferred): batch test (test_deliver_cmd.py:891) doesn't assert stderr refusal/pointer or no ledger row
Task 4: minor (deferred): cli_select.py:59 106 chars
Task 4: observation: batch with refused shows exits 0 (matches existing refusal behaviour)
POINTER T9: RF5 reapply leg — an unreadable campaign.json must fail the reapply row retryably (CampaignUnreadable propagates; reapply builds its own CatalogEntry at cli.py:3947 without awaiting_fix).
Task 4: complete (commits 79049ca..c45936f, review clean)
2026-10-26T23:19:47-0400 Task 4b: brief written /Users/shawn/projects/llama/.claude/worktrees/bulk-apply/.superpowers/sdd/2026-10-26-bulk-apply/task-4b-brief.md; dispatched t4b-impl (Opus), BASE c45936ff
2026-10-26T23:25:39-0400 Task 4b: impl DONE_WITH_CONCERNS 2ea940c9 (6055 passed; no expectation moved). Concerns: generate_briefing returns all problems, held-only decide retry/feedback, Task 2's caller split does the noting; ShowReplay.stored_brief_guard ignores overrules; refusal text names held problems only. Dispatched t4b-review (Opus).
POINTER T15: stored_brief_guard ignores overrules — a show whose stored-brief problems are all overruled would get "stored briefing fails today's guard"; T15 must decide whether the mark reason uses held (non-overruled) problems only (consistent with T4b reuse).

2026-10-26T23:27:57-0400 Task 4b: review ✅ spec, quality approved (t4b-review, Opus). briefing_reusable change = one line after tracks/broadcast/narration refusals, before restored-file check; accepts only more.
Task 4b: Ruling: T15's "stored briefing fails today's guard" mark reason uses only the HELD (non-overruled) stored guard problems (split stored_brief_guard with the show's overrules, at the marking site or in ShowReplay), consistent with T4b reuse — cost if wrong: an overruled-only show is either spuriously marked (wasted re-process) or, if the split is wrong, an unaccepted guard problem goes unmarked.
POINTER T9/T10: the show_unit rewrite of reapply's fresh brief must keep generate_briefing(overrules=...) AND the caller split (generate_briefing returns every problem; callers split).
Task 4b: minor (deferred): generate_briefing returns all problems; callers must split again (docstring-only guard)
Task 4b: minor (deferred): test_stage_brief.py _songs_briefing duplicates _x_briefing
Task 4b: minor (deferred): unused _overruled binding (replay.py:539, brief.py split)
Task 4b: complete (commits c45936f..2ea940c, review clean)
2026-10-26T23:28:07-0400 Task 5: dispatched t5-impl (Opus), BASE 2ea940c9
2026-10-26T23:37:55-0400 Task 5: impl DONE_WITH_CONCERNS f53a3931 (6084 passed, 7 scratch mutants caught; concerns: tool_processes self_script kwarg; write_mark/clear_mark leave emcee_running() to callers (T6/T15); mark_of returns {} for non-object mark; --replace-voiced equal refusal before gate; --fixed lists unreadable as refused). Dispatched t5-review (Opus)

2026-10-26T23:41:41-0400 Task 5: review ✅ spec, quality approved (t5-review, Opus); RF1 both branches pinned.
Task 5: minor (deferred): station_mark.py:104 ensure_ascii=False re-encodes emcee's \uXXXX escapes (data equal, bytes outside the mark change; clear does not restore originals) — fix ensure_ascii=before.isascii(); candidate for final review
Task 5: minor (deferred): station_mark.py:111-129 _swap_in raises raw OSError (not StationRefused) on a failed write — POINTER T6/T15: catch OSError per show (or wrap) so a dropped mount cannot crash the batch
Task 5: minor (deferred): cli.py:2710 _fixed_for_delivery docstring overstates the re-check
Task 5: minor (deferred): cli.py:2658-2664 equality refusal before the gate tells a held voiced marked show to clear-mark, which refuses held — POINTER T6
Task 5: minor (deferred): station_mark.py:115 SIGKILL leaves .manifest.json.llama-*.tmp (no sweep)
POINTER T15: write_mark does not call emcee_running(); call it before each write.
Task 5: complete (commits 2ea940c..f53a393, review clean)
2026-10-26T23:41:52-0400 Task 6: dispatched t6-impl (Opus), BASE f53a3931
2026-10-26T23:42:42-0400 Task 6: Ruling (parent-directed): Task 5 minor ensure_ascii=False folded into Task 6 — station_mark writes with emcee's JSON encoding (ensure_ascii/indent/separators/newline per emcee package_io.rewrite_manifest) + pin: mark then clear on a non-ASCII-title manifest is byte-identical; if not exactly matchable, report the difference — sent to t6-impl mid-run. Cost if wrong: bytes outside the mark differ (data equal).
2026-10-26T23:52:28-0400 Task 6: impl DONE_WITH_CONCERNS 003a5404 (6116 passed; encoding = json.dumps(indent=2) + original trailing newline, mark→clear byte-identical for emcee- and llama-written files; one helper changed; first suite run had 4 failures from a real emcee process seen by ps — clear-mark tests now stub emcee_running). Dispatched t6-review (Opus)

2026-10-26T23:57:18-0400 Task 6: review ✅ spec, quality approved (t6-review, Opus). Encoding pin holds; reviewer read-only checked 2786 live station manifests round-trip byte-identically (none non-ASCII).
POINTER T9: show.json-only commit then clear-mark on a delivered (purged) show prints deliver's "warning: kept library audio for <slug>: already purged" on the normal path — consider a quieter line for the already-purged case.
Task 6: minor (deferred): cli.py:2956-2962 interrupt between clear_mark and add_clear leaves station cleared, no clear recorded, audio unpurged; re-run refuses "not marked" (known limitation)
Task 6: minor (deferred): cli.py:2944/2951 library-manifest I/O error or failing ps escapes as traceback (nothing written yet)
Task 6: minor (deferred): refusal order only partly pinned (held/sha/differences swaps pass)
Task 6: minor (deferred): cli.py:2932 vs 2956 compared bytes not tied to rewritten bytes (small risk)
Task 6: minor (deferred): cli.py:2968-2971 put-back-failed message untested
Task 6: minor (deferred): cli.py:2887 private campaign._parse; 2877 copies catalog skip-reason text
Task 6: complete (commits f53a393..003a540, review clean)
2026-10-26T23:57:28-0400 Task 7: dispatched t7-impl (Sonnet), BASE 003a5404
2026-10-27T00:00:44-0400 Task 7: impl DONE_WITH_CONCERNS 402d138c (6128 passed; RED partial: -x stopped at first failure; 1 expectation moved: status summary gains awaiting-fix column before 'voiced on'). Dispatched t7-review (Opus) with a scratch mutation check of the new tests in place of the missing RED

2026-10-27T00:04:56-0400 Task 7: review ✅ spec, quality approved (t7-review, Opus); 5 scratch mutants all caught by predicted tests (stands in for the partial RED). CLAUDE.md update is Task 18's.
Task 7: minor (deferred): cli.py:506-512 marked package with invalid recorded move prints error/exit 1 rather than skip; neither order tested
Task 7: minor (deferred): cli.py:263-268 refusal rebuilt by stripping the status-line prefix (pinned by mutant d2)
Task 7: minor (deferred): cli.py:254 _process_one docstring omits the awaiting-fix first step
Task 7: minor (deferred): test_run_cmd.py:791 _forbid_spend duplicates helpers.forbid_spend
Task 7: minor (deferred): test_status_cmd.py:770-772 identity test checks non-null only
Task 7: minor (deferred): cli.py:628-637 voice --fresh on a marked package fails on stem validation first (no spend; message wrong)
Task 7: complete (commits 003a540..402d138, review clean)
2026-10-27T00:05:06-0400 Task 8: dispatched t8-impl (Opus), BASE 402d138c
2026-10-27T00:21:02-0400 Task 8: impl DONE_WITH_CONCERNS 6a8f7d81 (6159 passed; 8 scratch mutants caught; no expectation moved). Deviation: anchor station pairing also requires anchor identifier == show.json identifier (existing test test_held_reselection_then_overrule_never_ships_the_old_items_station_audio caught the literal reading). build_package now reads the campaign record before any write (T3 minor). Concerns: no --allow-download hint in triage/batch; pre-change held delivered shows have no anchor (no copy pairs → --allow-download); CLAUDE.md stale (T18); reapply strict + tally (T9). Dispatched t8-review (Opus).
POINTER T18: CLAUDE.md "a purged show re-delivers via redo --from package, which re-downloads" is now wrong for delivered shows.
POINTER T9: reapply's plan_reuse still non-strict; tally not threaded through process_show.

2026-10-27T00:24:36-0400 Task 8: review ✅ spec, quality approved (t8-review, Opus). RF3 pinned.
Task 8: Ruling: approve the deviation — anchor station pairing also requires anchor.identifier == show.json identifier (the literal brief rule would pair an old recording's station audio under a held re-selection's same-named files; build's identifier check compares against the new show.json and cannot catch it). Plan/brief wording superseded by this rule. — cost if wrong: a held show whose show.json identifier changed cannot reuse station audio through the anchor (refuses; --allow-download route).
Task 8: minor (deferred): M1 cli.py:3051-3053 _is_delivered duplicates reapply.py:66-68 _delivered — POINTER T9: share one helper
Task 8: minor (deferred): M2 package.py paired captured before in-place narrowing; strict + force=True would refuse over an in-place library file (latent, no caller passes force)
Task 8: minor (deferred): M3 missing paired copy reports "failed its length check"
Task 8: minor (deferred): M4 tally counts in-place files as neither reused nor downloaded
Task 8: minor (deferred): M5 triage strict refusal prints no route
Task 8: minor (deferred): M6 no test for fix --untitled under the refusal hint
Task 8: minor (deferred): M7 strict refusals fire at build time after gather/brief spend (T13 mount check is the guard)
POINTER T9: wire strict= and tally through reapply (reapply.py:159 still non-strict).
Task 8: complete (commits 402d138..6a8f7d8, review clean)
2026-10-27T00:24:47-0400 Task 9: dispatched t9-impl (Opus), BASE 6a8f7d81
2026-10-27T00:41:31-0400 Task 9: impl DONE_WITH_CONCERNS a2e0f20b (6178 passed; 19 new, each RED). Choices: unbriefed non-held still 'skipped: not held'; re-selection skip applies to held/processed too; --allow-download refuses multiple names; unreadable station + --allow-download = unvoiced; label-only/unchanged leave reuse-anchor.json; purge before after_commit (hook failure can't restore purged audio); list dry-run still counts purged delivered as download. Dispatched t9-review (Opus)

2026-10-27T00:46:22-0400 Task 9: review ✅ spec, quality approved (t9-review, Opus); all 8 implementer decisions accepted; cross-task invariants hold. ⚠️ CLAUDE.md reapply held-only text → T18.
Task 9: minor (deferred, RECOMMEND FIX at final review): reapply.py:179 re-selection skip unconditional — a processed (or held) re-selected show still points the operator at another redo --from select (full re-download); gate on awaiting_fix
Task 9: minor (deferred, RECOMMEND FIX at final review): reapply.py:330-336 purge before after_commit — a hook failure cannot restore purged library audio (station copy still holds it); run the hook before the purge
Task 9: minor (deferred): reapply.py:286 label-only/unchanged commits leave reuse-anchor.json forever
Task 9: minor (deferred): reapply.py:214-220 briefed-not-packaged show with no visible change commits show.json only, stays unpackaged
Task 9: minor (deferred): reapply.py:114 _purge_line duplicates cli._echo_purge messages
Task 9: minor (deferred): cli.py:4122 by-name failure line prints slug twice
Task 9: minor (deferred): cli.py:4269 dry-run download count over-counts delivered shows reused from the station
Task 9: complete (commits 6a8f7d8..a2e0f20, review clean)
2026-10-27T00:46:32-0400 Task 10: dispatched t10-impl (Sonnet), BASE a2e0f20b

## T9b (parent-directed addition, 2026-10-27T00:47:40-0400; runs after Task 10, before Task 11)
Ruling (parent-directed): fix Task 9's two RECOMMEND-FIX minors now. (1) reapply's re-selection skip applies only while the show is awaiting fix (last mark start 'select' AND awaiting_fix); a processed re-selected show is not sent to another redo --from select. (2) after_commit runs before the library-audio purge, so a hook failure restores the unit with the audio still in place. Each pinned by a test shown RED first. Implementer Sonnet; reviewers Opus. Cost if wrong: (1) a processed re-selected show re-enters normal reapply; (2) none expected.
Parent heads-up: expect RELAY-NOW after T9b's review (or earlier past ~400k context).
2026-10-27T00:52:51-0400 Task 10: impl DONE_WITH_CONCERNS 120b0405 (6192 passed; RED in scratch worktree, 10 failed, 4 pins pass by design; no expectation moved). Dispatched t10-review (Opus)
2026-10-27T00:56:51-0400 Task 10: review spec ❌ (1 point, Minor-rated) / quality approved (t10-review, Opus). Fix loop: round 1 → resumed t10-impl (Sonnet) with (1) align_reproduced from real align calls (reapply.py:230), (2) HerderError row-failure test + extract_setlist-leg failure test. FIX_BASE 120b0405.
Task 10: minor (deferred): reapply.py:212-217/231-239 scratch-dir + compute_legs block duplicated
Task 10: minor (deferred): test_reapply.py:700-701 no-op statement; :575 unused config param
Task 10: minor (deferred): no test pins set_breaks comparison in _align_reproduced
POINTER T13: write align_reproduced and kind into progress.jsonl.
2026-10-27T00:58:56-0400 Task 10: fix round 1 DONE 6e91a0c7 (6195 passed). Dispatched t10-rereview (Opus)
2026-10-27T01:01:01-0400 Task 10: fix round 1/5 (2 addressed, 1 open — NEW Critical: _CallCounter wraps the align provider list as one provider → AttributeError on the production ladder; commits 120b040..6e91a0c). Round 2 → resumed t10-impl (Sonnet): wrap each rung with a shared counter + list-provider tests. FIX_BASE 6e91a0c7.
2026-10-27T01:02:52-0400 Task 10: fix round 2 DONE dcfa5615 (6197 passed; pipeline.count_llm_calls over the ladder). Dispatched t10-rereview2 (Opus)
2026-10-27T01:04:30-0400 Task 10: fix round 2/5 (1 addressed, 0 open — ladder counting via pipeline.count_llm_calls; commits 6e91a0c..dcfa561); re-review t10-rereview2 (Opus) clean.
Task 10: minor (deferred): ladder tests use one FakeProvider for all rungs (escalated rung reach checked directly by the reviewer, not pinned)
Task 10: complete (commits a2e0f20..dcfa561, 2 fix rounds, review clean)
2026-10-27T01:04:42-0400 Task 9b: dispatched t9b-impl (Sonnet), BASE dcfa5615
2026-10-27T01:07:10-0400 Task 9b: impl DONE 9be72bde (6200 passed; RED live for both new behaviour tests, pin passed). Dispatched t9b-review (Opus)

2026-10-27T01:08:44-0400 Task 9b: review ✅ spec, quality approved (t9b-review, Opus).
Task 9b: minor (deferred): reapply.py:11-14 module docstring still says purge before after_commit
Task 9b: minor (deferred): reapply.py:380 comment wording ("a hook failure restores the unit, which cannot bring back purged audio")
Task 9b: minor (deferred): no test for a held show whose select mark was processed taking the held path
Task 9b: complete (commits dcfa561..9be72bd, review clean)

## HANDOFF (2026-10-27T01:08:44-0400)
State: Tasks 0-10 complete, plus parent-directed T4b and T9b. HEAD 9be72bde on bulk-apply, tree clean. Suite: 6200 passed, 1 skipped, 8 deselected (./.venv/bin/python -m pytest -q).
Next: Task 11 (per-batch snapshots and restore; implementer Opus), then 12 (CAMPAIGN_MIN_VERSION "2.20.0" ruling), 13, 14 → CHECKPOINT A (stop, report to parent).
Nothing in flight: no children, no background shells, no Monitors.
Carry into later dispatches (all are in this ledger as POINTER/Ruling lines):
- T13: write kind + align_reproduced into progress.jsonl; T8 M7 (strict refusals after spend) → mount check per wave.
- T14: build the titles subject from the base row's title_sources; never records_for(show) on today's show.json (T1 ⚠️).
- T15: (a) "stored briefing fails today's guard" uses only HELD (non-overruled) problems (T4b ruling); (b) emcee_running() before each write_mark (write_mark does not check); (c) catch OSError from station_mark._swap_in per show (a dropped mount must not crash the batch); (d) check the row outcome before row_visible_changes (needs-llm/unreplayable → ["files"]).
- T16: same as T15(d).
- T18: CLAUDE.md is stale on (i) "purged show re-downloads via redo --from package" (now strict for delivered shows; --allow-download) and (ii) "reapply is held-only"; plus all new commands per the plan.
- Final review: deferred minors listed per task above; T5 encoding fixed in T6; T9 recommend-fixes done in T9b.
Process notes: implementers must show RED for EVERY new test (no -x); tests touching emcee_running() must stub ps (a real emcee process broke 4 tests once); the production gather providers are LADDERS (lists), so tests must not pass only single providers where ladders matter.
Rulings so far: CAMPAIGN_MIN_VERSION 2.20.0 (parent); T2 brief-retry spend (superseded by T4b); T4b semantics (parent); T4b→T15 held-problems marking; T6 encoding fold-in (parent); T8 anchor identifier deviation approved; T9b (parent).
2026-10-27T01:09:13-0400 RELAY-NOW received: no task in flight; tick 204e1bcb deleted; armed flag removed (armed-global kept: other armed-* flags present). RELAY-READY.
