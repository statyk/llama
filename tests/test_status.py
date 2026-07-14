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
