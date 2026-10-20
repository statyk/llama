# t6-impl handback
Status: DONE_WITH_CONCERNS (see deviations)
Implemented `compare` in scripts/replay_holds.py per brief + orchestrator rulings: gates (exit 2: setlistfm/config fingerprint/digests/one-arm-only, nothing written; exit 3: <99% over base held non-needs-llm plus state=unknown/unreplayable rows, only drift.txt written), all report files, predicted/structure_changed/pilot lists, summary last. date included in exposure; arm-missing data read read-only from <root>/shows/<slug>/ and cache/md_<id>.json with placeholders; notes grouped with `other` (and `format sibling tagged`).
Tests: 11 new in scripts/test_replay_holds.py (brief's 7 + one-arm-only/setlistfm, unknown-state denominator, closest-calls/notes groups, pilot swap). Full suite: ./.venv/bin/python -m pytest -q -> 3282 passed, 1 skipped, 8 deselected.
Deviations/concerns: implementation and tests were written together, so no separate RED run was recorded. structure_changed_list rows use `outcome` = would_be. Slice 5c shows alignment/set_breaks only (Task 18 adds subsections). Exit-3 path writes drift.txt only. Pilot test is weak if the first 10 already hold 2 reuse rows. Summary lists counts, not file contents.

## Fix round 1
Changes: (1) gate now `ok * 100 < 99 * len(denom)`; (2) `_pilot` test rewritten with reuse rows beyond position 10, asserting the exact slug set; (3) new test for structure_changed_list (`outcome == would_be`, absent from predicted/pilot) and a needs-llm row in no list; (4) compare unlinks its known OUTPUT_FILES from --out after the gates pass (before drift.txt; never rmtree; other files kept). Exit 2 writes/removes nothing, leaving prior files alone, since nothing was decided.
Tests: test_compare_gate_boundary_is_99_percent[99-0,98-3], test_pilot_list_swaps_in_reuse_rows, test_structure_changed_and_needs_llm_rows_reach_the_right_lists, test_compare_clears_stale_outputs_before_a_failing_gate.
Mutants (scratch rsync copy, PYTHONPATH shadowing proven: llama.__file__ inside the copy, private PYTHONPYCACHEPREFIX each; baseline 36 passed):
- gate 99 -> 100 -> predicted test_compare_gate_boundary_is_99_percent[99-0] -> caught by it
- `while False and` in _pilot -> test_pilot_list_swaps_in_reuse_rows -> caught by it
- sclist r["outcome"] instead of would_be -> test_structure_changed_and_needs_llm_rows_reach_the_right_lists -> caught by it
- drop the unlink -> test_compare_clears_stale_outputs_before_a_failing_gate -> caught by it
Full suite: ./.venv/bin/python -m pytest -q -> 3286 passed, 1 skipped, 8 deselected.
