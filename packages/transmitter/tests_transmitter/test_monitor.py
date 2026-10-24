import json
import logging
import threading
import time

import pytest

from tests_transmitter.helpers import FakeBucket, make_station
from tests_transmitter.test_deadclock import E, live_playlist
from transmitter import alerts, grid, monitor, sdnotify
from transmitter import relay as relay_mod
from transmitter.deadclock import DeadClockMonitor
from transmitter.monitor import MONITOR_JOIN_S, MonitorLoop, R2Reader

NOW = E + 1000 * grid.D_US
WAIT_S = 5.0                     # bound on every wait for the thread: a regression fails, never hangs


@pytest.fixture
def fired(monkeypatch):
    events = []
    monkeypatch.setattr(alerts, "alert", lambda code, msg: events.append(("alert", code, msg)))
    monkeypatch.setattr(alerts, "resolve", lambda code: events.append(("resolve", code)))
    monkeypatch.setattr(alerts, "end_observation", lambda o, steps: events.append(("end", o, list(steps))))
    return events


class FakeCheck:
    def __init__(self, raises=None, on_call=None):
        self.calls = []
        self.raises, self.on_call = raises, on_call

    def check(self, now_us, guard_view):
        self.calls.append(now_us)
        if self.on_call is not None:
            self.on_call(len(self.calls))
        if self.raises is not None:
            raise self.raises


class FakeRelay:
    def __init__(self, raises=None):
        self.passes = 0
        self.raises = raises

    def run_pass(self):
        self.passes += 1
        if self.raises is not None:
            raise self.raises


def _loop(deadclock, relay=None, **kw):
    return MonitorLoop(deadclock, R2Reader(FakeBucket(), "b"), relay, clock=lambda: NOW, **kw)


def test_a_pass_runs_the_check_and_ends_the_monitor_observation(fired):
    check = FakeCheck()
    _loop(check).run_pass()
    assert check.calls == [NOW]
    assert [e for e in fired if e[0] == "end"] == [("end", alerts.MONITOR, ["dead-clock-check"])]


def test_a_raising_check_fires_dead_clock_check_and_the_loop_goes_on(fired):
    check = FakeCheck(raises=RuntimeError("boom"))
    mono = [10.0]
    loop = _loop(check, monotonic=lambda: mono[0])
    loop.run_pass()
    alerted = [e for e in fired if e[0] == "alert"]
    assert [e[1] for e in alerted] == ["dead-clock-check"] and "RuntimeError: boom" in alerted[0][2]
    assert ("end", alerts.MONITOR, ["dead-clock-check"]) in fired
    assert loop.last_pass == 10.0
    mono[0] = 70.0
    loop.run_pass()
    assert len(check.calls) == 2 and loop.last_pass == 70.0


def test_a_raising_relay_is_a_warning_only(fired, caplog):
    relay = FakeRelay(raises=RuntimeError("ntfy down"))
    with caplog.at_level(logging.WARNING, logger="transmitter.monitor"):
        _loop(FakeCheck(), relay).run_pass()
    assert relay.passes == 1
    assert "alert relay pass failed" in caplog.text
    assert [r.levelno for r in caplog.records if "relay" in r.getMessage()] == [logging.WARNING]
    assert not [e for e in fired if e[0] == "alert"]


def test_run_pass_without_relay_never_calls_the_relay(fired):
    relay = FakeRelay()
    check = FakeCheck()
    loop = _loop(check, relay)
    loop.run_pass(relay=False)
    assert relay.passes == 0 and check.calls == [NOW]
    loop.run_pass()
    assert relay.passes == 1


def test_a_pass_without_a_dead_clock_check_still_relays_and_ends_no_observation(fired):
    relay = FakeRelay()
    _loop(None, relay).run_pass()
    assert relay.passes == 1 and fired == []


class FakeNtfyChannel:
    name = "ntfy"

    def __init__(self):
        self.sent = []

    def send(self, subject, body, priority, tags=None):
        self.sent.append(subject)


def _guard_docs(bucket):
    bucket.objects["state/guard.json"] = {"Body": json.dumps(
        {"tripped": False, "evaluated_at": grid.us_to_iso(NOW - 5 * 60_000_000)}).encode()}
    bucket.objects["state/offair.json"] = {"Body": b'{"offair": false}'}


