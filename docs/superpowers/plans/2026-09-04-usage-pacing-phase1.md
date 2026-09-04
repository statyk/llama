# Usage Pacing — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a run exhausts the Claude 5-hour usage window, llama pauses until the window resets and continues, instead of failing every remaining show.

**Architecture:** `herder` learns to recognize a rate-limit failure (`RateLimited`, carrying the reset instant parsed out of the error text) and stops retrying it as transport noise. `llama`'s `_execute` catches it at the show boundary, and either sleeps until the reset and carries on, or checkpoints the session as `paused` and exits 0. Resume needs no new machinery: stage-level `should_run` already makes re-entry skip completed work.

**Tech Stack:** Python 3.11+, pydantic v2, typer, pytest. `zoneinfo` (stdlib) for reset parsing. No new third-party dependencies.

**Spec:** `docs/superpowers/specs/2026-09-04-usage-pacing-design.md` — read it first. This plan implements **phase 1 only** (the reactive half): the spec's proactive half (usage-cache reader, EWMA projection, percent thresholds, the fixed rail, `llama pacing`) is deliberately out of scope here.

## Global Constraints

- **Python 3.11+**, no new third-party dependencies. `zoneinfo` and `datetime` are stdlib.
- **Tests are offline and deterministic.** No wall-clock reads in logic under test, no real `$HOME`, no real sleeping. Time is injected (`now` parameter) and sleep is monkeypatched.
- **Never run a `.venv/bin/*` console script from a copy of the tree.** In a worktree, use `./.venv/bin/python -m pytest`. Verify with `./.venv/bin/python -c "import llama; print(llama.__file__)"` — it must resolve inside the tree you meant to test.
- **`herder` must not import from `llama` or `emcee`.** The dependency runs one way.
- **`emcee` must not import `llama`** — enforced by `packages/emcee/tests/test_no_llama_imports.py`.
- Full suite command: `./.venv/bin/python -m pytest -q` from the repo root. It is green at 1440+ tests before this work starts; it must be green after every task.
- Commit after every task. Commit messages use the repo's `type(scope): subject` style.

---

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

### Task 2: RateLimited classification and reset parsing

Pure functions only — no wiring into the provider yet, so a reviewer can judge the classifier on its own.

**Files:**
- Create: `packages/herder/src/herder/limits.py`
- Create: `packages/herder/tests/test_limits.py`
- Modify: `packages/herder/src/herder/__init__.py`

**Interfaces:**
- Consumes: `HerderError` from `herder.provider`.
- Produces: `RateLimited(HerderError)` with attributes `scope: str | None` and `resets_at: datetime | None`; `classify(text: str, now: datetime | None = None) -> RateLimited | None`; `parse_reset(text: str, now: datetime | None = None) -> datetime | None`. Tasks 3, 4 and 7 all import `RateLimited`.

- [ ] **Step 1: Write the failing test**

Create `packages/herder/tests/test_limits.py`:

```python
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from herder.limits import RateLimited, classify, parse_reset

# The measured signature, captured verbatim from a live run on 2026-09-04.
# Note the U+00B7 middle dot: it is part of the real string and must not be
# normalized away.
SESSION_LIMIT = (
    "claude exited 1: You've hit your session limit · "
    "resets 11:10am (America/New_York)"
)
# The dropped-connection failure this must NOT match; it is what stands
# between a network blip and a multi-hour idle.
CLOSED_MID = ("claude exited 1: API Error: Connection closed mid-response. "
              "The response above may be incomplete.")

NY = ZoneInfo("America/New_York")


def test_classifies_the_measured_session_limit():
    err = classify(SESSION_LIMIT, now=datetime(2026, 9, 4, 14, 0, tzinfo=NY))
    assert isinstance(err, RateLimited)
    assert err.scope == "five_hour"
    assert "session limit" in str(err)


def test_dropped_connection_is_not_a_rate_limit():
    assert classify(CLOSED_MID) is None


def test_ordinary_failures_are_not_rate_limits():
    assert classify("claude exited 1: boom") is None
    assert classify("claude output was not JSON: <html>") is None


def test_reset_resolves_to_the_next_future_occurrence():
    now = datetime(2026, 9, 4, 8, 30, tzinfo=NY)
    got = parse_reset(SESSION_LIMIT, now=now)
    assert got == datetime(2026, 9, 4, 11, 10, tzinfo=NY).astimezone(timezone.utc)


def test_reset_past_today_rolls_to_tomorrow_only_within_the_bound():
    # 11:10am already gone: tomorrow's 11:10am is >5.5h out, so it is refused
    # rather than becoming a day-long sleep.
    now = datetime(2026, 9, 4, 12, 0, tzinfo=NY)
    assert parse_reset(SESSION_LIMIT, now=now) is None


def test_reset_within_the_bound_is_accepted():
    now = datetime(2026, 9, 4, 7, 0, tzinfo=NY)
    got = parse_reset(SESSION_LIMIT, now=now)
    assert got is not None
    assert timedelta(0) < got - now.astimezone(timezone.utc) <= timedelta(hours=5.5)


def test_reset_is_read_in_the_zone_the_message_names_not_the_callers():
    # Caller in UTC; message says America/New_York. 11:10am EDT == 15:10 UTC.
    now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
    got = parse_reset(SESSION_LIMIT, now=now)
    assert got == datetime(2026, 9, 4, 15, 10, tzinfo=timezone.utc)


def test_reset_survives_a_dst_boundary():
    # 2026-11-01 02:00 EDT -> EST. 11:10am the morning after the switch is EST.
    text = "You've hit your session limit · resets 11:10am (America/New_York)"
    now = datetime(2026, 11, 1, 7, 30, tzinfo=NY)
    got = parse_reset(text, now=now)
    assert got == datetime(2026, 11, 1, 11, 10, tzinfo=NY).astimezone(timezone.utc)


def test_unknown_zone_or_unparseable_time_yields_no_reset():
    assert parse_reset("hit your session limit, resets soon") is None
    assert parse_reset("resets 11:10am (Mars/Olympus)") is None


def test_classified_error_without_a_parseable_reset_still_classifies():
    err = classify("You've hit your session limit")
    assert isinstance(err, RateLimited)
    assert err.resets_at is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest packages/herder/tests/test_limits.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'herder.limits'`

