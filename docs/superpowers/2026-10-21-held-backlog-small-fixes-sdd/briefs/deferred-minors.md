Task 9: minor (deferred): jackiegreene-2010-05-29 — operator venue override set, tie-break still changes city case ('Angels Camp, California' -> 'angels camp, california'); spec slice B says operator-override arm "unaffected"; no-event tie line runs before the venue override (suggested: tie = None if overrides.venue is not None)
Task 9: minor (deferred): venue_changes.txt prints 'null -> null' for a field neither arm changed (169 city lines), reads as "no city"
Task 9: minor (deferred): t9-cmp hand-check lists incomplete (40 of 154 DELIVERED; misses e.g. mymorningjacket-2005-06-23, littlefeat-2012-09-02); full lists in $D/t9-review/handback.md
Task 9: minor (deferred): drift row gratefuldead-1966-03-12 — base ADDS a city-conflict flag (not a Tier-1 clear); identical in both arms, so still not this branch
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
