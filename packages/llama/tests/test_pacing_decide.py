from datetime import datetime, timedelta, timezone

from herder.usage import Meter, UsageReading
from llama import pacing
from llama.config import Config

NOW = datetime(2026, 9, 5, 20, 0, tzinfo=timezone.utc)
RESET_5H = NOW + timedelta(hours=2)
RESET_7D = NOW + timedelta(days=3)


def _opts(**kw):
    return pacing.pace_options(Config(), **kw)


def _reading(five=10, seven=7, five_reset=RESET_5H, seven_reset=RESET_7D):
    return UsageReading(five_hour=Meter(five, five_reset),
                        seven_day=Meter(seven, seven_reset),
                        per_model={}, fetched_at=NOW)


def test_proceeds_when_both_meters_are_low():
    out = pacing.decide(NOW, _reading(), pacing.Progress(4.0), _opts())
    assert isinstance(out, pacing.Proceed)


def test_session_gate_fires_on_the_projection_not_the_bare_percent():
    # 88 is under the 90 ceiling; 88 + 4 is not. Gating on the bare
    # percentage would start a show that cannot finish.
    opts = _opts()
    assert isinstance(pacing.decide(NOW, _reading(five=88),
                                    pacing.Progress(None), opts), pacing.Proceed)
    out = pacing.decide(NOW, _reading(five=88), pacing.Progress(4.0), opts)
    assert isinstance(out, pacing.PauseUntil)
    assert out.scope == "five_hour"
    assert out.when == RESET_5H + timedelta(seconds=opts.reset_skew_s)


def test_weekly_ceiling_outranks_the_session_gate():
    # Both would fire; the weekly one must win, because sleeping to the
    # 5-hour reset would resume into a still-exhausted weekly window.
    out = pacing.decide(NOW, _reading(five=95, seven=95),
                        pacing.Progress(4.0), _opts())
    assert out.scope == "seven_day"
    assert out.when == RESET_7D + timedelta(seconds=_opts().reset_skew_s)


def test_no_reading_proceeds_rather_than_guessing():
    assert isinstance(pacing.decide(NOW, None, pacing.Progress(4.0), _opts()),
                      pacing.Proceed)


def test_disabled_pacing_never_gates():
    opts = _opts(no_pacing=True)
    assert isinstance(pacing.decide(NOW, _reading(five=99, seven=99),
                                    pacing.Progress(9.0), opts), pacing.Proceed)


def test_pause_without_a_known_reset_falls_back_to_the_unknown_wait():
    out = pacing.decide(NOW, _reading(five=99, five_reset=None, seven=1),
                        pacing.Progress(4.0), _opts())
    assert out.when == NOW + timedelta(seconds=_opts().unknown_reset_wait_s)


def test_ceiling_boundary_is_strict_greater_than():
    # Exactly at the ceiling proceeds; a hair over pauses.
    opts = _opts()
    assert isinstance(pacing.decide(NOW, _reading(five=86),
                                    pacing.Progress(4.0), opts), pacing.Proceed)
    assert isinstance(pacing.decide(NOW, _reading(five=87),
                                    pacing.Progress(4.0), opts), pacing.PauseUntil)
