# task11-fix1 handback

**Status: DONE.** All four ruled fixes are in one commit, `1d99568`.

**Fixes**
- **Important 1** (`publish.py`): the re-send range now runs to `max(nxt + batch_segments, high_water + 1)`. Lowering `batch_segments` after a crash can no longer hold the horizon forever.
  - Test `test_a_lowered_batch_size_after_a_crash_still_reaches_the_high_water_mark`: crash at batch=10, lower it to 5. One batch lands the horizon at (100, 109); the next batch is back to 5 segments.
- **Minor 1** (`pipeline.py`): recovery is now decided on `due = publish_next(rows, max(last, high_water)) <= now_n`. The log line names `due`.
  - I replaced my earlier test `test_plan_step_recovery_never_restarts_below_the_high_water_mark`, because that scenario no longer recovers.
  - New test `test_plan_step_does_not_recover_while_r2_may_list_past_now` shows no cut, no new run, segment files untouched and no recovery log.
  - `test_plan_step_recovery_cuts_at_the_high_water_mark` (high-water mark already past) still passes.
- **Minor 2** (`publish.py`): the guard cache is trusted only when `0 <= now_s - checked_at < interval_s`.
  - Test `test_a_clock_stepped_backwards_rereads_the_guard`: with the clock an hour back, the tripped guard is re-read and publishing stops ("guard"); 2 GETs.
- **Minor 5** (`site.py`): a non-string `briefing.file` now returns `(manifest, None)`.
  - Test is parametrised over 5, a list, a dict and True.

**Commands**
- `./.venv/bin/python -m pytest -q -p no:cacheprovider` (3.14, whole repo): **2379 passed**
- `./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q -p no:cacheprovider` (3.11): **230 passed**
- `transmitter.__file__` resolves inside the worktree.

**Mutants** (scratch `git archive` copies of HEAD; separate cleared PYTHONPYCACHEPREFIX; sentinel asserted that `transmitter.MUTANT_SENTINEL == "copy"` and that helpers loaded from the copy). Both predictions matched exactly:
- **I1**, batch range ignores the high-water mark: predicted red was only the lowered-batch test. Observed exactly that test; 229 passed.
- **M1**, `due = nxt`: predicted red was only `test_plan_step_does_not_recover_while_r2_may_list_past_now`. Observed exactly that test; 229 passed.

**Note:** `render_step` still refuses while `last + 1 <= now_n` (concern (c), deferred). In the Minor 1 case, publish re-sends up to the high-water mark on the next tick, and rendering then resumes.
