"""The weekly clock (scheduler spec, "The clock"): models, strict loading, the
last-good copy and expansion into concrete UTC occurrences."""

import re
import string
import tomllib
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from transmitter.errors import ConfigError
from transmitter.grid import us_to_iso
from transmitter.workspace import Workspace, atomic_write_bytes

DEFAULT_NEXT = "Coming up next, {title}. Then at {next_time}, {next_title}."
DEFAULT_NEXT_ONE = "Coming up next, {title}."
DEFAULT_LATER = "Stay tuned for {title} at {time}, followed by {next_title} at {next_time}."
DEFAULT_LATER_ONE = "Stay tuned for {title} at {time}."

_TWO_FIELDS = {"title", "time", "next_title", "next_time"}
_ONE_FIELDS = {"title", "time"}
_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_UNIX = datetime(1970, 1, 1, tzinfo=timezone.utc)
_US = timedelta(microseconds=1)


class _StrictModel(BaseModel):
    """Unknown keys are an error. Set on a shared base because pydantic does
    not propagate model_config to nested models."""
    model_config = ConfigDict(extra="forbid")


def _check_tz(name: str) -> str:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
        raise ValueError(f"unknown time zone {name!r}") from exc
    return name


def _check_template(text: str, allowed: set[str], key: str) -> None:
    try:
        names = {f for _, f, _, _ in string.Formatter().parse(text) if f is not None}
        extra = names - allowed
        if extra:
            raise ValueError(f"unknown field(s) {sorted(extra)}; allowed: {sorted(allowed)}")
        text.format(**{n: "x" for n in allowed})
    except ValueError as exc:
        raise ValueError(f"announce.{key}: {exc}") from exc
    except (KeyError, IndexError, AttributeError, TypeError) as exc:
        raise ValueError(f"announce.{key}: bad template ({exc!r})") from exc


class Zone(_StrictModel):
    tz: str
    label: str

    @field_validator("tz")
    @classmethod
    def _tz(cls, v: str) -> str:
        return _check_tz(v)


def _default_zones() -> list[Zone]:
    return [Zone(tz="America/New_York", label="Eastern"),
            Zone(tz="America/Los_Angeles", label="Pacific")]


class AnnounceConfig(_StrictModel):
    next: str = DEFAULT_NEXT
    next_one: str = DEFAULT_NEXT_ONE
    later: str = DEFAULT_LATER
    later_one: str = DEFAULT_LATER_ONE
    time_format: Literal["short12", "hm12", "24h"] = "short12"
    zones: list[Zone] = Field(default_factory=_default_zones)

    @model_validator(mode="after")
    def _templates(self) -> "AnnounceConfig":
        _check_template(self.next, _TWO_FIELDS, "next")
        _check_template(self.later, _TWO_FIELDS, "later")
        _check_template(self.next_one, _ONE_FIELDS, "next_one")
        _check_template(self.later_one, _ONE_FIELDS, "later_one")
        return self


_YEARS = re.compile(r"^(\d{4})(?:-(\d{4}))?$")


class Prefer(_StrictModel):
    years: str | None = None
    on_this_day: float | None = Field(default=None, ge=0)
    weight: float = Field(default=1.0, gt=0)

    @model_validator(mode="after")
    def _one_of(self) -> "Prefer":
        if (self.years is None) == (self.on_this_day is None):
            raise ValueError("prefer needs exactly one of years / on_this_day")
        if self.years is not None:
            m = _YEARS.match(self.years)
            if not m or (m.group(2) and int(m.group(2)) < int(m.group(1))):
                raise ValueError(f"years must be YYYY or YYYY-YYYY (ascending), got {self.years!r}")
        return self


