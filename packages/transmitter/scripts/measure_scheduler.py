#!/usr/bin/env python3
"""Offline measurement of the scheduler (spec "Measurement").

One continuous `scheduler.project` over the whole span, from an empty plan,
history accumulating through the projection's own recency, no per-week restart;
weekly figures are slices of that one projection.  Lengths are ESTIMATES only.
STRICTLY READ-ONLY toward the library: manifests and clip headers are read, no
audio is decoded, nothing is written there.

    python measure_scheduler.py --root /Volumes/media/lma-radio/delivered \\
        --clock clock-a.toml --weeks 50 --library delivered --no-interstitials --out a.json

The projection starts at frame 0 = the nominal start of the first clock
occurrence on or after `--start-date` (local midnight of that date, default
2026-11-02), so no block is entered mid-way.  No interstitial library is
loaded in any mode (there is none on this machine), so station IDs and
announcements never appear; `--no-interstitials` records that in the result.
"""

import argparse
import json
import pickle
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

from transmitter import aacenc, grid, pieces, station
from transmitter.clock import ClockConfig, load_clock, occurrences
from transmitter.grid import iso_to_us
from transmitter.history import Recency
from transmitter.scheduler import SchedulerInput, project

PAUSE_SECONDS = 0.75        # config default render.clip_pause_seconds
GAP_SECONDS = 2.0           # config default render.show_gap_seconds
QUIET_SECONDS = 600.0       # config default station.quiet_minutes * 60 (only affects voiced/unvoiced split)
WEEK_US = 7 * 86_400_000_000
GAP_BUCKETS = ((1, "<1d"), (7, "1-7d"), (30, "7-30d"), (45, "30-45d"), (90, "45-90d"), (float("inf"), ">=90d"))


def _minutes(frames: int) -> float:
    return frames * grid.FRAME_SAMPLES / grid.SAMPLE_RATE / 60


def _quantile(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def _summarize(pps: list, clock: ClockConfig, starts: list) -> dict:
    """Figures over the show rows `pps` (planned pieces) and `starts` (each
    occurrence's first show)."""
    block_cfg = {b.name: b for b in clock.block}
    misses = sum(1 for p in starts if p.miss)
    fill: Counter = Counter()
    bends: Counter = Counter()
    own: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])      # block -> [own min, total min]
    open_by_profile: Counter = Counter()
    fill_by_profile: Counter = Counter()
    degraded = sum(1 for p in starts if p.degraded)
    for p in pps:
        mins = _minutes(p.piece.frames)
        if p.fill:
            fill[p.fill] += mins
            fill_by_profile[p.piece.profile or "?"] += mins
        for b in p.bends:
            bends[b] += 1
        cfg = block_cfg[p.block]
        if cfg.profiles:
            o = own[p.block]
            o[1] += mins
            if p.piece.profile in cfg.profiles:
                o[0] += mins
        else:
            open_by_profile[p.piece.profile or "?"] += mins
    own_total = [sum(v[0] for v in own.values()), sum(v[1] for v in own.values())]
    return {
        "block_starts": len(starts), "misses": misses,
        "miss_share": misses / len(starts) if starts else None,
        "degraded_blocks": degraded,
        "show_minutes": round(sum(_minutes(p.piece.frames) for p in pps), 1),
        "fill_minutes": {k: round(v, 1) for k, v in sorted(fill.items())},
        "fill_minutes_by_profile": {k: round(v, 1) for k, v in fill_by_profile.most_common()},
        "bends": dict(sorted(bends.items())),
        "own_profile_share": own_total[0] / own_total[1] if own_total[1] else None,
        "own_profile_share_by_block": {k: (v[0] / v[1] if v[1] else None) for k, v in sorted(own.items())},
        "open_minutes_by_profile": {k: round(v, 1) for k, v in open_by_profile.most_common()},
    }


