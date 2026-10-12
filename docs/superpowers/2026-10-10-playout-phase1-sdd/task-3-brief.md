### Task 3: Config, workspace, epoch, local state, `config init`

**Model hint:** sonnet

**Files:**
- Create: `packages/transmitter/src/transmitter/config.py`, `workspace.py`, `state.py`
- Modify: `packages/transmitter/src/transmitter/cli.py` (add `config init`)
- Create: `packages/transmitter/tests_transmitter/test_config.py`, `test_workspace.py`, `test_state.py`
- Modify: `packages/transmitter/tests_transmitter/test_cli.py`

**Interfaces:**
- Consumes: `grid` (Task 1), `errors.ConfigError`.
- Produces:
  - `transmitter.config`: `DEFAULT_ROOT`, `default_root() -> Path` (`$TRANSMITTER_ROOT` else `~/.transmitter`); models `StationConfig(root: Path|None, quiet_minutes=10.0)`, `PlannerConfig(seed=0, start_delay_minutes=10.0)`, `RenderConfig(ffmpeg="ffmpeg", lead_hours=24.0, low_water_hours=20.0, music_target_lufs=-16.0, speech_target_lufs=-16.0, clip_pause_seconds=0.75, show_gap_seconds=2.0)`, `PublishConfig(account_id, bucket, endpoint_url, batch_segments=360, daily_put_budget=17500, prune_margin_minutes=10.0, prune_min_segments=60, guard_check_minutes=15.0)`, `AntennaConfig(dir: Path|None, site_url: str|None, station_name="llama radio")`, `TransmitterConfig(root, station, planner, render, publish, antenna)`; `load_config(path=None) -> TransmitterConfig`; `DEFAULT_CONFIG_TOML: str`.
  - `transmitter.workspace`: `atomic_write_bytes(path, data)`, `atomic_write_text(path, text)`, `write_json(path, obj)`, `read_json(path, default=None)`; `Workspace(root)` with properties `plan_path, cache_dir, render_dir, shows_dir, epoch_path, publish_state_path, puts_path, guard_cache_path, fallback_path, lock_path` and methods `seg_dir(epoch_id)`, `fallback_dir(version)`; `Epoch(epoch_id, epoch_us)` with `.iso`, `.start_us(n)`, `.index_at(t_us)`; `load_epoch(ws) -> Epoch | None`; `load_or_create_epoch(ws, now_us) -> Epoch`.
  - `transmitter.state`: `PublishState(epoch_id=None, first=None, last=None, runs=[], notes={})`; `load_publish_state(ws)`, `save_publish_state(ws, state)`, `load_fallback_version(ws) -> str | None`, `save_fallback_version(ws, version)`.

- [ ] **Step 1: Write the failing tests**

`tests_transmitter/test_config.py`:

```python
import tomllib
from pathlib import Path

import pytest

from transmitter.config import (DEFAULT_CONFIG_TOML, DEFAULT_ROOT, TransmitterConfig,
                                default_root, load_config)
from transmitter.errors import ConfigError


def test_default_root(monkeypatch, tmp_path):
    monkeypatch.delenv("TRANSMITTER_ROOT", raising=False)
    assert default_root() == DEFAULT_ROOT == Path.home() / ".transmitter"
    monkeypatch.setenv("TRANSMITTER_ROOT", str(tmp_path))
    assert default_root() == tmp_path
    assert TransmitterConfig().root == tmp_path


def test_defaults():
    cfg = TransmitterConfig()
    assert cfg.render.lead_hours == 24.0 and cfg.render.low_water_hours == 20.0
    assert cfg.render.music_target_lufs == -16.0 and cfg.render.speech_target_lufs == -16.0
    assert cfg.render.clip_pause_seconds == 0.75 and cfg.render.show_gap_seconds == 2.0
    assert cfg.publish.prune_margin_minutes == 10.0 and cfg.publish.guard_check_minutes == 15.0
    assert cfg.publish.prune_min_segments == 60
    assert cfg.station.root is None


def test_missing_file_gives_defaults(tmp_path):
    assert load_config(tmp_path / "nope.toml") == TransmitterConfig()


@pytest.mark.parametrize("text", [
    "typo = 1\n",                       # top level
    "[render]\nlead_hour = 1\n",        # nested section: strictness must reach it
    "[publish]\nbuckett = 'x'\n",
])
def test_unknown_keys_are_errors(tmp_path, text):
    path = tmp_path / "config.toml"
    path.write_text(text)
    with pytest.raises(ConfigError, match="invalid config"):
        load_config(path)


def test_low_water_must_be_below_lead(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[render]\nlead_hours = 10\nlow_water_hours = 10\n")
    with pytest.raises(ConfigError):
        load_config(path)


def test_bad_toml_is_a_config_error(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[render\n")
    with pytest.raises(ConfigError):
        load_config(path)


def test_template_parses_to_the_defaults():
    parsed = TransmitterConfig.model_validate(tomllib.loads(DEFAULT_CONFIG_TOML))
    assert parsed.model_dump(exclude={"root"}) == TransmitterConfig().model_dump(exclude={"root"})
```

