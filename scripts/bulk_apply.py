#!/usr/bin/env python3
"""The bulk-apply campaign's operator script (plan Task 12 scaffold).

Subcommands: `pin` (pin the campaign to a release tag's commit), `arm` (the replay arm,
behind the version and pin gates), and `snapshot` / `seal` / `restore` (thin wrappers over
`llama.batch_snapshot`). Later tasks add the writing subcommands here. A refused gate
exits 2. Run with the pinned worktree's own interpreter:
`./.venv/bin/python scripts/bulk_apply.py ...`.
"""
import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import replay_holds

import llama
from llama import batch_snapshot
from llama.campaign_gate import GateRefused, read_pin, require_pinned_code, require_tools, write_pin
from llama.config import DEFAULT_ROOT, load_config
from llama.errors import LlamaError
from llama.replay import code_identity

REPO = Path(__file__).resolve().parent.parent


def _echo(msg: str) -> None:
    print(msg)


def _config(args):
    path = args.config or DEFAULT_ROOT / "config.toml"
    if args.config is not None and not args.config.exists():
        raise GateRefused(f"no such config: {args.config}")
    return load_config(path)


def cmd_pin(args) -> int:
    root = _config(args).root
    done = subprocess.run(["git", "-C", str(REPO), "rev-parse", f"{args.tag}^{{commit}}"],
                          capture_output=True, text=True)
    if done.returncode != 0:
        raise GateRefused(f"cannot resolve tag {args.tag} in {REPO}: {done.stderr.strip()}")
    sha = done.stdout.strip()
    ident = code_identity()
    if ident != sha:
        raise GateRefused(f"the running code is {ident}, not {args.tag} ({sha}); pin from a "
                          f"clean checkout of the tag")
    pin = write_pin(root, tag=args.tag, sha=sha, version=llama.__version__,
                    worktree=str(REPO), replace=args.replace)
    print(f"pinned {pin['tag']} {sha} ({pin['version']}) at {root / 'campaign' / 'pin.json'}")
    return 0


def cmd_arm(args) -> int:
    config = _config(args)
    pin = require_pinned_code(config.root)
    require_tools(_echo, pin=pin)
    ns = argparse.Namespace(out=args.out, held=False, all=True, slugs=None,
                            strip_structure_overrides=False, strip_title_overrides=False,
                            rekey_overrides=False, disable_slices=None, config=args.config,
                            scratch=None)
    try:
        return replay_holds.run(ns)
    except replay_holds.Refusal as err:
        raise GateRefused(str(err)) from err


def _read_slugs(path: Path) -> list[str]:
    return [l.strip() for l in path.read_text().splitlines() if l.strip()]


def _station_root(config) -> Path | None:
    return config.delivery_path


def cmd_snapshot(args) -> int:
    config = _config(args)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap = config.root / "campaign" / "snapshots" / stamp
    batch_snapshot.take(snap, config.root, _read_slugs(args.slugs),
                        station_root=_station_root(config))
    print(f"snapshot: {snap}")
    return 0


def cmd_seal(args) -> int:
    config = _config(args)
    batch_snapshot.seal(args.snap, config.root, station_root=_station_root(config))
    print(f"sealed: {args.snap}")
    return 0


def cmd_restore(args) -> int:
    config = _config(args)
    slugs = set(_read_slugs(args.slugs)) if args.slugs else None
    results = batch_snapshot.restore(args.snap, config.root, station_root=_station_root(config),
                                     apply=args.apply, slugs=slugs, echo=_echo)
    if not args.apply:
        print("dry run: nothing written (pass --apply)")
    return 0 if not any(a.startswith("refused") for _, a in results) else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=None,
                    help="config file (default ~/.llama/config.toml, as llama)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help):
        p = sub.add_parser(name, help=help)
        p.add_argument("--config", type=Path, default=argparse.SUPPRESS)
        p.set_defaults(fn=fn)
        return p

    p = add("pin", cmd_pin, "pin the campaign to a release tag (must be the running code)")
    p.add_argument("--tag", required=True)
    p.add_argument("--replace", action="store_true", help="overwrite an existing pin")
    p = add("arm", cmd_arm, "replay every show into an arm JSON (version and pin gated)")
    p.add_argument("--out", type=Path, required=True)
    p = add("snapshot", cmd_snapshot, "snapshot the listed shows into campaign/snapshots/")
    p.add_argument("--slugs", type=Path, required=True, help="a file of slugs, one per line")
    p = add("seal", cmd_seal, "seal a snapshot (record every show's after state)")
    p.add_argument("snap", type=Path)
    p = add("restore", cmd_restore, "rewind a snapshot's shows (dry run unless --apply)")
    p.add_argument("snap", type=Path)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--slugs", type=Path, default=None)
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except (GateRefused, LlamaError) as err:
        print(str(err), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
