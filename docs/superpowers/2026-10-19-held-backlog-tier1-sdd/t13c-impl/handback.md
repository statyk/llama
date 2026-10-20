Task 13c DONE. Commit b6f353a. Full suite: ./.venv/bin/python -m pytest -q -> 3574 passed, 1 skipped, 8 deselected.
Changes: scripts/replay_holds.py (flag, stderr line, summary line 1), 3 new tests in scripts/test_replay_holds.py, plan doc (two -prev compares + sentence). Nothing else parses "base reproduces" except the existing test (still passes).
No-flag exit-3 case was already pinned (test_compare_refuses_a_baseline_that_does_not_reproduce, test_compare_clears_stale_outputs_before_a_failing_gate); added one more asserting no summary/predicted list and no skip text.
Deviations: none.
Mutation (shadowing proven, paths under scratch copy):
m1 flag ignored -> test_compare_no_repro_gate_reports_the_ratio_and_writes_everything -> caught by it
m2 flag skips _gates -> test_compare_no_repro_gate_still_refuses_a_moved_library -> caught by it
m3 gate always skipped -> the exit-3 tests -> caught by 6 (test_compare_refuses_a_baseline_that_does_not_reproduce, ..._low_reproduction_base_with_no_flag..., gate_boundary[98-3], unreadable_state..., clears_stale_outputs..., writes_the_report_set)