- [ ] **Step 3: Write minimal implementation**

Create `packages/herder/src/herder/limits.py`:

```python
"""Recognizing a usage-window exhaustion in a backend failure.

The 5-hour signature was captured from a live run on 2026-09-04:

    claude exited 1: You've hit your session limit - resets 11:10am (America/New_York)

Three things follow. Exit code 1, so it arrives through claude_cli's
returncode branch. "session limit" names the window, matching the usage
API's own vocabulary (`kind: "session"` for the 5-hour bucket,
`kind: "weekly_all"` for the 7-day one). And the reset instant is IN the
message, so nothing here needs to read Claude Code's internal state files.

A false positive is worse than a false negative: mistaking a transient
error for a window exhaustion idles a run for hours. So the patterns are
narrow, and the dropped-connection message is pinned as a negative test.
"""
import re
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from herder.provider import HerderError

# A 5-hour window's reset is always within 5 hours. Anything further out
# means the parse or the clock is wrong; parsing must never be able to
# manufacture a day-long sleep.
MAX_RESET_AHEAD_S = 5.5 * 3600

_SIGNATURES: tuple[tuple[re.Pattern, str | None], ...] = (
    # Measured 2026-09-04. Do not loosen without a new capture.
    (re.compile(r"hit your session limit", re.I), "five_hour"),
    # Unverified: the 7-day variant's wording has not been observed. The
    # scope is still useful when it matches, and a miss just falls through
    # to scope=None, which pauses without naming a window.
    (re.compile(r"(weekly|7-day|seven[ -]day) limit", re.I), "seven_day"),
    (re.compile(r"usage limit reached", re.I), None),
)

_RESET_RE = re.compile(
    r"resets\s+(\d{1,2}):(\d{2})\s*([ap]m)\s*\(([A-Za-z_]+/[A-Za-z_+-]+)\)", re.I)


class RateLimited(HerderError):
    """The backend refused because a usage window is exhausted.

    Distinct from every other HerderError in exactly two ways that matter:
    retrying it is pointless (see tasks._with_transport_retry) and it names
    a time after which retrying is not pointless.
    """

    def __init__(self, message: str, scope: str | None = None,
                 resets_at: datetime | None = None):
        super().__init__(message)
        self.scope = scope
        self.resets_at = resets_at


def parse_reset(text: str, now: datetime | None = None) -> datetime | None:
    """The UTC instant named by a `resets 11:10am (America/New_York)` clause.

    Resolved to the next future occurrence of that wall-clock time in the
    zone the message names - which is not necessarily the caller's zone.
    Returns None when absent, unparseable, or further out than
    MAX_RESET_AHEAD_S.
    """
    m = _RESET_RE.search(text)
    if not m:
        return None
    hour12, minute, meridiem, zone_name = m.groups()
    try:
        tz = ZoneInfo(zone_name)
    except Exception:
        return None
    hour = int(hour12) % 12 + (12 if meridiem.lower() == "pm" else 0)
    if not 0 <= int(minute) <= 59:
        return None
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(tz)
    target = datetime.combine(local.date(), time(hour, int(minute)), tzinfo=tz)
    if target <= local:
        target = datetime.combine(local.date() + timedelta(days=1),
                                  time(hour, int(minute)), tzinfo=tz)
    out = target.astimezone(timezone.utc)
    if (out - now.astimezone(timezone.utc)).total_seconds() > MAX_RESET_AHEAD_S:
        return None
    return out


def classify(text: str, now: datetime | None = None) -> RateLimited | None:
    """A RateLimited when the failure text names an exhausted window, else None."""
    for pattern, scope in _SIGNATURES:
        if pattern.search(text):
            return RateLimited(text.strip()[:500], scope=scope,
                               resets_at=parse_reset(text, now))
    return None
```

- [ ] **Step 4: Export it**

In `packages/herder/src/herder/__init__.py`, add after the `from herder.fake import FakeProvider` line:

```python
from herder.limits import RateLimited, classify, parse_reset
```

- [ ] **Step 5: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest packages/herder/tests/test_limits.py -q`
Expected: 10 passed

- [ ] **Step 6: Run the full suite**

Run: `./.venv/bin/python -m pytest -q`
Expected: all green, no change in count except the 10 new tests.

- [ ] **Step 7: Commit**

```bash
git add packages/herder/src/herder/limits.py packages/herder/src/herder/__init__.py packages/herder/tests/test_limits.py
git commit -m "feat(herder): classify usage-window exhaustion as RateLimited"
```

---

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

### Task 4: Stop retrying a rate limit as transport noise

Today a limit hit burns three attempts and 10 s of backoff per show. This is a standalone bug fix.

**Files:**
- Modify: `packages/herder/src/herder/tasks.py:36`
- Modify: `packages/herder/tests/test_llm_tasks.py`

**Interfaces:**
- Consumes: `RateLimited` (Task 2).
- Produces: no new API; `_with_transport_retry` re-raises `RateLimited` on the first raise.

- [ ] **Step 1: Write the failing test**

Append to `packages/herder/tests/test_llm_tasks.py`:

```python
from herder.limits import RateLimited


