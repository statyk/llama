### Task 9: The projection: occurrences, interstitials, announcements (Opus)

**Files:**
- Modify: `packages/transmitter/src/transmitter/scheduler.py`
- Test: `packages/transmitter/tests_transmitter/test_scheduler.py`

**Interfaces:**
- Consumes: `fill_block` (Task 8); `occurrences` (Task 4); `announce.text_for`, `ann_id` (Task 5); `Recency.with_piece` (Task 7).
- Produces:
  - `SchedulerInput` (frozen): `rows: Sequence[PlanRow]` (persisted), `start_frame: int`, `run_start: bool`, `pool: Sequence[Piece]`, `clock: ClockConfig`, `rec: Recency`, `epoch_us: int`, `gap_frames: int`, `seed: int`.
  - `PlannedPiece` (frozen): `piece: Piece`, `start_frame: int`, `run_start: bool`, `block: str`, `nominal_start: str`, `role: str` (`"show" | "id" | "next" | "later"`), `miss: bool | None`, `degraded: bool`, `fill: str | None`, `bends: tuple[str, ...]`, `names: tuple[tuple[str, str], ...]`; `end_frame` property. A boundary interstitial carries the occurrence (`block`, `nominal_start`) of the show that follows it: a `next` piece carries X.
  - `project(inp: SchedulerInput, *, until_frame: int | None = None, ahead: int = 2) -> list[PlannedPiece]` — pure; plans the continuing occurrence plus `ahead` more; with `until_frame`, through the occurrence containing `until_frame` plus `ahead` more (so every announcement's named blocks are known). Returns every piece in order. The live extend passes no `until_frame` (current + 2: enough for every announcement) and appends only the first piece; `schedule` and the measurement pass `until_frame`.
  - `to_row(pp: PlannedPiece, seq: int) -> PlanRow` (sets `kind`, `package`, every scheduler field; `role` from `PlannedPiece.role`, not from `Piece.role`, which is `"id" | "ann"`).
- Raises `PlanError("no eligible packages to plan")` only when the pool holds no show at all.

**Algorithm (`project`), the decisions this task owns:**
- Pools: own pool of a profile occurrence = shows whose `profile` is in its `profiles`; for an open occurrence the own pool is the open pool. Open pool = shows whose profile is not in `[open] exclude_profiles` (empty → all shows, recorded as bend `"exclude_profiles"` on every fill/open show chosen from it).
- Continuing occurrence: the occurrence named by the last persisted row's `(block, nominal_start)` when it has one and the live clock still yields that occurrence (a boundary interstitial row carries the occurrence of the show that follows it, so a `next` row carries X), with `placed` = its persisted show rows; otherwise (phase-1 rows, a fresh run) the occurrence containing `start_frame` with `placed=()`. Occurrences are then processed in sequence, never skipped. `prev_artist` = artist of the last persisted show row (looked up via the pool by slug; None if unknown).
- Phase A (shows): for each occurrence in turn call `fill_block` with `boundary_frames` = `gap_frames` when the ID pool is empty (one gap, no clip), else `2 * gap_frames + typical_id_frames` (median ID length), and `final_boundary_frames` the same; carry `start_frame` to `landing_frame`, add chosen shows to `used` and to the projection's `Recency` (`with_piece`) so later occurrences see them.
- Phase B (boundaries), walking the phase-A shows in order and laying every piece out exactly from `inp.start_frame` (gap layout: each piece starts at previous end + `gap_frames`; the first piece of a run uses `start_frame`/`run_start` as given):
  - Before the first show of occurrence X (not at a run start): try `next` for X. It requires X titled (a titled open block is announced) and not degraded, and X's first show start (computed with this clip in place) within X's window. The two-block form is used when the occurrence after X, Y, is titled, not degraded, and its projected first-show start is within Y's window; when the two-block form fails only on Y (Y untitled, outside its window or degraded), the one-block form (`next_one`) is used. Missing audio: two-block clip missing → one-block clip → station ID → nothing.
  - At the last internal boundary of occurrence W (the boundary before W's last show, counting fill shows), try `later` for the occurrence after W with the same rules and the same one-block fallback; otherwise, and at every other internal boundary, a station ID.
  - Station ID choice: the ID clip with the oldest `last_used_us` (never used first; tie `tie_rank`), updating the projection's recency so consecutive boundaries rotate.
  - If the persisted plan ends with a show row, the first projected piece is that boundary's interstitial (or the next show when no clip applies); if it ends with an interstitial row, the first projected piece is a show.
  - `miss` on each occurrence's first show = its start outside `[lo, hi]`; `fill`, `bends`, `degraded` copied from the `BlockPlan`; `names` on announcement pieces.
- Exact frames are what the pieces carry; estimates only change where later pieces land in the projection, never a written row (Task 11 analyses before writing).

- [ ] **Step 1: Failing tests** (`test_scheduler.py`, using the Task 8 fixture plus a few one-clip interstitial pieces)

```python
def test_project_is_pure_and_deterministic(): ...
def test_first_piece_continues_a_partly_filled_block(): ...          # persisted row in occ X counts toward max_shows
def test_a_next_row_last_continues_its_named_occurrence(): ...       # last persisted row is X's `next`: X continues with placed=()
def test_phase1_prefix_is_extended_mid_block(): ...                 # rows without block fields
def test_gap_layout_for_every_projected_piece(): ...                 # start == prev.end + gap_frames
def test_appending_first_pieces_reproduces_one_projection():
    # exact lengths: repeatedly append project(...)[0] to the rows (and add it to the recency);
    # the resulting piece sequence equals one project call over the same span
def test_station_id_between_shows_rotates_least_recent_first(): ...
def test_empty_id_pool_boundary_is_one_gap(): ...                    # boundary_frames == gap_frames
def test_next_announcement_at_block_start_names_x_and_y(): ...
def test_later_on_the_last_internal_boundary_only(): ...            # three-show open block: ID, later
def test_untitled_x_gets_an_id_not_an_announcement(): ...
def test_titled_open_block_is_announced(): ...
def test_degraded_y_uses_the_one_block_form(): ...
def test_y_outside_its_window_uses_the_one_block_form(): ...
def test_two_block_clip_missing_falls_back_to_one_block_then_id(): ...
def test_announcement_dropped_when_x_would_start_outside_its_window(): ...
def test_no_id_clips_means_plain_gaps(): ...
def test_overlapping_windows_resolve_as_a_late_start_and_a_miss(): ...
def test_exclude_profiles_bends_when_the_open_pool_is_empty(): ...
def test_plan_error_only_when_no_show_is_eligible(): ...
def test_implicit_clock_never_records_a_miss(): ...                 # IMPLICIT_CLOCK over 7 days of the fixture: no miss
def test_default_horizon_is_the_continuing_occurrence_plus_two(): ...
def test_until_frame_extends_the_horizon(): ...                     # through the occurrence containing until_frame, plus ahead
def test_project_over_a_3000_piece_pool_is_fast(): ...              # synthetic 3,000-piece pool, current + 2: under 2 s on the dev box
```

The timing test is a plain test (the suite has no `slow` marker).

- [ ] **Step 2: Run to verify failure.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the transmitter suite.** Expected: all PASS.
- [ ] **Step 5: Commit**

```bash
git add packages/transmitter/src/transmitter/scheduler.py packages/transmitter/tests_transmitter/test_scheduler.py
git commit -m "transmitter: scheduler projection with station IDs and truthful announcements"
```

---

