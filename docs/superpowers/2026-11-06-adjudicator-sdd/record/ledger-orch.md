# SDD ledger — plan: docs/superpowers/plans/2026-11-06-adjudicator.md
Orchestrator: peer session 894b18a7-5d04-4ac5-90cf-2b7082e70cc2 (Opus). Started 2026-11-07T06:11:45-0500. Base c251f440. Baseline (parent-measured): 6905 passed, 1 skipped, 8 deselected.
Work dir (briefs, review packages): /Users/shawn/projects/llama/.claude/worktrees/adjudicator-impl/.superpowers/sdd/2026-11-06-adjudicator

## Pre-flight scan
| Pair / task | Produces vs consumes | Found |
|---|---|---|
| T1->T2 | Overrides.recording | consistent |
| T1->T7 | staleness.stale_message | consistent |
| T1->T9 | AdjudicateConfig.enabled -> hook_enabled | consistent |
| T2->T5 | lineage_table, filename_keyed_entries | consistent |
| T2->T7 | override_keys.refusal (exists, override_keys.py:130), clear_hint | consistent |
| T3->T4 | Bundle.text | consistent |
| T3->T5 | Bundle.sections/own_row/length_of, escape_braces, Row | consistent |
| T4->T5 | Verdict, edit classes, PROPOSE_ONLY_OPS | consistent |
| T5->T6 | flag_passes, STRUCTURE_KINDS, has_track_list_*, GateResult, COVERAGE_ADDED_MAX_S | consistent |
| T6->T7 | apply_verdict(on_commit, trial), ApplyResult statuses | consistent |
| T7->T8 | Context(redo: (entry, stage)), outcome constants, ShowOutcome | consistent with _adjudicate_context lambda |
| T8->T9/T10/T11 | _adjudicate_context, render_proposal | consistent |
| T1 self | tests vs implement step | consistent |
| T2 self | clear_hint gains --clear-include in same task | consistent |
| T3 self | headers listed = tests | consistent |
| T4 self | prompt phrases test vs prompt contents list | consistent |
| T5 self | test name "two_61s" uses data (30,30,61) | name cosmetic; data correct (sum 121 > 120) |
| T5 vs spec | long bar: spec allows "track's position"; plan stem only | Shawn sign-off 2 = YES (stricter) |
| T6 self | algorithm vs tests | consistent |
| T7 self | outcome table vs tests | consistent |
| T9 vs spec | run approve hook beyond spec list | Shawn sign-off 1 = YES |
| T11 | "campaign_gate's process check" — no symbol named campaign_gate in llama; lives in scripts/bulk_apply.py | implementer locates |
| Global | worktree path .claude/worktrees/adjudicator | superseded by adjudicator-impl |
Ruling: plan's worktree path is superseded by .claude/worktrees/adjudicator-impl — brief from parent names it — costs nothing if wrong.
Ruling: T11 "campaign_gate's process check" resolves to scripts/bulk_apply.py's campaign_gate machinery; implementer reuses it rather than reinventing — if wrong, a duplicate process check (minor).

## Tasks

## Escapes

