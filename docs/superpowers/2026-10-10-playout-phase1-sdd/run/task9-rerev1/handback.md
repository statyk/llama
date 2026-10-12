# task9-rerev1: scoped re-review of Task 9 fix round 1 (f405b7a..775f0c1)

**Verdict: Approved.** All four findings are addressed, and the implementer's widening of item 3 is safe. One recommendation follows on the open question; it is not blocking.

Evidence: I re-ran my earlier probes (`test_probe_rev.py`) against a `git archive 775f0c1` scratch copy, PYTHONPATH-shadowed, with `transmitter.__file__` verified inside the copy. All three now fail their old assertions, which means the defects they demonstrated are gone:
- Config change: `DID NOT RAISE FrameCountDrift`. It logs `plan-changed: … planned frame count changed: 13008 now, 12986 in the plan`.
- Deleted plan: the fresh start is segment 1020 = last+1, where it was 1003 ≤ last before.
- Recovery followed by PlanError: the segments above last are still on disk.

Two new probes are described below. Log: `$D/task9-rerev1/task9-rerev1.log`.

## Finding Verdicts

1. **Frame-count model change re-plans: ADDRESSED.**
   - pipeline.py `render_step`: it analyses once, computes `planned = st.planned_frames(analysis)`, and sends any mismatch down the skip/re-plan path with a `plan-changed` reason. That happens before any encode.
   - `FrameCountDrift` is now raised only when an encode disagrees with the current model. It is still caught ahead of `TransmitterError`, and the drifted encode is still unlinked.
   - `Station.planned_frames` is the one function behind both `frames_of` and the render-time check, so planning and validation cannot drift apart.
   - A new probe confirms that an already-encoded row stays frozen and is kept, and that only the first unencoded stale row is re-planned.
   - Test: `test_render_step_replans_when_planned_frames_change`.

2. **Recovery ordering and recovery-pending: ADDRESSED.**
   - `plan_step` now runs cut → `extend` (in memory) → drop (only if `run_start`) → `write_plan` → log. A PlanError therefore leaves both the plan and the segment files untouched (`test_plan_step_recovery_with_nothing_eligible_touches_nothing`).
   - The crash ordering is preserved: the drop still happens before the write.
   - `render_step` returns `covered=False` and writes nothing when `publish_next(...) <= index_at(now)`. This is the same computation as plan_step's recovery condition, so a refused render always pairs with a recovering plan_step in the same tick (Runner gates both on `filling`), and the two cannot deadlock.
   - Test: `test_render_step_writes_nothing_while_recovery_is_pending`.

3. **Lost plan: ADDRESSED. The widening is safe.**
   - In `plan_step`, the `nxt is None` branch now starts at `max(fresh, (pub.last+1)*441)`. That value is always > now_n, so the recovery-pending guard never fires against it, and `render_step` begins at last+1 with the new show's frame 0.
   - On the widening, "every fresh run drops > `pub.last`":
     - The only `run_start=True` paths in `plan_step` are "no plan" and "recovery". With no plan there are no planned segments at all, so every local file above `pub.last` belongs to a lost plan. With `pub.last=None`, nothing is published, so the same holds for all of them. Recovery always dropped above last.
     - `render_step`'s own re-plan can pass `run_start=True` (when re-planning a run's first row), but it never calls the drop, which is correct because the segments before `n` are valid.
     - I found no path where a fresh run in `plan_step` coexists with unpublished segments of a live plan that must be kept.
   - The only case that can reach unpublished-but-planned segments is `publish_next` returning None while rows exist. That needs a plan with no `run_start` row, which `extend` never writes; it would take a hand-edit, and `validate_rows` would then reject the overlap anyway.

4. **Test gaps: ADDRESSED.** Each gap now has an assertion in test_pipeline.py:
   - drift unlinks the encode;
   - recovery keeps segment `last` (`published.read_bytes() == b"p"`);
   - the replacement row starts at the victim's start frame;
   - `test_render_step_refuses_without_marker` checks for StationRootError, no segments, and an unchanged plan.

## Open question: skip vs re-plan in place on a frame-count change

**Recommendation: re-plan in place, with a guard.** The skip is not just less gentle.

I reproduced it in a scratch copy: on a **one-package station**, a `clip_pause_seconds` change makes every `render_step` raise `PlanError: no eligible packages to plan`. The plan is unchanged, and the next tick does the same, so the wedge is permanent. It also happens on a larger station whenever every other package is momentarily ineligible at that boundary. The cause is that `excluded` empties the pool of the only show that would have worked.

The suggested change:
- Do not add the slug to `excluded` for the frame-count reason. `extend` then re-measures the show under the current model and puts it back in its own slot.
- This terminates: the re-planned row's frames come from the same `planned_frames` on a deterministic (and, in production, cached) analysis, so the next iteration matches and encodes.
- As a guard, exclude the slug on a second frame-count mismatch within the same call. That keeps a bounded-loop guarantee even if analysis were ever non-deterministic.

Severity is Minor: production libraries are large, and the trigger is a deliberate operator config change.

## New Issues in the Fix Diff
- None blocking.
- Minor: the open question above is the only behavioural gap I found in the fix.

## Out-of-Scope Observations
- **Same exclusion wedge, pre-existing, not from this fix.** On a one-package station, re-voicing the package (key K1 → K2) also excludes its slug for the call. The re-plan then has an empty pool and PlanError repeats on every tick, even though the new K2 version is eligible. Re-planning in place for "package changed" while the scan holds an eligible new key would fix both cases with the same change. Keep exclusion for `render failed`.
- **For Task 10 (publish), a hazard for the lost-plan start and recovery.** Both now trust local `publish.json` `last` as "nothing above this is listed". If publish ever writes `state/horizon.json` to R2 before persisting `last` locally, a crash in between leaves local `last` behind R2's. Then a lost-plan start or a recovery would re-render under keys that are already listed and CDN-cached (immutable for a year). The publisher must persist `last` before or atomically with the horizon write, or reconcile it on start.
- Earlier unruled Minors are unchanged: #2 negative memo, #6 seg `.tmp` GC, #7 helpers top-level import.

## Verdict
**Approved.** All four ruled findings are addressed with tests that pin them. The implementer reports that each fix's mutant was killed by the predicted test, and my old probes now fail exactly where the defects used to be. I recommend the one-line in-place re-plan with a second-mismatch guard for the frame-count reason. It removes a reproduced permanent wedge on a one-package station after a config change.
