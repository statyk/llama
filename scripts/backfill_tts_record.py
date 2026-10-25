#!/usr/bin/env python3
"""One-off: backfill `dj_audio.tts` on packages emcee voiced before it
recorded how their clips were synthesized.

For each voiced package whose `dj_audio` lacks the `tts` key and whose
recorded `presenter` is in BACKFILL, write that presenter's record. Every
other presenter (including `?` and the house voice) is left alone and
counted. `voice` is written as "unknown", never recomputed: the clone hash
is over the reference clip (and, on mlx_audio, its transcript) as they were
at voicing time, which the files on disk today may not match. The record is
display-only (`station.manifest_tts`), so it never changes readiness. Dry
run by default; `--apply` updates the raw manifest JSON in place (atomic
write). Needs emcee installed (it may import it; emcee never imports this).
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from emcee.config import load_config
from emcee.errors import EmceeError
from emcee.package_io import Package, atomic_write

# Operator-vouched, 2026-10-25: every Phil package was voiced on Voxtral at
# the pinned model, every Jimmy Green (jamesbrown) package on local Qwen.
BACKFILL = {
    "phil": {"backend": "voxtral", "model": "voxtral-mini-tts-2603",
             "voice": "unknown"},
    "jamesbrown": {"backend": "mlx_audio",
                   "model": "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16",
                   "voice": "unknown"},
}


def backfill(station_root: Path, records: dict[str, dict], apply: bool) -> None:
    written = 0
    left: Counter[str] = Counter()
    for d in sorted(station_root.iterdir()):
        if not d.is_dir() or d.name.startswith(".") or not (d / "manifest.json").exists():
            continue
        pkg = Package(d)
        try:
            manifest = pkg.manifest()
        except EmceeError as exc:
            print(f"skip {d.name}: {exc}")
            continue
        dj_audio = manifest.get("dj_audio")
        if not isinstance(dj_audio, dict) or "tts" in dj_audio:
            continue
        presenter = dj_audio.get("presenter", "?")
        record = records.get(presenter) if isinstance(presenter, str) else None
        if record is None:
            left["house" if presenter is None else str(presenter)] += 1
            continue
        if apply:
            # A raw-dict update, never a DJAudioBlock round trip: a legacy
            # block lacks the model's required profile/profile_source, and
            # unknown keys must survive.
            try:
                data = json.loads(pkg.manifest_path.read_text())
                data["dj_audio"]["tts"] = dict(record)
                atomic_write(pkg.manifest_path, json.dumps(data, indent=2) + "\n")
            except Exception as exc:  # one bad package must not stop the sweep
                print(f"skip {d.name}: {exc}")
                continue
        print(f"{d.name}: {presenter} -> {record['backend']} {record['model']}")
        written += 1
    verb = "wrote" if apply else "would write"
    print(f"{verb} {written}")
    if left:
        print("left alone (no record, presenter not vouched for): "
              + ", ".join(f"{k} {v}" for k, v in sorted(left.items())))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--station-root", type=Path, default=None)
    ap.add_argument("--apply", action="store_true", help="write the manifests")
    args = ap.parse_args(argv)
    root = args.station_root or load_config().station.root
    if root is None:
        print("no station root: pass --station-root or set [station] root", file=sys.stderr)
        return 2
    backfill(Path(root), BACKFILL, args.apply)
    if not args.apply:
        print("dry run: pass --apply to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
