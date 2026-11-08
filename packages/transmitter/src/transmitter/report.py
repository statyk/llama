"""Pure formatting for `transmitter schedule`, `library` and `status` (spec
"Commands"): block views over persisted rows plus a projection, a summary over
a span, and the text lines. No IO and no wall clock; callers pass everything in.

Bends are reported, never alerted (spec: status noise is an anti-goal)."""

import re
import statistics
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from transmitter import rules
from transmitter.announce import Needed
from transmitter.clock import ClockConfig
from transmitter.grid import FRAME_SAMPLES, SAMPLE_RATE, frame_to_us, iso_to_us
from transmitter.layout import PlanRow
from transmitter.scheduler import EXCLUDE_BEND, PlannedPiece
from transmitter.workspace import Epoch

BEND_ORDER = rules.RULES + (EXCLUDE_BEND,)
FILL_CAUSES = ("pool-short", "structural")
_US_PER_DAY = 86_400_000_000
FILL_LABELS = {"pool-short": "pool short", "structural": "longer than max_shows"}


def fill_label(cause: str) -> str:
    return FILL_LABELS.get(cause, cause)


def minutes_of(frames: int) -> float:
    return frames * FRAME_SAMPLES / SAMPLE_RATE / 60


@dataclass(frozen=True)
class ShowView:
    slug: str
    artist: str | None
    date: str | None
    minutes: float
    estimated: bool
    fill: str | None            # the fill cause, on fill shows
    start_us: int


@dataclass(frozen=True)
class BlockView:
    block: str
    title: str
    nominal_iso: str
    nominal_us: int | None
    nominal_local: str
    start_local: str | None     # the first show's start; None when no show is in view
    slip_minutes: float | None  # actual start minus nominal
    shows: tuple[ShowView, ...]
    breaks: tuple[str, ...]     # interstitials: "station ID <slug>", "announcement <slug>"
    miss: bool
    degraded: bool
    bends: tuple[str, ...]      # each bent rule, once per block
    missing: tuple[Needed, ...] # announcement audio this occurrence needs and the folder lacks
    persisted: bool             # every show of the occurrence is already in the plan


@dataclass(frozen=True)
class Summary:
    occurrences: int
    misses: int
    fill_minutes: dict[str, float]
    fill_total: float
    span_minutes: float
    fill_share: float
    bends: dict[str, int]
    degraded: int
    shortest_gap_days: float | None
    missing_audio: int


@dataclass(frozen=True)
class _Item:
    kind: str
    role: str | None
    slug: str
    start_frame: int
    frames: int
    block: str | None
    nominal: str | None
    miss: bool | None
    degraded: bool
    fill: str | None
    bends: tuple[str, ...]
    persisted: bool
    exact: bool
    artist: str | None
    date: str | None


def _from_row(r: PlanRow, meta_of: Callable[[str | None], tuple[str | None, str | None]]) -> _Item:
    artist, date = meta_of(r.package) if r.kind == "show" else (None, None)
    return _Item(r.kind, r.role, r.slug, r.start_frame, r.end_frame - r.start_frame, r.block, r.nominal_start,
                 r.miss, r.degraded, r.fill, tuple(r.bends), True, True, artist, date)


def _from_projected(pp: PlannedPiece) -> _Item:
    p = pp.piece
    return _Item(p.kind, pp.role, p.slug, pp.start_frame, p.frames, pp.block, pp.nominal_start, pp.miss,
                 pp.degraded, pp.fill, tuple(pp.bends), False, p.exact, p.artist, p.date)


def _no_meta(package: str | None) -> tuple[str | None, str | None]:
    return (None, None)


def local_text(us: int, tz: str) -> str:
    dt = datetime.fromtimestamp(us / 1_000_000, tz=timezone.utc).astimezone(ZoneInfo(tz))
    return dt.strftime("%a %m-%d %H:%M")


