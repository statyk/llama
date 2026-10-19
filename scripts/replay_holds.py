#!/usr/bin/env python3
"""Offline replay of the library's holds (held-backlog spec, slice 0).

`run` recomputes each show's flags from its stored artifacts and the
archive.org cache, under the code of THIS tree, with cache-only clients and
no LLM, and writes one "arm" JSON (plan "Contracts": Harness arm file).
`compare` (diffing two arms) is Task 6.

IO discipline is the point: the library is only read. Each show replays into
`<scratch>/<slug>`, removed after the show; the arm JSON is the one file
written. A scratch or `--out` that overlaps the library root is refused, and
so is a run whose imported `llama` is not this tree's (the CLAUDE.md
worktree and copied-tree trap, enforced rather than remembered). Run it with
the tree's own interpreter: `./.venv/bin/python scripts/replay_holds.py run
--out <arm.json>`.
"""
import argparse
import json
import logging
import os
import shutil
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import llama
from llama.catalog import derive_state
from llama.config import DEFAULT_ROOT, load_config
from llama.ledger import Ledger
from llama.replay import (CacheOnlyIA, ShowReplay, code_identity, config_fingerprint,
                          replay_show, setlistfm_client, setlistfm_configured)
from llama.workspace import ShowWorkspace

PROGRESS_EVERY = 100


class Refusal(Exception):
    """Exit 2 with this message: nothing has been read or written yet."""


def _overlaps(a: Path, b: Path) -> bool:
    a, b = a.resolve(), b.resolve()
    return a == b or a in b.parents or b in a.parents


def _check_identity() -> None:
    """`llama.__file__` (read at call time) must resolve under this tree's
    `packages/llama/src` (ruling M2: worktrees nest inside the main repo, so
    the bare repo root would accept a worktree's llama)."""
    tree = Path(__file__).resolve().parents[1]
    src = tree / "packages" / "llama" / "src"
    print(f"llama: {llama.__file__}", file=sys.stderr)
    if not Path(llama.__file__).resolve().is_relative_to(src):
        raise Refusal(f"refusing to run: llama imports from {llama.__file__}, "
                      f"not from this tree {tree}")


def _read_slugs(path: Path) -> list[str]:
    slugs = sorted({line.strip() for line in path.read_text().splitlines() if line.strip()})
    for s in slugs:
        if s in (".", "..") or "/" in s or os.sep in s:
            raise Refusal(f"invalid slug in {path}: {s!r}")
    return slugs


def _targets(shows_dir: Path, scope: str, slugs: list[str],
             delivered: set[str]) -> list[Path]:
    """The show directories to replay. Enumerated by hand, not via
    `catalog.iter_shows` (ruling M3: that reads every show's overrides.json,
    so one malformed file would abort the run). Under `held`, a show whose
    state cannot be derived is kept: `replay_show` records why."""
    if scope == "slugs":
        return [shows_dir / s for s in slugs]
    dirs = sorted(d for d in shows_dir.iterdir() if d.is_dir()) if shows_dir.is_dir() else []
    if scope == "all":
        return dirs
    out = []
    for d in dirs:
        try:
            if derive_state(ShowWorkspace(d), delivered)[0] != "held":
                continue
        except Exception:
            pass
        out.append(d)
    return out


def run(args: argparse.Namespace) -> int:
    _check_identity()
    config_path = args.config or DEFAULT_ROOT / "config.toml"   # as `llama` does
    if args.config is not None and not args.config.exists():
        raise Refusal(f"no such config: {args.config}")
    config = load_config(config_path)
    root = config.root
    if _overlaps(args.out, root):
        raise Refusal(f"refusing --out {args.out}: it overlaps the library root {root}")
    if args.scratch is not None and _overlaps(args.scratch, root):
        raise Refusal(f"refusing scratch {args.scratch}: it overlaps the library root {root}")
    scope = "slugs" if args.slugs else ("all" if args.all else "held")
    slugs = _read_slugs(args.slugs) if args.slugs else []

    delivered = {e.performance_id for e in Ledger(root / "ledger.jsonl").entries()
                 if e.status == "delivered"}
    targets = _targets(root / "shows", scope, slugs, delivered)
    ia = CacheOnlyIA(root / "cache")
    slfm = setlistfm_client(config)

    own_scratch = args.scratch is None
    scratch = Path(tempfile.mkdtemp(prefix="replay-")) if own_scratch else args.scratch
    scratch.mkdir(parents=True, exist_ok=True)
    rows: dict[str, dict] = {}
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        for i, d in enumerate(targets, 1):
            if not d.is_dir():
                rows[d.name] = ShowReplay(slug=d.name, state="missing", outcome="unreplayable",
                                          unreplayable="show directory missing").to_dict()
            else:
                show_scratch = scratch / d.name
                try:
                    rows[d.name] = replay_show(ShowWorkspace(d), config=config, ia=ia,
                                               slfm=slfm, scratch=show_scratch,
                                               delivered=delivered).to_dict()
                finally:
                    shutil.rmtree(show_scratch, ignore_errors=True)
            if i % PROGRESS_EVERY == 0:
                print(f"replayed {i}/{len(targets)}", file=sys.stderr)
    finally:
        logging.disable(previous)
        if own_scratch:
            shutil.rmtree(scratch, ignore_errors=True)

    arm = {
        "sha": code_identity(),
        "config_fingerprint": config_fingerprint(config),
        "setlistfm_configured": setlistfm_configured(config),
        "scope": scope,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "llama_file": llama.__file__,
        "root": str(root),
        "shows": {slug: rows[slug] for slug in sorted(rows)},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_name(f".{args.out.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(arm, indent=1) + "\n")
    os.replace(tmp, args.out)
    counts = Counter(r["outcome"] for r in rows.values())
    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    print(f"replayed {len(rows)} show(s): {summary}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="replay shows into an arm JSON")
    r.add_argument("--out", type=Path, required=True, help="the arm JSON to write")
    scope = r.add_mutually_exclusive_group()
    scope.add_argument("--held", action="store_true", help="held shows only (the default)")
    scope.add_argument("--all", action="store_true", help="every show in the library")
    scope.add_argument("--slugs", type=Path, help="a file of slugs, one per line")
    r.add_argument("--config", type=Path, default=None,
                   help="config file (default ~/.llama/config.toml, as llama)")
    r.add_argument("--scratch", type=Path, default=None,
                   help="scratch directory (default: a temp dir removed at exit)")
    args = ap.parse_args(argv)
    try:
        return run(args)
    except Refusal as err:
        print(str(err), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
