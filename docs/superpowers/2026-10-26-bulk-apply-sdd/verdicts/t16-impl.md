# t16-impl handback
Status: DONE_WITH_CONCERNS. Commit 928b784b.
RED: all 11 new tests failed before implementation (argparse "invalid choice: 'lists'/'wave-check'/'spot-check'", AttributeError no render_side_by_side); see t16-impl.log.
Tests (scripts/test_bulk_apply_lists.py, 11): the 8 named + render_side_by_side stars + unreadable-campaign stderr report + (selection test covers profile/state/kind/slugs/limit/include-voiced/famous).
Full suite: ./.venv/bin/python -m pytest -q -> 6316 passed, 1 skipped, 8 deselected.
Design: select_wave() shared by lists/--counts; outcome checked before row_visible_changes/row_label_only (_NO_DIFF); unreadable campaign record -> stderr string, not listed; unreadable station manifest/stat of a show -> stderr, excluded; no station copy = unvoiced; lists needs require_pinned_code + arm sha == pin sha + fingerprint == config's. --counts honours filters and famous exclusion, counts voiced separately.
Concerns: (1) wave-check refuses (exit 2) a delivered row with no station copy (brief: every delivered row's manifest must read). (2) --counts excludes famous slugs and honours --profile/--state/--kind/--slugs if given. (3) famous packet covers every famous slug in the arm, not only otherwise-listable ones. (4) I briefly wrote full.out/full.rc into $D/t16-impl (merged into the log, removed).

## Fix round 1 (commit c225ca33)
1. New test_lists_refuse_a_missing_station_root_or_delivery_path: RED "assert 0 == 2" (lists exited 0 with the station renamed away); fixed by refusing in cmd_lists before the pin/arm/show reads ("no delivery_path in config"; "station root X is not mounted or not a directory"), both list and --counts paths.
2. test_famous_shows_go_to_a_packet now sets explicit titles/sets/segues on the famous arm row and asserts index 1 unstarred, index 2 starred with "set 1->2", "title Song 2->Renamed", "segue -->>". RED against the _row_side->[] mutant in a scratch copy (git archive, PYTHONPATH shadowing, llama/bulk_apply __file__ proven inside copy): "*   1  set 1->?  title Song 1->?  segue -->?" starts with '*'.
Suite: ./.venv/bin/python -m pytest -q -> 6317 passed, 1 skipped, 8 deselected.
