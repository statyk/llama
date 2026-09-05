from datetime import datetime, timedelta, timezone

import pytest

from herder.limits import RateLimited
from llama import pacing
from llama.config import Config, PacingConfig


def test_parse_duration_accepts_the_documented_forms():
    assert pacing.parse_duration("6h") == 6 * 3600
    assert pacing.parse_duration("90m") == 90 * 60
    assert pacing.parse_duration("5h30m") == 5 * 3600 + 30 * 60
    assert pacing.parse_duration("45s") == 45


def test_parse_duration_rejects_nonsense():
    for bad in ("", "soon", "6", "-2h", "6x",
                "6h banana",       # trailing garbage after a valid prefix
                "5h30m!",          # trailing garbage after a full match
                "6s30m"):          # units out of order (h, m, s only)
        with pytest.raises(ValueError):
            pacing.parse_duration(bad)


def test_format_delta_is_human_readable():
    assert pacing.format_delta(4 * 3600 + 12 * 60) == "4h 12m"
    assert pacing.format_delta(90) == "1m"


def test_format_delta_floors_short_deltas_at_one_minute():
    # The docstring's invariant is "never bare seconds" -- pin the floor
    # itself, not just an upper bound on it.
    assert pacing.format_delta(5) == "1m"
    assert pacing.format_delta(0) == "1m"


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


def test_sleep_until_defaults_to_900s_chunks(monkeypatch):
    # Task 7 is the first real caller and will take this default; at 1s a
    # 6-hour wait would spam 21,600 progress lines, and at 60000s it would
    # emit none -- the dead prompt this function exists to prevent.
    start = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)
    clock = {"now": start}
    naps = []
    monkeypatch.setattr(pacing, "_now", lambda: clock["now"])

    def fake_sleep(s):
        naps.append(s)
        clock["now"] += timedelta(seconds=s)
    monkeypatch.setattr(pacing, "_sleep", fake_sleep)

    pacing.sleep_until(start + timedelta(seconds=1000), echo=lambda m: None)
    assert naps[0] == 900


def test_sleep_until_rejects_a_naive_when(monkeypatch):
    monkeypatch.setattr(pacing, "_sleep", lambda s: pytest.fail("should not sleep"))
    naive = datetime(2026, 9, 4, 9, 0)   # no tzinfo
    with pytest.raises(ValueError):
        pacing.sleep_until(naive, echo=lambda m: None)


def test_pacing_config_defaults_are_parseable():
    cfg = PacingConfig()
    assert cfg.enabled is True and cfg.wait is True
    assert pacing.parse_duration(cfg.max_wait) == 6 * 3600
    assert pacing.parse_duration(cfg.unknown_reset_wait) == 3600
    assert Config().pacing.max_wait == "6h"


@pytest.mark.parametrize("field", ["max_wait", "unknown_reset_wait", "reset_skew"])
def test_pacing_config_rejects_an_unparseable_duration(field):
    with pytest.raises(Exception):
        PacingConfig(**{field: "whenever"})


def _config(**pacing_kwargs) -> Config:
    return Config(pacing=PacingConfig(**pacing_kwargs))


def test_pace_options_reads_the_config_defaults():
    opts = pacing.pace_options(_config())
    assert opts.enabled is True
    assert opts.wait is True
    assert opts.max_wait_s == 6 * 3600
    assert opts.unknown_reset_wait_s == 3600
    assert opts.reset_skew_s == 120


def test_pace_options_layers_the_flags_over_the_config():
    cfg = _config(wait=True, max_wait="6h")
    assert pacing.pace_options(cfg, wait=False).wait is False
    assert pacing.pace_options(cfg, max_wait="30h").max_wait_s == 30 * 3600
    # None means "flag not given", so the config value survives -- and a
    # config `wait = false` is equally overridable in the other direction.
    assert pacing.pace_options(cfg, wait=None).wait is True
    assert pacing.pace_options(_config(wait=False), wait=True).wait is True


def test_pace_options_rejects_a_malformed_max_wait():
    with pytest.raises(ValueError):
        pacing.pace_options(_config(), max_wait="soon")


def test_resume_at_uses_the_named_reset_plus_the_skew():
    reset = datetime(2026, 9, 4, 11, 10, tzinfo=timezone.utc)
    err = RateLimited("session limit", scope="five_hour", resets_at=reset)
    assert pacing.resume_at(err, pacing.pace_options(_config())) == \
        reset + timedelta(seconds=120)


def test_resume_at_falls_back_when_the_refusal_named_no_reset(monkeypatch):
    now = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(pacing, "_now", lambda: now)
    err = RateLimited("usage limit reached")
    assert pacing.resume_at(err, pacing.pace_options(_config())) == now + timedelta(hours=1)


def test_resume_at_declines_a_naive_reset_rather_than_guessing_its_zone(monkeypatch):
    """A naive instant cannot reach sleep_until, which refuses it outright --
    so the pause would crash instead of pausing. The default wait is the
    known-safe answer."""
    now = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(pacing, "_now", lambda: now)
    err = RateLimited("session limit", resets_at=datetime(2026, 9, 4, 11, 10))
    when = pacing.resume_at(err, pacing.pace_options(_config()))
    assert when == now + timedelta(hours=1)
    assert when.tzinfo is not None
