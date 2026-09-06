from datetime import datetime, timedelta, timezone

from herder.usage import Meter, UsageReading
from llama import pacing
from llama.config import Config, PacingConfig

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


def test_each_window_is_judged_against_its_own_ceiling():
    # Both ceilings default to 90, which makes swapping them at the call
    # site invisible. Pull them apart: the weekly meter sits well under the
    # generous weekly ceiling while the session meter is over the strict
    # session one, so only a correct pairing pauses - and it pauses on the
    # session window, not the weekly one.
    opts = pacing.pace_options(
        Config(pacing={"five_hour_ceiling": 50, "seven_day_ceiling": 95}))
    out = pacing.decide(NOW, _reading(five=55, seven=60),
                        pacing.Progress(4.0), opts)
    assert isinstance(out, pacing.PauseUntil)
    assert out.scope == "five_hour"

    # And the mirror image, so a swap cannot pass by pausing for the wrong
    # reason: now only the weekly projection crosses.
    flipped = pacing.pace_options(
        Config(pacing={"five_hour_ceiling": 95, "seven_day_ceiling": 50}))
    out = pacing.decide(NOW, _reading(five=60, seven=55),
                        pacing.Progress(4.0), flipped)
    assert isinstance(out, pacing.PauseUntil)
    assert out.scope == "seven_day"


def test_a_missing_meter_is_skipped_rather_than_crashing():
    # UsageReading's meters are optional: /usage can print one window and
    # not the other. The absent one must not be consulted at all.
    only_weekly = UsageReading(five_hour=None,
                               seven_day=Meter(7, RESET_7D),
                               per_model={}, fetched_at=NOW)
    assert isinstance(pacing.decide(NOW, only_weekly, pacing.Progress(4.0),
                                    _opts()), pacing.Proceed)

    only_session = UsageReading(five_hour=Meter(99, RESET_5H), seven_day=None,
                                per_model={}, fetched_at=NOW)
    out = pacing.decide(NOW, only_session, pacing.Progress(4.0), _opts())
    assert isinstance(out, pacing.PauseUntil)
    assert out.scope == "five_hour"


def test_the_pause_reason_names_the_window_and_the_estimate():
    # The reason is what the operator reads in the pause line, so a run
    # sleeping on the weekly window must not claim it is the 5-hour one.
    out = pacing.decide(NOW, _reading(five=95, seven=95),
                        pacing.Progress(4.0), _opts())
    assert out.reason == "weekly window at 95%, est 4.0%/show"
    out = pacing.decide(NOW, _reading(five=95), pacing.Progress(None), _opts())
    assert out.reason == "5h window at 95%"


# `shows_that_fit` takes ONE meter, not a whole reading: taking the reading
# is what let it reach into `.five_hour` itself and forecast a window the
# gate was not binding on. `binding_forecast` below composes it over both.


def test_shows_that_fit_uses_the_ceiling_not_a_hundred():
    # 90 - 65 = 25 points of usable headroom at 4.2%/show.
    assert pacing.shows_that_fit(_reading(five=65).five_hour, 4.2, 90) == 5


def test_shows_that_fit_is_unknown_without_an_estimate():
    assert pacing.shows_that_fit(_reading(five=65).five_hour, None, 90) is None
    assert pacing.shows_that_fit(None, 4.2, 90) is None


def test_shows_that_fit_floors_at_zero_when_already_over():
    assert pacing.shows_that_fit(_reading(five=95).five_hour, 4.2, 90) == 0


def test_shows_that_fit_treats_a_zero_estimate_as_no_estimate():
    # `observe` really does produce PacingState(0.0, 1) -- an integer-percent
    # meter plus a cheap show is the ordinary case -- and `is None` here
    # would divide by it.
    assert pacing.shows_that_fit(_reading(five=65).five_hour, 0.0, 90) is None


# ---------------------------------------------------------------------------
# binding_forecast: the window that runs out FIRST
# ---------------------------------------------------------------------------


