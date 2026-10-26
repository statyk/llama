### Spec Compliance

**Verdict: compliant, with one gap in a required scenario.** The interfaces match the brief as amended by the controller notes:
- `Station.scan_pieces`, `Station.clock`, the new `Station.extend` (run 1, then analyse, then run 2), `ahead=1`, and a `Recency` rebuilt per appended row from `rows + appended`, with aired rows read once.
- `AiredRow.package` must be `str | None`.
- In `render_step`, re-validation is keyed by `(kind, slug)`, unknown kinds take the skip path, and the re-plan cap raises `PlanError`.
- The shuffle is retired.

Every change to the brief that the implementer made is defensible (see Decisions). The gap: the spec's required scenario "a `show_gap_seconds` change never fails a step" is tested only on the plan_step path. On the render skip path, the implementer's start-frame decision is the only thing that stops a LayoutError wedge, and no test pins it (mutant MA below).

The review ran in three passes: the source diff, the test diff, and mutation plus probes in a scratch copy at 6d16ed9. In the copy, `transmitter.__file__` and `tests_transmitter.__file__` both resolved inside the copy. The baseline was 146 passed.

### Strengths
- **Append-only holds.** `extend` copies `rows` and only appends. The only drop paths are still `replan_from` (render) and `cut_for_recovery` (plan_step), and both are unchanged. `validate_rows(out)` closes the call. The implementer's mutants 1 and 4 are caught by `test_append_only_under_a_clock_edit`, which also compares the plan file's bytes line by line.
- **Exact frames.**
  - A row is written only from an exact piece: from the pool, the learned cache, or `frames_of` with a check that frames > 0.
  - The run-2 fallback is pinned: M11 (`chosen = run2` unconditionally) turns `test_run2_pick_unanalysed_falls_back_to_run1` red.
  - `test_written_rows_always_carry_exact_frames` asserts that the estimates really differ from the exact counts, so the test is not vacuous.
- **The lazy `length_cache()`** rebuilds whenever cache_dir, pause or extra change, which keeps "exact" consistent with `planned_frames`. M9 (no rebuild) turns `test_render_step_replans_when_planned_frames_change` and `test_open_station_lengths_match_what_render_plans_with` red.
- **The Recency per-row rebuild is pinned.** M5 (Recency built once per call) turns `test_multi_row_extend_never_repeats_a_show_or_id_while_alternatives_exist` red: ID rotation repeats.
- **Exclusions reach the re-extend.** M17 (`extend` rescans and ignores the pool it was passed) turns six tests red, among them the changed-clip and skip-path scenarios.
- **Render re-validation is careful.** The cap is computed once and its count is pinned exactly in the test. A vanished or changed clip is excluded; a re-voiced show is re-planned in place. The on-air LayoutError guard comes before the cap. No loop is unbounded: every pass either writes a segment, raises, or increments `replans`, which the cap bounds.
- **`announcement_broken` is right on the main case.** It fires only on a block's first show (`miss is not None`). `PlanRow.from_json` restores `names` as tuples, so `occ in r.names` works on rows read back from disk (checked in `layout.py:87-92`).
- **`"clock"` is in neither `GATED_CODES` nor `LEVEL_CODES`.** It sends at once, and `_resolve` clears an active event code too. Both match the global constraints.
- **Shuffle removal leaves nothing dangling.** There are no remaining callers of `choose_next`, `planner.extend` or `shuffle_rank` in src, tests, scripts or the README.
- **The watchdog is fed** after every projection and every analysis, and the counts are asserted exactly in three tests plus the systemd runner test.
- **The scenario tests use realistic 2–3 h mixed blocks**, not long blocks. The rewritten phase-1 tests still assert real behaviour: eligible shows, keys, no repeats, back to back with the gap.

### Issues

#### Critical
None.

#### Important

**1. The render skip path after a `show_gap_seconds` change is unpinned, and getting it wrong wedges render.** Location: `packages/transmitter/src/transmitter/pipeline.py:322` (`expected = start if not appended else ...`), and `test_scenario_show_gap_seconds_change` in `tests_transmitter/test_pipeline.py`.

