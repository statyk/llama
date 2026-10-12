import configparser
import socket
import tempfile
from pathlib import Path

from tests_transmitter.helpers import FakeBucket, make_station
from tests_transmitter.test_service import _publisher
from transmitter import sdnotify, service

UNIT = Path(__file__).resolve().parents[1] / "systemd" / "transmitter@.service"


def test_notify_is_a_no_op_outside_systemd():
    assert sdnotify.notify("READY=1", env={}) is False


def test_notify_sends_one_datagram_to_notify_socket():
    with tempfile.TemporaryDirectory(dir="/tmp") as d:      # AF_UNIX paths are short (104 bytes on macOS)
        path = str(Path(d) / "n")
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as server:
            server.bind(path)
            assert sdnotify.notify("WATCHDOG=1", env={"NOTIFY_SOCKET": path}) is True
            assert server.recv(64) == b"WATCHDOG=1"


def test_notify_failure_is_logged_not_raised():
    assert sdnotify.notify("READY=1", env={"NOTIFY_SOCKET": "/nonexistent/socket"}) is False


def test_the_runner_says_ready_pings_the_watchdog_after_every_step_and_says_stopping(tmp_path):
    st, _ = make_station(tmp_path)
    sent: list[str] = []
    runner = service.Runner(st, _publisher(st, FakeBucket()), sleep=lambda s: None,
                            notify=lambda m: sent.append(m) or True)
    runner.run(max_ticks=1)
    assert sent[0] == "READY=1" and sent[-1] == "STOPPING=1"
    assert sent.count("WATCHDOG=1") == 4                    # plan, render, publish, and its one batch


def test_publish_all_feeds_the_watchdog_after_every_batch(tmp_path, monkeypatch):
    from transmitter import publish

    st, _ = make_station(tmp_path)
    batches = iter([publish.PublishReport(uploaded=[1]), publish.PublishReport(uploaded=[2]), publish.PublishReport()])
    monkeypatch.setattr(publish, "publish_batch", lambda p, t_us: next(batches))
    monkeypatch.setattr(publish, "prune", lambda p, t_us: publish.PruneReport())
    sent: list[str] = []
    service.publish_all(_publisher(st, FakeBucket()), 0, notify=lambda m: sent.append(m) or True)
    assert sent == ["WATCHDOG=1"] * 3


def test_the_unit_runs_transmitter_under_a_watchdog_and_always_restarts():
    unit = configparser.ConfigParser(strict=False, interpolation=None)
    unit.optionxform = str
    unit.read_string(UNIT.read_text())
    s = unit["Service"]
    assert s["Type"] == "notify" and s["NotifyAccess"] == "main"
    assert s["Restart"] == "always" and s["RestartSec"] == "30"
    assert s["WatchdogSec"] == "45min"
    assert s["User"] == "%i"
    assert s["EnvironmentFile"] == "/etc/transmitter/%i.env"
    assert s["ExecStart"].endswith("/bin/transmitter run")
    assert s["StandardOutput"] == "journal"
    assert unit["Install"]["WantedBy"] == "multi-user.target"
    assert "network-online.target" in unit["Unit"]["After"]
