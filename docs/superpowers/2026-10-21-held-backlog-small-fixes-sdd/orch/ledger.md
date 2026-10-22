# SDD ledger — plan: docs/superpowers/plans/2026-10-21-held-backlog-small-fixes.md
Peer orchestrator session 9847639b-42e2-4b9c-a407-cb7d6c8a5ada; worktree /Users/shawn/projects/llama/.claude/worktrees/held-backlog-small-fixes; branch held-backlog-small-fixes-impl; start bfaa837 (2026-10-21T18:41:39-0400)
SDD workspace (briefs, review packages): .superpowers/sdd/2026-10-21-held-backlog-small-fixes ; child dirs: $D/<task>/ (handback.md + done)

## Preflight conflict scan
| rows | produces vs consumes | found |
|---|---|---|
| T1 / T2 | both edit CLAUDE.md, different paragraphs; T2 does not use fold_curly_apostrophes | clean |
| T1 / T9 | fuzzy_norm_title fold reaches harness via gather | clean (expected) |
| T2 / T3 | T3 reports venue/city diffs that T2 creates | clean |
| T2 / T8 | B1-B12 mutants name T2's tests; names match T2 Step 1 | clean |
| T4 / T5,T6,T7 | show_unit, ShowView, capture_view, ShowChanged, tree_bytes names identical across tasks | clean |
| T5 / T6 | T5 keeps _redo_show stubs green; T6 retargets stubs to _redo_show_locked (reached via _redo_show) | clean |
| T6 / T7 | _untitled_resolution(config, ia, ledger, entry, show, view); T6 passes capture_view, T7 the session view; test_triage _stub_redo retargeted in T6 | clean |
| T4 / T8 | C1-C15 mutants name T4-T7 tests; C4 retired by the plan | clean |
| T5 self | except tuple -> (TaskFailed, HerderError, LlamaError) assumes IAError subclasses LlamaError — implementer verifies | note |
| T6 self | stub _propose_and_confirm_titles(ia, config, entry, show) must match the real signature — implementer verifies | note |
| T7 self | echo inside unit before redo vs "no stdout after last show write" constraint: echo precedes writes | clean |
| each T1-T8 | tests specified match files specified; (pin) tests marked | clean |

Ruling: models — every implementer Sonnet (the plan names no Opus task line; brief: Opus only on BLOCKED-for-reasoning); every reviewer Opus — brief's instruction — cost if wrong: an extra fix round on T6/T7.
Ruling: spec-compliance and code-quality reviewers run as two separate Opus dispatches, concurrently (both read-only on the same diff) — brief lists both; concurrency saves wall clock, 2 agents needs no fleet check — cost if wrong: a quality review of code that later changes in a spec fix round.

## Escapes
- T6 (t6-impl): red check done by temporarily reverting cli.py in the LIVE worktree (mandate 5 says scratch copy only); restored, tree clean at 3e3c8ef, suite green. Also wrote red.txt/red2.txt/green1.txt into $D/t6-impl (mandate 2: nothing else in that dir). No harm found; noted for the report.

