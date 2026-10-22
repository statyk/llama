# orch-r1 finish — held-backlog small-fixes, 2026-10-21T22:01:09-0400

Final commit: ba8c964 (branch held-backlog-small-fixes-impl, 16 commits since bfaa837). Suite run by orch-r1: ./.venv/bin/python -m pytest -q = 4047 passed, 1 skipped, 8 deselected.

## Rulings I made (orch-r1, in order) and the predecessor's (orch), each with cost if wrong
### orch (predecessor)
Ruling: models — every implementer Sonnet (the plan names no Opus task line; brief: Opus only on BLOCKED-for-reasoning); every reviewer Opus — brief's instruction — cost if wrong: an extra fix round on T6/T7.
Ruling: spec-compliance and code-quality reviewers run as two separate Opus dispatches, concurrently (both read-only on the same diff) — brief lists both; concurrency saves wall clock, 2 agents needs no fleet check — cost if wrong: a quality review of code that later changes in a spec fix round.
Ruling: T1 quality Minor 1 promoted to a fix round — the spec's slice D says tests cover both sides, and the gate's research side has none (a surviving mutant shows it) — cost if wrong: one cheap fix round. Minors 2-3 folded into the same round; Minor 4 kept as mandated.
Ruling: T4 fix round 1 also takes quality Minors 1-4 (take_snapshot failure path untested; vacuous audio assertion; unlink missing_ok in restore; initial discard must verify .txn is gone, = spec-review minor) — strict surface, all cheap, two reviewers flagged the leftover-discard path — cost if wrong: a slightly larger fix diff.
Ruling: T6 fix round 1 takes quality Minors 1+5 (three failure tests can pass via any early refusal; in-unit typer.Exit restore unpinned) and the spec's CLAUDE.md label minor — strict surface, tests a later mutation run leans on, cheap — cost if wrong: one small fix round.
Ruling: T7 fix round 1 takes quality Minor 2 (new [u] except has no test — the global constraint requires one; treated as a real gap), Minors 3-4 (tighten removed-show and metadata tests), Minor 6 (capture the view BEFORE the per-turn re-resolve, closing the offers/view window) — strict surface, cheap — cost if wrong: one small fix round.
Ruling: T8 mutant list amended for code moved by fix rounds — B1/B12 spelled against the implementation's form; C5 split into C5a (yield) / C5b (take_snapshot); C10b (.lock snapshotted) and C16 (_discard_leftover check removed) added; C8 prediction may widen to T4's newer leftover tests, written before flipping — the spec asks that each removed restore/re-resolve step turn a named test red, and these are the steps as built — cost if wrong: a few extra mutants.
Ruling: T8 has no diff, so one Opus verifier covers both spec and quality (audits the driver, re-runs a sample of mutants independently) instead of two reviewers — cost if wrong: a weaker review of a measurement, mitigated by independent re-runs.
### orch-r1
Ruling: jackiegreene override-city divergence goes to GATE B's final reviewer as a deferred minor rather than a Task 9 fix round — Task 9 has no diff of its own and the final review's one fix dispatch is the place for code changes; the spec ("operator override ... unaffected") favours fixing — cost if wrong: one show's city case differs until fixed.
Ruling: Minor 3 moves [m]/[i]'s echo after the unit, overriding T7's brief-mandated in-unit echo placement — llama-db's ruling for the owner; matches fix's existing order — cost if wrong: one line of output order.
Ruling: GATE B residual minors stay deferred — the skill allows exactly one final fix wave and none is load-bearing; the triage re-print test gap is the one worth a later pin — cost if wrong: a future regression of the re-print goes unseen by tests.

## llama-db/owner rulings applied by orch-r1
2026-10-21T20:48:23-0400 orch-r1 start. Task 9 AUTHORIZED by llama-db (owner go ~20:25, library kept quiet). Meter: 5h 26% resets 23:19; 7d 11%.
2026-10-21T20:49:28-0400 llama-db correction relayed to t9-run: stop on FIRST compare exit 2 (no re-run)
2026-10-21T20:53:48-0400 llama-db ruling: option (a) — compare --no-repro-gate on EXISTING arms into NEW dir cmp-norepro/ (cmp/ untouched); measurement only, its predicted_list.json NOT for apply; exit 2 or any venue/city flag change still = stop; 13 held drift rows = "known base drift (Tier-1 owner-rejected / not applied)" (minutemen-1985-11-30 was owner-rejected at Tier 1 Checkpoint E).
Task 9: complete (no commits; compare exit 3 then --no-repro-gate exit 0 per llama-db ruling; acceptance holds; review ACCEPT WITH NOTES)
2026-10-21T21:12:37-0400 STOPPED at GATE B: Important finding -> report to llama-db before acting (order).
2026-10-21T21:14:14-0400 llama-db GO for one GATE B fix wave: Important 1; Minor 2 (re-resolve + re-capture view + re-print after ShowChanged, retry works); Minor 3 NARROW ([m]/[i] print "updated" after unit exits; no new wording); Minor 4; Minor 5 + T4 docstring. Rest deferred. HOLD before any merge-ready report (owner may narrow slice B -> second wave + harness re-run).
Ruling: Minor 3 moves [m]/[i]'s echo after the unit, overriding T7's brief-mandated in-unit echo placement — llama-db's ruling for the owner; matches fix's existing order — cost if wrong: one line of output order.
2026-10-21T21:21:30-0400 HOLD before merge-ready report (llama-db): owner may narrow slice B (venues_equivalent) -> second wave + harness re-run.
2026-10-21T21:50:33-0400 llama-db: OWNER RULED to NARROW slice B — tie-break only when selected stripped string and vote string are structure.venues_equivalent; all existing conditions kept; failing-first non-equivalent test; mutant with prediction in scratch; spec + CLAUDE.md docs; CLAUDE.md:62 step order; re-run CAND arm only + compare --no-repro-gate vs existing base.json into cmp-norepro-2 (exit 2 -> re-run base too); then scoped Opus re-review; then remove base worktree and report merge-ready.

