### Task 13: `schedule`, `library` and `status`

**Files:**
- Modify: `packages/transmitter/src/transmitter/cli.py`, `service.py:418-449`
- Create: `packages/transmitter/src/transmitter/report.py` (pure formatting of projections and summaries)
- Test: `test_report.py`, `test_cli.py`, `test_service.py`

**Interfaces:**
- `report.block_views(rows: Sequence[PlanRow], projected: Sequence[PlannedPiece], clock, epoch, *, missing: Sequence[announce.Needed] = ()) -> list[BlockView]` — one per occurrence: block, title, nominal and actual start (local, clock timezone), slip minutes, shows `(artist, date, minutes, estimated: bool)`, fill shows with cause, interstitials, miss, degraded, bends, and the missing announcement audio naming that occurrence (`missing` entries whose `(block, nominal_iso)` is its key); `report.summary(views, span_us) -> Summary` (misses, counted from first-show rows with `miss`; fill minutes by cause and as a share of the span; bends by rule; shortest repeat gap in days; missing announcement audio).
- `transmitter schedule [--days 7] [--clock FILE] [--library eligible|delivered]` — no lock, writes nothing (it uses `load_epoch`, never `load_or_create_epoch`; with no epoch yet it previews from a provisional in-memory epoch at now and says so, writing no `epoch.json`): persisted rows from now, then `project(..., until_frame=<now + days>)` from the end of the persisted plan, on the live clock via `clock.live_clock(ws, save=False)` or `--clock`, and pieces from `st.scan_pieces(now_us, read_only=True)` (`--library delivered` uses `pieces.scan_delivered` on estimates). Estimated lengths are marked `~`. Missing announcement audio (`announce.needed` vs the folder) is listed per occurrence and in the summary.
- `transmitter library` — eligible shows by profile: count, median, p10, p90 minutes; the interstitial pool (IDs, announcements); ineligible packages counted by first reason.
- `status_lines` replaces the `anchors none (...)` line with: `clock` line (`clock.toml` / `last-good (problem)` / `no clock: open all week`, from `clock.live_clock(ws, save=False)`), current and next block from persisted rows, misses and fill minutes by cause for the last and next 24 h (persisted rows only), bend counts, degraded blocks, missing announcement audio (`announce.needed` for 8 days vs the folder). `status` never runs the scheduler or scans packages (the interstitials folder listing is a directory read).

- [ ] **Step 1: Failing tests**

```python
def test_block_views_report_slip_fill_cause_and_bends(): ...
def test_summary_counts(): ...                       # misses from first-show rows only
def test_schedule_writes_nothing(tmp_path):
    # snapshot the workspace tree (incl. cache/, clock.toml, clock.last-good.toml, alerts.json) before/after
    # `transmitter schedule` with the production FfmpegEngine path stubbed only for decode, or assert no
    # analysis is requested; the snapshots are equal
def test_schedule_marks_estimates(tmp_path): ...
def test_schedule_lists_missing_announcement_audio(tmp_path): ...   # per occurrence and in the summary
def test_library_reports_profiles_and_pool(tmp_path): ...
def test_status_says_no_clock_open_all_week(tmp_path): ...
def test_status_reads_persisted_rows_only(tmp_path): ...  # monkeypatch scheduler.project to raise: status still prints
```

- [ ] **Step 2: Run to verify failure.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the transmitter suite.** Expected: all PASS.
- [ ] **Step 5: Commit**

```bash
git add packages/transmitter/src/transmitter/{report,cli,service}.py packages/transmitter/tests_transmitter/test_{report,cli,service}.py
git commit -m "transmitter: schedule, library and scheduler status lines"
```

---

