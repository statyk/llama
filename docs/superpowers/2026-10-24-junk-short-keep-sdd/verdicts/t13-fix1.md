# t13-fix1 report
Status: DONE
Commit: 04afb6f fix(reuse): a new archive item pairs nothing; reapply refuses an undeletable aside
Changes:
1. ReusePlan.identifier (plan-time show.identifier, None without show.json); build_package empties library/station pairings when it differs (old audio still set aside). Tests: test_stage_package.py::test_a_different_identifier_pairs_nothing_but_still_sets_the_old_audio_aside, test_a_plan_without_a_show_json_has_no_identifier; test_redo_cmd.py::test_redo_that_picks_another_item_with_the_same_file_names_ships_no_old_audio. test_audio_reuse's plan equality gained identifier="gd73".
2. reapply: LlamaError "<slug>: cannot remove leftover audio aside <path>" when the aside survives discard_aside; test_reapply_refuses_when_a_leftover_aside_cannot_be_removed.
3. test_reapply_dry_run_leaves_a_leftover_aside now injects a commit-marker failure on the real run and asserts the leftover file never reaches package/audio/ (passes before and after: a guard).
4. cli.py import order fixed.
RED (scratch copy of HEAD src + new tests, PYTHONPATH-shadowed, sentinel confirmed): 4 failed, 2 passed (identifier AttributeError x2, redo downloads [] vs ['a.mp3','b.mp3'], reapply DID NOT RAISE).
GREEN: covering files (test_audio_reuse, test_stage_package, test_redo_cmd, test_fix, test_reapply) pass; full suite ./.venv/bin/python -m pytest -q -p no:cacheprovider: 5058 passed, 1 skipped, 8 deselected.
