"""The per-run lock (spec §4): every command that works a run takes an
exclusive flock on `runs/<id>/.lock` once, at entry, and holds it to exit;
the session readers report a live run as `running`.

A second holder is a real `fcntl.flock` on another fd: flock locks belong to
the open file description, so two fds in one process conflict exactly as two
processes do."""
import collections
import fcntl
import json
import os
import shutil
import threading
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

import llama.cli as cli
import llama.locks as locks
from llama.locks import Locked, RunMissing, run_is_live, run_lock
from llama.models import (
    Candidate, Criteria, QualityAssessment, RecordingSummary, ShortlistEntry,
)
from llama.sessions import STATE_COMPLETE, mark_awaiting, mark_complete
from llama.workspace import RunWorkspace, write_artifact

runner = CliRunner()

REFUSED = "is in progress in another process"
CRITERIA_JSON = json.dumps({"query": "x", "collection": "GratefulDead", "count": 1})
# A hang detector, not a correctness timer: every wait below is released by
# an event the test itself controls, so this only bounds a deadlock.
HANG_S = 30


def _cfg(tmp_path: Path) -> str:
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    return str(tmp_path / "config.toml")


def _entries():
    pid = "GratefulDead/1973-06-10"
    return [ShortlistEntry(
        rank=1,
        candidate=Candidate(performance_id=pid, collection="GratefulDead",
                            date="1973-06-10", venue="V",
                            recordings=[RecordingSummary(identifier="id1")]),
        assessment=QualityAssessment(performance_id=pid, quality_score=9.0,
                                     rationale="great show"),
    )]


def _session(tmp_path: Path, name: str = "r1") -> RunWorkspace:
    ws = RunWorkspace(tmp_path, name)
    write_artifact(ws.criteria, Criteria(query="q"))
    write_artifact(ws.shortlist, _entries())
    mark_awaiting(ws)
    return ws


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


def _snapshot(run_dir: Path) -> dict:
    return {str(p.relative_to(run_dir)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in sorted(run_dir.rglob("*")) if p.is_file()}


def _record_execute(monkeypatch) -> list:
    calls = []
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: calls.append((a, k)))
    return calls


# ---------------------------------------------------------------------------
# locks.run_lock / locks.run_is_live
# ---------------------------------------------------------------------------

def test_run_lock_never_creates_a_missing_run_dir(tmp_path: Path):
    run_dir = tmp_path / "runs" / "gone"
    for blocking in (False, True):
        with pytest.raises(RunMissing):
            with run_lock(run_dir, blocking=blocking):
                pass
    assert not run_dir.exists()
    assert not (tmp_path / "runs").exists()


def test_run_is_live_does_not_create_the_lock_file(tmp_path: Path):
    missing = tmp_path / "runs" / "gone"
    assert run_is_live(missing) is False
    assert not missing.exists()

    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)
    assert run_is_live(run_dir) is False
    assert not (run_dir / ".lock").exists()

    with _held(run_dir):
        assert run_is_live(run_dir) is True
    assert run_is_live(run_dir) is False          # the probe released at once


def test_run_lock_non_blocking_on_a_held_run_is_locked(tmp_path: Path):
    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)
    with _held(run_dir):
        with pytest.raises(Locked):
            with run_lock(run_dir, blocking=False):
                pass
    with run_lock(run_dir, blocking=False):
        assert run_is_live(run_dir) is True
    assert run_is_live(run_dir) is False


