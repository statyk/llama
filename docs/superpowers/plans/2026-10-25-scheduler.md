# Playout Phase 3 Scheduler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace transmitter's phase-1 shuffle planner with a clock-driven scheduler (blocks, pools, rotation rules, station IDs and schedule announcements, rotation history) plus the `schedule`, `library` and `announcements` commands, without ever changing a persisted plan row.

**Architecture:** A pure scheduler (`scheduler.py`) projects whole block occurrences forward from the end of the persisted plan, in memory, and the pipeline appends only its first piece per step, exactly as phase 1 appends one show per step. Everything below the scheduler becomes piece-aware (a piece is a show or a one-clip interstitial, both carried as `station.Show` so analysis, encode and the frame store are reused unchanged). The clock lives in its own strict TOML file with a last-good copy; history lives in `aired.jsonl`.

**Tech Stack:** Python 3.11 (hugo: Debian 12), pydantic v2 strict models, `zoneinfo`, typer, pytest; antenna's player JS with vitest.

**Spec:** `docs/superpowers/specs/2026-10-25-scheduler-design.md` (approved 2026-10-25). Parent: `docs/superpowers/specs/2026-10-09-playout-design.md`. Executors read the spec; this plan names the decisions the spec leaves to the builder.

## Global Constraints

- Python **3.11** compatible: no 3.12+ syntax (no `type X = …`, no PEP 695 generics, no nested same-quote f-strings). The gate is `packages/transmitter/scripts/test-in-debian12.sh`.
- transmitter never imports llama or emcee (`tests_transmitter/test_no_llama_or_emcee_imports.py`).
- Run tests in the worktree with its own venv: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q` (create it once per the repo CLAUDE.md setup line if missing; check `./.venv/bin/python -c "import transmitter; print(transmitter.__file__)"` resolves inside the worktree).
- Config models stay strict (`_StrictModel`, `extra="forbid"`); persisted state (`plan.jsonl` rows, `aired.jsonl`) is permissive.
- **The plan is append-only:** no new code changes or removes a persisted `plan.jsonl` row. Only `planner.replan_from` (render's skip path) and `planner.cut_for_recovery` (recovery) drop rows, unchanged.
- **Gap layout:** every appended non-`run_start` row starts at `previous.end_frame + gap_frames` (interstitials included); asserted on appended rows only.
- Written rows always carry exact frame counts (`Station.planned_frames` of a real analysis), never estimates.
- The scheduler adds no R2 writes; interstitial rows never reach `timeline.json`, `notes/` or `show/`.
- `[planner] seed` and `[planner] start_delay_minutes` stay as config keys.
- Clock file: `<TRANSMITTER_ROOT>/clock.toml`; last-good copy `<TRANSMITTER_ROOT>/clock.last-good.toml`.
- Interstitials folder default `<station root>/interstitials/`; station IDs `id-*.mp3`, announcements `ann-<id>.mp3`; transmitter only reads it (`announcements --export DIR` is the one explicit operator write).
- Announcement defaults (part of the clock contract; changing one later retires voiced clips):
  `next = "Coming up next, {title}. Then at {next_time}, {next_title}."`,
  `next_one = "Coming up next, {title}."`,
  `later = "Stay tuned for {title} at {time}, followed by {next_title} at {next_time}."`,
  `later_one = "Stay tuned for {title} at {time}."`,
  `time_format = "short12"`, `zones = [{tz="America/New_York", label="Eastern"}, {tz="America/Los_Angeles", label="Pacific"}]`.
- Rotation defaults: `concert_gap_days = 45`, `on_this_day_weight = 3.0`; open blocks `max_shows` default 6, profile blocks 2; `wiggle_minutes` 15.
- New alert code `clock` (not gated: sends at once, deduped by `repeat_hours`).
- Implementer model: Sonnet unless the task header says Opus.

## Review Focus

1. **Clock edited to something the library cannot serve** (a daily bluegrass block with 2 voiced bluegrass shows): the station keeps playing, the block repeats or degrades to open time, `status` says so, nothing alarms. Test: Task 8 `test_scarce_pool_repeats_rather_than_degrading` and `test_empty_pool_block_degrades_to_open_time`.
2. **Interstitials folder missing, empty, or holding only stale/partial files** (an `emcee say` in progress): no IDs or announcements, plain gaps, no errors. Test: Task 5 `test_missing_folder_is_an_empty_pool` and `test_clip_inside_quiet_period_is_not_eligible`.
3. **A clip deleted or re-voiced after its row was planned but before render:** render skips it at its boundary, re-extends without it, no loop. Test: Task 10 `test_render_skips_a_vanished_interstitial_and_moves_on`.
4. **DST weeks** (blocks at 02:30, the fall-back repeated hour) and **blocks crossing midnight**: occurrences resolve as the spec says; no zero-length block reaches the scheduler. Test: Task 4 `test_spring_forward_collapses_and_drops` and `test_fall_back_ambiguous_uses_first_occurrence`.
5. **Service restart / manual CLI while the service runs:** no double `aired.jsonl` rows; `plan`/`render` refused under the plan lock. Test: Task 7 `test_append_is_idempotent_across_restarts`; Task 2 `test_plan_and_render_refuse_while_locked`.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `packages/transmitter/src/transmitter/layout.py` | modify | `PlanRow` gains scheduler fields + unknown-key round trip |
| `packages/transmitter/src/transmitter/planner.py` | modify | strict row parsing keeps working with new fields; `choose_next`/`extend` retired (Task 10) |
| `packages/transmitter/src/transmitter/workspace.py` | modify | paths: `plan_lock_path`, `clock_path`, `clock_last_good_path`, `aired_path` |
| `packages/transmitter/src/transmitter/errors.py` | modify | `PlanLocked` |
| `packages/transmitter/src/transmitter/locks.py` | create | `plan_lock(ws)` |
| `packages/transmitter/src/transmitter/station.py` | modify | `Show.meta` carries estimate inputs + voiced profile |
| `packages/transmitter/src/transmitter/mp3info.py` | create | first-frame MP3 bitrate → seconds |
| `packages/transmitter/src/transmitter/pieces.py` | create | `Piece`, estimates, pool building, delivered-library scan |
| `packages/transmitter/src/transmitter/clock.py` | create | clock models, load, last-good, weekly expansion |
| `packages/transmitter/src/transmitter/interstitials.py` | create | folder resolution and scan into one-clip `Show`s |
| `packages/transmitter/src/transmitter/announce.py` | create | template rendering, ids, needed set |
| `packages/transmitter/src/transmitter/history.py` | create | `aired.jsonl`, recency index |
| `packages/transmitter/src/transmitter/rules.py` | create | scores, rule violations, bend counting |
| `packages/transmitter/src/transmitter/scheduler.py` | create | the pure projection |
| `packages/transmitter/src/transmitter/pipeline.py` | modify | scheduler-driven extend, plan lock, interstitial re-validation, re-plan cap |
| `packages/transmitter/src/transmitter/site.py` | modify | timeline skips interstitials |
| `packages/transmitter/src/transmitter/publish.py` | modify | `_publish_site` skips interstitial rows |
| `packages/transmitter/src/transmitter/service.py` | modify | plan lock in steps, aired append, status lines |
| `packages/transmitter/src/transmitter/cli.py` | modify | `schedule`, `library`, `announcements`; lock on `plan`/`render` |
| `packages/transmitter/src/transmitter/config.py` | modify | `[interstitials] dir` |
| `antenna/public/nowplaying.js`, `antenna/public/player.js` | modify | station name when no show airs |
| `packages/transmitter/scripts/probe_estimates.py` | create | hugo premise probe |
| `packages/transmitter/scripts/measure_scheduler.py` | create | measurement runner |
| `docs/superpowers/2026-10-2X-scheduler-measurement/` | create | edited naive script, clocks, evidence doc |
| `docs/playout-setup.md`, `CLAUDE.md` | modify | runbook and project notes |

---

### Task 1: Tolerant plan rows with scheduler fields (deploy to hugo first)

**Files:**
- Modify: `packages/transmitter/src/transmitter/layout.py:22-42`
- Modify: `packages/transmitter/src/transmitter/planner.py:118-158`
- Modify: `docs/playout-setup.md` (rollback note)
- Test: `packages/transmitter/tests_transmitter/test_layout.py`, `test_planner.py`

**Interfaces:**
- Produces: `PlanRow` fields, all with defaults so phase-1 rows load:
  `kind: str = "show"` (`"show" | "interstitial"`), `block: str | None = None`, `nominal_start: str | None = None` (ISO UTC of the occurrence's nominal start; with `block` it identifies the occurrence), `role: str | None = None` (`"show" | "id" | "next" | "later"`), `miss: bool | None = None` (set on a block's first show row), `degraded: bool = False`, `fill: str | None = None` (`"pool-short" | "structural"` on fill shows), `bends: tuple[str, ...] = ()`, `names: tuple[tuple[str, str], ...] = ()` (announcement rows: `(block, nominal_start)` of each named occurrence), `package: str | None = None`, `announcement_broken: bool = False`, `extra: Mapping[str, Any]` (unknown keys, default empty, excluded from equality).
  `PlanRow.from_json(data)` puts unknown keys in `extra`; `to_json()` writes known fields then `extra` keys (known fields win on collision). Tuples serialize as JSON lists and parse back to tuples.

- [ ] **Step 1: Write the failing tests**

```python
# test_layout.py
def test_phase1_row_loads_with_defaults():
    r = PlanRow.from_json({"seq": 0, "slug": "a", "dir": "a", "key": "k", "start_frame": 0,
                           "frames": 10, "run_start": True, "cut_frame": None})
    assert r.kind == "show" and r.block is None and r.bends == () and dict(r.extra) == {}