- **What:** the implementer's Decision 2 lays the first appended row at the caller's `start_frame`, which on the skip path is the dropped row's own start. That decision is correct, and I verified it. But no test exercises it.
- **Mutant MA:** the guard demands `out[-1].end_frame + gap_frames` for the first non-run-start row. Predicted: survives. Result: **SURVIVED** (155 passed, 1 skipped).
- **Probe in scratch:**
  1. Plan, then render 3 segments.
  2. Shrink the gap from 2.0 s to 0.5 s (87 → 22 frames).
  3. Make a later show fail to encode, then run render.
  - Base code: re-plans, the first new row sits at the victim's start, the later rows use the new gap, and `covered` is true.
  - MA: `LayoutError: scheduler laid row 2 ... at frame 494675; the gap layout puts it at 494610`.
- **Why it matters:** on hugo that LayoutError would recur every tick. Render would stop writing segments and the lead would drain to dead air. This is exactly the spec's "a `show_gap_seconds` change never fails a step". The required scenario test covers only plan_step, where `next_start` already uses the new gap, so it cannot see this.
- **Fix:** add the scenario as a test, essentially the probe:
  - plan with gap A, render a few segments;
  - switch to a smaller gap B and fail a later show's encode;
  - render; assert no error, `new[i].start_frame == victim.start_frame`, `_gap_ok(new[i:], B)`, and covered.

  Then re-run MA and expect that test red. A short comment at line 322 naming the skip-path reason would also help, since the guard reads as tautological otherwise.

#### Minor

**1. Forgetting the learned length on a frame-count mismatch is unpinned** (`pipeline.py:495-498`, Decision 3).
- Mutant M8 deletes `lengths.forget(piece.key)`. Predicted red: `test_one_package_station_replans_in_place_on_a_frame_count_change`. Result: **SURVIVED**.
- In every existing mismatch test the pause or the extra changed, so `length_cache()` rebuilds and `forget` is a no-op.
- The branch matters only when the count changes under an unchanged pause and extra, for example a re-analysis that differs from the stored analysis. Without `forget`, the stale learned count would be re-planned, mismatch again, and exclude the show; a lone show would raise PlanError.
- Fix: one test that changes `FakeEngine.samples_per_file` (not extra or pause) after planning, with the length learned in the same Station.

**2. The `degraded` arm of `_announcement_broken` is unpinned** (`pipeline.py:355`).
- Mutant M1 changes `not (row.miss or row.degraded)` to `not row.miss`. Predicted: survives. Result: **SURVIVED**.
- The spec counts "degrades to open time" as a broken promise.
- Fix: one test with a persisted announcement naming X, where X's first show is on time but degraded (no own-profile shows in the pool).

**3. The gap guard never relates the first appended row to the last persisted row** (`pipeline.py:322`).
- `project` always places piece [0] at `inp.start_frame`, so the check on the first row is tautological; the implementer's Concern 2 says the same.
- A caller passing a wrong `start_frame` that leaves a hole would pass. An overlap is still caught by `validate_rows`.
- Optional: in `plan_step`'s extend branch, assert `start == next_start(rows, gap)`. That path is the only caller where that equality must hold.

**4. A stale config comment** at `packages/transmitter/src/transmitter/config.py:187`: `# seed of the fixed shuffled order` is the `config init` template text. The seed now drives the scheduler's tie-break (`rules.tie_rank`). Reword it, for example "seed of the scheduler's deterministic tie-break".

