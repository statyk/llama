# Task 9 fix round 1 (task9-fix1): DONE

Commit `775f0c1` (on top of f405b7a). All four items are in this one commit. The three fixes share `plan_step`/`render_step`, and their tests were written together, so a split would have committed unwired intermediate states.

## Changes (packages/transmitter/src/transmitter/pipeline.py)
1. **Frame-count model change → re-plan, not drift.** I added `Station.planned_frames(analysis)`, and `frames_of` now uses it. Before encoding, `render_step` computes `planned` from the analysis it already holds (one `analyze` call). If `planned != r.frames`, the row takes the changed-package path: it is excluded, `replan_from` runs from its start frame, nothing is encoded, and the log reads `plan-changed: skipped <slug> at frame … (planned frame count changed: X now, Y in the plan (config or encoder change))`. `FrameCountDrift` (still caught before `TransmitterError`) now fires only when an encode disagrees with the current model, and the drifted encode is still unlinked.
2. **Recovery ordering.**
   - `plan_step` order is now: cut + `extend` (in memory) → `_drop_unpublished_segments` → `write_plan` → log `recovery: …`. A PlanError from `extend` leaves the plan and every segment file untouched.
   - Crash safety holds: a crash between the drop and the write leaves the old plan with no stale files, so stale files are never reused under new-run indices.
   - `render_step` returns immediately when `publish_next(rows, pub.last) <= epoch.index_at(now)`. It writes nothing, sets `covered=False`, and logs `recovery pending: …`.
3. **Lost plan.** When there is no plan and `pub.last` is set, the run starts at `max(fresh, (last+1)*441)` with `run_start=True`.
   - Every fresh run (`run_start=True`: first start, lost plan, recovery) drops local segments with index > `pub.last` before the plan is written.
   - With `pub.last=None`, that is every local segment, all of them unpublished. This is a slight widening of the ruling, which named only the lost-plan case. It closes the same reuse hole when the plan is lost before anything is published.

## Tests (test_pipeline.py: 13 → 19)
- New:
  - `test_render_step_replans_when_planned_frames_change`: plans at 0.75 s, renders at 1.0. It asserts `replanned == [rows[0].slug]`, that the victim is not encoded, that the new row 0 is `run_start` at the same frame, that segments are written with the new key, and that the log contains `plan-changed` and `frame count`.
  - `test_plan_step_recovery_with_nothing_eligible_touches_nothing`: PlanError; the plan and segment bytes are unchanged.
  - `test_render_step_writes_nothing_while_recovery_is_pending`: `written == []`, `covered` is False, files and plan unchanged.
  - `test_plan_step_without_a_plan_resumes_after_published_keys`: the reviewer's case, fresh 1003 / last 1019. The run starts at 1020×441, only segments ≤ last remain, and render begins at last+1 with the new show's frame 0.
  - `test_plan_step_without_a_plan_after_old_published_keys_starts_fresh`: an old `last` keeps the fresh start.
  - `test_render_step_refuses_without_marker`: StationRootError; no segments written; the plan is unchanged.
- Gaps closed:
  - The drift test asserts the encode is unlinked.
  - The recovery test asserts that segment `last` survives.
  - The encode-failure test asserts the replacement starts at the victim's start frame.

## TDD evidence
- RED (`./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_pipeline.py -q -p no:cacheprovider`): 4 failed, 15 passed. The four failures:
  - `FrameCountDrift: band-2005-11-03: encoded 13008 frames, plan says 12986` (item 1)
  - The seg-file dict lost 1034.aac and others (item 2a)
  - `[1034, 1035, …] == []` (28 written; item 2b)
  - `442323 == (1019+1)*441` (item 3)
  The item-4 gap assertions pass on the old code, as expected, since they pin existing behaviour.
- GREEN: 19 passed.
- Mutation check (scratch copies, PYTHONPATH-shadowed, `__file__` verified in the copy). For each mutant I named the test I expected to fail before running it, and every mutant failed exactly the predicted tests:
  - c (no planned-frames check) → `replans_when_planned_frames_change`
  - d (drop before extend) → `recovery_with_nothing_eligible_touches_nothing`
  - e (no recovery-pending return) → `writes_nothing_while_recovery_is_pending`
  - f (no `max(fresh, last+1)`) → `without_a_plan_resumes_after_published_keys`
  - g (no drift unlink) → `frame_count_drift_is_fatal`
  - h (no drop on a new run) → `recovers_after_an_outage` + `without_a_plan_resumes_after_published_keys`

## Commands and results
- `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`: 174 passed.
- `./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q -p no:cacheprovider`: 174 passed.
- `packages/transmitter/scripts/test-in-debian12.sh` (background, output in this task's log): `ffmpeg version 5.1.9-0+deb12u1`, `Python 3.11.2`, 174 passed.
- `./.venv/bin/python -m pytest -q -p no:cacheprovider` (full repo): 2323 passed, 7 deselected.

## Concerns (minor)
- Per the ruling, a frame-count model change *excludes* the first stale row's show rather than re-planning the same show in place. That show is absent from the kept rows, so it is chosen first at the next extension anyway. Re-planning it in place, by not adding it to `excluded` for this reason only, would be gentler. That is a one-line change if you want it.
- These reviewer minors were not addressed because they were not ruled: #2 (no negative memo for failing shows), #6 (stale seg `.tmp` files), and #7 (helpers imports pipeline at top).
