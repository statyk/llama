# RF sweep report
Status: DONE. Baseline at 3497e77e: 6343 passed, 1 skipped, 8 deselected.
Commits: 547b5cb7 (RF1), a82b0755 (RF2). Final suite: `./.venv/bin/python -m pytest -q` -> 6350 passed, 1 skipped, 8 deselected.

RF1: new `_all_progress_rows` (every parseable line) in scripts/bulk_apply.py; `_foreign_inside` counts spending lines of another kind (by list kind) in the block's window (window/n/measurement still last-row-per-slug; reapply.read_progress untouched). Tests: test_foreign_spend_hidden_by_a_later_retry_is_caught (RED before the fix: block measured as contiguous), test_foreign_window_is_inclusive (parametrized first/last `at`; passed on old code too, it pins the boundary). Commit message says 6345 passed; actual 6346 (3 tests added).

RF2: `_station_root_problem` ("unreadable" | "empty" | None; readable dir + first non-dot entry via scandir) used by cmd_lists, cmd_mark, cmd_wave_check (GateRefused, existing wording kept, empty -> `station root <p> is empty (is the station mounted?)`) and `_mark_one` (`refused: station root <p> is not readable` / `refused: station root <p> is empty (is the station mounted?)`). Tests (RED shown in a scratch copy, 4 failed): test_lists_refuse_an_empty_station_root (also dot-only), test_wave_check_refuses_an_empty_station_root, test_mark_refuses_an_empty_station_root (dry run + --apply, nothing written), test_mark_item_refused_when_the_station_empties_mid_batch.
Existing test changed: test_kind_held_from_briefing_none (lists) used an empty tmp station; fixture now has a `placeholder` dir (reason: RF2 refuses empty roots). No assertion weakened. No other test needed changes.
Concerns: none.
