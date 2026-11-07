"""The adjudication record and the digest loop guard (spec "Adjudication record and loop
guard"). `<show>/adjudication.json` holds the verdict, the gate outcome per edit, what was
applied and on what evidence, the result, the model and a digest. The digest is the one
staleness test: over the show's flags, track table, excluded rows, overrides without
overrule timestamps, and identifier; never research or briefing text. A later run judges a
held show again only when its digest moved.

An applied record is written inside the apply's `show_unit` (so it commits and restores
with the show) by `write_record`, which takes no lock. Every other record is written after
the unit has exited by `write_outside_unit`, which takes the show lock itself and writes
only while the show is still the state the verdict was about."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from llama.locks import file_lock
from llama.models import Overrides, Show
from llama.show_unit import ShowView, capture_view
from llama.workspace import ShowWorkspace, atomic_write_bytes

RECORD_FILE_VERSION = 1
ABSENT = "absent"


class AdjudicationRecord(BaseModel):
    """Permissive: a record written by a later version still reads."""
    version: int = RECORD_FILE_VERSION
    at: str = ""
    model: str = ""
    dry_run: bool = False
    outcome: Literal["applied", "proposal", "malformed", "dry-run", "accepted"]
    digest: str = ""
    verdict: dict = Field(default_factory=dict)
    malformed: list[str] = Field(default_factory=list)
    gate: list[dict] = Field(default_factory=list)          # EditGate as a dict
    vetoes: list[str] = Field(default_factory=list)
    applied: list[dict] = Field(default_factory=list)       # {index, op, target, evidence_kinds}
    result: dict = Field(default_factory=dict)              # ApplyResult fields
    partial_tape: bool = False
    held_proposal: dict | None = None                       # {flags: [...], edits: [...]}


def view_digest(view: ShowView) -> str:
    """sha256 over canonical JSON of what a verdict was about; `"absent"` without show.json."""
    if view.show is None:
        return ABSENT
    show = Show.model_validate_json(view.show)
    ov = (Overrides.model_validate_json(view.overrides) if view.overrides is not None
          else Overrides())
    ov_dump = ov.model_dump(mode="json")
    for rule in ov_dump.get("overrules", []):
        rule.pop("at", None)
    data = {
        "review_flags": list(show.review_flags),
        "tracks": [[t.filename, t.title, t.title_source, t.set, t.segue, t.duration_sec]
                   for t in show.tracks],
        "excluded": [[x.get("filename"), x.get("reasons")] for x in show.excluded_files],
        "overrides": ov_dump,
        "identifier": show.identifier,
    }
    blob = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def show_digest(show_ws: ShowWorkspace) -> str:
    return view_digest(capture_view(show_ws))


def _path(show_ws: ShowWorkspace, path: Path | None) -> Path:
    return path if path is not None else show_ws.adjudication


def write_record(show_ws: ShowWorkspace, rec: AdjudicationRecord, *,
                 path: Path | None = None) -> None:
    """Atomic write; no lock of its own (inside a unit the unit holds it)."""
    atomic_write_bytes(_path(show_ws, path), rec.model_dump_json(indent=2).encode())


def read_record(show_ws: ShowWorkspace, *, path: Path | None = None) -> AdjudicationRecord | None:
    """The stored record; None when absent or unreadable."""
    try:
        return AdjudicationRecord.model_validate_json(_path(show_ws, path).read_bytes())
    except (OSError, ValidationError, ValueError):
        return None


def is_current(show_ws: ShowWorkspace, *, path: Path | None = None) -> bool:
    """A readable, non-dry-run record whose digest is the show's digest now."""
    rec = read_record(show_ws, path=path)
    return rec is not None and not rec.dry_run and rec.digest == show_digest(show_ws)


def write_outside_unit(show_ws: ShowWorkspace, rec: AdjudicationRecord, *, expect: ShowView,
                       path: Path | None = None) -> bool:
    """Under the show lock: when the show is still `expect`, stamp the digest and write
    (True); otherwise write nothing (False). Never call it inside a `show_unit`:
    `file_lock` is not re-entrant."""
    with file_lock(show_ws.lock):
        if capture_view(show_ws) != expect:
            return False
        write_record(show_ws, rec.model_copy(update={"digest": view_digest(expect)}), path=path)
        return True
