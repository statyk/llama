### Task 3: Estimate inputs, estimates, and the hugo premise probe

**Files:**
- Create: `packages/transmitter/src/transmitter/mp3info.py`, `packages/transmitter/src/transmitter/pieces.py` (estimate part only), `packages/transmitter/scripts/probe_estimates.py`
- Modify: `packages/transmitter/src/transmitter/station.py:89-101, 202-212`
- Test: `test_mp3info.py`, `test_pieces.py`, `test_station.py`

**Interfaces:**
- Produces:
  - `station.file_set_key_and_sizes(pkg_dir, rels) -> tuple[str, dict[str, int]]` (one stat per entry; `file_set_key` delegates to it, same key bytes).
  - `Show.meta` additionally carries `"total_duration_sec": float | None` (manifest top-level), `"voiced_profile": str | None` (`dj_audio.profile` when a non-empty string, else `source.profile`), `"sizes": dict[str, int]` (broadcast.m3u entry → bytes). Existing meta keys unchanged.
  - `mp3info.mp3_seconds(path: Path, size: int | None = None) -> float | None`: skips an ID3v2 tag (syncsafe size), finds the first MPEG audio frame sync, reads version/layer/bitrate index/sample rate (MPEG-1/2/2.5 Layer III), returns `(file_size - audio_offset) * 8 / bitrate`, where `file_size` is `size` when given (no second stat) and the file's own size otherwise; `None` when no valid frame header is found in the first 64 KiB.
  - `pieces.estimate_frames(show: Show, *, pause_samples: int, extra: int, clip_seconds: Callable[[Path, int | None], float | None] = mp3info.mp3_seconds) -> int`: seconds = `total_duration_sec` (0 when None) + Σ clip seconds, each `clip_seconds(show.dir / entry.path, show.meta["sizes"][entry.path])` (a clip whose length is None counts `CLIP_FALLBACK_SECONDS = 120.0`); samples = `round(seconds * 44100) + pause_samples * n_clip_joins` (a join is each boundary between consecutive entries where either side is a clip, as `render.show_layout` counts); return `aacenc.frames_for(aacenc.pad_to_frame(samples), extra)`.
  - `pieces.UNVOICED_CLIP_ALLOWANCE_SECONDS = 240.0`.
  - `scripts/probe_estimates.py --config PATH [--limit N] [--time-one SLUG]`: read-only on hugo; for every eligible package with a cached analysis, prints slug, estimate frames, exact frames (`planned_frames` of the cached analysis with the live config), difference in seconds, and whether its clips are 64 kbps; a summary line with median and max absolute difference; `--time-one` times one cold `analysis.analyze_show` (no cache write) and prints seconds. Writes nothing.

- [ ] **Step 1: Failing tests**

```python
# test_mp3info.py
@requires_ffmpeg
def test_mp3_seconds_from_frame_header(tmp_path):
    p = tmp_path / "c.mp3"
    write_mp3(p, stereo_sine(10.0, 440, 0.1))      # 192 kbps CBR (helpers.write_mp3)
    assert mp3_seconds(p) == pytest.approx(10.0, abs=0.2)

def test_mp3_seconds_skips_id3v2(tmp_path):
    # an ID3v2 header (10 bytes, syncsafe size 100) + 100 bytes of tag + a valid MPEG-1 L3 128 kbps
    # 44.1 kHz frame header followed by 16_000 bytes: expect 16_004 * 8 / 128_000 within 1e-6.

def test_mp3_seconds_uses_the_given_size(tmp_path):
    # the same file with size=32_114 passed: expect (32_114 - 110) * 8 / 128_000 within 1e-6.

def test_mp3_seconds_none_without_a_frame(tmp_path):
    (tmp_path / "x.mp3").write_bytes(b"\0" * 1000)
    assert mp3_seconds(tmp_path / "x.mp3") is None
```

```python
# test_station.py
def test_show_meta_carries_estimate_inputs(tmp_path):
    root = make_root(tmp_path); pkg = build_package(root, "band-2005-11-01")
    m = json.loads((pkg / "manifest.json").read_text()); m["total_duration_sec"] = 180.0
    m["dj_audio"]["profile"] = "funk"; (pkg / "manifest.json").write_text(json.dumps(m)); set_age(pkg, 3600)
    show = station.evaluate(pkg, now_s=time.time(), quiet_s=0)
    assert show.meta["total_duration_sec"] == 180.0 and show.meta["voiced_profile"] == "funk"
    assert set(show.meta["sizes"]) == {e.path for e in show.entries}

def test_voiced_profile_falls_back_to_source_profile(tmp_path): ...   # no dj_audio.profile -> "indie"

def test_file_set_key_unchanged(tmp_path):
    # file_set_key(pkg, rels) == file_set_key_and_sizes(pkg, rels)[0]
```

```python
# test_pieces.py
def test_estimate_frames_counts_tracks_clips_and_pauses(tmp_path):
    # Show with entries clip, track, track, clip; meta total_duration_sec=100.0 and sizes for every entry;
    # clip_seconds=lambda p, size: 5.0; pause_samples=33075; extra=1
    # samples = round(110 * 44100) + 2 * 33075 -> frames_for(pad_to_frame(samples), 1)

def test_estimate_frames_passes_the_scanned_size(tmp_path): ...       # clip_seconds receives meta["sizes"][entry.path]
def test_unreadable_clip_uses_the_fallback(tmp_path): ...            # clip_seconds -> None adds 120 s
def test_missing_total_duration_counts_zero(tmp_path): ...
```

- [ ] **Step 2: Run to verify failure.** Expected: FAIL (missing modules / keys).
- [ ] **Step 3: Implement** as in Interfaces (`mp3info` is ~40 lines of header parsing; tables for MPEG-1 and MPEG-2/2.5 Layer III bitrates and sample rates).
- [ ] **Step 4: Run the transmitter suite.** Expected: all PASS.
- [ ] **Step 5: Probe smoke test** — run `./.venv/bin/python packages/transmitter/scripts/probe_estimates.py --help`; expected: usage text, exit 0.
- [ ] **Step 6: Commit**

```bash
git add packages/transmitter/src/transmitter/{mp3info,pieces,station}.py packages/transmitter/scripts/probe_estimates.py packages/transmitter/tests_transmitter/test_{mp3info,pieces,station}.py
git commit -m "transmitter: estimate inputs in the scan, MP3-header clip lengths, hugo estimate probe"
```

**Operator checkpoint (after Task 3, non-blocking):** the orchestrator asks the operator to run `probe_estimates.py` on hugo (and `--time-one` on one long package) and paste the summary. The spec's premise is "estimates land within seconds"; if the median absolute difference exceeds 15 s or the max exceeds 2 min, the orchestrator stops and escalates before Task 8 (estimates only steer choice and written rows are exact, but a block lands by the sum of at most a few estimates against a 15-minute window). Tasks 4-7 may proceed meanwhile.

---

