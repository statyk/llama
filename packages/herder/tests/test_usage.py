from datetime import datetime, timezone

from herder import usage

NOW = datetime(2026, 9, 5, 20, 30, tzinfo=timezone.utc)     # 16:30 EDT

# Captured verbatim 2026-09-05 from `claude -p "/usage"` on CLI 2.1.252.
REAL = """You are currently using your subscription to power your Claude Code usage

Current session: 10% used · resets Sep 5 at 5:20pm (America/New_York)
Current week (all models): 7% used · resets Sep 12 at 7am (America/New_York)
Current week (Fable): 0% used

What's contributing to your limits usage?
Approximate, based on local sessions on this machine.

Last 24h · 2817 requests · 46 sessions
  96% of your usage came from subagent-heavy sessions
"""


def test_parses_all_three_meters_from_the_real_output():
    r = usage.parse_usage_text(REAL, now=NOW)
    assert r.five_hour.percent == 10
    assert r.five_hour.resets_at == datetime(2026, 9, 5, 21, 20, tzinfo=timezone.utc)
    assert r.seven_day.percent == 7
    assert r.seven_day.resets_at == datetime(2026, 9, 12, 11, 0, tzinfo=timezone.utc)
    assert r.per_model == {"Fable": usage.Meter(0, None)}


def test_per_model_line_does_not_swallow_the_all_models_line():
    # "Current week (all models)" and "Current week (Fable)" share a prefix;
    # a per-model regex without the negative lookahead captures both and
    # silently reports an "all models" sub-meter that does not exist.
    r = usage.parse_usage_text(REAL, now=NOW)
    assert "all models" not in r.per_model


def test_stale_marker_is_a_failed_read_not_a_number():
    # The one case where the command SUCCEEDS and the number is a lie.
    text = REAL.replace("Current session: 10% used",
                        "Showing last-known usage\nCurrent session: 10% used")
    assert usage.parse_usage_text(text, now=NOW) is None


def test_missing_session_line_is_a_failed_read():
    assert usage.parse_usage_text("You are currently using your subscription\n",
                                  now=NOW) is None
    assert usage.parse_usage_text("", now=NOW) is None
    assert usage.parse_usage_text("total garbage, no meters here", now=NOW) is None


def test_a_meter_with_no_reset_clause_parses_with_resets_at_none():
    r = usage.parse_usage_text("Current session: 42% used\n", now=NOW)
    assert r.five_hour == usage.Meter(42, None)
    assert r.seven_day is None


def test_weekly_reset_uses_the_weekly_bound_not_the_session_one():
    # Seven days out must survive; under limits' 5.5h default it would not.
    r = usage.parse_usage_text(REAL, now=NOW)
    assert r.seven_day.resets_at is not None
