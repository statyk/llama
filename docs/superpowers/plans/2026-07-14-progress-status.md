# Progress Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make llama's long silent phases visible: counted progress log lines at every slow loop, plus a TTY-only elapsed-time heartbeat during long LLM calls.

**Architecture:** A new `llama/status.py` provides a `step(label)` context manager (logs once; pulses a heartbeat thread to stderr only when stderr is a TTY). Winnow's scoring/research loops and `process_show`'s stage sequence wrap their slow calls in `step`; winnow's fetch loop and package's download loop get plain counted log lines.

**Tech Stack:** Existing project (Python ≥3.11, stdlib threading, pytest). No new dependencies. No stage-signature changes.

**Spec:** `docs/superpowers/specs/2026-07-14-progress-status-design.md`.

## Global Constraints

- Heartbeat text exactly: `  … still working: {label} ({elapsed})`, newline-terminated, written to stderr, every `interval_s` (default 15.0), ONLY when `sys.stderr.isatty()`.
- Elapsed format: `45s`, `1m30s`, `12m05s` (minutes unpadded, seconds zero-padded past a minute).
- Non-TTY behavior: exactly one INFO log line on the `"llama"` logger, no thread.
- Thread stops promptly on context exit (event-based wait); exceptions propagate unchanged.
- No stage function signature changes; no new dependencies; no `\r` redraws.
- Heartbeat tests assert `>=1` line, never exact counts (timing-flake safety).
- All existing tests keep passing (currently 118 passed, 2 deselected). Conventional commits.

## File Structure

```
src/llama/status.py            # new: step() context manager + _fmt_elapsed
tests/test_status.py           # new: lifecycle + formatting tests
src/llama/stages/winnow.py     # + fetch counter line, step() around scoring/research
src/llama/pipeline.py          # + step() around each per-show stage
src/llama/stages/package.py    # + download counter line
tests/test_stage_winnow.py     # + caplog assertions
tests/test_stage_package.py    # + caplog assertion
```

---

### Task 1: status.py — step() context manager

**Files:**
- Create: `src/llama/status.py`
- Test: `tests/test_status.py`

**Interfaces:**
- Produces: `status.step(label: str, *, interval_s: float = 15.0)` context manager; `status._fmt_elapsed(seconds: float) -> str`. Task 2 imports `from llama.status import step`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_status.py`:

```python
import logging
import sys
import threading
import time

import pytest

from llama.status import _fmt_elapsed, step


def test_fmt_elapsed():
    assert _fmt_elapsed(45) == "45s"
    assert _fmt_elapsed(90) == "1m30s"
    assert _fmt_elapsed(725) == "12m05s"
    assert _fmt_elapsed(0.4) == "0s"


def test_non_tty_logs_once_no_heartbeat(monkeypatch, caplog, capsys):
    monkeypatch.setattr(sys.stderr, "isatty", lambda: False)
    threads_before = threading.active_count()
    with caplog.at_level(logging.INFO, logger="llama"):
        with step("doing a thing", interval_s=0.01):
            time.sleep(0.05)
    assert [r.message for r in caplog.records] == ["doing a thing"]
    assert capsys.readouterr().err == ""
    assert threading.active_count() == threads_before


def test_tty_heartbeat_emits_and_stops(monkeypatch, capsys):
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
    with step("slow llm call", interval_s=0.05):
        time.sleep(0.2)
    err = capsys.readouterr().err
    assert "still working: slow llm call" in err
    time.sleep(0.15)  # thread must be stopped: no further output
    assert capsys.readouterr().err == ""


def test_exception_propagates_and_stops_thread(monkeypatch, capsys):
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
    with pytest.raises(ValueError, match="boom"):
        with step("failing call", interval_s=0.05):
            raise ValueError("boom")
    capsys.readouterr()
    time.sleep(0.15)
    assert capsys.readouterr().err == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_status.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'llama.status'`

- [ ] **Step 3: Implement**

Create `src/llama/status.py`:

```python
import logging
import sys
import threading
import time
from contextlib import contextmanager

log = logging.getLogger("llama")


def _fmt_elapsed(seconds: float) -> str:
    secs = int(seconds)
    if secs < 60:
        return f"{secs}s"
    return f"{secs // 60}m{secs % 60:02d}s"


