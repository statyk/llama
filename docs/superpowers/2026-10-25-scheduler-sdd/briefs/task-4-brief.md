### Task 4: The clock

**Files:**
- Create: `packages/transmitter/src/transmitter/clock.py`
- Modify: `packages/transmitter/src/transmitter/workspace.py` (`clock_path`, `clock_last_good_path`)
- Test: `packages/transmitter/tests_transmitter/test_clock.py`

**Interfaces:**
- Produces (pydantic models on a local strict base, as `config._StrictModel`):
  - `Zone(tz: str, label: str)`; `AnnounceConfig(next: str = DEFAULT_NEXT, next_one: str = DEFAULT_NEXT_ONE, later: str = DEFAULT_LATER, later_one: str = DEFAULT_LATER_ONE; time_format: Literal["short12", "hm12", "24h"] = "short12"; zones: list[Zone] = Field(default_factory=<Eastern, Pacific>))` — the four `DEFAULT_*` module constants are the Global Constraints templates.
  - `Prefer(years: str | None = None, on_this_day: float | None = None, weight: float = 1.0)` — exactly one of `years`/`on_this_day`; `years` is `"YYYY"` or `"YYYY-YYYY"`; `on_this_day` is a weight overriding the global one for that block.
  - `BlockConfig(name: str, title: str | None = None, days: Literal["daily"] | list[Literal["mon","tue","wed","thu","fri","sat","sun"]] = "daily", start: str ("HH:MM"), profiles: list[str] = [], max_shows: int | None = None (≥1; None = the default: 2 for a profile block, unbounded for an open block), wiggle_minutes: float | None = None, early_minutes: float | None = None, late_minutes: float | None = None, prefer: list[Prefer] = [])` — `early`/`late` both set or neither; not with `wiggle_minutes`.
  - `OpenConfig(exclude_profiles: list[str] = [])`; `RotationConfig(concert_gap_days: float = 45, on_this_day_weight: float = 3.0)`.
  - `ClockConfig(timezone: str, wiggle_minutes: float = 15, announce: AnnounceConfig = Field(default_factory=AnnounceConfig), open: OpenConfig = Field(default_factory=OpenConfig), rotation: RotationConfig = Field(default_factory=RotationConfig), block: list[BlockConfig] = [])` — validators: valid `zoneinfo` name (and each zone's `tz`), unique block names, no two blocks sharing a weekday and `start`, at least one block. A clock file of `timezone` plus `[[block]]`s is valid.
  - Load-time validation, so a clock that loads cannot crash planning (`live_clock` would otherwise save it as last-good): each template formats with dummy values for exactly its allowed fields (two-block forms `next`/`later`: `title`, `time`, `next_title`, `next_time`; one-block forms `next_one`/`later_one`: `title`, `time` only); an unknown field, a stray brace or a `next_*` field in a one-block form is a `ConfigError`. Each block's effective window must be positive (`wiggle_minutes > 0`, or `early_minutes + late_minutes > 0`). `days` is `"daily"` or a non-empty list.
  - `IMPLICIT_CLOCK: ClockConfig` — timezone `America/New_York`, one open block `name="open"`, no title, daily `00:00`, no profiles, `max_shows` None (unbounded), `wiggle_minutes=720` (a ±12 h window, so every landing is in window).
  - `load_clock(path: Path) -> ClockConfig` (raises `ConfigError` with the file path on parse or validation failure).
  - `LiveClock(clock: ClockConfig, source: Literal["clock", "last-good", "implicit"], problem: str | None)`; `live_clock(ws: Workspace, *, save: bool = True) -> LiveClock`: no `clock.toml` → implicit; valid → `clock`, and, when `save`, `clock.last-good.toml` rewritten (atomic) when its bytes differ; invalid → the last-good copy if it loads (`source="last-good"`, `problem` = the error text), else implicit with `problem`. Never raises `ConfigError`. Read-only callers (`status`, `schedule`, `announcements`) pass `save=False` and write nothing.
  - `Occurrence(block: BlockConfig, nominal_us: int, lo_us: int, hi_us: int, end_us: int, local_date: datetime.date)` with `@property nominal_iso` (`grid.us_to_iso`) and `key -> tuple[str, str]` = `(block.name, nominal_iso)`; `max_shows -> int | None` property: block's, else 2 for a profile block, None (unbounded) for an open block; `is_open` = no profiles.
  - `occurrences(clock: ClockConfig, from_us: int, until_us: int) -> list[Occurrence]` — every occurrence whose span `[nominal_us, end_us)` intersects `[from_us, until_us)`, in time order; `end_us` is the next occurrence's `nominal_us`; zero-length occurrences dropped; window `lo = nominal - early`, `hi = nominal + late` (wiggle when symmetric).
- Local time: `datetime(..., tzinfo=ZoneInfo(tz))` with `fold=0` (an ambiguous time takes its first occurrence). A nonexistent local time resolves to the transition instant: the first UTC instant whose local wall time is at or after the requested one.

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

def test_minimal_clock_loads_with_defaults(tmp_path): ...   # timezone + one [[block]]: default announce, open, rotation
def test_duplicate_day_and_start_is_a_config_error(tmp_path): ...
def test_unknown_key_is_a_config_error(tmp_path): ...
def test_wiggle_and_early_late_together_is_an_error(tmp_path): ...
def test_bad_template_is_a_config_error(tmp_path): ...       # "{titel}" and a stray "{" each -> ConfigError
def test_one_block_form_cannot_name_next(tmp_path): ...      # next_one = "... {next_title}" -> ConfigError
def test_zero_window_is_a_config_error(tmp_path): ...        # wiggle_minutes = 0; early 0 + late 0 -> ConfigError
def test_empty_days_is_a_config_error(tmp_path): ...         # days = [] -> ConfigError

def test_live_clock_prefers_file_and_saves_last_good(tmp_path):
    ws = Workspace(tmp_path); ws.clock_path.write_text(VALID)
    lc = live_clock(ws)
    assert lc.source == "clock" and ws.clock_last_good_path.read_text() == VALID

def test_live_clock_save_false_writes_nothing(tmp_path): ...  # valid clock.toml, save=False -> no last-good file
def test_invalid_clock_falls_back_to_last_good(tmp_path):
    # after a valid load, overwrite clock.toml with "block = 3" -> source "last-good", problem mentions clock.toml

def test_invalid_clock_with_no_copy_is_implicit(tmp_path): ...       # source "implicit", problem set
def test_no_clock_file_is_implicit_without_problem(tmp_path): ...     # source "implicit", problem None
def test_open_block_is_unbounded_profile_block_defaults_to_two(): ...
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

