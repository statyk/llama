# task9-fix2 handback

Status: DONE

Commit: 98ae05a fix(transmitter): re-plan a re-voiced or re-measured show in place, not excluded

What changed (packages/transmitter/src/transmitter/pipeline.py, render_step):
- Split the old "package changed or is no longer eligible" reason: slug absent from scan -> "no longer eligible", excluded at once; slug present under a new key -> "package changed", re-planned in place.
- "planned frame count changed" re-plans in place (extend re-measures under the current model / new key).
- Bounded guard: a per-call `mismatched` set; a second package-changed/frame-count mismatch for the same slug in one call excludes it.
- "render failed" and "no longer eligible" still exclude on the first hit. Log line, report.replanned, FrameCountDrift-before-TransmitterError unchanged. Module docstring updated.

Tests (packages/transmitter/tests_transmitter/test_pipeline.py):
- New: test_one_package_station_replans_in_place_on_a_frame_count_change, test_one_package_station_replans_in_place_after_a_revoice (both red with PlanError before the fix; assert re-planned row same slug/start, new frames / key K2, segments written from it, first segment's payload is the new key), test_a_show_mismatching_twice_in_one_call_is_excluded (3 pkgs: replanned == [victim, victim], falls through to another show, segments written), test_a_lone_show_mismatching_twice_in_one_call_is_a_plan_error (1 pkg: PlanError, exactly one plan-changed log, nothing encoded), test_render_step_excludes_a_package_no_longer_eligible (broadcast.m3u removed -> excluded on first hit).
- UPDATED (they pinned the old exclusion, contradicting the ruling): test_render_step_replans_a_changed_package now asserts same slug re-planned under K2 and encoded; test_render_step_replans_when_planned_frames_change now asserts same slug with the new frame count, encoded.
- "render failed" excluding on first failure: confirmed pinned by existing test_render_step_skips_a_show_that_fails_to_encode (replanned == [victim], slug differs); passes unchanged.

Commands:
- ./.venv/bin/python -m pytest -q -p no:cacheprovider -> 2328 passed, 7 deselected
- ./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q -p no:cacheprovider -> 179 passed
- transmitter.__file__ resolves inside the worktree (both venvs).

Mutation (scratch copies via git archive HEAD under scratchpad, run from an empty cwd with `.venv/bin/python -m pytest`, PYTHONPATH shadowing, PYTHONDONTWRITEBYTECODE=1; sentinel MUTANT_SENTINEL appended to the mutant pipeline.py, `import transmitter.pipeline` printed the scratch path + sentinel):
- M1 (revert to unconditional exclude). Predicted red: both one-package tests with PlanError. Observed: both red with "PlanError: no eligible packages to plan", plus the 2 updated tests and both guard tests -> 6 failed, 18 passed.
- M2 (remove guard: never exclude on mismatch). Predicted: both guard tests hang. Observed: both killed by a 20 s alarm (rc 142); control test passed. Note: a guard regression shows as a HANG, not a failure (no pytest-timeout in the suite).

Concerns: none blocking. A lone show whose measurement never settles still PlanErrors every tick (by design per ruling; bounded within a call).
