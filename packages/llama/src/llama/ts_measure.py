"""Pure helpers for taperssection shows: age-adjusted download measure and
the title-derived venue fallback. No I/O."""
from __future__ import annotations

import re
from datetime import date

NO_EVIDENCE_AGE_DAYS = 75

_DATE_PART = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _parse_date(s: str | None) -> date | None:
    if not isinstance(s, str):
        return None
    m = _DATE_PART.match(s.strip())
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def rate(downloads: int | None, addeddate: str | None, today: date) -> float | None:
    """Downloads per day since addeddate; None when there is no evidence:
    addeddate missing/unparseable/future, or the item is under 75 days old
    (archive.org's counter lags). A missing download count on an
    evidence-bearing item is zero."""
    added = _parse_date(addeddate)
    if added is None:
        return None
    age = (today - added).days
    if age < NO_EVIDENCE_AGE_DAYS:
        return None
    return (downloads or 0) / age


def show_rate(items: list[dict], today: date) -> float | None:
    rates = [r for it in items
             if (r := rate(it.get("downloads"), it.get("addeddate"), today)) is not None]
    return max(rates) if rates else None


def percentile(value: float, population: list[float]) -> float | None:
    """Share (0-100) of the population at or below value."""
    if not population:
        return None
    return 100.0 * sum(1 for p in population if p <= value) / len(population)


def catalogue_rates(items_by_date: dict[str, list[dict]], today: date) -> list[float]:
    out = []
    for items in items_by_date.values():
        r = show_rate(items, today)
        if r is not None:
            out.append(r)
    return out


# --- title venue ---

_DATEISH = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|^\d+$")
_NOT_VENUE = re.compile(r"^(?:(?:set|disc|cd|d)\s*\d+|e\d*|encore|partial|early|late|soundcheck)\b", re.I)
_LIVE_AT = re.compile(r"\blive\s+at\s+(?P<v>.+?)\s+on\s+\S", re.I)
_AT_SIGN = re.compile(r"@\s*(?P<rest>\S.*)$")


def _clean(s: str | None) -> str | None:
    s = (s or "").strip(" \t-,")
    if not s or _DATEISH.search(s) or _NOT_VENUE.match(s):
        return None
    return s


def parse_title_venue(title: str) -> tuple[str | None, str | None]:
    """(venue, city) from an item title, or (None, None)."""
    if not title:
        return None, None
    parts = [p.strip() for p in title.split(" - ")]
    if len(parts) >= 3 and _DATEISH.fullmatch(parts[1]):
        venue = _clean(parts[2])
        if venue:
            return venue, _clean(", ".join(parts[3:])) if len(parts) > 3 else None
        return None, None
    m = _LIVE_AT.search(title)
    if m:
        venue = _clean(m["v"])
        return (venue, None) if venue else (None, None)
    m = _AT_SIGN.search(title)
    if m:
        segs = [x.strip() for x in m["rest"].split(" - ")]
        if len(segs) >= 2:  # "@ venue - city, ST - mic chain": stop at the second segment
            venue, city = _clean(segs[0]), _clean(segs[1])
        else:
            v, _, c = segs[0].partition(",")
            venue, city = _clean(v), _clean(c)
        if venue:
            return venue, city
    return None, None
