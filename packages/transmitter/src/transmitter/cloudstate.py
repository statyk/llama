"""The operator's levers in the cloud (spec "Blocking"): state/offair.json,
written by `transmitter offair on|off`, and state/budget.json, written by
`transmitter budget --raise-to`; plus read-only access to the clock's
state/guard.json and state/alerts.json for `budget` and `status`.

These writes must work while the cost guard is tripped and whatever the daily
PUT budget says -- they are how the operator takes the station off the air or
clears a spend trip -- so they bypass the publish lock, the guard check and the
PUT budget (ruling R7). Each is one small PUT made by hand. The guard never
writes offair.json; `offair off` clears only the operator's flag.

state/guard.json is read as antenna writes it (antenna/src/latch.ts `GuardDoc`):
its amounts may be null (JSON has no NaN), and anything this module cannot make
sense of is shown as unknown, or -- for a raise -- refused."""

import json
import math
import time
from typing import Any, Callable

from transmitter import grid
from transmitter.errors import CloudStateError
from transmitter.publish import GUARD_KEY, NON_RETRYABLE
from transmitter.publish import _error_code as _code

OFFAIR_KEY = "state/offair.json"
BUDGET_KEY = "state/budget.json"
ALERTS_KEY = "state/alerts.json"
JSON_TYPE = "application/json"
STATE_CACHE = "no-store"
# antenna's MAX_BUDGET_USD: the clock never honours a raise above it.
MAX_RAISE_USD = 100.0


def get_json(client: Any, bucket: str, key: str, *, corrupt_as_absent: bool = False) -> dict | None:
    """The object as a dict; None when absent. A read that fails is always a
    CloudStateError; bytes that are not a JSON object are one too, unless
    `corrupt_as_absent` (for a file the Worker itself ignores when corrupt)."""
    try:
        resp = client.get_object(Bucket=bucket, Key=key)
    except Exception as exc:
        if _code(exc) in ("NoSuchKey", "404"):
            return None
        raise CloudStateError(f"cannot read {key}: {exc}") from exc
    try:
        doc = json.loads(resp["Body"].read())
    except ValueError as exc:
        if corrupt_as_absent:
            return None
        raise CloudStateError(f"{key} is not JSON: {exc}") from exc
    if not isinstance(doc, dict):
        if corrupt_as_absent:
            return None
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
            if _code(exc) in NON_RETRYABLE:
                # Credentials or bucket are wrong: no retry can succeed.
                raise CloudStateError(f"could not write {key}: {exc}") from exc
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
    """Write the operator's flag. `until` is informational (R9): the flag stays
    until `offair off` (nothing clears it automatically)."""
    if not reason.strip():
        raise CloudStateError("give a --reason (it is shown in `transmitter status`)")
    doc = {"offair": on, "reason": reason.strip(), "since": grid.us_to_iso(now_us),
           "until": _iso_or_none(until, "--until") if on else None}
    put_state(client, bucket, OFFAIR_KEY, doc)
    return doc


