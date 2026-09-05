### Task 6: The `paused` session state

**Files:**
- Modify: `packages/llama/src/llama/sessions.py`
- Modify: `packages/llama/src/llama/cli.py` (`_print_sessions`, around line 455-465)
- Modify: `packages/llama/tests/test_sessions.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `STATE_PAUSED = "paused"`; `mark_paused(ws, outcome, failures, resume_after, scope, reason) -> None`; `SessionInfo.resume_after: str | None` and `SessionInfo.pause_reason: str | None`. Task 7 calls `mark_paused`.

- [ ] **Step 1: Write the failing test**

Append to `packages/llama/tests/test_sessions.py` (it already has `_run_ws(tmp_path) -> RunWorkspace` at line 202, used by the `mark_incomplete` tests — reuse it):

```python
from llama.sessions import (
    STATE_COMPLETE, STATE_PAUSED, attention_sessions, mark_complete,
    mark_paused, session_state,
)


def test_paused_round_trips_the_resume_time(tmp_path):
    ws = _run_ws(tmp_path)
    mark_paused(ws, "3 packaged", [], "2026-09-04T15:10:00+00:00",
                "five_hour", "session limit")
    assert session_state(ws.dir) == STATE_PAUSED
    info = [s for s in attention_sessions(tmp_path) if s.id == ws.name][0]
    assert info.state == STATE_PAUSED
    assert info.resume_after == "2026-09-04T15:10:00+00:00"
    assert info.pause_reason == "session limit"


def test_a_paused_run_is_on_the_attention_list(tmp_path):
    ws = _run_ws(tmp_path)
    mark_paused(ws, None, [], "2026-09-04T15:10:00+00:00", "five_hour", "x")
    assert [s.id for s in attention_sessions(tmp_path)] == [ws.name]


def test_completing_a_paused_run_erases_the_pause_block(tmp_path):
    ws = _run_ws(tmp_path)
    mark_paused(ws, None, [], "2026-09-04T15:10:00+00:00", "five_hour", "x")
    mark_complete(ws, "13 packaged")
    assert session_state(ws.dir) == STATE_COMPLETE
    assert attention_sessions(tmp_path) == []
    marker = json.loads((ws.dir / "session.json").read_text())
    assert "resume_after" not in marker or marker["resume_after"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_sessions.py -q`
Expected: FAIL — `ImportError: cannot import name 'STATE_PAUSED'`

- [ ] **Step 3: Write minimal implementation**

In `packages/llama/src/llama/sessions.py`:

Add the state constant next to the others:

```python
STATE_PAUSED = "paused"                  # waiting out an exhausted usage window
```

Extend `_write` to carry the pause block (it rewrites the marker wholesale, so a
later `mark_complete` erases these fields for free — the same reason `failures`
lives here rather than in a file of its own):

```python
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
```

Add the writer:

```python
def mark_paused(ws: RunWorkspace, outcome: str | None, failures: list[dict] | None,
                resume_after: str, scope: str | None, reason: str | None) -> None:
    """Stop a run that ran out of usage window, recording when to come back.

    Distinct from `mark_incomplete`: nothing is wrong with the shows this run
    has not reached yet, so they are not failures. It stays on the attention
    list (state != complete) until a resume finishes cleanly.
    """
    _write(ws, STATE_PAUSED, outcome, failures, resume_after, scope, reason)
```

Widen the state whitelist:

```python
def _state_of(marker: dict) -> str:
    state = marker.get("state")
    return state if state in (STATE_AWAITING, STATE_COMPLETE, STATE_INCOMPLETE,
                              STATE_PAUSED) \
        else STATE_INCOMPLETE
```

Add the fields to `SessionInfo`:

```python
    resume_after: str | None = None   # ISO instant a paused run may resume
    pause_reason: str | None = None   # the backend's own refusal text
```

and populate them in `iter_sessions`'s `SessionInfo(...)` construction:

```python
                resume_after=marker.get("resume_after"),
                pause_reason=marker.get("pause_reason"),
```

- [ ] **Step 4: Render it in `run list`**

In `packages/llama/src/llama/cli.py`, inside `_print_sessions`, after the
existing `if s.outcome:` line that appends the outcome, add:

```python
        if s.state == STATE_PAUSED and s.resume_after:
            line += f"   resumes {s.resume_after}"
```

Import `STATE_PAUSED` alongside the other session imports at the top of `cli.py`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_sessions.py packages/llama/tests/test_run_namespace.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add packages/llama/src/llama/sessions.py packages/llama/src/llama/cli.py packages/llama/tests/test_sessions.py
git commit -m "feat(llama): add a paused session state carrying its resume time"
```

---

