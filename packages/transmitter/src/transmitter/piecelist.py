"""The needed announcement pieces on disk: plan_step writes each missing text as
`<interstitials>/pieces/piece-<id>.txt` for emcee to voice, and keeps the whole
list in `<root>/pieces-needed.json`. transmitter never creates `pieces/` (its
absence keeps the feature dormant), never deletes a piece, and ignores every
dot-prefixed file (a temp of either side) and any name that is not exactly
`piece-<12 hex>.<txt|mp3|failed|expect>`."""

import json
import os
import re
import stat
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from transmitter import interstitials
from transmitter.concert import NeededPiece
from transmitter.config import TransmitterConfig
from transmitter.workspace import Workspace, write_json

PIECES_DIR = "pieces"
WRITES_PER_STEP = 250
TMP_MAX_AGE_S = 3600
_NAME = re.compile(r"^piece-([0-9a-f]{12})\.(txt|mp3|failed|expect)$")


def pieces_folder(cfg: TransmitterConfig) -> Path | None:
    base = interstitials.folder(cfg)
    return None if base is None else base / PIECES_DIR


def _clean_temps(folder: Path, names: Sequence[str], now_s: float) -> None:
    """Delete this side's own stale `.piece-*.txt.*.tmp` (emcee's `.mp3`/`.failed`
    temps are emcee's to clean); a failure here never matters."""
    for name in names:
        if not (name.startswith(".piece-") and name.endswith(".tmp") and ".txt." in name):
            continue
        try:
            if os.stat(folder / name).st_mtime < now_s - TMP_MAX_AGE_S:
                os.unlink(folder / name)
        except OSError:
            pass


def write_texts(folder: Path, needed: Sequence[NeededPiece], *, now_s: float) -> tuple[int, int]:
    """Write the texts `folder` lacks (at most WRITES_PER_STEP): returns
    (written, still_to_write). Raises OSError (also when `folder` is missing:
    it is never created). Each file lands by temp + fsync + rename, so a reader
    never sees a half-written text."""
    names = os.listdir(folder)
    have = set(names)
    _clean_temps(folder, names, now_s)
    todo = [p for p in needed if f"piece-{p.id}.txt" not in have]
    written = 0
    for piece in todo[:WRITES_PER_STEP]:
        final = folder / f"piece-{piece.id}.txt"
        tmp = folder / f".piece-{piece.id}.txt.{os.getpid()}-{uuid.uuid4().hex[:8]}.tmp"
        try:
            with open(tmp, "wb") as f:
                f.write(piece.text.encode("utf-8"))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, final)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        written += 1
    return written, len(todo) - written


def _scan(folder: Path | None, ext: str) -> list[tuple[str, os.stat_result]]:
    if folder is None:
        return []
    out = []
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    for name in names:
        m = _NAME.match(name)
        if not m or m.group(2) != ext:
            continue
        try:
            st = os.stat(folder / name)
        except OSError:
            continue
        if stat.S_ISREG(st.st_mode):
            out.append((m.group(1), st))
    return out


def present_ids(folder: Path | None, *, now_s: float, quiet_s: float) -> frozenset[str]:
    """Ids with a usable `piece-<id>.mp3`: a regular, non-empty file untouched
    for `quiet_s`."""
    return frozenset(i for i, st in _scan(folder, "mp3") if st.st_size > 0 and now_s - st.st_mtime >= quiet_s)


def failed_ids(folder: Path | None) -> frozenset[str]:
    return frozenset(i for i, _ in _scan(folder, "failed"))


def save_needed(ws: Workspace, needed: Sequence[NeededPiece], *, now_us: int) -> None:
    """Write the workspace list, only when its pieces changed."""
    pieces = [{"id": p.id, "text": p.text, "kind": p.kind} for p in needed]
    try:
        old = json.loads(ws.pieces_needed_path.read_text())
        if isinstance(old, dict) and old.get("pieces") == pieces:
            return
    except (OSError, ValueError):
        pass
    write_json(ws.pieces_needed_path, {"updated_us": now_us, "pieces": pieces})


def load_needed(ws: Workspace) -> list[NeededPiece] | None:
    """The saved list, or None when absent or unusable. Never raises."""
    try:
        rows = json.loads(ws.pieces_needed_path.read_text())["pieces"]
        if not all(isinstance(r, dict) and all(isinstance(r.get(k), str) for k in ("id", "text", "kind"))
                   for r in rows):
            return None
        return [NeededPiece(r["id"], r["text"], r["kind"]) for r in rows]
    except Exception:
        return None


@dataclass(frozen=True)
class PieceCounts:
    needed: int
    present: int
    failed: int
    missing: int


def counts(ws: Workspace, folder: Path | None, *, now_s: float, quiet_s: float) -> PieceCounts | None:
    needed = load_needed(ws)
    if needed is None:
        return None
    ids = {p.id for p in needed}
    present = present_ids(folder, now_s=now_s, quiet_s=quiet_s) & ids
    failed = (failed_ids(folder) & ids) - present
    return PieceCounts(len(ids), len(present), len(failed), len(ids) - len(present) - len(failed))
