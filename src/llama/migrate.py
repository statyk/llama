"""One-time move of runs/*/shows/* into the canonical shows/ library."""
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from llama.catalog import legacy_show_dirs, stage_depth
from llama.models import Criteria, Provenance, ShortlistEntry
from llama.util import slugify
from llama.workspace import (RunWorkspace, ShowWorkspace, read_model,
                             read_model_list, write_artifact)

log = logging.getLogger("llama")


@dataclass
class Move:
    src: Path
    dest: Path
    run: str
    winner: bool  # False: left in place (collision loser or target exists)


def plan_migration(root: Path) -> list[Move]:
    by_slug: dict[str, list[Path]] = {}
    for d in legacy_show_dirs(root):
        by_slug.setdefault(d.name, []).append(d)
    moves: list[Move] = []
    for slug, sources in sorted(by_slug.items()):
        dest = root / "shows" / slug
        # An existing target always wins: keeps migration idempotent.
        winner = None if dest.exists() else max(
            sources, key=lambda s: (stage_depth(ShowWorkspace(s)), s.parent.parent.name))
        for src in sorted(sources):
            moves.append(Move(src=src, dest=dest, run=src.parent.parent.name,
                              winner=src == winner))
    return moves


def _backfill_provenance(root: Path, move: Move) -> None:
    ws = ShowWorkspace(move.dest)
    if ws.provenance.exists():
        return
    run_ws = RunWorkspace(root, move.run)
    script = True
    if run_ws.criteria.exists():
        script = read_model(run_ws.criteria, Criteria).script
    if not run_ws.shortlist.exists():
        log.warning("no shortlist in %s: %s left without provenance", move.run, move.dest.name)
        return
    for entry in read_model_list(run_ws.shortlist, ShortlistEntry):
        if slugify(entry.candidate.performance_id) == move.dest.name:
            dossier = entry.assessment.rationale
            if entry.external_reputation:
                dossier += "\n\nExternal reputation: " + entry.external_reputation
            write_artifact(ws.provenance, Provenance(
                performance_id=entry.candidate.performance_id, run=move.run,
                dossier=dossier, candidate=entry.candidate, script=script,
                processed_at=datetime.now(timezone.utc).isoformat()))
            return
    log.warning("no shortlist entry for %s in %s: left without provenance",
                move.dest.name, move.run)


def apply_migration(root: Path, moves: list[Move]) -> None:
    for move in moves:
        if not move.winner:
            log.warning("left in place (collision or already migrated): %s", move.src)
            continue
        move.dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(move.src), str(move.dest))
        _backfill_provenance(root, move)
    # tidy now-empty runs/*/shows dirs
    for shows_dir in (root / "runs").glob("*/shows"):
        if shows_dir.is_dir() and not any(shows_dir.iterdir()):
            shows_dir.rmdir()
