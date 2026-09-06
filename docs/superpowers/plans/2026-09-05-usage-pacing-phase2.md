# Usage Pacing Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a llama run pause *before* exhausting a usage window, recover from a limit hit during the run-level stages, and answer "how many shows fit before the reset?"

**Architecture:** A new `herder/usage.py` reads the live account meter by shelling `claude -p "/usage"` (zero tokens, `num_turns: 0`) and parsing the prose out of the JSON envelope. A pure `decide()` in `llama/pacing.py` turns a reading plus a learned per-show delta into `Proceed` or `PauseUntil`. `_execute` consults it at three new points and reuses phase 1's existing pause rendering unchanged.

**Tech Stack:** Python 3.12+, Pydantic v2 (config), Typer (CLI), pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-05-usage-pacing-phase2-design.md`

## Global Constraints

- **Tests are offline and deterministic.** No wall-clock reads, no real `$HOME`, no subprocess spawns, no sleeping. `decide()` takes `now`; `read_usage` takes an injected `runner`.
- **`read_usage` and `parse_usage_text` never raise.** Every failure path returns `None`.
- **Backend gating:** the proactive rules run only when `config.llm_for("default").backend == "claude_cli"`. Under `openrouter` or `fake` the meter is never read.
- **`RateLimited` subclasses `HerderError`**, so every new `except RateLimited` must be ordered **before** any `except HerderError` in the same try block.
- **Do not touch `openrouter.py`.** openrouter pacing is an explicit non-goal.
- **Do not add `--batch`, `--force`, or `trust_age`.** They were proposed in the phase-1 spec and are deliberately not introduced.
- **Venv discipline (from CLAUDE.md):** in a worktree, give the worktree its own `.venv` and run `./.venv/bin/pytest`. Never run a `.venv/bin/*` console script from a copy of the tree. Verify with `./.venv/bin/python -c "import llama; print(llama.__file__)"`.
- Full suite: `pytest -q` from the repo root. Current baseline: 1742 tests passing.

## Rulings applied during execution

Recorded 2026-09-05 by the SDD orchestrator's pre-flight conflict scan, and
confirmed against source by the plan's author. Where a ruling and the task
text below disagree, **the ruling governs**.

- **R1 (Task 4) — `_pace` keeps `typer.Exit(1)`.** Task 4's snippet rewrites
  `_pace`'s except body to raise `typer.BadParameter`, which Typer exits with
  code 2. `test_pace_loop.py::test_a_malformed_max_wait_fails_before_the_run_starts`
  pins `exit_code == 1` across three parametrized argv. Change only the
  *construction* — `pace_options(config, wait=..., max_wait=..., no_pacing=...)`
  in place of `dataclasses.replace` — and leave the `typer.echo(...); raise
  typer.Exit(1)` body alone. The unused `replace` import still goes.

- **R2 (Task 6) — `_checkpoint_pause` is not shared with the per-show loop.**
  Its docstring claims both callers; in fact it is wired only to the run-level
  catch and Task 7's pre-flight gate. The per-show loop's own rendering
  (`paused after N shows: ...`) is pinned by
  `test_a_checkpoint_reports_how_many_shows_are_left` and additionally carries
  the no-progress guard and the sleep branch. Do not refactor it into the
  helper; write the docstring to match what the helper actually shares.

- **R3 (Task 7) — the per-show loop's `when` needs an isinstance guard.**
  Task 7 says to "pass `when=limited.when`", but the line in question is
  `when = resume_at(limited, pace)`, which does not call `_checkpoint_pause`.
  `resume_at` reads `getattr(err, "resets_at", None)`, and a `PauseUntil` has
  no such attribute — so a proactive pause would silently sleep the one-hour
  `unknown_reset_wait` default instead of sleeping to the reset the meter
  named. It becomes:

  ```python
  when = (limited.when if isinstance(limited, PauseUntil)
          else resume_at(limited, pace))
  ```

  and `limited`'s annotation widens to `RateLimited | PauseUntil | None`.
  Giving `PauseUntil` a `resets_at` property is the wrong fix: `PauseUntil.when`
  already includes `reset_skew`, so `resume_at` would apply it twice.

- **R4 (Task 9) — mutation 1's expected red set is corrected.** Mutating
  `usage.SEVEN_DAY_MAX_AHEAD_S` turns
  `test_weekly_reset_uses_the_weekly_bound_not_the_session_one` and
  `test_parses_all_three_meters_from_the_real_output` red, both in
  `test_usage.py`. It does **not** touch
  `test_parse_reset_bound_is_per_call_not_global`, which passes `7.5 * 86400`
  as a literal and so never reads the constant. The constraint is pinned
  either way; no test is strengthened.

## File Structure

| File | Responsibility |
| --- | --- |
| `packages/herder/src/herder/limits.py` | *Modified.* `parse_reset` gains a dated form and a per-call max-ahead bound. Refusal classification unchanged. |
| `packages/herder/src/herder/usage.py` | *New.* `Meter`, `UsageReading`, `parse_usage_text` (pure), `read_usage` (subprocess). Headroom only — no refusal logic. |
| `packages/llama/src/llama/pacing.py` | *Modified.* Gains `Proceed`, `PauseUntil`, `Progress`, `decide()`. Existing duration/sleep/`PaceOptions` helpers unchanged. |
| `packages/llama/src/llama/pacing_state.py` | *New.* EWMA over per-show deltas, persisted to `<root>/pacing-state.json` under a `file_lock`. |
| `packages/llama/src/llama/config.py` | *Modified.* `PacingConfig` gains two ceilings; `DEFAULT_CONFIG_TOML` gains the matching block. |
| `packages/llama/src/llama/cli.py` | *Modified.* Three new gate points in `_execute`, the run-level catch, the forecast line, and the `llama pacing` command. |
| `packages/herder/tests/test_usage.py` | *New.* Parser and reader tests. |
| `packages/llama/tests/test_pacing_decide.py` | *New.* Policy tables. |
| `packages/llama/tests/test_pacing_state.py` | *New.* EWMA and persistence. |
| `packages/llama/tests/test_pace_loop.py` | *Modified.* Run-level catch and gate integration. |

---

### Task 1: Dated reset parsing and a per-call max-ahead bound

The `/usage` output names a reset with a **date** (`resets Sep 5 at 5:20pm (America/New_York)`), and the weekly line may omit minutes entirely (`resets Sep 12 at 7am (America/New_York)`). The refusal message parsed today has neither. One parser, two shapes.

The existing single `MAX_RESET_AHEAD_S` (5.5 h) is correct for a session refusal and wrong for a weekly reading, which is legitimately up to seven days out. It becomes a default rather than a constant.

**Files:**
- Modify: `packages/herder/src/herder/limits.py`
- Test: `packages/herder/tests/test_limits.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `limits.parse_reset(text, now=None, max_ahead_s=MAX_RESET_AHEAD_S) -> datetime | None`, accepting both the time-only and dated forms. `limits.MAX_RESET_AHEAD_S` keeps its current value and meaning.

- [ ] **Step 1: Write the failing tests**

Append to `packages/herder/tests/test_limits.py`:

```python
def test_parse_reset_accepts_the_dated_usage_form():
    # /usage names a date; the refusal message does not. Same parser.
    now = datetime(2026, 9, 5, 20, 0, tzinfo=timezone.utc)   # 16:00 EDT
    out = limits.parse_reset("resets Sep 5 at 5:20pm (America/New_York)", now=now)
    assert out == datetime(2026, 9, 5, 21, 20, tzinfo=timezone.utc)


def test_parse_reset_accepts_a_dated_form_with_no_minutes():
    # Measured: the weekly line renders as "7am", not "7:00am".
    now = datetime(2026, 9, 5, 20, 0, tzinfo=timezone.utc)
    out = limits.parse_reset("resets Sep 12 at 7am (America/New_York)", now=now,
                             max_ahead_s=7.5 * 86400)
    assert out == datetime(2026, 9, 12, 11, 0, tzinfo=timezone.utc)


def test_parse_reset_bound_is_per_call_not_global():
    # The same weekly text is REJECTED under the default 5.5h bound and
    # ACCEPTED under a weekly one. This is the whole point of the parameter.
    now = datetime(2026, 9, 5, 20, 0, tzinfo=timezone.utc)
    text = "resets Sep 12 at 7am (America/New_York)"
    assert limits.parse_reset(text, now=now) is None
    assert limits.parse_reset(text, now=now, max_ahead_s=7.5 * 86400) is not None


def test_parse_reset_dated_rolls_to_next_year_then_fails_the_bound():
    # A date already past this year resolves to next year, which no bound
    # admits -- so a stale or skewed date degrades to None, never to a
    # year-long sleep.
    now = datetime(2026, 12, 31, 20, 0, tzinfo=timezone.utc)
    out = limits.parse_reset("resets Jan 2 at 7am (America/New_York)", now=now,
                             max_ahead_s=7.5 * 86400)
    assert out == datetime(2027, 1, 2, 12, 0, tzinfo=timezone.utc)
    assert limits.parse_reset("resets Dec 1 at 7am (America/New_York)", now=now,
                              max_ahead_s=7.5 * 86400) is None


def test_parse_reset_still_handles_the_refusal_form_unchanged():
    now = datetime(2026, 9, 4, 13, 0, tzinfo=timezone.utc)   # 09:00 EDT
    out = limits.parse_reset("resets 11:10am (America/New_York)", now=now)
    assert out == datetime(2026, 9, 4, 15, 10, tzinfo=timezone.utc)
```

Ensure the file's imports include `from herder import limits` and `from datetime import datetime, timezone`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest packages/herder/tests/test_limits.py -q -k "dated or per_call or refusal_form"`
Expected: FAIL — `parse_reset() got an unexpected keyword argument 'max_ahead_s'`, and the dated forms return `None`.

- [ ] **Step 3: Implement**

In `packages/herder/src/herder/limits.py`, add below `_RESET_RE`:

```python
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

# The /usage form: a date, an optional minute ("7am" is what the weekly line
# actually renders), then the same meridiem-and-zone tail as the refusal form.
# Tried FIRST because it is the more specific of the two; the time-only
# pattern cannot match it anyway, since "Sep" is not a digit.
_RESET_DATED_RE = re.compile(
    r"resets\s+([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2})\s+at\s+"
    r"(\d{1,2})(?::(\d{2}))?\s*([ap]m)\s*"
    r"\(([A-Za-z_]+(?:/[A-Za-z0-9_+-]+)*)\)", re.I)


def _hour24(hour12: str, meridiem: str) -> int:
    return int(hour12) % 12 + (12 if meridiem.lower() == "pm" else 0)


def _dated_target(m: re.Match, now: datetime) -> datetime | None:
    """The instant named by a dated clause, resolved to the next future year.

    The year is absent from the text, so it is inferred: this year if that
    lands in the future, else next. A date that has already passed therefore
    resolves a full year out, which no caller's bound admits - so a stale or
    clock-skewed date degrades to None rather than to a long sleep.
    """
    month_s, day_s, hour_s, minute_s, meridiem, zone_name = m.groups()
    month = _MONTHS.get(month_s[:3].lower())
    if month is None:
        return None
    try:
        tz = ZoneInfo(zone_name)
    except Exception:  # noqa: BLE001 - unknown zone must not crash the caller
        return None
    minute = int(minute_s) if minute_s else 0
    if not 0 <= minute <= 59:
        return None
    local = now.astimezone(tz)
    for year in (local.year, local.year + 1):
        try:
            target = datetime(year, month, int(day_s),
                              _hour24(hour_s, meridiem), minute, tzinfo=tz)
        except ValueError:      # e.g. Feb 29 in a non-leap year
            continue
        if target > local:
            return target
    return None
```

Then replace the body of `parse_reset` with:

```python
def parse_reset(text: str, now: datetime | None = None,
                max_ahead_s: float = MAX_RESET_AHEAD_S) -> datetime | None:
    """The UTC instant named by a `resets ...` clause, in either shape.

    Two forms are accepted: the refusal message's time-only
    `resets 11:10am (America/New_York)`, and /usage's dated
    `resets Sep 5 at 5:20pm (America/New_York)` (whose minutes are
    optional - the weekly line renders as `7am`). Both resolve to the next
    future occurrence in the zone the message names, which is not
    necessarily the caller's.

    `max_ahead_s` is per-call because the bound is a property of the WINDOW,
    not of the parser: a 5-hour reset is always within ~5 hours, a weekly one
    is legitimately up to seven days out. A single shared constant would
    either reject every valid weekly reading or let a mis-parsed session
    reset manufacture a week-long sleep.
    """
    now = now or datetime.now(timezone.utc)
    dated = _RESET_DATED_RE.search(text)
    if dated is not None:
        target = _dated_target(dated, now)
        if target is None:
            return None
    else:
        m = _RESET_RE.search(text)
        if not m:
            return None
        hour12, minute, meridiem, zone_name = m.groups()
        try:
            tz = ZoneInfo(zone_name)
        except Exception:  # noqa: BLE001 - see _dated_target
            return None
        if not 0 <= int(minute) <= 59:
            return None
        local = now.astimezone(tz)
        target = datetime.combine(local.date(),
                                  time(_hour24(hour12, meridiem), int(minute)),
                                  tzinfo=tz)
        if target <= local:
            target = datetime.combine(local.date() + timedelta(days=1),
                                      time(_hour24(hour12, meridiem), int(minute)),
                                      tzinfo=tz)
    out = target.astimezone(timezone.utc)
    if (out - now.astimezone(timezone.utc)).total_seconds() > max_ahead_s:
        return None
    return out
```

- [ ] **Step 4: Run the tests**

Run: `pytest packages/herder/tests/test_limits.py -q`
Expected: PASS, all of them — the pre-existing refusal-path tests included.

- [ ] **Step 5: Commit**

```bash
git add packages/herder/src/herder/limits.py packages/herder/tests/test_limits.py
git commit -m "feat(herder): parse the dated /usage reset form, bound per meter"
```

---

### Task 2: The usage reading and its parser (pure)

**Files:**
- Create: `packages/herder/src/herder/usage.py`
- Test: `packages/herder/tests/test_usage.py`

**Interfaces:**
- Consumes: `limits.parse_reset(text, now, max_ahead_s)` from Task 1.
- Produces: `usage.Meter(percent: int, resets_at: datetime | None)`, `usage.UsageReading(five_hour: Meter | None, seven_day: Meter | None, per_model: dict[str, Meter], fetched_at: datetime)`, `usage.parse_usage_text(text: str, now: datetime | None = None) -> UsageReading | None`, and the constants `usage.FIVE_HOUR_MAX_AHEAD_S`, `usage.SEVEN_DAY_MAX_AHEAD_S`, `usage.STALE_MARKER`.

- [ ] **Step 1: Write the failing tests**

Create `packages/herder/tests/test_usage.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest packages/herder/tests/test_usage.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'herder.usage'`.

- [ ] **Step 3: Implement**

Create `packages/herder/src/herder/usage.py`:

```python
"""Reading the account's live usage meters.

Deliberately separate from herder.limits. `limits` is about REFUSALS -
something has already gone wrong and the message is the evidence. This
module is about HEADROOM - nothing has gone wrong yet and the reading is a
measurement. Different lifetimes, different failure modes, different callers.

The source is `claude -p "/usage"`, a live GET /api/oauth/usage: measured
2026-09-05 on CLI 2.1.252 at num_turns 0, total_cost_usd 0, every token
count 0, ~0.5-3 s. It is NOT an inference call, so it may be taken at every
show boundary.

Deliberately NOT read: ~/.claude.json's cachedUsageUtilization. It is
write-throttled to five minutes, does not refresh when /usage runs, and was
measured on 2026-09-05 serving an ALREADY-EXPIRED window (23% against a
rolled-over window while the live read said 10%). It looks correct exactly
when someone is watching it and goes wrong during the unattended run pacing
exists for.
"""
import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone

from herder.limits import parse_reset

# Per-window bounds on how far ahead a reset may legitimately sit. See
# limits.parse_reset's max_ahead_s for why this is not one constant.
FIVE_HOUR_MAX_AHEAD_S = 5.5 * 3600
SEVEN_DAY_MAX_AHEAD_S = 7.5 * 86400

# When the fetch fails, /usage still exits 0 and prints cached numbers with
# this banner. An exit-code check alone would accept them.
STALE_MARKER = "Showing last-known usage"

_SESSION_RE = re.compile(r"^Current session:\s*(\d+)%\s*used(.*)$", re.M)
_WEEK_ALL_RE = re.compile(r"^Current week \(all models\):\s*(\d+)%\s*used(.*)$", re.M)
# The lookahead is load-bearing: without it this also matches the all-models
# line and reports a sub-meter named "all models" that does not exist.
_WEEK_MODEL_RE = re.compile(
    r"^Current week \((?!all models\))([^)]+)\):\s*(\d+)%\s*used(.*)$", re.M)


@dataclass(frozen=True)
class Meter:
    percent: int
    resets_at: datetime | None


@dataclass(frozen=True)
class UsageReading:
    five_hour: Meter | None
    seven_day: Meter | None
    per_model: dict[str, Meter] = field(default_factory=dict)
    fetched_at: datetime | None = None


def parse_usage_text(text: str, now: datetime | None = None) -> UsageReading | None:
    """A reading from /usage's prose, or None when it cannot be trusted.

    Never raises. Returns None on a stale banner, a missing session line, or
    anything else unrecognizable - a caller must not have to distinguish
    "no signal" from "bad signal", because it treats them identically.
    """
    now = now or datetime.now(timezone.utc)
    if not text or STALE_MARKER in text:
        return None
    m = _SESSION_RE.search(text)
    if not m:
        return None
    five = Meter(int(m.group(1)),
                 parse_reset(m.group(2), now=now, max_ahead_s=FIVE_HOUR_MAX_AHEAD_S))
    seven = None
    mw = _WEEK_ALL_RE.search(text)
    if mw:
        seven = Meter(int(mw.group(1)),
                      parse_reset(mw.group(2), now=now,
                                  max_ahead_s=SEVEN_DAY_MAX_AHEAD_S))
    per_model = {
        mm.group(1).strip(): Meter(int(mm.group(2)),
                                   parse_reset(mm.group(3), now=now,
                                               max_ahead_s=SEVEN_DAY_MAX_AHEAD_S))
        for mm in _WEEK_MODEL_RE.finditer(text)
    }
    return UsageReading(five_hour=five, seven_day=seven, per_model=per_model,
                        fetched_at=now)
```

- [ ] **Step 4: Run the tests**

Run: `pytest packages/herder/tests/test_usage.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add packages/herder/src/herder/usage.py packages/herder/tests/test_usage.py
git commit -m "feat(herder): parse the live /usage meters"
```

---

### Task 3: `read_usage` — the subprocess reader

**Files:**
- Modify: `packages/herder/src/herder/usage.py`
- Test: `packages/herder/tests/test_usage.py`

**Interfaces:**
- Consumes: `parse_usage_text` from Task 2; `claude_cli.ISOLATION_ARGS`, `claude_cli._subprocess_env`, `claude_cli._neutral_cwd`.
- Produces: `usage.read_usage(runner=None, now=None) -> UsageReading | None`, where `runner` is a zero-argument callable returning raw stdout (`str`) or `None`.

- [ ] **Step 1: Write the failing tests**

Append to `packages/herder/tests/test_usage.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest packages/herder/tests/test_usage.py -q -k read_usage`
Expected: FAIL with `AttributeError: module 'herder.usage' has no attribute 'read_usage'`.

- [ ] **Step 3: Implement**

Append to `packages/herder/src/herder/usage.py`:

```python
def _cli_runner(binary: str = "claude", timeout_s: int = 60):
    """Shell out to `claude -p "/usage"`, returning raw stdout or None.

    Uses the same isolation and neutral cwd as an ordinary headless call, so
    the operator's hooks, MCP servers and CLAUDE.md cannot alter the output.
    """
    from herder.claude_cli import ISOLATION_ARGS, _neutral_cwd, _subprocess_env
    cmd = [binary, "-p", "/usage", "--output-format", "json", *ISOLATION_ARGS]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout_s, env=_subprocess_env(),
                              cwd=_neutral_cwd())
    except (subprocess.SubprocessError, OSError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def read_usage(runner=None, now: datetime | None = None) -> UsageReading | None:
    """A live meter reading, or None when one cannot be had.

    `runner` is injected so tests never spawn a subprocess. Every failure -
    a missing binary, a non-zero exit, a malformed envelope, unrecognizable
    prose, a stale banner - collapses to None, because a caller cannot act
    differently on any of them.
    """
    runner = runner or _cli_runner
    try:
        raw = runner()
    except Exception:  # noqa: BLE001 - a reading is never worth a crash
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    text = data.get("result") if isinstance(data, dict) else None
    if not isinstance(text, str):
        return None
    return parse_usage_text(text, now=now)
```

- [ ] **Step 4: Run the tests**

Run: `pytest packages/herder/tests/test_usage.py -q`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add packages/herder/src/herder/usage.py packages/herder/tests/test_usage.py
git commit -m "feat(herder): read_usage, degrading to None on every failure"
```

---

### Task 4: `decide()` and the two ceilings

**Files:**
- Modify: `packages/llama/src/llama/pacing.py`
- Modify: `packages/llama/src/llama/config.py` (`PacingConfig`, `DEFAULT_CONFIG_TOML`)
- Test: `packages/llama/tests/test_pacing_decide.py` (create)

**Interfaces:**
- Consumes: `herder.usage.UsageReading`, `herder.usage.Meter`.
- Produces: `pacing.Proceed()`, `pacing.PauseUntil(when: datetime, scope: str, reason: str)`, `pacing.Progress(per_show_delta: float | None)`, `pacing.decide(now, reading, progress, opts) -> Proceed | PauseUntil`. `PaceOptions` gains `five_hour_ceiling: float` and `seven_day_ceiling: float`; `pace_options()` populates them from config.

- [ ] **Step 1: Write the failing tests**

Create `packages/llama/tests/test_pacing_decide.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest packages/llama/tests/test_pacing_decide.py -q`
Expected: FAIL — `module 'llama.pacing' has no attribute 'Proceed'`.

- [ ] **Step 3: Implement**

In `packages/llama/src/llama/config.py`, add to `PacingConfig` after `reset_skew`:

```python
    # The proactive gate's whole policy surface for each window. A run pauses
    # when the meter PLUS the projected next show would cross the ceiling.
    # 90 is "careful": it stops before the wall without leaving much unused.
    # Set lower (e.g. 70) to be "polite" and reserve headroom for interactive
    # work; there is deliberately no second `reserve` knob, which would be a
    # subtraction the reader has to perform.
    five_hour_ceiling: float = 90
    seven_day_ceiling: float = 90
```

In `DEFAULT_CONFIG_TOML`, append to the `[pacing]` block (after `reset_skew`):

```toml

# Pause when a meter plus the projected next show would cross these. 90 is
# careful - it stops before the wall. Lower them (e.g. 70) to reserve
# headroom for your own interactive sessions; the meter is account-wide.
five_hour_ceiling = 90
seven_day_ceiling = 90
```

In `packages/llama/src/llama/pacing.py`, add to `PaceOptions`:

```python
    five_hour_ceiling: float      # pause when the 5h meter + next show crosses this
    seven_day_ceiling: float      # same for the weekly meter; checked first
```

Extend `pace_options` to pass them, and add `no_pacing` so tests and callers share one construction path:

```python
def pace_options(config, wait: bool | None = None,
                 max_wait: str | None = None,
                 no_pacing: bool = False) -> PaceOptions:
    cfg = config.pacing
    return PaceOptions(
        enabled=cfg.enabled and not no_pacing,
        wait=cfg.wait if wait is None else wait,
        max_wait_s=parse_duration(max_wait or cfg.max_wait),
        unknown_reset_wait_s=parse_duration(cfg.unknown_reset_wait),
        reset_skew_s=parse_duration(cfg.reset_skew),
        five_hour_ceiling=cfg.five_hour_ceiling,
        seven_day_ceiling=cfg.seven_day_ceiling,
    )
```

Append the policy:

```python
@dataclass(frozen=True)
class Proceed:
    """Nothing in the way; run the next unit of work."""


@dataclass(frozen=True)
class PauseUntil:
    when: datetime
    scope: str
    reason: str


@dataclass(frozen=True)
class Progress:
    """Everything the policy knows about the run, as counters only.

    No clock, no IO - so the whole policy is a table test.
    """
    per_show_delta: float | None = None      # learned EWMA; None until observed


def _pause(meter, ceiling, scope, projected, now, opts):
    """A PauseUntil when this meter's projection crosses its ceiling, else None."""
    if meter is None or meter.percent + projected <= ceiling:
        return None
    when = (meter.resets_at + timedelta(seconds=opts.reset_skew_s)
            if meter.resets_at is not None
            else now + timedelta(seconds=opts.unknown_reset_wait_s))
    reason = (f"{'weekly' if scope == 'seven_day' else '5h'} window at "
              f"{meter.percent}%"
              + (f", est {projected:.1f}%/show" if projected else ""))
    return PauseUntil(when, scope, reason)


def decide(now: datetime, reading, progress: Progress,
           opts: PaceOptions) -> Proceed | PauseUntil:
    """Whether to start the next unit of work, or wait for a window to reset.

    Rules in priority order, first match wins:

    1. Weekly ceiling. Checked FIRST because a weekly exhaustion cannot be
       slept off at the 5-hour reset - resuming there would land in a window
       that is still empty.
    2. Session gate, on the PROJECTION rather than the bare percentage: that
       is what stops a run starting a show it cannot finish.
    3. Proceed.

    A missing reading proceeds rather than guessing. The reactive path
    (herder.limits.RateLimited, caught by the caller) remains the backstop,
    so a blind boundary costs one refused show, not a wrong multi-hour idle.
    """
    if not opts.enabled or reading is None:
        return Proceed()
    projected = progress.per_show_delta or 0.0
    return (_pause(reading.seven_day, opts.seven_day_ceiling, "seven_day",
                   projected, now, opts)
            or _pause(reading.five_hour, opts.five_hour_ceiling, "five_hour",
                      projected, now, opts)
            or Proceed())
```

Update `cli.py`'s `_pace` helper to use the new parameter rather than `replace`:

```python
def _pace(config, wait: bool | None, max_wait: str | None,
           no_pacing: bool) -> PaceOptions:
    """Resolve the pacing flags, failing on a bad --max-wait before the run
    starts rather than four shows in."""
    try:
        return pace_options(config, wait=wait, max_wait=max_wait,
                            no_pacing=no_pacing)
    except ValueError as e:
        raise typer.BadParameter(str(e)) from e
```

Remove the now-unused `replace` import from `cli.py` if nothing else uses it.

- [ ] **Step 4: Run the tests**

Run: `pytest packages/llama/tests/test_pacing_decide.py packages/llama/tests/test_config.py packages/llama/tests/test_pacing.py -q`
Expected: PASS. `test_config.py::test_default_config_template_matches_defaults` pins the TOML block against the model defaults, so a mismatch fails there.

- [ ] **Step 5: Commit**

```bash
git add packages/llama/src/llama/pacing.py packages/llama/src/llama/config.py \
        packages/llama/src/llama/cli.py packages/llama/tests/test_pacing_decide.py
git commit -m "feat(pacing): decide() over live meters, with two ceilings"
```

---

### Task 5: Learned per-show cost

**Files:**
- Create: `packages/llama/src/llama/pacing_state.py`
- Test: `packages/llama/tests/test_pacing_state.py` (create)

**Interfaces:**
- Consumes: `herder.usage.UsageReading`, `llama.locks.file_lock`, `llama.workspace.write_artifact`.
- Produces: `pacing_state.PacingState(per_show_delta: float | None, samples: int)`, `pacing_state.observe(before, after, state) -> PacingState`, `pacing_state.read_state(root: Path) -> PacingState`, `pacing_state.record(root: Path, before, after) -> PacingState`, `pacing_state.EWMA_ALPHA`.

- [ ] **Step 1: Write the failing tests**

Create `packages/llama/tests/test_pacing_state.py`:

```python
from datetime import datetime, timedelta, timezone

from herder.usage import Meter, UsageReading
from llama import pacing_state as ps

NOW = datetime(2026, 9, 5, 20, 0, tzinfo=timezone.utc)
RESET = NOW + timedelta(hours=2)
OTHER_RESET = NOW + timedelta(hours=4, minutes=59)


def _r(percent, reset=RESET):
    return UsageReading(five_hour=Meter(percent, reset), seven_day=None,
                        per_model={}, fetched_at=NOW)


def test_first_observation_seeds_the_estimate():
    out = ps.observe(_r(10), _r(14), ps.PacingState(None, 0))
    assert out.per_show_delta == 4.0
    assert out.samples == 1


def test_later_observations_are_smoothed():
    seeded = ps.PacingState(4.0, 1)
    out = ps.observe(_r(10), _r(20), seeded)
    expected = 4.0 + ps.EWMA_ALPHA * (10.0 - 4.0)
    assert out.per_show_delta == expected


def test_a_window_rollover_contributes_nothing():
    # resets_at changed, so the delta spans a reset and is meaningless.
    # Folding it in would drag the estimate toward zero -- an UNDER-estimate,
    # which is what walks a run into the wall.
    seeded = ps.PacingState(4.0, 3)
    assert ps.observe(_r(90), _r(2, OTHER_RESET), seeded) == seeded


def test_a_failed_reading_at_either_end_contributes_nothing():
    seeded = ps.PacingState(4.0, 3)
    assert ps.observe(None, _r(14), seeded) == seeded
    assert ps.observe(_r(10), None, seeded) == seeded
    assert ps.observe(_r(10), UsageReading(None, None, {}, NOW), seeded) == seeded


def test_a_negative_delta_contributes_nothing():
    seeded = ps.PacingState(4.0, 3)
    assert ps.observe(_r(20), _r(10), seeded) == seeded


def test_state_round_trips_through_disk(tmp_path):
    assert ps.read_state(tmp_path) == ps.PacingState(None, 0)
    out = ps.record(tmp_path, _r(10), _r(14))
    assert out.per_show_delta == 4.0
    assert ps.read_state(tmp_path) == out


def test_unreadable_state_degrades_to_empty(tmp_path):
    (tmp_path / "pacing-state.json").write_text("{ not json")
    assert ps.read_state(tmp_path) == ps.PacingState(None, 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest packages/llama/tests/test_pacing_state.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'llama.pacing_state'`.

- [ ] **Step 3: Implement**

Create `packages/llama/src/llama/pacing_state.py`:

```python
"""What a show costs, learned from the meter across show boundaries.

The reading taken before show N+1 minus the reading taken before show N is
exactly show N's cost. That is a cleaner attribution than any rate estimate
over time, and it is available for free because the meter read costs nothing.

Known bias, accepted: the meter is account-wide, so a run paced while the
operator works attributes their burn to llama and over-estimates. That
pauses EARLY, which is the safe direction. Do not try to correct it by
subtracting llama's own dollar spend - no dollars-to-percent conversion
exists (see the phase 2 spec's "Measured signals").
"""
import json
from dataclasses import dataclass
from pathlib import Path

from llama.locks import file_lock
from llama.workspace import write_artifact

STATE_NAME = "pacing-state.json"

# Weighted toward recent shows without letting one outlier swing the gate.
EWMA_ALPHA = 0.4


@dataclass(frozen=True)
class PacingState:
    per_show_delta: float | None = None
    samples: int = 0


def _five(reading):
    return getattr(reading, "five_hour", None) if reading is not None else None


def observe(before, after, state: PacingState) -> PacingState:
    """Fold one show boundary into the estimate, or decline to.

    A boundary contributes ONLY when both readings succeeded and `resets_at`
    is unchanged between them. A window rollover makes the delta negative or
    nonsensical; folding it in would drag the estimate toward zero, and an
    under-estimate is precisely what lets a run walk into the wall.
    """
    b, a = _five(before), _five(after)
    if b is None or a is None or b.resets_at != a.resets_at:
        return state
    delta = float(a.percent - b.percent)
    if delta < 0:
        return state
    if state.per_show_delta is None:
        return PacingState(delta, 1)
    smoothed = state.per_show_delta + EWMA_ALPHA * (delta - state.per_show_delta)
    return PacingState(smoothed, state.samples + 1)


def read_state(root: Path) -> PacingState:
    """The persisted estimate, or an empty one. Never raises."""
    try:
        data = json.loads((root / STATE_NAME).read_text())
        return PacingState(data.get("per_show_delta"), int(data.get("samples", 0)))
    except (OSError, ValueError, TypeError, AttributeError):
        return PacingState(None, 0)


def record(root: Path, before, after) -> PacingState:
    """Observe one boundary and persist the result.

    Read-modify-write on a workspace that is explicitly parallel-safe, so it
    takes the same advisory lock discipline as the ledger: two concurrent
    runs would otherwise each fold the other's burn into the shared estimate
    on a last-writer-wins race.
    """
    root.mkdir(parents=True, exist_ok=True)
    with file_lock(root / (STATE_NAME + ".lock")):
        state = observe(before, after, read_state(root))
        write_artifact(root / STATE_NAME, json.dumps(
            {"per_show_delta": state.per_show_delta, "samples": state.samples},
            indent=2))
        return state
```

- [ ] **Step 4: Run the tests**

Run: `pytest packages/llama/tests/test_pacing_state.py -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add packages/llama/src/llama/pacing_state.py packages/llama/tests/test_pacing_state.py
git commit -m "feat(pacing): learn per-show cost from meter deltas"
```

---

### Task 6: Close the run-level `RateLimited` escape

Phase 1's catch lives inside the per-show loop. `run_discover`, `run_search` and `run_winnow` execute before it, so a `RateLimited` raised there escapes `_execute`: exit 1, no session marker, no `paused` state. This task fixes that alone, with no proactive gate involved — it is independently valuable and independently reviewable.

**Files:**
- Modify: `packages/llama/src/llama/cli.py` (`_execute`)
- Test: `packages/llama/tests/test_pace_loop.py`

**Interfaces:**
- Consumes: `herder.limits.RateLimited`, `pacing.resume_at`, `sessions.mark_paused`.
- Produces: nothing new; `_execute` gains the behavior that a `RateLimited` from a run-level stage checkpoints and returns rather than propagating.

- [ ] **Step 1: Write the failing test**

`test_pace_loop.py` already has the harness: `_clock(monkeypatch)` freezes
`pacing._now`/`_sleep`, `_drive(tmp_path, monkeypatch, process, pids, *, pace, config)`
stubs the providers and calls `_execute`, and `NOW` is the frozen base instant.
`_drive` currently hard-codes `run_search`/`run_winnow` stubs, so first give it
two optional overrides (this is the only change to the existing helper):

```python
def _drive(tmp_path: Path, monkeypatch, process, pids, *,
           pace=None, config=None, winnow=None, search=None):
    ...
    monkeypatch.setattr(cli, "run_search", search or (lambda *a, **k: None))
    monkeypatch.setattr(cli, "run_winnow", winnow or (lambda *a, **k: entries))
```

Add `import json` to the file's imports, then append:

```python
def test_ratelimited_during_winnow_checkpoints_instead_of_exiting(tmp_path, monkeypatch):
    """Phase 1's stated gap: winnow runs BEFORE the per-show loop, so a limit
    there escaped _execute entirely -- exit 1, no marker, no resume_after.
    _drive returning normally is half the assertion."""
    _clock(monkeypatch)

    def _boom(*a, **k):
        raise RateLimited("You've hit your session limit", scope="five_hour",
                          resets_at=NOW + timedelta(hours=6))

    ws, seen = _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a"],
                      pace=pacing.pace_options(Config(), wait=False),
                      winnow=_boom)

    assert seen == []                                  # no show was reached
    assert iter_sessions(tmp_path)[0].state == STATE_PAUSED
    marker = json.loads(ws.session.read_text())
    assert marker["pause_scope"] == "five_hour"
    assert marker["resume_after"]                      # an instant, not None


def test_run_level_ratelimited_is_caught_before_herdererror(tmp_path, monkeypatch):
    """RateLimited subclasses HerderError. Ordered the other way this becomes
    an ordinary stage failure, so assert the PAUSED marker rather than merely
    that nothing propagated."""
    _clock(monkeypatch)

    def _boom(*a, **k):
        raise RateLimited("You've hit your session limit", scope="five_hour",
                          resets_at=None)

    ws, seen = _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a"],
                      pace=pacing.pace_options(Config(), wait=False),
                      search=_boom)

    assert iter_sessions(tmp_path)[0].state == STATE_PAUSED
```

`STATE_PAUSED` and `iter_sessions` are already imported at the top of the file.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest packages/llama/tests/test_pace_loop.py -q -k "winnow or before_herdererror"`
Expected: FAIL — `RateLimited` propagates out of `_execute`.

- [ ] **Step 3: Implement**

In `cli.py`, extract the checkpoint rendering that `_execute`'s pause loop already performs into a helper placed just above `_execute`:

```python
def _checkpoint_pause(ws, limited, pace, outcome=None, failures=None,
                      note: str | None = None, when=None) -> None:
    """Record a pause and tell the operator how to resume.

    Shared by the run-level stages and the per-show loop so the two cannot
    drift on what a paused session looks like on disk.

    `when` is precomputed by callers holding a `PauseUntil`, whose instant
    already includes reset_skew; letting resume_at recompute it would add the
    skew twice. RateLimited callers pass nothing and keep phase 1's behavior
    byte-for-byte.
    """
    when = when or resume_at(limited, pace)
    typer.echo(f"paused: {limited}", err=True)
    if note:
        typer.echo(f"  {note}")
    mark_paused(ws, outcome, failures or [], when.isoformat(),
                getattr(limited, "scope", None), str(limited))
    typer.echo(f"  resume with: llama run resume {ws.name}")
```

Wrap the three run-level stage calls. `run_discover` is already inside a conditional; the simplest correct shape is one try block around the whole discovery-through-winnow region of `_execute`. Locate the region beginning at the `artists = None` assignment and ending immediately after the `run_winnow(...)` call that produces `shortlist`, and wrap it:

```python
    try:
        ...   # existing artists / run_discover / run_search / run_winnow body
    except RateLimited as exc:
        # BEFORE any `except HerderError`: RateLimited subclasses it, and the
        # reverse ordering silently reverts this to an ordinary stage failure.
        if not pace.enabled:
            raise
        _checkpoint_pause(
            ws, exc, pace,
            note="limit hit before any show ran; resume re-runs the stage "
                 "that was interrupted")
        return
```

Note in a comment at that catch, so nobody mistakes it for cheap: `run_discover`/`run_search`/`run_winnow` gate on `should_run` at **whole-stage** granularity, so resuming re-runs the interrupted stage from the top and re-spends the `light_research` calls it had already made. This makes the run *recoverable*, not *cheap*; per-candidate artifacts are out of scope.

- [ ] **Step 4: Run the tests**

Run: `pytest packages/llama/tests/test_pace_loop.py -q`
Expected: PASS, including the pre-existing phase-1 pause tests.

- [ ] **Step 5: Commit**

```bash
git add packages/llama/src/llama/cli.py packages/llama/tests/test_pace_loop.py
git commit -m "fix(cli): a limit during interpret/search/winnow now checkpoints"
```

**Correction, post-review.** That commit subject is wrong in both directions and
is preserved only because the commit shipped under it. It names `interpret`,
which this task does **not** cover, and omits `discover`, which it does. What
landed covers exactly `run_discover`, `run_search` and `run_winnow` -- the three
stages inside `_execute`'s try block.

**Known gap: `run_interpret` is not covered.** A `RateLimited` there still exits
1 with no checkpoint. `run_interpret` is called at `cli.py:440` (in `get`,
before `_execute` is entered) and `cli.py:2556` (profile creation, scratch
workspace). A checkpoint there would be **unresumable**: `run_interpret` writes
`criteria.json` only on success (`stages/interpret.py:13`) and `run resume`
refuses a session without one (`cli.py:708-710`), so the query would exist only
in argv. Cost of leaving it: one LLM call with nothing written, `llama get`
only -- the `--profile` path never calls `run_interpret`. The confusing phrasing
originates in phase 1's spec, which wrote `` `interpret` (`run_discover`) ``
literally at `2026-09-04-usage-pacing-design.md:346-348`; note also that
`_PIPELINE_RUN_STAGES` (`cli.py:1186`) is a different triple that excludes
`discover`.

---

### Task T6b (FILED, NOT IMPLEMENTED): checkpoint a limit during `run_interpret`

**Status: UNBUILT. Do not implement as part of phase 2.** Filed so the gap above
is tracked rather than rediscovered.

Scope: `llama get` (`cli.py:440`), the profile-creation path (`cli.py:2556`),
and the `run approve` / `run resume` entry points, which must be able to pick up
whatever a checkpoint there leaves behind.

It is not a catch. It needs its own resumability design -- at minimum persisting
the raw query (and the explicit flags stamped onto criteria) at run-claim time
so `run resume` has something to re-interpret, plus a decision on what the
profile path's `TemporaryDirectory` scratch workspace should do, since it has no
run directory to checkpoint into at all. It needs its own tests.

---

### Task 7: Wire the proactive gate into `_execute`

**Files:**
- Modify: `packages/llama/src/llama/cli.py` (`_execute`)
- Test: `packages/llama/tests/test_pace_loop.py`

**Interfaces:**
- Consumes: `pacing.decide`, `pacing.Progress`, `pacing.PauseUntil`, `pacing_state.read_state`, `pacing_state.record`, `herder.usage.read_usage`.
- Produces: `_execute` gains a pre-flight gate, a before-each-show gate, and the delta measurement. No new public names.

- [ ] **Step 1: Write the failing tests**

**First, stop the whole suite from spawning the real CLI.** A default `Config()`
resolves to the `claude_cli` backend, so once the gate exists every test that
reaches `_execute` — `test_get_cmd.py`, `test_pipeline.py`, `test_redo_cmd.py`,
`test_sessions.py`, `test_run_namespace.py` and `test_pace_loop.py` — would shell
out to `claude -p "/usage"` once per gate call. That is a live subprocess from an
offline suite. Add an autouse fixture to `packages/llama/tests/conftest.py`,
beside the existing ambient-key fixtures:

```python
@pytest.fixture(autouse=True)
def _no_live_usage_meter(monkeypatch):
    """No test may spawn `claude -p "/usage"`.

    A default Config resolves to the claude_cli backend, so without this every
    test reaching _execute shells out to the real CLI once per gate -- slow,
    non-deterministic, and a network call from a suite contracted to be
    offline. Tests that want a reading override this with their own
    monkeypatch, which runs after the autouse fixture.
    """
    import llama.cli as cli
    monkeypatch.setattr(cli, "read_usage", lambda *a, **kw: None, raising=False)
```

`raising=False` so the fixture is harmless before Task 7 adds the import.

Then append to `packages/llama/tests/test_pace_loop.py` — add
`from llama.config import LLMTaskConfig` to its imports first:

```python
def _reading(five=10, seven=7):
    from herder.usage import Meter, UsageReading
    return UsageReading(five_hour=Meter(five, NOW + timedelta(hours=2)),
                        seven_day=Meter(seven, NOW + timedelta(days=3)),
                        per_model={}, fetched_at=NOW)


def test_preflight_gate_pauses_before_any_stage_runs(tmp_path, monkeypatch):
    """The opening burst is the expensive place to pause -- winnow writes its
    shortlist only on success -- so the gate must fire BEFORE run_search."""
    _clock(monkeypatch)
    monkeypatch.setattr(cli, "read_usage", lambda *a, **kw: _reading(five=99))
    searched = []

    ws, seen = _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a"],
                      pace=pacing.pace_options(Config(), wait=False),
                      search=lambda *a, **k: searched.append(1))

    assert searched == []                     # never entered the burst
    assert seen == []
    assert iter_sessions(tmp_path)[0].state == STATE_PAUSED


def test_per_show_gate_stops_between_shows(tmp_path, monkeypatch):
    """Reading order: pre-flight, before-a, after-a (the delta), before-b.
    The fourth read is over the ceiling, so 'a' is packaged and 'b' is not."""
    _clock(monkeypatch)
    calls = {"n": 0}

    def _read(*a, **kw):
        calls["n"] += 1
        return _reading(five=5 if calls["n"] <= 3 else 99)

    monkeypatch.setattr(cli, "read_usage", _read)
    ws, seen = _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a", "b"],
                      pace=pacing.pace_options(Config(), wait=False))

    assert seen == ["a"]
    assert iter_sessions(tmp_path)[0].state == STATE_PAUSED


def test_gate_is_skipped_entirely_on_a_non_claude_cli_backend(tmp_path, monkeypatch):
    """The fake backend has no window; reading a meter for it would be both
    meaningless and non-deterministic in the offline suite."""
    _clock(monkeypatch)
    monkeypatch.setattr(cli, "read_usage",
                        lambda *a, **kw: pytest.fail("meter read on a fake backend"))
    cfg = Config(root=tmp_path, llm={"default": LLMTaskConfig(backend="fake")})

    ws, seen = _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a"],
                      pace=pacing.pace_options(Config()), config=cfg)

    assert seen == ["a"]


def test_a_preflight_pause_exits_zero_like_every_other_pause(tmp_path, monkeypatch):
    """R20's resolution: a limit before any show ran is NOT a distinct failure
    signal. _execute returns normally; the session lands on the attention list."""
    _clock(monkeypatch)
    monkeypatch.setattr(cli, "read_usage", lambda *a, **kw: _reading(five=99))
    ws, seen = _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a"],
                      pace=pacing.pace_options(Config(), wait=False))
    assert iter_sessions(tmp_path)[0].state == STATE_PAUSED
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest packages/llama/tests/test_pace_loop.py -q -k "preflight or per_show_gate or non_claude_cli"`
Expected: FAIL — no gate exists, so the stages run and the session ends `complete`.

- [ ] **Step 3: Implement**

At the top of `cli.py`, add the imports, and extend the existing
`from llama.pacing import (...)` line so every new symbol is available
unqualified (the file already imports `PaceOptions`, `duration_arg`,
`format_delta`, `pace_options`, `resume_at`, `sleep_until`):

```python
from herder.usage import read_usage
from llama import pacing_state
from llama.pacing import (PauseUntil, Proceed, Progress, decide,
                          shows_that_fit)   # shows_that_fit lands in Task 8
```

Import `shows_that_fit` only once Task 8 defines it; adding the name earlier
makes `cli.py` fail to import.

Add a helper above `_execute`:

```python
def _meter(config):
    """A live meter reading, or None when there is no window to read.

    Gated on the backend because only claude_cli has an account window: the
    fake backend must never read one (it would make the offline suite
    non-deterministic) and openrouter has no /usage equivalent.
    """
    if config.llm_for("default").backend != "claude_cli":
        return None
    return read_usage()
```

Inside `_execute`, immediately after `pace` is resolved:

```python
    state = pacing_state.read_state(config.root)
    reading = _meter(config)
    verdict = decide(_pacing._now(), reading, Progress(state.per_show_delta),
                     pace)
    if isinstance(verdict, PauseUntil):
        _checkpoint_pause(ws, verdict, pace,
                          note="nothing has run yet; resume when the window "
                               "resets")
        return
```

Give `PauseUntil` a `__str__` returning `self.reason`, so `_checkpoint_pause`
renders it the same way it renders a `RateLimited`. Pass `when=verdict.when` at
every `PauseUntil` call site (Task 6 already gave `_checkpoint_pause` the
parameter); `RateLimited` call sites pass nothing.

Before each show, inside the `for idx, entry in enumerate(pending)` loop and **before** taking the show lock:

```python
            reading_before = _meter(config)
            verdict = decide(_pacing._now(), reading_before,
                             Progress(state.per_show_delta), pace)
            if isinstance(verdict, PauseUntil):
                limited = verdict
                unprocessed.extend(pending[idx:])
                break
```

After `_process(entry)` returns without setting `limited`, fold the boundary in:

```python
            if not limited:
                state = pacing_state.record(config.root, reading_before,
                                            _meter(config))
```

The existing pause-rendering block below already handles `limited` — sleeping when it fits under `max_wait`, else checkpointing — and works unchanged for a `PauseUntil`, because it reads only `resume_at(limited, pace)`, `str(limited)` and `limited.scope`. Pass `when=limited.when` when `limited` is a `PauseUntil`.

- [ ] **Step 4: Run the tests**

Run: `pytest packages/llama/tests/test_pace_loop.py packages/llama/tests/test_get_cmd.py -q`
Expected: PASS. Then the full suite: `pytest -q` — expect 1742 plus the new tests, nothing broken.

- [ ] **Step 5: Commit**

```bash
git add packages/llama/src/llama/cli.py packages/llama/src/llama/pacing.py \
        packages/llama/tests/test_pace_loop.py
git commit -m "feat(cli): proactive pacing gate at run and show boundaries"
```

---

### Task T7b (FILED, NOT IMPLEMENTED): let the run-level pause sites honour `--wait`

**Status: UNBUILT. Do not implement as part of phase 2.** Filed so the gap is
tracked rather than rediscovered, and because it is not Task 7's alone.

Both run-level pause sites checkpoint and exit 0 without ever sleeping,
whatever `--wait` and `--max-wait` say: the pre-flight gate (Task 7,
`cli.py:236-242`) and the reactive catch around discover/search/winnow
(Task 6, `cli.py:300-304`). Only the show loop sleeps. That is what each task
was asked to build, and the two are at least consistent with each other -- but
it is a `--wait` contract break relative to phase 1: `llama get --wait` started
twenty minutes before a reset used to enter the run, hit the limit reactively
at a show, sleep through it and finish. It now exits immediately having done
nothing, and an unattended invocation needs a manual `llama run resume`.

Scope: **both** sites, together. Doing one without the other replaces a
symmetry with a worse asymmetry. It is not a flag lookup -- sleeping at a
run-level site means re-deciding after the nap (the meter must be re-read; the
reset may have moved) and carrying the no-progress guard, which today lives
only in the show loop. `_checkpoint_pause` has no sleep branch by design, so
this is a new shared pause renderer, not a parameter.

Fold in while there: **the deferred second pass is ungated.** Shows another run
held the lock on are processed in the `for idx, entry in enumerate(deferred)`
pass with no gate and no boundary measurement, and that pass takes a
**blocking** lock (`cli.py:422`) -- so it can sit for an arbitrary time and
then process on a window whose last gate reading is stale by that whole wait.
The reactive `RateLimited` catch is still the backstop there, so the cost is
one refused show rather than a wrong idle.

---

### Task 8: `llama pacing` and the run-start forecast

**Files:**
- Modify: `packages/llama/src/llama/cli.py`
- Test: `packages/llama/tests/test_cli_commands.py`

**Interfaces:**
- Consumes: `_meter`, `pacing_state.read_state`, `pacing.decide`, `pacing.format_delta`.
- Produces: `pacing.shows_that_fit(reading, per_show_delta, ceiling) -> int | None`; a `llama pacing` Typer command.

- [ ] **Step 1: Write the failing tests**

Add to `packages/llama/tests/test_pacing_decide.py`:

```python
def test_shows_that_fit_uses_the_ceiling_not_a_hundred():
    # 90 - 65 = 25 points of usable headroom at 4.2%/show.
    assert pacing.shows_that_fit(_reading(five=65), 4.2, 90) == 5


def test_shows_that_fit_is_unknown_without_an_estimate():
    assert pacing.shows_that_fit(_reading(five=65), None, 90) is None
    assert pacing.shows_that_fit(None, 4.2, 90) is None


def test_shows_that_fit_floors_at_zero_when_already_over():
    assert pacing.shows_that_fit(_reading(five=95), 4.2, 90) == 0
```

Add to `packages/llama/tests/test_cli_commands.py` (follow the file's existing `CliRunner` conventions):

```python
def _usage_reading(five, seven):
    from datetime import datetime, timedelta, timezone
    from herder.usage import Meter, UsageReading
    now = datetime(2026, 9, 5, 20, 0, tzinfo=timezone.utc)
    return UsageReading(five_hour=Meter(five, now + timedelta(hours=2)),
                        seven_day=Meter(seven, now + timedelta(days=3)),
                        per_model={}, fetched_at=now)


def _cfg_file(tmp_path):
    """A config pointing at tmp_path, so the command never reads the real
    ~/.llama/config.toml. `cli_invoke` lives in conftest.py."""
    path = tmp_path / "config.toml"
    path.write_text(f'root = "{tmp_path}"\n')
    return path


def test_pacing_command_reports_meters_and_forecast(monkeypatch, tmp_path):
    from llama import cli as cli_mod
    monkeypatch.setattr(cli_mod, "read_usage", lambda *a, **kw: _usage_reading(65, 7))
    result = cli_invoke(_cfg_file(tmp_path), "pacing")
    assert result.exit_code == 0
    assert "5h 65%" in result.stdout
    assert "weekly 7%" in result.stdout


def test_pacing_command_says_so_when_the_meter_cannot_be_read(monkeypatch, tmp_path):
    from llama import cli as cli_mod
    monkeypatch.setattr(cli_mod, "read_usage", lambda *a, **kw: None)
    result = cli_invoke(_cfg_file(tmp_path), "pacing")
    assert result.exit_code == 0
    assert "unavailable" in result.stdout
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest packages/llama/tests/test_pacing_decide.py packages/llama/tests/test_cli_commands.py -q -k "fit or pacing_command"`
Expected: FAIL — `shows_that_fit` undefined, `No such command 'pacing'`.

- [ ] **Step 3: Implement**

In `pacing.py`:

```python
def shows_that_fit(reading, per_show_delta: float | None,
                   ceiling: float) -> int | None:
    """How many more shows the session window has room for, or None.

    None means "no estimate", which is a different thing from zero and must
    render differently - a run that has learned nothing yet has not been
    told it cannot proceed.
    """
    if reading is None or reading.five_hour is None or not per_show_delta:
        return None
    return max(0, int((ceiling - reading.five_hour.percent) // per_show_delta))
```

In `cli.py`, add a formatter and the command:

```python
def _pacing_line(reading, state, pace) -> str:
    """The one-line meter summary printed at run start and by `llama pacing`."""
    if reading is None or reading.five_hour is None:
        return "usage read unavailable — pacing on limit errors only"
    parts = [f"5h {reading.five_hour.percent}%"]
    if reading.seven_day is not None:
        parts.append(f"weekly {reading.seven_day.percent}%")
    if state.per_show_delta:
        parts.append(f"est {state.per_show_delta:.1f}%/show")
    fits = shows_that_fit(reading, state.per_show_delta, pace.five_hour_ceiling)
    if fits is not None and reading.five_hour.resets_at is not None:
        parts.append(f"~{fits} fit before "
                     f"{reading.five_hour.resets_at.astimezone():%H:%M}")
    return "pacing: " + " · ".join(parts)


@app.command()
def pacing() -> None:                       # shadows nothing: cli.py imports the
                                            # module as `_pacing`, deliberately
    """Show the usage meters, the learned per-show cost, and what fits.

    Read-only, in the shape of `llama pipeline`. Run it before launching to
    decide whether a run fits in the current window.
    """
    config = load_config(_config_path)      # the callback's --config, not the default
    pace = pace_options(config)
    state = pacing_state.read_state(config.root)
    reading = _meter(config)
    typer.echo(_pacing_line(reading, state, pace))
    if reading is None:
        return
    verdict = decide(_pacing._now(), reading, Progress(state.per_show_delta), pace)
    typer.echo("would proceed" if isinstance(verdict, Proceed)
               else f"would pause: {verdict.reason}")
```

Print `_pacing_line(...)` once in `_execute`, immediately after the pre-flight verdict returns `Proceed`. When `count` exceeds the forecast, append the consequence:

```python
    line = _pacing_line(reading, state, pace)
    fits = shows_that_fit(reading, state.per_show_delta, pace.five_hour_ceiling)
    if fits is not None and fits < count:
        line += f"; the remaining {count - fits} pause until the reset"
    typer.echo(line)
```

Do **not** reduce `count` — it feeds `choose_entries`' artist and year caps, so cutting it changes *which* shows are picked.

- [ ] **Step 4: Run the tests**

Run: `pytest packages/llama/tests/test_pacing_decide.py packages/llama/tests/test_cli_commands.py -q`
Expected: PASS.

- [ ] **Step 5: Update the docs and commit**

Add `llama pacing` to the command list in `CLAUDE.md` under "Run (llama, acquisition)", one clause, matching the existing style.

```bash
git add packages/llama/src/llama/cli.py packages/llama/src/llama/pacing.py \
        packages/llama/tests/ CLAUDE.md
git commit -m "feat(cli): llama pacing and the run-start forecast"
```

---

### Task 9: Mutation pass

Per the project's "green suite is not pinned" lesson, four constraints must be shown load-bearing by mutation, not merely covered by a passing test. Each is a one-line change a loosely written test would keep passing.

**Files:**
- Modify: whichever test file fails to catch a mutation (only if a mutation survives)
- Test: the whole suite

**Interfaces:**
- Consumes: everything from Tasks 1–8.
- Produces: no production code changes unless a mutation survives.

- [ ] **Step 1: Mutation 1 — the per-meter reset bound**

Change `usage.SEVEN_DAY_MAX_AHEAD_S` from `7.5 * 86400` to `5.5 * 3600`.
Run: `pytest packages/herder/tests/test_usage.py packages/herder/tests/test_limits.py -q`
Expected: **RED** — `test_weekly_reset_uses_the_weekly_bound_not_the_session_one` and `test_parse_reset_bound_is_per_call_not_global` fail.
Restore the value.

- [ ] **Step 2: Mutation 2 — the EWMA rollover guard**

In `pacing_state.observe`, delete `or b.resets_at != a.resets_at` from the guard.
Run: `pytest packages/llama/tests/test_pacing_state.py -q`
Expected: **RED** — `test_a_window_rollover_contributes_nothing` fails.
Restore.

- [ ] **Step 3: Mutation 3 — the stale-usage marker**

In `usage.parse_usage_text`, delete `or STALE_MARKER in text`.
Run: `pytest packages/herder/tests/test_usage.py -q`
Expected: **RED** — `test_stale_marker_is_a_failed_read_not_a_number` fails.
Restore.

- [ ] **Step 4: Mutation 4 — the run-level catch ordering**

In `_execute`, move the `except RateLimited` arm added in Task 6 to sit *after* an `except HerderError` arm (add one if the block has none, catching and reporting as a stage failure).
Run: `pytest packages/llama/tests/test_pace_loop.py -q`
Expected: **RED** — `test_run_level_ratelimited_is_caught_before_herdererror` fails.
Restore.

- [ ] **Step 5: If any mutation stayed GREEN, strengthen the test**

A surviving mutation means the constraint is not pinned. Write a test that fails under it, confirm it fails, restore, confirm it passes. Do not proceed until all four go red.

- [ ] **Step 6: Full suite and commit**

Run: `pytest -q`
Expected: PASS, 1742 baseline plus the new tests.

```bash
git add -A
git commit -m "test(pacing): pin the four phase-2 constraints by mutation"
```

---

## Notes for the executor

- **The four constants** (`FIVE_HOUR_MAX_AHEAD_S`, `SEVEN_DAY_MAX_AHEAD_S`, `EWMA_ALPHA`, the two ceilings) are policy, not tuning targets. Do not sweep them.
- **Do not unify `_meter` with the provider construction in `pipeline.make_providers`.** The meter read is not an LLM call and must not go through the tier/model resolution ladder.
- **`herder` must not import from `llama`** — enforced by `packages/herder/tests/test_no_llama_imports.py` and `packages/emcee/tests/test_no_llama_imports.py`.
- If a task's test needs a workspace fixture that `test_pace_loop.py` does not already have, add it to that file rather than to `conftest.py`; the phase-1 pause tests live there and the helpers should stay beside them.