class CountingLimitProvider:
    """Raises a rate limit every time, counting attempts."""

    def __init__(self):
        self.calls = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        raise RateLimited("You've hit your session limit", scope="five_hour")

    def research(self, brief: str) -> str:
        return self.complete(brief)


def test_rate_limit_is_not_retried_as_transport_noise(monkeypatch):
    # Retrying is not merely useless here, it spends three more calls
    # against a window that has none left.
    slept = []
    monkeypatch.setattr(tasks, "_sleep", lambda s: slept.append(s))
    provider = CountingLimitProvider()
    with pytest.raises(RateLimited):
        tasks.run_json_task(provider, "brief", Answer, template="hi")
    assert provider.calls == 1
    assert slept == []


def test_rate_limit_propagates_from_a_research_task(monkeypatch):
    monkeypatch.setattr(tasks, "_sleep", lambda s: None)
    provider = CountingLimitProvider()
    with pytest.raises(RateLimited):
        tasks.run_research_task(provider, "deep_research", template="hi")
    assert provider.calls == 1
```

That file already imports `pytest` and `tasks` (via `from herder import FakeProvider, HerderError, ResearchNotSupported, TaskFailed, tasks`) and defines the schema `Answer(BaseModel)` with a single `value: int` field. Reuse those; add only the `RateLimited` import.

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest packages/herder/tests/test_llm_tasks.py -q -k rate_limit`
Expected: FAIL — `assert 3 == 1`, because the retry loop swallows it twice before propagating.

- [ ] **Step 3: Write minimal implementation**

In `packages/herder/src/herder/tasks.py`, add to the imports:

```python
from herder.limits import RateLimited
```

Change line 36 from:

```python
        except (TaskFailed, ResearchNotSupported):
```

to:

```python
        except (TaskFailed, ResearchNotSupported, RateLimited):
```

And extend the docstring's final sentence so the reason travels with the code:

```python
    """Call a provider, retrying transient backend failures verbatim.

    Deliberately does NOT escalate the ladder or amend the prompt: a dropped
    connection is not evidence the model needed to be smarter, and paying for
    a tier upgrade over a network blip is the wrong reflex. TaskFailed and
    ResearchNotSupported are definitive verdicts, not transport noise, so
    they propagate on the first raise. RateLimited joins them for a
    different reason: the window is empty, so a retry is not merely useless
    but spends two more calls against a budget that has none left, and the
    caller has a reset time it can wait for instead.
    """
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest packages/herder/tests/test_llm_tasks.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add packages/herder/src/herder/tasks.py packages/herder/tests/test_llm_tasks.py
git commit -m "fix(herder): stop retrying a usage-limit refusal as transport noise"
```

---

### Task 4b: Stop `gather` swallowing a rate limit as an alignment failure

Found in the preflight scan, 2026-09-04, and approved as its own task. `stages/gather.py:992` wraps the `align_structure` LLM fallback in `except (TaskFailed, HerderError)` and merely logs a warning. `RateLimited` subclasses `HerderError`, so a limit hit there is **swallowed**: gather completes, appends a `low-confidence structure alignment` review flag the recording did not earn, and writes it to disk. Stage-level `should_run` then means the resume never recomputes it — so a transient window exhaustion leaves a permanent, wrong review flag on a show. That contradicts the spec's own guarantee that a limit hit means *nothing about the show is wrong*.

**Files:**
- Modify: `packages/llama/src/llama/stages/gather.py` (the `except (TaskFailed, HerderError)` at line 992)
- Modify: `packages/llama/tests/test_gather.py`

**Interfaces:**
- Consumes: `RateLimited` (Task 2).
- Produces: no new API; `run_gather` now propagates `RateLimited` instead of degrading to a review flag.

- [ ] **Step 1: Write the failing test**

Append to `packages/llama/tests/test_gather.py`. Follow whatever fixture that file already uses to drive `run_gather` down the `align_structure` fallback branch — the branch is reached when there is no usable jerrybase evidence and `result.coverage < structure_cfg.align_coverage_threshold`, with a non-None `align_provider`. Reuse the file's existing helpers rather than building a new fixture; if the file has no test that reaches this branch, the smallest honest test is a direct one on the fallback's provider seam.

The test must assert:

```python
    with pytest.raises(RateLimited):
        run_gather(...)          # the same call the neighbouring tests make
```

and, critically, that no `low-confidence structure alignment` flag was written — the defect is not merely that the exception is eaten, it is that a wrong flag is persisted in its place.

