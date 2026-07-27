"""Session lifecycle: a session (run) is a process object, not a derived view
of content, so its lifecycle is recorded on its own directory as
runs/<id>/session.json. Show state stays derived-never-stored; this marker
never lives under shows/ (spec §4)."""
import json
from datetime import datetime, timezone
from pathlib import Path

from llama.workspace import RunWorkspace, write_artifact

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