## Deferred minors (all)
Task 9: minor (deferred): jackiegreene-2010-05-29 — operator venue override set, tie-break still changes city case ('Angels Camp, California' -> 'angels camp, california'); spec slice B says operator-override arm "unaffected"; no-event tie line runs before the venue override (suggested: tie = None if overrides.venue is not None)
Task 9: minor (deferred): venue_changes.txt prints 'null -> null' for a field neither arm changed (169 city lines), reads as "no city"
Task 9: minor (deferred): t9-cmp hand-check lists incomplete (40 of 154 DELIVERED; misses e.g. mymorningjacket-2005-06-23, littlefeat-2012-09-02); full lists in $D/t9-review/handback.md
Task 9: minor (deferred): drift row gratefuldead-1966-03-12 — base ADDS a city-conflict flag (not a Tier-1 clear); identical in both arms, so still not this branch
GATE B: minor (deferred): test_triage.py:765-777 does not pin the re-print half of the ShowChanged retry (a capture-then-continue mutant passes); removed-meanwhile branch untested
GATE B: minor (deferred): CLAUDE.md:62 says "re-resolves, re-captures and re-prints" — code captures first then re-resolves (wording order)
GATE B: minor (deferred): retry branch tests 'not entry.ws.provenance.exists()' not show_unit's own condition; a held show with no provenance whose overrides change still dead-ends (near-unreachable)
GATE B: minor (deferred): re-entry runs inside the except block (exception chaining in later tracebacks; recursion depth = consecutive refusals) — cosmetic
GATE B: minor (deferred): CLAUDE.md Venue tie-break bullet does not say an operator venue override suppresses it (out of scope, accurate as written)
GATE B: minor (deferred): new 9:30 Club test's city assertion cannot fail (both recordings 'Washington, DC')
GATE B: minor (deferred / owner-visible): narrowing removes 58 ties, not ~38 as docs cite; ~20 of the 58 look like one venue spelled two ways venues_equivalent does not fold (Knaack Club/Klub, 1st/First Avenue, Ironhorse/Iron Horse Music Hall, ...) — they ship the vote as base did
GATE B: minor (deferred / owner-visible): venues_equivalent's subset rule lets long-form strings through (belafleckandtheflecktones-1991-08-02 'Lonesome Pine' -> 'Kentucky Center for the Arts, Bomhard Hall, Lonesome Pine Special', DELIVERED) — per the ruled predicate
Task 1: minor (deferred): CLAUDE.md:778 new clause is one ~230-char line in an 80-wrapped paragraph
Task 1: minor (deferred): test_structure.py:2077 imports added mid-file with noqa E402 (matches local style)
Task 2: minor (deferred): no pin for a tie in the final-else / 1c arms (code shows untouched)
Task 2: minor (deferred): gather.py:958 venue_tie_break's sel lacks the RecordingSummary | None annotation
Task 2: minor (deferred): gather.py:955 sel unannotated (dup of spec minor)
Task 2: minor (deferred): gather.py:1426-1432 step-1 predicate written twice (vote + tie); optional passes_step_1 helper
Task 2: minor (deferred): test_stage_gather.py:3037 mid-file imports
Task 2: minor (deferred): test_stage_gather.py:3080 lambda idiom (brief-verbatim)
Task 2: minor (deferred): incompatible-city tie test's venue assert is vacuous (strings strip equal); city half catches B2
Task 2: minor (deferred): step-1 non-corroborate test relies on vendored jerrybase CSV row
Task 2: minor (deferred): CLAUDE.md:623 new sentence one ~600-char line
Task 3: minor (deferred): test 'ignores an identical diff' still lists the show (city change); the identical-only skip path is untested
Task 3: minor (deferred): base-diff/cand-null direction and unreplayable header count untested
Task 3: minor (deferred): venue/city flag changes not separated from other flag changes (brief-mandated layout)
Task 3: minor (deferred): unreplayable shows counted not named; one-arm-unreplayable not distinguished; summary line omits skip count (plan-mandated)
Task 3: minor (deferred): unchanged no-diff field prints null -> null (may read as 'ships no venue')
Task 3: minor (deferred): untested: skip counter, cand-vs-base state, _all_flags vs _flags, added/removed swap
Task 3: minor (deferred): row omits outcome (needs-LLM rows' replayed venue may not ship)
Task 4: minor (deferred): symlinks dereferenced by snapshot/restore (library has none; docstring line)
Task 4: minor (deferred): a unit on an already-removed show leaves a .lock husk without any race (docstring says 'racing rm')
Task 4: minor (deferred): restore rewrites unchanged files (mode/mtime change; optional diff-only write-back)
Task 4: minor (deferred): c9d770c commit message test line does not name the full-suite command
Task 4: minor (deferred): refusal test patches shutil.rmtree process-wide (patch show_unit_mod.discard_snapshot instead)
Task 4: minor (deferred): show_unit docstring limitation 3 omits the new 'cannot remove leftover snapshot' refusal
Task 5: minor (deferred): redo's removed-show check runs after leftover discard + snapshot (spec C1 orders 3 before 4-5); harmless, plan-mandated
Task 5: minor (deferred): test_a_leftover_txn_is_deleted_not_restored_by_the_next_redo cannot distinguish deleted from restored (T4's ghost test pins it; carry to T8)
Task 5: minor (deferred): CLAUDE.md:65 'see llama fix below' — fix entry is above
Task 5: minor (deferred): batch FAILED line prints slug twice for ShowChanged (pre-existing format); IAError redundant in that tuple
Task 5: minor (deferred): batch restore test doesn't assert bready's write committed
Task 5: minor (deferred): single redo's pre-unit provenance check duplicates _redo_show_locked's message
Task 5: minor (deferred): test import polish (test_redo_cmd.py duplicate llama.workspace import; ordering)
Task 6: minor (deferred): CLAUDE.md 'One unit' text went into a new bullet labelled '`llama fix` is one unit' instead of the brief's 'One unit (2026-10-21):' on the existing fix entry (CLAUDE.md:61-62)
Task 6: minor (deferred): no-show.json tests don't cover --narration full refusal nor --unexclude/--set-breaks/--clear-title passing
Task 6: minor (deferred): test_no_run_stages_bad_overrides... passes on parent (redo restore is T5's); not marked (pin)
Task 6: minor (deferred): lone --overrule on a non-held show now waits on the show lock and snapshots before saying 'not held' (behaviour note for final review)
Task 6: minor (deferred): edit lines now print after the redo's progress (plan-mandated)
Task 6: minor (deferred): fix is ~305 lines; unit body a natural _apply_fix_edits helper
Task 6: minor (deferred): CLAUDE.md:65-66 fix entry now ends with a full stop so the 'llama redo' item starts as a fragment
Task 7: minor (deferred): triage tail passes a fresh _resolve_show(...) entry to _redo_show_locked instead of entry (harmless, under lock)
Task 7: minor (deferred): removed-show triage test asserts only 'error: '
Task 7: minor (deferred): no test fails [u]/[e]/[i]/[t] partway and asserts return to prompt
Task 7: minor (deferred): per-turn re-resolve scans the whole library (~1 s/turn warm on 3983 shows; plan-mandated) — factor a one-directory entry builder (OWNER-VISIBLE UX cost for final review)
Task 7: minor (deferred): five '# noqa: E731' lambdas with no linter configured; mixed lambda/def under one name (functools.partial suggested)
Task 7: minor (deferred): 'metadata override updated' echoed inside the unit then rolled back on failure (brief-mandated echo placement)
Task 7: minor (deferred): removed-show message is 'no show matches <path>' not slice C's 'the show was removed' (brief's choice)
Task 7: minor (deferred): no test pins capture_view-before-re-resolve ordering (concurrent-only window)
**Every deferred minor** is a "Task N: minor (deferred):" line in this ledger (46 lines; grep them) — point the final reviewer at that list. Notable ones: T2 step-1 predicate duplicated (vote + tie), CLAUDE.md long lines (T1 fixed; T2:623 not), vacuous venue assert in the incompatible-city tie test; T3 untested report edges (unreplayable header count, base-diff/cand-null, _all_flags vs _flags, added/removed swap), null->null rendering, row omits outcome; T4 docstring limitation 3 omits the new leftover refusal, refusal test patches shutil.rmtree process-wide, symlinks dereferenced, restore rewrites unchanged files; T5 batch FAILED line prints slug twice, batch test doesn't assert the success side, duplicated provenance message, test import polish, CLAUDE.md fragment; T6 fix ~305 lines (_apply_fix_edits), no-show.json flag coverage breadth; T7 noqa E731 lambdas, ordering pin. Every ruling is a "Ruling:" line above (8 so far).