Add `from herder.limits import RateLimited` to the imports.

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_gather.py -q -k rate_limit`
Expected: FAIL — the exception is caught by `except (TaskFailed, HerderError)`, logged, and `low-confidence structure alignment` is appended instead.

- [ ] **Step 3: Write minimal implementation**

In `packages/llama/src/llama/stages/gather.py`, add `from herder.limits import RateLimited` to the imports, and add an explicit re-raise **above** the existing broad clause — do **not** narrow the broad clause, because the point is that the intent is legible at the call site:

```python
                except RateLimited:
                    # A usage window ran out. Degrading to a review flag here
                    # would write a `low-confidence structure alignment` the
                    # recording did not earn, and `should_run` means the
                    # resume never recomputes it - so the wrong flag would be
                    # permanent. Let it reach _execute, which pauses instead.
                    raise
                except (TaskFailed, HerderError) as err:
                    log.warning("align_structure failed: %s", err)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_gather.py -q`
Expected: all pass.

- [ ] **Step 5: Run the full suite**

Run: `./.venv/bin/python -m pytest -q`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add packages/llama/src/llama/stages/gather.py packages/llama/tests/test_gather.py
git commit -m "fix(gather): let a usage-limit refusal propagate instead of flagging the show"
```

---

### Task 5: Duration parsing and the `[pacing]` config table

**Files:**
- Create: `packages/llama/src/llama/pacing.py`
- Create: `packages/llama/tests/test_pacing.py`
- Modify: `packages/llama/src/llama/config.py` (add `PacingConfig`, the `Config.pacing` field, and the `DEFAULT_CONFIG_TOML` block)
- Modify: `packages/llama/tests/test_config.py` (only if the template test needs the new block listed; run it and see)

**Interfaces:**
- Consumes: nothing.
- Produces: `parse_duration(text: str) -> float` (seconds, raises `ValueError`); `format_delta(seconds: float) -> str`; `sleep_until(when: datetime, echo) -> None`; module-level `_sleep` and `_now` indirections for tests. `PacingConfig` with fields `enabled: bool`, `wait: bool`, `max_wait: str`, `unknown_reset_wait: str`, `reset_skew: str`, and `Config.pacing`.

- [ ] **Step 1: Write the failing test**

Create `packages/llama/tests/test_pacing.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest

from llama import pacing
from llama.config import Config, PacingConfig


def test_parse_duration_accepts_the_documented_forms():
    assert pacing.parse_duration("6h") == 6 * 3600
    assert pacing.parse_duration("90m") == 90 * 60
    assert pacing.parse_duration("5h30m") == 5 * 3600 + 30 * 60
    assert pacing.parse_duration("45s") == 45


def test_parse_duration_rejects_nonsense():
    for bad in ("", "soon", "6", "-2h", "6x"):
        with pytest.raises(ValueError):
            pacing.parse_duration(bad)


def test_format_delta_is_human_readable():
    assert pacing.format_delta(4 * 3600 + 12 * 60) == "4h 12m"
    assert pacing.format_delta(90) == "1m"


def test_sleep_until_naps_in_chunks_and_reports(monkeypatch):
    start = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)
    clock = {"now": start}
    monkeypatch.setattr(pacing, "_now", lambda: clock["now"])
    monkeypatch.setattr(pacing, "_sleep",
                        lambda s: clock.update(now=clock["now"] + timedelta(seconds=s)))
    said = []
    pacing.sleep_until(start + timedelta(hours=1), echo=said.append, chunk_s=900)
    assert clock["now"] >= start + timedelta(hours=1)
    assert len(said) == 3          # reports after each of the first three naps


def test_sleep_until_returns_at_once_when_the_time_has_passed(monkeypatch):
    now = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(pacing, "_now", lambda: now)
    monkeypatch.setattr(pacing, "_sleep", lambda s: pytest.fail("should not sleep"))
    pacing.sleep_until(now - timedelta(minutes=1), echo=lambda m: None)


def test_pacing_config_defaults_are_parseable():
    cfg = PacingConfig()
    assert cfg.enabled is True and cfg.wait is True
    assert pacing.parse_duration(cfg.max_wait) == 6 * 3600
    assert pacing.parse_duration(cfg.unknown_reset_wait) == 3600
    assert Config().pacing.max_wait == "6h"


def test_pacing_config_rejects_an_unparseable_duration():
    with pytest.raises(Exception):
        PacingConfig(max_wait="whenever")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_pacing.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'llama.pacing'`

- [ ] **Step 3: Write minimal implementation**

Create `packages/llama/src/llama/pacing.py`:

```python
"""Waiting out a usage window.

Phase 1 is the reactive half only: llama learns the reset time from the
backend's own refusal (herder.limits) and either sleeps through it or
checkpoints. The proactive half - reading Claude Code's usage cache,
projecting per-show cost, pausing BEFORE a window is exhausted - is
phase 2 and deliberately absent here.
"""
import re
import time
from datetime import datetime, timezone

_DURATION_RE = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$")

_sleep = time.sleep                                  # indirection for tests
def _now() -> datetime:                              # noqa: E302 - paired with _sleep
    return datetime.now(timezone.utc)


def parse_duration(text: str) -> float:
    """Seconds from `6h`, `90m`, `5h30m`, `45s`. Raises ValueError otherwise."""
    m = _DURATION_RE.match((text or "").strip())
    if not m or not any(m.groups()):
        raise ValueError(f"not a duration: {text!r} (use forms like 6h, 90m, 5h30m)")
    hours, minutes, seconds = (int(g or 0) for g in m.groups())
    return hours * 3600 + minutes * 60 + seconds


def format_delta(seconds: float) -> str:
    """`4h 12m` / `12m` / `1m` - never bare seconds, which read as noise."""
    total = max(int(seconds), 60)
    hours, minutes = divmod(total // 60, 60)
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"


def sleep_until(when: datetime, echo, chunk_s: float = 900) -> None:
    """Sleep until `when`, reporting what is left after each nap.

    Chunked so a multi-hour wait is not a dead prompt, and so a
    KeyboardInterrupt lands promptly. The caller handles that interrupt.
    """
    while True:
        remaining = (when - _now()).total_seconds()
        if remaining <= 0:
            return
        _sleep(min(remaining, chunk_s))
        left = (when - _now()).total_seconds()
        if left > 0:
            echo(f"  … waiting, {format_delta(left)} left")
```

