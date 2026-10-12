### Spec Compliance

Scope reviewed: diff 9fc3c57..f405b7a (2309c67 Task 8 follow-ups + f405b7a Task 9). `pipeline.py` and `test_pipeline.py` match the brief's Step 3 and Step 1 verbatim, apart from the rulings applied: E is now 4e9 s, and `except FrameCountDrift: raise` sits before `except TransmitterError` at pipeline.py:235-238. One small deviation: helpers.py imports `Station` at module top where the brief had a lazy import.

- **Focus #1 (NFS down): satisfied.** `plan_step` calls `scan_now` first (pipeline.py:141), before the plan is read or written, and `test_plan_step_refuses_without_marker_and_keeps_plan` pins this. `render_step` also gets `StationRootError` from `scan_now` (pipeline.py:224) before any re-plan, so it never re-plans into an empty library. That path has no test (Minor).
- **Focus #2 (re-voiced between plan and render): satisfied.** A missing encode triggers the scan-key check (pipeline.py:227). On a mismatch it calls `replan_from` at the row's own start frame, and no encode happens. The implementer's key-check mutant was killed by `test_render_step_replans_a_changed_package`.
- **Task 8 follow-ups: correct.** render.py:107-115 unlinks `out_path` on any failure after `close()` and re-raises, so error types are unchanged. render.py is the only post-close caller of `adts.frame_offsets` (I grepped), so the monkeypatch test exercises the intended path. The implementer's RED result ("encode left at x.aac") confirms this. The segue assertion `t1.samples + t2.samples == 6*44_100` is present.
- **Missing (spec "Frozen means rendered": "everything after the render frontier is re-planned on any config or library change"):** a config change that alters frame counts makes the station fail permanently instead of re-planning. See Important #1.

### Strengths
- Recovery runs in a crash-safe order. Unpublished segments are dropped before the cut plan is written, so a crash in between leaves the old plan plus no stale files. The opposite order would let stale old-plan files be reused under the new run's indices.
- Rows passed to `build_segment` are always validated: by `read_plan`, by `extend` (validate_rows), or as slices of validated rows. `n` is always ≥ the current run start and > `pub.last`, and the end-of-plan precheck (pipeline.py:211) runs before `build_segment`. **(c) No.** Nothing here calls `build_segment` with unvalidated rows or with `n < first`.
- The on-air guard (`r.start_frame < n·441` with the encode missing → LayoutError before any scan or write) does what the operator rule needs, and its test checks that the plan is unchanged and the segment was not written.
- Encode GC keeps every key with a row ending after the render frontier. A cut row's `end_frame` is its `cut_frame`, which is correct. Temp files are matched by mkstemp's real names (`.{name}.XXXX.tmp`, checked in aacenc.py:61 and workspace.py:23). The 1 h mtime guard is safe because an in-flight encode keeps updating its mtime.
- The E time-bomb fix is correct and its comment explains it.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)

1. **A config change that alters frame counts makes the station fail on every tick (plan-mandated).** pipeline.py:231-234 compares the encode's frame count with `r.frames`, which was computed at plan time. If the operator changes `[render] clip_pause_seconds`, the planned frame counts change. The same happens if an ffmpeg upgrade changes `aacenc.extra_frames`. After the restart, `render_show`'s own check passes, because it uses the new settings. The pipeline check then fails and raises the fatal `FrameCountDrift` for a model failure that never happened.
   - **Reproduced** in a scratch copy: plan with the default 0.75 s, then render with a Station whose `clip_pause_seconds = 1.0`. `FrameCountDrift` is raised on every call and the plan stays unchanged.
   - In the plan's Task 12 `Runner`, this latches `halted` "until restart". The restart hits the same row, so the station drains its lead and goes to fallback. Each attempt also wastes a full encode first.
   - The obvious operator remedy, deleting plan.jsonl, leads into Minor #3.
   - The spec says config changes are re-planned after the render frontier.
   - **Fix:** before encoding, compare `st.frames_of(show)` with `r.frames`. This is cheap because the analysis is cached. On a mismatch, treat the row like a changed package: skip it at its boundary and log `plan-changed`. Keep `FrameCountDrift` for an encode that disagrees with the current model, which `render_show` already raises.

#### Minor (Nice to Have)

