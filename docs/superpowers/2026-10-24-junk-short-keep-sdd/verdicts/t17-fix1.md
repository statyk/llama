# Task 17 fix round 1 handback

Status: DONE. Commit c95c5cd `fix(scripts): rekey_overrides pins ordered kept list; pasteable routes` (on 368ccda).
Files: scripts/rekey_overrides.py, scripts/test_rekey_overrides.py.

## Per finding
1. (Important) New test `test_kept_list_is_compared_in_order`: show.json's track 1 and 2 filenames are swapped (same multiset), with set_breaks [3] and encore_after 5 present. It asserts only `kept list differs`, with detail `first difference at track 1: <d1t02> vs <d1t01>`. RED: mutant Mset (`if set(kept) != set(names):`) in a scratch copy turns it red.
2. (Minor) New test `test_a_matching_title_that_is_not_an_override_is_not_applied`: the legacy title "Morning Dew" on track 1, whose title_source is `tags`, gives `title not applied`. RED: mutant Ma (drop the title_source clause) turns it red.
3. (Minor) New test `test_a_negative_key_without_show_json_is_reported`: `{"titles": {"-1": "X"}}` with show.json removed gives `["no show.json", "title out of range"]`, the second with HAND_EDIT_ROUTE. RED: mutant Mc (`negative = []`) turns it red.
4. (Minor) The `title out of range` detail now gives each key with its number, via new helper `_reads_as`: e.g. `titles keys '7_0' (reads as 70), '+9' (reads as 9) outside 1..6`. This applies to all three out-of-range details. New test `test_title_out_of_range_names_the_number_each_key_reads_as` failed on 368ccda.
5. (Minor) `_print_refusal` now prints `r.route.replace('<show>', r.slug)`, and `Refusal.route` stays `REASONS[reason]`. New test `test_printed_routes_name_the_show` asserts the dataclass template, the printed `` repair: `llama redo gratefuldead-1973-06-10 --from gather` `` and that `<show>` never appears in the output. It failed on 368ccda. The test for each refusal reason now compares the printed repair line with the slug substituted.
6. (Minor) New constant `PROCESS_NOTE`. The dry run prints it right after the `llama processes running:` block: after `... none`, after the last listed process line, and also after a `process check failed` line. New test `test_dry_run_notes_what_the_process_check_cannot_see` checks the empty and the one-process cases. It failed on 368ccda.
7. (Minor) New helper `_first_line(exc)` replaces both copies of the one-liner (the overrides.json unreadable path and the show.json unreadable path).

## RED / GREEN
- RED, new tests against 368ccda's code: `./.venv/bin/python -m pytest scripts/test_rekey_overrides.py -q` gives `3 failed, 31 passed`. The failures are the tests for items 4, 5 and 6. Pins 1-3 pass on 368ccda by design.
- RED, mutants for pins 1-3: scratch git-archive copy of HEAD 368ccda plus the new tests, with PYTHONPATH shadowing. llama.__file__ and rekey_overrides.__file__ were both confirmed inside the copy. PYTHONDONTWRITEBYTECODE, run from an empty cwd. Results:
  - Mset: test_kept_list_is_compared_in_order is red.
  - Ma: test_a_matching_title_that_is_not_an_override_is_not_applied is red.
  - Mc: test_a_negative_key_without_show_json_is_reported is red.
  - Each run also shows the three item 4-6 tests red, which fail on 368ccda anyway. Each run: 4 failed, 30 passed.
- GREEN: `./.venv/bin/python -m pytest scripts/test_rekey_overrides.py -q` gives `34 passed`.
- Full suite: `./.venv/bin/python -m pytest -q` gives `5310 passed, 1 skipped, 8 deselected, 26 warnings in 40.92s`. llama.__file__ is inside the worktree.

## Concerns
None.
