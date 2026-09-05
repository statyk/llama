"""Session lifecycle: a session (run) is a process object, not a derived view
of content, so its lifecycle is recorded on its own directory as
runs/<id>/session.json. Show state stays derived-never-stored; this marker
never lives under shows/ (spec §4)."""
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from llama.models import Criteria
from llama.workspace import RunWorkspace, read_model, write_artifact

STATE_AWAITING = "awaiting-approval"
STATE_COMPLETE = "complete"
STATE_INCOMPLETE = "incomplete"          # written when shows failed; also the
                                         # fallback when no clean stop was recorded
STATE_PAUSED = "paused"                  # waiting out an exhausted usage window


def _write(ws: RunWorkspace, state: str, outcome: str | None,
           failures: list[dict] | None = None,
           resume_after: str | None = None, scope: str | None = None,
           reason: str | None = None) -> None:
    write_artifact(ws.session, json.dumps({
        "state": state,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "outcome": outcome,
        "failures": failures or [],
        "resume_after": resume_after,
        "pause_scope": scope,
        "pause_reason": reason,
    }, indent=2))


def mark_awaiting(ws: RunWorkspace) -> None:
    _write(ws, STATE_AWAITING, None)


def mark_complete(ws: RunWorkspace, outcome: str | None = None) -> None:
    _write(ws, STATE_COMPLETE, outcome)


def mark_incomplete(ws: RunWorkspace, outcome: str | None = None,
                    failures: list[dict] | None = None) -> None:
    """Stop a run that lost shows: it stays on the attention list until a
    resume finishes cleanly.

    `failures` is one `{"show": performance_id, "error": str}` per show the
    run could not process -- the only durable record of WHY, since the
    per-show handler otherwise only prints to stderr. They live in the
    session marker rather than a file of their own so that a later
    `mark_complete` erases them by rewriting the marker wholesale; a
    separate failures file would have to be deleted on every clean path, and
    a missed delete would leave a resumed run showing stale corpses.
    """
    _write(ws, STATE_INCOMPLETE, outcome, failures)


def mark_paused(ws: RunWorkspace, outcome: str | None, failures: list[dict] | None,
                resume_after: str, scope: str | None, reason: str | None) -> None:
    """Stop a run that ran out of usage window, recording when to come back.

    Distinct from `mark_incomplete`: nothing is wrong with the shows this run
    has not reached yet, so they are not failures. It stays on the attention
    list (state != complete) until a resume finishes cleanly.
    """
    _write(ws, STATE_PAUSED, outcome, failures, resume_after, scope, reason)


def _read_marker(run_dir: Path) -> dict:
    """The session marker as a dict, or {} when absent or unreadable."""
    path = run_dir / "session.json"
    if not path.exists():
        return {}
    try:
        marker = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return marker if isinstance(marker, dict) else {}


def _state_of(marker: dict) -> str:
    state = marker.get("state")
    return state if state in (STATE_AWAITING, STATE_COMPLETE, STATE_INCOMPLETE,
                              STATE_PAUSED) \
        else STATE_INCOMPLETE


def session_state(run_dir: Path) -> str:
    return _state_of(_read_marker(run_dir))


@dataclass
class SessionInfo:
    id: str
    state: str            # STATE_AWAITING | STATE_COMPLETE | STATE_INCOMPLETE | STATE_PAUSED
    updated_at: str       # marker updated_at, else dir-mtime ISO
    query: str            # criteria.query, "" when no criteria.json
    profile: str | None   # criteria.profile
    outcome: str | None = None      # marker outcome ("5 packaged, 3 held, 1 failed")
    failures: list[dict] = field(default_factory=list)  # per-show {show, error}
    resume_after: str | None = None   # ISO instant a paused run may resume
    pause_reason: str | None = None   # the backend's own refusal text


def _updated_at(run_dir: Path, marker: dict) -> str:
    return marker.get("updated_at") or \
        datetime.fromtimestamp(run_dir.stat().st_mtime, timezone.utc).isoformat()


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
            marker = _read_marker(run_dir)
            infos.append(SessionInfo(
                id=run_dir.name,
                state=_state_of(marker),
                updated_at=_updated_at(run_dir, marker),
                query=query,
                profile=profile,
                outcome=marker.get("outcome"),
                failures=marker.get("failures") or [],
                resume_after=marker.get("resume_after"),
                pause_reason=marker.get("pause_reason"),
            ))
    infos.sort(key=lambda s: s.updated_at, reverse=True)
    return infos


def attention_sessions(root: Path) -> list[SessionInfo]:
    """The subset of sessions with state != STATE_COMPLETE (spec §4)."""
    return [s for s in iter_sessions(root) if s.state != STATE_COMPLETE]