def block_views(rows: Sequence[PlanRow], projected: Sequence[PlannedPiece], clock: ClockConfig, epoch: Epoch, *,
                missing: Sequence[Needed] = (), since_frame: int | None = None,
                meta_of: Callable[[str | None], tuple[str | None, str | None]] = _no_meta) -> list[BlockView]:
    """One view per occurrence, in order of first appearance. A boundary
    interstitial belongs to the occurrence it carries (`block`, `nominal`).

    An occurrence's start, slip, miss and bends come from ALL its rows given;
    with `since_frame`, shows that ended at or before it (already aired) are
    left out of the per-show listing only."""
    items = [_from_row(r, meta_of) for r in rows] + [_from_projected(p) for p in projected]
    titles = {b.name: b.title or b.name for b in clock.block}
    open_blocks = {b.name for b in clock.block if not b.profiles}
    need: dict[tuple[str, str], list[Needed]] = {}
    for n in missing:
        need.setdefault((n.block, n.nominal_iso), []).append(n)
    groups: dict[tuple[str | None, str | None], list[_Item]] = {}
    for it in items:
        groups.setdefault((it.block, it.nominal), []).append(it)
    out: list[BlockView] = []
    for (block, nominal), its in groups.items():
        shows = [i for i in its if i.kind == "show"]
        nominal_us = None
        if nominal is not None:
            nominal_us = iso_to_us(nominal)
        first_us = epoch.epoch_us + frame_to_us(shows[0].start_frame) if shows else None
        slip = None if first_us is None or nominal_us is None or block in open_blocks \
            else (first_us - nominal_us) / 60_000_000     # open time has no start to keep
        bent: set[str] = set()
        for i in shows:
            bent.update(i.bends)
        breaks = tuple(("station ID " if i.role == "id" else "announcement ") + i.slug
                       for i in its if i.kind == "interstitial")
        first = shows[0] if shows else None
        out.append(BlockView(
            block=block or "(unscheduled)",
            title=titles.get(block or "", block or "(unscheduled)"),
            nominal_iso=nominal or "",
            nominal_us=nominal_us,
            nominal_local=local_text(nominal_us, clock.timezone) if nominal_us is not None else "",
            start_local=local_text(first_us, clock.timezone) if first_us is not None else None,
            slip_minutes=slip,
            shows=tuple(ShowView(i.slug, i.artist, i.date, minutes_of(i.frames), not i.exact, i.fill,
                                 epoch.epoch_us + frame_to_us(i.start_frame)) for i in shows
                        if since_frame is None or i.start_frame + i.frames > since_frame),
            breaks=breaks,
            miss=bool(first is not None and first.miss),
            degraded=any(i.degraded for i in shows),
            bends=tuple(r for r in BEND_ORDER if r in bent),
            missing=tuple(need.get((block or "", nominal or ""), ())),
            persisted=bool(shows) and all(i.persisted for i in shows)))
    return out


def summary(views: Sequence[BlockView], span_us: int) -> Summary:
    fill = {c: 0.0 for c in FILL_CAUSES}
    bends: dict[str, int] = {}
    last_start: dict[str, int] = {}
    shortest: int | None = None
    seen_missing: set[str] = set()
    for v in views:
        for s in v.shows:
            if s.fill:
                fill[s.fill] = fill.get(s.fill, 0.0) + s.minutes
            prev = last_start.get(s.slug)
            if prev is not None and (shortest is None or s.start_us - prev < shortest):
                shortest = s.start_us - prev
            last_start[s.slug] = s.start_us
        for r in v.bends:
            bends[r] = bends.get(r, 0) + 1
        seen_missing.update(n.id for n in v.missing)
    total = sum(fill.values())
    span_min = span_us / 60_000_000
    return Summary(occurrences=len(views), misses=sum(1 for v in views if v.miss), fill_minutes=fill,
                   fill_total=total, span_minutes=span_min,
                   fill_share=total / span_min if span_min > 0 else 0.0,
                   bends=bends, degraded=sum(1 for v in views if v.degraded),
                   shortest_gap_days=None if shortest is None else shortest / _US_PER_DAY,
                   missing_audio=len(seen_missing))


