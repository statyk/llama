#!/usr/bin/env python3
"""The parent's naive filler (docs/superpowers/2026-10-10-playout-review/feasibility-sim.py),
re-derived as the scheduler's like-for-like baseline (spec "Measurement").

Edits to the original: the station root is an argument; anchors and the window
come from the clock (a) file (every block's weekday starts, `late_minutes`);
the fill exclusion is the clock's `[open] exclude_profiles`; an anchor that
starts after its window is counted as "overran" and a gap the random search
cannot fill as "not fillable" (the original folded overruns in as x1000 and
printed one figure); lengths are the scheduler's estimate (manifest
total_duration_sec plus each voiced package's clip lengths, else the 4-minute
allowance: `pieces.scan_delivered` when `transmitter` is importable, else the
same arithmetic on the manifest alone, which ignores clip sizes); 50 seeds;
JSON output.  Read-only: only manifests (and clip headers) are read.

The simulation is the original's: one week of anchors, one random show per
anchor (the profile's unused shows first), a random 4000-try fill, no join
gaps between shows, no history across weeks.
"""

import argparse
import glob
import json
import pickle
import random
import sys
import time
import tomllib
from pathlib import Path

SAMPLE_RATE, FRAME_SAMPLES = 44_100, 1024
ALLOWANCE_MIN = 4.0
TRIES = 4000
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def anchors_of(clock: dict) -> tuple[list[tuple[int, str]], float]:
    """[(minute of week, profile)] sorted, and the window (late_minutes)."""
    out, late = [], None
    for b in clock["block"]:
        if not b.get("profiles"):
            continue
        days = range(7) if b.get("days", "daily") == "daily" else [DAYS.index(d) for d in b["days"]]
        h, m = b["start"].split(":")
        for d in days:
            out.append((d * 1440 + int(h) * 60 + int(m), b["profiles"][0]))
        if b.get("late_minutes") is not None:
            late = b["late_minutes"] if late is None else max(late, b["late_minutes"])
    out.sort()
    return out, float(late if late is not None else clock.get("wiggle_minutes", 15))


def load_shows(root: Path, scan_cache: Path | None, *, extra: int | None = None,
               pause_samples: int | None = None) -> tuple[list[tuple[str | None, float]], str]:
    """`extra`/`pause_samples` default to the measured/config values; they are part of the cache key."""
    try:
        from transmitter import aacenc, grid, pieces
        if extra is None:
            extra = aacenc.extra_frames()
        if pause_samples is None:
            pause_samples = grid.samples_for_seconds(0.75)
    except ImportError:
        pieces = None
    if pieces is not None:
        key = {"root": str(root), "library": "delivered", "pause_samples": pause_samples, "extra": extra}
        if scan_cache is not None and scan_cache.is_file():
            got = pickle.loads(scan_cache.read_bytes())
            if not (isinstance(got, dict) and all(got.get(k) == v for k, v in key.items())):
                raise SystemExit(f"error: {scan_cache} was scanned for another root/library/pause/extra; "
                                 "remove it or use another path")
            return [(p.profile, p.frames * FRAME_SAMPLES / SAMPLE_RATE / 60) for p in got["pool"]], "scan-cache"
        pool = pieces.scan_delivered(root, now_s=time.time(), quiet_s=600.0,
                                     pause_samples=pause_samples, extra=extra)
        if scan_cache is not None:
            scan_cache.write_bytes(pickle.dumps({**key, "pool": pool}))
        return [(p.profile, p.frames * FRAME_SAMPLES / SAMPLE_RATE / 60) for p in pool], "pieces.scan_delivered"
    shows = []
    for m in sorted(glob.glob(str(root / "*" / "manifest.json"))):
        try:
            j = json.load(open(m))
        except (OSError, ValueError):
            continue
        if not isinstance(j, dict) or not isinstance(j.get("schema_version"), int) or j["schema_version"] < 3:
            continue
        d = j.get("total_duration_sec")
        if not isinstance(d, (int, float)):
            continue
        dj = j.get("dj_audio")
        prof = (dj or {}).get("profile") if isinstance(dj, dict) else None
        prof = prof or (j.get("source") or {}).get("profile")
        shows.append((prof, d / 60 + ALLOWANCE_MIN))
    return shows, "manifest-only (+4 min allowance)"


def run(shows, anchors, win, exclude, seed):
    rnd = random.Random(seed)
    used: set[int] = set()
    pool = list(range(len(shows)))
    t = anchors[0][0]
    overran = not_fillable = no_show = 0
    gaps = len(anchors) - 1
    for k, (a, prof) in enumerate(anchors):
        cands = [i for i in pool if shows[i][0] == prof and i not in used] or \
                [i for i in pool if shows[i][0] == prof]
        if not cands:
            no_show += 1
            t = max(t, a)
        else:
            i = rnd.choice(cands)
            used.add(i)
            t = max(t, a) + shows[i][1]
        if k + 1 == len(anchors):
            break
        lo = anchors[k + 1][0]
        hi = lo + win
        if t > hi:
            overran += 1
            continue
        fp = [j for j in pool if shows[j][0] not in exclude and j not in used]
        best = None
        for _ in range(TRIES):
            rnd.shuffle(fp)
            s, pick = t, []
            for j in fp:
                if s >= lo:
                    break
                if s + shows[j][1] <= hi:
                    pick.append(j)
                    s += shows[j][1]
            if lo <= s <= hi:
                best = pick
                break
        if best is None:
            not_fillable += 1
            t = lo
        else:
            used.update(best)
            t = s
    return overran, not_fillable, gaps, no_show


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--clock", type=Path, default=Path(__file__).with_name("clock-a.toml"))
    ap.add_argument("--seeds", type=int, default=50)
    ap.add_argument("--scan-cache", type=Path, default=None, help="pickle of scanned pieces (your own scratch file)")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    clock = tomllib.loads(a.clock.read_text())
    anchors, win = anchors_of(clock)
    exclude = set((clock.get("open") or {}).get("exclude_profiles") or [])
    shows, estimator = load_shows(a.root, a.scan_cache)
    tot = {"overran": 0, "not_fillable": 0, "gaps": 0, "no_anchor_show": 0}
    per_seed = []
    for seed in range(a.seeds):
        o, n, g, z = run(shows, anchors, win, exclude, seed)
        tot["overran"] += o
        tot["not_fillable"] += n
        tot["gaps"] += g
        tot["no_anchor_show"] += z
        per_seed.append({"seed": seed, "overran": o, "not_fillable": n})
    res = {**tot, "overran_share": tot["overran"] / tot["gaps"], "not_fillable_share": tot["not_fillable"] / tot["gaps"],
           "miss_share": (tot["overran"] + tot["not_fillable"]) / tot["gaps"],
           "window_minutes": win, "anchors_per_week": len(anchors), "seeds": a.seeds, "shows": len(shows),
           "exclude_profiles": sorted(exclude), "estimator": estimator, "root": str(a.root),
           "clock": a.clock.name, "per_seed": per_seed}
    a.out.write_text(json.dumps(res, indent=1) + "\n")
    print(f"{len(shows)} shows ({estimator}); window {win:g} min; {tot['gaps']} gaps over {a.seeds} seeds: "
          f"overran {tot['overran']} ({res['overran_share']:.1%}), not fillable {tot['not_fillable']} "
          f"({res['not_fillable_share']:.1%}), miss {res['miss_share']:.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