**5. Redundant ffmpeg probes** (the implementer's Concern 4). `length_cache()` and every `planned_frames` call each probe `aacenc.extra_frames`, which is not cached. That is harmless (one ~8-frame encode per call) but could be memoised per call. It is not a correctness issue.

### Decisions
1. **Lazy `LengthCache` instead of an eager build in `open_station`: accept.** It stays consistent with `planned_frames` under config or encoder changes, publish and status never probe ffmpeg, and M9 pins it.
2. **First appended row at the caller's `start_frame`: accept.** It deviates from the literal gap-layout text but is required by "never fails a step" and "never cut". Laying the row at `prev.end + new_gap` with a smaller gap would put its opening inside already-rendered silence or raise LayoutError, as the probe showed. It needs the test in Important 1.
3. **Forget the learned length on a render-time mismatch: accept.** It keeps phase 1's "re-measured under the current model" behaviour. It is unpinned (Minor 1).
4. **A changed clip is excluded for the rest of the call; a show is re-planned in place; a model change re-plans clips in place: accept.** This matches spec "Re-validation", and mutant 5 is caught.
5. **`"clock"` as an ungated event code, not in `LEVEL_CODES`: accept.**
   - The brief and the global constraints ask only for alert and resolve, and `resolve` clears active event codes.
   - The concern that `status` stops showing an invalid clock is real only for the active-alert list, and it is moot. Task 12's `status_lines` adds a `clock` line read directly via `live_clock(ws, save=False)` (plan line 864); `status` never calls `Station.clock()`.
   - With the default lead of 24 h and low water of 20 h, a fill recurs about every 4 h, which is under the 6 h `repeat_hours`.
   - One consequence worth knowing: a clock that turns invalid is first alerted at the next fill, because `plan_step` returns before `extend` while the plan is covered.
6. **Checking `lengths.length` before calling `frames_of`: accept.** It avoids re-analysis on render's re-extend.
7. **The re-plan cap counts rows overlapping `[n, target]` at the call's first scan: accept.** That is the brief's wording, and the +10 margin covers growth.
8. **The `cli.plan` help-string edit outside the file list: accept.** It is cosmetic and correct.
9. **The render re-extend has no `max_new`, so a skip can trigger several cold analyses (up to about 215 s each) under the plan lock, delaying that tick's publish: accept.**
   - This is phase 1's existing behaviour. Each analysis pings the watchdog.
   - Filling starts only below 20 h of lead, so a delay of tens of minutes is safe.
   - Publish and the plan lock are independent; the delay comes only from the single-threaded tick.

### Assessment
**Task quality:** Needs fixes

**Reasoning:** The implementation is correct on every strict surface I probed:
- append-only, exact frames, the per-row Recency, exclusions into the re-extend, the cap, and clock alert semantics;
- the implementer's four mutants hold, and so do my M5, M9, M11 and M17.

One required scenario, though, is tested only on the path where it cannot fail. The render skip path after a `show_gap_seconds` change is guarded only by an untested decision, and reverting that decision (MA) would wedge render into dead air with the suite green. One added test closes it. Minors 1 and 2 are cheap test additions on the same strict surface and are worth doing in the same pass.

Mutant ledger (scratch copy, the four test files listed below):

| Mutant | Change | Predicted | Result |
|---|---|---|---|
| MA | the guard demands `prev.end + gap` for the first non-run-start row | survives | SURVIVED (Important 1) |
| M1 | the `degraded` arm is dropped from `_announcement_broken` | survives | SURVIVED (Minor 2) |
| M5 | Recency is built once per call | `test_multi_row_extend_never_repeats...` red | CAUGHT |
| M8 | `forget` removed | `test_one_package_station_replans_in_place_on_a_frame_count_change` red | SURVIVED (Minor 1) |
| M9 | `length_cache` never rebuilds | the service rebuild test red | CAUGHT (plus `test_render_step_replans_when_planned_frames_change`) |
| M11 | `chosen = run2` unconditionally | `test_run2_pick_unanalysed_falls_back_to_run1` red | CAUGHT |
| M17 | `extend` rescans and ignores the pool it was passed | `test_render_drops_a_changed_clip...` red | CAUGHT (6 red) |

The test files run against each mutant were `test_pipeline.py`, `test_service.py`, `test_planner.py` and `test_systemd.py`. The mutants and the probe are under `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-scheduler/6a271170-52a3-49a3-b4db-a9d5cd08acfc/scratchpad/t11rev/`, and the log is at `/Users/shawn/projects/llama/.claude/worktrees/scheduler/.superpowers/sdd/scheduler/task11-review/task11-review.log`.
