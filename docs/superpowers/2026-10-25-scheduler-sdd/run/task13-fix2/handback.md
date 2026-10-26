# Task 13 fix round 2 (task13-fix2) - commit ff7ba19
Suite: ./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q -> 886 passed, 1 skipped.
1. Trim: keep a view if nominal_us < until OR any show starts < until. Test test_schedule_keeps_a_late_block_whose_nominal_start_is_inside_the_horizon (probe: Block 10 10:00-13:00, Block 12 MISS at 13:00, preview 10:30, days 0.1). Open-time and M17 trim tests stay green.
2. live ignores block-less rows. Test test_schedule_does_not_pull_old_phase1_rows_into_the_unscheduled_view.
3. M30 pinned: same test asserts [fill: longer than max_shows], [fill: pool short] and the summary fill labels; mutant fill_label->identity goes red (that test and test_status_numbers).
4. Cruft removed (vacuous assert, dead PlanRow line); mid-file imports moved to top.
RED: HEAD dcd0a2a source + new tests (scratch copy): both new tests failed (view omitted -> StopIteration; 09-30 start printed). GREEN after fix.
