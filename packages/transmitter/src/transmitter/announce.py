"""Schedule announcements (spec "Station IDs and announcements"): text derived
from the clock alone; the id is a hash of the rendered text, so changing a
template or the time format retires old clips."""

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from transmitter.clock import AnnounceConfig, ClockConfig, Occurrence, occurrences

Form = Literal["next", "next_one", "later", "later_one"]

_US_PER_DAY = 86_400_000_000


def _fmt(local: datetime, time_format: str) -> str:
    if time_format == "24h":
        return f"{local.hour:02d}:{local.minute:02d}"
    h = local.hour % 12 or 12
    if time_format == "hm12":
        return f"{h}:{local.minute:02d}"
    return f"{h}" if local.minute == 0 else f"{h}:{local.minute:02d}"


def render_time(us: int, ann: AnnounceConfig) -> str:
    utc = datetime.fromtimestamp(us // 1_000_000, tz=timezone.utc).replace(microsecond=us % 1_000_000)
    parts = [f"{_fmt(utc.astimezone(ZoneInfo(z.tz)), ann.time_format)} {z.label}" for z in ann.zones]
    return ", ".join(parts)


def render(template: str, first: Occurrence, second: Occurrence | None, ann: AnnounceConfig) -> str:
    return template.format(
        title=first.block.title or "",
        time=render_time(first.nominal_us, ann),
        next_title=(second.block.title or "") if second is not None else "",
        next_time=render_time(second.nominal_us, ann) if second is not None else "")


def ann_id(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def text_for(form: Form, x: Occurrence, y: Occurrence | None, ann: AnnounceConfig) -> str:
    return render(getattr(ann, form), x, y, ann)


@dataclass(frozen=True)
class Needed:
    id: str
    text: str
    form: Form
    block: str
    nominal_iso: str


def needed(clock: ClockConfig, from_us: int, days: float = 8) -> list[Needed]:
    until = from_us + int(days * _US_PER_DAY)
    occs = sorted(occurrences(clock, from_us, until + 2 * _US_PER_DAY), key=lambda o: o.nominal_us)
    ann = clock.announce
    out: list[Needed] = []
    seen: set[str] = set()

    def add(form: Form, x: Occurrence, y: Occurrence | None) -> None:
        text = text_for(form, x, y, ann)
        i = ann_id(text)
        if i not in seen:
            seen.add(i)
            out.append(Needed(i, text, form, x.block.name, x.nominal_iso))

    for n, x in enumerate(occs):
        if x.nominal_us >= until or not x.block.title:
            continue
        add("next_one", x, None)
        add("later_one", x, None)
        y = occs[n + 1] if n + 1 < len(occs) else None
        if y is not None and y.block.title:
            add("next", x, y)
            add("later", x, y)
    return out
