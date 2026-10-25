# SDD ledger — plan: docs/superpowers/plans/2026-10-24-junk-short-keep.md
Peer orchestrator (successor r1) 68216777-fbbf-4e29-a05f-d8f145d56c7f; worktree .claude/worktrees/junk-filter; branch held-backlog-junk-filter; start 5d3e452
Predecessor ledger: $D/orch/ledger.md (read-only). Its rulings, deferred minors and carried items stand and go to the final review.
Gates: Task 8, Task 9 -> STOP Checkpoint A; Tasks 10-14 -> STOP Checkpoint B (Task 15); Tasks 16-21 -> STOP Checkpoint C (Task 22); Task 23 after go.

## Escapes
(none)

## Log
2026-10-24T04:32:36-0400 orch-r1 started; meter 5h 41% / week 93%; HEAD 5d3e452 clean
2026-10-24T04:33:23-0400 tick armed: cron ceeba840 (13,43), flags armed-68216777 + armed-global
Task 8 BASE=5d3e452
2026-10-24T04:33:23-0400 Task 8: implementer dispatched (t8-impl, Sonnet, a8bf6745fec5512e7, budget 90m); meter 5h 41% / wk 93%
2026-10-24T04:40:11-0400 Task 8: implementer DONE, 76c1830, 4984 passed/1 skipped/8 deselected (./.venv/bin/python -m pytest -q); concern: neighbour dropped_today true only for r1_files rows
2026-10-24T04:40:11-0400 Task 8: reviewer dispatched (t8-rev, Opus, a1bcd1fdd8c157eeb); meter 5h 43% / wk 93%
2026-10-24T04:40:11-0400 Task 9 Step 2 started early (background bzyyn7xs3): base arm then cand arm back to back, log ~/.llama-harness/piece4/arms.log; worktree clean at 76c1830, Task 8 touches only scripts/short_keep_probe.py which the arms do not import
Ruling: Task 9 arms run while Task 8 is in review — the arms import only packages/* and scripts/replay_holds.py, untouched by Task 8 and its possible fix round — cost if wrong: re-run both arms (~time only).
2026-10-24T04:43:24-0400 Task 9 Step 2 DONE: base.json (base sha e37f67024eb3, 04:40:03-04:40:52, rc 0) sha256 b8ea3d04..; cand.json (cand sha 76c18307bad6, clean, 04:40:52-04:41:52, rc 0) sha256 31ec0a03..; config_fingerprint 3f1af9a8.. both; cand 0 rekey_error rows, 0 unreplayable
2026-10-24T04:43:24-0400 Task 9 Step 3: compare REFUSED exit 3 — 'baseline reproduces 127/148 held shows that are not needs-LLM (< 99%)'; 21 held drift rows in ~/.llama-harness/piece4/compare/drift-held.txt (all 217 base drift rows in drift.txt). STOP per plan; --no-repro-gate needs an operator ruling
2026-10-24T04:43:24-0400 Task 9 (read-only context): short_keep_probe arms rc 0 — changed 1536 (ref 1537), files added 2648 (ref 2649), cleared 20, added 34, added classes = expected exactly, 0 BLOCKS MERGE, 0 base-consistency, 0 override moves, 0 unreplayable, fills lost 10 / gained 12; 1 reproduction difference: soundtribesector9-2005-02-07 d1t1 (26 s untagged, duplicate-listed under sts9-2005-02-07.flac/): r1 kept it pre-dedupe, cand drops it as an edge over the deduped play order = the Task 1 interior-over-deduped-pool ruling's predicted case
2026-10-24T04:47:24-0400 Task 8: review t8-rev (Opus) -> spec ✅, Needs fixes: Important 1 (no test separates candidate membership from r1_dec; M1/M2 survive), Important 2 (INSTRUCTIONS attributes an invented 'tuning chatter' direction to the operator). verdict /Users/shawn/projects/llama/.claude/worktrees/junk-filter/.superpowers/sdd/junk-short-keep/t8-rev/handback.md sha256 e5046c1ea16521b6
Ruling: Minors 2 (refuse rows lacking short_kept), 5 (90% boundary + untested bar classes) and 7 (first10.md blind; answers in a separate file; add position/floor_sec) go into fix round 1 — each bears directly on Task 9's hand-check and premise 2 — cost if wrong: a slightly larger fix diff.
Task 8: minor (deferred): neighbour dropped_today covers only short-arm drops (59 entries in 37 rows dropped for other reasons shown false); consider kept_now
Task 8: minor (deferred): :389 except Exception swallows cache miss/JSON error into empty neighbours; report ia.misses
Task 8: minor (deferred): answers dict last-wins; duplicates/unknown rows/rule_right-vs-decision contradictions not refused
Task 8: minor (deferred): neighbour test asserts only 1<=len(nb)<=5 (±1 window mutant survives)
Task 8: minor (deferred): INSTRUCTIONS rule summary omits crowd/applause from the junk list
Task 8: minor (deferred): score.md PASS does not say the 4th (human) part of the bar is open
Task 8: ⚠️ for Task 9/Checkpoint A: kept strata never draw r1-kept rows of census kind crowd (13), non-performance (2), spoken-broadcast (1) — 'zero kept non-performance' tests only other kinds; the 4th bar part is human
2026-10-24T04:47:24-0400 Task 8: fix round 1 dispatched (resumed a8bf6745fec5512e7, Sonnet, dir t8-fix1, FIX_BASE 76c1830); meter 5h 45% / wk 93%
2026-10-24T04:50:13-0400 Task 8: fix round 1 DONE (c7625c9, 4986 passed/1 skipped/8 deselected); M1/M2 not run by implementer -> asked of re-reviewer; leftover unused 'a = answers.get' line
2026-10-24T04:50:13-0400 Task 8: re-review dispatched (t8-rr1, Opus, a6bad306dca85700e); meter 5h 46% / wk 93%
2026-10-24T04:54:00-0400 Task 8: fix round 1/5 (5 addressed, 0 open — membership test, INSTRUCTIONS wording, short_kept refusal, 90% boundary, blind first10; commits 76c1830..c7625c9) re-review t8-rr1 Opus: all addressed; M1/M2/M3/M3b/M5/M7-M10 killed in scratch copies (sentinel-proven)
Task 8: minor (deferred): membership test row C (in show, short_kept false) has a non-kept kind, so M1b (kept = in_show) survives; give it kind "music" (measured: kills M1b, 37/37 pass)
Task 8: minor (deferred): unused 'a = answers.get(...)' line in score()'s first10 loop (short_keep_probe.py:513)
Task 8: complete (commits 5d3e452..c7625c9, review clean after fix round 1)
2026-10-24T11:29:38-0400 Operator ruling (relayed by llama-db), verbatim: "--no-repro-gate approved" (Shawn, 2026-10-24 ~11:25). Basis as llama-db put it: all 21 drift-held rows are shows whose stored show.json was written 2026-09-05..10-21, before pieces 1-3 were applied to the library, so the drift is in the stored inputs, not the branch; base and cand read the same inputs.
2026-10-24T11:31:39-0400 Task 9 Step 3 (after ruling): compare --no-repro-gate rc 0 -> ~/.llama-harness/piece4/compare (summary: needs-LLM held base 186 cand 186; needs_llm.txt base 653 cand 654; holds_delta 11 cleared/34 added; apply lists not written (rekeyed arm); no overrides-validation refusal); sibvocab: 630 of 5024 (5024 = spec 8 figure) -> /Users/shawn/.llama-harness/piece4/sibvocab/sibvocab.txt
2026-10-24T11:31:39-0400 Task 9 Step 5: packets --seed 47 -> /Users/shawn/.llama-harness/piece4/hc/packet.jsonl (60 rows, sha256 c242c54e..), INSTRUCTIONS.md; fleet check: 5h 2% / wk 0% (both reset), 2 Sonnet checkers ≈ <=10 pts each x1.5 -> fits
2026-10-24T11:31:39-0400 Task 9: checkers dispatched t9-hc1 (rows 1-30, Sonnet, ab7dea4ec43f1133e) and t9-hc2 (rows 31-60, Sonnet, a37fa4e0bd268ebae); answers to /Users/shawn/.llama-harness/piece4/hc/answers-{1,2}.jsonl
2026-10-24T11:32:05-0400 Task 9 Step 4 checks so far: 6(e) matches — losses 10 shows (ratdog-2007-08-12 19, derektrucksband-2004-11-20 12, belafleck-2003-04-12 2, 7 at 1), gains 12 shows incl darkstarorchestra-2015-07-11 12; 6(d) 0/0; 6(b) classes exact. needs-LLM net +1 (6 in: deadandcompany-2015-10-29, discobiscuits-2001-09-08, mountaingoats-2018-04-13, ratdog-2007-08-12, soundtribesector9-2004-05-01, stringcheeseincident-2005-03-25; 5 out: darkstarorchestra-2015-07-11, joerussosalmostdead-2017-08-31, radiators-2008-12-06, stuallenandmarshotel-2014-12-30, yondermountainstringband-2006-08-26)
2026-10-24T11:32:16-0400 Task 9: t9-hc2 DONE — 28/30 rule_right; wrong rows 36 (kept 0.0 s 'Promised Land >' stub, gd73-10-29d2t01_vbr.mp3) and 46 (dropped untagged edge '01 Intro.mp3', checker says keep, low); no archive.org pages opened
2026-10-24T11:33:33-0400 Task 9: t9-hc1 DONE — 29/30; wrong row 25 (dropped untagged edge skb2004-09-24d1t01.mp3 80 s; taper lists 'Tuning/Introduction'; checker says keep, low)
2026-10-24T11:33:33-0400 Task 9: score PASS right 57 wrong 3 of 60 (95.0%), 0 forbidden kept/dropped, 0 missing -> /Users/shawn/.llama-harness/piece4/hc-score/ (score.md, first10.md blind, first10-answers.md); answers.jsonl sha256 77fe89b3e0909bdd.. (= answers-1 b7691c26.. + answers-2 69e648ef..)
2026-10-24T11:34:01-0400 Task 9: Opus pre-screen dispatched (t9-pre, Opus, a203ef3b3e4c842bd): rows 25/36/46 classes + sibvocab premise 3; meter 5h 4% / wk 0%
2026-10-24T11:47:46-0400 Task 9: t9-pre (Opus) DONE: rows 25/46 class A (checker error), row 36 class C (audio-less 0.0 s stub kept; fix: zero duration skips the short rule). Premise 3: JUNK_PART no change (~200 variants, limitation); NONPERF misses broadcast/PA — 6 rule-kept non-performance files in the library (5 delivered); measured addition drops exactly those 6. PRE-EXISTING SEVERE: 20 GD shows ship every song twice (X.mp3 + X_vbr.mp3), 17 delivered; orchestrator verified 1974-09-11 station manifest read-only (45 tracks, pairs). verdict .superpowers/sdd/junk-short-keep/t9-pre/handback.md sha256 6c1daf27cd196151
2026-10-24T11:47:46-0400 Task 9 Step 6: acceptance.md committed 2c95825. STOP at Checkpoint A (Step 7).
CHECKPOINT A RULINGS (Shawn, 2026-10-24 ~12:30, relayed by llama-db), verbatim: "Recommendations accepted". The recommendations as llama-db put them, verbatim:
1. Row 36 audio-less stubs: FIX — in junk._apply_short_rule a zero duration does not enter the short rule (only ever drops; re-marks 3 corpus rows).
2. NONPERF: FIX — add the pre-screen's measured narrow addition (on/over the PA, closing/exit/outro music, case-sensitive call sign + existing qualifiers, `host #N`); it must newly drop exactly the 6 library files and lose no music (re-measure and show it).
3. JUNK_PART crowd/tuning variants (~200): ACCEPT as a spec section 7 limitation; record it there.
4. Sample coverage: run ONE Sonnet checker over just the 16 reference crowd(13)/non-performance(2)/spoken-broadcast(1) keeps (after the item-2 fix, against the candidate), report the result at Checkpoint B.
5. Doubled _vbr derivatives (20 GD shows): NOT in this branch — a separate small fix after piece 4 (keep one derivative per original within the winning format). Correction to your report: they are not on air — transmitter requires broadcast.m3u and all 17 are unvoiced; the risk is a future `emcee run`. Leave them alone; just list them in the record as a known follow-up.
Proceed: Task 10 (items 1-2), the item-4 check, then Tasks 11-14, then STOP at Checkpoint B (Task 15). Brakes unchanged (5h 85%, week 97%).
2026-10-24T12:30:12-0400 Ruling: Task 10 implementer on Sonnet — both fixes are vocabulary/reading changes (an extra NONPERF alternation; a zero-duration skip), not a structural change to the rule — cost if wrong: a fix round or an Opus re-dispatch.
Task 10 BASE=2c95825
2026-10-24T12:31:17-0400 Task 10: implementer dispatched (t10-impl, Sonnet, a2be727da660ba6a7, budget 90m); meter 5h 9% / wk 4%
2026-10-24T12:35:48-0400 Task 10: implementer DONE, cbd35c5, 5012 passed/1 skipped/8 deselected; corpus re-measure: exactly 9 decisions change keep->drop (ruling 1: bluegroundundergrass-2008-04-04 trk04, gd73-10-29d2t01_vbr, gd74-09-11v3d2t03_vbr; ruling 2: guster WXRT Intro, JRAD over PA, RRE on PA, theotherones d2t03/d2t14/d4t08); concern: census kinds of 3+3 of them are music/music-fragment (machine census; rows are exactly the ruled ones)
2026-10-24T12:35:48-0400 Task 10: reviewer dispatched (t10-rev, Opus, a85ca70fec9e75862); Task 10 Step 2 cand-a2 arm running (bg byt8egrvb) at cbd35c5 clean; meter 5h 10% / wk 4%
2026-10-24T12:39:07-0400 Task 10 Step 2 (orchestrator): cand-a2.json at cbd35c5 clean (12:35:40-12:36:47, rc 0) sha256 e7976e25..; compare-a2 --no-repro-gate rc 0; arms-a2 (sha256 f8906564..): changed 1531, files added 2639, cleared 20, added 34 (holds lists identical to cand), 0 BLOCKS MERGE, 0 override moves, fills 10/12 unchanged; cand vs cand-a2 differ on exactly 7 shows / 9 files, all removals, all ruled (bgug trk04; gd73 d2t01_vbr; gd74 v3d2t03_vbr; guster D1T01; JRAD s1t01; RRE d2t01; theotherones d2t03/d2t14/d4t08); reference-reproduction differences 40 = those 7 shows + sts9-2005-02-07, x5 fields
2026-10-24T12:39:07-0400 Ruling 4: packet /Users/shawn/.llama-harness/piece4/hc-a4/packet.jsonl (16 rows: reference keeps of kind crowd 13 / non-performance 2 / spoken-broadcast 1, all still kept by cand-a2; sha256 7f5051ef..; builder orch-r1/briefs/item4_packet.py); checker dispatched (t10-a4hc, Sonnet, a31111371a0180648); meter 5h 14% / wk 4%
2026-10-24T12:39:50-0400 Ruling 4 check: t10-a4hc (Sonnet) DONE — 10/16 rule_right; 6 kept rows it would drop, all crowd-only: rows 1 'Not Fade Away Chant', 2 'crowd/tuning jam' (edge), 10 'Unity College chanting', 11-12 'Crowd Doing Not Fade Away', 15 'crowd/1812 Overture' (low); answers sha256 in hc-a4; for Checkpoint B (pre-screen had leaned keep on crowd chants; operator accepted crowd/tuning variants as a limitation)
2026-10-24T12:42:05-0400 Task 10: review t10-rev (Opus) Approved, spec ✅, 0 Critical/Important; independent re-measure over 13,202 short drops + 75,277 library titles: only ruled rows change; 7/9 mutants caught. verdict sha256 aae910f6621b5988
Task 10: minor (deferred): spec:204 stale counts (now 691 junk drops; 3 newly dropped carry census kind music, ruled PA/host)
Task 10: minor (deferred): spec:189-191 'no song, segue or fragment among the rows newly dropped by any other path' vacuous; reword per review
Task 10: minor (deferred): section 7 should record the call-sign false-positive class (K/W band abbreviation or all-caps title beside a qualifier; 'Exit Music (For a Film)'); measured 0
Task 10: minor (deferred): no pin that a 1 s tagged file is still kept (threshold mutant M7 survives)
Task 10: minor (deferred): wrap\w* qualifier untested (M9 survives); add 'KBFH Wrap-Up'
Task 10: minor (deferred): spam-shaped zero-duration file now records 'implausibly short' not the tripwire reason (drop-only)
Task 10: minor (deferred): spec section 1 / 2.1 / 2.5 'unless' list lacks the zero-duration exception cross-reference
Ruling: Task 10's spec-text minors (1, 2, 3, 7) are batched into Task 23's docs pass rather than a fix round now — they change no code and nothing downstream reads them before Checkpoint C — cost if wrong: the spec carries stale counts until Task 23.
Task 10: complete (commits 2c95825..cbd35c5, review clean)
2026-10-24T12:43:19-0400 acceptance.md updated with Checkpoint A rulings verbatim + cand-a2 + ruling-4 check: 76af131
Task 11 BASE=76af131
2026-10-24T12:43:19-0400 Task 11: implementer dispatched (t11-impl, Sonnet, ae75b3a9f19c542e8, budget 90m); meter 5h 18% / wk 5%
2026-10-24T12:46:30-0400 Task 11: implementer DONE, 5c78650, 5019 passed/1 skipped/8 deselected; deviation: one joined 'broadcast fields changed: ...' message (fields titles, sets, segues, set_breaks, date, venue, city) instead of first-failure-returned, to keep test_briefing_reusable_names_every_changed_broadcast_field; concern: shipped_diff/classify still call a show that gained a short-kept track 'structure-changed', so reapply skips it without --allow-structure-change
Ruling: Task 11's joined message is accepted — spec 5.3 fixes what is compared, not the message shape; the reuse decision (None vs not) is identical either way and 'tracks differ' still comes first; keeping the existing test avoids moving an unrelated expectation — cost if wrong: reason text differs from the plan's brief.
Ruling: the 'structure-changed' classification of a show that gained a short-kept track is not Task 11's scope (spec 5.2 assigns extending reapply to the bulk-apply plan); carried to the Checkpoint B report as an item for the operator's bulk-apply plan — cost if wrong: a bulk apply that skips ~1,500 shows as structure-changed until run with --allow-structure-change.
2026-10-24T12:47:26-0400 Task 11: reviewer dispatched (t11-rev, Opus, ac2bc415cc69f4c36); meter 5h 20% / wk 5%
2026-10-24T12:51:53-0400 Task 11: review t11-rev (Opus) Approved, spec ✅, 0 Critical/Important; joined message changes no reuse decision (only caller branches on None); 10/11 mutants caught. verdict sha256 145354cbe9fb54f9
Task 11: ⚠️ reapply structure gate (shipped_diff marks every show that gained a short-kept file structure-changed) — already ruled: carried to Checkpoint B / bulk-apply plan
Task 11: ⚠️ old show.json filename format must match current gather or 'tracks differ' fires — Task 15's reuse count measures it
Task 11: minor (deferred): 'tracks differ' return untested (mutant survives); add assertion to test_briefing_reusable_reasons
Task 11: minor (deferred): 173-case test passes on old code (fields identical); test_a_moved_real_break_forces_a_brief unmarked pin
Task 11: minor (deferred): None break key (break preceded only by short-kept tracks) untested
Task 11: minor (deferred): briefing_reusable docstring stale ('first failing reason'; no short-kept/filename mention)
Task 11: complete (commits 76af131..5c78650, review clean)
Task 12 BASE=5c78650
2026-10-24T12:52:57-0400 Task 12: implementer dispatched (t12-impl, Opus per plan, a06ee43c476f9deae, budget 150m); meter 5h 24% / wk 6%
2026-10-24T12:53:12-0400 RELAY-NOW received from llama-db: finish Task 12 through review/fix, start nothing new, HANDOFF, disarm, RELAY-READY
2026-10-24T13:07:18-0400 Task 12: implementer DONE_WITH_CONCERNS, bacf701 57c1026 5a89be0, 5045 passed/1 skipped/8 deselected (./.venv/bin/python -m pytest -q -p no:cacheprovider); 8/8 mutants caught (i2 approximate); concerns: aside consulted in keep-in-place branch; reapply outside show_unit needs its own put_back/discard (Task 13)
2026-10-24T13:08:17-0400 Task 12: reviewer dispatched (t12-rev, Opus, a9976ee54076f465a); meter 5h 32% / wk 7%
2026-10-24T13:15:00-0400 Task 12: review t12-rev (Opus) -> spec ✅, Needs fixes: Important 1 (aside not single-use: a second set_aside in one unit overwrites it; reuse_into reads an aside another plan filled; probe: wrong audio under 03 - Jam.mp3 after a failed two-pass unit; unreachable today, Task 13 would wire it). full (i2) mutant caught. verdict sha256 c06e9c001a24f54e
Ruling: Task 12 Minor 1 (keep-in-place trusts packaged names alone; a same-titled replacement at the same position ships the old audio unflagged) and Minor 2 (limitation 5 docstring omits a part-way put_back failure) join fix round 1 — Minor 1 is a wrong-audio path on a strict surface with a one-line fix — cost if wrong: a slightly larger fix diff.
Task 12: minor (deferred): mid-file imports with noqa E402 in test_show_unit.py / test_stage_package.py
Task 12: minor (deferred): broad except Exception in plan_reuse (safe direction)
Task 12: minor (deferred): restore/put_back order correct but not load-bearing (m6 survives; equivalent)
2026-10-24T13:15:57-0400 Task 12: fix round 1 dispatched (resumed a06ee43c476f9deae, Opus, dir t12-fix1, FIX_BASE 5a89be0); meter 5h 36% / wk 7%
2026-10-24T13:19:10-0400 Task 12: fix round 1 DONE (ba4e10a, 5049 passed/1 skipped/8 deselected); set_aside refuses an existing aside; build_package reads the aside only if it made it; keep-in-place also requires library pairing; 4 new tests red-then-green
2026-10-24T13:20:05-0400 Task 12: re-review dispatched (t12-rr1, Opus, a60c6364d351e8cfe); meter 5h 39% / wk 8%
2026-10-24T13:23:58-0400 Task 12: fix round 1/5 (3 addressed, 0 open — single-use aside, keep-in-place source pairing, limitation-5 docstring; commits 5a89be0..ba4e10a) re-review t12-rr1 Opus: all addressed; mutants ma/mb/mc caught; original probe restores byte-for-byte
Task 12: minor (deferred): unreadable show.json at plan time now re-downloads an unchanged show (safe direction; rare)
Task 12: minor (deferred): build_package docstring (package.py:40-41) omits the source-pairing keep-in-place condition
Task 12: minor (deferred): two-pass unit test does not assert the refusal message (add match="audio aside already exists")
Task 12: minor (deferred, out-of-scope obs): an in-place pass re-tags kept audio the unit cannot restore (by design); relevant only if Task 13 threads two passes into one unit
Task 12: minor (deferred): refusal text says 'twice in one unit' even for a leftover aside outside a unit (cosmetic)
Task 12: complete (commits 5c78650..ba4e10a, review clean after fix round 1)

## HANDOFF (2026-10-24T13:23:58-0400, peer orch-r1 68216777-fbbf-4e29-a05f-d8f145d56c7f -> successor, on llama-db's RELAY-NOW)
State: Tasks 0-12 COMPLETE and reviewed (Opus) at HEAD ba4e10a on branch held-backlog-junk-filter, tree clean. Suite at ba4e10a: 5049 passed, 1 skipped, 8 deselected, 26 warnings (t12-fix1, ./.venv/bin/python -m pytest -q -p no:cacheprovider). Nothing in flight; no background shells or monitors; tick disarmed (below).
Next: Task 13 (thread plan_reuse through redo/fix/triage/reapply; brief already extracted at $D/orch-r1/briefs/task-13-brief.md; plan's implementer line applies), then Task 14 (brief at $D/orch-r1/briefs/task-14-brief.md), then STOP at Checkpoint B = Task 15 (brief $D/orch-r1/briefs/task-15-brief.md). No deliver-path change before llama-db's go at B.
Workspace: my briefs + mandates template (with THIS session's trailer — successor: regenerate the trailer for your own session) in $D/orch-r1/briefs/; review packages in $D/orch-r1/pkg/. Child dirs used: t8-impl t8-rev t8-fix1 t8-rr1 t9-hc1 t9-hc2 t9-pre t10-impl t10-rev t10-a4hc t11-impl t11-rev t12-impl t12-rev t12-fix1 t12-rr1 (single-use; pick fresh names, e.g. t13-impl).
Measurement artifacts (~/.llama-harness/piece4/): base.json, cand.json (76c1830), cand-a2.json (cbd35c5), compare/, compare-a2/, arms/, arms-a2/, sibvocab/, hc/ + hc-score/ (Checkpoint A hand check), hc-a4/ + hc-a4-score/ (ruling-4 check). Base tree base-e37f670 (detached worktree; remove later with git worktree remove). acceptance.md: docs/superpowers/2026-10-23-junk-short-keep-evidence/acceptance.md (commits 2c95825, 76af131).
Carried items:
- CHECKPOINT A RULINGS (verbatim above in this ledger and in acceptance.md): 1 zero-duration stubs FIX (done, Task 10); 2 NONPERF FIX (done, Task 10); 3 JUNK_PART variants ACCEPT as section 7 limitation (done, Task 10); 4 sample-coverage check — DONE EARLY, report at Checkpoint B: Sonnet checker 10/16 agree; the 6 it would drop are all crowd-only, still kept (deadandcompany-2015-11-17 'Not Fade Away Chant'; discobiscuits-2004-11-27 'crowd/tuning jam' edge; thebrew-2008-04-12 'Unity College chanting'; thedead-2015-07-05 'Crowd Doing Not Fade Away' x2; umphreysmcgee-2006-10-07 'crowd/1812 Overture' low); packet hc-a4/packet.jsonl sha256 7f5051ef.., answers 975be688..; the pre-screen had leaned keep on crowd chants; 5 doubled _vbr derivatives = known follow-up outside this branch (not on air; all 17 delivered unvoiced; risk = a future emcee run), recorded in spec section 7 and acceptance.md.
- For Checkpoint B / the operator's bulk-apply plan: reapply's structure gate — shipped_diff marks every show that gained a short-kept file 'structure-changed', so reapply skips it unless --allow-structure-change (~1,500 shows). Not changed here (spec 5.2 assigns extending reapply to the bulk-apply plan). Ruled and ledgered.
- For Task 15: old show.json filename format must equal current gather's or briefing reuse's 'tracks differ' fires on every old show — the reuse count (expect >= 1,017) measures it (Task 11 ⚠️).
- For Task 13: build_package/set_aside are single-use per unit (a second re-packaging in one unit refuses and restores); reapply runs outside show_unit and needs its own entry deletion of a leftover aside + put_back on failure + discard_aside on success; keep fix --untitled's second pass --from brief (no second set_aside). An in-place pass re-tags kept audio the unit cannot restore (by design).
- Task 17: the 'duplicate key' refusal ("7" and "07") must run before rekey_raw (Task 3 minor, predecessor). Task 19: --apply must call override_keys.rekey_raw (no copy) (Task 6 ⚠️). Task 17 consumes gather.final_kept(..., short_keep=False) (Task 4).
- Task 23 docs pass: Task 10's spec-text minors (spec:204 stale counts; spec:189-191 vacuous wording; section 7 call-sign false-positive class incl. 'Exit Music (For a Film)'; section 1/2.1/2.5 zero-duration cross-reference) — ruled to batch there.
- Open, Shawn's: REKEY_MIN_VERSION = 2.18.0 confirmation; the separate bulk-apply plan.
Rulings made by orch-r1 (in order; all also above): Task 8 Minors 2/5/7 into fix round 1; Task 9 arms run during Task 8 review; Task 10 on Sonnet; Task 10 spec-text minors batched to Task 23; Task 11 joined reason message accepted; Task 11 structure-gate item carried (not Task 11 scope); Task 12 Minors 1-2 into fix round 1. Predecessor's rulings in $D/orch/ledger.md stand.
Deferred minors: every 'minor (deferred)' line in this ledger (Tasks 8, 10, 11, 12) and in the predecessor's (Tasks 1-7) — for the final whole-branch review.
Escapes: none.
2026-10-24T13:24:07-0400 disarmed: CronDelete ceeba840; rm armed-68216777; armed-global kept (other armed-* present); STATE.md mode idle, in-flight []
