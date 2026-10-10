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