`tests_transmitter/test_workspace.py`:

```python
import pytest

from transmitter import grid
from transmitter.errors import ConfigError
from transmitter.workspace import (Epoch, Workspace, atomic_write_bytes, load_epoch,
                                   load_or_create_epoch, read_json, write_json)


def test_atomic_write_leaves_no_temp(tmp_path):
    target = tmp_path / "a" / "b.bin"
    atomic_write_bytes(target, b"one")
    atomic_write_bytes(target, b"two")
    assert target.read_bytes() == b"two"
    assert [p.name for p in target.parent.iterdir()] == ["b.bin"]


def test_json_round_trip_and_default(tmp_path):
    write_json(tmp_path / "x.json", {"a": 1})
    assert read_json(tmp_path / "x.json") == {"a": 1}
    assert read_json(tmp_path / "missing.json", {"d": 0}) == {"d": 0}


def test_workspace_paths(tmp_path):
    ws = Workspace(tmp_path)
    assert ws.plan_path == tmp_path / "plan.jsonl"
    assert ws.seg_dir("e1") == tmp_path / "render" / "seg" / "e1"
    assert ws.shows_dir == tmp_path / "render" / "shows"


def test_epoch_is_created_once_on_a_whole_second(tmp_path):
    ws = Workspace(tmp_path)
    now = grid.iso_to_us("2026-10-10T12:00:00Z") + 123_456
    e = load_or_create_epoch(ws, now)
    assert e.epoch_us == now - 123_456
    assert e.epoch_id == "e20261010T120000Z"
    assert e.iso == "2026-10-10T12:00:00.000Z"
    assert load_or_create_epoch(ws, now + 10**9) == e
    assert read_json(ws.epoch_path)["d"] == 10.24


def test_epoch_index_math():
    e = Epoch("x", 1_000_000)
    assert e.start_us(2) == 1_000_000 + 2 * grid.D_US
    assert e.index_at(e.start_us(2) + 5) == 2


def test_an_edited_d_is_refused(tmp_path):
    ws = Workspace(tmp_path)
    write_json(ws.epoch_path, {"epoch_id": "x", "epoch": "2026-10-10T12:00:00.000Z", "d": 6.0})
    with pytest.raises(ConfigError, match="epoch change"):
        load_epoch(ws)
```

`tests_transmitter/test_state.py`:

```python
from transmitter.state import (PublishState, load_fallback_version, load_publish_state,
                               save_fallback_version, save_publish_state)
from transmitter.workspace import Workspace


def test_publish_state_round_trip(tmp_path):
    ws = Workspace(tmp_path)
    assert load_publish_state(ws) == PublishState()
    state = PublishState(epoch_id="e1", first=10, last=20, runs=[[10, 20]], notes={"s": "abc"})
    save_publish_state(ws, state)
    assert load_publish_state(ws) == state


def test_fallback_version_round_trip(tmp_path):
    ws = Workspace(tmp_path)
    assert load_fallback_version(ws) is None
    save_fallback_version(ws, "3fa9c1d2e0b1")
    assert load_fallback_version(ws) == "3fa9c1d2e0b1"
```