class BlockConfig(_StrictModel):
    name: str = Field(min_length=1)
    title: str | None = None
    days: Literal["daily"] | list[Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]] = "daily"
    start: str
    profiles: list[str] = Field(default_factory=list)
    max_shows: int | None = Field(default=None, ge=1)
    wiggle_minutes: float | None = Field(default=None, ge=0)
    early_minutes: float | None = Field(default=None, ge=0)
    late_minutes: float | None = Field(default=None, ge=0)
    prefer: list[Prefer] = Field(default_factory=list)

    @field_validator("start")
    @classmethod
    def _start(cls, v: str) -> str:
        if not re.fullmatch(r"\d{2}:\d{2}", v):
            raise ValueError(f"start must be HH:MM, got {v!r}")
        h, m = int(v[:2]), int(v[3:])
        if h > 23 or m > 59:
            raise ValueError(f"start out of range: {v!r}")
        return v

    @field_validator("days")
    @classmethod
    def _days(cls, v):
        if v != "daily":
            if not v:
                raise ValueError("days must be \"daily\" or a non-empty list")
            if len(set(v)) != len(v):
                raise ValueError("days lists a weekday twice")
        return v

    @model_validator(mode="after")
    def _window(self) -> "BlockConfig":
        if (self.early_minutes is None) != (self.late_minutes is None):
            raise ValueError("early_minutes and late_minutes go together")
        if self.early_minutes is not None and self.wiggle_minutes is not None:
            raise ValueError("wiggle_minutes cannot be combined with early_minutes/late_minutes")
        return self

    def weekdays(self) -> list[int]:
        return list(range(7)) if self.days == "daily" else [_DAYS.index(d) for d in self.days]


class OpenConfig(_StrictModel):
    exclude_profiles: list[str] = Field(default_factory=list)


class RotationConfig(_StrictModel):
    concert_gap_days: float = Field(default=45, ge=0)
    on_this_day_weight: float = Field(default=3.0, ge=0)


class ClockConfig(_StrictModel):
    timezone: str
    wiggle_minutes: float = Field(default=15, ge=0)
    announce: AnnounceConfig = Field(default_factory=AnnounceConfig)
    open: OpenConfig = Field(default_factory=OpenConfig)
    rotation: RotationConfig = Field(default_factory=RotationConfig)
    block: list[BlockConfig] = Field(default_factory=list)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        return _check_tz(v)

    @model_validator(mode="after")
    def _blocks(self) -> "ClockConfig":
        if not self.block:
            raise ValueError("a clock needs at least one [[block]]")
        names = [b.name for b in self.block]
        if len(set(names)) != len(names):
            raise ValueError("block names must be unique")
        seen: dict[tuple[int, str], str] = {}
        for b in self.block:
            for wd in b.weekdays():
                other = seen.setdefault((wd, b.start), b.name)
                if other != b.name:
                    raise ValueError(
                        f"blocks {other!r} and {b.name!r} share {_DAYS[wd]} {b.start}")
            e, l = self.window_minutes(b)
            if e + l <= 0:
                raise ValueError(f"block {b.name!r}: the wiggle window must be positive")
        return self

    def window_minutes(self, b: BlockConfig) -> tuple[float, float]:
        """(early, late) minutes for a block."""
        if b.early_minutes is not None:
            return b.early_minutes, b.late_minutes or 0.0
        w = b.wiggle_minutes if b.wiggle_minutes is not None else self.wiggle_minutes
        return w, w


IMPLICIT_CLOCK = ClockConfig(
    timezone="America/New_York",
    wiggle_minutes=720,
    block=[BlockConfig(name="open", start="00:00", wiggle_minutes=720)],
)


def _parse(text: str, path: Path) -> ClockConfig:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid clock at {path}: {exc}") from exc
    try:
        return ClockConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"invalid clock at {path}: {exc}") from exc


def load_clock(path: Path) -> ClockConfig:
    path = Path(path)
    try:
        text = path.read_text()
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"cannot read clock at {path}: {exc}") from exc
    return _parse(text, path)


@dataclass(frozen=True)
class LiveClock:
    clock: ClockConfig
    source: Literal["clock", "last-good", "implicit"]
    problem: str | None


