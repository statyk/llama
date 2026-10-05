#!/usr/bin/env python3
"""One-off: purge the library audio of shows delivered before `llama deliver`
did it itself.

For every show dir whose manifest's `source.performance_id` has a `delivered`
ledger row, verify the station copy at `<dest>/<slug>` holds every manifest
track at the same size (`catalog.purge_package_audio`, the same check deliver
runs) and only then delete `shows/<slug>/package/audio/*`. Each show is
handled under its show lock. Dry run by default; `--apply` deletes. Imports
llama; nothing imports this.
"""
import argparse
import sys
from pathlib import Path

from llama.catalog import human_bytes, purge_package_audio
from llama.config import load_config
from llama.ledger import Ledger
from llama.locks import file_lock
from llama.workspace import ShowWorkspace, read_json


def _manifest_pid(ws: ShowWorkspace) -> str | None:
    try:
        return read_json(ws.package_dir / "manifest.json")["source"]["performance_id"]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def purge(root: Path, dest: Path, apply: bool) -> None:
    delivered = {e.performance_id for e in Ledger(root / "ledger.jsonl").entries()
                 if e.status == "delivered"}
    shows_dir = root / "shows"
    freed = purged = already = 0
    for d in sorted(shows_dir.iterdir()) if shows_dir.is_dir() else []:
        ws = ShowWorkspace(d)
        if not d.is_dir() or _manifest_pid(ws) not in delivered:
            continue
        with file_lock(ws.lock):
            r = purge_package_audio(ws, dest / d.name, dry_run=not apply)
        if r.skipped == "already purged":
            already += 1
            continue
        if r.skipped:
            print(f"{d.name}: kept ({r.skipped})")
            continue
        if r.warning:
            print(f"{d.name}: partly purged ({r.warning})")
        else:
            print(f"{d.name}: {'purged' if apply else 'would purge'} ({human_bytes(r.freed)})")
        freed += r.freed
        purged += 1
    verb = "freed" if apply else "would free"
    print(f"{verb} {human_bytes(freed)} across {purged} show(s); {already} already purged")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=None)
    ap.add_argument("--dest", type=Path, default=None,
                    help="the delivered-packages folder (default: config delivery_path)")
    ap.add_argument("--apply", action="store_true", help="delete the audio")
    args = ap.parse_args(argv)
    config = load_config(args.config)
    dest = args.dest or config.delivery_path
    if dest is None:
        print("no destination: pass --dest or set delivery_path", file=sys.stderr)
        return 2
    purge(config.root, Path(dest), args.apply)
    if not args.apply:
        print("dry run: pass --apply to delete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