@pytest.mark.parametrize("replace", ["lock-file", "dir-with-lock", "dir-only"])
def test_lock_on_a_replaced_lock_file_is_run_missing(tmp_path: Path, monkeypatch, replace):
    """Review Focus 4: a `run rm` + re-create landing while an acquirer waits
    must not leave it holding a lock on the deleted file."""
    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)
    lock_file = run_dir / ".lock"

    def do_replace():
        if replace == "lock-file":
            lock_file.unlink()
            lock_file.touch()
        else:
            shutil.rmtree(run_dir)
            run_dir.mkdir()
            if replace == "dir-with-lock":
                lock_file.touch()

    replaced = threading.Event()

    class _Fcntl:
        """`locks.fcntl`, except the acquirer's first LOCK_EX first replaces
        the lock file -- after its fd was opened, before the lock is granted."""
        def __getattr__(self, name):
            return getattr(fcntl, name)

        def flock(self, fd, op):
            if (threading.current_thread().name == "acquirer"
                    and op & fcntl.LOCK_EX and not replaced.is_set()):
                do_replace()
                replaced.set()
            return fcntl.flock(fd, op)

    monkeypatch.setattr(locks, "fcntl", _Fcntl())
    outcome = []

    def acquire():
        try:
            with run_lock(run_dir, blocking=True):
                outcome.append("acquired")
        except RunMissing:
            outcome.append("missing")
        except BaseException as exc:   # surfaced by the assertion below
            outcome.append(repr(exc))

    holder = os.open(lock_file, os.O_CREAT | os.O_RDWR, 0o644)
    fcntl.flock(holder, fcntl.LOCK_EX)
    try:
        t = threading.Thread(target=acquire, name="acquirer", daemon=True)
        t.start()
        assert replaced.wait(HANG_S)
        fcntl.flock(holder, fcntl.LOCK_UN)      # the acquirer may now be granted
        t.join(HANG_S)
        assert not t.is_alive()
        assert outcome == ["missing"]
        # ...and it holds nothing: neither the old inode nor the new file.
        fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(holder, fcntl.LOCK_UN)
        assert run_is_live(run_dir) is False
    finally:
        os.close(holder)


# ---------------------------------------------------------------------------
# Commands that work an existing run refuse a live one
# ---------------------------------------------------------------------------

def test_resume_refuses_a_live_run(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _session(tmp_path)
    calls = _record_execute(monkeypatch)
    with _held(ws.dir):
        before = _snapshot(ws.dir)
        result = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "r1"])
        after = _snapshot(ws.dir)
    assert result.exit_code == 1, result.output
    assert f"run r1 {REFUSED}" in result.output
    assert calls == []
    assert after == before