def test_unknown_keys_survive_a_round_trip():
    data = {"seq": 1, "slug": "a", "dir": "a", "key": "k", "start_frame": 0, "frames": 10,
            "run_start": False, "cut_frame": None, "future_field": {"x": 1}}
    r = PlanRow.from_json(data)
    assert r.extra["future_field"] == {"x": 1}
    assert PlanRow.from_json(r.to_json()).to_json() == r.to_json()
    assert r.to_json()["future_field"] == {"x": 1}

def test_scheduler_fields_round_trip_as_tuples():
    r = PlanRow(seq=2, slug="ann-abc", dir="interstitials", key="k2", start_frame=5, frames=3,
                kind="interstitial", role="next", block="dead-evening",
                nominal_start="2096-10-02T23:00:00Z", names=(("dead-evening", "2096-10-02T23:00:00Z"),),
                bends=("era",))
    back = PlanRow.from_json(json.loads(json.dumps(r.to_json())))
    assert back == r and back.names == (("dead-evening", "2096-10-02T23:00:00Z"),)
```

```python
# test_planner.py
def test_read_plan_keeps_unknown_keys_through_write(tmp_path):
    p = tmp_path / "plan.jsonl"
    p.write_text(json.dumps({"seq": 0, "slug": "a", "dir": "a", "key": "k", "start_frame": 0,
                             "frames": 441, "run_start": True, "cut_frame": None, "zz": 7}) + "\n")
    rows = read_plan(p)
    write_plan(p, rows)
    assert json.loads(p.read_text())["zz"] == 7

def test_read_plan_still_type_checks_known_fields(tmp_path):
    p = tmp_path / "plan.jsonl"
    p.write_text(json.dumps({"seq": "0", "slug": "a", "dir": "a", "key": "k", "start_frame": 0,
                             "frames": 441, "run_start": True, "cut_frame": None}) + "\n")
    with pytest.raises(PlanError):
        read_plan(p)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_layout.py packages/transmitter/tests_transmitter/test_planner.py -q`
Expected: FAIL (unexpected keyword / missing attributes).

- [ ] **Step 3: Implement**

`PlanRow` stays a frozen dataclass; `extra` is `field(default_factory=dict, compare=False)` typed `Mapping[str, Any]` (wrap in `types.MappingProxyType` so the frozen row is not mutated through it). `from_json` splits known/unknown keys via `dataclasses.fields`, converts `bends` to a tuple and `names` to a tuple of 2-tuples. `planner._parse_row` keeps its integer/string/bool checks on the phase-1 fields and adds: `kind` in `{"show", "interstitial"}`, `bends`/`names` are tuples after parsing. `validate_rows` is unchanged.

- [ ] **Step 4: Run the transmitter suite**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`
Expected: all PASS.

- [ ] **Step 5: Runbook note**

In `docs/playout-setup.md`, under the operations/rollback material, add a short "Rolling transmitter back" subsection: the oldest safe rollback target is this task's commit (an older build rejects scheduler rows and wedges plan, render and publish); never truncate `plan.jsonl` by hand; before rolling back past Task 5, remove `[interstitials]` from `config.toml`.

- [ ] **Step 6: Commit**

```bash
git add packages/transmitter/src/transmitter/layout.py packages/transmitter/src/transmitter/planner.py \
  packages/transmitter/tests_transmitter/test_layout.py packages/transmitter/tests_transmitter/test_planner.py docs/playout-setup.md
git commit -m "transmitter: tolerant plan rows with scheduler fields (deploy before the scheduler)"
```

**Operator checkpoint (after Task 1):** this commit is meant to be deployed to hugo on its own, before the scheduler lands, so any later rollback lands on a reader that tolerates scheduler rows. The orchestrator reports it ready to deploy and continues; deployment is the operator's.

---

### Task 2: Plan lock

**Files:**
- Create: `packages/transmitter/src/transmitter/locks.py`
- Modify: `packages/transmitter/src/transmitter/errors.py`, `workspace.py`, `service.py:300-325`, `cli.py:604-624`
- Test: `packages/transmitter/tests_transmitter/test_locks.py`, `test_service.py`, `test_cli.py`

**Interfaces:**
- Produces: `errors.PlanLocked(TransmitterError)`; `Workspace.plan_lock_path -> root / "plan.lock"`; `locks.plan_lock(ws: Workspace) -> ContextManager[None]` (non-waiting `fcntl.flock(LOCK_EX | LOCK_NB)`, raises `PlanLocked("another transmitter plan or render holds the lock (is `transmitter run` running?); not waiting")`, mirroring `publish.publish_lock`).
- The service wraps each of its plan and render step bodies in `plan_lock`; `Runner._step` treats `PlanLocked` exactly like `PublishLocked` (warning, step skipped, returns False). The `plan` and `render` CLI commands take the lock around their whole body (refusal → `error: …`, exit 1 via `main_cli`). `status` and (later) `schedule` take no lock.

- [ ] **Step 1: Write the failing tests**

```python
# test_locks.py
def test_plan_lock_refuses_a_second_holder(tmp_path):
    ws = Workspace(tmp_path)
    with plan_lock(ws):
        with pytest.raises(PlanLocked):
            with plan_lock(ws):
                pass
    with plan_lock(ws):      # released
        pass
```

```python
# test_cli.py
def test_plan_and_render_refuse_while_locked(tmp_path, monkeypatch):
    # build a config pointing root at tmp_path (as the existing cli tests do), hold plan_lock, invoke
    # `transmitter plan` and `transmitter render` through main_cli/CliRunner: each exits 1 with
    # "another transmitter plan or render holds the lock" on stderr and plan.jsonl is not created.
```