In `packages/llama/src/llama/config.py`, add near the other nested config models (after `ArtistsConfig`):

```python
class PacingConfig(BaseModel):
    """Waiting out an exhausted usage window (see llama/pacing.py).

    Durations are strings so the config reads in the units a human thinks
    in; they are validated at load time rather than at the point of use, so
    a typo fails `llama get` immediately instead of four shows in.
    """
    enabled: bool = True
    wait: bool = True
    max_wait: str = "6h"
    unknown_reset_wait: str = "1h"
    reset_skew: str = "2m"

    @field_validator("max_wait", "unknown_reset_wait", "reset_skew")
    @classmethod
    def _durations_parse(cls, v: str) -> str:
        from llama.pacing import parse_duration
        parse_duration(v)
        return v
```

Add `field_validator` to the pydantic import at the top of `config.py` if it is not already imported, and add the field to `Config`:

```python
    pacing: PacingConfig = Field(default_factory=PacingConfig)
```

Append to `DEFAULT_CONFIG_TOML`, after the `[winnow]` block:

```toml

[pacing]
# When the backend refuses because a usage window is exhausted, wait it out
# instead of failing every remaining show. Set enabled = false to restore the
# old behaviour (the run fails the show and moves on).
enabled = true

# Sleep through the wait (true) or checkpoint the session and exit 0 (false).
# Either way the run resumes with `llama run resume <name>`; stages skip work
# already done, so resuming costs nothing for shows already packaged.
wait = true

# Never sleep longer than this. A wait beyond it checkpoints instead - which
# is what keeps a 7-day window from parking the process for days. Raise it
# (e.g. --max-wait 30h) to deliberately wait out a weekly reset.
max_wait = "6h"

# How long to wait when the refusal names no reset time.
unknown_reset_wait = "1h"

# Added to the reset instant before resuming, so we do not race the window.
reset_skew = "2m"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_pacing.py packages/llama/tests/test_config.py -q`
Expected: all pass. If `test_default_config_template_matches_defaults` fails, the TOML block above does not match the model defaults — fix the block, not the test.

- [ ] **Step 5: Commit**

```bash
git add packages/llama/src/llama/pacing.py packages/llama/src/llama/config.py packages/llama/tests/test_pacing.py
git commit -m "feat(llama): add [pacing] config and duration/sleep helpers"
```

---

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

### Task 7: Pause and resume the show loop

The integration. `_execute` catches `RateLimited` at the show boundary and either sleeps and carries on, or checkpoints and exits 0.

**Files:**
- Modify: `packages/llama/src/llama/cli.py:155-278` (`_execute`), plus the `get`, `run approve` and `run resume` command signatures
- Modify: `packages/llama/tests/test_sessions.py` — its `test_a_run_that_lost_a_show_ends_incomplete_and_records_why` (line 261) is the end-to-end pattern to copy: `runner.invoke(cli.app, [...])` with `fake_providers`, `FakeIA`, and a `config.toml` written into `tmp_path`.

**Interfaces:**
- Consumes: `RateLimited` (Task 2), `parse_duration`/`format_delta`/`sleep_until` (Task 5), `mark_paused` (Task 6).
- Produces: `_execute(..., pace: PaceOptions | None = None)`; `PaceOptions` dataclass in `llama/pacing.py` with fields `enabled: bool`, `wait: bool`, `max_wait_s: float`, `unknown_reset_wait_s: float`, `reset_skew_s: float`, and the constructor `pace_options(config, wait: bool | None, max_wait: str | None) -> PaceOptions`.

- [ ] **Step 1: Add PaceOptions to pacing.py**

```python
from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True)
class PaceOptions:
    enabled: bool
    wait: bool
    max_wait_s: float
    unknown_reset_wait_s: float
    reset_skew_s: float


def pace_options(config, wait: bool | None = None,
                 max_wait: str | None = None) -> PaceOptions:
    """Config defaults with the CLI flags layered on top."""
    cfg = config.pacing
    return PaceOptions(
        enabled=cfg.enabled,
        wait=cfg.wait if wait is None else wait,
        max_wait_s=parse_duration(max_wait or cfg.max_wait),
        unknown_reset_wait_s=parse_duration(cfg.unknown_reset_wait),
        reset_skew_s=parse_duration(cfg.reset_skew),
    )


def resume_at(err, pace: PaceOptions) -> datetime:
    """When to come back after a refusal: the reset it named, else a default.

    The skew keeps us from racing the window's own clock.
    """
    when = getattr(err, "resets_at", None)
    if when is None:
        return _now() + timedelta(seconds=pace.unknown_reset_wait_s)
    return when + timedelta(seconds=pace.reset_skew_s)
```

- [ ] **Step 2: Write the failing test**

Append to `packages/llama/tests/test_sessions.py`, following the existing
end-to-end pattern (same `config.toml`, `fake_providers`, `FakeIA` and
`runner.invoke` as `test_a_run_that_lost_a_show_ends_incomplete_and_records_why`).
The fixture run processes one show, `GratefulDead/1973-06-10`.

