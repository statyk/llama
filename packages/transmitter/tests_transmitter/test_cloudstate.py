import json

import pytest
from typer.testing import CliRunner

from tests_transmitter.helpers import FakeBucket
from transmitter import cloudstate, grid, service
from transmitter.cli import app
from transmitter.errors import CloudStateError

NOW = grid.iso_to_us("2026-10-20T12:00:00Z")
GUARD = {"schema": 1, "tripped": True, "reason": "spend", "tripped_at": "2026-10-20T11:00:00.000Z",
         "period": {"start": "2026-10-11T00:00:00.000Z", "end": "2026-11-11T00:00:00.000Z"},
         "evaluation": {"at": "2026-10-20T11:45:00.000Z", "actual_usd": 14.0, "projected_usd": 14.0,
                        "budget_usd": 15}, "last_error": None, "waf": {"enabled": True, "error": None}}


def _seed(bucket, key, doc):
    bucket.objects[key] = {"Body": json.dumps(doc).encode(), "ContentType": "application/json", "CacheControl": "no-store"}


def test_offair_on_and_off_write_the_flag_uncached():
    b = FakeBucket()
    doc = cloudstate.set_offair(b, "b", True, "objection received", "2026-10-21T00:00:00Z", NOW)
    assert b.json("state/offair.json") == doc == {"offair": True, "reason": "objection received",
                                                    "since": "2026-10-20T12:00:00.000Z",
                                                    "until": "2026-10-21T00:00:00.000Z"}
    assert b.objects["state/offair.json"]["CacheControl"] == "no-store"
    cloudstate.set_offair(b, "b", False, "back", None, NOW + 1)
    assert b.json("state/offair.json")["offair"] is False


def test_offair_needs_a_reason_and_a_valid_until():
    with pytest.raises(CloudStateError, match="reason"):
        cloudstate.set_offair(FakeBucket(), "b", True, "  ", None, NOW)
    with pytest.raises(CloudStateError, match="ISO-8601"):
        cloudstate.set_offair(FakeBucket(), "b", True, "x", "tomorrow", NOW)


def test_writes_retry_then_fail_loudly():
    b = FakeBucket()
    b.fail_puts["state/offair.json"] = 2
    cloudstate.put_state(b, "b", "state/offair.json", {"offair": True}, sleep=lambda s: None)
    assert b.json("state/offair.json") == {"offair": True}
    b.fail_puts["state/offair.json"] = 5
    with pytest.raises(CloudStateError, match="after 3 attempts"):
        cloudstate.put_state(b, "b", "state/offair.json", {"offair": False}, sleep=lambda s: None)


def test_raise_writes_the_budget_until_the_guards_period_end():
    b = FakeBucket()
    _seed(b, "state/guard.json", GUARD)
    doc = cloudstate.raise_budget(b, "b", 20, NOW)
    assert doc == {"budget_usd": 20, "expires": "2026-11-11T00:00:00.000Z", "written_at": "2026-10-20T12:00:00.000Z"}
    assert b.json("state/budget.json") == doc


@pytest.mark.parametrize("usd, match", [(15, "above the budget"), (10, "above the budget"),
                                        (float("nan"), "above the budget"), (101, "capped")])
def test_raise_must_raise_and_stay_under_the_cap(usd, match):
    b = FakeBucket()
    _seed(b, "state/guard.json", GUARD)
    with pytest.raises(CloudStateError, match=match):
        cloudstate.raise_budget(b, "b", usd, NOW)
    assert "state/budget.json" not in b.objects


def test_raise_refuses_without_a_guard_state_period_or_evaluation():
    with pytest.raises(CloudStateError, match="has not run"):
        cloudstate.raise_budget(FakeBucket(), "b", 20, NOW)
    b = FakeBucket()
    _seed(b, "state/guard.json", {**GUARD, "period": None})
    with pytest.raises(CloudStateError, match="billing period"):
        cloudstate.raise_budget(b, "b", 20, NOW)
    _seed(b, "state/guard.json", {**GUARD, "evaluation": None})
    with pytest.raises(CloudStateError, match="no evaluation"):
        cloudstate.raise_budget(b, "b", 20, NOW)
    _seed(b, "state/guard.json", GUARD)
    with pytest.raises(CloudStateError, match="period ended"):
        cloudstate.raise_budget(b, "b", 20, grid.iso_to_us("2026-11-12T00:00:00Z"))