def test_the_forecast_follows_the_weekly_window_when_that_is_what_binds():
    """The measured regression, verbatim: 5h at 20%, weekly at 84%, 4%/show.

    The session window has room for 17 more shows and the weekly one has
    room for 1. Reporting 17 tells an operator to start a 13-show run that
    will stop after one and wait three days -- the failure this feature
    exists to prevent, committed by the feature itself.
    """
    out = pacing.binding_forecast(_reading(five=20, seven=84), 4.0, _opts())
    assert out.shows == 1
    assert out.scope == "seven_day"
    assert out.resets_at == RESET_7D


def test_the_forecast_follows_the_session_window_when_that_is_what_binds():
    out = pacing.binding_forecast(_reading(five=65, seven=7), 4.0, _opts())
    assert out.shows == 6                      # (90-65)//4, not (90-7)//4
    assert out.scope == "five_hour"
    assert out.resets_at == RESET_5H


def test_a_tie_goes_to_the_weekly_window_because_that_is_where_decide_pauses():
    """Both windows run out on the same show. `decide` checks seven_day
    first, so that is the pause the run would actually take -- and naming
    the 5-hour reset would promise a wait of hours for a wait of days."""
    # 90-50 = 40 and 90-50 = 40: identical headroom, identical cost.
    out = pacing.binding_forecast(_reading(five=50, seven=50), 4.0, _opts())
    assert out.shows == 10
    assert out.scope == "seven_day"
    assert out.resets_at == RESET_7D


def test_each_window_is_measured_against_its_own_ceiling():
    """They are independent config fields that merely share a default. With
    the weekly ceiling lowered the weekly binds even though its meter reads
    LOWER than the session one -- which a shared ceiling cannot express."""
    cfg = Config(pacing=PacingConfig(five_hour_ceiling=90, seven_day_ceiling=50))
    opts = pacing.pace_options(cfg)

    out = pacing.binding_forecast(_reading(five=60, seven=40), 5.0, opts)
    assert out.scope == "seven_day"
    assert out.shows == 2                      # (50-40)//5, not (90-40)//5


def test_the_forecast_is_none_when_nothing_can_be_forecast():
    assert pacing.binding_forecast(None, 4.0, _opts()) is None
    assert pacing.binding_forecast(_reading(), None, _opts()) is None
    assert pacing.binding_forecast(_reading(), 0.0, _opts()) is None


def test_a_window_with_no_meter_does_not_compete():
    """Half a reading still forecasts, against the half that exists. The
    weekly meter is the one /usage most often omits."""
    from herder.usage import Meter, UsageReading
    only_session = UsageReading(five_hour=Meter(65, RESET_5H), seven_day=None,
                                per_model={}, fetched_at=NOW)
    out = pacing.binding_forecast(only_session, 5.0, _opts())
    assert (out.shows, out.scope) == (5, "five_hour")

    only_weekly = UsageReading(five_hour=None, seven_day=Meter(65, RESET_7D),
                               per_model={}, fetched_at=NOW)
    out = pacing.binding_forecast(only_weekly, 5.0, _opts())
    assert (out.shows, out.scope) == (5, "seven_day")


def test_the_binding_windows_missing_reset_is_carried_not_swapped():
    """`Meter(pct, None)` is what the live meter produces -- /usage prints
    `Current week (Fable): 0% used` with no reset clause at all. The
    forecast must carry the binding window's own None rather than falling
    back to the other window's instant, which would name a reset belonging
    to a window that is not what stops the run."""
    from herder.usage import Meter, UsageReading
    reading = UsageReading(five_hour=Meter(20, RESET_5H),
                           seven_day=Meter(84, None),
                           per_model={}, fetched_at=NOW)
    out = pacing.binding_forecast(reading, 4.0, _opts())
    assert (out.shows, out.scope) == (1, "seven_day")
    assert out.resets_at is None
