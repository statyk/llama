# Task 13 fix round 1 (task13-fix1)
Commit: see `git log -1` on playout-scheduler. Suite: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q` -> 884 passed, 1 skipped.

## Changes
1. schedule keeps every persisted row of any block still airing (`live` set), so start/slip/MISS/bends come from the whole occurrence. CHOICE: ended shows are dropped from the per-show listing (`block_views(..., since_frame=)`), kept for the header. Test: test_schedule_inside_a_blocks_second_show_keeps_the_blocks_start_miss_and_bends.
2. Pinning tests: test_schedule_after_a_plan_continues_it_and_writes_nothing (plan.jsonl/aired.jsonl/cache/last-good snapshot; start == rows[-1].end+gap, run_start False, base rows, rec.count), test_status_writes_nothing_even_with_a_differing_last_good_clock, test_status_numbers_over_hand_written_rows, test_schedule_trims_views_at_the_horizon.
   Found while testing: trimming by nominal start hid an open-time block that airs now but whose (next) nominal is past the horizon (implicit clock printed "nothing planned"). Views are now trimmed by first-show start.
3/4. status block line: "none now; next X" when the current occurrence's last show has ended (between blocks, plan over); dead condition removed. Tests: test_status_block_is_none_between_blocks_and_after_the_plan.
5. reason_key strips a leading count (`\d+( of \d+)? `). 6. Labels "pool short" / "longer than max_shows" (schedule and status). 7. No slip for open blocks (header prints "starts X" only). 8. CLAUDE.md wording. 9. delivered test asserts `library    delivered: 4 package(s)` and the unvoiced act.

## RED / GREEN
RED (HEAD d7f2bcf source + new tests, scratch copy): 5 failed — second_show (item 1), status_numbers (labels), status_block_is_none (3), open_time_no_slip (7), reason_key (5). Others pass on old code as expected (they pin already-correct behaviour). GREEN: 884 passed.

## Mutants (scratch copy, imports verified inside copy, -B), expected red test named first
- M4 live_clock(save=True) in status -> test_status_writes_nothing_even_with_a_differing_last_good_clock: RED
- M7 misses counts miss is not None / M8 fill over all rows / M12 bends+degraded over whole plan / M15 next may name current -> test_status_numbers_over_hand_written_rows: RED (each)
- M17 no view trim -> test_schedule_trims_views_at_the_horizon: RED
- M18 shown = all base rows (first attempt survived: since_frame made it equivalent; added the assertion that the aired "Block 6" header is absent) -> second_show test: RED
- M19 rows=[] / M20 start=end, run_start True / M21 empty history -> test_schedule_after_a_plan_continues_it_and_writes_nothing: RED (M19 also second_show)
- Item-1 regression (shown = end_frame > now only) -> second_show test: RED