def _repeat_gaps(pps: list, epoch_us: int) -> dict:
    last: dict[str, int] = {}
    gaps: list[float] = []
    for p in pps:
        us = epoch_us + grid.frame_to_us(p.start_frame)
        if p.piece.slug in last:
            gaps.append((us - last[p.piece.slug]) / 86_400_000_000)
        last[p.piece.slug] = us
    out = {"shows_aired": len(last), "repeats": len(gaps)}
    if gaps:
        counts = Counter()
        for g in gaps:
            for hi, name in GAP_BUCKETS:
                if g < hi:
                    counts[name] += 1
                    break
        out.update(min=round(min(gaps), 2), p10=round(_quantile(gaps, 0.1), 1),
                   median=round(statistics.median(gaps), 1), p90=round(_quantile(gaps, 0.9), 1),
                   buckets={name: counts.get(name, 0) for _, name in GAP_BUCKETS})
    return out


def _gaps_by_profile(pps: list, epoch_us: int) -> dict:
    last: dict[str, int] = {}
    gaps: dict[str, list[float]] = defaultdict(list)
    for p in pps:
        us = epoch_us + grid.frame_to_us(p.start_frame)
        if p.piece.slug in last:
            gaps[p.piece.profile or "?"].append((us - last[p.piece.slug]) / 86_400_000_000)
        last[p.piece.slug] = us
    return {k: {"repeats": len(v), "min": round(min(v), 2), "p10": round(_quantile(v, 0.1), 1),
                "median": round(statistics.median(v), 1), "max": round(max(v), 1),
                "within_7d": sum(1 for g in v if g < 7)} for k, v in sorted(gaps.items())}


def measure(pool: list, clock: ClockConfig, *, weeks: int, start_date: date | None = None,
            seed: int = 0, gap_seconds: float = GAP_SECONDS) -> dict:
    tz = ZoneInfo(clock.timezone)
    start_date = start_date or date(2026, 11, 2)
    midnight = datetime.combine(start_date, dtime(0, 0), tzinfo=tz)
    from_us = int(midnight.timestamp()) * 1_000_000
    span_us = weeks * WEEK_US
    first = occurrences(clock, from_us, from_us + span_us + 8 * 86_400_000_000)
    first = next(o for o in first if o.nominal_us >= from_us)
    epoch_us = first.nominal_us
    until_frame = grid.frames_ceil(grid.samples_for_seconds(span_us / 1e6))
    inp = SchedulerInput(rows=(), start_frame=0, run_start=True, pool=list(pool), clock=clock, rec=Recency(),
                         epoch_us=epoch_us, gap_frames=grid.gap_frames(gap_seconds), seed=seed)
    t0 = time.monotonic()
    out = project(inp, until_frame=until_frame, ahead=2)
    elapsed = time.monotonic() - t0

    epoch_local = (datetime.fromtimestamp(epoch_us / 1e6, tz)).date()

    def week_of(p) -> int:
        """Week index in LOCAL dates: 7-day spans of the local calendar from the start day,
        so a DST change does not move a block into the next week."""
        d = datetime.fromtimestamp(iso_to_us(p.nominal_start) / 1e6, tz).date()
        return (d - epoch_local).days // 7

    shows = [p for p in out if p.role == "show" and 0 <= week_of(p) < weeks]
    starts = [p for p in shows if p.miss is not None]
    per_week = []
    for w in range(weeks):
        per_week.append({"week": w, **_summarize([p for p in shows if week_of(p) == w], clock,
                                                 [p for p in starts if week_of(p) == w])})
    per_week_occ = sum(len(b.weekdays()) for b in clock.block)
    total = _summarize(shows, clock, starts)
    total["repeat_gap_days"] = _repeat_gaps(shows, epoch_us)
    total["repeat_gap_days_by_profile"] = _gaps_by_profile(shows, epoch_us)
    # a block that landed early / was missed, by block name
    miss_by_block: Counter = Counter(p.block for p in starts if p.miss)
    starts_by_block: Counter = Counter(p.block for p in starts)
    total["miss_by_block"] = {k: [miss_by_block.get(k, 0), n] for k, n in sorted(starts_by_block.items())}
    aired: dict[str, set] = defaultdict(set)
    for p in shows:
        aired[p.piece.profile or "?"].add(p.piece.slug)
    pool_n = Counter(p.profile or "?" for p in pool if p.kind == "show")
    total["distinct_aired_by_profile"] = {k: [len(aired.get(k, ())), n] for k, n in sorted(pool_n.items())}
    total["shows_per_block_start"] = round(len(shows) / len(starts), 2) if starts else None
    return {
        "weeks": per_week, "total": total, "occurrences_per_week": per_week_occ,
        "clock_start": first.nominal_iso, "project_seconds": round(elapsed, 2),
        "pool": {"shows": sum(1 for p in pool if p.kind == "show"),
                 "profiles": dict(Counter(p.profile or "?" for p in pool if p.kind == "show").most_common())},
        "seed": seed,
    }