@pytest.mark.parametrize("seeded", [False, True])
def test_the_monitor_only_reads_r2_never_touches_the_guard_cache_and_never_notifies(
        tmp_path, monkeypatch, fired, seeded):
    st, _ = make_station(tmp_path)
    if seeded:
        st.ws.guard_cache_path.parent.mkdir(parents=True, exist_ok=True)
        st.ws.guard_cache_path.write_bytes(b'{"checked_at": 1.0, "blocked": true}')
    before = st.ws.guard_cache_path.read_bytes() if seeded else None
    notified = []
    monkeypatch.setattr(sdnotify, "notify", lambda *a, **k: notified.append(a))
    bucket = FakeBucket()
    _guard_docs(bucket)
    deadclock = DeadClockMonitor("https://radio.example.org/live.m3u8", E, 120.0, 2700.0, 17,
                                 fetch=lambda url: (200, live_playlist(1000)))
    reader = R2Reader(bucket, "b")
    bucket.objects[relay_mod.RELAY_KEY] = {"Body": json.dumps({"stream": "s", "ring": [
        {"seq": 1, "at": grid.us_to_iso(NOW), "key": "waf-api", "kind": "alert", "priority": "high",
         "title": "T", "message": "M"}]}).encode()}
    ntfy = FakeNtfyChannel()
    real_relay = relay_mod.Relay(reader.get_json, ntfy, "st", tmp_path / "relay-cursor.json",
                                 now=lambda: NOW / 1_000_000)
    loop = MonitorLoop(deadclock, reader, real_relay, clock=lambda: NOW)
    loop.run_pass()
    loop.run_pass()
    assert ntfy.sent == ["st: T"]                                   # the real relay ran and pushed once
    assert bucket.log and {op for op, _ in bucket.log} == {"get"}
    assert {k for _, k in bucket.log} == {"state/guard.json", "state/offair.json", relay_mod.RELAY_KEY}
    if seeded:
        assert st.ws.guard_cache_path.read_bytes() == before
    else:
        assert not st.ws.guard_cache_path.exists()
    assert notified == []
    assert not hasattr(loop, "notify")
    assert ("resolve", "dead-clock") in fired and ("resolve", "guard-stale") in fired   # the view was used


def test_r2_reader_exposes_only_get_json():
    bucket = FakeBucket()
    reader = R2Reader(bucket, "b")
    assert {n for n in dir(reader) if not n.startswith("_")} - {"client", "bucket"} == {"get_json"}
    assert reader.get_json("state/guard.json") is None              # NoSuchKey
    bucket.objects["state/guard.json"] = {"Body": b"{not json"}
    with pytest.raises(json.JSONDecodeError):
        reader.get_json("state/guard.json")
    bucket.fail_gets.add("state/offair.json")
    with pytest.raises(Exception, match="InternalError"):
        reader.get_json("state/offair.json")


def test_the_thread_is_a_daemon_passes_every_interval_and_stops(fired):
    second = threading.Event()
    check = FakeCheck(on_call=lambda n: n >= 2 and second.set())
    loop = _loop(check, interval_s=0.01)
    loop.start()
    try:
        assert loop.started
        assert second.wait(WAIT_S)
        assert loop._thread.daemon and loop._thread.name == "transmitter-monitor"
    finally:
        loop.stop()
    assert not loop._thread.is_alive()


def test_stop_joins_within_the_join_bound(fired):
    loop = _loop(FakeCheck())                       # interval 60 s: the thread sits in its wait
    loop.start()
    started = time.monotonic()
    loop.stop()
    assert not loop._thread.is_alive() and time.monotonic() - started < MONITOR_JOIN_S


def _wait_until(pred):
    deadline = time.monotonic() + WAIT_S
    while not pred():
        assert time.monotonic() < deadline, "timed out waiting for the monitor thread"
        time.sleep(0.005)


def test_stalled_counts_from_the_start_until_the_first_pass(fired):
    mono = [0.0]
    entered, release = threading.Event(), threading.Event()

    def on_call(n):
        if n == 1:
            entered.set()
            release.wait(WAIT_S)

    loop = _loop(FakeCheck(on_call=on_call), monotonic=lambda: mono[0])
    assert loop.stalled() is None                   # not started: never stalled
    loop.start()
    try:
        assert entered.wait(WAIT_S)
        mono[0] = 299.0
        assert loop.stalled() is None
        mono[0] = 301.0
        msg = loop.stalled()
        assert msg is not None and "5 minutes" in msg
        mono[0] = 302.0
        release.set()
        _wait_until(lambda: loop.last_pass == 302.0)
        assert loop.stalled() is None
    finally:
        release.set()
        loop.stop()


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_a_dead_thread_is_stalled(fired):
    loop = _loop(FakeCheck())

    def die(**kw):
        raise SystemExit

    loop.run_pass = die
    loop.start()
    loop._thread.join(WAIT_S)
    assert not loop._thread.is_alive()
    assert "not running" in loop.stalled()
    loop.stop()


def test_the_monitor_module_imports_neither_service_nor_sdnotify():
    import ast
    import pathlib
    tree = ast.parse(pathlib.Path(monitor.__file__).read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names |= {f"{node.module}.{a.name}" for a in node.names} | {node.module or ""}
    assert not {n for n in names if n.endswith(("service", "sdnotify"))}
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "notify"]


def test_a_thread_that_cannot_start_leaves_stop_harmless(fired, monkeypatch):
    # Task 4b review BM2: if Thread.start() fails, Runner.run's finally calls
    # stop(); joining an unstarted thread would raise and mask the original error.
    loop = _loop(FakeCheck())

    def refuse(self):
        raise RuntimeError("can't start new thread")

    monkeypatch.setattr(threading.Thread, "start", refuse)
    with pytest.raises(RuntimeError, match="can't start new thread"):
        loop.start()
    monkeypatch.undo()
    loop.stop()                                     # no RuntimeError from join()
    assert not loop.started and loop._thread is None
    assert loop.stalled() is None                   # never started: not watched