```python
from datetime import datetime, timedelta, timezone

from herder.limits import RateLimited
from llama import pacing
from llama.sessions import STATE_PAUSED


class LimitedProvider:
    """Raises a usage limit for the first `times` calls, then defers to `then`."""

    def __init__(self, resets_at, times=1, then=None):
        self.resets_at, self.times, self.then = resets_at, times, then
        self.calls = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        if self.calls <= self.times:
            raise RateLimited("You've hit your session limit", scope="five_hour",
                              resets_at=self.resets_at)
        return self.then.complete(prompt)

    def research(self, brief: str) -> str:
        return self.complete(brief)


def test_a_usage_limit_pauses_the_run_instead_of_failing_the_show(
        tmp_path: Path, monkeypatch):
    """A limit is not a show failure: nothing is wrong with the show, so it
    is left for the resume rather than recorded in failures[]."""
    now = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(pacing, "_now", lambda: now)
    monkeypatch.setattr(pacing, "_sleep", lambda s: pytest.fail("must not sleep"))

    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    providers = fake_providers(None)
    # 30h out, well past the 6h default cap, so it checkpoints rather than sleeps
    providers["brief"] = LimitedProvider(now + timedelta(hours=30))
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "get", "GD 1973", "--auto", "--name", "pausedrun"])
    assert result.exit_code == 0, result.output

    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_PAUSED
    assert info.failures == []                    # NOT a failure
    assert info.resume_after.startswith("2026-09-05")
    assert info in attention_sessions(tmp_path)
    assert "run resume pausedrun" in result.output


def test_a_usage_limit_within_max_wait_sleeps_and_then_finishes(
        tmp_path: Path, monkeypatch):
    clock = {"now": datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(pacing, "_now", lambda: clock["now"])
    monkeypatch.setattr(pacing, "_sleep",
                        lambda s: clock.update(now=clock["now"] + timedelta(seconds=s)))

    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    providers = fake_providers(None)
    real_brief = providers["brief"]
    providers["brief"] = LimitedProvider(clock["now"] + timedelta(hours=2),
                                         times=1, then=real_brief)
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "get", "GD 1973", "--auto", "--name", "sleptrun"])
    assert result.exit_code == 0, result.output

    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_COMPLETE           # slept, retried, finished
    assert info.failures == []
    assert clock["now"] >= datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)
    # The three assertions above ALL hold if the interrupted show is silently
    # dropped from the queue instead of retried, which is exactly the bug this
    # test exists to catch. These two are what actually pin it: the show came
    # back round, and it packaged.
    assert providers["brief"].calls >= 2          # refused once, then retried
    assert info.outcome == "1 packaged"
    assert "packaged:" in result.output


def test_no_pacing_restores_the_old_failure_behaviour(tmp_path: Path, monkeypatch):
    """--no-pacing is the escape hatch: the limit is a per-show failure again."""
    now = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(pacing, "_now", lambda: now)
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    providers = fake_providers(None)
    providers["brief"] = LimitedProvider(now + timedelta(hours=2), times=99)
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "get", "GD 1973", "--auto", "--name", "nopacing", "--no-pacing"])
    assert result.exit_code == 0, result.output

    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_INCOMPLETE
    assert [f["show"] for f in info.failures] == ["GratefulDead/1973-06-10"]
```

If `test_sessions.py` does not already import `pytest`, `STATE_COMPLETE` or
`attention_sessions`, add them to its existing import lines rather than
duplicating imports.

- [ ] **Step 3: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_sessions.py -q -k usage_limit`
Expected: FAIL — `_execute` has no `pace` parameter; the limit is caught by the
existing `except (TaskFailed, HerderError, IAError)` and recorded as a failure.

- [ ] **Step 4: Write minimal implementation**

In `packages/llama/src/llama/cli.py`, add imports:

```python
from herder.limits import RateLimited
from llama.pacing import PaceOptions, format_delta, pace_options, resume_at, sleep_until
from llama.sessions import STATE_PAUSED, mark_paused
```

Add the parameter to `_execute`'s signature:

```python
def _execute(config: Config, ia, ledger, ws: RunWorkspace, criteria: Criteria,
             count: int, auto: bool, human_gate: bool, force: bool = False,
             force_stage: str | None = None,
             full_rationale: bool = False, plan: bool = False,
             pace: PaceOptions | None = None) -> None:
```

and immediately after `providers = make_providers(config)` add:

```python
    pace = pace or pace_options(config)
    set_capture_dir(config.root / "llm-failures")
