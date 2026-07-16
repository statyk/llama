import logging
import sys
import threading
import time

import pytest

from llama.status import NarrationHandler, _fmt_elapsed, detail, step


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


from llama.status import NarrationFormatter, configure_logging


def rec(level, msg):
    return logging.LogRecord("llama", level, __file__, 0, msg, None, None)


def test_narration_formatter_non_tty_passthrough_all_levels():
    f = NarrationFormatter(tty=False, color=False)
    assert f.format(rec(logging.INFO, "searching")) == "searching"
    assert f.format(rec(logging.WARNING, "uh oh")) == "uh oh"
    assert f.format(rec(logging.ERROR, "boom")) == "boom"


def test_narration_formatter_tty_dims_and_indents_info():
    f = NarrationFormatter(tty=True, color=True)
    assert f.format(rec(logging.INFO, "searching")) == "\x1b[2m  searching\x1b[0m"


def test_narration_formatter_tty_no_color_indents_only():
    f = NarrationFormatter(tty=True, color=False)
    assert f.format(rec(logging.INFO, "searching")) == "  searching"


def test_narration_formatter_tty_warnings_flush_left_and_loud():
    f = NarrationFormatter(tty=True, color=True)
    assert f.format(rec(logging.WARNING, "uh oh")) == "warning: uh oh"
    assert f.format(rec(logging.ERROR, "boom")) == "boom"


def _narration_handlers(logger):
    return [h for h in logger.handlers if isinstance(h.formatter, NarrationFormatter)]


def test_configure_logging_idempotent_and_keeps_propagation():
    llama_log = logging.getLogger("llama")
    saved = _narration_handlers(llama_log)  # cli import may have configured already
    for h in saved:
        llama_log.removeHandler(h)
    try:
        configure_logging()
        configure_logging()
        assert len(_narration_handlers(llama_log)) == 1
        assert llama_log.propagate is True  # caplog and root handlers still see records
    finally:
        for h in _narration_handlers(llama_log):
            llama_log.removeHandler(h)
        for h in saved:
            llama_log.addHandler(h)


def test_tty_heartbeat_is_dimmed(monkeypatch, capsys):
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
    monkeypatch.delenv("NO_COLOR", raising=False)
    with step("slow call", interval_s=0.05):
        time.sleep(0.12)
    err = capsys.readouterr().err
    assert "still working: slow call" in err
    assert "\x1b[2m" in err


def test_tty_heartbeat_respects_no_color(monkeypatch, capsys):
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
    monkeypatch.setenv("NO_COLOR", "1")
    with step("slow call", interval_s=0.05):
        time.sleep(0.12)
    err = capsys.readouterr().err
    assert "still working: slow call" in err
    assert "\x1b[2m" not in err  # no dimming; \r/erase-line control codes are fine


def test_tty_heartbeat_redraws_in_place(monkeypatch, capsys):
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
    with step("slow call", interval_s=0.05):
        time.sleep(0.2)
    err = capsys.readouterr().err
    assert err.count("still working: slow call") >= 2  # redrew several times...
    assert "\n" not in err                             # ...without stacking lines
    assert err.endswith("\r\x1b[2K")                   # and erased itself when done


def test_detail_on_tty_updates_transient_line(monkeypatch, capsys):
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
    with step("packaging", interval_s=60):
        detail("downloading 3/17: d1t03.mp3")
    err = capsys.readouterr().err
    assert "downloading 3/17: d1t03.mp3" in err
    assert "\n" not in err
    assert err.endswith("\r\x1b[2K")


def test_detail_non_tty_is_a_plain_log_line(monkeypatch, caplog, capsys):
    monkeypatch.setattr(sys.stderr, "isatty", lambda: False)
    with caplog.at_level(logging.INFO, logger="llama"):
        with step("packaging", interval_s=0.01):
            detail("downloading 3/17: d1t03.mp3")
    assert [r.message for r in caplog.records] == ["packaging", "downloading 3/17: d1t03.mp3"]
    assert capsys.readouterr().err == ""


def test_detail_outside_step_is_a_plain_log_line(monkeypatch, caplog):
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
    with caplog.at_level(logging.INFO, logger="llama"):
        detail("downloading 3/17: d1t03.mp3")
    assert [r.message for r in caplog.records] == ["downloading 3/17: d1t03.mp3"]


def test_log_lines_clear_transient_before_printing(monkeypatch, capsys):
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
    llama_log = logging.getLogger("llama")
    handler = NarrationHandler(sys.stderr)
    handler.setFormatter(NarrationFormatter(tty=True, color=False))
    llama_log.addHandler(handler)
    try:
        with step("gathering", interval_s=0.05):
            time.sleep(0.12)  # transient line is on screen
            llama_log.warning("uh oh")
    finally:
        llama_log.removeHandler(handler)
    err = capsys.readouterr().err
    # the warning line starts on a cleared line, not appended to the heartbeat
    assert "\r\x1b[2Kwarning: uh oh\n" in err