Task 1: dispatched implementer t1-impl (Sonnet) base c251f440 at 2026-11-07T06:11:52
Task 1: implementer DONE 27ef8ef9 (suite 6911 passed, 1 skipped, 8 deselected); dispatched t1-review (Opus)
Task 1: review Approved (Opus t1-review), 0 Critical/Important.
Task 1: minor (deferred): test_config.py four blank lines before test_adjudicate_section_defaults_on_and_is_strict
Task 1: minor (deferred): template test is a substring check after [adjudicate] (tomllib assert would be tighter)
Task 1: minor (deferred -> carried to Task 2/6): Overrides docstring lists only gather/brief as readers, "never auto-written by a stage"; update when select reads recording (T2) and adjudicator writes (T6)
Task 1: minor (deferred): ShowNotes docstring test is a doc check (plan-mandated)
Task 1: complete (commits c251f440..27ef8ef9, review clean)
Task 2: dispatched t2-impl (Sonnet) base 27ef8ef9
Parent instruction (06:2x): from Task 2 on, spec-compliance and code-quality review are two separate Opus reviewers, spec first then quality. Task 1 combined review stands.
Task 2: implementer DONE 1e0ef956 (6925 passed); concern: RED verified after implementing (TDD order); dispatched t2-spec (Opus)
Task 2: spec review ✅ (t2-spec Opus), 2 Minor.
Task 2: ⚠️ resolved by controller: redo --from select calls drop_stage_artifacts(entry.ws, "select") (cli.py _redo_show_locked) so selection.json is dropped and should_run re-runs select; pin takes effect.
Task 2: Ruling: `--clear-recording cannot be combined with <flag>` (vs brief's `--recording ...` for both) stands — names the flag the operator typed, mirrors --untitled — costs a one-string change if wrong.
Task 2: minor (deferred): lineage_table uses `or`, an empty era scores dict falls back to the global table.
Task 2: dispatched t2-quality (Opus)
Task 2: quality review Needs fixes (t2-quality Opus): 1 Important (duplicate _packaged_with_two_recordings/_SLUG in test_fix.py), 6 Minor.
Task 2: Ruling: minor "--include F --clear-include F is a silent no-op" goes into fix round 1 alongside the Important — user-facing silent no-op, one clash check like the existing exclude/include one — cost if wrong: one extra small change.
Task 2: minor (deferred): pin accepted for a scored recording with kept_tracks == 0 (fails later in gather)
Task 2: minor (deferred): no test for --clear-include with another file flag, or N whose file not in include
Task 2: minor (deferred): cli.py nested conditional stage expression >100 cols
Task 2: minor (deferred): import ordering select_recording.py:9, test_override_keys.py:667
Task 2: minor (deferred): `if recording` truthiness vs `is not None` guard inconsistency
Task 2: fix round 1 sent to t2-impl (Sonnet, resumed), FIX_BASE 1e0ef956
Task 2: fix round 1 commit 43cade93 (6926 passed); dispatched t2-rereview (Opus)
Task 2: fix round 1/5 (2 addressed, 0 open; commits 1e0ef956..43cade93)
Task 2: minor (deferred): no test pins "overrides.include printed once" (cli.py:3910 gate)
Task 2: complete (commits 27ef8ef9..43cade93, review clean)
Task 3: dispatched t3-impl (Sonnet) base 43cade93
Task 3: implementer DONE_WITH_CONCERNS 7bf661c2 (6940 passed); RED first this time; concerns are builder decisions (SETLISTFM_CAP 5000, reviews from ia.metadata, cap may be exceeded if non-cuttable sections overflow); dispatched t3-spec (Opus)
Task 3: spec review ✅ (t3-spec Opus), 6 Minor, 5 ⚠️.
Task 3: Ruling: setlist.fm cache key and jerrybase.lookup in the bundle use the item date (`show.item_date or show.date`), as gather does (gather.py:952 setlistfm.setlist(artist, candidate.date); :1782 jerrybase.lookup(artist, candidate.date)) — the bundle must show what gather saw — cost if wrong: a date-overridden show's bundle shows the item date's setlist (weak, propose-only evidence anyway).
Task 3: Ruling: minor "file rows render raw IA length '11:04' instead of seconds" enters fix round (brief column is "length s", Step 3 says lengths go through util.length_seconds) — model compares durations for sibling matching — cost: none.
Task 3: Ruling: minor "track table renders unknown duration as 0" enters fix round (render unknown as "?", same in excluded rows) — model told 0 s for a track the gate treats as long; strict surface — cost: none.
Task 3: Ruling: ⚠️ bundle may exceed BUNDLE_CAP once siblings and research are exhausted — accepted; only protected sections remain, all others are capped; the prompt still renders; Task 4 has no hard limit — cost if wrong: an oversize call fails as TaskFailed for that show only (FAILED, logged).
Task 3: ⚠️ own_row one-hop original: accepted as briefed; Task 5 treats None as "no own row".
Task 3: ⚠️ Row.title unescaped vs Row.text escaped: noted for Task 5 (gate normalises quote via escape_braces; titles compared via normalize(edit.title) against quote — carry to Task 5).
Task 3: minor (deferred): setlistfm section dumps every cached setlist for artist+date, not gather's _pick (multi-event dates include other performances; setlistfm is weak/propose-only evidence)
Task 3: minor (deferred): SETLISTFM_CAP=5000 added (builder's call)
Task 3: minor (deferred): NUL stripped (consequence of brief's test input)
Task 3: minor (deferred): length_of not tested with one-side-unknown cases
Task 3: dispatched t3-quality (Opus)
Task 3: quality review Needs fixes (t3-quality Opus): 2 Important (list-valued IA description/notes rendered as repr breaks substring gate; no test pins row-text-in-bundle-text invariant), 10 Minor.
Task 3: Ruling: minors into fix round 1 as well: Row.title/FileMeta.title store the cleaned (escaped, NUL-stripped) title; narrow sibling `except Exception` to IAError/httpx.HTTPError/ValueError + one test — Task 5 compares titles; swallowed errors — cost: none.
Task 3: minor (deferred): _render re-reads vetting/notes/briefing per cap-loop pass
Task 3: minor (deferred): _read_text catches only FileNotFoundError (non-UTF-8 research fails the bundle -> FAILED for that show)
Task 3: minor (deferred): len<=BUNDLE_CAP assert in brief test is vacuous (real coverage in oversize test)
Task 3: minor (deferred): sibling ia.metadata may write md_<id> cache files under <root>/cache and hit network (outside show dir; pilot reads real IA)
Task 3: fix round 1 sent to t3-impl (Sonnet, resumed), FIX_BASE 7bf661c2; F1-F7
Task 3: fix commit 4fb2edc5 (6945 passed); dispatched t3-rereview (Opus)
Task 3: fix round 1/5 (7 addressed, 0 open; commits 7bf661c2..4fb2edc5)
Task 3: minor (deferred): _secs f"{s:g}" exponent at >=1e6 s (unreachable)
Task 3: minor (deferred): long inline-conditional f-strings bundle.py:239,242
Task 3: complete (commits 43cade93..4fb2edc5, review clean)
Task 4: dispatched t4-impl (Opus) base 4fb2edc5
Task 4: implementer DONE_WITH_CONCERNS 12cc2718 (6960 passed); dropped v2 'partial tapes: hold' (contradicts spec class ruling) — Ruling: correct, spec governs — cost: none; dispatched t4-spec (Opus)
Task 4: spec review ❌ (t4-spec Opus): 3 Important (I1 prompt lists sibling-tracks as taper-side for structure, gate does not; I2 switch bullet allows overrule/city beside switch, gate allows only venue; I3 prompt omits spurious<->overrule-edit coupling and no-edits veto, so partial-tape verdicts get vetoed), 5 Minor.
Task 4: Ruling: prompt follows the Task 5 gate where gate is stricter than spec wording (I2 switch: venue-only) — the gate is what runs; plan ambiguity #7 already ruled this — cost if wrong: switches with overrules held instead of applied.
Task 4: Ruling: minors M1-M4 (unknown length sends whole verdict long; no-tracks in never list; title-kind overrule evidence = high + taper-description/original-tag/sibling-tracks with no per-file anchors; better-sibling: always give switch when better, the gate decides auto vs propose) enter the fix round — prompt wording only — cost: none. M5 (encore not in breaks_after) stays (consistent with fix).
Task 4: ⚠️ open design question for Checkpoint A (not Task 4): partial-tape shows' typical flags may be kinds whose OVERRULE_BAR is never (titles, tape-spans, duration mismatch) or structure-bar (research-sets, jerrybase-set-count, needing taper-side quote); the "partial tape airs" class ruling may have little gate path. No design change now; the pilot measures it; raise to parent at Checkpoint A.
Task 4: dispatched t4-quality (Opus); fix round deferred until quality findings are in (one combined round)
Task 4: quality review Needs fixes (t4-quality Opus): 2 Important (empty/whitespace payload strings validate — empty title passes a substring check; partial-tape path ambiguous in prompt), 8 Minor.
Task 4: Ruling: partial-tape clearance = each holding flag gets an `overrule` edit at its own bar (structure-kind flags such as research-sets/jerrybase-set-count need a taper-side quote showing the tape is partial); `partial_tape: true` is a record note, not a clearance; flags whose bar is never (titles, tape-spans, duration mismatch) cannot be cleared and the show holds — per spec + Task 5 tables — cost if wrong: partial tapes held more often (pilot measures; raise at Checkpoint A).
Task 4: Ruling: quality minors m1 (case/whitespace-normalise literals), m2 (strip leading "- " on flag fields), m3 (null -> default for partial_tape/root_causes/lists), m5 (encore_after in breaks_after rejected by schema), m6 (propose-only example in the prompt JSON), m7 ("prefer untitled" wording), m8 (nested extra=ignore test) enter fix round 1 — cheap, and m1/m3 each save a retry Opus call — cost: none.
Task 4: minor (deferred): ProposeOnly with an invalid evidence kind fails the whole verdict (could drop instead)
Task 4: minor (deferred): structure op line "encore not in breaks_after" extra vs brief (now enforced by schema per m5)
Task 4: fix round 1 sent to t4-impl (Opus, resumed), FIX_BASE 12cc2718; findings file task-4-fix1-findings.md
Task 4: fix commit 80a0cd84 (6975 passed); dispatched t4-rereview (Opus)
Task 4: fix round 1/5 (all 19 finding IDs addressed, 0 open; commits 12cc2718..80a0cd84)
Task 4: Ruling: re-review minors m1 (partial-tape "it airs unless a never-bar flag holds"), m2 (cross-ref to Reply for kind rule), m3 (shipping as-is needs at least one overrule edit), m4 (better_sibling typed Text|None, "" -> None) carried into the Task 5 dispatch as small extra edits — m3/m4 interact with Task 5's no-edits and better_sibling vetoes — cost: Task 5 diff touches verdict.py/adjudicate.md lightly.
Task 4: minor (deferred): adjudicate.md:113 over-long line
Task 4: complete (commits 4fb2edc5..80a0cd84, review clean)
Task 5: dispatched t5-impl (Opus) base 80a0cd84, budget 90
Task 5: implementer DONE_WITH_CONCERNS 5d05e7e9+981b898a (7152 passed; gate 173); mutation 82/82 CAUGHT (first run's 21 'MISSED' were a driver id-parsing bug, re-run); dispatched t5-spec (Opus)
Task 5: spec review ✅ (t5-spec Opus), 3 Minor, 2 ⚠️.
Task 5: ⚠️ carried to Task 7: evaluate() fails open on targets validate_targets rejects — runner must validate first and stop on reasons (plan step 6 before 7 already; Task 7 dispatch + review to pin it).
Task 5: ⚠️ carried to Task 7: Facts.complaints must be built from assessment.recording_complaints keyed on reviewed_identifier, else the complaints part of the switch bar is inert.
Task 5: minor (deferred): structure edit from setlistfm/jerrybase at medium/low gets bar label `structure` not `propose-only` (outcome same; accept is op-based)
Task 5: minor (deferred): inline kind/bar literals in _title_anchor etc. (thresholds/sets are constants)
Task 5: minor -> quality reviewer: no mutant row for switch "at least one checked quote" part
Task 5: dispatched t5-quality (Opus) incl. independent 8-mutant audit
Parent instruction: evaluate() fails closed (veto) on any target validate_targets rejects; test + mutation row; folded into Task 5 quality fix round; Task 7 carry stays (two layers). Spec does not forbid it (malformed => held with verdict stored; a veto keeps it held).
Task 5: quality review Needs fixes (t5-quality Opus): 1 Important (switch checked-quote part unpinned: mutant M8 skipping quote check for SwitchRecording leaves 173 green); mutant audit 7/7 table mutants CONFIRMED CAUGHT; 6 Minor.
Task 5: Ruling: minors into fix round 1 (strict surface): own-row exclusion when FileMeta.original is None (treat same-stem rows as own); numeric-only stem (e.g. 01.mp3) never satisfies stem_in (operator ruling: a bare track number never counts); stem_in lookarounds Unicode-aware (letter or digit) — fail-closed direction, cost if wrong: some long-bar edits held instead of applied.
Task 5: minor (deferred): quote_ok on "\n".join lets a quote stitch two rows (short/medium/structure/venue bars only; plan-mandated)
Task 5: minor (deferred): normalize lacks NFC (fails closed)
Task 5: fix round 1 sent to t5-impl (Opus, resumed), FIX_BASE 5d05e7e9; F1-F5 + 6 mutation rows
Task 5: fix commit 44d321b6 (7163 passed); 6 new mutants CAUGHT
Task 5: dispatched t5-rereview (Opus) incl. 2 new-pattern lookaround mutants
Task 5: fix round 1/5 (F1-F5 addressed, 0 open; commits 5d05e7e9..44d321b6); reviewer re-ran 2 lookaround mutants on new pattern: CAUGHT. Mutation total: 82 + 6 (implementer) all CAUGHT; reviewer-confirmed 7 + 2; M8 was MISSED before the fix, now CAUGHT.
Task 5: minor (deferred): fail-closed test asserts only "malformed: edit 0" prefix, not per-kind reason
Task 5: minor (deferred): "bar passes, still vetoed" case covers include only
Task 5: minor (deferred): F3 same-stem compare is case-sensitive; a case-mismatched original row counts as "another" row (fail-open direction, pre-fix behaviour; rare on LMA)
Task 5: complete (commits 80a0cd84..44d321b6, review clean)
Task 6: dispatched t6-impl (Opus) base 44d321b6, budget 100
Task 6: implementer DONE_WITH_CONCERNS a6f0ac34 (7218 passed; 55 apply tests, RED per-test via NotImplementedError); mutation 36/36 CAUGHT (12 brief + 24 own). IAError subclasses LlamaError: transient checked before refused, pinned by a mutant. RateLimited lives in herder.limits.
Task 6: carry to Task 7: earliest_stage raises ValueError with no applicable edit — runner/accept must not call apply with propose-only edits alone (accept step 3 already gives NO_PROPOSAL); legacy track-number keys handled by runner step 3 refusal (STALE).
Task 6: dispatched t6-spec (Opus)
Task 6: spec review ❌ (t6-spec Opus): 1 CRITICAL fail-open — whole_show_diff never reports predicted files absent from kept (an include that does not land still `applied`; exclude-truncated/include-complete verdict could drop a track from air); the brief's "kept-set exactness dropped" mutant could not catch it because that half was never written. 3 Minor.
Task 6: Ruling: apply_verdict refuses (status refused, nothing written) a verdict that carries switch_recording plus any non-venue applicable edit — a switch runs coverage only, never the whole-show diff, and accept skips the gate that enforces switch-only — defense in depth for [a] — cost if wrong: none (gate already forbids it in auto).
Task 6: Ruling: minor "coverage post_titles counts unresolved/placeholder/filler post tracks" enters fix round (strict surface; apply _resolved_song on post side) — cost: some switches proposed instead of applied.
Task 6: minor (deferred): !r quoting in diff/changes lines renders "Truckin'" vs brief's '<old>' form (report text)
Task 6: dispatched t6-quality (Opus) incl. 7-mutant audit + adversarial missing-half hunt
Task 6: quality review Needs fixes (t6-quality Opus): same include-not-landed gap (Important), mutant audit M1-M6 CAUGHT matching the table; own M7 (rehold package failure swallowed) GAP; 5 Minor.
Task 6: Ruling: quality minors into fix round 1: rehold redo("package") failure test; set_title target order checked (order over all non-included kept files); trial asserts no .txn; "exclude did not land" message; promote gate._resolved_song public — strict surface / cheap — cost: none.
Task 6: minor (deferred): n_res tuple readability apply.py:316
Task 6: fix round 1 sent to t6-impl (Opus, resumed), FIX_BASE a6f0ac34; F1-F8 + 5 mutation rows
Task 6: fix commit 24e98902 (7225 passed); 6 mutation rows CAUGHT
Task 6: dispatched t6-rereview (Opus) incl. F1/F2 mutant re-run
Task 6: fix round 1/5 (F1-F8 addressed, 0 open; commits a6f0ac34..24e98902); reviewer re-ran F1/F2 mutants: CAUGHT. Mutation totals: 36 + 6 implementer CAUGHT; reviewers confirmed 6 + 2; M7 gap fixed (F4). Critical include-not-landed CLOSED.
Task 6: minor (deferred): no test for switch + city / switch + overrule refusal specifically
Task 6: complete (commits 44d321b6..24e98902, review clean)
Task 7: dispatched t7-impl (Opus) base 24e98902, budget 100; carries C1-C4 + 12-mutant table
Task 7: implementer DONE_WITH_CONCERNS e4fd470a (7295 passed; 70 new tests, RED per-test); 12/12 mutants CAUGHT; dispatched t7-spec (Opus)
Task 7: spec review ✅ (t7-spec Opus), 0 Critical/Important, 5 Minor; every step/outcome mapped; RateLimited leaves adjudication.json unchanged on every path.
Task 7: ⚠️ resolved by controller: take_snapshot rglobs the whole show dir (show_unit.py ~110) except package/audio handling, so adjudication.json is covered; Task 6 restore tests assert tree_bytes incl. it.
Task 7: ⚠️ bundle.view captured first: Task 3 test_bundle_view_is_captured_before_reading pins it.
Task 7: minors noted for the quality fix round if one happens: corrupt show.json raises out of adjudicate_show (steps 1-2, before any try); accept's _accept_verdict unguarded on an invalid stored verdict/held_proposal; C4 log line untested; RateLimited tests check model equality not bytes.
Task 7: dispatched t7-quality (Opus) incl. 4-mutant audit + ordering-gap hunt
Task 7: quality review Needs fixes (t7-quality Opus): 2 Important (accept applied[].index re-based onto filtered list; trial RateLimited unpinned — mutant q6 MISSED); audit q1-q4 CAUGHT by predicted; 6 Minor.
Task 7: Ruling: minors 1 (wrap steps 1-2 -> FAILED "read show"), 2 (accept guard -> NO_PROPOSAL "stored proposal unreadable"), 4 (_no_apply raises a BaseException subclass), 5 (CURRENT-before-stale pinned with a raising stale_message), 6 (trial ShowChanged test; re-held apply record test; accept delivered_changed test) into fix round 1 — cheap, loop-guard surface — cost: none.
Task 7: Ruling: minor 3 (shared override_keys refusal helper replacing runner._switch_refusal + cli.py copy) rides with Task 8, which edits cli.py — avoids a cross-task conflict — cost: duplicate text lives one more task.
Task 7: carry to Task 9: the hook wraps adjudicate_show in its own catch-all (RateLimited handled as pause) so nothing escapes into get/redo.
Task 7: fix round 1 sent to t7-impl (Opus, resumed), FIX_BASE e4fd470a
RELAY-NOW received (parent, context ~395k): finish Task 7 fix round + re-review, send Checkpoint A, start no new task, write HANDOFF, then RELAY-READY.
Task 7: fix commit e57be91c (7307 passed); 4 mutation rows CAUGHT
Task 7: fix round 1/5 (7 addressed, 0 open; commits e4fd470a..e57be91c); reviewer re-ran q6 + I1 mutants: CAUGHT.
Task 7: minor (deferred): _accept_pairs keys flags against bundle.show (post) while held_proposal keys verdict overrule evidence against pre — titles-kind key can disagree (narrow; applied[].index vs evidence_kinds mismatch)
Task 7: minor (deferred): M1 wrap is bare except Exception (no RateLimited re-raise; none can arise at steps 1-2)
Task 7: minor (deferred): test helper ApplyCalled reused as stale guard (naming)
Task 7: complete (commits 24e98902..e57be91c, review clean)

## Checkpoint A (2026-11-07, after Task 7)
Suite (controller-run): `./.venv/bin/pytest -q -p no:cacheprovider` at e57be91c -> 7307 passed, 1 skipped, 8 deselected, 26 warnings (adjudicator test files alone: 380 passed, 0 warnings). llama.__file__ inside worktree.
Mutation tables (full rows in handbacks): t5-impl/handback.md sha256 c771a5ab…a5e9; t6-impl/handback.md sha256 3af41ebc…ab6c; t7-impl/handback.md sha256 a0e18eea…caef.
No MISSED mutant open on any strict surface.

## HANDOFF (RELAY-NOW, peer 894b18a7 context ~400k)
State: Tasks 1-7 complete and reviewed (spec + quality, separate Opus reviewers from Task 2 on). HEAD e57be91c on adjudicator-impl, tree clean. Checkpoint A reported to parent. Shawn pre-authorized proceeding to Task 8 unless amiss; nothing amiss.
Next: Task 8 (Sonnet implementer per plan) — `llama adjudicate` command + report.py. Then 9 (Opus), 10 (Sonnet), 11 (Sonnet), final whole-branch Opus review (diff c251f440..HEAD vs spec), then PRE-PILOT stop; pilot steps gated per the parent brief.
Process in use: briefs via superpowers task-brief script into W=.superpowers/sdd/2026-11-06-adjudicator/; shared files there: global-constraints.md, implementer-common.md (run rules + mutation protocol + report contract), reviewer-common.md, spec-reviewer.md, quality-reviewer.md, rereview.md, state.py (STATE.md in-flight helper: `python3 $W/state.py $D/STATE.md <task> <agentId>`). Each child: sdd-dispatch.sh claim, mandates 1-5 verbatim in prompt, handback at $D/<task>/handback.md. Fix rounds: resume implementer via SendMessage with a findings file $W/task-N-fix1-findings.md; scoped re-review on Opus; quality reviewers also run an independent bounded mutant audit (has caught real MISSED gaps in T5, T6, T7).
Carry-overs (open, must be honoured):
 - CO1 (Task 8): replace runner._switch_refusal's verbatim copy of cli.py's `fix --recording` refusal text with a shared helper in override_keys (e.g. filename_keyed_refusal(slug, keyed)) used by both cli.py and runner; keep test_adjudicator_runner's pin and add a cli test for the same string.
 - CO2 (Task 9): the pipeline hook (_adjudicate_after) wraps adjudicate_show in its own catch-all; RateLimited/PauseUntil become a pause per plan; nothing may escape into get/redo or touch the caller's committed result.
 - CO3 (Tasks 8/9/10): never call apply with only propose-only edits (earliest_stage raises ValueError); runner already returns NO_PROPOSAL — CLI layers must not bypass the runner.
 - CO4 (Task 10 [a]): accept goes only through runner.accept_proposal (apply refuses switch + non-venue; coverage-only for switch).
 - CO5 (Checkpoint B / Shawn): partial-tape design question — a partial tape's holding flags are often never-bar kinds (titles, tape-spans, duration mismatch) or structure-bar kinds needing a taper-side quote, so the "partial tape airs" class ruling may have little auto path under the spec's tables. Prompt now says partial_tape is a note, not a clearance. No design change made; pilot measures it.
 - CO6 (final review): deferred minors throughout this ledger ("minor (deferred)") for triage; parent rulings recorded above.
Tick: disarmed at relay (CronDelete fe48e36d, armed flag removed). Successor must arm its own.