```

with `from herder.failures import set_capture_dir` added to the imports at the
top of `cli.py`. This is the one place capture is switched on: every provider
built by `make_providers` shares the module-level destination.

Replace the block from `packaged = held = 0` through the `mark_complete(ws, outcome)`
tail with:

```python
    setlistfm = make_client(config)
    packaged = held = 0
    failures: list[dict] = []          # {show, error} per show this run lost
    limited: RateLimited | None = None  # set when a usage window ran out

    def _process(entry):
        nonlocal packaged, held, limited
        try:
            pkg = process_show(ws, ia, ledger, entry, providers, ws.name, config.audio_format,
                               force=force,
                               setlistfm=setlistfm,
                               structure_cfg=config.structure, selection_cfg=config.selection,
                               jerrybase_enabled=config.jerrybase.enabled,
                               force_stage=force_stage, profile=criteria.profile)
        except RateLimited as exc:
            # Not a failure: nothing is wrong with this show. Its finished
            # stages are on disk and a resume redoes only what is missing.
            if not pace.enabled:
                typer.echo(f"FAILED {entry.candidate.performance_id}: {exc}", err=True)
                failures.append({"show": entry.candidate.performance_id, "error": str(exc)})
                return
            limited = exc
            return
        except (TaskFailed, HerderError, IAError) as exc:
            if isinstance(exc, TaskFailed) and exc.raw_output:
                failure_path = ws.show_ws(entry.candidate.performance_id).dir / "llm-failure.txt"
                failure_path.parent.mkdir(parents=True, exist_ok=True)
                failure_path.write_text(exc.raw_output)
            typer.echo(f"FAILED {entry.candidate.performance_id}: {exc}", err=True)
            failures.append({"show": entry.candidate.performance_id, "error": str(exc)})
            return
        if pkg:
            typer.echo(f"packaged: {pkg}")
            packaged += 1
        else:
            typer.echo(f"needs-review, skipped: {entry.candidate.performance_id}")
            held += 1

    def _outcome() -> str | None:
        parts = []
        if packaged:
            parts.append(f"{packaged} packaged")
        if held:
            parts.append(f"{held} held")
        if failures:
            parts.append(f"{len(failures)} failed")
        return ", ".join(parts) if parts else None

    pending = list(chosen)
    done_before_pause = -1                  # progress watermark; see the guard below
    while pending:
        deferred, unprocessed = [], []
        for idx, entry in enumerate(pending):
            lock_path = ws.show_ws(entry.candidate.performance_id).lock
            try:
                with file_lock(lock_path, blocking=False):
                    _process(entry)
            except Locked:
                deferred.append(entry)         # another run is building it
            # AFTER the call, not before: `pending[idx:]` must INCLUDE the show
            # that hit the limit. Checking at the top of the body instead starts
            # the slice one entry late and silently drops that show from the
            # run, which then reports `complete` having never processed it.
            if limited:
                unprocessed.extend(pending[idx:])
                break
        if limited:
            unprocessed.extend(deferred)
        else:
            for idx, entry in enumerate(deferred):   # come back and wait
                with file_lock(ws.show_ws(entry.candidate.performance_id).lock):
                    _process(entry)
                if limited:
                    unprocessed.extend(deferred[idx:])
                    break
        if not limited:
            break

        when = resume_at(limited, pace)
        wait_s = (when - _pacing._now()).total_seconds()
        reason = str(limited)
        scope = limited.scope
        # No-progress guard: if a whole pause cycle bought us nothing, sleeping
        # again would nap indefinitely against a backend that keeps refusing.
        # Checkpoint instead, and say WHY so it is not read as an ordinary
        # window pause.
        done_now = packaged + held + len(failures)
        stalled = done_now == done_before_pause
        done_before_pause = done_now
        typer.echo(f"paused after {packaged + held} shows: {reason}")
        if stalled:
            typer.echo("  no progress since last pause — checkpointing rather "
                       "than waiting again")
        if not stalled and pace.wait and wait_s <= pace.max_wait_s:
            typer.echo(f"  resumes {when.astimezone().strftime('%H:%M')} "
                       f"({format_delta(wait_s)})")
            try:
                sleep_until(when, echo=lambda m: typer.echo(m))
            except KeyboardInterrupt:
                mark_paused(ws, _outcome(), failures, when.isoformat(), scope, reason)
                typer.echo(f"\ninterrupted; resume with: llama run resume {ws.name}")
                return
            limited = None
            pending = unprocessed
            continue
        if wait_s > pace.max_wait_s:
            typer.echo(f"  resets in {format_delta(wait_s)} — exceeds "
                       f"--max-wait {format_delta(pace.max_wait_s)}")
        mark_paused(ws, _outcome(), failures, when.isoformat(), scope, reason)
        typer.echo(f"  {len(unprocessed)} shows left; resume with: "
                   f"llama run resume {ws.name}"
                   + (f" --max-wait {format_delta(wait_s)}"
                      if wait_s > pace.max_wait_s else ""))
        return

    outcome = _outcome()
    # A run that lost shows stays on the attention list (`run list` is
    # state != complete) until a `run resume` finishes cleanly -- otherwise a
    # usage limit or a dropped connection costs shows silently, and the only
    # record of why scrolls off the terminal.
    if failures:
        mark_incomplete(ws, outcome, failures)
    else:
        mark_complete(ws, outcome)
```

**Clock access must go through the module, never a rebound name.** Import it as:

```python
from llama import pacing as _pacing
```

and read the clock as `_pacing._now()`. A `from llama.pacing import _now` binds
the original function at import time and silently defeats
`monkeypatch.setattr(pacing, "_now", ...)`, which would make every test above
depend on the real wall clock.

- [ ] **Step 5: Wire the CLI flags**

Add to `get`, `run_approve` and `run_resume` the same three options:

```python
    wait: bool = typer.Option(None, "--wait/--no-wait",
                              help="On a usage-limit pause: sleep until the window "
                                   "resets (default), or checkpoint and exit"),
    max_wait: str = typer.Option(None, "--max-wait",
                                 help="Never sleep longer than this (default 6h); a "
                                      "longer wait checkpoints instead. e.g. 30h"),
    no_pacing: bool = typer.Option(False, "--no-pacing",
                                   help="Disable usage pacing: a limit fails the show "
                                        "as it did before"),
```

and in each body build the options before calling `_execute`:

```python
    pace = pace_options(config, wait=wait, max_wait=max_wait)
    if no_pacing:
        pace = replace(pace, enabled=False)
