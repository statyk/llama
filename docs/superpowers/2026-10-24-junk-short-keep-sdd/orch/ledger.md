# SDD ledger — plan: docs/superpowers/plans/2026-10-24-junk-short-keep.md
Peer orchestrator c03ad18d-bb48-4421-b153-6a96191ad85b; worktree .claude/worktrees/junk-filter; branch held-backlog-junk-filter; start c7dac0c
Spec: docs/superpowers/specs/2026-10-23-junk-short-keep-design.md (FINAL bd5ba03)
Gates: Task 9 -> STOP Checkpoint A; Tasks 10-14 -> STOP Checkpoint B (Task 15); Tasks 16-21 -> STOP Checkpoint C (Task 22); Task 23 after go.

## Escapes
(none)

## Log
2026-10-24T02:10:59-0400 orch started; meter 5h 7% / week 88%; Task 0 started (venv + baseline)
2026-10-24T02:11:16-0400 tick armed: cron de976b96 (13,43), flags armed-c03ad18d + armed-global

## Pre-flight scan (2026-10-24 ~02:20)
| pair / task | produces -> consumes | finding |
|---|---|---|
| T1->T2 | ordering["short_kept"], short_tag_is_junk | consistent |
| T1->T3 | T1 renumbers fixture positional overrides ("re-keyed by filename in Task 3"); T3 converts them to filename values | consistent |
| T1->T4->T17 | filter_files(short_keep=) -> final_kept(short_keep=) -> check_show passes False | consistent with T1 Step 6 ("only Task 17's check will") |
| T2<->T3<->T4 | all edit stages/gather.py title_inputs/title_cascade (note after slice5; inp.positions; final_kept extraction) | serial, compatible: positions computed from final kept list |
| T3->T4/T5 | _legacy_message, xfail(strict) marks in test_triage/test_show_cmd removed by T5 | consistent |
| T3->T6->T7 | rekey_raw/classify; ShowReplay filenames/short_kept/segues/breaks/flags (titles/title_sources/sets exist already, replay.py:394ff) | consistent |
| T7<->T8<->T14<->T16 | all extend scripts/short_keep_probe.py | serial |
| T6<->T16 | both edit scripts/replay_holds.py | serial |
| T2->T11 | Track.short_kept | consistent |
| T12->T13->T14 | ReusePlan/plan_reuse/set_aside/put_back | consistent |
| T17-T20 | one script, contract block lines 506-551 | serial |
| T21 | every predicted test name exists in its owning task (checked a,b,c1,c2,d..s) | consistent |
| T1 self | corpus totals: drop-edge 37 = 35 edge + 2 filename; 3+2 = 5 filename | consistent |
| T9 self | Step 1 adds a git worktree outside this worktree (~/.llama-harness/piece4/base-e37f670) | Ruling below |
| GC "one commit per task" vs mandate 4 "commit incrementally" | | Ruling below |

