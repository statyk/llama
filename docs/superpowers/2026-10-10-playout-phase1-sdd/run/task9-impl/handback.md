# Task 9 handback (task9-impl): DONE_WITH_CONCERNS (minor)

## What I implemented
Commit `f405b7a` on playout-phase1, on top of 2309c67. The diff is the only change in it.
- `packages/transmitter/src/transmitter/pipeline.py` (new): copied verbatim from the brief's Step 3. It contains `Engine` protocol, `FfmpegEngine`, `Station`
  (scan_now, gap_frames, pause_samples, lead_us, start_margin_segments, until_frame, frames_of, extend),
  `plan_step`, `RenderReport`, `render_step`, `_gc_encodes`, `_drop_unpublished_segments`. The catch order is
  as the brief has it: `except FrameCountDrift: raise` comes before `except TransmitterError`. All of its imports are used.
- `packages/transmitter/tests_transmitter/helpers.py`: adds `E`, `NOW`, `FakeEngine`, `make_station`. All new imports
  are at module top, including `from transmitter.pipeline import Station`, which the brief had imported lazily inside
  `make_station`. I also added the return annotation `-> tuple[Station, list[str]]`.
- `packages/transmitter/tests_transmitter/test_pipeline.py` (new): the brief's 13 tests, unchanged.

## Epoch ruling (I1)
`E = 4_000_000_000 * 1_000_000` (2096-10-02T07:06:40Z, on a whole second). I rewrote the comment to explain why E sits in
the far future: test packages have real-clock mtimes, while the quiet check runs at the simulated NOW. `NOW = E + 1000*D_US`
is derived from E. No test hard-codes a value derived from E (every test uses NOW, `st.epoch.index_at` or
offsets from it), so nothing else needed changing.

## Tests
- RED: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_pipeline.py -q` gave a collection error,
  `E ModuleNotFoundError: No module named 'transmitter.pipeline'` (helpers.py:25). The brief expects exactly this, since the
  module didn't exist yet.
- GREEN: test_pipeline.py has 13 passed.
- Transmitter suite on py3.14 (`./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q -p no:cacheprovider`): 168 passed.
- Transmitter suite on py3.11 (`./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q -p no:cacheprovider`, 3.11.15): 168 passed.
  Both venvs import transmitter from this worktree (I checked `transmitter.__file__`).
- Debian 12 gate (`packages/transmitter/scripts/test-in-debian12.sh`): `ffmpeg version 5.1.9-0+deb12u1`, `Python 3.11.2`,
  168 passed, rc 0.
- Full repo suite (`./.venv/bin/python -m pytest -q -p no:cacheprovider`): 2317 passed, 7 deselected, 26 warnings.
- 168 is 155 existing tests plus 13 new ones. The pre-flight figure of "192" was presumably a count over more of the plan.

## Mutation check (scratch copies under scratchpad, PYTHONPATH-shadowed, `__file__` verified to be in the copy)
For each mutant I named the test I expected to fail before running it.
- (a) Removed `except FrameCountDrift: raise`. Predicted failure: test_frame_count_drift_is_fatal. It failed; 12 others passed.
- (b) Changed `show is None or show.key != r.key` to `show is None` (plan focus #2). Predicted failure:
  test_render_step_replans_a_changed_package. It failed; 12 others passed.
- Focus #1 (NFS down) is covered by test_plan_step_refuses_without_marker_and_keeps_plan, which passes. In plan_step,
  scan_now runs before anything reads or writes the plan.

## Self-review
- render_step re-validates a show only when its encode is missing. After a re-plan it continues without advancing n, so
  the same segment is rebuilt against the new rows. If the missing-encode row started before segment n, it raises LayoutError
  before scanning or writing anything (test checks that the plan is unchanged and the segment is not written).
- A failed encode never leaves a file behind. On drift the pipeline unlinks the encode, and render_show already does the same.
- `_gc_encodes` keeps the key of every row whose end_frame is past next_n*F (a cut row's end_frame is its cut_frame).
  It removes `.*.tmp` files only when their mtime is more than an hour old.

## Concerns (minor, none blocking)
1. If the re-plan has no eligible show left (for example a one-package station whose only package changed), `extend`
   raises `PlanError("no eligible packages to plan")` out of render_step. That is the brief's behaviour, and as a loud
   failure it is arguably correct, but no test covers it. Task 12/daemon wiring should treat it as an alert.
2. Exclusion only lasts for one render_step call. A re-voiced package that becomes eligible again with a new key can be
   planned on a later extension. As far as I can tell this is intended.
3. A process slip, now cleaned up: my first Debian-gate invocation ran in the foreground and wrote its stdout to
   `<worktree>/scratch-deb.out` and its rc to `$D/task9-deb.rc`, which are outside the task directory. The run finished
   in under 2 minutes and passed. I appended its output to task9-impl.log, deleted both stray files, and neither was committed.
   I also deleted the `full.rc` poll file after use.

## Files
- /Users/shawn/projects/llama/.claude/worktrees/playout-phase1/packages/transmitter/src/transmitter/pipeline.py
- /Users/shawn/projects/llama/.claude/worktrees/playout-phase1/packages/transmitter/tests_transmitter/helpers.py
- /Users/shawn/projects/llama/.claude/worktrees/playout-phase1/packages/transmitter/tests_transmitter/test_pipeline.py