```python
# test_service.py
def test_tick_skips_plan_and_render_while_the_plan_lock_is_held(tmp_path):
    # Runner over make_station + a fake publisher (as existing tick tests do), filling=True;
    # hold plan_lock(st.ws) during runner.tick(NOW): plan.jsonl unchanged, no "plan"/"render"
    # alert fired, publish still ran.
```

- [ ] **Step 2: Run to verify failure**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_locks.py packages/transmitter/tests_transmitter/test_cli.py packages/transmitter/tests_transmitter/test_service.py -q`
Expected: FAIL (`ModuleNotFoundError: transmitter.locks`).

- [ ] **Step 3: Implement** as in Interfaces.

- [ ] **Step 4: Run the transmitter suite** — Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter/src/transmitter/{locks,errors,workspace,service,cli}.py packages/transmitter/tests_transmitter/test_{locks,service,cli}.py
git commit -m "transmitter: plan lock around plan and render (service skips, CLI refuses)"
```

---

### Task 3: Estimate inputs, estimates, and the hugo premise probe

**Files:**
- Create: `packages/transmitter/src/transmitter/mp3info.py`, `packages/transmitter/src/transmitter/pieces.py` (estimate part only), `packages/transmitter/scripts/probe_estimates.py`
- Modify: `packages/transmitter/src/transmitter/station.py:89-101, 202-212`
- Test: `test_mp3info.py`, `test_pieces.py`, `test_station.py`

**Interfaces:**
- Produces:
  - `station.file_set_key_and_sizes(pkg_dir, rels) -> tuple[str, dict[str, int]]` (one stat per entry; `file_set_key` delegates to it, same key bytes).
  - `Show.meta` additionally carries `"total_duration_sec": float | None` (manifest top-level), `"voiced_profile": str | None` (`dj_audio.profile` when a non-empty string, else `source.profile`), `"sizes": dict[str, int]` (broadcast.m3u entry → bytes). Existing meta keys unchanged.
  - `mp3info.mp3_seconds(path: Path) -> float | None`: skips an ID3v2 tag (syncsafe size), finds the first MPEG audio frame sync, reads version/layer/bitrate index/sample rate (MPEG-1/2/2.5 Layer III), returns `(file_size - audio_offset) * 8 / bitrate`; `None` when no valid frame header is found in the first 64 KiB.
  - `pieces.estimate_frames(show: Show, *, pause_samples: int, extra: int, clip_seconds: Callable[[Path], float | None] = mp3info.mp3_seconds) -> int`: seconds = `total_duration_sec` (0 when None) + Σ clip seconds (a clip whose length is None counts `CLIP_FALLBACK_SECONDS = 120.0`); samples = `round(seconds * 44100) + pause_samples * n_clip_joins` (a join is each boundary between consecutive entries where either side is a clip, as `render.show_layout` counts); return `aacenc.frames_for(aacenc.pad_to_frame(samples), extra)`.
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
    # Show with entries clip, track, track, clip; meta total_duration_sec=100.0;
    # clip_seconds=lambda p: 5.0; pause_samples=33075; extra=1
    # samples = round(110 * 44100) + 2 * 33075 -> frames_for(pad_to_frame(samples), 1)

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

**Operator checkpoint (after Task 3, non-blocking):** the orchestrator asks the operator to run `probe_estimates.py` on hugo (and `--time-one` on one long package) and paste the summary. The spec's premise is "estimates land within seconds"; if the median absolute difference exceeds 60 s or the max exceeds 5 min, the orchestrator stops and escalates before Task 8. Tasks 4-7 may proceed meanwhile.

---

### Task 4: The clock

**Files:**
- Create: `packages/transmitter/src/transmitter/clock.py`
- Modify: `packages/transmitter/src/transmitter/workspace.py` (`clock_path`, `clock_last_good_path`)
- Test: `packages/transmitter/tests_transmitter/test_clock.py`