def test_approve_refuses_a_live_run_before_prompting(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _session(tmp_path)
    calls = _record_execute(monkeypatch)
    with _held(ws.dir):
        before = _snapshot(ws.dir)
        result = runner.invoke(cli.app, ["--config", cfg, "run", "approve", "r1"],
                               input="1\ny\n")
        after = _snapshot(ws.dir)
    assert result.exit_code == 1, result.output
    assert f"run r1 {REFUSED}" in result.output
    assert "Approve which ranks" not in result.output
    assert "1973-06-10" not in result.output          # the shortlist never printed
    assert calls == []
    assert after == before


def test_redo_run_level_refuses_a_live_run(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _session(tmp_path)
    write_artifact(ws.candidates, [])
    calls = _record_execute(monkeypatch)
    for stage in ("search", "winnow"):
        with _held(ws.dir):
            before = _snapshot(ws.dir)
            result = runner.invoke(cli.app, ["--config", cfg, "redo", "--run", "r1",
                                             "--from", stage], input="y\n")
            after = _snapshot(ws.dir)
        assert result.exit_code == 1, result.output
        assert f"run r1 {REFUSED}" in result.output
        assert after == before                     # shortlist/candidates kept
    assert calls == []


def test_rm_refuses_a_live_run(tmp_path: Path):
    cfg = _cfg(tmp_path)
    ws = _session(tmp_path)
    with _held(ws.dir):
        before = _snapshot(ws.dir)
        for args in (["run", "rm", "r1", "--yes"], ["run", "rm", "r1"]):
            result = runner.invoke(cli.app, ["--config", cfg, *args], input="y\n")
            assert result.exit_code == 1, result.output
            assert f"run r1 {REFUSED}" in result.output
            assert "Proceed?" not in result.output
        after = _snapshot(ws.dir)
    assert after == before


def test_rm_holds_the_lock_through_rmtree(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _session(tmp_path)
    seen = []
    real_rmtree = shutil.rmtree

    def rmtree(path, *a, **k):
        seen.append(run_is_live(Path(path)))
        return real_rmtree(path, *a, **k)

    monkeypatch.setattr(cli.shutil, "rmtree", rmtree)
    result = runner.invoke(cli.app, ["--config", cfg, "run", "rm", "r1", "--yes"])
    assert result.exit_code == 0, result.output
    assert seen == [True]
    assert not ws.dir.exists()


# ---------------------------------------------------------------------------
# get: the lock on its own run dir
# ---------------------------------------------------------------------------

def _get_harness(monkeypatch):
    """Record every `run_lock` cli takes (blocking, and whether request.json
    already existed), and from `_execute` whether the run is held."""
    real = locks.run_lock
    taken, probes = [], []

    def recording(run_dir, *, blocking):
        taken.append((blocking, (run_dir / "request.json").exists()))
        return real(run_dir, blocking=blocking)

    def fake_execute(config, ia, ledger, ws, *a, **k):
        try:
            with real(ws.dir, blocking=False):
                probes.append("free")
        except Locked:
            probes.append("held")

    monkeypatch.setattr(cli, "run_lock", recording)
    monkeypatch.setattr(cli, "_execute", fake_execute)
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: collections.defaultdict(
                            lambda: _fake_provider()))
    return taken, probes


def _fake_provider():
    from herder import FakeProvider
    return FakeProvider(completes=[CRITERIA_JSON] * 3)


def test_get_takes_a_blocking_lock_on_its_fresh_dir(tmp_path: Path, monkeypatch):
    from llama.profiles import Profile, save_profile

    cfg = _cfg(tmp_path)
    taken, probes = _get_harness(monkeypatch)
    result = runner.invoke(cli.app, ["--config", cfg, "get", "GD classics"])
    assert result.exit_code == 0, result.output
    assert taken == [(True, False)]               # blocking, before request.json
    assert probes == ["held"]
    assert RunWorkspace(tmp_path, f"{date.today().isoformat()}-gd-classics").request.exists()

    save_profile(tmp_path, Profile(name="classic", criteria=Criteria(query="GD classics")))
    taken.clear(), probes.clear()
    result = runner.invoke(cli.app, ["--config", cfg, "get", "--profile", "classic"])
    assert result.exit_code == 0, result.output
    assert taken == [(True, False)]
    assert probes == ["held"]
    assert RunWorkspace(tmp_path, f"{date.today().isoformat()}-classic").request.exists()


def test_get_name_creates_and_locks_its_dir(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    taken, probes = _get_harness(monkeypatch)
    ws = RunWorkspace(tmp_path, "mine")
    result = runner.invoke(cli.app, ["--config", cfg, "get", "GD", "--name", "mine"])
    assert result.exit_code == 0, result.output
    assert ws.dir.is_dir() and ws.request.exists()
    assert taken == [(True, False)]               # created here: blocking
    assert probes == ["held"]

    # An existing, non-live dir of that name is reused exactly as before,
    # under a non-blocking lock.
    taken.clear(), probes.clear()
    result = runner.invoke(cli.app, ["--config", cfg, "get", "GD", "--name", "mine"])
    assert result.exit_code == 0, result.output
    assert taken == [(False, True)]
    assert probes == ["held"]


def test_get_name_existing_live_run_is_refused(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    taken, probes = _get_harness(monkeypatch)
    interpreted = []
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: interpreted.append(1) or {})
    ws = RunWorkspace(tmp_path, "busy")
    ws.dir.mkdir(parents=True)
    with _held(ws.dir):
        before = _snapshot(ws.dir)
        result = runner.invoke(cli.app, ["--config", cfg, "get", "GD", "--name", "busy"])
        after = _snapshot(ws.dir)
    assert result.exit_code == 1, result.output
    assert f"run busy {REFUSED}" in result.output
    assert taken == [(False, False)]
    assert probes == [] and interpreted == []
    assert not ws.request.exists()
    assert after == before


# ---------------------------------------------------------------------------
# No self-deadlock: the lock is never re-taken inside `_execute`
# ---------------------------------------------------------------------------

def _stub_stages(monkeypatch) -> list:
    """Real `_execute`, stubbed stages; each stage records whether the run is
    held while it runs."""
    live = []

    def search(ws, *a, **k):
        live.append(("search", run_is_live(ws.dir)))

    def winnow(ws, *a, **k):
        live.append(("winnow", run_is_live(ws.dir)))
        return _entries()

    def process_show(ws, *a, **k):
        live.append(("show", run_is_live(ws.dir)))
        return "pkg"

    monkeypatch.setattr(cli, "make_providers",
                        lambda config: collections.defaultdict(_fake_provider))
    monkeypatch.setattr(cli, "run_search", search)
    monkeypatch.setattr(cli, "run_winnow", winnow)
    monkeypatch.setattr(cli, "process_show", process_show)
    monkeypatch.setattr(cli, "make_client", lambda config: None)
    return live


def _invoke_bounded(args):
    box = []
    t = threading.Thread(target=lambda: box.append(runner.invoke(cli.app, args)),
                         daemon=True)
    t.start()
    t.join(HANG_S)
    assert not t.is_alive(), "the command deadlocked"
    return box[0]


def test_no_self_deadlock_get_to_execute(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    live = _stub_stages(monkeypatch)
    result = _invoke_bounded(["--config", cfg, "get", "GD", "--auto", "--name", "e2e"])
    assert result.exit_code == 0, result.output
    assert "packaged: pkg" in result.output
    assert live == [("search", True), ("winnow", True), ("show", True)]
    ws = RunWorkspace(tmp_path, "e2e")
    assert json.loads(ws.session.read_text())["state"] == STATE_COMPLETE
    assert run_is_live(ws.dir) is False           # released at exit


def test_no_self_deadlock_resume_to_execute(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.criteria, Criteria(query="q", count=1))
    live = _stub_stages(monkeypatch)
    result = _invoke_bounded(["--config", cfg, "run", "resume", "r1"])
    assert result.exit_code == 0, result.output
    assert "packaged: pkg" in result.output
    assert live == [("search", True), ("winnow", True), ("show", True)]
    assert json.loads(ws.session.read_text())["state"] == STATE_COMPLETE
    assert run_is_live(ws.dir) is False


# ---------------------------------------------------------------------------
# Readers report a live run as `running`
# ---------------------------------------------------------------------------

def test_run_list_reports_running(tmp_path: Path):
    cfg = _cfg(tmp_path)
    live = RunWorkspace(tmp_path, "live-run")
    write_artifact(live.criteria, Criteria(query="q"))
    mark_complete(live, "done")       # a stale marker: live wins regardless
    idle = _session(tmp_path, "idle-run")
    with _held(live.dir):
        text = runner.invoke(cli.app, ["--config", cfg, "run", "list"])
        as_json = runner.invoke(cli.app, ["--config", cfg, "run", "list", "--json"])
    assert text.exit_code == 0, text.output
    row = next(ln for ln in text.output.splitlines() if ln.startswith("live-run"))
    assert row.split()[1] == "running"
    assert "in progress" in row
    other = next(ln for ln in text.output.splitlines() if ln.startswith("idle-run"))
    assert "running" not in other and "run approve" in other

    rows = {r["id"]: r for r in json.loads(as_json.output)}
    assert rows["live-run"]["state"] == "running"
    assert rows["live-run"]["next"] is None
    assert rows["idle-run"]["state"] == "awaiting-approval"
    assert rows["idle-run"]["next"] == f"llama run approve {idle.name}"


def test_status_by_run_marks_running(tmp_path: Path):
    cfg = _cfg(tmp_path)
    live = _session(tmp_path, "live-run")
    _session(tmp_path, "idle-run")
    with _held(live.dir):
        text = runner.invoke(cli.app, ["--config", cfg, "status", "--by-run"])
        as_json = runner.invoke(cli.app, ["--config", cfg, "status", "--by-run", "--json"])
    assert text.exit_code == 0, text.output
    lines = text.output.splitlines()
    assert next(ln for ln in lines if ln.startswith("live-run")).endswith("  [running]")
    assert "[running]" not in next(ln for ln in lines if ln.startswith("idle-run"))
    rows = {r["id"]: r for r in json.loads(as_json.output)["runs"]}
    assert rows["live-run"]["running"] is True
    assert rows["idle-run"]["running"] is False