def _finite(value: Any) -> float | None:
    """A JSON number as the Worker counts one (`typeof v === "number"` and
    finite): bools and strings are not numbers."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _iso_ok(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        grid.iso_to_us(value)
    except ValueError:
        return False
    return True


def guard_doc_problem(guard: Any) -> str | None:
    """Why antenna's latch.ts `parseGuardDoc` would reject this document (and
    the Worker treat it as corrupt: a spend trip latched at the budget then in
    effect, which would swallow a raise written now), or None when it would
    accept it. A mirror of its shape checks; the Worker writes ISO times with
    toISOString, so `since` is checked with grid.iso_to_us."""
    def str_or_null(v: Any) -> bool:
        return v is None or isinstance(v, str)

    def num_or_null(v: Any) -> bool:
        return v is None or _finite(v) is not None

    if not isinstance(guard, dict) or guard.get("schema") != 1 or isinstance(guard.get("schema"), bool):
        return "schema is not 1"
    if not isinstance(guard.get("tripped"), bool):
        return "tripped is not a boolean"
    if guard.get("reason", "missing") not in (None, "spend", "blind"):
        return "reason is not null, spend or blind"
    if guard["tripped"] != (guard["reason"] is not None):
        return "tripped and reason disagree"
    if not _iso_ok(guard.get("since")):
        return "since is not a time"
    for k in ("tripped_at", "tripped_period_start", "last_success", "evaluated_at", "last_error"):
        if not str_or_null(guard.get(k, 0)):
            return f"{k} is not a string or null"
    if not num_or_null(guard.get("tripped_budget_usd", "missing")):
        return "tripped_budget_usd is not a number or null"
    waf = guard.get("waf")
    if not isinstance(waf, dict) or not (waf.get("enabled", 0) is None or isinstance(waf.get("enabled"), bool)) \
            or not str_or_null(waf.get("error", 0)):
        return "waf is not {enabled, error}"
    period = guard.get("period", "missing")
    if not (period is None or (isinstance(period, dict) and isinstance(period.get("start"), str)
                               and isinstance(period.get("end"), str))):
        return "period is not null or {start, end}"
    ev = guard.get("evaluation", "missing")
    if not (ev is None or (isinstance(ev, dict) and isinstance(ev.get("at"), str)
                           and all(num_or_null(ev.get(k, "missing"))
                                   for k in ("actual_usd", "projected_usd", "budget_usd")))):
        return "evaluation is not null or {at, actual_usd, projected_usd, budget_usd}"
    return None


def guard_period_end_us(guard: dict) -> int:
    try:
        return grid.iso_to_us(guard["period"]["end"])
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise CloudStateError("state/guard.json has no billing period yet: wait for the guard's first "
                              "successful evaluation (within 15 minutes of deploying antenna)") from exc


def current_budget_usd(guard: dict) -> float:
    """The effective budget of the guard's last evaluation (`evaluation.budget_usd`:
    the configured budget, or a raise it honoured). Refuses -- fails closed --
    when that is not a finite number."""
    evaluation = guard.get("evaluation")
    if not isinstance(evaluation, dict):
        raise CloudStateError("state/guard.json has no evaluation yet: wait for the guard's first successful "
                              "evaluation")
    value = _finite(evaluation.get("budget_usd"))
    if value is None:
        raise CloudStateError("state/guard.json's last evaluation recorded no valid budget (is antenna's "
                              "MONTHLY_BUDGET_USD set?), so a raise cannot be checked against it")
    return value


def raise_verdict(raised: dict, now_us: int, period_end_us: int | None,
                  base_usd: float | None = None) -> tuple[float | None, str]:
    """(the budget the Worker honours from this state/budget.json, or None;
    why), by latch.ts effectiveBudget's rules: a finite budget_usd above the
    configured budget, unexpired, expiring no later than the period's end, and
    capped at MAX_BUDGET_USD. An unknown period end or base skips that check."""
    usd = _finite(raised.get("budget_usd"))
    if usd is None:
        return None, "ignored: budget_usd is not a number"
    try:
        expires = grid.iso_to_us(raised["expires"])
    except (KeyError, TypeError, ValueError, AttributeError):
        return None, "ignored: expires is not a time"
    if expires <= now_us:
        return None, "expired"
    if base_usd is not None and usd <= base_usd:
        return None, f"ignored: not above the configured budget ({usd_text(base_usd)})"
    if period_end_us is not None and expires > period_end_us:
        return None, "ignored: expires after the billing period ends"
    if usd > MAX_RAISE_USD:
        return MAX_RAISE_USD, f"honoured, capped at ${MAX_RAISE_USD:.0f}"
    return usd, "honoured"


def _pending_raise_usd(raised: dict | None, now_us: int, period_end_us: int) -> float | None:
    """A raise already in state/budget.json that the Worker would honour now
    -- possibly written after the guard's last evaluation, so not yet in
    `evaluation.budget_usd`. (The configured-budget check is skipped: such a
    raise is below the evaluated budget anyway.)"""
    return None if raised is None else raise_verdict(raised, now_us, period_end_us)[0]


def raise_budget(client: Any, bucket: str, usd: float, now_us: int) -> dict:
    """Write state/budget.json {budget_usd, expires: the guard's period end,
    written_at}. It must raise the budget the guard uses now and stays at or
    under MAX_RAISE_USD. "The budget the guard uses now" is the highest of the
    last evaluation's budget, the budget a spend trip was latched at (latch.ts
    clears "spend" only above it, R3), and a raise already written but not yet
    evaluated. The guard evaluates at its next run (a raise newer than its last
    evaluation triggers one) and clears a spend trip only if that evaluation is
    under the thresholds."""
    guard = get_json(client, bucket, GUARD_KEY)
    if guard is None:
        raise CloudStateError("no state/guard.json: the cost guard has not run yet (is antenna deployed?)")
    problem = guard_doc_problem(guard)
    if problem is not None:
        raise CloudStateError(f"state/guard.json is not a document the guard wrote ({problem}): the guard treats it "
                              "as a spend trip and would swallow a raise written now. It rewrites the document "
                              "within a minute; retry once `transmitter budget` shows an evaluation")
    end_us = guard_period_end_us(guard)
    if end_us <= now_us:
        raise CloudStateError(f"state/guard.json's billing period ended at {grid.us_to_iso(end_us)}; wait for "
                              "the guard to evaluate the new period")
    floor, what = current_budget_usd(guard), "the budget the guard uses now"
    if guard.get("tripped") is True and guard.get("reason") == "spend":
        tripped_at = _finite(guard.get("tripped_budget_usd"))
        if tripped_at is not None and tripped_at > floor:
            floor, what = tripped_at, "the budget the guard tripped at"
    # A corrupt budget.json is ignored by the Worker too (it evaluates against
    # the configured budget, and alerts telling the operator to rewrite it).
    pending = _pending_raise_usd(get_json(client, bucket, BUDGET_KEY, corrupt_as_absent=True), now_us, end_us)
    if pending is not None and pending > floor:
        floor, what = pending, "the raise already in state/budget.json"
    if not math.isfinite(usd) or round(usd, 2) <= floor:
        raise CloudStateError(f"--raise-to must be above {what} (${floor:.2f})")
    if usd > MAX_RAISE_USD or round(usd, 2) > MAX_RAISE_USD:
        raise CloudStateError(f"--raise-to is capped at ${MAX_RAISE_USD:.0f} (the clock ignores more); the "
                              "station's policy is to shut down, not to keep raising")
    doc = {"budget_usd": round(usd, 2), "expires": grid.us_to_iso(end_us), "written_at": grid.us_to_iso(now_us)}
    put_state(client, bucket, BUDGET_KEY, doc)
    return doc


def usd_text(value: Any) -> str:
    """$x.xx, or "unknown" for a null (or otherwise not finite) amount."""
    amount = _finite(value)
    return "unknown" if amount is None else f"${amount:.2f}"


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
        lines.append(f"spend      actual {usd_text(ev.get('actual_usd'))}, projected "
                     f"{usd_text(ev.get('projected_usd'))} of {usd_text(ev.get('budget_usd'))} "
                     f"(evaluated {ev.get('at')})")
    period = guard.get("period")
    if isinstance(period, dict) and period:
        lines.append(f"period     {period.get('start')} .. {period.get('end')}")
    if guard.get("last_error"):
        lines.append(f"reading    failing since {guard.get('last_success') or guard.get('since')}: "
                     f"{guard.get('last_error')}")
    waf = guard.get("waf") if isinstance(guard.get("waf"), dict) else {}
    enabled = waf.get("enabled")
    state = "enabled" if enabled is True else "disabled" if enabled is False else "unknown"
    lines.append(f"killswitch {state}" + (f" (error: {waf['error']})" if waf.get("error") else ""))
    return lines
