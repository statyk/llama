### Task 12: `transmitter offair` and `transmitter budget`

**Model hint:** opus (the takedown lever and the spend-trip clearance)

**Files:**
- Create: `packages/transmitter/src/transmitter/cloudstate.py`, `packages/transmitter/tests_transmitter/test_cloudstate.py`
- Modify: `packages/transmitter/src/transmitter/errors.py`, `packages/transmitter/src/transmitter/cli.py`

**Interfaces:**
- Consumes:
  - `state/guard.json` as the guard writes it (Task 4's `GuardDoc`): `tripped`, `reason`, `tripped_at`, `period.{start,end}`, `evaluation.{at, actual_usd, projected_usd, budget_usd}`, `last_error`, `last_success`, `since` and `waf.{enabled, error}`.
  - The clock's raise cap (`MAX_BUDGET_USD = 100`).
- Produces:
  - `errors.CloudStateError(TransmitterError)`.
  - `cloudstate`: `OFFAIR_KEY`, `BUDGET_KEY`, `GUARD_KEY`, `ALERTS_KEY`, `MAX_RAISE_USD = 100.0`; `get_json(client, bucket, key) -> dict | None`; `put_state(client, bucket, key, doc, *, attempts=3, sleep=time.sleep)`; `set_offair(client, bucket, on, reason, until, now_us) -> dict`; `guard_period_end_us(guard)`; `current_budget_usd(guard)`; `raise_budget(client, bucket, usd, now_us) -> dict`; `guard_summary(guard | None) -> list[str]`.
  - CLI: `transmitter offair on --reason TEXT [--until ISO]`, `transmitter offair off [--reason TEXT]`, `transmitter budget [--raise-to USD]`; helper `cli._cloud(config) -> (client, bucket)` (Task 16 reuses it).

Ruling R7: these writes bypass the publish lock, the guard check and the daily PUT budget. A test pins that `offair on` works while the guard is tripped and the PUT budget is spent. The JSON is written `no-store`.

`raise_budget`:
- refuses without a `guard.json`, without a period or evaluation, or after the period has ended;
- refuses a value at or below the budget the guard uses now, or above $100;
- writes `{budget_usd, expires: <the guard's period end>, written_at}`.

- [ ] **Step 1: Write the failing test**

`packages/transmitter/tests_transmitter/test_cloudstate.py`:

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_cloudstate.py -q`
Expected: FAIL. `cannot import name 'cloudstate'`.

- [ ] **Step 3: Implement**

Append to `packages/transmitter/src/transmitter/errors.py`:

```python


class CloudStateError(TransmitterError):
    """An operator command could not read or write the station's cloud state
    (state/offair.json, state/budget.json, state/guard.json)."""
```

`packages/transmitter/src/transmitter/cloudstate.py`:

```python
"""The operator's levers in the cloud (spec "Blocking"): state/offair.json,
written by `transmitter offair on|off`, and state/budget.json, written by
`transmitter budget --raise-to`; plus read-only access to the clock's
state/guard.json and state/alerts.json for `budget` and `status`.

These writes must work while the cost guard is tripped and whatever the daily
PUT budget says -- they are how the operator takes the station off the air or
clears a spend trip -- so they bypass the publish lock, the guard check and the
PUT budget. Each is one small PUT made by hand. The guard never writes
offair.json; `offair off` clears only the operator's flag."""

import json
import math
import time
from typing import Any, Callable

from transmitter import grid
from transmitter.errors import CloudStateError

OFFAIR_KEY = "state/offair.json"
BUDGET_KEY = "state/budget.json"
GUARD_KEY = "state/guard.json"
ALERTS_KEY = "state/alerts.json"
JSON_TYPE = "application/json"
STATE_CACHE = "no-store"
# antenna's MAX_BUDGET_USD: the clock never honours a raise above it.
MAX_RAISE_USD = 100.0


def _code(exc: Exception) -> str | None:
    response = getattr(exc, "response", None)
    return response.get("Error", {}).get("Code") if isinstance(response, dict) else None


def get_json(client: Any, bucket: str, key: str) -> dict | None:
    """The object as a dict; None when absent. Anything else is a CloudStateError."""
    try:
        resp = client.get_object(Bucket=bucket, Key=key)
    except Exception as exc:
        if _code(exc) in ("NoSuchKey", "404"):
            return None
        raise CloudStateError(f"cannot read {key}: {exc}") from exc
    try:
        doc = json.loads(resp["Body"].read())
    except ValueError as exc:
        raise CloudStateError(f"{key} is not JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise CloudStateError(f"{key} is not a JSON object")
    return doc


def put_state(client: Any, bucket: str, key: str, doc: dict, *, attempts: int = 3,
              sleep: Callable[[float], None] = time.sleep) -> None:
    body = (json.dumps(doc, sort_keys=True) + "\n").encode()
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            resp = client.put_object(Bucket=bucket, Key=key, Body=body, ContentType=JSON_TYPE,
                                     CacheControl=STATE_CACHE)
            if resp.get("ResponseMetadata", {}).get("HTTPStatusCode") == 200:
                return
            last = CloudStateError(f"PUT {key}: HTTP {resp.get('ResponseMetadata', {}).get('HTTPStatusCode')}")
        except Exception as exc:
            last = exc
        if attempt + 1 < attempts:
            sleep(2.0 ** attempt)
    raise CloudStateError(f"could not write {key} after {attempts} attempts: {last}") from last


def _iso_or_none(value: str | None, what: str) -> str | None:
    if value is None:
        return None
    try:
        return grid.us_to_iso(grid.iso_to_us(value))
    except ValueError as exc:
        raise CloudStateError(f"{what} must be an ISO-8601 UTC time like 2026-10-20T18:00:00Z: {value!r}") from exc


def set_offair(client: Any, bucket: str, on: bool, reason: str, until: str | None, now_us: int) -> dict:
    """Write the operator's flag. `until` is informational: the flag stays
    until `offair off` (nothing clears it automatically)."""
    if not reason.strip():
        raise CloudStateError("give a --reason (it is shown in `transmitter status`)")
    doc = {"offair": on, "reason": reason.strip(), "since": grid.us_to_iso(now_us),
           "until": _iso_or_none(until, "--until") if on else None}
    put_state(client, bucket, OFFAIR_KEY, doc)
    return doc


def guard_period_end_us(guard: dict) -> int:
    try:
        return grid.iso_to_us(guard["period"]["end"])
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise CloudStateError("state/guard.json has no billing period yet: wait for the guard's first "
                              "successful evaluation (within 15 minutes of deploying antenna)") from exc


def current_budget_usd(guard: dict) -> float:
    evaluation = guard.get("evaluation") or {}
    value = evaluation.get("budget_usd")
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        raise CloudStateError("state/guard.json has no evaluation yet: wait for the guard's first successful "
                              "evaluation")
    return float(value)


def raise_budget(client: Any, bucket: str, usd: float, now_us: int) -> dict:
    """Write state/budget.json {budget_usd, expires: the guard's period end,
    written_at}. It must raise the budget the guard uses now, and stays at or
    under MAX_RAISE_USD. The guard evaluates at its next run (a raise newer than
    its last evaluation triggers one) and clears a spend trip only if that
    evaluation is under the thresholds."""
    guard = get_json(client, bucket, GUARD_KEY)
    if guard is None:
        raise CloudStateError("no state/guard.json: the cost guard has not run yet (is antenna deployed?)")
    end_us = guard_period_end_us(guard)
    if end_us <= now_us:
        raise CloudStateError(f"state/guard.json's billing period ended at {grid.us_to_iso(end_us)}; wait for "
                              "the guard to evaluate the new period")
    current = current_budget_usd(guard)
    if not math.isfinite(usd) or usd <= current:
        raise CloudStateError(f"--raise-to must be above the budget the guard uses now (${current:.2f})")
    if usd > MAX_RAISE_USD:
        raise CloudStateError(f"--raise-to is capped at ${MAX_RAISE_USD:.0f} (the clock ignores more); the "
                              "station's policy is to shut down, not to keep raising")
    doc = {"budget_usd": round(usd, 2), "expires": grid.us_to_iso(end_us), "written_at": grid.us_to_iso(now_us)}
    put_state(client, bucket, BUDGET_KEY, doc)
    return doc


def guard_summary(guard: dict | None) -> list[str]:
    """Human lines for `budget` and `status`."""
    if guard is None:
        return ["guard      no state/guard.json yet (antenna not deployed, or not run)"]
    lines = []
    if guard.get("tripped"):
        lines.append(f"guard      TRIPPED ({guard.get('reason')}) since {guard.get('tripped_at')}")
    else:
        lines.append("guard      not tripped")
    ev = guard.get("evaluation")
    if isinstance(ev, dict):
        lines.append(f"spend      actual ${ev.get('actual_usd', 0):.2f}, projected ${ev.get('projected_usd', 0):.2f} "
                     f"of ${ev.get('budget_usd', 0):.2f} (evaluated {ev.get('at')})")
    period = guard.get("period") or {}
    if period:
        lines.append(f"period     {period.get('start')} .. {period.get('end')}")
    if guard.get("last_error"):
        lines.append(f"reading    failing since {guard.get('last_success') or guard.get('since')}: "
                     f"{guard.get('last_error')}")
    waf = guard.get("waf") or {}
    state = {True: "enabled", False: "disabled", None: "unknown"}.get(waf.get("enabled"), "unknown")
    lines.append(f"killswitch {state}" + (f" (error: {waf['error']})" if waf.get("error") else ""))
    return lines
```

In `cli.py`, change `from transmitter import aacenc, fallback, grid, pipeline, service` to `from transmitter import aacenc, cloudstate, fallback, grid, pipeline, service`. Then insert after `app.add_typer(fallback_app, name="fallback")`:

```python

offair_app = typer.Typer(help="Take the station off the air (state/offair.json), or put it back",
                         pretty_exceptions_enable=False, no_args_is_help=True)
app.add_typer(offair_app, name="offair")


def _cloud(config: Path | None):
    """(client, bucket) for the operator commands: R2 keys from the environment."""
    from transmitter.errors import ConfigError

    cfg = load_config(config)
    if not cfg.publish.bucket:
        raise ConfigError("set [publish] bucket in transmitter's config.toml")
    return service.make_client(cfg), cfg.publish.bucket


@offair_app.command("on")
def offair_on(
    reason: str = typer.Option(..., "--reason", help="Why (shown in `transmitter status`)"),
    until: str = typer.Option(None, "--until", help="Expected end, ISO-8601 UTC (informational only)"),
    config: Path = CONFIG_OPT,
):
    """Off the air: within about a minute the clock lists the off-air notice and
    ENDLIST, index.html becomes the off-air page and the WAF kill switch is on."""
    client, bucket = _cloud(config)
    doc = cloudstate.set_offair(client, bucket, True, reason, until, service.now_us())
    typer.echo(f"state/offair.json: off the air since {doc['since']} ({doc['reason']}). The clock blocks the "
               "station within about a minute: the off-air playlist and page, and the kill switch.")


@offair_app.command("off")
def offair_off(
    reason: str = typer.Option("back on air", "--reason", help="Why (shown in `transmitter status`)"),
    config: Path = CONFIG_OPT,
):
    """Back on the air (clears only the operator's flag; a tripped cost guard keeps the station blocked)."""
    client, bucket = _cloud(config)
    doc = cloudstate.set_offair(client, bucket, False, reason, None, service.now_us())
    typer.echo(f"state/offair.json: on the air since {doc['since']}.")
    guard = cloudstate.get_json(client, bucket, cloudstate.GUARD_KEY)
    if guard and guard.get("tripped"):
        typer.echo(f"note: the cost guard is tripped ({guard.get('reason')}); the station stays blocked until it "
                   "clears (see `transmitter budget`).", err=True)


@app.command()
def budget(
    raise_to: float = typer.Option(None, "--raise-to", help="Raise this billing period's budget to USD"),
    config: Path = CONFIG_OPT,
):
    """Show the cost guard's state, or raise the budget for the rest of this billing period."""
    client, bucket = _cloud(config)
    if raise_to is not None:
        doc = cloudstate.raise_budget(client, bucket, raise_to, service.now_us())
        typer.echo(f"state/budget.json: ${doc['budget_usd']:.2f} until {doc['expires']}. The guard evaluates at its "
                   "next run; a spend trip clears only if that evaluation is under the thresholds.")
        return
    for line in cloudstate.guard_summary(cloudstate.get_json(client, bucket, cloudstate.GUARD_KEY)):
        typer.echo(line)
    raised = cloudstate.get_json(client, bucket, cloudstate.BUDGET_KEY)
    if raised:
        typer.echo(f"raise      ${float(raised.get('budget_usd', 0)):.2f} until {raised.get('expires')}")
```

- [ ] **Step 4: Run the transmitter suite on both Pythons**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q && ./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter/src/transmitter/cloudstate.py packages/transmitter/src/transmitter/errors.py packages/transmitter/src/transmitter/cli.py packages/transmitter/tests_transmitter/test_cloudstate.py
git commit -m "feat(transmitter): offair on|off and budget --raise-to write the station's cloud state"
```

---

