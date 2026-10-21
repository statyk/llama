"""`llama run resume --all` -- the sweep (spec §6): one pass over every run
that is safely resumable, oldest first, each resumed in-process under its own
run lock; everything else skipped with a reason.

`_execute` is stubbed throughout (as test_run_lock / test_run_namespace do):
what is under test is which runs reach it, in what order, with what pacing,
and what the sweep makes of how each one ended. A live run is a real
`fcntl.flock` on another fd, which conflicts with the sweep's own acquire
exactly as another process's would."""
import collections
import fcntl
import json
import os
import shutil
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import typer
from herder.fake import FakeProvider
from typer.testing import CliRunner

import llama.cli as cli
from llama.config import Config
from llama.locks import Locked
from llama.models import Criteria
from llama.pacing import pace_options
from llama.sessions import (KIND_ARCHIVE, KIND_DOWNLOAD, KIND_LLM, KIND_OTHER,
                            KIND_RATE_LIMITED, KIND_TRANSPORT, STATE_COMPLETE,
                            STATE_INCOMPLETE, failure_record, iter_sessions,
                            mark_awaiting, mark_complete, mark_incomplete,
                            mark_paused, sweep_verdict)
from llama.workspace import RunWorkspace, write_artifact

runner = CliRunner()

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
PAST = NOW - timedelta(hours=1)
FUTURE = NOW + timedelta(hours=2)
REFUSED = "is in progress in another process"


def _cfg(tmp_path: Path) -> str:
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    return str(tmp_path / "config.toml")


def _fail(kind: str, show: str = "GD/1973-06-10") -> dict:
    return failure_record(show, RuntimeError(f"{kind} went wrong"), kind=kind, now=PAST)


def _run(tmp_path: Path, name: str, *, state: str | None = STATE_INCOMPLETE,
         failures=None, resume_after: datetime | None = None,
         updated_at: datetime | None = None, criteria: bool = True,
         request: dict | None = None) -> RunWorkspace:
    """A run dir: criteria and/or request, plus a marker written by the real
    `mark_*` (state=None: no marker at all), its `updated_at` then pinned."""
    ws = RunWorkspace(tmp_path, name)
    ws.dir.mkdir(parents=True, exist_ok=True)
    if criteria:
        write_artifact(ws.criteria, Criteria(query="q"))
    if request is not None:
        write_artifact(ws.request, json.dumps(request))
    if state == STATE_INCOMPLETE:
        mark_incomplete(ws, None, failures)
    elif state == "paused":
        mark_paused(ws, None, failures,
                    resume_after.isoformat() if resume_after else None,
                    "five_hour", "limit")
    elif state == "awaiting-approval":
        mark_awaiting(ws)
    elif state == STATE_COMPLETE:
        mark_complete(ws, "done")
    if state is not None and updated_at is not None:
        marker = json.loads(ws.session.read_text())
        marker["updated_at"] = updated_at.isoformat()
        ws.session.write_text(json.dumps(marker))
    return ws


def _marker(ws: RunWorkspace) -> dict:
    return json.loads(ws.session.read_text())