def live_clock(ws: Workspace, *, save: bool = True) -> LiveClock:
    path, good = ws.clock_path, ws.clock_last_good_path
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return LiveClock(IMPLICIT_CLOCK, "implicit", None)
    except OSError as exc:
        raw, problem = None, f"cannot read clock at {path}: {exc}"
    else:
        try:
            clock = _parse(raw.decode(), path)
        except UnicodeDecodeError as exc:
            problem = f"invalid clock at {path}: {exc}"
        except ConfigError as exc:
            problem = str(exc)
        else:
            if save:
                try:
                    try:
                        same = good.read_bytes() == raw
                    except OSError:
                        same = False
                    if not same:
                        atomic_write_bytes(good, raw)
                except OSError:
                    pass  # a failed copy must not block planning on a valid clock
            return LiveClock(clock, "clock", None)
    try:
        return LiveClock(load_clock(good), "last-good", problem)
    except ConfigError:
        return LiveClock(IMPLICIT_CLOCK, "implicit", problem)


@dataclass(frozen=True)
class Occurrence:
    block: BlockConfig
    nominal_us: int
    lo_us: int
    hi_us: int
    end_us: int
    local_date: date

    @property
    def nominal_iso(self) -> str:
        return us_to_iso(self.nominal_us)

    @property
    def key(self) -> tuple[str, str]:
        return (self.block.name, self.nominal_iso)

    @property
    def is_open(self) -> bool:
        return not self.block.profiles

    @property
    def max_shows(self) -> int | None:
        if self.block.max_shows is not None:
            return self.block.max_shows
        return None if self.is_open else 2


def _to_us(dt_utc: datetime) -> int:
    return (dt_utc - _UNIX) // _US


def _resolve(tz: ZoneInfo, d: date, hhmm: str) -> int:
    """Local wall time -> UTC us. Ambiguous: first occurrence (fold=0). Nonexistent:
    the transition instant (first UTC instant whose wall time is >= requested)."""
    naive = datetime.combine(d, time(int(hhmm[:2]), int(hhmm[3:])))
    first = naive.replace(tzinfo=tz, fold=0)
    utc = first.astimezone(timezone.utc)
    if utc.astimezone(tz).replace(tzinfo=None) == naive:
        return _to_us(utc)
    # In a gap: fold=1 uses the post-transition offset, giving an earlier UTC.
    lo = naive.replace(tzinfo=tz, fold=1).astimezone(timezone.utc)  # wall < naive
    hi = utc                                                         # wall > naive
    lo_s, hi_s = int((lo - _UNIX).total_seconds()), int((hi - _UNIX).total_seconds())
    while hi_s - lo_s > 1:
        mid = (lo_s + hi_s) // 2
        wall = (_UNIX + timedelta(seconds=mid)).astimezone(tz).replace(tzinfo=None)
        if wall >= naive:
            hi_s = mid
        else:
            lo_s = mid
    return hi_s * 1_000_000


def occurrences(clock: ClockConfig, from_us: int, until_us: int) -> list[Occurrence]:
    tz = ZoneInfo(clock.timezone)
    # A block never runs longer than a week, so a week of padding each side
    # brings in the occurrence running at from_us and the one that ends the last.
    first = (_UNIX + timedelta(microseconds=from_us)).astimezone(tz).date() - timedelta(days=8)
    last = (_UNIX + timedelta(microseconds=until_us)).astimezone(tz).date() + timedelta(days=8)
    starts: list[tuple[int, str, date, BlockConfig]] = []
    d = first
    while d <= last:
        for b in clock.block:
            if d.weekday() in b.weekdays():
                starts.append((_resolve(tz, d, b.start), b.start, d, b))
        d += timedelta(days=1)
    starts.sort(key=lambda s: (s[0], s[1]))
    out: list[Occurrence] = []
    for i, (nominal, _, d, b) in enumerate(starts[:-1]):
        end = starts[i + 1][0]
        if end <= nominal:
            continue  # collapsed by a DST gap
        if end <= from_us or nominal >= until_us:
            continue
        early, late = clock.window_minutes(b)
        out.append(Occurrence(
            block=b, nominal_us=nominal,
            lo_us=nominal - round(early * 60_000_000),
            hi_us=nominal + round(late * 60_000_000),
            end_us=end, local_date=d))
    return out