def _show_text(s: ShowView) -> str:
    who = " ".join(x for x in (s.artist, s.date) if x) or s.slug
    mark = "~" if s.estimated else ""
    fill = f"  [fill: {fill_label(s.fill)}]" if s.fill else ""
    return f"{who} ({mark}{s.minutes:.0f} min){fill}"


def schedule_lines(views: Sequence[BlockView], s: Summary) -> list[str]:
    lines: list[str] = []
    for v in views:
        head = f"{v.nominal_local}  {v.title}" if v.nominal_local else v.title
        if v.start_local is not None:
            head += f"  starts {v.start_local}" + ("" if v.slip_minutes is None else f" ({v.slip_minutes:+.0f} min)")
        flags = [f for f, on in (("MISS", v.miss), ("degraded to open time", v.degraded)) if on]
        if v.bends:
            flags.append("bent: " + ", ".join(v.bends))
        lines.append(head + (f"  [{'; '.join(flags)}]" if flags else "") + ("" if v.persisted else "  (projected)"))
        for sh in v.shows:
            lines.append(f"    {_show_text(sh)}")
        for b in v.breaks:
            lines.append(f"    . {b}")
        for n in v.missing:
            lines.append(f"    ! missing announcement audio ann-{n.id}.mp3: {n.text}")
    if not views:
        lines.append("(nothing planned)")
    lines.append("")
    lines.append(f"summary    {s.occurrences} block occurrence(s) over {s.span_minutes / 60:.0f} h; "
                 f"misses {s.misses}; degraded {s.degraded}")
    parts = ", ".join(f"{fill_label(c)} {s.fill_minutes.get(c, 0.0):.0f} min" for c in FILL_CAUSES)
    lines.append(f"fill       {s.fill_total:.0f} min = {s.fill_share * 100:.1f}% of the span ({parts})")
    bends = ", ".join(f"{r} {s.bends[r]}" for r in BEND_ORDER if r in s.bends)
    lines.append(f"bends      {bends or 'none'}")
    lines.append("repeat gap " + ("none repeated in the span" if s.shortest_gap_days is None
                                  else f"shortest {s.shortest_gap_days:.1f} days"))
    lines.append(f"audio      {s.missing_audio} announcement(s) missing" if s.missing_audio
                 else "audio      no announcement audio missing")
    return lines


# --- library -----------------------------------------------------------------

def percentile(sorted_values: Sequence[float], q: float) -> float:
    """Nearest-rank percentile of a sorted, non-empty sequence."""
    k = max(0, min(len(sorted_values) - 1, round(q * (len(sorted_values) - 1))))
    return sorted_values[k]


@dataclass(frozen=True)
class ProfileStats:
    profile: str
    count: int
    median: float
    p10: float
    p90: float
    estimated: int


def profile_stats(entries: Iterable[tuple[str | None, float, bool]]) -> list[ProfileStats]:
    """(profile, minutes, estimated) per eligible show -> per-profile stats."""
    by: dict[str, list[tuple[float, bool]]] = {}
    for profile, minutes, est in entries:
        by.setdefault(profile or "(none)", []).append((minutes, est))
    out = []
    for name in sorted(by):
        mins = sorted(m for m, _ in by[name])
        out.append(ProfileStats(name, len(mins), statistics.median(mins), percentile(mins, 0.1),
                                percentile(mins, 0.9), sum(1 for _, e in by[name] if e)))
    return out


def reason_key(reason: str) -> str:
    """A reason without its per-package detail ("awaiting fix from llama: why" -> "awaiting fix from llama")."""
    if reason.startswith("changed ") and "quiet period" in reason:
        return "changed within the quiet period"
    reason = re.sub(r"^\d+( of \d+)? ", "", reason)         # "3 DJ clip(s) missing" == "1 DJ clip(s) missing"
    return reason.split(": ", 1)[0]


