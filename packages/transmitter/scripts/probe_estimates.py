#!/usr/bin/env python3
"""Hugo premise probe: do package-scan estimates land within seconds of the
decoded frame counts?  STRICTLY READ-ONLY: it reads the config, the station
root and the analysis cache, and writes nothing (no cache write, no workspace
file).  Run it on hugo with the production config:

    python probe_estimates.py --config ~/.transmitter/config.toml [--limit N]
    python probe_estimates.py --config ... --time-one SLUG   # one cold analysis, no cache write
"""

import argparse
import statistics
import sys
import time
from pathlib import Path

from transmitter import aacenc, analysis, grid, mp3info, pieces, render, station
from transmitter.config import load_config
from transmitter.grid import FRAME_SAMPLES, SAMPLE_RATE
from transmitter.workspace import Workspace


def _is_64k(show: station.Show) -> bool:
    sizes = show.meta.get("sizes") or {}
    flags = []
    for e in show.entries:
        if e.kind != "clip":
            continue
        secs = mp3info.mp3_seconds(show.dir / e.path, sizes.get(e.path))
        size = sizes.get(e.path)
        flags.append(secs is not None and size is not None and secs > 0
                     and abs((size * 8 / secs) - 64_000) < 2_000)
    return bool(flags) and all(flags)


def _why_not_eligible(slug: str, root: Path | None, ineligible: list[station.Ineligible]) -> str:
    """Why `slug` is not an eligible package: its Ineligible reasons (a quiet period is among them), or
    'not found' when the station root has no such package."""
    got = next((i for i in ineligible if i.slug == slug), None)
    if got is not None:
        return f"error: package {slug!r} is not eligible: " + "; ".join(got.reasons)
    if root is not None and (Path(root) / slug).is_dir():
        return f"error: package {slug!r} is not eligible (no reason reported)"
    return f"error: package {slug!r} not found in the station root"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, required=True, help="transmitter config.toml")
    ap.add_argument("--limit", type=int, default=None, help="probe at most N packages")
    ap.add_argument("--time-one", metavar="SLUG", default=None,
                    help="time one cold analysis of SLUG (nothing is cached) and exit")
    args = ap.parse_args(argv)

    if not args.config.is_file():
        print(f"error: --config {args.config} is not an existing file", file=sys.stderr)
        return 2
    cfg = load_config(args.config)
    cache_dir = Workspace(cfg.root).cache_dir
    shows, _skipped = station.scan(cfg.station.root, now_s=time.time(),
                                   quiet_s=cfg.station.quiet_minutes * 60)
    if args.time_one:
        match = [s for s in shows if s.slug == args.time_one]
        if not match:
            print(_why_not_eligible(args.time_one, cfg.station.root, _skipped), file=sys.stderr)
            return 1
        t0 = time.monotonic()
        result = analysis.analyze_show(match[0], cfg.render.ffmpeg)
        print(f"{args.time_one}: cold analysis {time.monotonic() - t0:.1f} s "
              f"({len(result.files)} files, not cached)")
        return 0

    extra = aacenc.extra_frames(cfg.render.ffmpeg)
    pause = grid.samples_for_seconds(cfg.render.clip_pause_seconds)
    diffs: list[float] = []
    for show in shows:
        if args.limit is not None and len(diffs) >= args.limit:
            break
        cached = analysis.load_cached(cache_dir, show.key)
        if cached is None:
            continue
        exact = render.planned_frames(cached, pause, extra)
        est = pieces.estimate_frames(show, pause_samples=pause, extra=extra)
        diff = (est - exact) * FRAME_SAMPLES / SAMPLE_RATE
        diffs.append(abs(diff))
        print(f"{show.slug}\test={est}\texact={exact}\tdiff={diff:+.2f}s\t"
              f"clips64k={'yes' if _is_64k(show) else 'no'}")
    if not diffs:
        print("no eligible package has a cached analysis")
        return 0
    print(f"n={len(diffs)} median |diff|={statistics.median(diffs):.2f}s max |diff|={max(diffs):.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
