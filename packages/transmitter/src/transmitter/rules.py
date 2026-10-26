"""Selection score and rotation rules (scheduler spec, "Selection score and
rotation rules").

Pure functions over a piece, its slot and the rotation history. The score is
additive and never negative: a recency term (1.0 never aired, else
0.9 x the fraction of the concert gap elapsed, saturating at 0.9; with gap 0
the fraction of `GAP0_RECENCY_HORIZON_DAYS`) plus the
block's matching `years` weights plus the on-this-day weight. Weights are
finite but unbounded, so a score may be +inf; it is never NaN (no term is
negative, so no inf - inf arises), and callers compare tuples, never
differences of scores.

The rules are counted, never enforced: `violations` returns per-rule counts
for a candidate sequence, hardest rule first (`RULES`), and the scheduler
ranks options lexicographically on them. `concert_gap_days = 0` disables the
gap rule (no division by it; every gap comparison is in float days)."""

import functools
import hashlib
from collections.abc import Sequence, Set
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from transmitter.clock import ClockConfig, Occurrence
    from transmitter.history import Recency
    from transmitter.pieces import Piece

RULES = ("adjacency", "gap", "artist_day", "era")

DAY_US = 86_400_000_000
NEVER_AIRED = 1.0
AIRED_CEILING = 0.9
# With concert_gap_days = 0 the recency term grows over this many days instead
# of the gap (no gap rule is counted; least recently aired still ranks first).
GAP0_RECENCY_HORIZON_DAYS = 365
_UNIX = datetime(1970, 1, 1, tzinfo=timezone.utc)


@functools.lru_cache(maxsize=1 << 16)
def tie_rank(seed: int, slug: str) -> str:
    """The deterministic tie-break (phase 1's `planner.shuffle_rank`)."""
    return hashlib.sha256(f"{seed}:{slug}".encode()).hexdigest()


def local_date(us: int, tz: ZoneInfo) -> date:
    return (_UNIX + timedelta(microseconds=us)).astimezone(tz).date()


def recency_term(last_us: int | None, slot_us: int, gap_days: float) -> float:
    """1.0 never aired; else 0.9 x the fraction of the concert gap elapsed,
    saturating at 0.9. With `gap_days == 0` (no gap rule) the fraction is
    taken over `GAP0_RECENCY_HORIZON_DAYS` instead, so least recently aired
    still ranks first (operator ruling, R16)."""
    if last_us is None:
        return NEVER_AIRED
    days = abs(slot_us - last_us) / DAY_US
    horizon = gap_days if gap_days > 0 else GAP0_RECENCY_HORIZON_DAYS
    return AIRED_CEILING * min(days / horizon, 1.0)


def gap_hit(last_us: int | None, slot_us: int, gap_days: float) -> bool:
    """Aired within the concert gap of this slot (float days; gap 0 never hits)."""
    return gap_days > 0 and last_us is not None and abs(slot_us - last_us) / DAY_US < gap_days


def _years(spec: str) -> tuple[int, int]:
    lo, _, hi = spec.partition("-")
    return int(lo), int(hi or lo)


def year_ranges(occ: "Occurrence") -> tuple[tuple[int, int, float], ...]:
    return tuple((*_years(p.years), p.weight) for p in occ.block.prefer if p.years is not None)


def on_this_day_weight(occ: "Occurrence", clock: "ClockConfig") -> float:
    """The block's own `on_this_day` (its first such entry) overrides the rotation default."""
    for p in occ.block.prefer:
        if p.on_this_day is not None:
            return p.on_this_day
    return clock.rotation.on_this_day_weight


def year_weight(year: int | None, ranges: tuple[tuple[int, int, float], ...]) -> float:
    if year is None:
        return 0.0
    return sum(w for lo, hi, w in ranges if lo <= year <= hi)


def score(p: "Piece", occ: "Occurrence", rec: "Recency", clock: "ClockConfig", slot_us: int) -> float:
    tz = ZoneInfo(clock.timezone)
    pkg = p.package
    s = recency_term(rec.last_aired_us(pkg) if pkg is not None else None, slot_us,
                     clock.rotation.concert_gap_days)
    s += year_weight(p.year, year_ranges(occ))
    md = p.month_day
    if md is not None and md == local_date(slot_us, tz).strftime("%m-%d"):
        s += on_this_day_weight(occ, clock)
    return s


class RecDays:
    """`Recency`'s per-local-date artists and (artist, year) pairs as cached sets."""

    def __init__(self, rec: "Recency"):
        self.rec = rec
        self._cache: dict[date, tuple[frozenset, frozenset]] = {}

    def get(self, d: date) -> tuple[frozenset, frozenset]:
        hit = self._cache.get(d)
        if hit is None:
            hit = (frozenset(self.rec.artists_on(d)), frozenset(self.rec.artist_years_on(d)))
            self._cache[d] = hit
        return hit


def violations(seq: Sequence["Piece"], prev_artist: str | None, occ: "Occurrence", rec: "Recency",
               clock: "ClockConfig", starts_us: Sequence[int], *,
               exempt: Set[str] = frozenset()) -> tuple[int, int, int, int]:
    """Per-rule counts (`RULES` order) for shows `seq` placed at `starts_us`.

    adjacency: same artist as the show before (the first against `prev_artist`);
    gap: aired within `concert_gap_days`, or earlier in this sequence;
    artist_day: artist already on that local date (history or earlier here);
    era: same artist and year already on that local date. Era implies
    artist_day, by definition, except on an exempt show.

    `exempt` (slugs): shows drawn from a single-artist pool, for which
    adjacency and artist_day are not counted (spec "What counts as a bend":
    a rule the pool makes impossible is not applied within that pool at
    all). Their artist still counts against the shows after them that are
    not exempt; gap and era apply to them as to any show."""
    tz = ZoneInfo(clock.timezone)
    gap_days = clock.rotation.concert_gap_days
    days = RecDays(rec)
    adj = gap = day = era = 0
    prev = prev_artist
    seen: set[str] = set()
    seq_a: dict[date, set] = {}
    seq_ay: dict[date, set] = {}
    for p, s in zip(seq, starts_us, strict=True):
        d = local_date(s, tz)
        artist, year, pkg = p.artist, p.year, p.package
        free = p.slug in exempt
        if artist and prev == artist and not free:
            adj += 1
        if pkg is not None and gap_days > 0 and (pkg in seen or gap_hit(rec.last_aired_us(pkg), s, gap_days)):
            gap += 1
        if artist:
            ra, ray = days.get(d)
            if not free and (artist in ra or artist in seq_a.get(d, ())):
                day += 1
            if year is not None and ((artist, year) in ray or (artist, year) in seq_ay.get(d, ())):
                era += 1
            seq_a.setdefault(d, set()).add(artist)
            if year is not None:
                seq_ay.setdefault(d, set()).add((artist, year))
        if pkg is not None:
            seen.add(pkg)
        prev = artist
    return adj, gap, day, era
