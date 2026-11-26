#!/usr/bin/env python3
"""Time the concert assembler on real pieces: assemble N breaks (P pieces each,
drawn from the present `piece-*.mp3` files of a folder) into a temp dir and
print, per break, the assembly seconds and the analysis seconds (the same
`analysis.analyze_show` the plan uses; nothing is cached). Writes only under a
temporary directory:

    python time_assembly.py <pieces dir> [--breaks 5] [--per-break 6] [--bed /abs/bed.mp3] [--ffmpeg ffmpeg]
"""

import argparse
import random
import sys
import tempfile
import time
from pathlib import Path

from transmitter import analysis
from transmitter.announce_config import AnnounceSettings
from transmitter.assemble import Assembler
from transmitter.concert import BreakContent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pieces", type=Path)
    ap.add_argument("--breaks", type=int, default=5)
    ap.add_argument("--per-break", type=int, default=6)
    ap.add_argument("--bed", type=Path, default=None)
    ap.add_argument("--ffmpeg", default="ffmpeg")
    args = ap.parse_args(argv)
    ids = sorted(p.name[len("piece-"):-len(".mp3")] for p in args.pieces.glob("piece-*.mp3")
                 if not p.name.startswith(".") and p.stat().st_size > 0)
    if not ids:
        print(f"no piece-*.mp3 in {args.pieces}", file=sys.stderr)
        return 1
    rng = random.Random(0)
    settings = AnnounceSettings(bed=args.bed.resolve() if args.bed else None)
    with tempfile.TemporaryDirectory() as tmp:
        asm = Assembler(pieces=args.pieces, out_dir=Path(tmp), settings=settings, ffmpeg=args.ffmpeg)
        for n in range(args.breaks):
            chosen = rng.sample(ids, min(args.per_break, len(ids)))
            # the text only picks the gap after each piece; unknown here, so none ends a phrase
            content = BreakContent(pieces=tuple((i, "") for i in chosen), entries=(), names=(),
                                   phrases=("next",), y_time_id=None)
            t0 = time.monotonic()
            show = asm.build(content)
            t1 = time.monotonic()
            result = analysis.analyze_show(show, args.ffmpeg)
            t2 = time.monotonic()
            frames = sum(f.samples for f in result.files)
            print(f"break {n + 1}: {len(chosen)} pieces, {frames / 44100:.1f} s of audio, "
                  f"assembly {t1 - t0:.2f} s, analysis {t2 - t1:.2f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
