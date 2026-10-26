# Task 11 handback: pipeline integration (task11-impl)

**Status: DONE.** Branch `playout-scheduler`. Two commits on top of f28dbd0, both green, tree clean:
- `af274f3`: `AiredRow.from_json` now requires `package` to be `str | None` (the Task 7 deferred minor), with bad shapes added to `test_unusable_rows_are_skipped_not_loaded`. Also test helpers: `make_station(clock=, lead_hours=, quiet_minutes=, packages=, ids=)`, `add_clip`, `write_clock`, `FakeEngine(clip_samples=)`, `build_package(artist=, date=)`.
- `6d16ed9`: the scheduler drives plan and render, re-validation knows about pieces, and the shuffle planner is retired.

Test command (every commit): `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q` → **827 passed, 1 skipped** (the baseline was 807 passed, 1 skipped).

## What was implemented
- `Station.lengths: LengthCache | None` plus `Station.length_cache()`. The cache is built from `ws.cache_dir`, `pause_samples` and `engine.extra_frames()`, the same inputs `planned_frames` uses. It is rebuilt whenever any of those changes.
- `Station.scan_pieces(now_us, *, read_only=False)` does the station scan plus `interstitials.scan(folder, now_s, quiet_s=quiet_minutes*60)` and passes the result to `build_pool`. Clips are analysed through `frames_of` unless `read_only`. Each dropped clip is logged as `skipping <slug>: <exc>`. `scan_now` is kept.
- `Station.clock()` calls `live_clock(ws)` on every call. When the clock has a problem it raises `alerts.alert("clock", <condensed problem> + "; planning with the <source> clock")`; otherwise it calls `alerts.resolve("clock")`. `condense_clock_problem` turns pydantic's message into one line: it drops the errors.pydantic.dev lines and the `[type=...]` tails, joins the rest with `; `, and caps the result at 300 characters. The first line still names the file.
- `Station.extend(rows, pool, now_us, *, start_frame, run_start, max_new=None)`. Per row:
  - Rebuild `Recency` from `rows + appended`. `aired` is read once per call, and `meta_of` comes from the pool's show pieces.
  - Run 1 is `project(inp, ahead=1)[0]`, followed by a watchdog ping.
  - If run 1's piece is an estimate: first check whether the `LengthCache` already learned it. Otherwise call `frames_of`; on `TransmitterError` or ≤0 frames, log `skipping <slug>: <exc>`, drop the piece from the pool and continue. Then `mark_exact`, refresh the piece in the pool, and run 2 (followed by a ping). Append run 2's pick if its piece is exact, else run 1 with the exact piece.
  - Guard: the first appended row must start at `start_frame`, and each later one at `prev.end + gap_frames`. `run_start` must match. A violation raises `LayoutError`.
  - `announcement_broken` is set, and `announcement-broken: <block> <nominal>` logged, when the row is a block's first show (`miss is not None`) with miss or degraded, and a persisted or already-appended `next`/`later` row names its occurrence.
  - `validate_rows` runs at the end.
- `plan_step` uses `scan_pieces` and the new `extend`. Recovery and fresh-run logic are unchanged. Nothing is trimmed.
- `render_step`:
  - Pieces are keyed `(kind, slug)` from `scan_pieces`, and exclusions and in-place mismatches are tracked per `(kind, slug)`.
  - An interstitial row is valid only when its clip is in the pool with the same key, and it is encoded through the same engine path from the folder's one-clip Show.
  - A row of an unknown `kind` takes the skip path.
  - The re-plan cap is `clips + len(rows_overlapping(rows, n*F, (target+1)*F)) + 10`, fixed when the first scan of the call is made. Exceeding it raises `PlanError("render re-planned <k> times in one call; stopping")`, with k = cap (the call makes exactly cap re-plans and then stops).
- `planner.py`: `choose_next`, `extend` and the `shuffle_rank` re-export are removed, and the docstring is rewritten.
- `pieces.LengthCache.forget(key)` was added (see Decisions).
- `cli.plan` help text: "(phase 1: fixed shuffled order)" is now "(the scheduler, on the live clock)".

