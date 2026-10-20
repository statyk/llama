# SDD ledger — plan: docs/superpowers/plans/2026-10-19-held-backlog-tier1.md
peer session d4918098-e484-43e4-8857-2fae7853ad18; worktree /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1; start f1744ad; 2026-10-19T14:32:07-0400
Spec: docs/superpowers/specs/2026-10-19-held-backlog-guard-fixes-design.md (approved)
Meter at start: 5h 19% (resets 16:19), 7d 85% (resets Oct 24 06:59). Brake: 5h>85% or 7d>92%.

## Escapes
(none)

## Log
- 2026-10-19T14:32:07-0400 setup: ledger created; venv + baseline suite running
- 2026-10-19T14:32:41-0400 venv ok: llama -> worktree packages/llama/src/llama/__init__.py. Baseline `./.venv/bin/python -m pytest -q -p no:cacheprovider`: 3153 passed, 1 skipped, 8 deselected (f1744ad)
- 2026-10-19T14:32:41-0400 keepalive tick armed (cron 9067ca5e, 13,43), STATE.md at $D/STATE.md
- 2026-10-19T14:32:41-0400 dispatched preflight (opus, read-only conflict scan); Task 1 waits on its rulings

## Preflight (opus, handback at $D/preflight/handback.md; 6 BLOCKER, 9 MAJOR, minors) — 2026-10-19T14:55:45-0400
Pair/self-consistency table: in $D/preflight/handback.md (full) — compressed: T1(B1,M6) T11(M4) T12(B2) T13(B3) T17(B4) T18(B5,M1) T19(B6); others consistent apart from MAJOR/MINOR below.
- Ruling: B1 T1 extract_setlist test description -> "An amazing night of music, seeded with love." (parses 0 items) — plan's prose parses 3 low items so fallback never reached — cost if wrong: one test string.
- Ruling: B2 T12 add spec's "race track"->"racetrack" fold in _place_tokens (spec line 418 names it) — plan's own test row fails without it — cost: one fold row.
- Ruling: B3 T13 fix fixture: _jb_event gains state kw, test_gather_venue_equivalent_passes_no_mismatch passes "DC" — spec step 1 mandates cities_compatible; plan's "gd73 tests unchanged" yields to spec — cost: one existing test fixture edited.
- Ruling: B4 T17 rename the new test helper (not _tracks; e.g. _titled_tracks) — collides with existing _tracks(n,dur) (36 callers) — cost: none.
- Ruling: B5 T18 unmatched encore title "JBG" -> "Casey Jones" — JBG matches Johnny B. Goode — cost: one test string.
- Ruling: B6 T19 snapshot tests: touch entry.ws.lock before snapshot (or exclude .lock) — file_lock leaves .lock — cost: none.
- Ruling: M1 T18 5c.3 leading-parenthetical fold is a FALLBACK tier inside _closer_candidates, used only when unfolded tiers find nothing; keep test_closer_matching_preserves_a_leading_parenthetical unchanged — spec 801-803/814-817 "no other anchoring rule changes / zero changes on already-anchored shows" — cost: fold may recover fewer closers than plan's version.
- Ruling: M2 T5 identity check requires llama.__file__ under <script root>/packages/llama/src — nested worktree passes the parents[1] check wrongly — cost: none.
- Ruling: M3 T5/T20 enumerate shows/ dirs and derive state per show inside per-show error handling, not catalog.iter_shows (one bad overrides.json aborts it) — Review Focus 2 — cost: small duplication.
- Ruling: M4 T11 near-miss test must pass the vote (e.g. 8 glued titles + 3AM + 01ABBA) so the lookahead is load-bearing — cost: none.
- Ruling: M5 T20 patch herder.tasks._sleep in the transport-failure test — cost: none.
- Ruling: M6 T1 switch test_stage_gather.py:2020,2072,2112,2121 3-tuple unpacks of build_canonical to attribute access — cost: none.
- Ruling: M7 T4/T5/T6 add "date" {old,new}|null to ShowReplay and packaged_exposure; shipped diff compares against the VETTED show (what would ship) — Contracts list date as shipped; vet can adopt a placeholder date — cost: one arm key beyond contract text.
- Ruling: M8 pre-screen + sample replacing full hand reads: RATIFIED per llama-45 brief ("operator approved the Opus pre-screen at checkpoints") — cost: if strict lists needed full reads, operator decides at each checkpoint.
- Ruling: M9 T9 2b emits no demotion note for positions in overrides.titles — spec 576-577 override never judged — cost: none.
- Ruling: T4 minor — no stored vetting.json => needs-LLM, per spec lines 322/840, even when gather flags remain — cost: bucket counts shift between needs-llm/still-held; nothing applied either way.
- Ruling: remaining MINORs (missing imports, T2 typo/'make' builder, T5 logging.disable restore, T11 gather.py in Files + glued vote on both paths, T14 shared prose-join helper, T16 resolved is a count, T18 note to notes.json not conflicts (Global Constraint 29 wins), T21 refuse --clear-* with --untitled, add catching test rows for T9(d)/T10(c)/T14(a) mutants) — carried into each task's dispatch; implementer applies — cost: small.
- OPEN for llama-45 at Finish: spec Kickoff says "Review mode: Fable" (final branch reviewer Fable); brief says every reviewer Opus. Not deciding now; raise before the final review.
- 2026-10-19T14:56:21-0400 Task 1: dispatched t1-impl (opus) BASE f1744ad; rulings B1, M6 carried
- 2026-10-19T14:57:03-0400 Ruling (llama-45, operator): Review mode Fable — per-task reviewers Opus; FINAL whole-branch review on Fable (operator-approved upgrade for this run). OPEN item closed.
- 2026-10-19T15:00:41-0400 Task 1: impl DONE dd0bf7c (3163 passed); deviations: notes.json written before show.json; one test added post-impl. Dispatched t1-rev (opus)
- 2026-10-19T15:02:39-0400 Task 1: review t1-rev (opus): spec ✅, quality Approved, 0 Crit/0 Imp, 4 minor. Baseline also had 26 warnings (not new).
- Task 1: minor (deferred): extract-with-provider negative case unpinned (needs_llm=True above provider check survives) — CARRIED into Task 4 dispatch (consumer of needs_llm) as an extra test
- Task 1: minor (deferred): ("extract_setlist","align_structure") tuple unreachable (observation)
- Task 1: minor (deferred): _read_show_notes strict read — malformed notes.json raises in show/triage (consistent with show.json)
- Task 1: complete (commits f1744ad..dd0bf7c, review clean)
- 2026-10-19T15:03:04-0400 Task 2: dispatched t2-impl (sonnet) BASE dd0bf7c; rulings: fingerprint dict typo, make() builder
- 2026-10-19T15:05:18-0400 Task 2: impl DONE 1ba0819 (3171 passed); deviation: shared _slim() helper. Dispatched t2-rev (opus)
- 2026-10-19T15:08:25-0400 Task 2: review t2-rev (opus): spec ✅, Approved, 0/0, 6 minor. Real-cache --from-cache exercised by reviewer OK.
- Task 2: minor (deferred → CARRIED to Task 5): CacheOnlySetlistFM.setlist can raise on malformed slfm json where real client returns None (0/3466 today) — mirror try/except
- Task 2: minor (deferred → CARRIED to Task 5): code_identity -dirty / version fallback untested (Task 20 load_list depends)
- Task 2: ⚠ for Task 5: CacheMiss is not IAError — run must catch CacheMiss and read_model validation errors per show
- Task 2: minor (deferred): fingerprint test lacks audio_format/jerrybase asserts; setlistfm_client test lacks cache_dir assert; setlistfm_configured restates make_client key test (plan-mandated); capture_fixture bad args IndexError
- Task 2: complete (commits dd0bf7c..1ba0819, review clean)
- 2026-10-19T15:08:43-0400 Task 3: dispatched t3-impl (sonnet) BASE 1ba0819
- 2026-10-19T15:10:44-0400 Task 3: impl DONE 383e01a (3174 passed); no RED observed (tests+code together). Dispatched t3-rev (opus)
- 2026-10-19T15:12:34-0400 Task 3: review t3-rev (opus): spec ✅, Approved, 0/0, 3 minor; reviewer mutants: 2/2 caught by predicted tests
- Task 3: minor (deferred → CARRIED to Task 15): run_vet_research writes notes.json AFTER vetting.json (done-marker) — reorder marker-last before vet notes become non-empty
- Task 3: minor (deferred): run_vet_research show param now dead (brief-mandated); no apply_vet unit test for needs_review True→False
- Task 3: complete (commits 1ba0819..383e01a, review clean)
- 2026-10-19T15:13:06-0400 Task 4: dispatched t4-impl (opus) BASE 383e01a; carried M7 (date + diff vs vetted), spec no-vetting=>needs-LLM, package flags count for brief gate, T1 minor provider test, RF3
- 2026-10-19T15:23:11-0400 Task 4: impl DONE_WITH_CONCERNS 0b3ece1,30461a1 (3225 passed). Mutation: 13 mutants, 12 caught as predicted; (l) briefing_reusable on gathered show survived → test added, now caught. Concerns: count-change → structure-changed (beyond brief); Legs.replayed_show + scratch guard; Task 19 step 5 "legs.vet None only on still-held" stale under ruling (CARRY to T19); Task 5 must map overrides ValidationError → unreplayable (CARRY to T5). Dispatched t4-rev (opus)
- 2026-10-19T15:25:47-0400 Task 4: review t4-rev (opus): spec ✅, Approved, 0/0, 5 minor. Deviation (a) count-change⇒structure-changed judged correct (conservative on strict surface).
- Ruling: T4 deviation (a) accepted — a changed track list is a larger structural change than a relabel; must go through the structure-changed hand check — cost if wrong: some would-be needs-brief shows land in the structure-changed list for hand check.
- Task 4: minor (deferred → CARRIED to Task 5): count-change rows report new:None — populate new/new_source from new.tracks[i] when i < len (keep every index)
- Task 4: minor (deferred → CARRIED to Task 5): scratch guard protects only ws.dir — also refuse scratch at/inside shows/ (ws.dir.parent)
- Task 4: minor (deferred → CARRIED to Task 14): brief_flags re-runs guard; normalize_briefing must apply at both guard calls + reused briefing (shared helper)
- Task 4: minor (deferred): held branch gives carried package flags precedence (still-held-package) — untested with both kinds; mid-file test imports
- CARRY to Task 19: plan step 5 "legs.vet None only on still-held" stale (never None past classify); replayed_show.review_flags lacks package flags — final show must add carried_flags
- Task 4: complete (commits 383e01a..30461a1, review clean)
- 2026-10-19T15:26:20-0400 Task 5: dispatched t5-impl (opus) BASE 30461a1; carried M2, M3, CacheMiss/ValidationError per show, logging.disable restore, T2 minors (slfm malformed, code_identity tests), T4 minors (count-change new values, scratch guard shows/)
- 2026-10-19T15:37:28-0400 Task 5: impl DONE a838a66,f39ad88 (3270 passed); 5/5 guard mutants caught as predicted. Real-library smoke (held, mktemp out): 18.4 s, 1073 shows: still-held 538, needs-llm 492, needs-brief 43, unreplayable 0; 581/581 non-needs-LLM reproduce. ~/.llama mtime changes attributed to concurrent operator llama run resume (ps confirms operator runs live, e.g. 'llama run resume 2026-10-09-dead-family-6' started 15:35:47). Extra refusals (overlap, missing --config, bad slugs); new arm states unknown/missing (Task 6 must accept — CARRY). Dispatched t5-rev (opus)
- 2026-10-19T15:41:46-0400 Task 5: review t5-rev (opus): spec ✅, Needs fixes — 1 Important (zero-writes test blind to a swallowed write; reviewer mutant B survived), 3 minor. Write-surface named risk: harness cannot have written pacing-state/provenance (modules not loaded) — attribution to operator run confirmed.
- Task 5: minor (deferred): --slugs missing file → traceback exit 1 not Refusal exit 2; herder not identity-checked; default mkdtemp scratch not overlap-checked
- CARRY to Task 6: compare must tolerate arm states unknown/missing/vetted/selected; decide 99% denominator treatment of state=unknown rows
- 2026-10-19T15:41:46-0400 Task 5: fix round 1 dispatched (resume t5-impl, opus) — Important 1; sentinel done-r1
- 2026-10-19T15:43:59-0400 Task 5: fix r1 commit 3263f45 (3271 passed; reviewer mutant B now caught by predicted test). Dispatched t5-rr1 (opus re-review)
- 2026-10-19T15:44:51-0400 Task 5: fix round 1/5 (1 addressed, 0 open — zero-writes on writable root; commits f39ad88..3263f45)
- Task 5: minor (deferred): helper test 'deleted file' half relies on ns mtimes (spurious fail on coarse-ts Linux FS)
- Task 5: complete (commits 30461a1..3263f45, review clean after r1)
- 2026-10-19T15:45:24-0400 Task 6: dispatched t6-impl (sonnet) BASE 3263f45
- Ruling: T6 denominator — held-scope state=unknown rows (outcome unreplayable) count in the 99% denominator as not reproducing — Contracts include unreplayable; conservative — cost if wrong: gate slightly stricter (0 unreplayable in today's smoke run)
- Ruling: T6 reports read identifier/asserted_dates/durations from <root>/shows/<slug>/ read-only; unmatched notes grouped 'other'; flags.txt "<family>: removed <n>, added <m>"; date in packaged_exposure (M7) — cost: none
- 2026-10-19T15:48:22-0400 Task 6: impl DONE_WITH_CONCERNS e5bf134 (3282 passed); no RED run; structure_changed rows outcome=would_be; 5c subsections deferred to T18; pilot test weak. Dispatched t6-rev (opus)
- 2026-10-19T15:51:39-0400 Task 6: review t6-rev (opus): spec ✅, Needs fixes — 3 Important (99% boundary untested: mutant survived; pilot swap never exercised: mutant survived; structure_changed_list content untested), 7 minor
- Ruling: T6 minor "--out reused without clearing" ELEVATED to Important — a stale predicted/pilot list beside a failing drift.txt invites applying a stale list (strict surface) — remove known output names before writing; exit 2 leaves prior files — cost: none
- Ruling: T6 ⚠ _in_denominator ignores arm scope (unknown rows count in --all arms too) — intended; safe direction (false exit 3, never false pass) — cost: possible spurious exit 3 on an --all arm with unreadable state
- Task 6: minor (deferred): hc_rows duplicates _hand_check selection; E731 lambda; silent "." root fallback & roots not compared; non-dict arm row → traceback; untested report bodies (briefings 2/3, hand-check order/cap, title_sources, structure_changed, 1c cut); 1c greedy regex
- 2026-10-19T15:51:39-0400 Task 6: fix round 1 dispatched (resume t6-impl, sonnet) — 4 findings; sentinel done-r1
- 2026-10-19T15:53:55-0400 Task 6: fix r1 commit 528ab8f (3286 passed; 4/4 mutants caught by written tests). Dispatched t6-rr1 (opus re-review)
- 2026-10-19T15:54:59-0400 Task 6: fix round 1/5 (4 addressed, 0 open — 99% gate pinned+integer, pilot swap pinned, structure list pinned, stale outputs cleared; commits e5bf134..528ab8f)
- Task 6: minor (deferred): no test that exit 2 removes nothing from a dir with prior outputs
- Task 6: minor (deferred → CARRIED to Task 7): OUTPUT_FILES hand-kept — add a test that every file a successful compare writes is in OUTPUT_FILES
- Task 6: complete (commits 3263f45..528ab8f, review clean after r1)
- 2026-10-19T15:55:16-0400 Task 7: dispatched t7-impl (sonnet) BASE 528ab8f; carried OUTPUT_FILES completeness test
- 2026-10-19T15:57:25-0400 Task 7: impl DONE 050c84b (3292 passed; RED observed). Interpretations: held=state; unreadable show.json + only low-confidence setlist excluded. Dispatched t7-rev (opus)
- 2026-10-19T15:59:14-0400 Task 7: review t7-rev (opus): spec ✅ (both interpretations upheld), Needs fixes — 1 Important (JS sort parseFloat prefix: date/slug order wrong, non-transitive), 4 minor
- Task 7: minor (deferred): no test of the state==held filter (deleting it survives); show.json read 3x per candidate; missing duration counts 0 + excluded rows leave no trace; NARRATION_FLAGS[1] unused, title_source None:, unused gather_only param
- 2026-10-19T15:59:14-0400 Task 7: fix round 1 dispatched (resume t7-impl, sonnet) — sort comparator; sentinel done-r1
- 2026-10-19T16:00:44-0400 Task 7: fix r1 commit 0038589 (3294 passed; node comparator test ran). Dispatched t7-rr1 (opus re-review)
- 2026-10-19T16:01:27-0400 Task 7: fix round 1/5 (1 addressed, 0 open — sort whole-string numeric; commits 050c84b..0038589)
- Task 7: minor (deferred): node comparator test slices JS by markers (errors loudly on rewrite)
- Task 7: complete (commits 528ab8f..0038589, review clean after r1)
- SLICE 0 COMPLETE (Tasks 1-7) at 0038589

## CHECKPOINT A — 2026-10-19T16:03:53-0400 (STOPPED, awaiting operator via llama-45)
- Suite at 0038589: `./.venv/bin/python -m pytest -q -p no:cacheprovider` 3294 passed, 1 skipped, 8 deselected; llama.__file__ in worktree.
- Tagged tier1-base = 0038589 (local tag). Arms run FROM THIS WORKTREE (HEAD == tier1-base); the separate held-backlog-tier1-base worktree was NOT created (brief: touch no other checkout) — needs llama-45 go before Checkpoint B.
- Operator 'llama run resume 2026-10-18-dead-tribute-11' (pid 55980, 15:53) live during the arms (read-only harness; self-compare unaffected).
- held arm: 15.9 s, 1073 shows: needs-brief 43, needs-llm 492, still-held 538, unreplayable 0. compare self → exit 0. Reproduction 581/581. Held drift: none.
- all arm: 38.9 s, 3468 shows: clean 2038, needs-brief 43, needs-llm 844, newly-held 4, still-held 538, unreplayable 1. compare self → exit 0. all-drift 5: aquariumrescueunit-2005-01-08 (single-set), gd1971-04-29 (jb closer UJB), gd1977-05-09 (venue Buffalo Memorial vs War Memorial), gd1985-06-24 (River Bend vs Riverbend), yondermountainstringband-2005-12-31 (researched, missing show.json → unreplayable).
- briefing guard reproduces 55/55; clean briefings firing base 0. slfm/cache misses 0. predicted_list 43, pilot 10.
- Outputs: ~/.llama-harness/{A-base-held.json,A-base-all.json,cmp-A-held/,cmp-A-all/}
- 2026-10-19T16:13:39-0400 CHECKPOINT A PASSED (operator via llama-45): tier1-base=0038589 accepted; drift + needs-LLM 492 match. APPROVED: run scripts/replay_holds.py run READ-ONLY in /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1-base (verify llama.__file__ first). -prev: ask llama-45 at C. Operator loop killed; confirm quiet library before each checkpoint's arms.
- Ruling: llama-45 said "proceed with slice 1 per the plan order"; plan order (and brief gates: B after slice 2, C after slice 1) puts slice 2 (Tasks 8-11) next — following plan order, stated in next report — cost if wrong: slices swapped; independent per plan line 183.
- 2026-10-19T16:14:02-0400 Task 8: dispatched t8-impl (opus) BASE 0038589
- 2026-10-19T16:21:08-0400 Task 8: impl DONE e416018 (3383 passed); mutants a-f,e2,g,h caught; 1 equivalent survivor (lma: filter). Concerns: recording_level_junk stricter (deviation); shared {} default; short uncorroborated tags = residue (FF,J,42,7-11). Dispatched t8-rev (opus)
- 2026-10-19T16:24:38-0400 Task 8: review t8-rev (opus): spec ✅, Approved, 0/0, 5 minor. Deviation (recording_level_junk non-empty after fuzzy_norm) accepted as more faithful to spec :569. Equivalent survivor verified (ordering-dependent; keep lma: filter).
- Ruling: T8 deviation accepted — spec :569 "item's own title"; demotes less (safe) — cost: a few junk tags on items titled with punctuation-only stay unresolved-candidates rather than demoted.
- Task 8: minor (deferred → CARRIED to Task 9): is_placeholder_title combines classes without is_real_title scope (True for 42/FF/J/7-11); no consumer — add a docstring scoping note (callers pre-gate on is_real_title, spec :576-577); Task 9 must keep is_real_title(t) and is_residue(t)
- Task 8: minor (deferred → CHECKPOINT B pre-screen note): residue class is "one word + date" (Ripple 1970-09-20, Drums 1977-05-08, Encore 12-31-99 demoted), P5 ruling mechanism
- Task 8: minor (deferred): shared {} default (MappingProxyType or comment); redundant 'or' assertion + mid-file import; no test for selected-missing-from-candidate with copying sibling
- Task 8: complete (commits 0038589..e416018, review clean)
- 2026-10-19T16:25:05-0400 Task 9: dispatched t9-impl (opus) BASE e416018; carried M9, is_real_title gate + d1t02 row, is_placeholder_title docstring, format-sibling note, Ripple pin
- 2026-10-19T16:33:13-0400 Task 9: impl DONE de14749 (3401 passed); 10/10 mutants caught. Deviations: format note gated on format_titles None; M9 in gather; blind_tag_gapfill.py now demotes w/o exemption; extra Track 01 row. Dispatched t9-rev (opus)
- 2026-10-19T16:37:09-0400 Task 9: review t9-rev (opus): spec ✅, Approved, 0/0, 5 minor. All 4 deviations verified (M9 order safe; blind_tag_gapfill read-only diagnostic; format-note gate correct; Track 01 row needed).
- Ruling: T9 deviations 1-4 accepted per review — cost: none on strict surface
- Task 9: minor (deferred): format-sibling loop near-duplicates _recover_format_titles; recording_level_junk votes over re-admitted files; blind_tag_gapfill.py fidelity drift (no corroboration/item_title); positions computed twice; format note threshold plain title_fraction (→ CHECKPOINT B note: format-sibling count may be inflated)
- Task 9: complete (commits e416018..de14749, review clean)
- 2026-10-19T16:37:34-0400 Task 10: dispatched t10-impl (opus) BASE de14749; carried T10(c) row, Track import, M9, notes-only
- 2026-10-19T16:45:44-0400 Task 10: impl DONE 84c8803 (3421 passed); mutants a-e + f-i caught (f survived first, test added). Deviation: strip_taper_markers fixpoint. Dispatched t10-rev (opus)
- 2026-10-19T16:49:52-0400 Task 10: review t10-rev (opus): spec ❌ — 1 Important (2a re-accepts 2b recording-level-demoted positions: J > J ×4 shipped), 3 minor. Fixpoint deviation accepted (1,158-string probe: never strips outside marker set). Wiring order verified. tnd label moves expected (spec:188-195).
- Ruling: T10 strip_taper_markers fixpoint accepted — spec:542 "no shipped title keeps a trailing taper marker" — cost: none found
- Task 10: minor (deferred → CHECKPOINT B note): junk/metadata vetoes judge whole core not per component (J > 05:27 contrived)
- Task 10: minor (deferred → CHECKPOINT B / operator): accepted titles may ship trailing -,@,^,~ (brief regexes verbatim; spec:502 vs :542 reading) — hand-check should look
- 2026-10-19T16:49:52-0400 Task 10: fix round 1 dispatched (resume t10-impl, opus) — skip 2b-demoted positions; sentinel done-r1
- 2026-10-19T16:52:22-0400 Task 10: fix r1 commit e5e4411 (3425 passed; mutants j,k caught; RED on behaviour). Dispatched t10-rr1 (opus re-review)
- 2026-10-19T16:53:40-0400 Task 10: fix round 1/5 (1 addressed, 0 open — 2a skips 2b-demoted positions; commits 84c8803..e5e4411)
- Task 10: minor (deferred): docstring "J > J x 3" wording (rule is recording-level)
- Task 10: complete (commits de14749..e5e4411, review clean after r1)
- 2026-10-19T16:54:03-0400 Task 11: dispatched t11-impl (sonnet) BASE e5e4411; carried gather.py in Files, glued vote both paths, M4 near-miss + lookahead mutant, M9
- 2026-10-19T16:55:24-0400 RELAY-NOW received from llama-45: finish T11 through review/fix, start nothing new (no Checkpoint B arms/pre-screen), write HANDOFF, then RELAY-READY
- 2026-10-19T16:57:39-0400 Task 11: impl DONE 127dd45 (3432 passed; lookahead mutant caught). early return → fall-through; note only for tag_source==tags. Dispatched t11-rev (opus)
- 2026-10-19T17:01:17-0400 Task 11: review t11-rev (opus): spec ✅, Approved, 0/0, 5 minor. Fall-through proven identical when glued vote fails (200k-case differential, 0 mismatches); double strip impossible; both-paths pinned (mutant A caught; B2 equivalent).
- Task 11: minor (deferred → CHECKPOINT B note): glued strip also changes sibling-format (format-recovered) titles with no note (brief: tags-only); survey population 0 — confirm harness shipped-field list covers that path
- Task 11: minor (deferred): misleading comments titles.py:219-221 + test name (votes disjoint); gather.py:26 145-char import line; private _GLUED_NUM_PREFIX import; 52Nd Street / 10Th Avenue same class as ruled 100 Years gap (optional accepted-gap test)
- Task 11: complete (commits e5e4411..127dd45, review clean)
- SLICE 2 COMPLETE (Tasks 8-11) at 127dd45

## HANDOFF — 2026-10-19T17:01:17-0400 (peer d4918098-e484-43e4-8857-2fae7853ad18, RELAY-NOW from llama-45)

State: branch held-backlog-tier1 @ 127dd45, tree clean. Tasks 1-11 COMPLETE (slice 0 + slice 2), each with an Opus task review and, where needed, fix rounds re-reviewed clean. Suite at 127dd45 per T11 implementer: `./.venv/bin/python -m pytest -q` 3432 passed, 1 skipped, 8 deselected (successor: re-run it yourself). Local tag tier1-base = 0038589.
NEXT: Checkpoint B (plan line 1728) — NOT started (no arms, no pre-screen). Then Tasks 12-13 (slice 1) → Checkpoint C, etc.

Checkpoint A decisions (operator, via llama-45):
- tier1-base = 0038589 ACCEPTED as baseline; drift (5 non-held, 0 held) and needs-LLM 492 match expectations.
- SCOPE AMENDMENT: the orchestrator may run `scripts/replay_holds.py run` READ-ONLY (nothing else; no commits/edits/writing commands) in /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1-base (detached at tier1-base, own .venv). Verify `./.venv/bin/python -c "import llama; print(llama.__file__)"` resolves inside that tree before each use.
- The -prev checkout (Checkpoint C onward): ASK llama-45 at that point; it will create it.
- Operator's llama run-resume loop was killed; still CONFIRM QUIET (no llama process; no recent writes under ~/.llama/shows and ~/.llama/runs) immediately before recording each checkpoint's arms, and report if not.
- Checkpoint A artifacts: ~/.llama-harness/{A-base-held.json,A-base-all.json,cmp-A-held/,cmp-A-all/}.
- Note: Checkpoint A arms were run from this worktree (HEAD was tier1-base then).

Checkpoint B pre-screen notes (pass to the Opus pre-screener):
1. 2b residue class includes "one word + date" tags (Jam 12-31-99, Ripple 1970-09-20, Drums 1977-05-08) — spec P5 mechanism, ruled; expect them on the 2b demotion list.
2. 2a-accepted titles can still ship a trailing -, @, ^, ~ (brief regexes verbatim; spec :502 vs :542 ambiguity) — hand-check them; operator decides the reading.
3. The "format sibling tagged" note count may be inflated (threshold is plain title_fraction; a lossless sibling tagged tmp/Track NN throughout counts as tagged).
Also: 2a junk/metadata vetoes judge the whole core, not per segue component (J > 05:27 contrived); 2c glued strip also changes sibling-format titles with NO note (population 0 per survey) — confirm the harness shipped-field listing covers it; tnd2006-12-13 set labels move under 2a (expected, structure-changed list).

Open items carried to later tasks (successor must put them in those dispatches):
- Task 12: B2 — add spec's "race track"→"racetrack" fold in _place_tokens; region-name fold table approved by operator.
- Task 13: B3 — _jb_event gains state kw, test_gather_venue_equivalent_passes_no_mismatch passes "DC"; preflight minors: 1a placement ambiguous; Checkpoint C calls 1d a note but it is a FLAG; blank vote + blank jb venue with incompatible cities (spec :413).
- Task 14: carried from T4 review — brief_flags re-runs guard; normalize_briefing must apply at BOTH guard calls and to the reused briefing (one shared helper); preflight: extract brief._guard_prose(b) so compare's briefings.txt section (4) cannot drift; missing test imports (pytest, normalize_song, read_model); pre-empt mutant (a) with row ("Drums > Nope", ["Drums"], False).
- Task 15: carried from T3 review — run_vet_research writes notes.json AFTER vetting.json (done-marker); reorder notes.json first before vet notes become non-empty; missing pytest import.
- Task 16: info["resolved"] is a COUNT not a list; if Checkpoint E moves RIGHT_SHOW_MIN_TAPE_FRACTION, test_constants_are_the_spec_values changes in the same commit.
- Task 17: B4 — rename the new test helper (not _tracks; existing _tracks(n,dur) has 36 callers).
- Task 18: B5 — unmatched encore title "JBG" → "Casey Jones"; M1 — 5c.3 leading-parenthetical fold is a FALLBACK tier only when unfolded tiers find nothing; keep test_closer_matching_preserves_a_leading_parenthetical unchanged; 5c.2 note to notes.json (GatherResult.notes) NOT structure.conflicts (Global Constraint line 29 wins).
- Task 19: B6 — touch entry.ws.lock before snapshot tests (file_lock leaves .lock); plan step 5 "legs.vet None only on still-held" is STALE (no vetting.json ⇒ needs-LLM; legs.vet never None past classify); replayed_show.review_flags lacks package flags — final show must add carried_flags; import generate_briefing; reapply.py must import compute_legs and build_package by name (tests patch them there).
- Task 20: M3 — resolve each list row's slug to ShowWorkspace directly + derive_state, NOT catalog.iter_shows; M5 — patch herder.tasks._sleep in the transport-failure test; code_identity -dirty/version behaviour now tested (T5).
- Task 21: refuse --clear-set-breaks/--clear-encore/--clear-title alongside --untitled; spec end-state acceptance only met with _redo_show stubbed (note it).
- Final review: Review mode FABLE — final whole-branch reviewer on Fable (operator-approved upgrade); per-task reviewers stay Opus. Point it at every "minor (deferred)" line in this ledger.

Process notes for the successor:
- Shared files: $D/orch/common.md (child run rules), $D/orch/reviewer-template.md, $D/orch/rereview-template.md, $D/orch/setflight.py (STATE.md in-flight writer). Briefs/review packages: .superpowers/sdd/2026-10-19-held-backlog-tier1/.
- Fix rounds resumed the implementer via SendMessage with a new sentinel name (done-r1); the tick only watches `done`, so it shows TASK-DONE during a fix round.
- Every Ruling: line in this ledger goes into the final "Rulings I made" list.
- Meter at handoff: 5h 3% (resets 21:20), 7d 88% (brake 92%).
- 2026-10-19T17:01:24-0400 RELAY-READY: no children/shells/monitors running; tick 9067ca5e deleted; armed-d4918098 removed (armed-global kept: other armed-* flags present)
