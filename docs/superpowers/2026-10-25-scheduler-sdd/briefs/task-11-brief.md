### Task 11: Pipeline integration (Opus)

**Files:**
- Modify: `packages/transmitter/src/transmitter/pipeline.py` (Station gains `lengths: LengthCache` and a `clock()` method; `scan_pieces`; `extend` replaced; render re-validation), `planner.py` (remove `choose_next`, `extend`, `shuffle_rank` re-export), `service.py` (`open_station` builds the `LengthCache`)
- Test: `test_pipeline.py`, `test_planner.py` (drop shuffle tests), `test_service.py`

**Interfaces:**
- Consumes: Tasks 4-9.
- Produces:
  - `Station.lengths: LengthCache` (built by `service.open_station` and the test `make_station` from `ws.cache_dir` and the station's `pause_samples` and encoder `extra`, as `planned_frames` uses them). No `live` field.
  - `Station.scan_pieces(now_us, *, read_only: bool = False) -> list[Piece]` — station scan + `interstitials.scan(folder, now_s=now_us / 1e6, quiet_s=cfg.station.quiet_minutes * 60)` → `pieces.build_pool(..., read_only=read_only)` (clips analysed via `frames_of` unless `read_only`); each dropped clip is logged `skipping <slug>: <exc>`. Keeps `scan_now` for callers that need packages only.
  - `Station.clock() -> ClockConfig` — `clock.live_clock(ws)` each call (saving the last-good copy); when `problem` is set, `alerts.alert("clock", problem + "; planning with the " + source + " clock")`, else `alerts.resolve("clock")`. Read-only commands (`status`, `schedule`, `announcements`) call `clock.live_clock(ws, save=False)` directly, never `Station.clock()`.
  - `Station.extend(rows, pool: list[Piece], now_us, *, start_frame, run_start, max_new=None) -> list[PlanRow]` — the loop: while the plan is short of `until_frame(now_us)` and under `max_new`: `run1 = project(...)[0]` (no `until_frame`: the continuing occurrence plus two); if `run1.piece` is not exact, `frames_of(run1.piece.show)` (on `TransmitterError` → log `skipping <slug>: <exc>`, drop it from the pool, continue), `lengths.mark_exact`, refresh the piece in the pool; `run2 = project(...)[0]`; append `to_row(run2)` if `run2.piece.exact` else `to_row(run1 with exact frames)`. After each `project` call, `notify("WATCHDOG=1")` when `st.notify` is set. Each appended non-run-start row must start at `prev.end_frame + gap_frames` (else `LayoutError`, an internal-bug guard). When appending a block's first show row, mark `announcement_broken=True` (and log `announcement-broken: <block> <nominal>`) if any persisted announcement row names its occurrence and this row has `miss` or `degraded`. `validate_rows` at the end.
  - `Recency` is rebuilt from the grown rows after every appended row inside `extend`, not once per call: `history.recency(aired, rows + appended, epoch, clock.timezone, meta_of)`, with `aired = history.load_aired(ws)` read once per call and `meta_of` from the pool's show pieces (`(artist, date)` by package slug).
  - `plan_step` uses `scan_pieces` and the new `extend`; recovery and fresh-run logic unchanged. Per Builder calls, pieces are analysed only when chosen and `plan.jsonl` is not trimmed.
  - `render_step` re-validation: pieces keyed by `(kind, slug)` from `scan_pieces`; an interstitial row is valid when its slug is in the clip pool with the same key; a row of any other unknown `kind` is not eligible (the skip path); exclusions apply to both kinds; re-plan cap `len(clip pool) + len(rows overlapping [n, target]) + 10`, exceeding it raises `PlanError("render re-planned <k> times in one call; stopping")`.

- [ ] **Step 1: Failing tests** (`test_pipeline.py`; adapt `make_station` to write a `clock.toml` when a test needs one, otherwise the implicit clock)

```python
def test_written_rows_always_carry_exact_frames(tmp_path): ...   # estimates differ from FakeEngine's exact counts
def test_run2_pick_unanalysed_falls_back_to_run1(tmp_path): ...
def test_at_least_one_row_per_step_while_short(tmp_path): ...
def test_appended_rows_obey_the_gap_layout(tmp_path): ...
def test_multi_row_extend_never_repeats_a_show_or_id_while_alternatives_exist(tmp_path): ...  # empty plan, max_new=None
def test_extend_feeds_the_watchdog_after_each_projection(tmp_path): ...
def test_append_only_under_a_clock_edit(tmp_path):
    # plan with clock A, edit clock.toml to B, plan again: every row of the first plan is unchanged, in place
def test_invalid_clock_alerts_and_plans_with_last_good(tmp_path): ...
def test_render_skips_a_vanished_interstitial_and_moves_on(tmp_path):
    # plan an ID row, delete the clip, render: plan-changed logged, the row dropped with the rest, re-extended, segments written
def test_render_skips_a_row_of_unknown_kind(tmp_path): ...
def test_render_replan_cap(tmp_path): ...
def test_interstitial_rows_are_rendered_from_the_clip_folder(tmp_path): ...
    # also: a clip inside the quiet period (cfg.station.quiet_minutes) is not in the pool and gets no row
def test_announcement_broken_marked_on_the_named_blocks_first_show(tmp_path): ...
```

```python
# required scenarios (spec "Testing"), each its own test in test_pipeline.py:
def test_scenario_clock_edit_mid_fill(tmp_path): ...
def test_scenario_skip_path_drops_an_interstitial_and_a_show(tmp_path): ...
def test_scenario_recovery_after_a_guard_stop_longer_than_the_lead(tmp_path): ...
def test_scenario_show_gap_seconds_change(tmp_path): ...           # old rows keep old gaps; new rows use the new gap; no failure
def test_scenario_phase1_plan_extended(tmp_path): ...
def test_scenario_crash_between_append_and_render(tmp_path): ...    # plan written, render never ran: next tick renders it unchanged
# (the manual-plan-while-rendering scenario is Task 2's lock test)
```

- [ ] **Step 2: Run to verify failure.** Expected: FAIL.
- [ ] **Step 3: Implement.** Existing pipeline tests that assert shuffle order are rewritten to assert scheduler behaviour under the implicit clock (any eligible show, back to back, IDs absent when no folder).
- [ ] **Step 4: Run the transmitter suite.** Expected: all PASS.
- [ ] **Step 5: Mutation check of the strict surface** — on a scratch copy shadowed via `PYTHONPATH` (per the repo CLAUDE.md: never a `.venv/bin/*` script from a copy; run `./.venv/bin/python -B -m pytest …` with `PYTHONDONTWRITEBYTECODE=1`, or a fresh `PYTHONPYCACHEPREFIX` per mutant, so each mutant runs with its own bytecode cache), apply each mutant and name the red test before running it:
  1. `extend` replaces the last persisted row instead of appending → expect `test_append_only_under_a_clock_edit` red.
  2. `extend` writes run 1's estimated frames → expect `test_written_rows_always_carry_exact_frames` red.
  3. gap assertion removed and the scheduler starts a row at `prev.end` → expect `test_appended_rows_obey_the_gap_layout` red.
  4. `extend` drops the last persisted row before appending → expect `test_append_only_under_a_clock_edit` red.
  Record the four results in the task report.
- [ ] **Step 6: Commit**

```bash
git add packages/transmitter/src/transmitter/{pipeline,planner,service}.py packages/transmitter/tests_transmitter/test_{pipeline,planner,service}.py
git commit -m "transmitter: the scheduler drives plan and render; piece-aware re-validation; shuffle retired"
```

---