Ruling: Task 9 Step 1's `git worktree add --detach ~/.llama-harness/piece4/base-e37f670 e37f670` is a NEW detached checkout the plan mandates, not "another checkout" in the brief's sense; I create it and touch no other existing checkout — cost if wrong: one extra worktree entry in the shared .git, removable by `git worktree remove`.
Ruling: "One commit per task" reads as "each task's commits are its own"; mandate 4 (incremental green commits) governs — cost if wrong: a few more commits per task than the plan pictured.
Ruling: SDD workspace = $D/orch (briefs/, pkg/); the skill's default `.superpowers/sdd/2026-10-24-junk-short-keep` is unused; implementer report file = $D/<task>/handback.md (mandate 1) — cost if wrong: none (paths only).
2026-10-24T02:12:57-0400 Task 0: complete. venv python3.14; llama.__file__ = worktree/packages/llama/src/llama/__init__.py; BASELINE: '4788 passed, 1 skipped, 8 deselected, 26 warnings in 88.52s' (./.venv/bin/python -m pytest -q -p no:cacheprovider); ~/.llama-harness/piece4 created
Task 1 BASE=c7dac0c
2026-10-24T02:14:05-0400 Task 1: implementer dispatched (t1-impl, Opus, agentId a7c560e2d5ef200ca, budget 120m); meter 5h 7% / wk 88%
2026-10-24T02:32:49-0400 Task 1: implementer DONE_WITH_CONCERNS, commit fdd7f1d, 4844 passed/1 skipped/8 deselected (./.venv/bin/python -m pytest -q); 4 concerns (format choice sees rule-kept files; furthur mp3/FLAC asymmetry; windsor coverage 27/28 until Task 2; restored old-shape fixtures) -> to reviewer
2026-10-24T02:32:49-0400 Task 1: reviewer dispatched (t1-rev, Opus, agentId a91e0f2cc8a334345); meter 5h 11% / wk 89%
2026-10-24T02:38:06-0400 Task 1: review (t1-rev, Opus) -> Needs fixes: Important 1 (interior test over pre-dedupe listings admits untagged short EDGE files on duplicate-listed items; reproduced by reviewer). verdict /Users/shawn/projects/llama/.claude/worktrees/junk-filter/.superpowers/sdd/junk-short-keep/t1-rev/handback.md sha256 801b36352b468b9b
Ruling: Important 1 is fixed, not parked — spec 2.4 (ruling 4, binding) derives play order "the way filter_files derives it", i.e. over one copy per listing; spec 7 "Interior timing" accepts only the stage timing (excluded/readmitted neighbours), not duplicate listings re-sorting the play order; strict surface (c) — cost if wrong: Task 9's reference reproduction may differ on doubled items (the r1 harness patched the filter in-process), each such row to be explained there.
Task 1: minor (deferred): _furthur_without_short_tuning defined twice (test_stage_gather ~:2405, test_title_cascade:126)
Task 1: minor (deferred): test_floor_unchanged_by_kept_short_files near-tautological (brief-mandated pin; keep)
Task 1: minor (deferred): junk.py:210-213 interior=False sentinel + spam re-check per untagged file; a classifier helper would read better
Task 1: minor (deferred): junk.py:177 own_title or original_title — whitespace-only own title does not fall back (as measured); pin or comment
Task 1: minor (deferred): concern 1 format choice can now be won by a format holding only tagged short files (<5 durations, all <90 s); spec-mandated by 2.5 placement
Task 1: minor (deferred): concern 2 furthur mp3 tmp kept / FLAC "Tuning Up" junk; ships D's "Tuning Up" with the Task 2 junk note — check in Task 2 that the note fires
Task 1: minor (deferred): concern 3 windsor coverage 27/28 until Task 2; Task 2 dry run must restore 1.0 and check conflicts
2026-10-24T02:38:24-0400 Task 1: fix round 1 dispatched (resumed a7c560e2d5ef200ca, Opus, dir t1-fix1, FIX_BASE fdd7f1d); meter 5h 13% / wk 89%
2026-10-24T02:42:42-0400 Task 1: fix round 1 DONE (7b8a30e, 4848 passed); re-review dispatched (t1-rr1, Opus, a6780d0c064028301); meter 5h 15% / wk 89%
2026-10-24T02:44:32-0400 Task 1: fix round 1/5 (1 addressed, 0 open — interior over deduped pool; commits fdd7f1d..7b8a30e) re-review t1-rr1 Opus: all addressed
Task 1: minor (deferred): junk.py:246 pool dedupe may choose a different winning copy than the final dedupe (same key, untagged candidate first by name, no titles) — exotic; track-tag vs filename order mismatch only
Task 1: minor (deferred): test _doubled prefix param never non-default (prefix sorting before top level not exercised; traced by reading as fine)
Task 1: minor (deferred, out-of-scope obs): an untagged candidate without a track tag forces filename order for the interior test (spec 2.4 includes candidates in the set — spec-mandated)
Task 1: minor (deferred): _listing_key copies dedupe's inline key (drift risk; docstring records the coupling)
Task 1: complete (commits c7dac0c..7b8a30e, review clean after fix round 1)
2026-10-24T02:45:38-0400 Task 2: BASE=7b8a30e; implementer dispatched (t2-impl, Sonnet, a0ef54610647787d5, budget 90m); carries Task 1 minors on windsor coverage/conflicts + furthur junk note; meter 5h 15% / wk 89%
2026-10-24T02:51:30-0400 Task 2: implementer DONE, 679357f, 4856 passed/1 skipped/8 deselected; windsor coverage 1.0 restored, conflicts still lists 'Weather Report Suite Part 1' (no second filter, spec 3); furthur junk note fires ('Tuning Up', track 10)
2026-10-24T02:51:30-0400 Task 2: reviewer dispatched (t2-rev, Opus, a38d7a5eadcd9568c); meter 5h 16% / wk 89%
2026-10-24T02:54:31-0400 Task 2: review t2-rev (Opus) Approved, 0 Critical/Important. ⚠️ notes.json landing resolved by orchestrator: run_gather writes res.notes via write_artifact(show_ws.notes, ShowNotes(gather=res.notes,...)) gather.py:2084.
Task 2: minor (deferred): test_short_kept_survives_to_show_json — 'plain' and 'owned' legs identical (both taper-owned); non-owned align path only covered indirectly by windsor; name overstates (checks in-memory Show)
Task 2: minor (deferred): gather.py:2029-2032 junk note also judges unresolved tracks (title = filename, e.g. 'tuning.mp3' -> junk); optional title_source != 'unresolved'
Task 2: minor (deferred): test_short_kept_file_votes_like_any_kept_file imports _inputs_like_gather from test_title_cascade (test-module coupling)
Task 2: complete (commits 7b8a30e..679357f, review clean)
2026-10-24T02:55:04-0400 Task 3: BASE=679357f; implementer dispatched (t3-impl, Opus, a5a9de40bb0749fdb, budget 150m); meter 5h 17% / wk 90%
2026-10-24T03:21:09-0400 Task 3: implementer DONE_WITH_CONCERNS, 08a35fd 853239a, 4887 passed/1 skipped/8 deselected/4 xfailed (test_triage, strict, 're-keyed in Task 5')
Ruling: Task 3 decision 1 accepted — cli._legacy_message returns the MIXED refusal for a mixed file (brief says None unless legacy); spec 4.1 "writers refuse ... when the file holds any legacy value", a mixed file holds one, and the mixed text names the right repair route — cost if wrong: a writer on a mixed file prints the mixed message instead of nothing/legacy text; Tasks 4-5 inherit it.
2026-10-24T03:21:39-0400 Task 3: reviewer dispatched (t3-rev, Opus, a6c86bd58ac2ed1b2); meter 5h 23% / wk 90%
2026-10-24T03:27:17-0400 Task 3: review t3-rev (Opus) Approved, 0 Critical/Important; reviewer agrees with the Decision-1 ruling on the merits. verdict sha256 74216da9d07c5624
Task 3: ⚠️ carried to Task 4: fix --untitled/--suggest-titles prompt before _edit_overrides refuses legacy — Task 4's _refuse_legacy at entry closes it; no staleness until Task 4 (_stale) — both already in Task 4's brief
Task 3: ⚠️ carried to Task 5: two strict-xfailed test_triage tests fail on fixture shape ('9,17' vs a 1-track show.json → 'no track 9'); Task 5 needs a multi-track show.json there
Task 3: minor (deferred): override_keys.py:333-335 duplicate filename in the kept list maps to its first position silently (unreachable today; migration has 'repeated filename' refusal)
Task 3: minor (deferred): override_keys.py:278 rekey_raw collapses colliding title keys ("7","07") last-wins — Task 17's 'duplicate key' refusal must run before rekey_raw (carried to Task 17)
Task 3: minor (deferred): gather cascade 'overrides.titles: no track k' check unreachable from gather; test_cascade_out_of_range_override_raises_like_gather no longer exercises it
Task 3: minor (deferred): Positions frozen but holds dict/list (shallow)
Task 3: minor (deferred): two commits instead of one — accepted per the per-task-commits ruling
Task 3: complete (commits 679357f..853239a, review clean)
2026-10-24T03:28:24-0400 Task 4: BASE=853239a; implementer dispatched (t4-impl, Opus, ac73e94b374f4d8d6, budget 150m); carries Task 3 ⚠️ items + --clear-title filename + stale comments; meter 5h 25% / wk 91%
2026-10-24T03:47:42-0400 Task 4: implementer DONE_WITH_CONCERNS, 904eeb5, 4922 passed/1 skipped/8 deselected/4 xfailed; hand-offs to Task 5: triage [t] lacks _stale, [e] lacks keyed-exclusion refusal, legacy check (use _legacy_message, not the Exit-raising _refuse_legacy); triage tests need cli.IAClient stubbed (un-stubbed IAClient reaches archive.org)
Ruling: Task 4 decision 1 accepted — --suggest-titles calls final_kept twice (staleness + proposal) where the brief's test line says once; spec 4.2 requires both comparisons to use the one helper and _stale returns only the message — cost if wrong: one extra metadata filter pass per --suggest-titles.
2026-10-24T03:48:09-0400 Task 4: reviewer dispatched (t4-rev, Opus, ab3f85556dbf36985); meter 5h 29% / wk 91%
2026-10-24T03:51:21-0400 Task 4: review t4-rev (Opus) Approved, 0 Critical/Important; agrees with Decision-1 ruling. verdict sha256 075e90cd923829f9
Task 4: ⚠️ carried to Task 5: _refuse_legacy docstring says "and triage's" — Task 5 must make it true or reword
Task 4: minor (deferred): _stale lets IAError escape fix as a traceback (safe; not the usual 'error:' exit 1)
Task 4: minor (deferred): file_of (cli diff l.391) third copy of number->filename translation (names[n-1] vs _resolve_exclude_tokens' t.index)
Task 4: minor (deferred): _keyed_files extra={} mutable default (never mutated)
Task 4: minor (deferred): test_suggest_titles_kept_list_comes_from_final_kept first half lacks exit_code assert
Task 4: minor (deferred): exclusion over-refusal on --clear-X + --set-X + --exclude of the new file (conservative; unpinned)
Task 4: minor (deferred): --suggest-titles combination message wording predates filename keys
Task 4: complete (commits 853239a..904eeb5, review clean)
2026-10-24T03:52:25-0400 Task 5: BASE=904eeb5; implementer dispatched (t5-impl, Sonnet, a5f188ac17f70fa8f, budget 120m); meter 5h 31% / wk 91%
2026-10-24T03:58:20-0400 Task 5: implementer DONE, cbe7591 (in ~4 min); orchestrator re-ran suite: 4936 passed, 1 skipped, 8 deselected, 26 warnings (./.venv/bin/python -m pytest -q -p no:cacheprovider); xfails gone
2026-10-24T03:58:44-0400 Task 5: reviewer dispatched (t5-rev, Opus, a8f8f8a34748a1766); meter 5h 32% / wk 91%
2026-10-24T04:02:02-0400 Task 5: review t5-rev (Opus) Approved, 0 Critical/Important; ⚠️ warnings resolved: 26 = Task-0 baseline 26. verdict sha256 ae8b651aa282dc90
Task 5: minor (deferred): _edit_overrides docstring doesn't mention to_file's string passthrough (callers may pass a string only for a stored key)
Task 5: minor (deferred): cli.py:2069-2071 and/or precedence; parenthesise
Task 5: minor (deferred): dangling filename containing ',' or '=' can't be kept through an edited [m] answer (fails safe)
Task 5: minor (deferred): triage keyed-exclusion test covers titles only (not set_breaks/encore flag text)
Task 5: complete (commits 904eeb5..cbe7591, review clean)
2026-10-24T04:03:09-0400 Task 6: BASE=cbe7591; implementer dispatched (t6-impl, Sonnet, ab2c4adbc0c85a0e6, budget 120m); meter 5h 33% / wk 92%
2026-10-24T04:03:50-0400 Task 9 Step 1 (done early, independent): base tree ~/.llama-harness/piece4/base-e37f670 detached at e37f67024eb3df6ae7fad19357ef3c8a1f84b34c, own .venv, llama.__file__ inside it, status --porcelain empty
2026-10-24T04:08:27-0400 Task 6: implementer DONE, b04041c c34c99d c728356, 4949 passed/1 skipped/8 deselected
2026-10-24T04:08:51-0400 Task 6: reviewer dispatched (t6-rev, Opus, a5964a3a7136ada0c); meter 5h 34% / wk 92%
2026-10-24T04:13:25-0400 Task 6: review t6-rev (Opus) Approved, 0 Critical/Important. verdict sha256 bd97a053ca6ab4d6
Task 6: ⚠️ carried to Task 19: scripts/rekey_overrides.py --apply must call override_keys.rekey_raw (no copy) — already the plan's contract
Task 6: minor (deferred): a failed re-key under both strip flags replays clean (rekey_error set) and compare never surfaces rekey_error; suggest a 'rekey errors' summary line
Task 6: minor (deferred): taper_probe._fix_applied TypeError when a filename set_breaks list mixes found/unfound files (sorted int vs str)
Task 6: minor (deferred): test_record_carries_filenames_short_kept_and_flags asserts shape, not values (breaks/segues vs gathered show; no short_kept=True fixture)
Task 6: minor (deferred): title_hygiene_probe stripped_positions unread; _shadow rekey kwarg has no caller
Task 6: minor (deferred): summary.txt does not state which arm was re-keyed
Task 6: complete (commits cbe7591..c728356, review clean)
2026-10-24T04:14:33-0400 Task 7: BASE=c728356; implementer dispatched (t7-impl, Sonnet, af1cfee8519f9c520, budget 120m); meter 5h 36% / wk 92%
2026-10-24T04:15:31-0400 RELAY-NOW received from llama-db: finish Task 7 through review/fix, start nothing new, HANDOFF, disarm, RELAY-READY
2026-10-24T04:19:19-0400 Task 7: implementer DONE, 4de43d2, 4968 passed/1 skipped/8 deselected; validated arms on a synthetic cand built from arm_r1.jsonl: tallies 1537/2649/20/34, classes match spec, 0/0 override moves, fills 10 lost/12 gained; RED shown after the fact (impl written first)
2026-10-24T04:19:48-0400 Task 7: reviewer dispatched (t7-rev, Opus, a3cb0fe91730fb891); meter 5h 37% / wk 92%
2026-10-24T04:24:07-0400 Task 7: review t7-rev (Opus) -> Needs fixes: spec ❌ repro lacks library-root --out guard; Important 1 reproduction pinned on 2 of 6 fields (M1 survives); Important 2 class precedence untested (M2, M6 survive); Important 3 library-root guard untested in arms (M5) and missing in repro. verdict sha256 510389898b263ea1
Ruling: Important 3's fix includes resolving the library root the way replay_holds.run does (reading the default config.toml's root), which the reviewer listed as Minor — the guard exists to keep --out out of the real library, and a guard that ignores the configured root does not do that — cost if wrong: a few extra lines in the fix round.
Task 7: minor (deferred): 'shows LOSING a file' counter from m3 not ported
Task 7: minor (deferred): vet/carried flag order indistinguishable in tests (M4 survives; vet_flags empty)
Task 7: minor (deferred): repro test assertion "differences (" vacuous; repro exits 0 on two empty arms; repro refuses an --out that is an ancestor of an input (over-strict); override-show set rebuilt per added show; RED only by collection error
Task 7: ⚠️ carried to Task 9: confirm on the first real candidate run that arm_r1 flags were built like Legs.flags (a mismatch would list every show)
2026-10-24T04:24:30-0400 Task 7: fix round 1 dispatched (resumed af1cfee8519f9c520, Sonnet, dir t7-fix1, FIX_BASE 4de43d2)
2026-10-24T04:27:39-0400 Task 7: fix round 1 DONE (5d3e452, 4980 passed); each mutant M1/M1b/M1c/M1d/M2/M6/M5a/M5r turns exactly one new test red
2026-10-24T04:28:01-0400 Task 7: re-review dispatched (t7-rr1, Opus, a75a8b091e295b51c); meter 5h 40% / wk 92%
2026-10-24T04:29:37-0400 Task 7: fix round 1/5 (4 addressed, 0 open — repro guard, reproduction fields, class precedence, arms guard tests; commits 4de43d2..5d3e452) re-review t7-rr1 Opus: all addressed
Task 7: minor (deferred): ConfigError from load_config in _guard_out ends in a traceback, not exit 2 (same as replay_holds)
Task 7: minor (deferred): probe tests without --config now read the real ~/.llama/config.toml (read-only; would fail on a malformed file)
Task 7: minor (deferred): module docstring repro usage omits --config; refused-overlaps sentence incomplete
Task 7: minor (deferred): ref-dir --out guard not independently pinned (its test also trips missing-fields)
Task 7: complete (commits c728356..5d3e452, review clean after fix round 1)