Append to `tests_transmitter/test_cli.py`:

```python
from transmitter.config import DEFAULT_CONFIG_TOML


def test_config_init_writes_once(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSMITTER_ROOT", str(tmp_path))
    runner = CliRunner()
    first = runner.invoke(app, ["config", "init"])
    assert first.exit_code == 0
    assert (tmp_path / "config.toml").read_text() == DEFAULT_CONFIG_TOML
    second = runner.invoke(app, ["config", "init"])
    assert second.exit_code == 1


def test_config_init_stdout():
    result = CliRunner().invoke(app, ["config", "init", "--stdout"])
    assert result.exit_code == 0 and result.output == DEFAULT_CONFIG_TOML
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_config.py packages/transmitter/tests_transmitter/test_workspace.py packages/transmitter/tests_transmitter/test_state.py packages/transmitter/tests_transmitter/test_cli.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'transmitter.config'`.

- [ ] **Step 3: Implement**

`packages/transmitter/src/transmitter/config.py`:

```python
"""transmitter's config (`~/.transmitter/config.toml`). Strict, like llama's
and emcee's: a typo'd key is an error, not a silently ignored knob."""

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from transmitter.errors import ConfigError

DEFAULT_ROOT = Path.home() / ".transmitter"


def default_root() -> Path:
    root = os.environ.get("TRANSMITTER_ROOT")
    return Path(root) if root else DEFAULT_ROOT


class _StrictModel(BaseModel):
    """Unknown keys are an error. Set on a shared base because pydantic does
    not propagate model_config to nested models."""
    model_config = ConfigDict(extra="forbid")


class StationConfig(_StrictModel):
    root: Path | None = None                       # NFS path on hugo; needs `.station-root`
    quiet_minutes: float = Field(default=10.0, ge=0)


class PlannerConfig(_StrictModel):
    seed: int = 0
    # A fresh run (first start, or after an outage longer than the lead) begins
    # this far ahead of now: long enough to analyse, encode and upload the
    # first show's opening batch before it airs.
    start_delay_minutes: float = Field(default=10.0, gt=0)


class RenderConfig(_StrictModel):
    ffmpeg: str = "ffmpeg"
    lead_hours: float = Field(default=24.0, gt=0)
    low_water_hours: float = Field(default=20.0, gt=0)
    music_target_lufs: float = -16.0
    speech_target_lufs: float = -16.0
    clip_pause_seconds: float = Field(default=0.75, ge=0)
    show_gap_seconds: float = Field(default=2.0, ge=0)

    @model_validator(mode="after")
    def _low_water_below_lead(self):
        if self.low_water_hours >= self.lead_hours:
            raise ValueError("render.low_water_hours must be below render.lead_hours")
        return self


class PublishConfig(_StrictModel):
    account_id: str | None = None
    bucket: str | None = None
    endpoint_url: str | None = None
    batch_segments: int = Field(default=360, ge=1)
    # ~2x the expected daily count: 86400/10.24 = 8,438 segments, plus the
    # timeline/horizon/notes/page writes of each publish batch and prune's
    # horizon rewrites (at most one per prune_min_segments, ~141/day at 60)
    # ~= 8.9k/day.
    daily_put_budget: int = Field(default=17_500, ge=1)
    prune_margin_minutes: float = Field(default=10.0, ge=0)
    # prune (one horizon PUT + free deletes) only once this many are prunable
    prune_min_segments: int = Field(default=60, ge=1)
    guard_check_minutes: float = Field(default=15.0, ge=0)


class AntennaConfig(_StrictModel):
    dir: Path | None = None            # the repo's antenna/ (templates/show.html)
    site_url: str | None = None        # public base URL, for Open Graph links
    station_name: str = "llama radio"


class TransmitterConfig(_StrictModel):
    root: Path = Field(default_factory=default_root)
    station: StationConfig = Field(default_factory=StationConfig)
    planner: PlannerConfig = Field(default_factory=PlannerConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)
    publish: PublishConfig = Field(default_factory=PublishConfig)
    antenna: AntennaConfig = Field(default_factory=AntennaConfig)


def load_config(path: Path | None = None) -> TransmitterConfig:
    path = path or default_root() / "config.toml"
    if not path.exists():
        return TransmitterConfig()
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid config at {path}: {exc}") from exc
    try:
        return TransmitterConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"invalid config at {path}: {exc}") from exc


# Seeded by `transmitter config init`; kept equal to the defaults above by
# tests/test_config.py::test_template_parses_to_the_defaults.
DEFAULT_CONFIG_TOML = """\
# transmitter config - seeded by `transmitter config init`.
# A value here REPLACES its built-in default; unknown keys are errors.

# workspace (plan, caches, rendered audio); default ~/.transmitter or $TRANSMITTER_ROOT
# root = "/home/station/.transmitter"

[station]
# the delivered-packages folder (NFS on hugo); must contain a `.station-root`
# marker file, or `plan` refuses (a down NFS mount is an empty directory)
# root = "/nfs/media/station"
# a package must be untouched this long before it may air
quiet_minutes = 10.0

[planner]
# seed of the fixed shuffled order
seed = 0
# a fresh run (first start, or after an outage longer than the lead) begins
# this far ahead of now
start_delay_minutes = 10.0

[render]
ffmpeg = "ffmpeg"
# keep this much audio published ahead of now; render again below low water
lead_hours = 24.0
low_water_hours = 20.0
# per-show music loudness ceiling (tracks only) and per-clip speech target;
# gain = min(target - I, -1 dBTP - TP)
music_target_lufs = -16.0
speech_target_lufs = -16.0
# pause between a DJ clip and a track; gap between shows
clip_pause_seconds = 0.75
show_gap_seconds = 2.0

[publish]
# R2 endpoint is https://<account_id>.r2.cloudflarestorage.com unless
# endpoint_url is set. Keys come from the environment:
# R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY.
# account_id = "..."
# bucket = "llama-radio"
# endpoint_url = "https://..."
# segments per publish batch (state/horizon.json advances once per batch)
batch_segments = 360
# own-write cap: publishing stops (and alerts) past this many PUTs per UTC day
daily_put_budget = 17500
# delete segments that started more than this long ago
prune_margin_minutes = 10.0
# ...but only once this many are due (each prune rewrites state/horizon.json)
prune_min_segments = 60
# read state/guard.json at most this often
guard_check_minutes = 15.0

[antenna]
# the repo's antenna/ directory (the show-page template is templates/show.html)
# dir = "/home/station/llama/antenna"
# public base URL, for Open Graph links on show pages
# site_url = "https://radio.example.org"
station_name = "llama radio"
"""
```

