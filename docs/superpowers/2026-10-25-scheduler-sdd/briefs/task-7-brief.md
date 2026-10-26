### Task 7: Rotation history

**Files:**
- Create: `packages/transmitter/src/transmitter/history.py`
- Modify: `packages/transmitter/src/transmitter/workspace.py` (`aired_path -> root / "aired.jsonl"`), `service.py` (append in `_tick` after publish; backfill when `aired.jsonl` is absent)
- Test: `test_history.py`, `test_service.py`

**Interfaces:**
- Produces:
  - `AiredRow` (frozen): `epoch_id, start_frame, end_frame, kind, slug, package, block, nominal_start, role, miss, degraded, fill, bends, announcement_broken, start, end` (ISO strings). `from_json` ignores unknown keys. For `kind == "show"`, `package = row.package or row.slug` (phase-1 rows carry no `package`); the same rule gives the package for recency.
  - `aired_rows_due(rows: Sequence[PlanRow], epoch: Epoch, pub_last: int | None, now_us: int) -> list[AiredRow]` — rows whose `end_frame` (cut end included) is at or before the end of segment `pub_last` (`(pub_last + 1) * SEGMENT_FRAMES`) and whose end instant is at or before `now_us`.
  - `append_aired(ws: Workspace, epoch: Epoch, rows: Sequence[PlanRow], pub_last: int | None, now_us: int) -> int` — appends (one `json.dumps` line each, `open(..., "a")` then `flush`+`fsync`) only rows whose identity `(epoch_id, start_frame)` is not already in the file; returns how many. A first call with no file is the backfill (same rule).
  - `load_aired(ws) -> list[AiredRow]` — a corrupt line is skipped with a log warning, never raises.
  - `Recency` with `last_aired_us(package: str) -> int | None`, `last_used_us(clip_slug: str) -> int | None`, `artists_on(local_date) -> list[str]`, `artist_years_on(local_date) -> list[tuple[str, int]]`, and `with_piece(piece, start_us, local_date) -> Recency` (a new index, for the projection's own choices). Built by `recency(aired: Sequence[AiredRow], rows: Sequence[PlanRow], epoch: Epoch, tz: str, meta_of: Callable[[str], tuple[str | None, str | None]])` — union of aired rows and persisted plan rows (deduped by identity); `meta_of(package)` gives `(artist, date)` from the current scan, unknown → `(None, None)`.
- Service: after `publish_all` in `_tick`, call `history.append_aired` inside its own `_step("history", …)`; failures alert `history` and never stop the tick. The history step is **not** added to `ran` and is not declared in `alerts.STEP_CODES`/`OBSERVER_STEPS`: `end_observation` rejects unknown steps. `history` is therefore an ungated event code.

- [ ] **Step 1: Failing tests**

```python
def test_only_published_and_past_rows_are_appended(tmp_path): ...
def test_append_is_idempotent_across_restarts(tmp_path):
    # append_aired twice with the same inputs -> second returns 0, file has one line per row
def test_a_cut_row_records_its_cut_end(tmp_path): ...
def test_backfill_from_a_phase1_plan(tmp_path): ...               # rows without scheduler fields -> kind "show", package == slug
def test_corrupt_line_is_skipped(tmp_path): ...
def test_recency_counts_persisted_unaired_rows(tmp_path): ...
def test_artists_on_uses_the_clock_timezone(tmp_path): ...        # a show at 02:00Z counts on the previous local day in New York
```

```python
# test_service.py
def test_tick_appends_aired_rows_after_publishing(tmp_path): ...
def test_history_failure_alerts_and_the_tick_completes(tmp_path): ...   # append_aired raises: "history" alerted; end_observation does not raise
```

- [ ] **Step 2: Run to verify failure.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the transmitter suite.** Expected: all PASS.
- [ ] **Step 5: Commit**

```bash
git add packages/transmitter/src/transmitter/{history,workspace,service}.py packages/transmitter/tests_transmitter/test_{history,service}.py
git commit -m "transmitter: aired.jsonl history (published rows only, idempotent) and the recency index"
```

---