## HANDOFF (2026-10-24T04:29:37-0400, peer c03ad18d-bb48-4421-b153-6a96191ad85b -> successor, on llama-db's RELAY-NOW)
State: Tasks 0-7 COMPLETE and reviewed (Opus) at HEAD 5d3e452 on branch held-backlog-junk-filter, tree clean. Suite at 5d3e452: 4980 passed, 1 skipped, 8 deselected (Task 7 fix report; orchestrator last re-ran at cbe7591: 4936 passed, 26 warnings = baseline). Nothing in flight; no background shells or monitors; tick disarmed.
Next: Task 8 (Sonnet implementer; packets/score/sibvocab in scripts/short_keep_probe.py), then Task 9 measurement -> STOP at Checkpoint A.
Workspace: briefs for Tasks 1-8 in $D/orch/briefs/ (task-N-brief.md, global-constraints.md, mandates.tmpl); review packages in $D/orch/pkg/. Task 8 brief already extracted: $D/orch/briefs/task-8-brief.md. Child dirs t1-impl..t7-rr1 under $D (single-use names; next free e.g. t8-impl).
Task 9 Step 1 DONE early: base tree ~/.llama-harness/piece4/base-e37f670, git worktree --detach at e37f67024eb3df6ae7fad19357ef3c8a1f84b34c, own .venv (pip -e herder, llama[dev], emcee, transmitter[dev]; python3 venv), llama.__file__ inside it, status --porcelain empty. Remove later with 'git worktree remove' from this repo. Steps 2+ not started; ~/.llama-harness/piece4/ holds only that tree.
Carried items:
- Task 8: same script as Task 7 — reuse _guard_out(out, config, ...) (reads config.toml root like replay_holds.run) for every new subcommand's --out; arms/repro tests use tmp config. Reference data ~/.llama-harness/piece45/ is read-only; r_packets.py is the packet-format source.
- Task 9: (a) Ruling from Task 1 — the interior test now derives play order over one copy per listing (dedupe key); the r1 reference harness patched the filter in-process pre-dedupe, so reference-reproduction differences on duplicate-listed items are expected and must each be explained. (b) Task 7 ⚠️ — confirm on the first real candidate run that arm_r1.jsonl 'flags' were built like replay.Legs.flags (a mismatch would list every show as differing in flags). (c) Task 6 minor — compare never surfaces rekey_error; check cand.json rows for rekey_error by hand. (d) Task 7's own validation (synthetic cand from arm_r1) reproduced tallies 1537/2649/20/34 and the 6(b) classes, so the instrument agrees with the reference on the reference.
- Task 17: the 'duplicate key' refusal ("7" and "07") must run before rekey_raw, which collapses colliding title keys last-wins (Task 3 minor). Task 19: --apply must call override_keys.rekey_raw (no copy) (Task 6 ⚠️). Task 17 consumes gather.final_kept(..., short_keep=False) (Task 4).
- Task 11+: _legacy_message returns the MIXED refusal for a mixed file (ruling, Task 3); writers/triage inherit it.
Rulings made (all also above, in order): preflight x3 (base worktree outside, multi-commit tasks, workspace=$D/orch); Task 1 interior over deduped pool; Task 3 mixed message; Task 4 final_kept twice on --suggest-titles; Task 7 guard reads config.toml root.
Deferred minors: every 'minor (deferred)' line above (Tasks 1-7) — for the final whole-branch review.
Escapes: none.
2026-10-24T04:29:45-0400 disarmed: CronDelete de976b96; rm armed-c03ad18d; armed-global kept (other armed-* present); STATE.md mode idle, in-flight []
