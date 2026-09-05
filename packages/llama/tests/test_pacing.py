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