## Decisions (where the brief and the built interfaces diverged)
1. **The `LengthCache` is built lazily by the Station, not eagerly in `open_station`.** `aacenc.extra_frames` runs an ffmpeg probe on every call. An eager build would make `publish`, `status`-adjacent commands and `fallback render` probe the encoder for nothing. More importantly, a cache fixed at open time goes stale when the encoder or clip pause changes (tests do this with `dataclasses.replace(st, cfg=..., engine=...)` and `engine.extra += 1`, and the frame-count-change tests rely on it). `length_cache()` rebuilds on any change of cache_dir, pause or extra. `open_station` therefore only gained a docstring, and `test_service` asserts that the cache it yields matches cache_dir, pause and extra and is rebuilt on an extra change.
2. **The gap guard checks the first appended row against `start_frame`, not against `prev.end + gap`.** On the render skip path, `replan_from` re-plans from the dropped row's own start frame. After a `show_gap_seconds` change, that start is `prev.end + old_gap`. Starting at `prev.end + new_gap` with a smaller gap would put the row inside an already-written segment, which is a cut. So the first row sits at the caller's start (`next_start` on the normal path), and every later appended row at `prev.end + gap_frames`.
3. **A render-time frame-count mismatch forgets the learned length** (`LengthCache.forget`) so that the re-plan re-measures, which keeps phase 1's "re-measured under the current model" behaviour. Marking the newly measured count as exact instead broke `test_the_second_mismatch_rule_is_per_slug`: a once-flaky measurement became a second mismatch and was excluded.
4. **A changed clip (different file-set key) is excluded for the rest of the call** (spec: "a failing clip is removed from the interstitial pool for the rest of that call"). A changed show is still re-planned in place, as before. A frame-count model change re-plans clips in place like shows, because it is the model that failed, not the clip.
5. **`"clock"` stays an event alert code, not a `LEVEL_CODES` member.** The brief only asked for alert and resolve, and `resolve()` clears an active event code anyway. Changing `alerts.py` and its tests felt out of scope; flagged under Concerns.
6. The `extend` loop checks `lengths.length(show)` before calling `frames_of`. On the render re-extend path the scanned pieces are stale estimates, so this avoids re-analysing a piece this process already measured.

## TDD evidence (log: `$D/task11-impl/task11-impl.log`)
- History RED: `pytest .../test_history.py -q` → `1 failed, 11 passed` (`assert (4 == 1)`: the list, dict and int packages loaded). GREEN: `12 passed`.
- Pipeline RED, with the new tests written before the implementation: `pytest .../test_pipeline.py -q` → `19 failed, 41 passed`. The errors were 9× `'Station' object has no attribute 'scan_pieces'`, `module 'transmitter.pipeline' has no attribute 'project'`, block `None` where `'open'` was expected, and similar. Three scenarios already passed on phase 1 (recovery, gap change, crash): their invariants predate the scheduler.
- GREEN: test_pipeline 64 passed; full suite 827 passed, 1 skipped.
- Rewritten existing tests:
  - `test_plan_step_starts_a_run_ahead_of_now` now asserts scheduler behaviour under the implicit clock: block `open`, shows only (no IDs without a folder), eligible slugs and keys, no repeat, back to back with the gap.
  - The three watchdog tests count one ping per analysis plus one per projection.
  - The systemd runner ping count likewise.
  - `test_planner` lays its rows out by hand; the shuffle tests are dropped.
  - `test_rules` no longer references `planner.shuffle_rank`.
- New tests in `test_pipeline.py`:
  - every test named in the brief;
  - `test_run2_pick_is_appended_when_analysed`, `test_an_exact_run1_pick_is_appended_without_a_second_run`;
  - `test_no_clock_plans_on_the_implicit_open_block`, `test_announcement_kept_or_not_made_is_not_broken`, `test_render_drops_a_changed_clip_for_the_rest_of_the_call`;
  - `test_a_show_measuring_no_frames_is_skipped_not_fatal`, `test_nothing_eligible_is_a_plan_error_only_when_planning_is_needed`, `test_scan_pieces_analyses_clips_unless_read_only`;
  - all six required scenarios.
- Clock tests use short, mixed blocks: 2 h and 3 h, alternating open, indie-only, open and jazz-only, wiggle 20 min. Shows are 20 minutes and IDs 10 s.

