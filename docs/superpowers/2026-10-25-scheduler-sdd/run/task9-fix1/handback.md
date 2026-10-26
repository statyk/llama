# Task 9 fix round 1: handback

Status: DONE. Both commits are on `playout-scheduler`. Each was green, and neither was amended.
- **a839abb** fixes items 1–6: `later` only once and only at the last boundary, `used` anchored to frames, the horizon counted in projected frames, the exact block start, `ahead ≥ 1`, and typing.
- **cdc9dc4** fixes item 7 (ruling R16): at gap 0, least recently aired still ranks first.

Command: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`
Final output: **797 passed, 1 skipped in 24.38s**

## Changes

1. **`later` only at the last boundary, and at most once per occurrence** (`scheduler.py`, `_try_later` / `boundary`).
   - **(i)** `_try_later(s)` now judges each form with its own clip in place. It uses `_run_at(s + clip + gap)` and requires `step(k).shows` to be non-empty and `step(k+1).shows` to be empty. X's start is that run's final landing. Y is judged on X's run from there, with the last show added to `rec` and to `used`.
   - If no form qualifies, the active run is restored and the ID decided at `m` stands.
   - **(ii)** A `later_done` flag is set from the rows: any persisted row with `role == "later"` that names this occurrence. It is also set when a `later` is projected, and reset on entering a new occurrence. While it is set, "last" boundaries get an ID.
2. **R14: `used` is anchored to the frame line.**
   - `USED_WINDOW_HOURS = 24`, and `USED_WINDOW_FRAMES = frames_ceil(samples_for_seconds(24*3600)) = 3_720_938`.
   - `used_at(F)` returns the slugs of show pieces, persisted or projected, whose `start_frame` lies in `[F − W, F)`. It reads sorted start lists with `bisect`.
   - Every run gets `used_at(its start)`. A judgment run for Y after a `later` also gets the last show.
   - `SchedulerInput.now_us` is removed.
   - `_run_at` reuses the active run only when `run.used ∪ placed == used_at(start) ∪ placed`, which is exactly what a fresh live run would see.
3. **The `until_frame` horizon is counted in projected frames.** The projection runs until a piece's `end_frame` reaches `until_frame`, then goes `ahead` more occurrences. It never stops before the old clock-based horizon (`max` of the two).
4. **One fill cause per block.**
   - `_BlockRun` takes an optional `block_start`. When it is None, the old formula is used, so `fill_block` and its tests are unchanged.
   - The projection passes the frame of the occurrence's first show, whether persisted or projected (`self.block_start`).
5. **`ahead < 1` now raises `ValueError`.** This is documented in `project`.
6. **Typing.** A `_Choice` NamedTuple carries the `_try_*` and `boundary` results. The stop value is a typed `_STOP: Final = _Stop()`. `boundary` returns `PlannedPiece | _Stop | None` and `show` returns `PlannedPiece | _Stop`.
7. **R16** (`rules.py`). `GAP0_RECENCY_HORIZON_DAYS = 365`.
   - With `gap_days == 0`, an aired show's recency term is `0.9 * min(days / 365, 1.0)`, computed in float days. A never-aired show stays at 1.0.
   - With gap > 0 the term is unchanged. The gap rule is still off at 0.
   - The module docstring and the `recency_term` docstring are updated.
   - **Test changed:** `test_rules.py::test_gap_zero_disables_the_gap_rule_without_dividing`. It pinned the flat 0.9 for a show aired an hour ago; it now expects `0.9 * (1/24) / 365`. No other test pinned 0.9 at gap 0. `test_scheduler_block.py::test_gap_zero_never_counts_a_gap_bend` and `test_scheduler.py`'s `used` test still pass unchanged.

## Covering tests (all in `test_scheduler.py` unless noted)

- **Item 1:**
  - `test_later_only_at_the_last_boundary_over_varied_lengths[repro|day|eve]` uses 3 seeds per clock, 4 ID clips of 5–30 s, every announcement voiced at 4–20 s, and 4 days per run. It asserts at most one `later` per occurrence, that every `later` is followed by exactly one show of its own occurrence, and at least 3 `later`s per run. Runtime is about 0.5 s per clock.
  - `test_a_persisted_later_turns_a_later_last_boundary_into_an_id` covers clause (ii).
- **Item 2:**
  - `test_used_is_the_shows_started_in_the_24_hours_before_a_run`: yesterday's 10:00 favourite comes back exactly once, at or after +24 h.
  - `test_used_window_is_half_open_on_the_frame_line`: `F−W` is in the window, `F−W−1` is out, `F−1` is in.
- **Item 3:** `test_until_frame_is_reached_by_the_projected_pieces_when_blocks_land_early`. It uses four 6 h blocks with one 60-min show each, so blocks land early.
- **Item 4:** `test_one_fill_cause_per_block_whatever_the_id_lengths`. The two longest own shows land 30 s before the next window. IDs are 5/5/60 s and the estimate uses 5 s. Three 4-min fill rows follow.
- **Item 5:** `test_ahead_below_one_is_refused`. `test_until_frame_extends_the_horizon` now uses `ahead=1`.
- **Item 7:**
  - `test_rules.py::test_gap_zero_ranks_least_recently_aired_first`: never aired (1.0) > 400 d (0.9) > 60 d (0.9·60/365) > 1 d (0.9/365); gap > 0 unchanged.
  - `test_scheduler_block.py::test_gap_zero_prefers_the_show_aired_longer_ago`: `fill_block` with equal shows; the tie rank is arranged to favour yesterday's show, and the 200-day-old show wins.

## RED and GREEN output (log: `task9-fix1.log`)

Items 1–6 RED, run against the old code with a temporary `now_us=None` shim in `mk` (removed before the commit):
```
FAILED test_used_is_the_shows_started_in_the_24_hours_before_a_run      (no USED_WINDOW_HOURS)
FAILED test_used_window_is_half_open_on_the_frame_line                  (no USED_WINDOW_FRAMES)
FAILED test_ahead_below_one_is_refused                                  DID NOT RAISE ValueError
FAILED test_until_frame_is_reached_by_..._land_early                    assert 1245106 >= 4651172
FAILED test_one_fill_cause_per_block_whatever_the_id_lengths            ['structural', 'pool-short', 'pool-short']
FAILED test_later_only_at_the_last_boundary_..[day]   ('day', 2, ('b', ..), ['id','show','later','show','later','show'])
FAILED test_later_only_at_the_last_boundary_..[eve]   2 laters in ('late', '2026-11-03T04:30')
FAILED test_later_only_at_the_last_boundary_..[repro] 2 laters in ('night', '2026-11-03T02:30')
8 failed, 34 passed
```
Items 1–6 GREEN: `test_scheduler.py` 42 passed, then 43 with the clause (ii) test. Full suite: 795 passed, 1 skipped.

Item 7 RED:
```
test_gap_zero_disables_...: Obtained 0.9, Expected 0.000102739726...
test_gap_zero_ranks_least_recently_aired_first: no attribute 'GAP0_RECENCY_HORIZON_DAYS'
test_gap_zero_prefers_the_show_aired_longer_ago: ['y'] != ['x']   (yesterday's show won on tie rank)
```
Item 7 GREEN: full suite 797 passed, 1 skipped.

## Mutants (scratch copy shadowed through `PYTHONPATH`, `-B`, `transmitter.__file__` checked inside the copy, the red test predicted before each run)

Item 1, each clause separately:
- **Clause (i) removed** (the exactly-one-more-show check with the clip in place):
  - Prediction: the property test turns red.
  - Result: red on `test_later_only_at_the_last_boundary_over_varied_lengths[day]`, `[eve]` and `[repro]` (3 failed, 40 passed).
- **Clause (ii) removed** (`not self.later_done`):
  - Prediction: `test_a_persisted_later_turns_a_later_last_boundary_into_an_id` turns red.
  - Result: red on exactly that test (1 failed, 42 passed).
- With (i) in place, the property test alone does **not** catch the loss of (ii). After the fix, a second `later` needs a re-plan after the block's last show, which the probe never produced. That is why clause (ii) has its own state-derived test.

Other mutants:
- **Item 2, the window ignored:** red on both `used` tests.
- **Item 3, clock horizon only:** red on the early-landing test.
- **Item 4, no `block_start` passed:** red on the fill-cause test.
- **Run reuse ignoring `used`:** red on `test_used_is_the_shows_started_in_the_24_hours_before_a_run`.

## Probe re-run (the reviewer's `p7.py`, 14 days × 3 clocks × 4 seeds)

Every run reports **0 occurrences with more than one `later`** and **0 occurrences whose `later` is not followed by exactly one show**:
- repro, seeds 0–3: 45 occurrences, 28–30 `later`s, 0.4 s each
- day, seeds 0–3: 45 occurrences, 14–15 `later`s, 0.5 s each
- eve, seeds 0–3: 45 occurrences, 42–45 `later`s, 0.6 s each

Before the fix the reviewer measured up to 7% of occurrences with 2–3 `later`s.

## Live versus one-shot after the fix (`stress.py`, outside the suite)

- 4 clocks (repro, implicit, eve, busy with `exclude_profiles`) × 3 seeds, 2–5 ID clips of 5–30 s, 80% of announcements present, 3 days each: **12 runs, 0 mismatches**.
- `test_appending_first_pieces_reproduces_one_projection` passes.

## Notes and concerns

- **Cost under the implicit clock.** A frame-anchored `used` slides with the run start. A run therefore stops being reusable once a show from the previous day leaves the 24 h window, and a fresh run is built. With 24 h open blocks this costs more:
  - one-shot over 3 days: about 1.3 s, previously 0.7 s;
  - one live `project` call: about 0.6 s, previously 0.3 s, on this Mac;
  - the implicit-clock 7-day test: 2.0 s, previously 1.2 s.
  - Profile-block clocks are unaffected (the 3000-pool test still takes 0.20 s).
  - This is the price of being exact: a fresh live run sees the same window.
- **Task 8 behaviour I noticed while building the fill-cause scenario (not changed):** once a block's landing is inside the window, the `()` option is tier 0 and ends the block. A run that planned two fill shows therefore plays only one when the first fill already lands it.
