### Spec Compliance

**Compliant.** render.py (9fc3c57) and test_render.py match the Task 8 brief's listings verbatim. The planner follow-ups in 48565c9 do what the orchestrator ruled. Nothing is missing, nothing extra was added, and nothing is misunderstood.

- **Joins.** `show_layout` (render.py:41-51) adds `pause_samples` only when either neighbour is a clip, so track→track inserts no silence, and clip↔track and clip↔clip both get the pause (the clip↔clip pause is a sanctioned addition). It pads to a whole frame with `pad_to_frame`. `test_layout_joins` pins this: [0,107,1107,2114], content 2164, padded 3072.
- **Frame arithmetic.** render_show writes `start_sample - pos` of silence before each file and `padded - pos` after the last one. Total samples written therefore equal `layout.padded_samples` exactly, and `expected = frames_for(padded, extra)` is the same value `planned_frames` returns for the same settings. The plan's Engine builds both from one `RenderSettings`, so the two cannot diverge on the pause count. I checked `samples_for_seconds` (round(0.75 × 44100) = 33075, exact). Its only other users are spike.py's dev tool.
- **Gain.** `file_gain` (render.py:71-76) gives clips `gain_db(speech_target, f.i_lufs, f.tp_dbfs)` and tracks `gain_db(music_target, tracks_i_lufs, tracks_tp_dbfs)`, so music is measured over tracks only. I checked analysis.gain_db: it computes min(target − I, −1 − TP), and an unmeasurable I gives unity gain. The result is linear. The clamp `np.clip(pcm * gain, -1, 1)` builds a new array, which is safe because `iter_decode` yields read-only `np.frombuffer` views (checked audio.py:55). It is the sanctioned clamp-not-limiter deviation.
- **Changed package.** Two checks catch it:
  - A key or path-list mismatch raises `RenderError("does not match")` before the encoder exists, so no ffmpeg process or temp file is created.
  - If a file decodes to a different count than its analysis, `RenderError("... the package changed")` is raised per file inside the try. The check runs before `pos` advances, so a negative silence write can never mask it.
- **Encoder lifecycle.** I checked `AacFileEncoder`:
  - On success, `close()` is called explicitly.
  - Any exception, including one raised inside `close()`, goes to `except BaseException: enc.abort(); raise`. `abort()` kills ffmpeg and unlinks the tmp, and it is a no-op after `close()` has already cleaned up on a non-zero exit.
  - The drift test and the changed-package test both assert that neither the output nor `.x.aac.*` is left behind.
  - When an exception escapes mid-iteration, the abandoned `iter_decode` generator is released by the except-handler's stack unwind, and its `finally` kills the decoder.
- **FrameCountDrift.** The frame count comes from `len(frame_offsets(...)) - 1` (frame_offsets appends a final len(buf) entry; checked adts.py:39-49). On a mismatch the output is unlinked and `FrameCountDrift` is raised. Both error types are `TransmitterError` subclasses.
- **Task 6 follow-ups (48565c9):**
  - `read_plan` routes every non-blank line through `_parse_row` and turns ValueError/TypeError into `PlanError(f"{path}: line {i}: …")`. This covers invalid JSON (JSONDecodeError is a ValueError), a non-dict line, missing fields (`cls(**data)` raises TypeError; checked layout.py:41-42, `from_json` does not coerce), and wrong types: int fields reject bool, run_start must be bool, cut_frame must be int or None. A corrupt plan is never read as empty, and a missing file still returns `[]`.
  - The boundary test's arithmetic checks out: 10F+1000 = 5410, plus a gap of 323 gives 5733 = 13·441, and `published_last=12` puts the boundary at 13F. The `>=` drop at planner.py:89 is pinned, and the implementer reports that a mutant changing `>=` to `>` was killed.
  - `extend` raises `PlanError` for `frames <= 0` inside the per-show try, so the show goes through `on_skip`. The test asserts `("bravo", PlanError)`.

### Strengths
- The layout is a pure function and the encode follows it exactly. Writing silence as `start_sample - pos` makes "planned == written" hold by construction rather than by a parallel computation.
- Each failure path's cleanup is asserted on disk (no output, no temp), not just inferred.
- The integration test is real. A phase-continuous sine split at an odd sample (130001) across two MP3s checks the gapless decode end-to-end. It uses a 24 kHz mono clip to exercise resampling against the analysis sample count, and it checks the clip→track pause as true silence. It passed on ffmpeg 8.1 and on the Debian 12 / ffmpeg 5.1 gate.
- The `_parse_row` type checks close the bool-is-int hole and the from_json no-coercion hole. The comment at read_plan states why: a plan read as empty would mean restarting over immutable published keys.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **The frame count is checked after the encode is already at its final path** (render.py:97-103; plan-mandated). `AacFileEncoder.close()` does the `os.replace` to `out_path` before `frame_offsets` runs. Two cases leave an unverified encode at the path that `FrameStore.has()` treats as "rendered" (plan line 2400-2401):
   - The process is killed in that window.
   - `frame_offsets` raises `AdtsError` on a malformed output. That path does not unlink.

   This is not a silent bad publish: `FrameStore.build_segment` compares `frame_count` against `r.frames` and raises `LayoutError` (plan ~line 2428). The cost is a stuck state needing manual cleanup. The fix is to verify the frame count on the temp file before the rename, which needs a hook in `AacFileEncoder`, or to unlink on any exception after `close()`.
2. **The segue "no dip" assertion is loose** (test_render.py, `rel=0.15` over a 4096-sample RMS window; plan-mandated). The measured ratio is already 0.971. By arithmetic, an inserted gap of about one MP3 granule (576 samples) would cost about 7% RMS and still pass. The structural guard is elsewhere: per-file decoded counts must equal analysis, and the handback measured the tracks summing to exactly 6.0 s. But that sum is not asserted here. Asserting `t1.samples + t2.samples == 6 * 44100`, or taking the minimum short-window RMS across the join, would make the test catch a gap directly.
3. **A changed package is detected only after the whole mismatched file has been decoded and encoded.** This is by design and harmless: the encode is aborted and the work is wasted. Noted only because a much longer replacement file costs a full decode before the refusal.
4. **Note for Task 10, not a defect here.** `FrameCountDrift` subclasses `RenderError` (errors.py, plan-mandated), yet RenderError's docstring says the show is "skipped and re-planned", while drift must be fatal. `render_step` must catch `FrameCountDrift` before any `except RenderError`, or drift will be swallowed as a per-show skip. Its reviewer should check the order.

### Assessment
**Task quality:** Approved
**Reasoning:** render.py follows the plan exactly. The samples written equal the planned frames by construction, the gain and clamp rules match the constraints, and every failure path aborts the encoder and leaves nothing on disk. The Task 6 follow-ups do what was ruled and are pinned by tests. The remaining items are minor hardening (verify before the rename, a tighter segue assertion) plus a catch-order warning for Task 10.
