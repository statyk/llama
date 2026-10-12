# task9-fix2 — render_step re-plan pool wedge (parked Task 9 ruling)

Where it fits: Task 9 (plan/render steps, `packages/transmitter/src/transmitter/pipeline.py`, `render_step`) is complete and reviewed at 775f0c1. One reviewer Minor was ruled FIX and parked for this round.

## Defect (reproduced by the Task 9 re-reviewer)
In `render_step`, whenever a row's encode is missing and `reason` is set, the slug is added to `excluded` and the re-plan pool is `shows - excluded`. On a ONE-package station (or whenever every other package is momentarily ineligible) the pool is empty, `st.extend` raises `PlanError: no eligible packages to plan`, the plan is unchanged, and the next tick does the same -> permanent wedge. Two triggers:
1. "planned frame count changed" (a config/encoder change such as `clip_pause_seconds`), introduced by task9-fix1.
2. Pre-existing: the package was re-voiced (scan holds the same slug with an eligible NEW key K2 != row key K1) -> "package changed".

## Ruling (orchestrator, binding)
- For reason (1) frame-count change, and for reason (2) when the scan holds the slug with an eligible new key: do NOT add the slug to `excluded`. `extend` re-measures and re-plans the show in place under the current model / new key.
- Bounded-loop guard: if the SAME slug hits a frame-count/package-changed mismatch a SECOND time within one `render_step` call, exclude it then (so non-deterministic analysis can never loop forever).
- Keep excluding immediately for "render failed: ..." and for "no longer eligible" (show absent from scan).
- Keep the existing log line ("plan-changed: skipped <slug> ...") and `report.replanned` behaviour; FrameCountDrift stays fatal and is caught before TransmitterError as now.
- Verify (by test, not reasoning) that after the in-place re-plan the loop terminates and writes the segment from the re-planned row, i.e. the re-planned row for the same slug matches on the next iteration and encodes.

## Tests required (in packages/transmitter/tests_transmitter/test_pipeline.py)
- One-package station + frame-count change (e.g. clip_pause_seconds changed after planning): render_step does NOT raise PlanError; it re-plans the show and writes segments; plan rows carry the new frame count.
- One-package station + re-voice (key K1 -> K2, still eligible): same — no PlanError, the row is re-planned under K2 and rendered.
- Guard: a show whose planned frame count changes on every analysis (monkeypatched non-deterministic `planned_frames`/analysis) is excluded on its second mismatch in the call (with another show available it falls through to that show; with none, PlanError — assert whichever the code does, bounded, no infinite loop).
- "render failed" still excludes on the first failure (existing test should already pin it; confirm).
The re-reviewer's scratch probe that reproduced the wedge (from the Task 9 review, written against 775f0c1) is at `.superpowers/sdd/2026-10-10-playout-phase1/task9-fix2-reviewer-probe.py` — read it for a ready-made one-package fixture setup; adapt, don't copy it in wholesale.

## Constraints
- Python must stay 3.11-compatible. transmitter must import neither llama nor emcee. All tests offline and deterministic.
- Run: `./.venv/bin/python -m pytest -q` (full repo, 3.14) AND `./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q -p no:cacheprovider` (3.11). Confirm `./.venv/bin/python -c "import transmitter; print(transmitter.__file__)"` resolves inside the worktree.
- This task touches no ffmpeg code path; the Debian-12 gate is NOT required for it.
- Mutation check (scratch copy only, mandate 5): name the expected red test, then revert the "don't exclude" change in a scratch copy and confirm the one-package tests go red with PlanError. Use `python -m pytest` from the copy with PYTHONPATH shadowing and prove the shadowing with a sentinel.