@contextmanager
def _held(run_dir: Path):
    """Another holder of the run lock, on its own fd."""
    fd = os.open(run_dir / ".lock", os.O_CREAT | os.O_RDWR, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        yield fd
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _stub_execute(monkeypatch, actions: dict | None = None) -> list:
    """`_execute` replaced: records (run name, auto, pace) and then does what
    `actions[name]` says -- a callable taking the workspace -- defaulting to
    finishing the run cleanly."""
    actions = actions or {}
    calls = []

    def fake(config, ia, ledger, ws, criteria, count, auto, **kw):
        calls.append((ws.name, auto, kw.get("pace")))
        actions.get(ws.name, lambda w: mark_complete(w, "1 packaged"))(ws)

    monkeypatch.setattr(cli, "_execute", fake)
    return calls


def _sweep(cfg: str, *extra: str):
    return runner.invoke(cli.app, ["--config", cfg, "run", "resume", "--all", *extra])


def _lines(result) -> list[str]:
    return [ln.strip() for ln in result.output.splitlines()]


def _raiser(exc):
    def act(ws):
        raise exc
    return act


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------

def _hhmm(when: datetime) -> str:
    return when.astimezone().strftime("%H:%M")


ELIGIBILITY = {
    "paused-past": (dict(state="paused", resume_after=PAST), None),
    "paused-absent": (dict(state="paused", resume_after=None), None),
    "paused-future": (dict(state="paused", resume_after=FUTURE),
                      f"paused until {_hhmm(FUTURE)}"),
    "paused-past-with-transport": (dict(state="paused", resume_after=PAST,
                                        failures=[_fail(KIND_TRANSPORT)]),
                                   "needs attention"),
    "paused-past-with-download": (dict(state="paused", resume_after=PAST,
                                       failures=[_fail(KIND_DOWNLOAD)]), None),
    "awaiting": (dict(state="awaiting-approval"), "awaiting approval"),
    "incomplete-no-failures": (dict(failures=[]), None),
    "incomplete-download-and-archive": (
        dict(failures=[_fail(KIND_DOWNLOAD), _fail(KIND_ARCHIVE, "GD/1973-06-09")]), None),
    **{f"incomplete-with-{kind}": (
        dict(failures=[_fail(KIND_DOWNLOAD), _fail(kind, "GD/1973-06-09")]),
        "needs attention")
       for kind in (KIND_TRANSPORT, KIND_LLM, KIND_RATE_LIMITED, KIND_OTHER)},
    "legacy-download-record": (
        dict(failures=[{"show": "GD/x", "error": "download of gd.mp3 failed: 500"}]), None),
    "legacy-boom-record": (dict(failures=[{"show": "GD/x", "error": "boom"}]),
                           "needs attention"),
    "no-criteria-no-request": (dict(criteria=False), "needs attention"),
    "no-marker-auto-false": (dict(state=None, criteria=False,
                                  request={"mode": "query", "query": "q", "auto": False}),
                             "needs attention"),
    "no-marker-auto-true": (dict(state=None, criteria=False,
                                 request={"mode": "query", "query": "q", "auto": True}),
                            None),
    "no-marker-no-auto-key": (dict(state=None, criteria=False,
                                   request={"mode": "query", "query": "q"}), None),
}


@pytest.mark.parametrize("case", list(ELIGIBILITY))
def test_eligibility_per_state_and_kind(tmp_path: Path, case):
    kwargs, expected = ELIGIBILITY[case]
    ws = _run(tmp_path, "r1", **kwargs)
    [info] = iter_sessions(tmp_path)
    assert sweep_verdict(info, ws.dir, NOW) == expected


def test_live_runs_are_skipped_as_running(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    live = _run(tmp_path, "live-run", updated_at=PAST)
    _run(tmp_path, "idle-run", updated_at=NOW)
    calls = _stub_execute(monkeypatch)
    with _held(live.dir):
        result = _sweep(cfg)
    assert result.exit_code == 0, result.output
    assert "skip live-run: running" in _lines(result)
    assert [c[0] for c in calls] == ["idle-run"]
    assert _marker(live)["state"] == STATE_INCOMPLETE       # untouched


# ---------------------------------------------------------------------------
# Order, pause, isolation
# ---------------------------------------------------------------------------

def test_oldest_first_and_summary(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    _run(tmp_path, "a-new", updated_at=NOW - timedelta(hours=1))
    _run(tmp_path, "b-old", updated_at=NOW - timedelta(days=3))
    _run(tmp_path, "c-mid", updated_at=NOW - timedelta(days=1))
    calls = _stub_execute(monkeypatch)
    result = _sweep(cfg)
    assert result.exit_code == 0, result.output
    assert [c[0] for c in calls] == ["b-old", "c-mid", "a-new"]
    assert all(auto is True for _, auto, _ in calls)
    lines = _lines(result)
    headers = [ln for ln in lines if ln.startswith("== ")]
    assert headers == ["== b-old", "== c-mid", "== a-new"]
    summary = lines[lines.index("summary:") + 1:]
    assert summary == ["b-old: complete", "c-mid: complete", "a-new: complete"]


def test_stops_on_a_pause(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    _run(tmp_path, "r1", updated_at=NOW - timedelta(days=3))
    _run(tmp_path, "r2", updated_at=NOW - timedelta(days=2))
    r3 = _run(tmp_path, "r3", updated_at=NOW - timedelta(days=1))
    calls = _stub_execute(monkeypatch, {
        "r2": lambda ws: mark_paused(ws, None, [], FUTURE.isoformat(), "five_hour",
                                     "limit")})
    result = _sweep(cfg)
    assert result.exit_code == 1, result.output
    assert [c[0] for c in calls] == ["r1", "r2"]
    lines = _lines(result)
    assert "not reached: r3" in lines
    assert "== r3" not in lines
    summary = lines[lines.index("summary:") + 1:]
    assert summary == ["r1: complete", "r2: paused"]
    assert _marker(r3)["state"] == STATE_INCOMPLETE


def test_one_run_raising_does_not_stop_the_others_and_writes_a_marker(
        tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    r1 = _run(tmp_path, "r1", updated_at=NOW - timedelta(days=2))
    _run(tmp_path, "r2", updated_at=NOW - timedelta(days=1))
    calls = _stub_execute(monkeypatch, {"r1": _raiser(RuntimeError("boom"))})
    result = _sweep(cfg)
    assert result.exit_code == 1, result.output
    assert [c[0] for c in calls] == ["r1", "r2"]
    marker = _marker(r1)
    assert marker["state"] == STATE_INCOMPLETE
    assert len(marker["failures"]) == 1
    [failure] = marker["failures"]
    assert failure["show"] is None
    assert failure["kind"] == KIND_OTHER and failure["error"] == "boom"
    lines = _lines(result)
    summary = lines[lines.index("summary:") + 1:]
    assert summary == ["r1: error: boom", "r2: complete"]

    # The next pass leaves it alone rather than re-spending on it.
    calls.clear()
    again = _sweep(cfg)
    assert again.exit_code == 0, again.output
    assert "skip r1: needs attention" in _lines(again)
    assert "nothing to resume" in _lines(again)
    assert calls == []

    listed = runner.invoke(cli.app, ["--config", cfg, "run", "list"])
    assert listed.exit_code == 0, listed.output
    assert "      - (run): boom" in listed.output.splitlines()


def test_crash_marker_for_typer_exit_reads_exit_code(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    r1 = _run(tmp_path, "r1", updated_at=NOW - timedelta(days=2))
    r2 = _run(tmp_path, "r2", updated_at=NOW - timedelta(days=1))
    _stub_execute(monkeypatch, {"r1": _raiser(typer.Exit(1)),
                                "r2": _raiser(typer.Exit(0))})
    result = _sweep(cfg)
    assert result.exit_code == 1, result.output
    [failure] = _marker(r1)["failures"]
    assert failure["error"] == "exit 1" and failure["kind"] == KIND_OTHER
    # Exit(0) is not a crash: no marker, the run's own state stands.
    assert _marker(r2)["failures"] == []
    lines = _lines(result)
    summary = lines[lines.index("summary:") + 1:]
    assert summary == ["r1: error: exit 1", "r2: incomplete"]


def test_keyboard_interrupt_stops_the_sweep(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    r1 = _run(tmp_path, "r1", updated_at=NOW - timedelta(days=2))
    _run(tmp_path, "r2", updated_at=NOW - timedelta(days=1))
    before = r1.session.read_text()
    calls = _stub_execute(monkeypatch, {"r1": _raiser(KeyboardInterrupt())})
    result = _sweep(cfg)
    assert result.exit_code != 0
    assert [c[0] for c in calls] == ["r1"]
    assert r1.session.read_text() == before                 # no crash marker
    assert "summary:" not in _lines(result)


def test_run_that_turned_live_reports_running(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    r1 = _run(tmp_path, "r1", updated_at=PAST)
    before = r1.session.read_text()
    calls = _stub_execute(monkeypatch)

    def locked(run_dir, *, blocking):
        raise Locked(run_dir / ".lock")

    monkeypatch.setattr(cli, "run_lock", locked)
    result = _sweep(cfg)
    assert result.exit_code == 0, result.output
    assert calls == []
    assert r1.session.read_text() == before
    lines = _lines(result)
    assert lines[lines.index("summary:") + 1:] == ["r1: running"]


def test_a_run_removed_before_its_turn_is_reported_gone(tmp_path: Path, monkeypatch):
    """Review Focus 5: removed between the listing and its turn -- reported,
    never an error, and nothing recreates it."""
    cfg = _cfg(tmp_path)
    _run(tmp_path, "r1", updated_at=NOW - timedelta(days=2))
    r2 = _run(tmp_path, "r2", updated_at=NOW - timedelta(days=1))

    def remove_r2(ws):
        shutil.rmtree(r2.dir)
        mark_complete(ws, "1 packaged")

    calls = _stub_execute(monkeypatch, {"r1": remove_r2})
    result = _sweep(cfg)
    assert result.exit_code == 0, result.output
    assert [c[0] for c in calls] == ["r1"]
    assert not r2.dir.exists()
    lines = _lines(result)
    assert lines[lines.index("summary:") + 1:] == ["r1: complete", "r2: gone"]


# ---------------------------------------------------------------------------
# Flags and exit status
# ---------------------------------------------------------------------------

def test_no_wait_is_the_default_for_the_sweep(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    _run(tmp_path, "r1")
    calls = _stub_execute(monkeypatch, {"r1": lambda ws: None})   # stays eligible
    assert pace_options(Config(root=tmp_path)).wait is True      # config default
    _sweep(cfg)
    _sweep(cfg, "--wait")
    _sweep(cfg, "--max-wait", "30m")
    _sweep(cfg, "--no-pacing")
    paces = [c[2] for c in calls]
    assert [p.wait for p in paces] == [False, True, False, False]
    assert paces[2].max_wait_s == 1800
    assert [p.enabled for p in paces] == [True, True, True, False]


def test_exit_codes(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    nothing = _sweep(cfg)
    assert nothing.exit_code == 0, nothing.output
    assert "nothing to resume" in _lines(nothing)

    _run(tmp_path, "r1", updated_at=NOW - timedelta(days=2))
    _run(tmp_path, "r2", updated_at=NOW - timedelta(days=1))
    _stub_execute(monkeypatch)
    done = _sweep(cfg)
    assert done.exit_code == 0, done.output

    _run(tmp_path, "r3")
    _stub_execute(monkeypatch, {"r3": mark_awaiting})
    awaiting = _sweep(cfg)
    assert awaiting.exit_code == 1, awaiting.output
    lines = _lines(awaiting)
    assert lines[lines.index("summary:") + 1:] == ["r3: awaiting-approval"]

    only_skips = _sweep(cfg)                  # r3 now awaits approval: skipped
    assert only_skips.exit_code == 0, only_skips.output
    assert "skip r3: awaiting approval" in _lines(only_skips)
    assert "nothing to resume" in _lines(only_skips)


def test_session_and_all_are_exclusive(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    _run(tmp_path, "r1")
    calls = _stub_execute(monkeypatch)
    both = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "r1", "--all"])
    assert both.exit_code == 1, both.output
    neither = runner.invoke(cli.app, ["--config", cfg, "run", "resume"])
    assert neither.exit_code == 1, neither.output
    assert calls == []


def test_all_rejects_interactive(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    _run(tmp_path, "r1")
    calls = _stub_execute(monkeypatch)
    result = _sweep(cfg, "--interactive")
    assert result.exit_code == 1, result.output
    assert calls == []


def test_single_resume_still_refuses_a_live_run_and_records_no_crash_marker(
        tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _run(tmp_path, "r1")
    before = ws.session.read_text()
    calls = _stub_execute(monkeypatch, {"r1": _raiser(RuntimeError("boom"))})
    with _held(ws.dir):
        refused = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "r1"])
    assert refused.exit_code == 1, refused.output
    assert f"run r1 {REFUSED}" in refused.output
    assert calls == []

    crashed = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "r1"])
    assert isinstance(crashed.exception, RuntimeError)
    assert [c[0] for c in calls] == ["r1"]
    assert ws.session.read_text() == before                 # no crash marker


def test_no_matching_artists_marks_the_run_complete(tmp_path: Path, monkeypatch):
    config = Config(root=tmp_path)
    ws = RunWorkspace(tmp_path, "r1")
    ws.dir.mkdir(parents=True)
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: collections.defaultdict(
                            lambda: FakeProvider(completes=["x"])))
    monkeypatch.setattr(cli, "run_discover", lambda *a, **k: [])
    cli._execute(config, None, None, ws, Criteria(query="x", soft_preferences="folk"),
                 1, auto=True, human_gate=False)
    marker = _marker(ws)
    assert marker["state"] == STATE_COMPLETE
    assert marker["outcome"] == "no matching artists found"
