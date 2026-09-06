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


def test_session_line_without_its_own_reset_is_not_polluted_by_a_later_clause():
    # F1: the (.*)$ tail on each regex keeps a meter's captured reset text
    # to that meter's own line, honoring limits.parse_reset's single-clause
    # contract. Widening any one of them to span lines (or dropping the
    # anchors) would let the SESSION meter's parse_reset call pick up the
    # WEEKLY line's reset clause instead of correctly seeing none.
    text = ("Current session: 10% used\n"
            "Current week (all models): 7% used · resets Sep 5 at 9pm "
            "(America/New_York)\n")
    r = usage.parse_usage_text(text, now=NOW)
    assert r.five_hour == usage.Meter(10, None)


# F2: REAL's only per-model line (Fable, 0%, no reset) is tautological -
# every field of usage.Meter(0, None) is its own zero value, so the
# per-model comprehension's percent group, reset-text group, bound, and
# key .strip() can each be mutated with the suite still green. This
# fixture adds a second per-model line with a non-zero percent, its own
# dated reset clause, and surrounding whitespace around the model name.
EXTRA_MODEL = REAL.replace(
    "Current week (Fable): 0% used\n",
    "Current week (Fable): 0% used\n"
    "Current week ( Codex ): 31% used · resets Sep 12 at 7am "
    "(America/New_York)\n",
)


def test_per_model_meter_parses_percent_reset_and_strips_whitespace():
    r = usage.parse_usage_text(EXTRA_MODEL, now=NOW)
    assert r.per_model["Codex"] == usage.Meter(
        31, datetime(2026, 9, 12, 11, 0, tzinfo=timezone.utc))


def test_session_reset_far_beyond_the_five_hour_bound_is_rejected():
    # F3: swapping FIVE_HOUR_MAX_AHEAD_S for SEVEN_DAY_MAX_AHEAD_S on the
    # session meter's parse_reset call would let a mis-parsed or
    # clock-skewed week-out session reset survive. Only the opposite
    # direction is pinned, by
    # test_weekly_reset_uses_the_weekly_bound_not_the_session_one.
    text = ("Current session: 10% used · resets Sep 12 at 5:20pm "
            "(America/New_York)\n")
    r = usage.parse_usage_text(text, now=NOW)
    assert r.five_hour == usage.Meter(10, None)


def test_weekly_all_line_without_its_own_reset_is_not_polluted_by_a_later_clause():
    # F1 continued: the same slicing property, pinned for _WEEK_ALL_RE.
    text = ("Current session: 10% used\n"
            "Current week (all models): 7% used\n"
            "Current week (Codex): 31% used · resets Sep 12 at 7am "
            "(America/New_York)\n")
    r = usage.parse_usage_text(text, now=NOW)
    assert r.seven_day == usage.Meter(7, None)


def test_session_line_is_matched_only_at_its_own_line_start():
    # F1 continued: _SESSION_RE's leading ^ (with re.M) means a
    # "Current session:" substring that does not begin its own line is not
    # a session reading at all - dropping the anchor would instead match it
    # anywhere, mid-prose. Fail-closed: the whole read is untrusted.
    text = "Note: Current session: 10% used\n"
    assert usage.parse_usage_text(text, now=NOW) is None


import json


def _envelope(text):
    return json.dumps({"type": "result", "subtype": "success",
                       "is_error": False, "num_turns": 0,
                       "total_cost_usd": 0, "result": text})


def test_read_usage_parses_the_json_envelope():
    r = usage.read_usage(runner=lambda: _envelope(REAL), now=NOW)
    assert r.five_hour.percent == 10


def test_read_usage_degrades_to_none_on_every_failure_shape():
    for bad in (lambda: None,                       # runner reported failure
                lambda: "",                          # empty stdout
                lambda: "not json at all",           # unparseable envelope
                lambda: json.dumps({"result": None}),   # result not a string
                lambda: json.dumps({"no_result": 1}),   # result absent
                lambda: _envelope("unrecognized prose")):
        assert usage.read_usage(runner=bad, now=NOW) is None


def test_read_usage_never_raises_when_the_runner_explodes():
    def boom():
        raise OSError("claude is not installed")
    assert usage.read_usage(runner=boom, now=NOW) is None