## Mutation check (Step 5), scratch copy only
Setup:
- `git archive HEAD | tar -x` into `<scratchpad>/mut/base`, one `cp -R` per mutant.
- Each run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<copy>/packages/transmitter/src:<copy>/packages/transmitter .venv/bin/python -B -m pytest -p no:cacheprovider --rootdir=<copy>/packages/transmitter <copy>/.../test_pipeline.py`, from an empty cwd.
- `transmitter.__file__`/`transmitter.pipeline.__file__` and `tests_transmitter.__file__` printed inside each copy.
- The unmutated copy ran 64 passed.

| # | Mutant | Predicted red | Result |
|---|---|---|---|
| 1 | `extend` replaces the last persisted row instead of appending | `test_append_only_under_a_clock_edit` | **CAUGHT**: predicted test red (21 red in total) |
| 2 | `extend` writes run 1's estimate (`chosen = run1`) | `test_written_rows_always_carry_exact_frames` | **CAUGHT**: predicted test red (35 red) |
| 3 | gap guard removed + the scheduler's `_add` lays the next piece at `prev.end` | `test_appended_rows_obey_the_gap_layout` | **CAUGHT**: predicted test red, and the only one (`DID NOT RAISE LayoutError`). The scheduler's own spacing only moves its lookahead, since `extend` takes piece [0] each time, so the guard sub-check is what catches it. |
| 3b | gap guard removed + `extend` lays each appended row at `prev.end` | `test_appended_rows_obey_the_gap_layout` | **CAUGHT**: predicted test red (10 red) |
| 4 | `extend` drops the last persisted row before appending | `test_append_only_under_a_clock_edit` | **CAUGHT**: predicted test red (22 red) |
| 5 (extra) | a changed clip re-planned in place instead of excluded | `test_render_drops_a_changed_clip_for_the_rest_of_the_call` | **CAUGHT**: the only red |

## Timing of a plan step
`<scratchpad>/plan_timing.py` runs `Station.extend` on this Mac against the 300-show fixture library (real durations, exact lengths, so one projection per row) plus 4 IDs:
- **Implicit clock:** one row (a service tick, `max_new=1`) takes 0.393 s for 1 projection. A 24 h fill is 21 rows in 6.14 s: mean 0.293 s, max 0.421 s per projection.
- **Short-block clock** (10 blocks of 2–3 h, mixed profiles): one row takes 0.005 s. A 24 h fill is 27 rows in 0.10 s, about 0.004 s per projection.

An estimated pick costs two projections plus its analysis (hugo: 146–215 s cold). At about 3× slower on hugo, an implicit-clock tick is about 1–2.5 s of projection. The transmitter suite now takes about 29 s, against 24 s before.

## Files changed
- `packages/transmitter/src/transmitter/{pipeline,planner,service,pieces,history,cli}.py`
- `packages/transmitter/tests_transmitter/{helpers,test_pipeline,test_planner,test_rules,test_service,test_systemd,test_history}.py`

## Self-review
- **Append-only.** `extend` copies `rows` and only appends. The two drop paths stay `replan_from` (render) and `cut_for_recovery` (plan_step), unchanged. Mutants 1 and 4 are caught.
- **Exact frames.** A row is written only from an exact piece (pool, cache or `frames_of`). Mutant 2 is caught.
- **Watchdog.** A ping follows each `project` call and each analysis (`frames_of`); `max_new` pacing is untouched (the service still calls with `max_new=1`).
- **Python 3.11.** Every changed file was parsed with `python3.11` (`ast.parse`). The Debian-12 docker gate was not run.
- **Read-only commands** (`schedule`, `status`, `announcements`) do not call `Station.clock()`; `announcements` already uses `live_clock(save=False)`.

## Concerns
1. **`"clock"` is not in `alerts.LEVEL_CODES`.** As an event code it expires after `repeat_hours` without a new fire, and plan runs only while filling, so `status` can stop showing a still-invalid clock between fills. Consider adding it to `LEVEL_CODES` (it is resolved on every valid read); I left `alerts.py` alone.
2. **The guard is close to tautological against the built scheduler.** `project` always places piece [0] at `start_frame`, so the guard fires only on a future scheduler bug or a caller passing an inconsistent `start_frame`. Mutant 3 shows that a scheduler-internal spacing bug is visible only through this guard.
3. **The re-plan cap counts rows overlapping `[n, target]` when the call first scans,** which is after any already-rendered segments are skipped. That is close to the brief's wording, but a call that re-plans many times early could legitimately need more if the plan grows. The +10 margin covers the tests' cases.
4. **ffmpeg probes.** `length_cache()` runs `engine.extra_frames()` (an ffmpeg probe with FfmpegEngine) once per `scan_pieces` and once per `extend`. That is about two extra probes per filling tick on hugo, in addition to the existing per-analysis probes.
5. **`cli.py` help string** was edited (one line, outside the brief's file list).
6. **The Debian-12 / Python 3.11 container suite was not run** (docker); only the 3.11 syntax parse.