def test_get_json_absent_corrupt_and_unreachable():
    b = FakeBucket()
    assert cloudstate.get_json(b, "b", "state/guard.json") is None
    b.objects["state/guard.json"] = {"Body": b"{nope", "ContentType": "x", "CacheControl": "x"}
    with pytest.raises(CloudStateError, match="not JSON"):
        cloudstate.get_json(b, "b", "state/guard.json")
    b.fail_gets.add("state/guard.json")
    with pytest.raises(CloudStateError, match="cannot read"):
        cloudstate.get_json(b, "b", "state/guard.json")


def test_guard_summary_lines():
    lines = cloudstate.guard_summary(GUARD)
    assert lines[0].startswith("guard      TRIPPED (spend)")
    assert "actual $14.00, projected $14.00 of $15.00" in lines[1]
    assert lines[-1] == "killswitch enabled"
    assert cloudstate.guard_summary(None)[0].startswith("guard      no state/guard.json")


def _cli(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSMITTER_ROOT", str(tmp_path / "tx"))
    bucket = FakeBucket()
    monkeypatch.setattr(service, "make_client", lambda cfg: bucket)
    monkeypatch.setattr(service, "now_us", lambda: NOW)
    cfgp = tmp_path / "c.toml"
    cfgp.write_text('[publish]\nbucket = "b"\n')
    return bucket, cfgp


def test_cli_offair_on_off_and_budget(tmp_path, monkeypatch):
    bucket, cfgp = _cli(tmp_path, monkeypatch)
    r = CliRunner().invoke(app, ["offair", "on", "--reason", "maintenance", "--config", str(cfgp)])
    assert r.exit_code == 0, r.output
    assert "within about a minute" in r.output and bucket.json("state/offair.json")["offair"] is True
    _seed(bucket, "state/guard.json", GUARD)
    r = CliRunner().invoke(app, ["offair", "off", "--config", str(cfgp)])
    assert r.exit_code == 0 and bucket.json("state/offair.json")["offair"] is False
    assert "cost guard is tripped" in r.output
    r = CliRunner().invoke(app, ["budget", "--config", str(cfgp)])
    assert r.exit_code == 0 and "TRIPPED (spend)" in r.output
    r = CliRunner().invoke(app, ["budget", "--raise-to", "20", "--config", str(cfgp)])
    assert r.exit_code == 0 and bucket.json("state/budget.json")["budget_usd"] == 20
    r = CliRunner().invoke(app, ["budget", "--config", str(cfgp)])
    assert "raise      $20.00 until 2026-11-11T00:00:00.000Z" in r.output


def test_cli_offair_on_requires_a_reason_and_works_while_tripped_and_over_the_put_budget(tmp_path, monkeypatch):
    bucket, cfgp = _cli(tmp_path, monkeypatch)
    assert CliRunner().invoke(app, ["offair", "on", "--config", str(cfgp)]).exit_code != 0
    _seed(bucket, "state/guard.json", GUARD)                     # tripped: publishing is stopped
    (tmp_path / "tx").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tx" / "puts.json").write_text('{"day": "2026-10-20", "count": 999999}')
    r = CliRunner().invoke(app, ["offair", "on", "--reason", "x", "--config", str(cfgp)])
    assert r.exit_code == 0, r.output


# The document exactly as antenna's guard writes it (latch.ts GuardDoc): the
# fields the brief's GUARD omits, and null amounts where JSON has no NaN.
WORKER_GUARD = {**GUARD, "tripped_period_start": "2026-10-11T00:00:00.000Z", "tripped_budget_usd": 15,
                "since": "2026-10-11T00:01:00.000Z", "last_success": "2026-10-20T11:45:00.000Z",
                "evaluated_at": "2026-10-20T11:45:00.000Z",
                "evaluation": {**GUARD["evaluation"], "base_budget_usd": 15,
                               "period_to_date": {"workersRequests": 0, "r2ClassA": 0, "r2ClassB": 0,
                                                  "r2StorageGbMonth": 0},
                               "projected": {"workersRequests": 0, "r2ClassA": 0, "r2ClassB": 0,
                                             "r2StorageGbMonth": 0},
                               "unknown_action_types": []}}
NULL_AMOUNTS = {**WORKER_GUARD, "evaluation": {**WORKER_GUARD["evaluation"], "actual_usd": None,
                                               "projected_usd": None, "budget_usd": None}}


def test_raise_works_on_the_document_the_worker_writes():
    b = FakeBucket()
    _seed(b, "state/guard.json", WORKER_GUARD)
    assert cloudstate.raise_budget(b, "b", 20, NOW)["budget_usd"] == 20


def test_null_amounts_never_crash_the_summary():
    lines = cloudstate.guard_summary(NULL_AMOUNTS)
    assert "actual unknown, projected unknown of unknown" in lines[1]


def test_a_raise_is_refused_when_the_current_budget_is_unknown():
    b = FakeBucket()
    _seed(b, "state/guard.json", NULL_AMOUNTS)
    with pytest.raises(CloudStateError, match="no valid budget"):
        cloudstate.raise_budget(b, "b", 20, NOW)
    assert "state/budget.json" not in b.objects


def test_a_spend_trip_needs_a_raise_above_the_budget_it_tripped_at():
    # latch.ts applyAttempt clears "spend" only when the effective budget
    # exceeds tripped_budget_usd; evaluation.budget_usd can sit below it
    # (a removed budget.json), and a raise between the two never clears.
    b = FakeBucket()
    _seed(b, "state/guard.json", {**WORKER_GUARD, "tripped_budget_usd": 25})
    with pytest.raises(CloudStateError, match=r"tripped at \(\$25\.00\)"):
        cloudstate.raise_budget(b, "b", 20, NOW)
    assert cloudstate.raise_budget(b, "b", 26, NOW)["budget_usd"] == 26


def test_a_blind_trip_does_not_set_the_floor():
    b = FakeBucket()
    _seed(b, "state/guard.json", {**WORKER_GUARD, "reason": "blind", "tripped_budget_usd": 25})
    assert cloudstate.raise_budget(b, "b", 20, NOW)["budget_usd"] == 20


def test_a_raise_not_yet_evaluated_counts_as_the_budget_in_use():
    b = FakeBucket()
    _seed(b, "state/guard.json", WORKER_GUARD)
    _seed(b, "state/budget.json", {"budget_usd": 30, "expires": "2026-11-11T00:00:00.000Z",
                                   "written_at": "2026-10-20T11:59:00.000Z"})
    with pytest.raises(CloudStateError, match=r"\$30\.00"):
        cloudstate.raise_budget(b, "b", 20, NOW)
    assert b.json("state/budget.json")["budget_usd"] == 30
    assert cloudstate.raise_budget(b, "b", 31, NOW)["budget_usd"] == 31


@pytest.mark.parametrize("pending", [
    {"budget_usd": 30, "expires": "2026-10-20T00:00:00.000Z", "written_at": "2026-10-12T00:00:00.000Z"},  # expired
    {"budget_usd": 30, "expires": "2026-12-11T00:00:00.000Z", "written_at": "2026-10-12T00:00:00.000Z"},  # past period
    {"budget_usd": "30", "expires": "2026-11-11T00:00:00.000Z", "written_at": "2026-10-12T00:00:00.000Z"},
    {"nope": True},
])
def test_a_raise_the_worker_ignores_does_not_set_the_floor(pending):
    b = FakeBucket()
    _seed(b, "state/guard.json", WORKER_GUARD)
    _seed(b, "state/budget.json", pending)
    assert cloudstate.raise_budget(b, "b", 20, NOW)["budget_usd"] == 20


def test_a_corrupt_budget_file_is_overwritten_but_an_unreadable_one_refuses():
    b = FakeBucket()
    _seed(b, "state/guard.json", WORKER_GUARD)
    b.objects["state/budget.json"] = {"Body": b"{nope", "ContentType": "x", "CacheControl": "x"}
    assert cloudstate.raise_budget(b, "b", 20, NOW)["budget_usd"] == 20       # the guard's own advice
    b.fail_gets.add("state/budget.json")
    with pytest.raises(CloudStateError, match="cannot read state/budget.json"):
        cloudstate.raise_budget(b, "b", 25, NOW)
    assert b.json("state/budget.json")["budget_usd"] == 20


def test_the_raise_is_compared_after_rounding_to_cents():
    b = FakeBucket()
    _seed(b, "state/guard.json", WORKER_GUARD)
    with pytest.raises(CloudStateError, match="above the budget"):
        cloudstate.raise_budget(b, "b", 15.004, NOW)


def test_cli_budget_tolerates_an_odd_raise_file(tmp_path, monkeypatch):
    bucket, cfgp = _cli(tmp_path, monkeypatch)
    _seed(bucket, "state/guard.json", NULL_AMOUNTS)
    _seed(bucket, "state/budget.json", {"budget_usd": "lots"})
    r = CliRunner().invoke(app, ["budget", "--config", str(cfgp)])
    assert r.exit_code == 0, r.output
    assert "raise      unknown until None" in r.output