```

(`from dataclasses import replace`). Thread `pace=pace` through `_get_query`,
`_get_profile` and the two `run_*` calls into `_execute`. Validate `--max-wait`
eagerly so a typo fails before the run starts:

```python
    try:
        pace = pace_options(config, wait=wait, max_wait=max_wait)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest packages/llama/tests -q`
Expected: all pass.

- [ ] **Step 7: Run the full suite**

Run: `./.venv/bin/python -m pytest -q`
Expected: green.

- [ ] **Step 8: Commit**

```bash
git add packages/llama/src/llama/cli.py packages/llama/src/llama/pacing.py packages/llama/tests/
git commit -m "feat(llama): pause and resume a run when the usage window runs out"
```

---

### Task 8: Mutation pass and documentation

A green suite is not evidence a constraint is load-bearing. Each mutation below is a one-line change that a loosely written test would happily keep passing.

**Files:**
- Modify: `CLAUDE.md` (the `llama get` command list and the LLM-layer bullet)
- Modify: `docs/workflow.md` (wherever the "usage limit reached" example failure is described)

- [ ] **Step 1: Mutation 1 — the catch ordering**

In `cli.py`'s `_process`, move the `except RateLimited` clause *below* the
`except (TaskFailed, HerderError, IAError)` clause. Python does **not** reject
this — the clause is simply unreachable, which is the whole point of the
mutation. Then run:

Run: `./.venv/bin/python -m pytest packages/llama/tests -q -k rate_limit`
Expected: FAIL — `RateLimited` subclasses `HerderError`, so the broad clause
swallows it and the run records a failure instead of pausing.
Restore the original order and confirm green.

- [ ] **Step 2: Mutation 2 — the no-retry set**

In `tasks.py:36`, remove `RateLimited` from the tuple.

Run: `./.venv/bin/python -m pytest packages/herder/tests/test_llm_tasks.py -q -k rate_limit`
Expected: FAIL — `assert 3 == 1`.
Restore and confirm green.

- [ ] **Step 3: Mutation 3 — the reset sanity bound**

In `limits.py`, raise `MAX_RESET_AHEAD_S` to `48 * 3600`.

Run: `./.venv/bin/python -m pytest packages/herder/tests/test_limits.py -q`
Expected: FAIL — `test_reset_past_today_rolls_to_tomorrow_only_within_the_bound`.
Restore and confirm green.

- [ ] **Step 4: Mutation 4 — the negative classification**

In `limits.py`, add `(re.compile(r"error", re.I), None)` to `_SIGNATURES`.

Run: `./.venv/bin/python -m pytest packages/herder/tests -q`
Expected: FAIL — the dropped-connection tests, which is exactly the guard that
keeps a network blip from idling a run for hours.
Restore and confirm green.

- [ ] **Step 4b: Mutation 5 — the gather re-raise**

In `stages/gather.py`, delete the `except RateLimited: raise` clause added in
Task 4b, leaving only the broad `except (TaskFailed, HerderError)`.

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_gather.py -q -k rate_limit`
Expected: FAIL — the limit is swallowed and a `low-confidence structure
alignment` flag is written in its place, which is the permanent-wrong-flag
defect Task 4b exists to prevent.
Restore and confirm green.

- [ ] **Step 5: Update CLAUDE.md**

In the `## Commands` section, extend the `llama get` entry:

```
`llama get` takes `--wait/--no-wait`, `--max-wait <dur>` and `--no-pacing`
(also on `run approve`/`run resume`): when the claude_cli backend refuses
because a usage window is exhausted, the run pauses at the show boundary
rather than failing every remaining show — sleeping until the reset the
refusal names, or checkpointing the session as `paused` when the wait
exceeds `--max-wait` (default 6h). Resuming costs nothing for shows already
packaged: stage-level `should_run` skips them.
```

In the architecture section's LLM-layer bullet, add:

```
A usage-window refusal is classified as `herder.limits.RateLimited` (measured
signature: `You've hit your session limit · resets 11:10am (America/New_York)`),
carrying the reset instant parsed from the message itself — so pausing needs no
access to Claude Code's internal state. It is excluded from
`_with_transport_retry`, which would otherwise spend three more calls against
an empty window. Every failed `claude -p` is captured whole under
`~/.llama/llm-failures/`; the 7-day refusal's wording is still unobserved and
that capture is how it will be learned.
```

- [ ] **Step 6: Update docs/workflow.md**

Find the passage using `"usage limit reached"` as an illustrative
`failures[].error` string and add a sentence noting that such a failure now
pauses the run instead of being recorded per-show, with the session state
`paused` and a `resume_after` instant.

- [ ] **Step 7: Full suite and commit**

```bash
./.venv/bin/python -m pytest -q
git add CLAUDE.md docs/workflow.md
git commit -m "docs: record usage pacing and the measured rate-limit signature"
```

---

## Out of scope (phase 2)

Listed so no task quietly grows into them. All are specified in
`docs/superpowers/specs/2026-09-04-usage-pacing-design.md`:

- The usage-cache reader (`cachedUsageUtilization`) and its staleness ladder.
- Per-show cost capture (`UsageMeter`) and the learned Δ-utilization EWMA.
- Proactive percent thresholds (`five_hour_threshold`, `seven_day_stop`) and
  the pre-flight projection warning.
- The fixed rail (`shows_per_batch` / `--batch N`).
- The `llama pacing` read-only command.
- Backend gating of percent rules — irrelevant in phase 1, since the reactive
  path is driven by a refusal any backend could in principle raise.