@dataclass(frozen=True)
class LibraryReport:
    profiles: list[ProfileStats]
    ids: list[tuple[str, float]] = field(default_factory=list)                 # (slug, minutes)
    announcements: list[tuple[str, float, str | None]] = field(default_factory=list)   # (slug, minutes, text)
    ineligible: dict[str, list[str]] = field(default_factory=dict)             # reason -> slugs


def library_lines(rep: LibraryReport) -> list[str]:
    lines = ["eligible shows by profile (minutes; ~ = some lengths estimated)"]
    if not rep.profiles:
        lines.append("  none")
    for p in rep.profiles:
        est = f"  ~{p.estimated} estimated" if p.estimated else ""
        lines.append(f"  {p.profile:<16} {p.count:>4} shows  median {p.median:.0f}  p10 {p.p10:.0f}  "
                     f"p90 {p.p90:.0f}{est}")
    lines.append(f"station IDs  {len(rep.ids)}" + (": " + ", ".join(f"{s} ({m * 60:.0f} s)" for s, m in rep.ids)
                                                  if rep.ids else "  (none: boundaries get no ID)"))
    lines.append(f"announcements  {len(rep.announcements)}")
    for slug, m, text in rep.announcements:
        lines.append(f"  {slug} ({m * 60:.0f} s)  {text if text is not None else '(not named by the live clock)'}")
    total = sum(len(v) for v in rep.ineligible.values())
    lines.append(f"ineligible packages  {total}")
    for reason, slugs in sorted(rep.ineligible.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        sample = ", ".join(slugs[:3]) + (", ..." if len(slugs) > 3 else "")
        lines.append(f"  {len(slugs):>4}  {reason}  ({sample})")
    return lines


# --- rotation ------------------------------------------------------------------

TOP_PLAYED = 10


@dataclass(frozen=True)
class ProfileRotation:
    profile: str
    eligible: int
    played: int                 # eligible shows aired at least once
    never: int
    plays: int                  # airings of eligible shows
    repeated: int               # eligible shows aired twice or more
    gap_min: float | None       # days between consecutive airings of the same show
    gap_median: float | None
    gap_mean: float | None
    under_gap: int              # such gaps shorter than `concert_gap_days`
    never_slugs: tuple[str, ...]


@dataclass(frozen=True)
class ShowPlays:
    package: str
    profile: str | None         # None: no longer eligible
    plays: int
    last_us: int


@dataclass(frozen=True)
class RotationReport:
    profiles: list[ProfileRotation]
    total: ProfileRotation
    gone_shows: int             # aired, not eligible now
    gone_plays: int
    gone_under_gap: int
    top: list[ShowPlays]
    first_us: int | None        # the window's first and last airing
    last_us: int | None
    since_us: int | None
    gap_days: float


def _gaps(times: dict[str, list[int]]) -> list[float]:
    return [(b - a) / _US_PER_DAY for ts in times.values() for a, b in zip(ts, ts[1:])]


def _profile_rotation(name: str, packages: Sequence[str], times: dict[str, list[int]],
                      gap_days: float) -> ProfileRotation:
    mine = {p: times[p] for p in packages if p in times}
    gaps = _gaps(mine)
    never = tuple(sorted(p for p in packages if p not in times))
    return ProfileRotation(
        profile=name, eligible=len(packages), played=len(mine), never=len(never),
        plays=sum(len(ts) for ts in mine.values()), repeated=sum(1 for ts in mine.values() if len(ts) > 1),
        gap_min=min(gaps) if gaps else None, gap_median=statistics.median(gaps) if gaps else None,
        gap_mean=statistics.fmean(gaps) if gaps else None,
        under_gap=sum(1 for g in gaps if gap_days > 0 and g < gap_days), never_slugs=never)


def rotation(eligible: Iterable[tuple[str, str | None]], airings: Iterable[tuple[str, int]], *,
             gap_days: float, since_us: int | None = None) -> RotationReport:
    """Airplay by profile. `eligible` is (package, profile) per show eligible now; `airings` is
    (package, start_us) per aired show row. A show's profile is its current one; airings of a
    package not eligible now are counted apart ("gone")."""
    profile_of = dict(eligible)
    times: dict[str, list[int]] = {}
    for pkg, start in airings:
        if since_us is None or start >= since_us:
            times.setdefault(pkg, []).append(start)
    for ts in times.values():
        ts.sort()
    by: dict[str, list[str]] = {}
    for pkg, prof in profile_of.items():
        by.setdefault(prof or "(none)", []).append(pkg)
    profiles = [_profile_rotation(name, by[name], times, gap_days) for name in sorted(by)]
    total = _profile_rotation("total", list(profile_of), times, gap_days)
    gone = {p: ts for p, ts in times.items() if p not in profile_of}
    gone_gaps = _gaps(gone)
    top = sorted((ShowPlays(p, profile_of.get(p), len(ts), ts[-1]) for p, ts in times.items() if len(ts) > 1),
                 key=lambda s: (-s.plays, -s.last_us, s.package))[:TOP_PLAYED]
    starts = [t for ts in times.values() for t in ts]
    return RotationReport(
        profiles=profiles, total=total, gone_shows=len(gone), gone_plays=sum(len(ts) for ts in gone.values()),
        gone_under_gap=sum(1 for g in gone_gaps if gap_days > 0 and g < gap_days), top=top,
        first_us=min(starts) if starts else None, last_us=max(starts) if starts else None,
        since_us=since_us, gap_days=gap_days)


def _days(v: float | None) -> str:
    return "-" if v is None else f"{v:.1f}"


def rotation_lines(rep: RotationReport, *, tz: str, never: bool) -> list[str]:
    rule = f"concert gap {rep.gap_days:g} days" if rep.gap_days > 0 else "no concert gap rule"
    if rep.first_us is None:
        span = "nothing aired" + (" in the window" if rep.since_us is not None else " yet")
    else:
        span = (f"airings {local_text(rep.first_us, tz)} .. {local_text(rep.last_us, tz)}"
                + (f" (window from {local_text(rep.since_us, tz)})" if rep.since_us is not None else ""))
    lines = [f"rotation   {span}; {rule}", "",
             f"  {'profile':<16} {'eligible':>8} {'played':>6} {'never':>5} {'plays':>5} {'repeated':>8}  "
             f"{'gap days min/median/mean':<24} {'under gap':>9}"]

    def row(p: ProfileRotation) -> str:
        gap = f"{_days(p.gap_min)} / {_days(p.gap_median)} / {_days(p.gap_mean)}"
        return (f"  {p.profile:<16} {p.eligible:>8} {p.played:>6} {p.never:>5} {p.plays:>5} {p.repeated:>8}  "
                f"{gap:<24} {p.under_gap:>9}")

    lines += [row(p) for p in rep.profiles]
    lines.append(row(rep.total))
    lines.append(f"aired, no longer eligible  {rep.gone_shows} show(s), {rep.gone_plays} play(s)"
                 + (f", {rep.gone_under_gap} gap(s) under the rule" if rep.gone_under_gap else ""))
    lines.append("")
    lines.append("most played" + ("" if rep.top else "  none repeated"))
    for s in rep.top:
        who = s.profile or "no longer eligible"
        lines.append(f"  {s.package}  {s.plays} plays, last {local_text(s.last_us, tz)}  ({who})")
    if never:
        lines.append("")
        lines.append("never played" + ("" if rep.total.never else "  none"))
        for p in rep.profiles:
            if p.never_slugs:
                lines.append(f"  {p.profile} ({p.never})")
                lines += [f"    {slug}" for slug in p.never_slugs]
    return lines