**Interfaces:**
- Produces (pydantic models on a local strict base, as `config._StrictModel`):
  - `Zone(tz: str, label: str)`; `AnnounceConfig(next, next_one, later, later_one: str; time_format: Literal["short12", "hm12", "24h"] = "short12"; zones: list[Zone] = <Eastern, Pacific>)`.
  - `Prefer(years: str | None = None, on_this_day: float | None = None, weight: float = 1.0)` — exactly one of `years`/`on_this_day`; `years` is `"YYYY"` or `"YYYY-YYYY"`; `on_this_day` is a weight overriding the global one for that block.
  - `BlockConfig(name: str, title: str | None = None, days: Literal["daily"] | list[Literal["mon","tue","wed","thu","fri","sat","sun"]] = "daily", start: str ("HH:MM"), profiles: list[str] = [], max_shows: int | None = None (≥1), wiggle_minutes: float | None = None, early_minutes: float | None = None, late_minutes: float | None = None, prefer: list[Prefer] = [])` — `early`/`late` both set or neither; not with `wiggle_minutes`.
  - `OpenConfig(exclude_profiles: list[str] = [])`; `RotationConfig(concert_gap_days: float = 45, on_this_day_weight: float = 3.0)`.
  - `ClockConfig(timezone: str, wiggle_minutes: float = 15, announce: AnnounceConfig, open: OpenConfig, rotation: RotationConfig, block: list[BlockConfig] = [])` — validators: valid `zoneinfo` name (and each zone's `tz`), unique block names, no two blocks sharing a weekday and `start`, at least one block.
  - `IMPLICIT_CLOCK: ClockConfig` — timezone `America/New_York`, one block `name="open"`, no title, daily `00:00`, no profiles, `wiggle_minutes=720` (so every landing is in window).
  - `load_clock(path: Path) -> ClockConfig` (raises `ConfigError` with the file path on parse or validation failure).
  - `LiveClock(clock: ClockConfig, source: Literal["clock", "last-good", "implicit"], problem: str | None)`; `live_clock(ws: Workspace) -> LiveClock`: no `clock.toml` → implicit; valid → `clock`, and `clock.last-good.toml` rewritten (atomic) when its bytes differ; invalid → the last-good copy if it loads (`source="last-good"`, `problem` = the error text), else implicit with `problem`. Never raises `ConfigError`.
  - `Occurrence(block: BlockConfig, nominal_us: int, lo_us: int, hi_us: int, end_us: int, local_date: datetime.date)` with `@property nominal_iso` (`grid.us_to_iso`) and `key -> tuple[str, str]` = `(block.name, nominal_iso)`; `max_shows` property: block's, else 2 for a profile block, 6 for an open block; `is_open` = no profiles.
  - `occurrences(clock: ClockConfig, from_us: int, until_us: int) -> list[Occurrence]` — every occurrence whose span `[nominal_us, end_us)` intersects `[from_us, until_us)`, in time order; `end_us` is the next occurrence's `nominal_us`; zero-length occurrences dropped; window `lo = nominal - early`, `hi = nominal + late` (wiggle when symmetric).
- Local time: `datetime(..., tzinfo=ZoneInfo(tz))` with `fold=0`; a nonexistent time resolves forward: detect by round-tripping through UTC (if the round-tripped wall time differs, use the instant `zoneinfo` gives for `fold=0` and then take the first valid instant at or after it, i.e. the transition instant).

- [ ] **Step 1: Failing tests** (`test_clock.py`)

```python
def test_weekday_rotation_expands_by_day():
    # blocks: funk mon 22:00, southern tue..sun 22:00 (same start, disjoint days); 7 days from a Monday 00:00 local
    # -> 7 occurrences at 22:00 local, Monday's block "funk", the rest "southern"

def test_block_runs_to_the_next_start_across_midnight():
    # blocks 19:00 and 02:00 daily -> the 19:00 occurrence's end_us is the next day's 02:00

def test_spring_forward_collapses_and_drops():
    # America/New_York, 2027-03-14: blocks 02:30 and 03:00 daily -> 02:30 resolves to 03:00 (07:00Z),
    # zero length with the 03:00 one, dropped; exactly one occurrence at 07:00Z that day

def test_fall_back_ambiguous_uses_first_occurrence():
    # 2027-11-07 01:30 local -> 05:30Z (EDT), not 06:30Z

def test_asymmetric_window():
    # early_minutes=0, late_minutes=15 -> lo == nominal, hi == nominal + 15 min

def test_duplicate_day_and_start_is_a_config_error(tmp_path): ...
def test_unknown_key_is_a_config_error(tmp_path): ...
def test_wiggle_and_early_late_together_is_an_error(tmp_path): ...

def test_live_clock_prefers_file_and_saves_last_good(tmp_path):
    ws = Workspace(tmp_path); ws.clock_path.write_text(VALID)
    lc = live_clock(ws)
    assert lc.source == "clock" and ws.clock_last_good_path.read_text() == VALID

def test_invalid_clock_falls_back_to_last_good(tmp_path):
    # after a valid load, overwrite clock.toml with "block = 3" -> source "last-good", problem mentions clock.toml

def test_invalid_clock_with_no_copy_is_implicit(tmp_path): ...       # source "implicit", problem set
def test_no_clock_file_is_implicit_without_problem(tmp_path): ...     # source "implicit", problem None
def test_open_block_defaults_to_six_shows_profile_block_to_two(): ...
```

- [ ] **Step 2: Run to verify failure.** Expected: FAIL (`ModuleNotFoundError`).
- [ ] **Step 3: Implement** as in Interfaces.
- [ ] **Step 4: Run the transmitter suite.** Expected: all PASS.
- [ ] **Step 5: Commit**

```bash
git add packages/transmitter/src/transmitter/{clock,workspace}.py packages/transmitter/tests_transmitter/test_clock.py
git commit -m "transmitter: the clock file, last-good copy, weekly expansion with DST rules"
```

---

### Task 5: Interstitials and announcements

**Files:**
- Create: `packages/transmitter/src/transmitter/interstitials.py`, `packages/transmitter/src/transmitter/announce.py`
- Modify: `packages/transmitter/src/transmitter/config.py` (`InterstitialsConfig(dir: Path | None = None)` on `TransmitterConfig.interstitials`; add to `DEFAULT_CONFIG_TOML` commented, keep `test_template_parses_to_the_defaults` green), `cli.py` (`announcements` command)
- Test: `test_interstitials.py`, `test_announce.py`, `test_cli.py`, `test_render.py`

**Interfaces:**
- Produces:
  - `interstitials.folder(cfg: TransmitterConfig) -> Path | None` — `cfg.interstitials.dir`, else `<station root>/interstitials`, else None (no station root).
  - `interstitials.row_dir(cfg, folder: Path) -> str` — the folder relative to the station root when inside it (`"interstitials"`), else its absolute path string. `Path(station_root) / row_dir` resolves back to the folder either way.
  - `interstitials.scan(folder: Path | None, *, now_s: float, quiet_s: float) -> list[Show]` — one `Show` per `id-*.mp3` / `ann-*.mp3` file older than the quiet period (mtime) and non-empty: `slug` = stem, `dir` = folder, `entries = (Entry(name, "clip", "Station ID" | "Announcement"),)`, `key = station.file_set_key(folder, [name])`, `meta = {"role": "id" | "ann", "ann_id": <id or None>}`. Missing folder → `[]`; an `OSError` on one file skips that file. Sorted by slug.
  - `announce.render_time(us: int, ann: AnnounceConfig) -> str` — for each zone in order: local hour/minute, formatted (`short12`: `"11"`, `"11:30"`, `"1"`; `hm12`: `"11:00"`; `24h`: `"23:00"`) then `" " + label`; zones joined with `", "`. E.g. `"11 Eastern, 8 Pacific"`.
  - `announce.render(template: str, first: Occurrence, second: Occurrence | None, ann: AnnounceConfig) -> str` — `str.format` with `title`, `time`, `next_title`, `next_time`.
  - `announce.ann_id(text: str) -> str` — first 12 hex chars of `sha256(text.encode())`.
  - `announce.Form = Literal["next", "next_one", "later", "later_one"]`.
  - `announce.text_for(form: Form, x: Occurrence, y: Occurrence | None, ann) -> str` (the template keyed by `form`).
  - `announce.Needed(id: str, text: str, form: Form, block: str, nominal_iso: str)`; `announce.needed(clock: ClockConfig, from_us: int, days: float = 8) -> list[Needed]` — for each occurrence X with a title in the span: `next_one` and `later_one`; plus `next` and `later` when the occurrence after X has a title. Deduplicated by id, in time order.
  - CLI `transmitter announcements [--clock FILE] [--days N] [--export DIR]` — lists `id  present|missing  text`, using the live clock (`live_clock`) or `--clock` (`load_clock`, errors exit 1); `--export` writes `ann-<id>.txt` (UTF-8 text, trailing newline) for each missing one into DIR (created if absent) and prints how many; never writes elsewhere.

- [ ] **Step 1: Failing tests**

```python
# test_interstitials.py
def test_scan_finds_ids_and_announcements(tmp_path): ...  # id-hello.mp3, ann-0123456789ab.mp3, notes.txt
    # -> two Shows, roles id/ann, ann_id "0123456789ab", entries kind "clip", dir == folder
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
    # needed ids as ann-<id>.txt with the exact rendered text; the present one is not exported
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

### Task 6: Pieces and pools

**Files:**
- Modify: `packages/transmitter/src/transmitter/pieces.py`
- Test: `packages/transmitter/tests_transmitter/test_pieces.py`

**Interfaces:**
- Consumes: Task 3 `estimate_frames`; Task 5 `interstitials.scan`, `row_dir`; `analysis.load_cached`; `render.planned_frames`.
- Produces:
  - `Piece` (frozen dataclass): `kind: Literal["show", "interstitial"]`, `show: station.Show`, `dir: str` (the `PlanRow.dir` to write), `frames: int`, `exact: bool`, and derived properties `slug`, `key` (from `show`), `package` (show slug for shows, None for clips), `artist`, `date` (`"YYYY-MM-DD"` or None), `year` (int or None), `month_day` (`"MM-DD"` or None), `profile` (`meta["voiced_profile"]`), `role` (`"show"` for shows, else `meta["role"]`), `ann_id`.
  - `LengthCache(cache_dir: Path, pause_samples: int, extra: int)` with `length(show: Show) -> tuple[int, bool]` — exact `planned_frames` when `load_cached(cache_dir, show.key)` hits (memoised by key), else `estimate_frames` (memoised by key), `exact=False`; `mark_exact(key: str, frames: int)` records an exact count learned this process.
  - `build_pool(shows: Sequence[Show], clips: Sequence[Show], *, lengths: LengthCache, clip_dir: str, analyze_clip: Callable[[Show], int]) -> list[Piece]` — shows become `kind="show"`, `dir=show.dir.name`; clips `kind="interstitial"`, `dir=clip_dir`. Interstitial pieces are always exact: `analyze_clip` (the Station's `frames_of`) is called for every clip `lengths` does not already know exactly, and the result recorded with `mark_exact` (clips are short). A clip whose analysis raises `TransmitterError` is left out of the pool (logged by the caller).
  - `scan_delivered(root: Path) -> list[Piece]` — for `--library delivered`: every non-dot package dir with a readable v3+ manifest, voiced or not: a `Show` built from the manifest only (entries from tracks, plus the DJ clips when voiced), `key = "m-" + sha256(f"{mtime_ns}:{size}" of manifest.json)[:20]`, estimate = `total_duration_sec` + (`UNVOICED_CLIP_ALLOWANCE_SECONDS` when unvoiced, else clip sizes via `mp3_seconds`), all `exact=False`. Never decodes, never writes.

- [ ] **Step 1: Failing tests**

```python
def test_cached_analysis_gives_an_exact_length(tmp_path): ...       # write a ShowAnalysis json under cache/<key>.json
def test_uncached_show_is_estimated_and_marked(tmp_path): ...
def test_mark_exact_overrides_the_estimate(tmp_path): ...
def test_build_pool_analyses_every_clip(tmp_path): ...              # analyze_clip called once per clip; pieces exact
def test_piece_properties_from_meta(tmp_path): ...                  # artist/date/year/month_day/profile/role
def test_scan_delivered_includes_unvoiced_with_allowance(tmp_path):
    # build_package(voiced=False) with total_duration_sec=3600 -> frames for 3600 + 240 s, exact False
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

### Task 7: Rotation history

**Files:**
- Create: `packages/transmitter/src/transmitter/history.py`
- Modify: `packages/transmitter/src/transmitter/workspace.py` (`aired_path -> root / "aired.jsonl"`), `service.py` (append in `_tick` after publish; backfill when `aired.jsonl` is absent)
- Test: `test_history.py`, `test_service.py`

**Interfaces:**
- Produces:
  - `AiredRow` (frozen): `epoch_id, start_frame, end_frame, kind, slug, package, block, nominal_start, role, miss, degraded, fill, bends, announcement_broken, start, end` (ISO strings). `from_json` ignores unknown keys.
  - `aired_rows_due(rows: Sequence[PlanRow], epoch: Epoch, pub_last: int | None, now_us: int) -> list[AiredRow]` — rows whose `end_frame` (cut end included) is at or before the end of segment `pub_last` (`(pub_last + 1) * SEGMENT_FRAMES`) and whose end instant is at or before `now_us`.
  - `append_aired(ws: Workspace, epoch: Epoch, rows: Sequence[PlanRow], pub_last: int | None, now_us: int) -> int` — appends (one `json.dumps` line each, `open(..., "a")` then `flush`+`fsync`) only rows whose identity `(epoch_id, start_frame)` is not already in the file; returns how many. A first call with no file is the backfill (same rule).
  - `load_aired(ws) -> list[AiredRow]` — a corrupt line is skipped with a log warning, never raises.
  - `Recency` with `last_aired_us(package: str) -> int | None`, `last_used_us(clip_slug: str) -> int | None`, `artists_on(local_date) -> list[str]`, `artist_years_on(local_date) -> list[tuple[str, int]]`, and `with_piece(piece, start_us, local_date) -> Recency` (a new index, for the projection's own choices). Built by `recency(aired: Sequence[AiredRow], rows: Sequence[PlanRow], epoch: Epoch, tz: str, meta_of: Callable[[str], tuple[str | None, str | None]])` — union of aired rows and persisted plan rows (deduped by identity); `meta_of(package)` gives `(artist, date)` from the current scan, unknown → `(None, None)`.
- Service: after `publish_all` in `_tick`, call `history.append_aired` (inside its own `_step("history", …)`; failures alert `history`, never stop the tick).

- [ ] **Step 1: Failing tests**

```python
def test_only_published_and_past_rows_are_appended(tmp_path): ...
def test_append_is_idempotent_across_restarts(tmp_path):
    # append_aired twice with the same inputs -> second returns 0, file has one line per row
def test_a_cut_row_records_its_cut_end(tmp_path): ...
def test_backfill_from_a_phase1_plan(tmp_path): ...               # rows without scheduler fields -> kind "show"
def test_corrupt_line_is_skipped(tmp_path): ...
def test_recency_counts_persisted_unaired_rows(tmp_path): ...
def test_artists_on_uses_the_clock_timezone(tmp_path): ...        # a show at 02:00Z counts on the previous local day in New York
```

```python
# test_service.py
def test_tick_appends_aired_rows_after_publishing(tmp_path): ...
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

### Task 8: Scores, rules and filling one block (Opus)

**Files:**
- Create: `packages/transmitter/src/transmitter/rules.py`, `packages/transmitter/src/transmitter/scheduler.py` (block filling part)
- Test: `test_rules.py`, `test_scheduler_block.py`, fixture `tests_transmitter/fixtures/library_durations.json`

**Interfaces:**
- Consumes: `Piece` (Task 6), `Occurrence`/`ClockConfig` (Task 4), `Recency` (Task 7).
- Produces (`rules.py`):
  - `RULES = ("adjacency", "gap", "artist_day", "era")` — hardest first; bend order is the reverse (era bends first).
  - `score(p: Piece, occ: Occurrence, rec: Recency, clock: ClockConfig, slot_us: int) -> float` = recency term (`1.0` never aired; else `0.9 * min(days_since / concert_gap_days, 1.0)`) + Σ matching `prefer` weights (`years` range contains `p.year`) + on-this-day weight (block override else `rotation.on_this_day_weight`) when `p.month_day` equals the slot's local month-day.
  - `violations(seq: Sequence[Piece], prev_artist: str | None, occ, rec, clock, starts_us: Sequence[int]) -> tuple[int, int, int, int]` — counts per rule for a candidate sequence of shows placed at `starts_us`: adjacency (same artist as the previous show, the first compared to `prev_artist`), gap (aired within `concert_gap_days`, or twice in this sequence), artist_day (artist already on that local date, including earlier in the sequence), era (same artist and year already on that local date).
  - `tie_rank(seed: int, slug: str) -> str` — `planner.shuffle_rank` moved here (planner keeps a re-export until Task 10 removes the shuffle).
- Produces (`scheduler.py`, part 1):
  - `BlockPlan` (frozen): `shows: tuple[Piece, ...]`, `fill_from: int | None` (index of the first fill show), `fill_cause: str | None` (`"pool-short" | "structural"`), `tier: int` (0 own profile in window, 1 with fill in window, 2 miss), `landing_frame: int` (where the next block's first show would start), `bends: tuple[str, ...]`, `degraded: bool`.
  - `fill_block(occ: Occurrence, next_occ: Occurrence, *, start_frame: int, placed: Sequence[Piece], own_pool: Sequence[Piece], open_pool: Sequence[Piece], boundary_frames: int, final_boundary_frames: int, prev_artist: str | None, rec: Recency, clock: ClockConfig, epoch_us: int, seed: int, used: frozenset[str]) -> BlockPlan`.

**Algorithm (`fill_block`), the decisions this task owns:**
- Positions: shows follow `start_frame` back to back with `boundary_frames` between consecutive shows (gap + typical clip + gap) and `final_boundary_frames` after the last (into the next block). `landing_frame` = end of the last show + `final_boundary_frames`. In window ⇔ `next_occ.lo_us <= landing_us <= next_occ.hi_us`.
- `placed` = shows of this occurrence already in the persisted plan; they count toward `max_shows` and supply `prev_artist`.
- Own pool empty → `degraded=True`, and the block is filled as open time from `open_pool` (its `max_shows` becomes 6).
- Candidates: drop pieces in `used` (slugs chosen earlier in this projection) only when the pool has other candidates (else allow, the gap rule then counts it). Rank candidates by `score` (tie: `tie_rank`).
- Tier 0 — own shows only, `k = 1 .. max_shows - len(placed)` shows: singles over every candidate; pairs with the first from the top 32 by score and the second from any candidate landing the window; for `k > 2`, extend greedily (highest score whose addition keeps the landing at or before `hi`) until two slots remain, then the single/pair search. Keep options landing in window.
- Tier 1 — only when tier 0 is empty: for the best 5 own prefixes (≥ 1 own show when the own pool is non-empty, else 0) whose landing is before `hi`, fill the remainder from `open_pool` minus own-pool pieces with up to 3 fill shows by the same single/pair/greedy search. Cause `"structural"` when the `max_shows` longest own candidates together still land before `lo`, else `"pool-short"`.
- Tier 2 — miss: among own-only options with ≥ 1 own show (or the open pool when degraded), the one whose landing is closest to the window; ties prefer late over early.
- Order within a tier: `violations` lexicographically (fewest adjacency first, then gap, artist_day, era), then the larger of `mean(score) - 0.5 * |landing - nominal| / max(early, late)` (for tier 2 only the distance outside the window, then violations, then value), then `tie_rank` of the first show.
- Bends: for the chosen option, each rule it violates for which some option in the same tier had a zero count for that rule. Rules no option keeps are therefore never bends (single-artist pools, concert gap longer than the pool's airtime).
- A block whose window for the next block has already passed at `start_frame` and that has no placed show returns `shows=()` (the occurrence is absorbed by the previous overrun; the next block starts late).

- [ ] **Step 1: Build the fixture** — `fixtures/library_durations.json`: a list of `{slug, artist, date, profile, frames}` for ~300 shows drawn from the measured profile distribution (medians, p10/p90 in the spec's Intent section; Dead all one artist "Grateful Dead"). Commit a small generator note in the fixture's sibling `README.md` (generated once, deterministic seed).

- [ ] **Step 2: Failing tests** (`test_rules.py`, `test_scheduler_block.py`)

```python
def test_never_aired_outranks_recently_aired(): ...
def test_on_this_day_boost_uses_the_slot_local_date(): ...
def test_years_preference_adds_its_weight(): ...
def test_violations_count_each_rule(): ...

def test_single_show_landing_in_window_is_tier0(): ...
def test_pair_fills_a_long_block_from_its_own_profile():
    # 4 h jam block, own pool only 2 h and 1.9 h shows -> both chosen, tier 0
def test_own_profile_pair_beats_fill_even_when_pairing_breaks_adjacency():
    # single-artist Dead pool, block needs two shows: tier 0 pair chosen; "adjacency" not in bends
def test_fill_when_the_own_pool_cannot_reach_the_window():
    # own shows all short; tier 1 with fill_cause "pool-short"
def test_structural_fill_when_block_is_longer_than_max_shows_can_cover(): ...
def test_miss_keeps_the_blocks_own_profile():
    # every own show overruns: tier 2, one own show, landing late, no fill
def test_empty_pool_block_degrades_to_open_time(): ...
def test_scarce_pool_repeats_rather_than_degrading():
    # own pool of 2 shows both aired yesterday: still own profile, "gap" not a bend (no option kept it)
def test_bend_counted_only_when_a_keeping_option_existed(): ...
def test_overrun_previous_block_absorbs_this_one(): ...
def test_deterministic_with_seed_tiebreak(): ...
```

- [ ] **Step 3: Run to verify failure.** Expected: FAIL.
- [ ] **Step 4: Implement** per the algorithm above.
- [ ] **Step 5: Run the transmitter suite.** Expected: all PASS.
- [ ] **Step 6: Commit**

```bash
git add packages/transmitter/src/transmitter/{rules,scheduler,planner}.py packages/transmitter/tests_transmitter/test_{rules,scheduler_block}.py packages/transmitter/tests_transmitter/fixtures/
git commit -m "transmitter: scheduler block filling with tiers, rotation rules and bend accounting"
```

---

### Task 9: The projection: occurrences, interstitials, announcements (Opus)

**Files:**
- Modify: `packages/transmitter/src/transmitter/scheduler.py`
- Test: `packages/transmitter/tests_transmitter/test_scheduler.py`

**Interfaces:**
- Consumes: `fill_block` (Task 8); `occurrences` (Task 4); `announce.text_for`, `ann_id` (Task 5); `Recency.with_piece` (Task 7).
- Produces:
  - `SchedulerInput` (frozen): `rows: Sequence[PlanRow]` (persisted), `start_frame: int`, `run_start: bool`, `pool: Sequence[Piece]`, `clock: ClockConfig`, `rec: Recency`, `epoch_us: int`, `gap_frames: int`, `seed: int`.
  - `PlannedPiece` (frozen): `piece: Piece`, `start_frame: int`, `run_start: bool`, `block: str`, `nominal_start: str`, `role: str`, `miss: bool | None`, `degraded: bool`, `fill: str | None`, `bends: tuple[str, ...]`, `names: tuple[tuple[str, str], ...]`; `end_frame` property.
  - `project(inp: SchedulerInput, until_frame: int) -> list[PlannedPiece]` — pure; plans whole occurrences from the one containing `start_frame` until the occurrence containing `until_frame` plus two more (so every announcement's named blocks are known), and returns every piece in order. The live step appends only the first.
  - `to_row(pp: PlannedPiece, seq: int) -> PlanRow` (sets `kind`, `package`, every scheduler field).
- Raises `PlanError("no eligible packages to plan")` only when the pool holds no show at all.

**Algorithm (`project`), the decisions this task owns:**
- Pools: own pool of an occurrence = shows whose `profile` is in its `profiles`; open pool = shows whose profile is not in `[open] exclude_profiles` (empty → all shows, recorded as bend `"exclude_profiles"` on every fill/open show chosen from it).
- Continuation: `placed` for the first occurrence = persisted show rows whose `(block, nominal_start)` equals its key; `prev_artist` = artist of the last persisted show row (looked up via the pool by slug; None if unknown). Persisted rows without a `block` (phase 1) contribute nothing to `placed`.
- Phase A (shows): for each occurrence in turn call `fill_block` with `boundary_frames = 2 * gap_frames + typical_id_frames` (median ID length, 0 and no clip when the ID pool is empty) and `final_boundary_frames` the same; carry `start_frame` to `landing_frame`, add chosen shows to `used` and to the projection's `Recency` (`with_piece`) so later occurrences see them.
- Phase B (boundaries), walking the phase-A shows in order and laying every piece out exactly from `inp.start_frame` (gap layout: each piece starts at previous end + `gap_frames`; the first piece of a run uses `start_frame`/`run_start` as given):
  - Before the first show of occurrence X (not at a run start): try `next` for X (two-block form when the occurrence after X, Y, is titled and not degraded; else `next_one`); requires X titled and not degraded, and X's first show start (computed with this clip in place) within X's window, and when two-block, Y's projected first-show start within Y's window and Y not degraded. Fallback chain: two-block clip missing → one-block clip → station ID → nothing.
  - At the last internal boundary of occurrence W (the boundary before W's last show, counting fill shows), try `later` for the occurrence after W with the same rules; otherwise, and at every other internal boundary, a station ID.
  - Station ID choice: the ID clip with the oldest `last_used_us` (never used first; tie `tie_rank`), updating the projection's recency so consecutive boundaries rotate.
  - If the persisted plan ends with a show row, the first projected piece is that boundary's interstitial (or the next show when no clip applies); if it ends with an interstitial row, the first projected piece is a show.
  - `miss` on each occurrence's first show = its start outside `[lo, hi]`; `fill`, `bends`, `degraded` copied from the `BlockPlan`; `names` on announcement pieces.
- Exact frames are what the pieces carry; estimates only change where later pieces land in the projection, never a written row (Task 10 analyses before writing).

- [ ] **Step 1: Failing tests** (`test_scheduler.py`, using the Task 8 fixture plus a few one-clip interstitial pieces)

```python
def test_project_is_pure_and_deterministic(): ...
def test_first_piece_continues_a_partly_filled_block(): ...          # persisted row in occ X counts toward max_shows
def test_phase1_prefix_is_extended_mid_block(): ...                 # rows without block fields
def test_gap_layout_for_every_projected_piece(): ...                 # start == prev.end + gap_frames
def test_station_id_between_shows_rotates_least_recent_first(): ...
def test_next_announcement_at_block_start_names_x_and_y(): ...
def test_later_on_the_last_internal_boundary_only(): ...            # three-show open block: ID, later
def test_untitled_x_gets_an_id_not_an_announcement(): ...
def test_degraded_y_uses_the_one_block_form(): ...
def test_two_block_clip_missing_falls_back_to_one_block_then_id(): ...
def test_announcement_dropped_when_x_would_start_outside_its_window(): ...
def test_no_id_clips_means_plain_gaps(): ...
def test_overlapping_windows_resolve_as_a_late_start_and_a_miss(): ...
def test_exclude_profiles_bends_when_the_open_pool_is_empty(): ...
def test_plan_error_only_when_no_show_is_eligible(): ...
def test_until_frame_plus_two_occurrences_are_projected(): ...
```

- [ ] **Step 2: Run to verify failure.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the transmitter suite.** Expected: all PASS.
- [ ] **Step 5: Commit**

```bash
git add packages/transmitter/src/transmitter/scheduler.py packages/transmitter/tests_transmitter/test_scheduler.py
git commit -m "transmitter: scheduler projection with station IDs and truthful announcements"
```

---

### Task 10: Pipeline integration (Opus)

**Files:**
- Modify: `packages/transmitter/src/transmitter/pipeline.py` (Station gains `lengths: LengthCache`, `live: LiveClock`; `scan_pieces`; `extend` replaced; render re-validation), `planner.py` (remove `choose_next`, `extend`, `shuffle_rank` re-export), `service.py` (`row_analysis` interstitial-safe, clock alert)
- Test: `test_pipeline.py`, `test_planner.py` (drop shuffle tests), `test_service.py`

**Interfaces:**
- Consumes: Tasks 4-9.
- Produces:
  - `Station.scan_pieces(now_us) -> list[Piece]` — station scan + interstitial scan → `pieces.build_pool` (clips analysed via `frames_of`). Keeps `scan_now` for callers that need packages only.
  - `Station.clock() -> ClockConfig` — `clock.live_clock(ws)` each call; when `problem` is set, `alerts.alert("clock", problem + "; planning with the " + source + " clock")`, else `alerts.resolve("clock")`.
  - `Station.extend(rows, pool: list[Piece], now_us, *, start_frame, run_start, max_new=None) -> list[PlanRow]` — the loop: while the plan is short of `until_frame(now_us)` and under `max_new`: `run1 = project(...)[0]`; if `run1.piece` is not exact, `frames_of(run1.piece.show)` (on `TransmitterError` → log `skipping <slug>: <exc>`, drop it from the pool, continue), `lengths.mark_exact`, refresh the piece in the pool; `run2 = project(...)[0]`; append `to_row(run2)` if `run2.piece.exact` else `to_row(run1 with exact frames)`. Each appended non-run-start row must start at `prev.end_frame + gap_frames` (else `LayoutError`, an internal-bug guard). When appending a block's first show row, mark `announcement_broken=True` (and log `announcement-broken: <block> <nominal>`) if any persisted announcement row names its occurrence and this row has `miss` or `degraded`. `validate_rows` at the end.
  - Each `extend` call builds its `Recency` once: `history.recency(history.load_aired(ws), rows, epoch, clock.timezone, meta_of)` with `meta_of` from the pool's show pieces (`(artist, date)` by package slug).
  - `plan_step` uses `scan_pieces` and the new `extend`; recovery and fresh-run logic unchanged.
  - Two builder calls from the spec, settled here: no background analysis of the rest of the library (pieces are analysed only when chosen; estimates steer the search), and no trimming of `plan.jsonl` in this phase.
  - `render_step` re-validation: pieces keyed by `(kind, slug)` from `scan_pieces`; an interstitial row is valid when its slug is in the clip pool with the same key; exclusions apply to both kinds; re-plan cap `len(clip pool) + len(rows overlapping [n, target]) + 10`, exceeding it raises `PlanError("render re-planned <k> times in one call; stopping")`.
  - `service.row_analysis` returns None for interstitial rows (never evaluates them as packages).

- [ ] **Step 1: Failing tests** (`test_pipeline.py`; adapt `make_station` to write a `clock.toml` when a test needs one, otherwise the implicit clock)

```python
def test_written_rows_always_carry_exact_frames(tmp_path): ...   # estimates differ from FakeEngine's exact counts
def test_run2_pick_unanalysed_falls_back_to_run1(tmp_path): ...
def test_at_least_one_row_per_step_while_short(tmp_path): ...
def test_appended_rows_obey_the_gap_layout(tmp_path): ...
def test_append_only_under_a_clock_edit(tmp_path):
    # plan with clock A, edit clock.toml to B, plan again: every row of the first plan is unchanged, in place
def test_invalid_clock_alerts_and_plans_with_last_good(tmp_path): ...
def test_render_skips_a_vanished_interstitial_and_moves_on(tmp_path):
    # plan an ID row, delete the clip, render: plan-changed logged, the row dropped with the rest, re-extended, segments written
def test_render_replan_cap(tmp_path): ...
def test_interstitial_rows_are_rendered_from_the_clip_folder(tmp_path): ...
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
- [ ] **Step 5: Mutation check of the strict surface** — on a scratch copy run with `PYTHONPATH` shadowing (per the repo CLAUDE.md: never a `.venv/bin/*` script from a copy), apply each mutant and name the red test before running it:
  1. `extend` replaces the last persisted row instead of appending → expect `test_append_only_under_a_clock_edit` red.
  2. `extend` writes run 1's estimated frames → expect `test_written_rows_always_carry_exact_frames` red.
  3. gap assertion removed and the scheduler starts a row at `prev.end` → expect `test_appended_rows_obey_the_gap_layout` red.
  Record the three results in the task report.
- [ ] **Step 6: Commit**

```bash
git add packages/transmitter/src/transmitter/{pipeline,planner,service}.py packages/transmitter/tests_transmitter/test_{pipeline,planner,service}.py
git commit -m "transmitter: the scheduler drives plan and render; piece-aware re-validation; shuffle retired"
```

---

### Task 11: Timeline and player

**Files:**
- Modify: `packages/transmitter/src/transmitter/site.py:41-62`, `publish.py:239-249`, `antenna/public/nowplaying.js:51-57`, `antenna/public/player.js:161`, `antenna/test/nowplaying.test.ts`
- Test: `test_site.py`, `test_publish.py`, `antenna/test/nowplaying.test.ts`

**Interfaces:**
- `build_timeline` skips rows with `kind == "interstitial"` (they never appear in `shows` or `recent`); `_publish_site` does not call `analysis_for` for them; `anchors` stays `[]`.
- `nowPlayingText(np, timelineLoaded, stationName = "llama radio")`: no show → `stationName` when loaded (was "We'll be back shortly."), "Tuning in…" otherwise. `player.js` passes `document.title`. The off-air path (`hlsErrorNotice`, `classifyProbe`, offair page) is unchanged; verify by reading `player.js` that off-air sets its own text rather than calling `nowPlayingText`.

- [ ] **Step 1: Failing tests**

```python
def test_timeline_lists_no_interstitial_rows(): ...
def test_publish_site_never_asks_for_an_interstitial_analysis(tmp_path): ...
```

```ts
expect(nowPlayingText(null, true, "llama radio")).toBe("llama radio");
expect(nowPlayingText(null, false, "llama radio")).toBe("Tuning in…");
```

- [ ] **Step 2: Run to verify failure** — `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_site.py packages/transmitter/tests_transmitter/test_publish.py -q` and `cd antenna && npm test`. Expected: FAIL.
- [ ] **Step 3: Implement**; run `cd antenna && npm run pages` if `npm test`'s freshness check says `src/pages.ts` is stale.
- [ ] **Step 4: Run both suites.** Expected: all PASS.
- [ ] **Step 5: Commit**

```bash
git add packages/transmitter/src/transmitter/{site,publish}.py packages/transmitter/tests_transmitter/test_{site,publish}.py antenna/public antenna/src/pages.ts antenna/test/nowplaying.test.ts
git commit -m "transmitter, antenna: interstitials stay out of the timeline; the player shows the station name between shows"
```

---

### Task 12: `schedule`, `library` and `status`

**Files:**
- Modify: `packages/transmitter/src/transmitter/cli.py`, `service.py:418-449`
- Create: `packages/transmitter/src/transmitter/report.py` (pure formatting of projections and summaries)
- Test: `test_report.py`, `test_cli.py`, `test_service.py`

**Interfaces:**
- `report.block_views(rows: Sequence[PlanRow], projected: Sequence[PlannedPiece], clock, epoch) -> list[BlockView]` — one per occurrence: block, title, nominal and actual start (local, clock timezone), slip minutes, shows `(artist, date, minutes, estimated: bool)`, fill shows with cause, interstitials, miss, degraded, bends; `report.summary(views, span_us) -> Summary` (misses, fill minutes by cause and as a share of the span, bends by rule, shortest repeat gap in days).
- `transmitter schedule [--days 7] [--clock FILE] [--library eligible|delivered]` — no lock, writes nothing: persisted rows from now, then `project` from the end of the persisted plan through `--days` (live clock or `--clock`; `--library delivered` uses `pieces.scan_delivered` on estimates). Estimated lengths are marked `~`.
- `transmitter library` — eligible shows by profile: count, median, p10, p90 minutes; the interstitial pool (IDs, announcements); ineligible packages counted by first reason.
- `status_lines` replaces the `anchors none (...)` line with: `clock` line (`clock.toml` / `last-good (problem)` / `no clock: open all week`), current and next block from persisted rows, misses and fill minutes by cause for the last and next 24 h (persisted rows only), bend counts, degraded blocks, missing announcement audio (`announce.needed` for 8 days vs the folder). `status` never runs the scheduler or scans packages (the interstitials folder listing is a directory read).

- [ ] **Step 1: Failing tests**

```python
def test_block_views_report_slip_fill_cause_and_bends(): ...
def test_summary_counts(): ...
def test_schedule_writes_nothing(tmp_path):  # snapshot the workspace tree before/after `transmitter schedule`
def test_schedule_marks_estimates(tmp_path): ...
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

### Task 13: Measurement

**Files:**
- Create: `packages/transmitter/scripts/measure_scheduler.py`, `docs/superpowers/2026-10-2X-scheduler-measurement/{naive_filler.py,clock-a.toml,clock-b.toml,clock-c.toml,results.json,evidence.md}` (date = the day it runs)
- Test: `packages/transmitter/tests_transmitter/test_measure.py` (one smoke test on the fixture library)

**Interfaces:**
- `measure_scheduler.py --root PATH --clock FILE --weeks N [--library delivered|eligible] [--no-interstitials] --out JSON` — runs `project` week after week from an empty plan, feeding each week's chosen shows into the in-memory recency (history accumulates), on estimated lengths; writes per-week and total: block starts, misses, fill minutes by cause, bends by rule, repeat-gap distribution, share of block airtime on its own profile.
- `naive_filler.py` = `docs/superpowers/2026-10-10-playout-review/feasibility-sim.py` with: `--root` argument; anchors read from `clock-a.toml`; separate `overran` and `not_fillable` counts (no ×1000 weight); the scheduler's estimate (`pieces.estimate_frames` inputs: `total_duration_sec` + clip sizes, or the 4-minute allowance); fill exclusion read from `[open] exclude_profiles`; 50 seeds; JSON output.
- `clock-a.toml`: 07:00 dead, 12:00 bluegrass, 19:00 dead daily, Saturday 22:30 funk, Sunday 15:00 dead-family, `early_minutes = 0`, `late_minutes = 15`, `[open] exclude_profiles = ["dead", "funk", "dead-family"]`. `clock-b.toml`: the operator's shape (spec Measurement (b)). `clock-c.toml`: soft launch (Dead and funk blocks, open time).

- [ ] **Step 1: Smoke test** — `test_measure.py` runs the measurement function on the Task 8 fixture for 2 weeks and asserts the result keys and that `block_starts == 2 * occurrences_per_week`.
- [ ] **Step 2: Run to verify failure, implement, run.** Expected: PASS.
- [ ] **Step 3: Run the measurement** against `/Volumes/media/lma-radio/delivered` (read-only): clock (a) with `--library delivered --no-interstitials --weeks 50`, the naive script with 50 seeds; clocks (b) and (c) for 50 weeks (`c` also with `--library eligible`).
- [ ] **Step 4: Write `evidence.md`** — the numbers, the floor check (scheduler's share of block starts outside the window ≤ naive `overran + not_fillable`), and anything surprising. **Checkpoint:** if the floor fails, stop and escalate to the operator with the numbers before Task 14.
- [ ] **Step 5: Commit**

```bash
git add packages/transmitter/scripts/measure_scheduler.py packages/transmitter/tests_transmitter/test_measure.py docs/superpowers/2026-10-2X-scheduler-measurement
git commit -m "docs: scheduler measurement against the delivered library, with the like-for-like naive baseline"
```

---

### Task 14: Runbook and project notes

**Files:**
- Modify: `docs/playout-setup.md`, `CLAUDE.md` (transmitter paragraph), `packages/transmitter/src/transmitter/config.py` docstring/template if needed

- [ ] **Step 1: Runbook** — a "Clock and schedule" section: where `clock.toml` lives; edit a draft, check it with `transmitter schedule --clock draft.toml` then move it into place; what `status` says for an invalid clock; edits reach air after the persisted plan (about one lead plus one show). An "Announcements" section, copy-paste: `transmitter announcements --export <dir>`; on the Mac `cd /Volumes/media/lma-radio/delivered/interstitials && for f in ann-*.txt; do emcee say "$f"; done`; station IDs are any `id-*.mp3`. The rollback subsection from Task 1, extended with `[interstitials]`.
- [ ] **Step 2: CLAUDE.md** — update the transmitter Commands bullet (`schedule`, `library`, `announcements`, plan lock, `clock.toml`) and the architecture paragraph (append-only scheduler, pieces, interstitials folder, `aired.jsonl`), in the file's existing terse style.
- [ ] **Step 3: Full verification** — `./.venv/bin/python -m pytest -q` (whole repo), `cd antenna && npm test`, and `packages/transmitter/scripts/test-in-debian12.sh` (needs docker; if unavailable, say so in the report).
- [ ] **Step 4: Commit**

```bash
git add docs/playout-setup.md CLAUDE.md packages/transmitter/src/transmitter/config.py
git commit -m "docs: scheduler runbook (clock, announcements, rollback) and project notes"
```
