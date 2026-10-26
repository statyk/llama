# Task 11 fix round 1 handback (task11-fix1)

**Status: DONE.** Commit `e157449` sits on top of `6d16ed9`; tree clean.

Full suite: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q` gives **831 passed, 1 skipped** (was 827).

## Changes
1. **(Important) The render skip path after a `show_gap_seconds` change is now pinned.**
   - New test `test_scenario_skip_path_after_a_show_gap_seconds_change`. It plans with the 2 s gap, renders 3 segments, shrinks the gap to 0.5 s, makes a later show fail to encode, then renders.
   - It asserts:
     - no error;
     - `new[i].start_frame == victim.start_frame == new[i-1].end_frame + old_gap`;
     - rows before the victim are unchanged and keep the old gap;
     - the victim is gone;
     - every row from `new[i]` on uses the new gap;
     - the plan is covered and render reached the target.
   - The first-row guard in `Station.extend` (the `expected = ...` line) now carries a comment. It says the first row goes at the caller's start because the skip path hands back the dropped row's own start. After a gap change, `prev.end + new gap` could fall inside an already-written segment, which would be a cut.
2. **(Minor) Forgetting the learned length on a mismatch is now pinned.**
   - New test `test_a_frame_count_change_under_the_same_pause_and_extra_is_re_measured`. It raises `FakeEngine.samples_per_file` after planning, in the same Station, so the cache is not rebuilt.
   - It asserts:
     - `rows[0]` is re-planned once, in place, at the new count;
     - no piece is re-planned twice;
     - the first encode is `rows[0]`;
     - the plan is covered.
3. **(Minor) The `degraded` arm of `_announcement_broken` is now pinned.**
   - New test `test_announcement_broken_when_the_named_block_degrades_to_open_time`. The clock gives b05 `profiles = ["polka"]` and no package has that profile.
   - A persisted `next` announcement names X. X's first show is `miss=False, degraded=True`.
   - It asserts `announcement_broken=True` and the log line `announcement-broken: b05 <iso>`.
4. **(Minor) `plan_step` now guards its own next start.**
   - In the extend branch only, after `start = next_start(rows, gap)`, it raises `LayoutError("plan_step's next start ... is not the gap after the last row ...")` unless `start == rows[-1].end_frame + st.gap_frames`.
   - Run starts (first start, recovery) and the render skip path (`replan_from` inside `render_step`) do not pass through this branch, so they are unaffected. The recovery, skip-path and gap-change tests all stay green.
   - New test `test_plan_step_guards_the_first_appended_rows_start`. It monkeypatches `pipeline.next_start` one frame late, expects `LayoutError`, and asserts `plan.jsonl` is unchanged.
5. **(Minor) Config template comment.** `config.py`'s `[planner]` comment now reads "seed of the scheduler's deterministic tie-break". `test_config` (including `test_template_parses_to_the_defaults`) is green.

## RED/GREEN
I wrote the four tests first, then ran `pytest test_pipeline.py -k "gap_seconds_change or same_pause or degrades_to_open or guards_the_first"`. Result: **1 failed, 4 passed**.
- **RED:** `test_plan_step_guards_the_first_appended_rows_start` failed with `DID NOT RAISE LayoutError`.
- **Already passing:** the other three pin behaviour that was already correct. Their red evidence is the mutant runs below.

After the implementation, `test_pipeline.py` + `test_config.py` gave 85 passed, and the full suite 831 passed, 1 skipped.

## Mutants
Mutants were run in a scratch copy only: a tar copy of the working tree under `<scratchpad>/fix1/{base,MA,M8,M1}`. Each was run from an empty cwd with `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<copy>/packages/transmitter/src:<copy>/packages/transmitter .venv/bin/python -B -m pytest -p no:cacheprovider`, and `transmitter.pipeline.__file__` / `tests_transmitter.__file__` were printed inside each copy. The unmutated copy gave 68 passed.

| Mutant | Change | Predicted red | Result |
|---|---|---|---|
| MA | first non-run-start row's expected start is `out[-1].end_frame + gap_frames` | `test_scenario_skip_path_after_a_show_gap_seconds_change` | **CAUGHT**: only that test red (1 failed, 67 passed) |
| M8 | `lengths.forget(piece.key)` removed | `test_a_frame_count_change_under_the_same_pause_and_extra_is_re_measured` | **CAUGHT**: only that test red (1 failed, 67 passed) |
| M1 | `_announcement_broken` ignores `degraded` | `test_announcement_broken_when_the_named_block_degrades_to_open_time` | **CAUGHT**: only that test red (1 failed, 67 passed) |

## Files
- `packages/transmitter/src/transmitter/pipeline.py`
- `packages/transmitter/src/transmitter/config.py`
- `packages/transmitter/tests_transmitter/test_pipeline.py`

## Concerns
None new. The plan_step guard is tautological against today's `next_start`; it exists to catch a future edit.
