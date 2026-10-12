### Verdicts (task11-fix1, ad6ef13..1d99568)
- Important 1 (the re-batch range reaches high_water): ADDRESSED. publish.py:257-262 sets `end = max(nxt + batch_segments, high_water + 1)`. When high_water == last, as after every successful batch, this is the plain batch size. After a new run above hw, `nxt` is already ≥ hw+1, so the range does not change.
  - **Probe** (scratch copy of 1d99568, sentinel-proven shadowing, isolated pycache): I re-ran my wedge probe (crash at batch=10, then batch_segments=5). Tick 0 landed horizon (100, 109) with last=109. Tick 1 was a normal 5-segment batch (110-114). There was no "horizon held".
  - **Pinned by:** test_publish.py `test_a_lowered_batch_size_after_a_crash_still_reaches_the_high_water_mark`. The implementer's mutant I1 was killed.
- Minor 1 (recovery decided on listed): ADDRESSED. pipeline.py:138-152 uses `due = publish_next(rows, listed)` in both the floor guard and the recovery branch.
  - **None-safety:** the `nxt is None` check short-circuits, and when rows exist `due` is not None.
  - **No deadlock:** render_step still refuses while last+1 ≤ now_n, but either the publisher re-sends the files in (last, hw], which are kept on disk, or time passes until due ≤ now_n and normal recovery runs.
  - **Coverage of the replaced test is preserved.** Its scenario (hw beyond now) correctly no longer recovers, and the new `test_plan_step_does_not_recover_while_r2_may_list_past_now` pins that: no cut, no run_start, files untouched, no recovery log. Mutant M1 (`due = nxt`) was killed. `test_plan_step_recovery_cuts_at_the_high_water_mark` still pins the cut at listed when hw ≤ now. `test_plan_step_without_a_plan_resumes_after_the_high_water_mark` still pins the lost-plan floor.
- Minor 2 (guard cache only at 0 ≤ age < interval): ADDRESSED at publish.py:128. `test_a_clock_stepped_backwards_rereads_the_guard` would fail without the fix: a cached `blocked:false` with negative age would be trusted and the batch would publish.
- Minor 5 (non-string briefing.file means unreadable): ADDRESSED at site.py:86-89. The test is parametrised over 5, a list, a dict and True. Falsy values still fall back to "briefing.md", which is acceptable.

### New issues
- Critical: none. Important: none.
- Minor: pipeline.py:141-145. The `listed + 1` floor is now a no-op whenever the recovery branch is taken. Recovery requires due ≤ now_n, and due ≥ listed+1, so listed+1 ≤ now_n < fresh. The floor only takes effect in the lost-plan branch, where it is tested. This is harmless and defensive. The comment above it could say so, or the floor could move into the `nxt is None` branch. No action required.

### Out of scope
- None beyond the deferred concerns (a) and (c).

Verdict: Approved