`packages/transmitter/src/transmitter/workspace.py`:

```python
"""~/.transmitter layout, atomic writes, and the epoch (spec "transmitter --
state and commands"; "The core contract")."""

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from transmitter import grid
from transmitter.errors import ConfigError


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Unique temp file + rename: concurrent writers never interleave."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode())


def write_json(path: Path, obj: Any) -> None:
    atomic_write_text(path, json.dumps(obj, indent=2, sort_keys=True) + "\n")


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


@dataclass(frozen=True)
class Workspace:
    root: Path

    @property
    def plan_path(self) -> Path:
        return self.root / "plan.jsonl"

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache"

    @property
    def render_dir(self) -> Path:
        return self.root / "render"

    @property
    def shows_dir(self) -> Path:
        return self.render_dir / "shows"

    def seg_dir(self, epoch_id: str) -> Path:
        return self.render_dir / "seg" / epoch_id

    def fallback_dir(self, version: str) -> Path:
        return self.render_dir / "fallback" / version

    @property
    def epoch_path(self) -> Path:
        return self.root / "epoch.json"

    @property
    def publish_state_path(self) -> Path:
        return self.root / "publish.json"

    @property
    def puts_path(self) -> Path:
        return self.root / "puts.json"

    @property
    def guard_cache_path(self) -> Path:
        return self.root / "guard-cache.json"

    @property
    def fallback_path(self) -> Path:
        return self.root / "fallback.json"

    @property
    def lock_path(self) -> Path:
        return self.root / "publish.lock"


@dataclass(frozen=True)
class Epoch:
    epoch_id: str
    epoch_us: int

    @property
    def iso(self) -> str:
        return grid.us_to_iso(self.epoch_us)

    def start_us(self, n: int) -> int:
        return grid.segment_start_us(self.epoch_us, n)

    def index_at(self, t_us: int) -> int:
        return grid.segment_index_at(self.epoch_us, t_us)


_D_SECONDS = grid.D_US / 1_000_000


def load_epoch(ws: Workspace) -> Epoch | None:
    data = read_json(ws.epoch_path)
    if data is None:
        return None
    if data.get("d") != _D_SECONDS:
        raise ConfigError(f"{ws.epoch_path}: d={data.get('d')!r} is not {_D_SECONDS}; an epoch "
                          "change is a deliberate re-render-everything operation, not an edit")
    return Epoch(data["epoch_id"], grid.iso_to_us(data["epoch"]))


def load_or_create_epoch(ws: Workspace, now_us: int) -> Epoch:
    existing = load_epoch(ws)
    if existing is not None:
        return existing
    e_us = now_us - now_us % 1_000_000
    stamp = datetime.fromtimestamp(e_us // 1_000_000, tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    epoch = Epoch(f"e{stamp}", e_us)
    write_json(ws.epoch_path, {"epoch_id": epoch.epoch_id, "epoch": epoch.iso, "d": _D_SECONDS})
    return epoch
```