## Log
Task 0: complete — .venv built; llama.__file__ = /Users/shawn/projects/llama/.claude/worktrees/held-backlog-small-fixes/packages/llama/src/llama/__init__.py; baseline `./.venv/bin/python -m pytest -q`: 3964 passed, 1 skipped, 8 deselected (18:41)
T1 BASE bfaa837; t1-impl dispatched Sonnet agent a9937aaba87026adb (18:42)
T1 impl DONE feedc82 (3974 passed); t1-spec Opus ab0ddec417b45e7e5, t1-qual Opus a71301b0163b42d07 dispatched (18:44)
T1 spec review: ✅ compliant, 0 Crit/Imp (18:45)
Task 1: minor (deferred): CLAUDE.md:778 new clause is one ~230-char line in an 80-wrapped paragraph
Task 1: minor (deferred): test_structure.py:2077 imports added mid-file with noqa E402 (matches local style)
T1 quality review: Approved, 0 Crit/Imp; minors: (1) right_show_gate research_known fold untested (mutant survives 171 tests) (2) mid-file import (3) CLAUDE.md wrap (4) known_song exact fold redundant-but-mandated, keep (18:46)
Ruling: T1 quality Minor 1 promoted to a fix round — the spec's slice D says tests cover both sides, and the gate's research side has none (a surviving mutant shows it) — cost if wrong: one cheap fix round. Minors 2-3 folded into the same round; Minor 4 kept as mandated.
T1 fix round 1 impl DONE 158619f (3975 passed); t1-rr1 Opus a2960086ee2ca102e dispatched (18:48)
T1 fix round 1/5 (3 addressed, 0 open; commits feedc82..158619f)
Task 1: complete (commits bfaa837..158619f, review clean)
T2 BASE 158619f; t2-impl Sonnet af61a41c212235792 dispatched (18:50)
T2 impl DONE fcbddf0 (3986 passed); t2-spec Opus ad448c13c2464a0bc, t2-qual Opus a77c844a2d95ef079 (18:52)
T2 spec review: ✅ compliant, 0 Crit/Imp; step-1 city check uses archive_city = sel_city or vote_city = the shipped city (18:53)
Task 2: minor (deferred): no pin for a tie in the final-else / 1c arms (code shows untouched)
Task 2: minor (deferred): gather.py:958 venue_tie_break's sel lacks the RecordingSummary | None annotation
T2 quality review: Approved, 0 Crit/Imp; preview mutation B1-B12 all caught by named tests (B1/B12 spelled against n==0/n!= form — carry to Task 8) (18:55)
Task 2: minor (deferred): gather.py:955 sel unannotated (dup of spec minor)
Task 2: minor (deferred): gather.py:1426-1432 step-1 predicate written twice (vote + tie); optional passes_step_1 helper
Task 2: minor (deferred): test_stage_gather.py:3037 mid-file imports
Task 2: minor (deferred): test_stage_gather.py:3080 lambda idiom (brief-verbatim)
Task 2: minor (deferred): incompatible-city tie test's venue assert is vacuous (strings strip equal); city half catches B2
Task 2: minor (deferred): step-1 non-corroborate test relies on vendored jerrybase CSV row
Task 2: minor (deferred): CLAUDE.md:623 new sentence one ~600-char line
Task 2: complete (commits 158619f..fcbddf0, review clean)
T3 BASE fcbddf0; t3-impl Sonnet a0928a30624e23a29 (18:55)
T3 impl DONE aa9d278 (3988 passed); concern: header counts every unreplayable show (per plan); t3-spec Opus aae43c012fdbf6632, t3-qual Opus a00bccbc96b3eb197 (18:58)
T3 spec review: ✅, 0 Crit/Imp; one-arm-diff risk checked: _pair never emits equal pairs, _shipped correct (18:58)
Task 3: minor (deferred): test 'ignores an identical diff' still lists the show (city change); the identical-only skip path is untested
Task 3: minor (deferred): base-diff/cand-null direction and unreplayable header count untested
Task 3: minor (deferred): venue/city flag changes not separated from other flag changes (brief-mandated layout)
T3 quality review: Approved, 0 Crit/Imp (18:59)
Task 3: minor (deferred): unreplayable shows counted not named; one-arm-unreplayable not distinguished; summary line omits skip count (plan-mandated)
Task 3: minor (deferred): unchanged no-diff field prints null -> null (may read as 'ships no venue')
Task 3: minor (deferred): untested: skip counter, cand-vs-base state, _all_flags vs _flags, added/removed swap
Task 3: minor (deferred): row omits outcome (needs-LLM rows' replayed venue may not ship)
Task 3: complete (commits fcbddf0..aa9d278, review clean)
T4 BASE aa9d278; t4-impl Sonnet a171d0cbbf54009be (18:59)
T4 impl DONE 1fe9109 (4000 passed); t4-spec Opus ad0dacaae3f501438, t4-qual Opus af11881570254a212 (19:01)
T4 spec review: ✅, 0 Crit/Imp; minors: leftover discard uses rmtree(ignore_errors=True) -> a part-deleted stale .txn file could be resurrected by a later failed restore (strict surface, low odds); take_snapshot-raises branch untested (19:03)
T4 quality review: Approved w/ 2 Important test gaps (mutants survive): (I1) .lock-tracked mutant — no test checks .lock inode; (I2) initial discard deleted — no test plants a leftover file absent from the show then fails a unit (19:05)
Ruling: T4 fix round 1 also takes quality Minors 1-4 (take_snapshot failure path untested; vacuous audio assertion; unlink missing_ok in restore; initial discard must verify .txn is gone, = spec-review minor) — strict surface, all cheap, two reviewers flagged the leftover-discard path — cost if wrong: a slightly larger fix diff.
Task 4: minor (deferred): symlinks dereferenced by snapshot/restore (library has none; docstring line)
Task 4: minor (deferred): a unit on an already-removed show leaves a .lock husk without any race (docstring says 'racing rm')
Task 4: minor (deferred): restore rewrites unchanged files (mode/mtime change; optional diff-only write-back)
T4 fix round 1 impl DONE c9d770c (4005 passed; commit's test line lacks the literal command — minor); t4-rr1 Opus a601e5a61a4b8c023 (19:08)
Task 4: minor (deferred): c9d770c commit message test line does not name the full-suite command
T4 fix round 1/5 (6 addressed, 0 open; commits 1fe9109..c9d770c)
Task 4: minor (deferred): refusal test patches shutil.rmtree process-wide (patch show_unit_mod.discard_snapshot instead)
Task 4: minor (deferred): show_unit docstring limitation 3 omits the new 'cannot remove leftover snapshot' refusal
Task 4: complete (commits aa9d278..c9d770c, review clean)
T5 BASE c9d770c; t5-impl Sonnet af6970e38fe953f5e (19:10)
T5 impl DONE 4284fa5 (4014 passed); t5-spec Opus ae708ed67aab59e73, t5-qual Opus ae4b523b68de15de8 (19:12)
T5 spec review: ✅, 0 Crit/Imp; lock discipline checked at every _redo_show site; Locked/RunMissing not LlamaError (19:15)
Task 5: minor (deferred): redo's removed-show check runs after leftover discard + snapshot (spec C1 orders 3 before 4-5); harmless, plan-mandated
Task 5: minor (deferred): test_a_leftover_txn_is_deleted_not_restored_by_the_next_redo cannot distinguish deleted from restored (T4's ghost test pins it; carry to T8)
Task 5: minor (deferred): CLAUDE.md:65 'see llama fix below' — fix entry is above
T5 quality review: Approved, 0 Crit/Imp; widened catch reaches only per-show LlamaErrors; tests hermetic (19:15)
Task 5: minor (deferred): batch FAILED line prints slug twice for ShowChanged (pre-existing format); IAError redundant in that tuple
Task 5: minor (deferred): batch restore test doesn't assert bready's write committed
Task 5: minor (deferred): single redo's pre-unit provenance check duplicates _redo_show_locked's message
Task 5: minor (deferred): test import polish (test_redo_cmd.py duplicate llama.workspace import; ordering)
Task 5: complete (commits c9d770c..4284fa5, review clean)
T6 BASE 4284fa5; t6-impl Sonnet a860f363bb613daaa (19:15)
T6 impl DONE 287c20f..3e3c8ef (4030 passed); deviation: _billy_shape slug yondermountainstringband-2005-12-31; t6-spec Opus a83dcd0ee39360d07, t6-qual Opus a121e368053938cc8 (19:21)
T6 spec review: ✅, 0 Crit/Imp; C14 mutant (view after prompt) caught by named test (scratch mutation); slug deviation is a correction (19:24)
Task 6: minor (deferred): CLAUDE.md 'One unit' text went into a new bullet labelled '`llama fix` is one unit' instead of the brief's 'One unit (2026-10-21):' on the existing fix entry (CLAUDE.md:61-62)
Task 6: minor (deferred): no-show.json tests don't cover --narration full refusal nor --unexclude/--set-breaks/--clear-title passing
Task 6: minor (deferred): test_no_run_stages_bad_overrides... passes on parent (redo restore is T5's); not marked (pin)
T6 quality review: Approved, 0 Crit/Imp; every write inside the unit; typer.Exit inside unit byte-identical (probe, not in suite) (19:24)
Ruling: T6 fix round 1 takes quality Minors 1+5 (three failure tests can pass via any early refusal; in-unit typer.Exit restore unpinned) and the spec's CLAUDE.md label minor — strict surface, tests a later mutation run leans on, cheap — cost if wrong: one small fix round.
Task 6: minor (deferred): lone --overrule on a non-held show now waits on the show lock and snapshots before saying 'not held' (behaviour note for final review)
Task 6: minor (deferred): edit lines now print after the redo's progress (plan-mandated)
Task 6: minor (deferred): fix is ~305 lines; unit body a natural _apply_fix_edits helper
T6 fix round 1 impl DONE f616ea5 (4032 passed); t6-rr1 Opus a792c4aec337a76e3 (19:26)
T6 fix round 1/5 (3 addressed, 0 open; commits 3e3c8ef..f616ea5)
Task 6: minor (deferred): CLAUDE.md:65-66 fix entry now ends with a full stop so the 'llama redo' item starts as a fragment
Task 6: complete (commits 4284fa5..f616ea5, review clean)
T7 BASE f616ea5; t7-impl Sonnet a19aa1e6520277795 (19:27)
T7 impl DONE acdb255 (4040 passed); t7-spec Opus ac7e728156c895931, t7-qual Opus a4bf2e1d7e0f94541 (19:30)
T7 spec review: ✅, 0 Crit/Imp; all 7 triage edit paths in one unit with the session view; C15 reasoned red (19:31)
Task 7: minor (deferred): triage tail passes a fresh _resolve_show(...) entry to _redo_show_locked instead of entry (harmless, under lock)
Task 7: minor (deferred): removed-show triage test asserts only 'error: '
Task 7: minor (deferred): no test fails [u]/[e]/[i]/[t] partway and asserts return to prompt
T7 quality review: Approved, 0 Crit/Imp (19:33)
Ruling: T7 fix round 1 takes quality Minor 2 (new [u] except has no test — the global constraint requires one; treated as a real gap), Minors 3-4 (tighten removed-show and metadata tests), Minor 6 (capture the view BEFORE the per-turn re-resolve, closing the offers/view window) — strict surface, cheap — cost if wrong: one small fix round.
Task 7: minor (deferred): per-turn re-resolve scans the whole library (~1 s/turn warm on 3983 shows; plan-mandated) — factor a one-directory entry builder (OWNER-VISIBLE UX cost for final review)
Task 7: minor (deferred): five '# noqa: E731' lambdas with no linter configured; mixed lambda/def under one name (functools.partial suggested)
Task 7: minor (deferred): 'metadata override updated' echoed inside the unit then rolled back on failure (brief-mandated echo placement)
Task 7: minor (deferred): removed-show message is 'no show matches <path>' not slice C's 'the show was removed' (brief's choice)
T7 fix round 1 impl DONE 36473d8 (4041 passed); t7-rr1 Opus a9e324c40070d7413 (19:35)
T7 fix round 1/5 (4 addressed, 0 open; commits acdb255..36473d8)
Task 7: minor (deferred): no test pins capture_view-before-re-resolve ordering (concurrent-only window)
Task 7: complete (commits f616ea5..36473d8, review clean)
T8 BASE 36473d8; t8-mut Sonnet a54c99ef17c9ee824 (19:37)
Ruling: T8 mutant list amended for code moved by fix rounds — B1/B12 spelled against the implementation's form; C5 split into C5a (yield) / C5b (take_snapshot); C10b (.lock snapshotted) and C16 (_discard_leftover check removed) added; C8 prediction may widen to T4's newer leftover tests, written before flipping — the spec asks that each removed restore/re-resolve step turn a named test red, and these are the steps as built — cost if wrong: a few extra mutants.
T8 run DONE: 30 mutants, 30 caught by prediction (C8b: 2 of 3 predicted tests red), 0 survived, nothing committed, suite 4041 (19:44)
Ruling: T8 has no diff, so one Opus verifier covers both spec and quality (audits the driver, re-runs a sample of mutants independently) instead of two reviewers — cost if wrong: a weaker review of a measurement, mitigated by independent re-runs.
t8-verify Opus a6e4643285abfed08 (19:44)
T8 verify: ✅ sound, Approved; 7 independent re-runs reproduced; 5 extra conditions X1-X5 all caught; minors: B12 catch only via an off-production call shape (unit-level pin, legit); malformed first BASE line in t8-mut.log (19:51)
Task 8: complete (no commits; 30/30 caught, 0 survived; review clean). Orchestrator re-ran ./.venv/bin/python -m pytest -q at 36473d8: 4041 passed, 1 skipped, 8 deselected; llama.__file__ in worktree; tree clean.
GATE A reached 19:51 — stopped; Task 9 waits for llama-db's go.

## HANDOFF (2026-10-21 19:52 EDT) — RELAY-NOW from llama-db at GATE A
**State.** Worktree /Users/shawn/projects/llama/.claude/worktrees/held-backlog-small-fixes, branch held-backlog-small-fixes-impl, HEAD 36473d8 (12 commits since bfaa837), tree clean. Tasks 0-8 COMPLETE and reviewed (spec + quality on Opus for T1-T7; one Opus verifier for T8). Last full suite, run by this orchestrator at 36473d8: `./.venv/bin/python -m pytest -q` = 4041 passed, 1 skipped, 8 deselected; `./.venv/bin/python -c "import llama; print(llama.__file__)"` resolves inside the worktree. Worktree .venv built in Task 0 (baseline 3964). Nothing in flight; tick disarmed at relay.
Commits: feedc82 + 158619f (T1 slice D) · fcbddf0 (T2 slice B) · aa9d278 (T3 harness venue_changes.txt) · 1fe9109 + c9d770c (T4 show_unit) · 4284fa5 (T5 redo unit) · 287c20f + 3e3c8ef + f616ea5 (T6 fix unit) · acdb255 + 36473d8 (T7 triage units). T8: no commits (0 survivors).

**Task 8 reports (pins).** Runner: $D/t8-mut/handback.md sha256 9299475a74702737f10f58460022bdad7d79342459477b8eef0b1499c62ae7d1. Verifier: $D/t8-verify/handback.md sha256 0d2d25c84bb491d89003ac773ef5b570eac0d9daf8d4cfc9da5614d43cf01bf7. Result: 30/30 caught by prediction (C8b 2 of 3 predicted; plan's test cannot catch it, T4's newer leftover tests do), 0 survived; verifier reproduced 7 independently and ran 5 extra conditions (X1-X5), all caught.

**Owner-visible notes for the final review.**
1. A lone `fix --overrule` on a show that is not held now takes the show lock (may wait behind a get) and snapshots before saying "not held" (T6 quality minor 2).
2. Triage re-resolves each show via catalog.resolve_show -> iter_shows on every turn: ~1 s/turn warm (3 s cold) on 3983 shows, plan-mandated; fix = a one-directory entry builder (T7 quality minor 1).
3. Removed-show message in triage is "no show matches <path>", not slice C's "the show was removed" (brief's choice).
4. Edit lines in `fix` now print after the redo's progress; triage's "metadata override updated" is echoed inside the unit and then rolled back on failure.
5. Escape (T6): implementer showed RED by temporarily reverting cli.py in the LIVE worktree (mandate 5); restored, no harm found.

**Every deferred minor** is a "Task N: minor (deferred):" line in this ledger (46 lines; grep them) — point the final reviewer at that list. Notable ones: T2 step-1 predicate duplicated (vote + tie), CLAUDE.md long lines (T1 fixed; T2:623 not), vacuous venue assert in the incompatible-city tie test; T3 untested report edges (unreplayable header count, base-diff/cand-null, _all_flags vs _flags, added/removed swap), null->null rendering, row omits outcome; T4 docstring limitation 3 omits the new leftover refusal, refusal test patches shutil.rmtree process-wide, symlinks dereferenced, restore rewrites unchanged files; T5 batch FAILED line prints slug twice, batch test doesn't assert the success side, duplicated provenance message, test import polish, CLAUDE.md fragment; T6 fix ~305 lines (_apply_fix_edits), no-show.json flag coverage breadth; T7 noqa E731 lambdas, ordering pin. Every ruling is a "Ruling:" line above (8 so far).

**Task 9 — NOT authorized yet** (owner must keep the live library quiet: no get/fix/triage/run resume --all while both arms run). When llama-db says go: brief .superpowers/sdd/2026-10-21-held-backlog-small-fixes/task-9-brief.md. Preconditions: tree clean, suite green. Base worktree at $(git merge-base HEAD main) -> /Users/shawn/projects/llama/.claude/worktrees/held-backlog-small-fixes-base with its own .venv (prove llama.__file__ under it); run `scripts/replay_holds.py run --all` for base and cand (each tree's own interpreter, background, read-only on ~/.llama) into ~/.llama-harness/small-fixes/{base,cand}.json; `compare` with the cand tree into ~/.llama-harness/small-fixes/cmp (exit 0; exit 2 = library changed, re-run both; exit 3 = stop and report). Acceptance: any added/removed venue or city flag ("venue mismatch:" or "recordings of this date disagree on city") on a venue_changes.txt row is a DEFECT -> stop and report; flags.txt added 0 for every family; packaged_exposure "newly held" (none); record predicted_list.json row count. Apply NOTHING; leave the base worktree for the owner; note predicted_list.json is tied to this branch's sha. Dispatch: Sonnet implementer (runs, long — background + 270 s polls), then an Opus reviewer of the numbers.
**GATE B** — after Task 9: one Opus final whole-branch reviewer (review mode Opus) over review-package bfaa837..HEAD (or merge-base main), pointed at this ledger's deferred-minor and Ruling lines; ONE fix dispatch for its findings + one scoped Opus re-review; adjudicate residuals; then stop at the finish menu and report (never merge or push). Final report lists every Ruling: line with its cost-if-wrong.
**Mechanics for the next orchestrator.** $D=/Users/shawn/projects/llama/.claude/worktrees/held-backlog-small-fixes/.superpowers/sdd/small-fixes; dispatch via ~/.claude/sdd-dispatch.sh (task names used so far: t1-* … t8-verify; pick new ones). Shared child instructions: .superpowers/sdd/2026-10-21-held-backlog-small-fixes/{implementer-common.md,reviewer-common.md,global-constraints.md} (mandates 1-5 verbatim inside; commit trailer Opus 5.5 + session_01YRawdtMCo2dUTWXzXESNHV). Briefs task-N-brief.md and review packages live in the same SDD workspace dir. STATE.md at $D/STATE.md (in-flight empty, mode done). Re-arm a tick on takeover.
