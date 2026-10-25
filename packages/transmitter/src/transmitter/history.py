"""Rotation history (spec "Rotation history"): `aired.jsonl` holds one row per
plan row once it has been published and its air time has passed, and
`Recency` indexes those rows (plus persisted-but-unaired plan rows) for the
scheduler's rotation rules.

`aired.jsonl` is persisted state: reading is permissive (unknown keys ignored,
a corrupt line skipped with a warning, never raising). Identity is
`(epoch_id, start_frame)`, so a restart never double-appends."""

import json
import logging
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, fields
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from transmitter import grid
from transmitter.layout import PlanRow
from transmitter.workspace import Epoch, Workspace

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AiredRow:
    epoch_id: str
    start_frame: int
    end_frame: int
    kind: str
    slug: str
    package: str | None = None
    block: str | None = None
    nominal_start: str | None = None
    role: str | None = None
    miss: bool | None = None
    degraded: bool = False
    fill: str | None = None
    bends: tuple[str, ...] = ()
    announcement_broken: bool = False
    start: str = ""      # ISO UTC
    end: str = ""

    @property
    def identity(self) -> tuple[str, int]:
        return (self.epoch_id, self.start_frame)

    def to_json(self) -> dict:
        d = {f.name: getattr(self, f.name) for f in fields(self)}
        d["bends"] = list(self.bends)
        return d

    @classmethod
    def from_json(cls, data: dict) -> "AiredRow":
        known = {f.name for f in fields(cls)}
        kw = {k: v for k, v in data.items() if k in known}
        if "bends" in kw:
            if not isinstance(kw["bends"], (list, tuple)):
                raise TypeError(f"bends must be a list, got {kw['bends']!r}")
            kw["bends"] = tuple(str(b) for b in kw["bends"])
        return cls(**kw)


def package_of(row: PlanRow | AiredRow) -> str | None:
    """A show's package: the row's own, else its slug (phase-1 rows carry none)."""
    if row.kind != "show":
        return None
    return row.package or row.slug


def _start_us(epoch: Epoch, frame: int) -> int:
    return epoch.epoch_us + grid.frame_to_us(frame)


def _aired(row: PlanRow, epoch: Epoch) -> AiredRow:
    end = row.end_frame
    return AiredRow(
        epoch_id=epoch.epoch_id, start_frame=row.start_frame, end_frame=end, kind=row.kind, slug=row.slug,
        package=package_of(row), block=row.block, nominal_start=row.nominal_start, role=row.role,
        miss=row.miss, degraded=row.degraded, fill=row.fill, bends=tuple(row.bends),
        announcement_broken=row.announcement_broken,
        start=grid.us_to_iso(_start_us(epoch, row.start_frame)), end=grid.us_to_iso(_start_us(epoch, end)))


def aired_rows_due(rows: Sequence[PlanRow], epoch: Epoch, pub_last: int | None, now_us: int) -> list[AiredRow]:
    """Rows whose end (a cut end included) lies within published segments and
    is already in the past."""
    if pub_last is None:
        return []
    bound = (pub_last + 1) * grid.SEGMENT_FRAMES
    return [_aired(r, epoch) for r in rows
            if r.end_frame <= bound and _start_us(epoch, r.end_frame) <= now_us]


def load_aired(ws: Workspace) -> list[AiredRow]:
    try:
        text = ws.aired_path.read_text()
    except FileNotFoundError:
        return []
    out: list[AiredRow] = []
    for i, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            if not isinstance(data, dict):
                raise TypeError("not an object")
            out.append(AiredRow.from_json(data))
        except Exception as exc:
            log.warning("%s line %d skipped: %s: %s", ws.aired_path, i, type(exc).__name__, exc)
    return out


def append_aired(ws: Workspace, epoch: Epoch, rows: Sequence[PlanRow], pub_last: int | None, now_us: int) -> int:
    """Append the due rows not already recorded; return how many. A first call
    with no file is the backfill (same rule)."""
    due = aired_rows_due(rows, epoch, pub_last, now_us)
    if not due:
        return 0
    have = {r.identity for r in load_aired(ws)}
    new = [r for r in due if r.identity not in have]
    if not new:
        return 0
    ws.aired_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ws.aired_path, "a") as f:
        for r in new:
            f.write(json.dumps(r.to_json(), sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return len(new)


def _local_date(us: int, tz: str) -> str:
    dt = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=us)
    return dt.astimezone(ZoneInfo(tz)).date().isoformat()


def _year_of(d: str | None) -> int | None:
    try:
        return int(d[:4]) if d else None
    except ValueError:
        return None


@dataclass(frozen=True)
class _Use:
    start_us: int
    local_date: str
    kind: str
    slug: str
    package: str | None
    artist: str | None
    year: int | None


@dataclass(frozen=True)
class Recency:
    uses: tuple[_Use, ...] = field(default=())

    def last_aired_us(self, package: str) -> int | None:
        xs = [u.start_us for u in self.uses if u.kind == "show" and u.package == package]
        return max(xs) if xs else None

    def last_used_us(self, clip_slug: str) -> int | None:
        xs = [u.start_us for u in self.uses if u.kind != "show" and u.slug == clip_slug]
        return max(xs) if xs else None

    def artists_on(self, local_date: date | str) -> list[str]:
        d = str(local_date)
        return [u.artist for u in self.uses if u.kind == "show" and u.local_date == d and u.artist]

    def artist_years_on(self, local_date: date | str) -> list[tuple[str, int]]:
        d = str(local_date)
        return [(u.artist, u.year) for u in self.uses
                if u.kind == "show" and u.local_date == d and u.artist and u.year is not None]

    def with_piece(self, piece: Any, start_us: int, local_date: date | str) -> "Recency":
        """A new index including a piece the projection itself chose."""
        use = _Use(start_us, str(local_date), piece.kind, piece.slug, piece.package, piece.artist, piece.year)
        return Recency(self.uses + (use,))


def recency(aired: Sequence[AiredRow], rows: Sequence[PlanRow], epoch: Epoch, tz: str,
            meta_of: Callable[[str], tuple[str | None, str | None]]) -> Recency:
    """Aired rows plus persisted plan rows, deduped by (epoch_id, start_frame);
    `meta_of(package)` gives (artist, date) from the current scan."""
    seen: set[tuple[str, int]] = set()
    uses: list[_Use] = []

    def add(epoch_id: str, start_frame: int, start_us: int, kind: str, slug: str, package: str | None) -> None:
        if (epoch_id, start_frame) in seen:
            return
        seen.add((epoch_id, start_frame))
        artist, d = meta_of(package) if package else (None, None)
        uses.append(_Use(start_us, _local_date(start_us, tz), kind, slug, package, artist, _year_of(d)))

    for a in aired:
        add(a.epoch_id, a.start_frame, grid.iso_to_us(a.start), a.kind, a.slug, a.package or package_of(a))
    for r in rows:
        add(epoch.epoch_id, r.start_frame, _start_us(epoch, r.start_frame), r.kind, r.slug, package_of(r))
    return Recency(tuple(uses))
