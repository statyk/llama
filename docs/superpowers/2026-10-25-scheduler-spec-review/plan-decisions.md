# Plan review decisions (apply exactly to docs/superpowers/plans/2026-10-25-scheduler.md)

Two reviewers (Opus, Fable). Apply every item; keep the plan's voice; no reviewer/round labels in the plan.

## Structure
S1. Reorder: the measurement task moves ahead of pipeline integration. New order: 1 tolerant rows (+ timeline skip, see T1), 2 plan lock, 3 estimates + probe, 4 clock, 5 interstitials + announcements, 6 pieces, 7 history, 8 block filling, 9 projection, 10 measurement (was 13), 11 pipeline integration (was 10), 12 player (was 11's antenna half only), 13 schedule/library/status (was 12), 14 runbook. Renumber every cross-reference ("Task N", Consumes lines, checkpoints, Review Focus test locations, File Structure).
S2. Measurement (now Task 10) consumes only Tasks 3-9 (pieces, scheduler); its floor checkpoint therefore lands before the pipeline is wired.

## Task 1
T1. Task 1 also makes everything downstream skip non-show rows, so this deploy-first commit is itself safe against scheduler rows: `site.build_timeline` skips rows whose `kind != "show"` (not in `shows`, not in `recent`); `publish._publish_site` never calls `analysis_for` for them; `service.row_analysis` returns None for them BEFORE the cache lookup (a clip's analysis is cached, so the guard must come first). Tests: `test_timeline_lists_no_interstitial_rows`, `test_publish_site_never_asks_for_an_interstitial_analysis`, `test_row_analysis_ignores_interstitial_rows_even_when_cached`. The player task (12) keeps only the antenna change.
T2. `kind` is validated only as a non-empty string (no closed set). Consumers decide: timeline/publish/row_analysis skip non-`show` kinds; render re-validation (Task 11) treats an unknown kind as not eligible (the skip path).
T3. `to_json` is hand-written: known fields via `dataclasses.fields` (tuples as lists), then `extra` keys; never `dataclasses.asdict` (it deep-copies, and `copy.deepcopy` of a `MappingProxyType` raises). State this in Step 3.
T4. Runbook text names "this commit" / "the commit adding `[interstitials]`" rather than plan task numbers, and adds one sentence: a build from before this commit would list interstitial rows in `timeline.json` and publish notes/pages for them.

## Task 2
T5. Fix the reference: `cli.py:155-176` (`plan`, `render`). `plan_lock` creates `ws.root` first, as `publish_lock` does.

## Task 3
T6. Keep `meta["sizes"]` and use it: `mp3info.mp3_seconds(path: Path, size: int | None = None)` uses the given size instead of a second stat; `estimate_frames` passes `meta["sizes"][entry.path]`.
T7. Checkpoint thresholds: stop and escalate if the median absolute estimate error exceeds 15 s or the max exceeds 2 min (estimates only steer choice; written rows are exact; a block lands by the sum of at most a few estimates against a 15-minute window).

## Task 4
T8. Defaults on the models: `AnnounceConfig` fields default to the Global Constraints templates, `time_format="short12"`, `zones` default Eastern+Pacific; `ClockConfig.announce/open/rotation` use `default_factory`. A clock file of `timezone` + `[[block]]`s is valid.
T9. Load-time validation (so a clock that loads cannot crash planning; `live_clock` would otherwise save it as last-good): each template formats with dummy values for exactly its allowed fields (two-block forms: `title`, `time`, `next_title`, `next_time`; one-block forms: `title`, `time` only; an unknown field, stray brace or a `next_*` in a one-block form is a `ConfigError`); the effective window must be positive (`wiggle_minutes > 0`, or `early_minutes + late_minutes > 0`); `days` is `"daily"` or a non-empty list. Tests: `test_bad_template_is_a_config_error`, `test_one_block_form_cannot_name_next`, `test_zero_window_is_a_config_error`, `test_empty_days_is_a_config_error`.
T10. Nonexistent local time: "resolve to the transition instant: the first UTC instant whose local wall time is at or after the requested one" (replace the fold recipe). Keep the 07:00Z assertion.
T11. `live_clock(ws, *, save: bool = True)`: read-only callers (`status`, `schedule`, `announcements`) pass `save=False` (no last-good write). Test: `test_live_clock_save_false_writes_nothing`.
T12. Open blocks: `max_shows` default None = unbounded (the search's greedy extension handles any count); profile blocks default 2. `IMPLICIT_CLOCK` is one open block with unbounded shows and `wiggle_minutes=720`. Test (Task 9): `test_implicit_clock_never_records_a_miss` over 7 days of the fixture.

## Task 5
T13. `announcements --days` stays (default 8), recorded as a builder call: DST shifts the rendered zone times, so the needed set is a window, not a fixed weekly set.

## Task 6
T14. `build_pool(...) -> tuple[list[Piece], list[tuple[Show, TransmitterError]]]` — the dropped clips are returned for the caller to log.
T15. `build_pool(..., read_only: bool = False)`: with `read_only=True` an unanalysed clip is estimated via `mp3_seconds` (marked `exact=False`) instead of analysed, so read-only commands never write the analysis cache. Written rows are still always exact (Task 11 analyses before writing).
T16. `scan_delivered`: a package that `station.evaluate` accepts uses its file-set key and its normal estimate; only the others (unvoiced or not yet eligible) use the manifest mtime+size key and the 4-minute allowance.

## Task 7
T17. Phase-1 rows: `package = row.package or row.slug` for `kind == "show"` (aired rows and recency). Pin it in `test_backfill_from_a_phase1_plan`.
T18. The history step is NOT added to `ran` and not declared in `alerts.STEP_CODES`/`OBSERVER_STEPS`: `end_observation` rejects unknown steps. `history` is an ungated event code. State this in the Interfaces block.

## Task 8
T19. Continuation (the Critical): `fill_block` treats `placed` as a fixed prefix and may add 0 .. `max_shows - len(placed)` more own shows (0 allowed when `placed` is non-empty), then fill after the prefix (tier 1), then a miss. With `placed` already at `max_shows`, tier 0/1 consider only "no more own shows" (+ fill), and tier 2 is "no more shows" (land where the prefix ends); there is always at least one option, never an empty `min()`.
T20. REMOVE the absorption rule (`shows=()` when the window has passed) and its test. Per the spec, overlapping windows resolve as a late start plus a miss: an occurrence always plays at least one show of its own (or, for an open/degraded block, open-pool) profile, late, `miss=True` on its first show. Replace the test with `test_overlapping_window_plays_late_with_a_miss`.
T21. Open blocks: for an open occurrence (`is_open`) the own pool IS the open pool; `degraded=True` only for a profile block whose own pool is empty (it is then filled from the open pool and not announced).
T22. Search bound: pair partners come from candidates whose length lands the window (sort the pool by frames once; bisect the landing range), capped at the top 64 by score; first members from the top 32; tier-1 fill uses the same bound. State the bound: per occurrence at most 32 × 64 pair evaluations per prefix, 5 prefixes.
T23. Score: keep `mean(score)` and record it as a builder call: a summed score would always prefer more shows over fewer, against Goal 2's "normally at most two".
T24. Tier 1 requiring at least one own show (when the own pool is non-empty) is kept and recorded as an interpretation to confirm with the operator: the block keeps its profile at its time and the NEXT block slips, rather than the block airing only other profiles. (The orchestrator does not change it without the operator.)
T25. Tests added: `test_softest_rule_bends_first` (an option breaking only era beats one breaking only artist_day, beats gap, beats adjacency); `test_placed_prefix_at_max_shows_has_an_option`; `test_early_landing_block_gets_no_extra_show`.
T26. Fixture: commit the generator script (`tests_transmitter/fixtures/make_library_durations.py`, deterministic seed) instead of a README note.

## Task 9
T27. Continuing occurrence: the occurrence named by the last persisted row's `(block, nominal_start)` when it has one (a boundary interstitial row carries the occurrence of the show that follows it, i.e. a `next` row carries X), with `placed` = its persisted shows; otherwise (phase-1 rows, a fresh run) the occurrence containing `start_frame` with `placed=()`. Occurrences are then processed in sequence, never skipped.
T28. Horizon: `project(inp, *, until_frame: int | None = None, ahead: int = 2) -> list[PlannedPiece]` plans the continuing occurrence plus `ahead` more, extended to the occurrence containing `until_frame` when given. The live extend passes no `until_frame` (current + 2: enough for every announcement). `schedule` and the measurement pass `until_frame`.
T29. Required test (the Critical's guard): `test_appending_first_pieces_reproduces_one_projection` — with exact lengths, repeatedly appending `project(...)[0]` to the rows (and adding it to the recency) yields the same piece sequence as one `project` call over the same span.
T30. Interstitial `boundary_frames` with an empty ID pool is exactly `gap_frames` (one gap, no clip); with IDs, `2 * gap_frames + typical_id_frames`.
T31. Fallback when the two-block form fails only on Y (Y outside its window or degraded): use the one-block form. State it in Phase B and add `test_y_outside_its_window_uses_the_one_block_form`.
T32. `to_row` takes `role` from `PlannedPiece.role` (`"show" | "id" | "next" | "later"`), not from `Piece.role` (`"id" | "ann"`).
T33. `test_titled_open_block_is_announced`.

## Task 10 (measurement, was 13)
T34. One continuous projection over the whole span (50 weeks), history accumulating, no per-week restart; weekly figures are slices of it. The smoke test asserts a time budget: projecting 2 weeks of the fixture takes under 10 s.
T35. Add a timing test in Task 9: `project` over a synthetic 3,000-piece pool for current + 2 occurrences finishes in under 2 s on the dev box (marked `slow` only if the suite has that marker; otherwise plain).

## Task 11 (pipeline, was 10)
T36. Recency is rebuilt from the grown rows after every appended row inside `extend` (not once per call). Test: `test_multi_row_extend_never_repeats_a_show_or_id_while_alternatives_exist` (empty plan, `max_new=None`).
T37. `extend` calls `notify("WATCHDOG=1")` after each `project` call when `st.notify` is set.
T38. `Station` gains a `lengths: LengthCache` field and a `clock()` method only (no `live` field). `Station.clock()` alerts `clock` / resolves it; read-only commands call `clock.live_clock(ws, save=False)` directly, never `Station.clock()`.
T39. `scan_pieces(now_us, *, read_only=False)` passes `quiet_s=cfg.station.quiet_minutes * 60` to `interstitials.scan`; add the quiet-period case to `test_interstitial_rows_are_rendered_from_the_clip_folder`.
T40. Re-validation: an unknown `kind` row is not eligible (skip path).
T41. Mutation step: run each mutant with its own bytecode cache (`PYTHONDONTWRITEBYTECODE=1` and `python -B`, or a fresh `PYTHONPYCACHEPREFIX` per mutant) on a scratch copy shadowed via `PYTHONPATH`; add a fourth mutant: `extend` drops the last persisted row before appending → expect `test_append_only_under_a_clock_edit` red.
T42. The timeline/publish/row_analysis skips are now Task 1's; remove them from here and from the player task.

## Task 12 (player, was 11)
T43. Antenna only: `nowPlayingText(np, timelineLoaded, stationName)` and `player.js`. Steps run `cd antenna && npm ci` first in a fresh worktree.

## Task 13 (schedule/library/status, was 12)
T44. `schedule` output includes missing announcement audio (from `announce.needed` vs the folder) per occurrence and in the summary.
T45. `schedule`, `status`, `announcements` use `live_clock(ws, save=False)` and `scan_pieces(..., read_only=True)` (schedule) — `test_schedule_writes_nothing` snapshots the workspace (incl. `cache/`, the clock files, `alerts.json`) with the production `FfmpegEngine` path stubbed only for decode, or asserts that no analysis is requested.
T46. Absorbed-occurrence counting is moot (T20); misses are counted from first-show rows.

## Calls to record in the plan header area (a short "Builder calls" list after Review Focus)
- `mean(score)` within a tier (T23); tier 1 keeps ≥1 own show (T24, to confirm with the operator); open blocks unbounded; implicit clock = open block ±12 h; no background analysis; no `plan.jsonl` trimming; `announcements --days`; search bound (T22).
