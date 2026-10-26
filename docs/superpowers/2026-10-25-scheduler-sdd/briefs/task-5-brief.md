### Task 5: Interstitials and announcements

**Files:**
- Create: `packages/transmitter/src/transmitter/interstitials.py`, `packages/transmitter/src/transmitter/announce.py`
- Modify: `packages/transmitter/src/transmitter/config.py` (`InterstitialsConfig(dir: Path | None = None)` on `TransmitterConfig.interstitials`; add to `DEFAULT_CONFIG_TOML` commented, keep `test_template_parses_to_the_defaults` green), `cli.py` (`announcements` command)
- Test: `test_interstitials.py`, `test_announce.py`, `test_cli.py`, `test_render.py`

**Interfaces:**
- Produces:
  - `interstitials.folder(cfg: TransmitterConfig) -> Path | None` — `cfg.interstitials.dir`, else `<station root>/interstitials`, else None (no station root).
  - `interstitials.row_dir(cfg, folder: Path) -> str` — the folder relative to the station root when inside it (`"interstitials"`), else its absolute path string. `Path(station_root) / row_dir` resolves back to the folder either way.
  - `interstitials.scan(folder: Path | None, *, now_s: float, quiet_s: float) -> list[Show]` — one `Show` per `id-*.mp3` / `ann-*.mp3` file older than the quiet period (mtime) and non-empty: `slug` = stem, `dir` = folder, `entries = (Entry(name, "clip", "Station ID" | "Announcement"),)`, `key = station.file_set_key(folder, [name])`, `meta = {"role": "id" | "ann", "ann_id": <id or None>, "sizes": {name: <bytes>}}` (`sizes` as a package's, so `estimate_frames` works on a clip). Missing folder → `[]`; an `OSError` on one file skips that file. Sorted by slug.
  - `announce.render_time(us: int, ann: AnnounceConfig) -> str` — for each zone in order: local hour/minute, formatted (`short12`: `"11"`, `"11:30"`, `"1"`; `hm12`: `"11:00"`; `24h`: `"23:00"`) then `" " + label`; zones joined with `", "`. E.g. `"11 Eastern, 8 Pacific"`.
  - `announce.render(template: str, first: Occurrence, second: Occurrence | None, ann: AnnounceConfig) -> str` — `str.format` with `title`, `time`, `next_title`, `next_time`.
  - `announce.ann_id(text: str) -> str` — first 12 hex chars of `sha256(text.encode())`.
  - `announce.Form = Literal["next", "next_one", "later", "later_one"]`.
  - `announce.text_for(form: Form, x: Occurrence, y: Occurrence | None, ann) -> str` (the template keyed by `form`).
  - `announce.Needed(id: str, text: str, form: Form, block: str, nominal_iso: str)`; `announce.needed(clock: ClockConfig, from_us: int, days: float = 8) -> list[Needed]` — for each occurrence X with a title in the span: `next_one` and `later_one`; plus `next` and `later` when the occurrence after X has a title. Deduplicated by id, in time order.
  - CLI `transmitter announcements [--clock FILE] [--days N] [--export DIR]` — lists `id  present|missing  text`, using the live clock (`live_clock(ws, save=False)`) or `--clock` (`load_clock`, errors exit 1); `--days` defaults to 8 (see Builder calls); `--export` writes `ann-<id>.txt` (UTF-8 text, trailing newline) for each missing one into DIR (created if absent) and prints how many; never writes elsewhere.

- [ ] **Step 1: Failing tests**

```python
# test_interstitials.py
def test_scan_finds_ids_and_announcements(tmp_path): ...  # id-hello.mp3, ann-0123456789ab.mp3, notes.txt
    # -> two Shows, roles id/ann, ann_id "0123456789ab", entries kind "clip", dir == folder, sizes == {name: bytes}
def test_missing_folder_is_an_empty_pool(tmp_path):
    assert interstitials.scan(tmp_path / "nope", now_s=time.time(), quiet_s=0) == []
def test_clip_inside_quiet_period_is_not_eligible(tmp_path): ...   # mtime now, quiet 600 -> []
def test_zero_byte_clip_is_skipped(tmp_path): ...
def test_row_dir_inside_and_outside_root(tmp_path): ...            # "interstitials" vs absolute str
def test_interstitials_folder_is_invisible_to_the_package_scan(tmp_path):
    # make_root + build_package + an interstitials/ folder with id-a.mp3: station.scan returns the package only
```

```python
# test_announce.py
def test_time_names_every_zone_in_order():
    # 2096-10-03T03:00Z (23:00 EDT) with default zones -> "11 Eastern, 8 Pacific"
def test_short12_shows_minutes_only_when_nonzero(): ...   # 23:30 local -> "11:30 Eastern, 8:30 Pacific"
def test_24h_format(): ...
def test_next_and_later_texts():
    # x title "Here Comes the Funk" at 23:00 EDT, y "Gravel & Steel" at 01:00 EDT
    # later -> "Stay tuned for Here Comes the Funk at 11 Eastern, 8 Pacific, followed by Gravel & Steel at 1 Eastern, 10 Pacific."
    # next  -> "Coming up next, Here Comes the Funk. Then at 1 Eastern, 10 Pacific, Gravel & Steel."
def test_ids_are_stable_for_unchanged_text(): assert ann_id("a") == ann_id("a") != ann_id("b")
def test_needed_skips_untitled_blocks_and_uses_one_forms(): ...
    # blocks A(titled) B(untitled) C(titled): A gets next_one/later_one only (B untitled);
    # B gets nothing; C gets the two-block forms when the following occurrence is titled
```

```python
# test_render.py
@requires_ffmpeg
def test_a_single_clip_piece_encodes_to_its_planned_frame_count(tmp_path):
    # the spec's unverified premise: write_mp3 a 7 s speech-like clip as interstitials/id-test.mp3,
    # scan it, analyze_show, render_show -> returned frames == planned_frames(analysis, pause, extra)
```

```python
# test_cli.py
def test_announcements_export_writes_missing_scripts_only(tmp_path): ...
    # clock with one titled block; folder holds ann-<one id>.mp3; --export out/ writes the other
    # needed ids as ann-<id>.txt with the exact rendered text; the present one is not exported;
    # no clock.last-good.toml is written
```

- [ ] **Step 2: Run to verify failure.** Expected: FAIL.
- [ ] **Step 3: Implement** as in Interfaces.
- [ ] **Step 4: Run the transmitter suite.** Expected: all PASS (ffmpeg tests skip without ffmpeg).
- [ ] **Step 5: Commit**

```bash
git add packages/transmitter/src/transmitter/{interstitials,announce,config,cli}.py packages/transmitter/tests_transmitter/test_{interstitials,announce,cli,render,config}.py
git commit -m "transmitter: interstitials folder scan, announcement texts with time zones, announcements command"
```

---