`packages/transmitter/src/transmitter/state.py`:

```python
"""Local publish state (`publish.json`): the authoritative mirror of what is in
R2 -- horizon first/last, every run of segment keys uploaded (or attempted:
a batch records its range before its first PUT) and not yet pruned (prune
deletes by these computed ranges; no List calls), and the digest of each
show's uploaded notes/page. Plus the current fallback version."""

from dataclasses import asdict, dataclass, field

from transmitter.workspace import Workspace, read_json, write_json


@dataclass
class PublishState:
    epoch_id: str | None = None
    first: int | None = None
    last: int | None = None
    runs: list[list[int]] = field(default_factory=list)
    notes: dict[str, str] = field(default_factory=dict)


def load_publish_state(ws: Workspace) -> PublishState:
    data = read_json(ws.publish_state_path)
    if data is None:
        return PublishState()
    return PublishState(epoch_id=data.get("epoch_id"), first=data.get("first"),
                        last=data.get("last"), runs=[list(r) for r in data.get("runs", [])],
                        notes=dict(data.get("notes", {})))


def save_publish_state(ws: Workspace, state: PublishState) -> None:
    write_json(ws.publish_state_path, asdict(state))


def load_fallback_version(ws: Workspace) -> str | None:
    data = read_json(ws.fallback_path)
    return data.get("version") if data else None


def save_fallback_version(ws: Workspace, version: str) -> None:
    write_json(ws.fallback_path, {"version": version})
```

In `cli.py`, add after the `app` definition (add `from pathlib import Path` and the config import at the top):

```python
from pathlib import Path

from transmitter.config import DEFAULT_CONFIG_TOML, default_root

config_app = typer.Typer(help="Config file utilities", pretty_exceptions_enable=False)
app.add_typer(config_app, name="config")


@config_app.command("init")
def config_init(
    stdout: bool = typer.Option(False, "--stdout", help="Print the default config instead of writing it"),
    config_path: Path = typer.Option(None, "--config", help="Target file (default: $TRANSMITTER_ROOT "
                                                            "or ~/.transmitter, then /config.toml)"),
):
    """Seed a config file with the baked-in defaults, commented."""
    if stdout:
        typer.echo(DEFAULT_CONFIG_TOML, nl=False)
        return
    target = config_path or default_root() / "config.toml"
    if target.exists():
        typer.echo(f"{target} already exists - not overwriting", err=True)
        raise typer.Exit(1)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(DEFAULT_CONFIG_TOML)
    typer.echo(f"wrote {target}")
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): strict config, workspace, epoch, local publish state, config init"
```

---