@contextmanager
def step(label: str, *, interval_s: float = 15.0):
    """Log `label`; while the block runs on a TTY, pulse a heartbeat to stderr.

    Non-TTY (cron, piped logs) gets exactly the one log line.
    """
    log.info("%s", label)
    stop = threading.Event()
    thread: threading.Thread | None = None
    if sys.stderr.isatty():
        start = time.monotonic()

        def pulse() -> None:
            while not stop.wait(interval_s):
                elapsed = _fmt_elapsed(time.monotonic() - start)
                print(f"  … still working: {label} ({elapsed})", file=sys.stderr)

        thread = threading.Thread(target=pulse, daemon=True, name=f"heartbeat:{label}")
        thread.start()
    try:
        yield
    finally:
        stop.set()
        if thread is not None:
            thread.join(timeout=1.0)
```

Note: `pulse` looks up `sys.stderr` at print time, so pytest's capture (and any later redirection) is honored.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_status.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/llama/status.py tests/test_status.py
git commit -m "feat: add step() progress heartbeat helper"
```

---

### Task 2: Instrument winnow, process_show, and package

**Files:**
- Modify: `src/llama/stages/winnow.py` (fetch loop, scoring loop, research loop)
- Modify: `src/llama/pipeline.py` (`process_show` stage calls)
- Modify: `src/llama/stages/package.py` (download loop)
- Test: `tests/test_stage_winnow.py`, `tests/test_stage_package.py` (extend)

**Interfaces:**
- Consumes: `from llama.status import step` (Task 1). No signatures change anywhere.

- [ ] **Step 1: Write the failing test additions**

In `tests/test_stage_winnow.py`, add `import logging` to the imports, then append:

```python
def test_winnow_logs_progress(tmp_path: Path, caplog):
    cands = [candidate(f"GratefulDead/1974-0{i}-01", f"1974-0{i}-01") for i in range(1, 6)]
    ws, led = setup(tmp_path, cands)
    pids = [c.performance_id for c in cands]
    fake = FakeProvider(
        completes=[assessments_json(pids[:2]), assessments_json(pids[2:4]), assessments_json(pids[4:])],
        researches=["r"] * 5,
    )
    crit = Criteria(query="q", collection="GratefulDead")
    with caplog.at_level(logging.INFO, logger="llama"):
        run_winnow(ws, fake, fake, StubIA(), crit, led, batch_size=2)
    messages = [r.getMessage() for r in caplog.records]
    assert "winnow: fetching reviews 5/5" in messages
    assert "winnow: scoring reviews batch 3/3" in messages
    assert any(m.startswith("winnow: researching ") and m.endswith("(5/5)") for m in messages)
```

In `tests/test_stage_package.py`, add `import logging` to the imports, then append:

```python
def test_package_logs_downloads(tmp_path: Path, caplog):
    sws, show = setup(tmp_path)
    with caplog.at_level(logging.INFO, logger="llama"):
        run_package(sws, StubIA(), show, make_notes())
    messages = [r.getMessage() for r in caplog.records]
    assert "downloading 1/2: d1t01.mp3" in messages
    assert "downloading 2/2: d2t01.mp3" in messages
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stage_winnow.py::test_winnow_logs_progress tests/test_stage_package.py::test_package_logs_downloads -q`
Expected: 2 FAIL (log messages absent)

- [ ] **Step 3: Implement — winnow**

In `src/llama/stages/winnow.py`, add to the imports:

```python
from llama.status import step
```

Replace the review-fetch loop (`payload = []` block) with:

```python
    payload = []
    reviewed: dict[str, str] = {}
    for i, c in enumerate(survivors, 1):
        log.info("winnow: fetching reviews %d/%d", i, len(survivors))
        best = _best_recording(c)
        md = ia.metadata(best.identifier)
        reviewed[c.performance_id] = best.identifier
        payload.append({
            "performance_id": c.performance_id,
            "date": c.date,
            "venue": c.venue,
            "avg_rating": best.avg_rating,
            "num_reviews": best.num_reviews,
            "reviews": [
                {"title": r.get("reviewtitle"), "stars": r.get("stars"),
                 "body": str(r.get("reviewbody") or "")[:1500]}
                for r in md.get("reviews", [])[:10]
            ],
        })
```

Replace the scoring loop with:

```python
    assessments = {}
    n_batches = (len(payload) + batch_size - 1) // batch_size
    for bi, i in enumerate(range(0, len(payload), batch_size), 1):
        batch = payload[i : i + batch_size]
        with step(f"winnow: scoring reviews batch {bi}/{n_batches}"):
            result = run_json_task(score_provider, "score_reviews", QualityBatch,
                                   candidates_json=json.dumps(batch, indent=2),
                                   soft_preferences=criteria.soft_preferences or "(none)")
        for a in result.assessments:
            a.reviewed_identifier = reviewed.get(a.performance_id, "")
            assessments[a.performance_id] = a
```

Replace the light-research loop body with:

```python
    entries: list[ShortlistEntry] = []
    for rank, (c, a) in enumerate(top, 1):
        with step(f"winnow: researching {c.performance_id} ({rank}/{len(top)})"):
            rep = run_research_task(
                research_provider, "light_research",
                artist=criteria.artist or criteria.collection or c.collection,
                date=c.date, venue=c.venue or "unknown venue",
            )
        entries.append(ShortlistEntry(candidate=c, assessment=a,
                                      external_reputation=rep, rank=rank))
```

(Keep the surrounding code — ledger exclusion, mechanical filter, truncation warning, sort, `write_artifact` — exactly as it is. The `score_provider`/`research_provider` names and the `soft_preferences` kwarg already exist in the current file; preserve them.)

- [ ] **Step 4: Implement — process_show**

In `src/llama/pipeline.py`, add to the imports:

```python
from llama.status import step
```

In `process_show`, wrap the five stage calls (keep all surrounding logic — dossier assembly, re-reads, needs_review gates, ledger record — unchanged):

```python
    pid = cand.performance_id
    with step(f"[{pid}] selecting recording"):
        identifier = run_select_recording(show_ws, ia, cand, entry.assessment,
                                          audio_format=audio_format, force=force)
    with step(f"[{pid}] gathering"):
        show = run_gather(show_ws, ia, providers["extract_setlist"], cand, identifier,
                          audio_format=audio_format, force=force)
    dossier = entry.assessment.rationale
    if entry.external_reputation:
        dossier += "\n\nExternal reputation: " + entry.external_reputation
    with step(f"[{pid}] researching"):
        research_md = run_research(show_ws, providers["deep_research"], show, dossier, force=force)
    reviews = read_json(show_ws.reviews) if show_ws.reviews.exists() else []
    with step(f"[{pid}] synthesizing"):
        notes = run_synthesize(show_ws, providers["synthesize"], show, research_md, reviews, force=force)
```

and later, on the packaging path:

```python
    with step(f"[{pid}] packaging"):
        pkg = run_package(show_ws, ia, show, notes, force=force)
```

- [ ] **Step 5: Implement — package downloads**

In `src/llama/stages/package.py`, inside the track loop, change the download branch to:

```python
        if not dest.exists() or force:
            log.info("downloading %d/%d: %s", t.index, len(show.tracks), t.filename)
            ia.download_file(show.identifier, t.filename, dest, md5=md5s.get(t.filename))
```

and add at the top of the file (with the other imports):

```python
import logging

log = logging.getLogger("llama")
```

- [ ] **Step 6: Run the new tests, then the full suite**

Run: `pytest tests/test_stage_winnow.py tests/test_stage_package.py tests/test_pipeline.py -q`
Expected: all pass (the pipeline E2E runs through the new `step` wrappers; non-TTY in pytest, so no heartbeat threads)
Run: `pytest -q`
Expected: 124 passed, 2 deselected (118 prior + 4 status + 2 log tests)

- [ ] **Step 7: Commit**

```bash
git add src/llama/stages/winnow.py src/llama/pipeline.py src/llama/stages/package.py tests/test_stage_winnow.py tests/test_stage_package.py
git commit -m "feat: add counted progress lines and heartbeats to slow loops"
```

---

## Plan Self-Review Notes

- **Spec coverage:** `step()` semantics incl. exact heartbeat text, elapsed format, non-TTY single-line, exception safety (Task 1); all five instrumentation points — winnow fetch counter, scoring batches, research counter, per-show stage steps, download counter (Task 2); testing strategy incl. ≥1-line flake safety and caplog extensions (both tasks); out-of-scope items (spinners, signature changes, flags) not present.
- **Placeholder scan:** clean.
- **Type consistency:** `step(label, *, interval_s)` identical in both tasks; winnow snippets preserve the current two-provider signature and `soft_preferences` kwarg from the merged codebase.
