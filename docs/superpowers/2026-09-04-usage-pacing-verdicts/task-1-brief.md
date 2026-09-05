### Task 1: Raw failure capture in herder

Today a failed `claude -p` survives only as a 500-char truncated string. This writes the whole thing to disk, which is what turns the next unrecognized backend failure into evidence.

**Files:**
- Create: `packages/herder/src/herder/failures.py`
- Create: `packages/herder/tests/test_failures.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `set_capture_dir(path: Path | None) -> None` and `capture_failure(cmd: list[str], proc) -> Path | None`, both imported by Task 3.

- [ ] **Step 1: Write the failing test**

Create `packages/herder/tests/test_failures.py`:

```python
import json

from herder import failures


class FakeProc:
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr


def test_capture_writes_the_whole_envelope(tmp_path):
    failures.set_capture_dir(tmp_path)
    try:
        path = failures.capture_failure(["claude", "-p"], FakeProc(
            stdout=json.dumps({"result": "You've hit your session limit"}),
            stderr="noise", returncode=1))
    finally:
        failures.set_capture_dir(None)
    assert path is not None and path.exists()
    body = path.read_text()
    assert "exit_code: 1" in body
    assert "session limit" in body
    assert "noise" in body
    assert "claude -p" in body


def test_capture_is_a_no_op_when_no_dir_is_set():
    failures.set_capture_dir(None)
    assert failures.capture_failure(["claude"], FakeProc(returncode=1)) is None


def test_capture_never_raises_when_the_dir_is_unwritable(tmp_path):
    # A capture failure must never mask the backend failure being captured.
    blocked = tmp_path / "not-a-dir"
    blocked.write_text("i am a file")
    failures.set_capture_dir(blocked)
    try:
        assert failures.capture_failure(["claude"], FakeProc(returncode=1)) is None
    finally:
        failures.set_capture_dir(None)


def test_each_capture_gets_its_own_file(tmp_path):
    failures.set_capture_dir(tmp_path)
    try:
        a = failures.capture_failure(["claude"], FakeProc(returncode=1, stderr="first"))
        b = failures.capture_failure(["claude"], FakeProc(returncode=1, stderr="second"))
    finally:
        failures.set_capture_dir(None)
    assert a != b
    assert "first" in a.read_text() and "second" in b.read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest packages/herder/tests/test_failures.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'herder.failures'`

- [ ] **Step 3: Write minimal implementation**

Create `packages/herder/src/herder/failures.py`:

```python
"""Raw capture of failed backend invocations.

A failed `claude -p` reaches the caller as at most 500 characters of
`_error_detail`'s pick of the message, which is enough to read but not
enough to CLASSIFY: the envelope's structured fields (api_error_status,
subtype, terminal_reason) are gone by then. Capturing the whole thing is
what lets an unrecognized failure be diagnosed after the fact instead of
being reproduced on purpose.

The destination is module-level rather than a provider constructor
argument because providers are built deep inside `resolve.provider_ladder`,
which has no workspace to thread a path through. The app sets it once at
startup; tests set it to a tmp_path and reset it.
"""
import os
import time
from pathlib import Path

_capture_dir: Path | None = None


def set_capture_dir(path: Path | None) -> None:
    """Where to write captures. None disables capture entirely."""
    global _capture_dir
    _capture_dir = Path(path) if path is not None else None


def capture_failure(cmd: list[str], proc) -> Path | None:
    """Write a failed invocation's full stdout/stderr/exit code. Never raises.

    Returns the path written, or None when capture is off or impossible -
    a capture problem must never mask the backend failure being captured.
    """
    if _capture_dir is None:
        return None
    try:
        _capture_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%S")
        path = _capture_dir / f"{stamp}-{os.getpid()}-{time.monotonic_ns() % 1_000_000}.txt"
        path.write_text(
            f"cmd: {' '.join(cmd)}\n"
            f"exit_code: {getattr(proc, 'returncode', None)}\n"
            f"--- stdout ---\n{getattr(proc, 'stdout', '') or ''}\n"
            f"--- stderr ---\n{getattr(proc, 'stderr', '') or ''}\n"
        )
        return path
    except OSError:
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest packages/herder/tests/test_failures.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add packages/herder/src/herder/failures.py packages/herder/tests/test_failures.py
git commit -m "feat(herder): capture the full envelope of a failed claude invocation"
```

---

