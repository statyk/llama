### Task 6: Pieces and pools

**Files:**
- Modify: `packages/transmitter/src/transmitter/pieces.py`
- Test: `packages/transmitter/tests_transmitter/test_pieces.py`

**Interfaces:**
- Consumes: Task 3 `estimate_frames`, `mp3_seconds`; Task 5 `interstitials.scan`, `row_dir`; `station.evaluate`; `analysis.load_cached`; `render.planned_frames`.
- Produces:
  - `Piece` (frozen dataclass): `kind: Literal["show", "interstitial"]`, `show: station.Show`, `dir: str` (the `PlanRow.dir` to write), `frames: int`, `exact: bool`, and derived properties `slug`, `key` (from `show`), `package` (show slug for shows, None for clips), `artist`, `date` (`"YYYY-MM-DD"` or None), `year` (int or None), `month_day` (`"MM-DD"` or None), `profile` (`meta["voiced_profile"]`), `role` (`"show"` for shows, else `meta["role"]`), `ann_id`.
  - `LengthCache(cache_dir: Path | None, pause_samples: int, extra: int)` (`cache_dir=None`: no cache lookups, estimates only — the measurement's mode) with `length(show: Show) -> tuple[int, bool]` — exact `planned_frames` when `load_cached(cache_dir, show.key)` hits (memoised by key), else `estimate_frames` (memoised by key), `exact=False`; `mark_exact(key: str, frames: int)` records an exact count learned this process.
  - `build_pool(shows: Sequence[Show], clips: Sequence[Show], *, lengths: LengthCache, clip_dir: str, analyze_clip: Callable[[Show], int] | None = None, read_only: bool = False) -> tuple[list[Piece], list[tuple[Show, TransmitterError]]]` — shows become `kind="show"`, `dir=show.dir.name`; clips `kind="interstitial"`, `dir=clip_dir`. Interstitial pieces are exact: `analyze_clip` (the Station's `frames_of`) is called for every clip `lengths` does not already know exactly, and the result recorded with `mark_exact` (clips are short). A clip whose analysis raises `TransmitterError` is left out of the pool and returned with its error in the second element, for the caller to log. `analyze_clip` is required unless `read_only=True`. With `read_only=True` an unanalysed clip is never analysed: it takes `lengths.length(clip)` (an estimate via `mp3_seconds`, `exact=False`), so read-only commands never write the analysis cache. Written rows are still always exact (Task 11 analyses before writing).
  - `scan_delivered(root: Path, *, now_s: float, quiet_s: float, pause_samples: int, extra: int) -> list[Piece]` — for `--library delivered`: every non-dot package dir with a readable v3+ manifest, voiced or not. A package `station.evaluate` accepts uses its own `Show` (its file-set key) and its normal estimate (`estimate_frames`). Only the others (unvoiced, or not yet eligible) get a `Show` built from the manifest only (entries from tracks, plus the DJ clips when voiced), `key = "m-" + sha256(f"{mtime_ns}:{size}" of manifest.json)[:20]`, and an estimate of `total_duration_sec` + `UNVOICED_CLIP_ALLOWANCE_SECONDS`. All `exact=False`. Never decodes, never writes.

- [ ] **Step 1: Failing tests**

```python
def test_cached_analysis_gives_an_exact_length(tmp_path): ...       # write a ShowAnalysis json under cache/<key>.json
def test_uncached_show_is_estimated_and_marked(tmp_path): ...
def test_mark_exact_overrides_the_estimate(tmp_path): ...
def test_build_pool_analyses_every_clip(tmp_path): ...              # analyze_clip called once per clip; pieces exact
def test_build_pool_returns_the_clips_it_dropped(tmp_path): ...     # analyze_clip raises for one: (show, exc) returned, not in the pool
def test_build_pool_read_only_never_analyses(tmp_path): ...         # analyze_clip never called; clip pieces exact False; cache/ untouched
def test_piece_properties_from_meta(tmp_path): ...                  # artist/date/year/month_day/profile/role
def test_scan_delivered_includes_unvoiced_with_allowance(tmp_path):
    # build_package(voiced=False) with total_duration_sec=3600 -> frames for 3600 + 240 s, exact False
def test_scan_delivered_uses_the_file_set_key_of_an_eligible_package(tmp_path): ...
    # an eligible voiced package: key == station.evaluate(...).key, frames == estimate_frames(show, ...)
```

- [ ] **Step 2: Run to verify failure.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the transmitter suite.** Expected: all PASS.
- [ ] **Step 5: Commit**

```bash
git add packages/transmitter/src/transmitter/pieces.py packages/transmitter/tests_transmitter/test_pieces.py
git commit -m "transmitter: pieces, exact-or-estimated lengths, pools, delivered-library scan"
```

---

