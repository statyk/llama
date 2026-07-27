"""Session lifecycle: a session (run) is a process object, not a derived view
of content, so its lifecycle is recorded on its own directory as
runs/<id>/session.json. Show state stays derived-never-stored; this marker
never lives under shows/ (spec §4)."""
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from llama.models import Criteria
from llama.workspace import RunWorkspace, read_model, write_artifact

STATE_AWAITING = "awaiting-approval"
STATE_COMPLETE = "complete"
STATE_INCOMPLETE = "incomplete"          # derived: no clean stop recorded


def _write(ws: RunWorkspace, state: str, outcome: str | None) -> None:
    write_artifact(ws.session, json.dumps({
        "state": state,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "outcome": outcome,
    }, indent=2))


def mark_awaiting(ws: RunWorkspace) -> None:
    _write(ws, STATE_AWAITING, None)


def mark_complete(ws: RunWorkspace, outcome: str | None = None) -> None:
    _write(ws, STATE_COMPLETE, outcome)


def session_state(run_dir: Path) -> str:
    path = run_dir / "session.json"
    if not path.exists():
        return STATE_INCOMPLETE
    try:
        state = json.loads(path.read_text()).get("state")
    except (OSError, json.JSONDecodeError):
        return STATE_INCOMPLETE
    return state if state in (STATE_AWAITING, STATE_COMPLETE) else STATE_INCOMPLETE


@dataclass
class SessionInfo:
    id: str
    state: str            # STATE_AWAITING | STATE_COMPLETE | STATE_INCOMPLETE
    updated_at: str       # marker updated_at, else dir-mtime ISO
    query: str            # criteria.query, "" when no criteria.json
    profile: str | None   # criteria.profile


def _updated_at(run_dir: Path) -> str:
    path = run_dir / "session.json"
    if path.exists():
        try:
            updated_at = json.loads(path.read_text()).get("updated_at")
        except (OSError, json.JSONDecodeError):
            updated_at = None
        if updated_at:
            return updated_at
    return datetime.fromtimestamp(run_dir.stat().st_mtime, timezone.utc).isoformat()


def iter_sessions(root: Path) -> list[SessionInfo]:
    """Every dir under runs/, newest-first by updated_at."""
    runs_dir = root / "runs"
    infos = []
    if runs_dir.is_dir():
        for run_dir in runs_dir.iterdir():
            if not run_dir.is_dir():
                continue
            ws = RunWorkspace(root, run_dir.name)
            query, profile = "", None
            if ws.criteria.exists():
                criteria = read_model(ws.criteria, Criteria)
                query, profile = criteria.query, criteria.profile
            infos.append(SessionInfo(
                id=run_dir.name,
                state=session_state(run_dir),
                updated_at=_updated_at(run_dir),
                query=query,
                profile=profile,
            ))
    infos.sort(key=lambda s: s.updated_at, reverse=True)
    return infos


def attention_sessions(root: Path) -> list[SessionInfo]:
    """The subset of sessions with state != STATE_COMPLETE (spec §4)."""
    return [s for s in iter_sessions(root) if s.state != STATE_COMPLETE]