def load_pool(root: Path, library: str, *, pause_samples: int, extra: int, scan_cache: Path | None = None) -> list:
    if scan_cache is not None and scan_cache.is_file():
        got = pickle.loads(scan_cache.read_bytes())
        if not (isinstance(got, dict) and got.get("root") == str(root) and got.get("library") == library):
            raise SystemExit(f"error: {scan_cache} was scanned for another root/library; remove it or use another path")
        return got["pool"]
    if library == "delivered":
        pool = pieces.scan_delivered(root, now_s=time.time(), quiet_s=QUIET_SECONDS,
                                     pause_samples=pause_samples, extra=extra)
    else:
        shows = station.scan(root, now_s=time.time(), quiet_s=QUIET_SECONDS)[0]
        lengths = pieces.LengthCache(None, pause_samples, extra)
        pool, _ = pieces.build_pool(shows, [], lengths=lengths, clip_dir="", read_only=True)
    if scan_cache is not None:
        scan_cache.write_bytes(pickle.dumps({"root": str(root), "library": library, "pool": pool}))      # the caller's own scratch file, never the library
    return pool


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--clock", type=Path, required=True)
    ap.add_argument("--weeks", type=int, default=50)
    ap.add_argument("--library", choices=("delivered", "eligible"), default="delivered")
    ap.add_argument("--no-interstitials", action="store_true")
    ap.add_argument("--start-date", type=date.fromisoformat, default=date(2026, 11, 2))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--exclude-slugs", type=Path, default=None, help="file of package slugs, one per line, to drop from the pool")
    ap.add_argument("--extra", type=int, default=None, help="encoder extra frames (default: measured with ffmpeg)")
    ap.add_argument("--scan-cache", type=Path, default=None, help="pickle of the scanned pool (your own scratch file)")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    extra = a.extra if a.extra is not None else aacenc.extra_frames()
    pause = grid.samples_for_seconds(PAUSE_SECONDS)
    t0 = time.monotonic()
    pool = load_pool(a.root, a.library, pause_samples=pause, extra=extra, scan_cache=a.scan_cache)
    scan_s = time.monotonic() - t0
    excluded = 0
    if a.exclude_slugs is not None:
        drop = {ln.strip() for ln in a.exclude_slugs.read_text().splitlines() if ln.strip() and not ln.startswith("#")}
        before = len(pool)
        pool = [p for p in pool if p.slug not in drop]
        excluded = before - len(pool)
    res = measure(pool, load_clock(a.clock), weeks=a.weeks, start_date=a.start_date, seed=a.seed)
    res.update(library=a.library, root=str(a.root), clock_file=a.clock.name, weeks_requested=a.weeks,
               no_interstitials=a.no_interstitials, excluded_slugs=excluded, extra_frames=extra, scan_seconds=round(scan_s, 1))
    a.out.write_text(json.dumps(res, indent=1) + "\n")
    t = res["total"]
    print(f"{a.clock.name}: {t['block_starts']} block starts, {t['misses']} outside window "
          f"({t['miss_share']:.1%}); project {res['project_seconds']} s, scan {scan_s:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
