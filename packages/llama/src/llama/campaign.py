"""The per-show campaign record (bulk-apply spec "The library side").

`<show>/campaign.json` says when and why a show was marked for re-processing,
the stage re-processing starts from, and once processed: when, the input
digests and the sha256 of the package manifest built. It is kept, never
deleted, and is deliberately NOT part of `replay.input_digests` nor of
`workspace.show_stage_artifacts` (a redo must not drop it).

Awaiting fix = marks non-empty and (processed is None or processed.at is
before the last mark's `at`).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from llama.errors import LlamaError
from llama.workspace import ShowWorkspace, atomic_write_bytes

CAMPAIGN_FILE = "campaign.json"
FROZEN_FILE = "campaign/needs-llm-frozen.json"


class CampaignUnreadable(LlamaError):
    """campaign.json exists but cannot be read; never treated as "no record"."""


class CampaignMark(BaseModel):
    at: str
    reason: str
    start_stage: Literal["gather", "select"]
    batch: str


class CampaignProcessed(BaseModel):
    at: str
    digests: dict[str, str | None]
    manifest_sha256: str | None = None


class CampaignClear(BaseModel):
    at: str
    outcome: Literal["equal", "change accepted"]


class CampaignRecord(BaseModel):
    marks: list[CampaignMark] = []
    processed: CampaignProcessed | None = None
    clears: list[CampaignClear] = []


def frozen_slugs(root: Path) -> frozenset[str]:
    """The `slugs` of `<root>/campaign/needs-llm-frozen.json`; empty when the
    file is missing or unreadable (it only picks a hint's wording)."""
    try:
        data = json.loads((root / FROZEN_FILE).read_text())
        slugs = data["slugs"]
        return frozenset(s for s in slugs if isinstance(s, str))
    except (OSError, ValueError, KeyError, TypeError):
        return frozenset()


def is_awaiting(ws: ShowWorkspace) -> bool:
    """awaiting_fix(read_record(ws)), but an unreadable record counts as
    awaiting: it is never treated as "no record"."""
    try:
        return awaiting_fix(read_record(ws))
    except CampaignUnreadable:
        return True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _unreadable(ws: ShowWorkspace, err) -> CampaignUnreadable:
    detail = " ".join(str(err).split())          # one line
    return CampaignUnreadable(
        f"{ws.dir.name}: cannot read {CAMPAIGN_FILE} ({detail}); check it by hand")


def read_record(ws: ShowWorkspace) -> CampaignRecord | None:
    try:
        data = ws.campaign.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise _unreadable(ws, exc) from exc
    try:
        return CampaignRecord.model_validate_json(data)
    except (ValidationError, ValueError) as exc:
        raise _unreadable(ws, exc) from exc


def _write(ws: ShowWorkspace, rec: CampaignRecord) -> None:
    from llama.catalog import _flush_to_disk

    atomic_write_bytes(ws.campaign, rec.model_dump_json(indent=2).encode())
    _flush_to_disk(ws.campaign)


def _parse(at: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(at)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def last_mark(rec: CampaignRecord | None) -> CampaignMark | None:
    return rec.marks[-1] if rec and rec.marks else None


def awaiting_fix(rec: CampaignRecord | None) -> bool:
    mark = last_mark(rec)
    if mark is None:
        return False
    if rec.processed is None:
        return True
    done, marked = _parse(rec.processed.at), _parse(mark.at)
    if done is None or marked is None:
        return True            # an unparseable time cannot prove it was processed
    return done < marked


def add_mark(ws: ShowWorkspace, *, reason: str, start_stage: str, batch: str, at: str) -> None:
    rec = read_record(ws) or CampaignRecord()
    rec.marks.append(CampaignMark(at=at, reason=reason, start_stage=start_stage, batch=batch))
    _write(ws, rec)


def remove_marks(ws: ShowWorkspace, batch: str) -> int:
    rec = read_record(ws)
    if rec is None:
        return 0
    kept = [m for m in rec.marks if m.batch != batch]
    removed = len(rec.marks) - len(kept)
    if removed:
        rec.marks = kept
        _write(ws, rec)
    return removed


def manifest_sha256(ws: ShowWorkspace) -> str | None:
    try:
        return hashlib.sha256((ws.package_dir / "manifest.json").read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def mark_processed(ws: ShowWorkspace, *, held: bool) -> bool:
    from llama.replay import input_digests   # replay imports the stages

    rec = read_record(ws)
    if rec is None:
        return False
    rec.processed = CampaignProcessed(
        at=_now(), digests=input_digests(ws),
        manifest_sha256=None if held else manifest_sha256(ws))
    _write(ws, rec)
    return True


def after_package(ws: ShowWorkspace) -> None:
    rec = read_record(ws)
    if rec is None or rec.processed is None:
        return
    rec.processed.manifest_sha256 = manifest_sha256(ws)
    _write(ws, rec)


def add_clear(ws: ShowWorkspace, outcome: str) -> None:
    rec = read_record(ws) or CampaignRecord()
    rec.clears.append(CampaignClear(at=_now(), outcome=outcome))
    _write(ws, rec)