1. **Named risk (a): recovery drop, then PlanError.**
   - What holds: with every package momentarily ineligible, the plan is not rewritten, only segments > `pub.last` are dropped, and the next tick repeats the recovery. The drop is idempotent, and nothing published is lost or deleted.
   - **Reproduced** what goes wrong: the plan's Task 12 `Runner._step` runs render even after plan fails. `render_step` then works off the un-cut plan from `n = last+1`, which is already past due. In the probe it re-rendered 28 old-plan segments (1034..1061) while `now_n` was 2054.
   - Publish would upload these past segments in the same tick: wasted PUTs, bounded by the batch size and the old plan's tail, and self-limiting. If the spanning row's encode was already GC'd (the R2-outage variant, where render ran far ahead of publish), it instead raises a misleading "already on air … refusing to re-plan" LayoutError on every tick.
   - Nothing is listed that does not exist, and recovery itself makes the only cut.
   - **Fix:** in the recovery branch, compute `cut_for_recovery` + `extend` first, then drop, then `write_plan`. This keeps the crash ordering, and a PlanError then touches nothing. Optionally, `render_step` could refuse when `publish_next(...) <= index_at(now)` (recovery pending).
2. **Named risk (b): no negative memo.** This costs CPU and log noise only, with no on-air effect.
   - A show that fails analysis is retried first on every `extend` call, because its `last_seq` is -1. Each retry costs a full decode in `load_or_analyze`, since failures are not cached.
   - A show that analyses but fails to encode gets planned again at every extension, fails again at its boundary, and is replaced. That is one wasted (possibly near-complete) encode per extension, and every replacement happens before air.
   - Bounded to one attempt per extend/render call. A memo keyed by `show.key` would be safe, because a fixed package gets a new key.
3. **Plan missing while `publish.json` exists → the fresh run starts under published keys.** pipeline.py:147-148 starts at `now_n + margin` without consulting `pub.last`.
   - **Reproduced:** fresh run at segment 1003 with published `last` = 1019. `render_step` then skipped the existing old-plan files 1020+ (`path.exists()`), which publish would upload under the new plan.
   - The new plan's first show then airs from mid-way, (last+1−1003) segments in, right after old-plan content, so a show is cut into mid-song. The timeline would also disagree with the audio.
   - This needs an operator to delete plan.jsonl, but that is the natural remedy for Important #1.
   - **Fix:** when `rows` is empty and `pub.last` is set, drop segments > last and start at `max(fresh, (last+1)·441)`.
4. **Named risk (d): untested PlanError when no eligible show remains for a render-time re-plan.**
   - The behaviour is acceptable: the plan is unwritten, segments before the boundary are already written, the frontier stalls, and the lead drains to fallback. Nothing invalid is listed and nothing is cut mid-show.
   - Two gaps: no test pins it, and in the encode-failure variant the doomed encode is redone every tick.
5. **Test gaps a mutant would survive:**
   - `test_frame_count_drift_is_fatal` does not assert that the drifted encode is unlinked (pipeline.py:233). Removing that line leaves a frozen bad encode, which would only be caught later by `build_segment`'s LayoutError.
   - The recovery test does not assert that segments ≤ `last` survive the drop.
   - The encode-failure test does not assert that the replacement row starts at the victim's start frame.
   - No `render_step` + `StationRootError` test.
6. **Stale `.N.aac.XXXX.tmp` files in `render/seg/<epoch>/`** from a crash mid-`atomic_write_bytes` are never collected. `_gc_encodes` covers only `render/shows`. The files are small and the case is rare.
7. **helpers.py now imports `transmitter.pipeline` at module top** (the brief imported it lazily). An import error in pipeline.py will now fail collection of every transmitter test module, not just test_pipeline. Harmless today.

### Assessment
**Task quality:** Needs fixes
**Reasoning:** The implementation matches the brief, both plan-review focus items are met, and the Task 8 follow-ups are correct. However, an ordinary config change (`clip_pause_seconds`) produces a permanent fatal `FrameCountDrift` instead of the spec's re-plan after the render frontier. This defect is plan-mandated and was reproduced in a scratch copy. Its fix is small: compare planned frames before encoding and re-plan on a mismatch.

Probe tests (scratch copy only, PYTHONPATH-shadowed, `__file__` verified in the copy): `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-playout-phase1/1e18c958-066d-4cae-ae48-e032d3e8aa40/scratchpad/t9rev/tree/packages/transmitter/tests_transmitter/test_probe_rev.py` (3 passed, each confirming the stated behaviour). Log: `$D/task9-rev/task9-rev.log`.
