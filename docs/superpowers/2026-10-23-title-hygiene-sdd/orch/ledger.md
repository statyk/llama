# SDD ledger — plan: /Users/shawn/projects/llama/.claude/worktrees/title-hygiene/docs/superpowers/plans/2026-10-23-title-hygiene.md
Orchestrator: peer session f6d9aa57-d60b-422e-842e-6c1d7f64c903 (Opus), parent llama-db. Started 2026-10-23T01:25:34-0400 at 0a2f583.
Spec: docs/superpowers/specs/2026-10-22-title-hygiene-design.md (approved, review mode Fable).

## Escapes
(none)

## Log
- 2026-10-23T01:25:34-0400 Task 0 Step 1 done by parent; Steps 2-4 running (venv, llama.__file__, baseline).
- keepalive tick armed: cron 0cce2b6a (13,43), flags armed-f6d9aa57… + armed-global, STATE.md at $D/STATE.md.

## Pre-flight scan (plan 2026-10-23-title-hygiene.md vs spec 2026-10-22)
Shared file/interface pairs:
| pair | produces -> consumes | finding |
|---|---|---|
| T1->T2,T3 desc_list.py | Cleaned/clean_entries -> DescList.cleaned | consistent |
| T2->T3 | read_numbered -> read_desc_list prefers (i) | consistent |
| T1,T2,T3->T4..T9 | Cleaned, DescList, written_seconds -> judge/checks/decide_d/C/slice4 | consistent |
| T4->T5,T6,T7,T9 title_hygiene.py | agrees/duplicate/judge (track_no 1-based) -> checks, decide_d, plan_setlist_rung, confirm_short_tags | consistent (1-based track_no restated in T6/T7) |
| T5->T6,T9 | position_agreement -> check 3, slice-4 neighbour | consistent (no aliases both) |
| T6->T7 | DDecision.shift/failed/track_declines -> apply_deferred_setlist | consistent |
| T4 structure.py hygienic_title(require_real) -> T8 C hygienic (default) | consistent |
| T8 lossless_titles -> T11 cascade (in_scope computed by caller) | consistent |
| T11 gather.py/titles.py/structure.py additive -> T13 probe, T16 wiring | consistent; T11 must leave compute_gather untouched |
| T12 replay_holds.py -> T13 (_shadow keys) -> T19 (run --disable-slices) | consistent |
| T13 dump alt_* -> T14 gate rows R4,R14-R17,R10 | consistent |
| T16 GatherResult fields -> T17 replay, T18 slice5, T19 reports | consistent |
| T10 title_cosmetics -> T13 (applied to slice5 arms) and T18 | consistent |
Per task self-consistency: T1-T22 each read once; tests match interfaces. Notes:
- T1 test `clean_one("1 Samuel 15:23")` strips to `1 Samuel`: plan mandates, spec states the rule, R19 measures; consistent (Checkpoint A rules on gating).
- T7 mode order: `chosen` precedes `untagged` (test_chosen_canonical_untagged_tape_writes_no_q1_note) — consistent with the stated order.
- T15/T18 conditional on Checkpoint A — gated by llama-db relay per brief.
- Commit trailer: "One commit per task" — implementers use the session attribution trailer (Co-Authored-By Claude Opus 5.5 / Claude-Session lines), passed in every dispatch.
Result: no conflicts requiring a ruling before Task 1.
- 2026-10-23T01:26:19-0400 Task 0: baseline '4474 passed, 1 skipped, 8 deselected' (78s); llama.__file__ in worktree. Task 1 implementer dispatched (Sonnet), BASE 0a2f583.
- t1 agentId ab769c4ac8e93b103
- 2026-10-23T01:29:06-0400 Task 1 impl DONE d23a20e (4481 passed); reviewer dispatched (Opus)
- t1-rev agentId a96bf0565ee5306d7
- Task 1 review (Opus): spec ✅, Needs fixes: 1 Important (date-shaped test never under a passing vote). Fix round 1 sent to implementer ab769c4.
- Task 1: minor (deferred): trailing_time_stripped tab/space edge (`Song \t4:47` True); only one trailing time stripped; _BRACKETED mismatched brackets / _secs accepts >=60s; whole `(4:47)`/`[4:47]` entries kept unstripped with no duration (beyond brief, unpinned; matters for Task 5 share count); durations in pass order not text order; mixed wrapping quotes not stripped; `E: Filler: X` → filler_marked False; missing h:mm:ss trailing/tab tests.
- Task 1 fix round 1 commit 06052a7; re-review t1-rr1 (Opus) agentId ad569650308e46220
- Task 1: fix round 1/5 (1 addressed, 0 open; commits d23a20e..06052a7)
- Task 1: complete (commits 0a2f583..06052a7, review clean)
- 2026-10-23T01:34:44-0400 Task 2 implementer dispatched (Sonnet), BASE 06052a7
- t2 agentId ac3e3574a2bca7b69
- Task 2 impl DONE_WITH_CONCERNS ea02f12 (4493 passed; no RED captured; judgement calls in handback); reviewer t2-rev (Opus)
- t2-rev agentId a7a22a1258051ead3
- Task 2 review (Opus): spec ✅, Approved.
- Task 2: minor (deferred): timestamp-line skip can never fire under _NUMLINE (test pins nothing; add census-parity comment); mid-file import in test; judgement calls unpinned (first entry must be 1, header before first entry ignored, first header names boundary, numbering continuing across disc-prefix change, 3-digit test texts); no RED captured.
- Task 2: CHECKPOINT-A NOTE: reviewer ran read_numbered over 15,607 cached descriptions: admissible 5,160 / no numbered 8,985 / non-contiguous 1,142 (764 after an unbroken run >=5) / empty entry 89. Restarts mostly follow disc labels outside the fixed grammar (`disc two [59m16s]`, `DISC TWO (65:24)`, `~Disc 2~`, `Disc 2 - 50:52`, `D2`, `SET 2/2`, bare `N:`); leading prose starting with a digit becomes entry 1. Suggest the gate count rejections by reason.
- Task 2: complete (commits 06052a7..ea02f12, review clean)
- 2026-10-23T01:42:00-0400 Task 3 implementer dispatched (Opus, per plan), BASE ea02f12
- t3 agentId aca3b9b73b0dcd599
- Task 3 impl DONE_WITH_CONCERNS f172be3 (4508 passed; RED captured; 8 scratch mutants caught). Judgement calls: (1) read_parse applies drop_leading_artist_items after clean; (2) a line is exempt if ANY of its items is in removed_indices (surviving fragment of a partly stripped banner line stays); (3) cleaner report/output mismatch -> "cleaner count disagrees"; (4) non-exempt line yielding 0 items makes (ii) inadmissible; (5) used = first count-matched admissible, (i) before (ii).
- Ruling: call (5) stands — spec "when both lists qualify, prefer (i)": qualifying = count-matched admissible — cost if wrong: a few shows use a (ii) list where (i) existed but did not count-match; the gate shows reader per show.
- Ruling: call (4) stands — spec's literal rule ("every other non-empty line ... must yield exactly one item") — cost if wrong: yield on lists with a Total Time footer; gate measures (ii) rejections.
- Task 3 reviewer t3-rev dispatched (Opus).
- t3-rev agentId a3ea3923aaf1a804b
- Task 3 review (Opus): spec ✅; Approved implementation; 1 Important plan-mandated (partly removed multi-item banner line exempt → its fragment enters the list).
- Task 3: Ruling: exempt a line only when ALL its items are in removed_indices; the brief's `{0}`-removed two-item-line test becomes inadmissible ("line yields 2 items: …") and a `{0,1}` variant is the admissible case — spec (ii) exempts "the banner or artist lines the cleaning removes" and makes any several-item line inadmissible; a half-removed line is not a removed line, and its fragment would sit ahead of every real entry — cost if wrong: lists whose banner line is half-stripped become inadmissible (yield loss; those shows stay held as today, the safe direction).
- Task 3: CHECKPOINT-A QUESTION: (ii) bypasses (i)'s contiguity guard (a gapped `1,2,4` numbered list is used via (ii) when (i) says non-contiguous; likewise header-less restarts). Spec-literal. Gate should count shows where used.reader=="parse" while numbered is non-contiguous; operator rules beside R16.
- Task 3: minor (deferred): sum check does not prove per-line attribution (comment at the check); no test of _parsed_lines' _RECOVER_FLOOR branch; header/decoration lines (`CD 2:`, `=====`) become (ii) entries (check 1 declines them; gate count); cleaner report checked by length only, out-of-range indices ignored; _is_marker duplicates inline predicate; _lines(desc) lacks `desc or ""` guard; 26 warnings in full-suite output (pre-existing baseline also had 26).
- Task 3 fix round 1 commit 94e9c90; re-review t3-rr1 (Opus) agentId a3528e0baa0de840c
- Task 3: fix round 1/5 (1 addressed, 0 open; commits f172be3..94e9c90)
- Task 3: complete (commits ea02f12..94e9c90, review clean)
- 2026-10-23T01:58:07-0400 Task 4 implementer dispatched (Sonnet), BASE 94e9c90
- t4 agentId a439f217f4626c5f5
- Task 4 impl DONE 3bdd0c3 (4518 passed); reviewer t4-rev (Opus)
- t4-rev agentId a5bef7456c16b64bf
- Task 4 review (Opus): spec ✅, Approved.
- Task 4: minor (deferred): decline tests assert scope but not class name (only "Set" 1: checks h.check) — class names feed notes, SHIFT_CHECKS and gate counts; untested arms (_LEAD_TIME timestamp, bare is_timestamp, over length, no alnum, junk title, header-only Set 2/CD 2); judge re-composes is_placeholder_text's arms (plan-mandated split; suggest implication pin); empty stem == empty text gives filename residue not no alnum.
- Task 4: CHECKPOINT-A NOTE: a lone `01-?` passes check 1 when the list's leader vote does not strip `01-` (rosehilldrive reaches `?` only via the vote); spec-literal `\bopened\b` declines a song `Opened Up` as show-level annotation. Gate rows.
- Task 4: complete (commits 94e9c90..3bdd0c3, review clean)
- 2026-10-23T02:03:58-0400 Task 5 implementer dispatched (Sonnet), BASE 3bdd0c3
- t5 agentId a505b820936cd0e5a
- Task 5 impl DONE_WITH_CONCERNS 50f8bed (4534 passed). Concerns: Scarlet/Scarlet Begonias already agrees without aliases (subphrase), so the alias-only test uses Chinacat; filler example Tuning (Drums is not is_filler); slug is gracepotterandthenocturnals-2009-07-26.
- Ruling: the alias-only agreement_share case uses Chinacat / China Cat Sunflower — the brief's intent is "GD_SHORTHAND applies only when aliases is given", and Scarlet cannot show that because loosely_same_title already matches it — cost if wrong: none (test intent preserved).
- Task 5 reviewer t5-rev (Opus) dispatched.
- t5-rev agentId aacf18da89399cba2
- Task 5 review (Opus): spec ✅, Approved.
- Task 5: Ruling: agreement_share excludes `Filler:`-marked entries from its song-like denominator — a Filler: entry names music not played that night, so the canonical cannot be expected to contain it — cost if wrong: share slightly higher on lists with Filler: entries (fewer agreement declines); gate R9 shows them.
- Task 5: CHECKPOINT-A QUESTION / Ruling: check 2 compares a cleaned candidate with the neighbour's RAW title, so `Bertha (5:00)`/`Bertha [4:47]`/`Bertha (1)` neighbours do not count as duplicates (spec-literal: only check 3 "runs on cleaned copies"). Keep as built; Task 13's probe gets an extra alternative `alt_check2_cleaned` (check 2 with clean_one on neighbour titles) so the gate reports what cleaning would add, and the operator rules at Checkpoint A — cost if wrong: an S one-late fill beside a decorated tag on a partly tagged tape passes check 2.
- Task 5: minor (deferred): gracepotter test asserts only position 0 (filler arm), not the full tuple; test_check2 builds a track then overwrites it; import order nit.
- Task 5: complete (commits 3bdd0c3..50f8bed, review clean)
- 2026-10-23T02:10:01-0400 Task 6 implementer dispatched (Opus, per plan), BASE 50f8bed
- t6 agentId a8c89309100f61277
- Task 6 impl DONE_WITH_CONCERNS d4a27da (4561 passed). Concerns: (1) rosehilldrive `07-8th Wonder` ships with its number (leader needs a non-digit after it) — gate row; (2) filler-neutral sibling pairs don't count toward MIN_ANCHORS; (3) when every unresolved position declines per track, donor() never runs, so deferred S (Task 7) could fill slot-placeholder positions without the sibling shift check — carry to Task 7; (4) note text chosen for agreement (first unmatched entry) and block size (first entry of first mismatched block), via private _agreement helper; (5) set-index test uses synthetic filenames.
- Task 6 reviewer t6-rev (Opus) dispatched.
- t6-rev agentId ac3f93900489819c8
- Task 6 review (Opus): spec ❌ (1 Important: filler-neutral sibling pairs excluded from the MIN_ANCHORS count, making the shift detector inert where brief/spec say it declines). Needs fixes.
- Task 6: Ruling: follow the brief — filler pairs count toward MIN_ANCHORS as neutral pairs (never disagree) — brief text and spec (b) "pairs fewer than MIN_ANCHORS tracks" — cost if wrong: a few more sibling-duration declines on wholly untagged tapes (holds), measured at the gate.
- Task 6: Ruling (reviewer Minor 2 promoted, strict surface (e)): is_self_filled is False whenever any track is `unresolved` — an unresolved track's title is its filename, so is_filler on it is not evidence it is filler; spec "every song-like track is desc-position" read safely — cost if wrong: a tape with an unresolved filler-named file loses the Q2 exemption (it is held on unresolved titles anyway).
- Task 6: minor (deferred): dead defensive code in block-size detail (:180-183), redundant `ag[1] is not None`, `tag or ""`; set-index test synthetic filenames; 26 warnings = baseline count (baseline run also showed 26).
- Task 6: CHECKPOINT-A NOTE: rosehilldrive-2008-12-31 `07-8th Wonder` keeps its `07-` (leader strip needs a non-digit after it) and D would ship it unflagged — gate row.
- Task 6: CARRY to Task 11 reviewer: the `donor` callable must return None (not raise) when target `length` is missing (Review Focus 5).
- Task 6 fix round 1 commit 015afa4; re-review t6-rr1 (Opus) agentId a284ead8b5a48045f
- Task 6: fix round 1/5 (2 addressed, 0 open; commits d4a27da..015afa4)
- Task 6: minor (deferred): stale comment test_title_hygiene.py:542 "filler ... is not a pair" contradicts new rule.
- Ruling: implementer concern 3 (donor() not called when every unresolved position is declined per track) needs no change — the sibling check runs only on wholly untagged tapes, where Q1 forbids S (deferred mode never occurs there), so deferred S cannot fill those positions without the check — cost if wrong: none found.
- Task 6: complete (commits 50f8bed..015afa4, review clean)
- 2026-10-23T02:26:00-0400 Task 7 implementer dispatched (Opus, per plan), BASE 015afa4
- t7 agentId a3597733de8292135
- Task 7 impl DONE_WITH_CONCERNS 58424c4 (4585 passed; RED via NotImplementedError stubs). Calls: (1) Q1 note only when s_positions non-empty (mode still untagged) → CARRY to Task 13/14: R5 counts non-empty declined/notes, not mode; (2) S candidates cleaned with clean_entries over the S candidates only; (3) today's is_placeholder_text refusal kept silent per track, not declined; (4) on a D shift, one S note naming D's first shift check; (5) deferred S fills D's per-track slot-placeholder/metadata declines after a passing D, never filler entry; (6) chosen+list+slice2 off+untagged gives untagged with "no admissible taper list" note (ablation only).
- Task 7 reviewer t7-rev (Opus) dispatched.
- t7-rev agentId aaf1af23d94290c9f
- Task 7 review (Opus): spec ✅, Approved.
- Task 7: minor (deferred): is_placeholder_text branch in _s_check effectively unreachable (judge catches first; docstring/handback misdescribe it as silent; test asserts only `2 not in fills`); chosen+desc_used+slice2 off+untagged writes "no admissible taper list" note (ablation only; fix: _Q1_CHOSEN_NOTE only when not desc_used); S leader vote over candidate subset (comment); no test for apply_deferred_setlist(d=None).
- Ruling: a wholly untagged tape with no S position takes mode `untagged` with no Q1 note — no fill was withdrawn, so a Q1 note would be false — cost if wrong: none; CARRY to Task 13/14: count Q1 (R5) by mode `untagged` with non-empty `declined`, not by mode alone.
- Task 7: complete (commits 015afa4..58424c4, review clean)
- 2026-10-23T02:35:05-0400 Task 8 implementer dispatched (Opus, per plan), BASE 58424c4
- t8 agentId a8d1f91dcd04dc663
- Task 8 impl DONE_WITH_CONCERNS 19d1975 (4612 passed; RED vs stub; 11 scratch mutants, all caught except the C2 fuzzy_norm-differs clause, judged redundant). Concerns: derektrucks real canonical is shifted (C reaches Announcements/crowd via the taper list; gate to confirm); hygienic_title also applied to C2's lossless tag; out-of-scope / no-lossless declines write no note; greensky veto and C2 differs clause never change outcome; override positions may get a C note before the override replaces them.
- Ruling: C2's lossless tag must also pass hygienic_title — C2 replaces a real tag without confirmation (strict surface (b)); a non-hygienic replacement is never preferable — cost if wrong: a few fewer C2 replacements (adds no holds).
- CARRY to Task 11: C must not write a note (or count a change) at an overrides.titles position; the cascade passes override positions to C or filters C notes/changes there.
- Task 8 reviewer t8-rev (Opus) dispatched.
- t8-rev agentId aea3f17918623037e
- Task 8 review (Opus): spec ✅, Approved.
- Ruling: C's "agrees" stays `loosely_same_title` with its containment arm — the spec defines Agree as loosely_same_title; "whole-text containment is never used" read as "never match against the whole description text" (contains_sequence sense) — cost if wrong: C2 can replace `Drums` with lossless `Drums > Space` when the list entry is `Space`. CHECKPOINT-A QUESTION: operator confirms this reading; gate should list C2 replacements that agree only by containment.
- Task 8: CHECKPOINT-A NOTE: a single off-by-one lossless tag below the 2+ skip is adopted via (c) against a disagreeing reference (probe: adjacent `Deal, Deal`, unflagged) — spec/plan-prescribed; R17 must surface (c) adoptions where (a)/(b) disagreed; C1 can ship a trailing taper marker (`Blue Night @`) — gate line.
- Task 8: minor (deferred): one-off-by-one test asserts only declined != "off by one" (pin changed/c1_verdicts); off-by-one note written when C had no targets/candidates; greensky veto inert in apply_lossless (comment); case/punct-not-C2 test pins nothing distinctive; _BRACKETED greedy (`[a] b [c]`).
- Task 8: complete (commits 58424c4..19d1975, review clean)
- 2026-10-23T02:49:33-0400 Task 9 implementer dispatched (Sonnet), BASE 19d1975
- t9 agentId a8c774efc13a7a920
- Task 9 impl DONE 9e44bcf (4623 passed). Calls: entry matches tag core OR its shipped_short_tag form (7-11 (3)> vs entry 7-11); neighbours judged on tracks as passed (no chaining, unpinned); decline order entry→neighbour→stem→veto; desc None/not count-matched → nothing. Reviewer t9-rev (Opus).
- t9-rev agentId a1a0521476205b01d
- Task 9 review (Opus): spec ✅, Approved.
- Ruling: slice 4's entry test accepts the tag core OR its shipped_short_tag form (fuzzy_norm_title, whole entry) — slice 1's cleanup strips footnotes from the entry, so under the literal "core equals the whole entry" the spec's own `7-11 (3)>` example could never fire; whole-entry equality still required (`VA` vs `Quantico, VA` declines) — cost if wrong: footnoted short tags (`42(1)`) adopted where the literal reading would decline. CHECKPOINT-A plan reading.
- Task 9: CHECKPOINT-A QUESTION: a `Filler:`-marked entry (`Filler: J`) confirms its tag `J` (confirm_short_tags reads only .text); D declines the same position per track. Unpinned; operator rules (decline with reason `filler entry`, or accept). Deferred to Checkpoint A / final fix wave.
- Task 9: minor (deferred): duplicate block in test_short_tag_needs_an_agreeing_neighbour (no case with only a disagreeing neighbour); length guard misses tag_sources (IndexError on short list); unused `sources` param in _s4.
- Task 9: complete (commits 19d1975..9e44bcf, review clean)
- 2026-10-23T02:55:29-0400 Task 10 implementer dispatched (Sonnet), BASE 9e44bcf
- t10 agentId aec923c1089eae398
- Task 10 impl DONE 897e66a (4631 passed). Reviewer t10-rev (Opus).
- t10-rev agentId a2b165d30472d35b3
- Task 10 review (Opus): spec ✅; Needs fixes: 1 Important (keep rule unpinned — mutant `_acceptable = bool` passes every test). Fix round 1 sent.
- Task 10: minor (deferred): whitespace-only difference counted as a strip (probably unreachable); verbatim stem regex leaves debris (`Esau (s2t01)`→`Esau ()`, `gd_d1t04 Song`→`gd_Song`, `foo.bar.d1t1.Song`→`foo.bar.Song`, `s1t2s1t3 Song`→`s1t3 Song`) — CHECKPOINT-A/hand-check note; test_never_override_or_unresolved's unresolved input strips to "" anyway.
- Task 10 fix round 1 commit 7cacd9d; re-review t10-rr1 (Opus) agentId a3ec2719597c3696c
- Task 10: fix round 1/5 (1 addressed, 0 open; commits 897e66a..7cacd9d)
- Task 10: complete (commits 9e44bcf..7cacd9d, review clean)
- 2026-10-23T03:03:31-0400 Task 11 implementer dispatched (Opus, per plan), BASE 7cacd9d
- t11 agentId afae6d89fdfab38ae
- 2026-10-23T03:05:15-0400 RELAY-NOW received from llama-db: finish Task 11 through review/fix rounds, start no new task, then HANDOFF + RELAY-READY.
- Task 11 impl DONE 5d0b6c3, dd3a513 (4678 passed; RED captured per step; no existing test edited; compute_gather AST-identical to main; no-slices equality over 12 fixtures x2). Calls: C at override positions undone (not counted, no note; a C1 show-level decline caused there is kept); wholly-untagged count and 2b demotions passed to resolve_titles include override positions as today; furthur fixture 20 entries vs 19 files → C declines (pinned).
- Task 11 reviewer t11-rev (Opus) dispatched.
- t11-rev agentId a8d04117f724a84ab
- Task 11 review (Opus): spec ✅, Approved. 1 Important plan-mandated (verbatim duplication of compute_gather's prelude/title blocks in title_inputs/title_cascade).
- Task 11: Ruling: the duplication stands as transitional — the plan forbids editing compute_gather before Task 16, and gate 0 (Task 13) proves the copies agree — Task 16 MUST delete compute_gather's copies (its reviewer checks) — cost if wrong: a fix to one copy diverges until Task 16.
- Task 11: minor (deferred): C1 decisions can still be driven by an override position (show-level "C1 unconfirmed" decline triggered there; c1_verdicts lists override positions vs CascadeRecord docstring); wholly_untagged/tag_real use layer_demoted incl. override positions (unpinned; Checkpoint A plan reading); test_accept_short_tags_default_sources_unchanged uses synthetic tracks; equality harness reads op_notes via sys._getframe (comment); commit subjects ("1 of 3", "eleven fixtures").
- Task 11: complete (commits 7cacd9d..dd3a513, review clean)

## HANDOFF (2026-10-23T03:23:30-0400, RELAY-NOW from llama-db)
State: Tasks 0-11 complete, each review-clean. HEAD dd3a513 on held-backlog-title-hygiene, tree clean. Suite at HEAD: 4678 passed, 1 skipped, 8 deselected (26 warnings = baseline). Nothing in flight.
Next: Task 12 (harness --strip-title-overrides, Sonnet), then Task 12 Step 6 (orchestrator: base worktree at 11dbffb + cherry-pick of Task 12's commit, own .venv), Task 13 (probe dump, Opus), Task 14 (gate table + CHECKPOINT A).
Commits by task: T1 d23a20e,06052a7 | T2 ea02f12 | T3 f172be3,94e9c90 | T4 3bdd0c3 | T5 50f8bed | T6 d4a27da,015afa4 | T7 58424c4 | T8 19d1975 | T9 9e44bcf | T10 897e66a,7cacd9d | T11 5d0b6c3,dd3a513.
Infrastructure (reuse): briefs $D/orch/briefs/task-N-brief.md (Global Constraints + Review Focus + task; Tasks 1-14 built; rebuild with $D/orch/mkbrief.sh N); $D/orch/implementer-rules.md; $D/orch/review-rubric.md; $D/orch/rereview-rubric.md; $D/orch/mandates.md (verbatim text; still paste into every dispatch); $D/orch/setflight.sh <task> <agentId>|none (STATE.md in-flight); review packages via superpowers SDD scripts/review-package (writes to .superpowers/sdd/2026-10-23-title-hygiene/).
MUST CARRY into Task 13 (probe) / Task 14 (gate) dispatches:
 - R5: count Q1 by mode `untagged` with NON-EMPTY declined, not by mode alone (Task 7 ruling).
 - Add alternative `alt_check2_cleaned`: check 2 with clean_one on neighbour titles, what it would add (Task 5 ruling).
 - Gate rows/notes: reader (i) rejections by reason incl. unrecognised disc-label shapes (Task 2); shows where used.reader=="parse" while numbered is non-contiguous (Task 3 question); lone `01-?` passing check 1 when the vote fails, `Opened Up` declined as annotation (Task 4); rosehilldrive `07-8th Wonder` shipped with its number (Task 6); C2 replacements agreeing only by containment (Task 8 question), (c) adoptions where (a)/(b) disagreed incl. single off-by-one (R17), C1 shipping trailing taper markers (Task 8); `Filler:` entries confirming slice-4 tags (Task 9); slice-5 stem debris (`Esau ()`) for the hand check (Task 10).
MUST CARRY into Task 16: delete compute_gather's duplicated prelude/title blocks; its reviewer checks (Task 11 ruling).
Checkpoint A plan readings / questions to list for the operator (beyond R10/R14-R17/R19): Task 3 (ii)-bypasses-(i)-contiguity; Task 5 check-2 raw neighbour; Task 8 containment reading; Task 9 shipped-form entry match and Filler: confirm; Task 11 override positions in wholly_untagged.
All rulings are the "Ruling:" lines above (collect them for the finish).
- 2026-10-23T03:23:35-0400 Tick 0cce2b6a deleted; armed-f6d9aa57 removed (armed-global kept: another session's armed flag present).
