# Task 11 fix round 1 re-review (task11-rereview1)

Scope: fix diff 6d16ed9..e157449 (config.py comment, pipeline.py guard and comment, four new tests in test_pipeline.py). This was a read-only review. Mutants ran only in `git archive e157449` copies under `<scratchpad>/t11rr/{base,MA,M8,M1}`, each from an empty cwd with `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<copy>/packages/transmitter/src:<copy>/packages/transmitter .venv/bin/python -B -m pytest -p no:cacheprovider`. In every copy, `transmitter.pipeline.__file__` and `tests_transmitter.__file__` were printed and resolve inside that copy.

The full `tests_transmitter` suite ran per copy. Base: 830 passed, 1 skipped, plus `test_relay_key_matches_antenna`. That test reads `antenna/src/alerts.ts`, which was not in the archive. With `antenna/src` added it passes (48/48 in test_relay.py), so base is 831 passed, 1 skipped, the same as the fix report.

## Finding Verdicts

1. **(Important) Render skip path after a `show_gap_seconds` change: ADDRESSED.**
   - New test: `test_scenario_skip_path_after_a_show_gap_seconds_change`.
     - Setup: plan at gap A, render 3 segments, shrink to 0.5 s, fail a later show that is not on air, render.
     - Asserts: no error; `new[i].start_frame == victim.start_frame == new[i-1].end_frame + old_gap`; prefix unchanged on the old gap; victim gone; `new[i:]` on the new gap; covered; target reached.
   - The comment at the `expected = ...` line in `Station.extend` names the skip-path reason.
   - Mutant MA: the first non-run-start row must sit at `(appended[-1] or out[-1]).end_frame + gap`.
     - Predicted red: that test.
     - Result: **exactly that test red** (2 failed, but the second is the copy-scope relay test that also fails on base; 829 passed).
2. **(Minor) Forget-on-mismatch: ADDRESSED.**
   - New test: `test_a_frame_count_change_under_the_same_pause_and_extra_is_re_measured`. It raises `samples_per_file` on the same Station. It asserts the in-place re-plan of rows[0] at the new count, each piece re-planned once, rows[0] encoded first, and covered.
   - Mutant M8: `lengths.forget(piece.key)` replaced by `pass`.
     - Predicted red: that test.
     - Result: **exactly that test red** (plus the copy-scope relay test).
3. **(Minor) `degraded` arm of `_announcement_broken`: ADDRESSED.**
   - New test: `test_announcement_broken_when_the_named_block_degrades_to_open_time`. b05 is restricted to `polka` and there are no polka shows. The test asserts the first row `miss=False, degraded=True`, `announcement_broken=True`, and the log line.
   - Mutant M1: `not (row.miss or row.degraded)` becomes `not row.miss`.
     - Predicted red: that test.
     - Result: **exactly that test red** (plus the copy-scope relay test).
4. **(Minor) plan_step extend-branch guard: ADDRESSED.**
   - Placement: the guard is only in the `else` (extend) branch, after `next_start`. It runs before `st.extend` and `write_plan`, so a raise leaves the plan and the segments untouched. The test asserts `plan.jsonl` is unchanged.
   - Cannot fire on a legitimate path:
     - `planner.next_start` is literally `rows[-1].end_frame + gap_frames`, so the guard compares the same expression with itself.
     - A fresh run (`nxt is None`) and recovery (`cut_for_recovery`, `start = fresh`) are the other two branches and never reach it.
     - A phase-1 plan, or one laid under an older gap, still goes through `end + current gap` on both sides. `end_frame` honours `cut_frame` on both sides.
     - Render's re-extend calls `st.extend` directly with `replan_from`'s start, not `plan_step`.
   - Test: `test_plan_step_guards_the_first_appended_rows_start` monkeypatches `pipeline.next_start`, which pipeline imports by name, so the patch takes effect. `pytest.raises` also proves the extend branch was reached.
5. **(Minor) Config template comment: ADDRESSED.** It now reads "seed of the scheduler's deterministic tie-break". `test_config`, including `test_template_parses_to_the_defaults`, is green in the base copy.

## New Breakage in the Fix Diff
None.

## Out-of-Scope Observations
- `test_relay_key_matches_antenna` needs `antenna/src` in the copy, and `test_measure` needs `docs/superpowers/2026-10-25-scheduler-measurement`. The brief's `git archive ... packages/transmitter antenna/templates` recipe omits both, so the two fail in a scratch copy. This is a recipe gap, not a defect.

## Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage.
