### Task 3: Raise RateLimited from the claude_cli provider

**Files:**
- Modify: `packages/herder/src/herder/claude_cli.py:114-136`
- Modify: `packages/herder/tests/test_claude_cli.py`

**Interfaces:**
- Consumes: `capture_failure` (Task 1), `classify` and `RateLimited` (Task 2).
- Produces: `ClaudeCLIProvider.complete`/`.research` now raise `RateLimited` (a `HerderError` subclass) instead of a bare `HerderError` when the failure text names an exhausted window.

- [ ] **Step 1: Write the failing test**

Append to `packages/herder/tests/test_claude_cli.py`:

```python
from herder.limits import RateLimited

SESSION_LIMIT_MSG = ("You've hit your session limit · "
                     "resets 11:10am (America/New_York)")


def test_session_limit_on_nonzero_exit_raises_rate_limited(monkeypatch):
    patch_run(monkeypatch, FakeProc(returncode=1, stderr=SESSION_LIMIT_MSG), {})
    with pytest.raises(RateLimited) as exc:
        ClaudeCLIProvider().complete("x")
    assert exc.value.scope == "five_hour"
    assert "session limit" in str(exc.value)


def test_session_limit_in_an_error_envelope_raises_rate_limited(monkeypatch):
    envelope = {"is_error": True, "result": SESSION_LIMIT_MSG}
    patch_run(monkeypatch, FakeProc(returncode=0, stdout=json.dumps(envelope)), {})
    with pytest.raises(RateLimited):
        ClaudeCLIProvider().complete("x")


def test_dropped_connection_stays_a_plain_herder_error(monkeypatch):
    patch_run(monkeypatch, FakeProc(returncode=1, stdout=json.dumps(CLOSED_MID)), {})
    with pytest.raises(HerderError) as exc:
        ClaudeCLIProvider().complete("x")
    assert not isinstance(exc.value, RateLimited)


def test_a_failure_is_captured_when_a_capture_dir_is_set(monkeypatch, tmp_path):
    from herder import failures
    patch_run(monkeypatch, FakeProc(returncode=1, stderr="boom"), {})
    failures.set_capture_dir(tmp_path)
    try:
        with pytest.raises(HerderError):
            ClaudeCLIProvider().complete("x")
    finally:
        failures.set_capture_dir(None)
    written = list(tmp_path.iterdir())
    assert len(written) == 1
    assert "boom" in written[0].read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest packages/herder/tests/test_claude_cli.py -q`
Expected: FAIL — the new tests raise `HerderError`, not `RateLimited`; the capture test finds an empty directory.

- [ ] **Step 3: Write minimal implementation**

In `packages/herder/src/herder/claude_cli.py`, add to the imports at the top:

```python
from herder.failures import capture_failure
from herder.limits import classify
```

Then replace the body of `_run` from the `if proc.returncode != 0:` line through the `is_error` branch with:

```python
        if proc.returncode != 0:
            message = f"claude exited {proc.returncode}: {_error_detail(proc)}"
            capture_failure(cmd, proc)
            limited = classify(message)
            if limited is not None:
                raise limited
            raise HerderError(message)
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            capture_failure(cmd, proc)
            raise HerderError(f"claude output was not JSON: {proc.stdout[:200]}") from e
        if data.get("is_error"):
            message = f"claude reported an error: {_message_or(data, str(data))[:500]}"
            capture_failure(cmd, proc)
            limited = classify(message)
            if limited is not None:
                raise limited
            raise HerderError(message)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest packages/herder/tests/test_claude_cli.py -q`
Expected: all pass, including the pre-existing `test_nonzero_exit_surfaces_the_message_not_the_envelope`.

- [ ] **Step 5: Commit**

```bash
git add packages/herder/src/herder/claude_cli.py packages/herder/tests/test_claude_cli.py
git commit -m "feat(herder): raise RateLimited and capture raw output on backend failure"
```

---

