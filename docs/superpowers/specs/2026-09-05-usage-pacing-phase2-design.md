# Usage pacing, phase 2 — design

Status: designed, not implemented.
Date: 2026-09-05.
Supersedes the proactive half of
`docs/superpowers/specs/2026-09-04-usage-pacing-design.md` (phase 1), whose
reactive half is implemented and unchanged by this document.

## Problem

Phase 1 made a run survive a usage-window refusal: `herder.limits` classifies
the refusal, parses the reset instant out of its text, and `_execute` pauses at
the show boundary and resumes for free. That is the *reactive* half, and it only
ever acts after the backend has already said no.

Three things are left undone, and they are the whole of phase 2:

- **A run cannot see the wall coming.** There is no proactive gate, so llama
  always discovers the limit by being refused. The refusal costs a
  partially-spent show, and the operator learns the window was nearly empty only
  once it is empty.
- **A limit during `discover`, `search` or `winnow` loses the run.** Phase 1's
  catch is inside the per-show loop. `run_discover`, `run_search` and
  `run_winnow` all execute before it, so a `RateLimited` raised there propagates
  out of `_execute`: exit 1, no session marker, no `paused` state, no
  `resume_after`. The operator sees a failure, not a pause. This is stated
  explicitly as a boundary in the phase-1 spec (amendment R22).

  **These three stages, and only these three.** The phase-1 spec wrote
  `` `interpret` (`run_discover`) `` literally
  (`2026-09-04-usage-pacing-design.md:346-348`), which is where the recurring
  "interpret/search/winnow" phrasing comes from -- but `interpret` and
  `discover` are different stages, and `cli.py`'s module-level
`_PIPELINE_RUN_STAGES` is
  a third, different triple that excludes `discover` altogether. Read the call
  sites, not the phrase.

- **There is no way to plan a run against the window.** The operator times runs
  around available capacity by hand, with no answer to "will 13 shows fit before
  the reset?"

### Known gap: `run_interpret` is not covered

A `RateLimited` raised by `run_interpret` still exits 1 with no checkpoint, and
phase 2 deliberately leaves it that way. `run_interpret` is called at
`cli._get_query` (the `get` command's query-mode helper, **before** `_execute`
is entered) and in `cli.profile_add` (the profile-creation path, against a
scratch workspace in a `TemporaryDirectory`). Wrapping it would not produce a resumable run: it writes
`criteria.json` only on success (`stages/interpret.py:13`), and `run resume`
refuses a session that has no `criteria.json` (the `ws.criteria.exists()`
guard at the top of `cli.run_resume`), so a
checkpoint there would park a session that cannot be resumed -- the query exists
only in argv. Making it resumable is new design (persist the raw query at run
claim time), not a catch.

The cost of leaving it is one LLM call with nothing written, on `llama get`
only: the profile path (`--profile`) reads stored criteria and never calls
`run_interpret` at all. See **T6b** in the plan, filed and unbuilt.

## What changed since phase 1: the signal

Phase 1's spec built its proactive half on `~/.claude.json` →
`cachedUsageUtilization`, an undocumented internal of another tool, and spent
considerable design on a staleness ladder because that cache is refreshed only
periodically. **That was the wrong source, and the right one is both simpler and
free.**

Measured 2026-09-05 against Claude Code 2.1.252:

```
$ claude -p "/usage"
You are currently using your subscription to power your Claude Code usage

Current session: 10% used · resets Sep 5 at 5:20pm (America/New_York)
Current week (all models): 7% used · resets Sep 12 at 7am (America/New_York)
Current week (Fable): 0% used

What's contributing to your limits usage?
... (analytics prose, ignored)
```

`claude -p "/usage" --output-format json` returns an ordinary result envelope
whose `result` field is that prose string, with:

```
num_turns: 0, total_cost_usd: 0, duration_ms: 470,
input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0
```

It is a live `GET /api/oauth/usage`, not an inference call. **Zero tokens,
sub-second to ~3 s, works with no session open, and returns all three meters at
once.** It uses the same OAuth the `claude_cli` backend already relies on, so it
needs no new credentials.

**The cache is not merely stale — it can serve an expired window.** At 04:16 EDT
the cache read `five_hour: 23%, resets 2026-09-05T11:09:59Z` while the live read
returned `10%, resets 21:19:59Z`. Those are different windows; the cache was
still reporting one that had rolled over. By 04:19 an interactive session had
refreshed it to `9% / 21:19:59Z`. That is the trap: **the cache looks correct
precisely when someone is sitting there watching it**, and goes wrong during the
unattended run that pacing exists for. The `usage-pacing` skill records the same
class of failure independently (2026-08-24: a live 14% beside a cached 10% four
minutes old) and states that the cache is write-throttled to five minutes and
does **not** refresh when `/usage` runs.

Consequences for the design, all simplifications:

- `read_usage_snapshot` and the `~/.claude.json` reader are **not built**.
- `trust_age` and the staleness degradation ladder are **not built**. A reading
  can be taken fresh at any boundary for zero tokens, so the degradation case
  narrows from "this number is 40 minutes old" to "the read failed".
- The percent rules become genuinely load-bearing for unattended runs, rather
  than self-disabling half an hour in.
- `UsageMeter` (per-call `total_cost_usd` capture) is **not built**. It existed
  only as a *relative* per-show weight, because no dollars-to-percent conversion
  is available. A free direct percent reading at both ends of a show boundary
  measures the delta directly.

## Goals

- A long run pauses **before** exhausting the window and resumes after the
  reset, without ever being refused.
- A limit raised anywhere on the `_execute` path checkpoints and resumes, rather
  than exiting 1.
- The operator can ask, before launching, how much of a run fits in the current
  window.
- Offline suite stays deterministic; no wall-clock reads, no real `$HOME`, no
  subprocess spawns in tests.

## Non-goals

- **`openrouter` pacing.** `openrouter.py:37` raises a plain `HerderError` on any
  non-200, so an HTTP 429 is still retried as transport noise and then fails the
  show. openrouter has no `/usage` equivalent and none of this work transfers.
  Ruled out deliberately on 2026-09-05: openrouter use is rare and must remain
  *possible*, not paced. The boundary stays documented and unfixed.
- **A burn-rate history log** in the style of `~/.claude/skills/usage-pacing/burnrate.sh`.
  That tool derives a rate over time and attributes it across sessions. llama gets
  cleaner attribution for free by measuring across its own show boundaries. If the
  per-show estimate proves unreliable in practice, this is the thing to add — against
  evidence, not in advance.
- **Cheap resume of a partially-completed `winnow`.** See "Integration".
- **Shrinking `count` to fit the window.** `count` feeds `choose_entries`' artist
  and year distribution caps, so cutting it changes *which* shows are picked, not
  just how many. The forecast warns; it never shrinks.
- Mid-stage pausing. Decisions happen at run and show boundaries only, as in
  phase 1.

## Architecture

### `herder/usage.py` (new)

Deliberately separate from `herder/limits.py`. `limits` is about **refusals** —
something has already gone wrong, and the message is the evidence. `usage` is
about **headroom** — nothing has gone wrong yet, and the reading is a
measurement. Different lifetimes, different failure modes, different callers.

```
Meter:        percent: int, resets_at: datetime | None
UsageReading: five_hour: Meter | None
              seven_day: Meter | None
              per_model: dict[str, Meter]
              fetched_at: datetime

read_usage(runner, now) -> UsageReading | None
```

`runner` is injected, so tests never spawn a subprocess. `read_usage` **never
raises**. It returns `None` on:

- non-zero exit from `claude -p`,
- unparseable or missing `result`,
- absence of a `Current session:` line,
- **presence of `Showing last-known usage`** — the documented tell that the
  fetch failed and cached data is being substituted. This is the only case where
  the command *succeeds* and the number is a lie, and it is the reason a bare
  "did it exit 0" check is insufficient.

**Parsing.** Line-based, defensive, and tolerant of the analytics prose that
follows. The three recognized lines are `Current session:`, `Current week (all
models):`, and `Current week (<model>):` — the last captured into `per_model`
under an arbitrary key, because the per-model sub-meter is account-dependent
(this account shows `Fable`; an account whose high tier is Opus would show
something else). Everything from the blank line before `What's contributing`
onward is ignored.

**Reset parsing extends `limits.parse_reset`.** The `/usage` form carries a date
(`Sep 5 at 5:19pm (America/New_York)`); the refusal form carries only a time
(`11:10am (America/New_York)`). Same U+00B7 separator, same IANA zone, same
`zoneinfo` resolution. One parser, two accepted shapes.

**The reset sanity bound becomes per-meter.** `limits.MAX_RESET_AHEAD_S`
(`limits.py:26`) is a single 5.5-hour constant, correct for a session-limit
refusal and wrong for a weekly reading, which is legitimately up to seven days
out. The bound moves onto the meter: 5.5 h for `five_hour`, 7.5 d for
`seven_day`. The existing refusal path keeps the value it has today. A shared
constant would reject every valid weekly reading, and widening the shared
constant to 7.5 d would let a mis-parsed session reset manufacture a week-long
sleep — which is exactly what the bound exists to prevent.

**Reset rendering is unstable to the minute.** `21:19:59Z` was observed printed
as both `5:20pm` and `5:19pm` within five minutes. Nothing may depend on the
reset to better than a minute; `reset_skew` (default 2 m) already absorbs it.

**Backend gating.** Meaningful only on `claude_cli`. Under `openrouter` or
`fake`, `read_usage` is never called, the proactive rules never fire, and the
offline suite stays deterministic — the same discipline phase 1 uses.

### `llama/pacing.py` (extended)

A pure `decide()` joins the existing duration, sleep and `PaceOptions` helpers.
IO stays in the caller, matching `siblings.py` and `structure.py`.

```
decide(now, reading, progress, opts) -> Proceed | PauseUntil(when, scope, reason)
```

`progress` is counters only — shows done, shows remaining, learned per-show
delta. No clock reads, no IO, so the whole policy is a table test.

## Policy

Rules in priority order; first match wins.

1. **Weekly ceiling.** `seven_day + projected_next_show > seven_day_ceiling` →
   `PauseUntil(seven_day.resets_at)`. Days out, so it exceeds `max_wait` and
   checkpoints rather than sleeping. That is correct: nothing is gained by
   idling for four days.
2. **Session gate.** `five_hour + projected_next_show > five_hour_ceiling` →
   `PauseUntil(five_hour.resets_at + reset_skew)`. Always within five hours, so
   it fits under the default six-hour `max_wait` and genuinely sleeps and
   resumes. This is the rule the feature exists for.
3. Otherwise `Proceed`.

Gating on the **projection** rather than the bare percentage is what stops a run
starting a show it cannot finish. Before any delta has been learned, both rules
degrade to gating on the bare percentage.

### The learned per-show delta

An EWMA over `five_hour` deltas measured across llama's own show boundaries: a
reading taken **after** a show minus the one taken **before** it is exactly that
show's cost. Persisted workspace-level in `pacing-state.json`, so a fresh run
starts calibrated rather than blind.

Before/after, and deliberately not before-N/before-N+1: the gate's own meter
read and the `pacing-state.json` write both happen *between* shows, so a
boundary spanning one show's start to the next show's start would fold them
into every sample — a constant with nothing to do with the show it is
attributed to. The cost is a second meter read per show, which is not an
inference call.

**A boundary contributes only when both readings succeeded and `resets_at` is
unchanged between them.** A window rollover makes the delta negative and
meaningless; folding it in would drag the estimate toward zero, which fails in
the dangerous direction — an under-estimate is what lets a run walk into the
wall. This guard is on the mutation list.

`pacing-state.json` is a read-modify-write on a workspace that is explicitly
parallel-safe, so it takes a short `file_lock` in the same discipline as the
ledger lock (`locks.py`). Two concurrent runs would otherwise each fold the
other's burn into the shared EWMA on a last-writer-wins race.

### Stated trade: account-wide attribution

The meter is account-wide and cannot separate llama's burn from the operator's
concurrent interactive sessions. A run paced while the operator works will
attribute that burn to llama and pause **early**.

This is correct for the primary goal (never hit the wall) and wrong for the
secondary one (deliberately driving the window to the line when nothing else is
running). The escape hatches are `--no-pacing` and a raised or lowered
`five_hour_ceiling`; the bias is not to be "fixed" by subtracting llama's own
dollar spend, because the dollars-to-percent conversion does not exist.

### One ceiling, not two knobs

`five_hour_ceiling` (default 90) is the whole policy surface for the session
window. "Careful" is the default: with a per-show delta around 4-5 % and
generous estimate error, 90 stops before the wall without leaving much unused.
"Polite" — deliberately reserving headroom for the operator's own work — is the
same knob set lower, e.g. 70, which holds back roughly three shows' worth.

A separate `reserve` field was considered and rejected: `ceiling = 90,
reserve = 20` would mean an effective ceiling of 70, which is two ways to write
one number and a subtraction the reader has to perform.

## Integration

Four touch points in `_execute` (`cli.py`), two of them new, one of them
existing and unchanged.

1. **Pre-flight**, after criteria resolution and before `run_discover`. New.
   This is the most valuable place for a conservative gate, for a reason the
   resume machinery makes concrete: `run_winnow` calls `light_research` once per
   shortlisted candidate and `score_reviews` in batches of five, and writes
   `ws.shortlist` only on success. `run_discover`, `run_search` and `run_winnow`
   all gate on `should_run` at **whole-stage** granularity, so a pause *inside*
   winnow discards every call already made and resume re-runs it from the top.
   The opening burst is the one stretch of a run where pausing is genuinely
   expensive, so the fix is to decide before entering it.

2. **A reactive catch around the three run-level stages.** New. `except
   RateLimited` wrapping `run_discover` / `run_search` / `run_winnow`, converting
   to the same `PauseUntil` a boundary check produces. This closes phase 1's
   stated exit-1 gap.

   **Honest limit:** this makes the run *recoverable*, not *cheap*. Resume
   re-spends whatever winnow had already done. Cheap resume would need
   per-candidate artifacts, which is separate work and deliberately not folded
   in here.

3. **Before each show**, at the top of the `for entry in chosen` loop. New —
   phase 1 has only the reactive catch, not a boundary check. This is where the
   proactive gate does its main work and where the delta measurement is taken.

4. **Around `process_show`.** Existing, unchanged. `except RateLimited` still
   ordered **before** `except (TaskFailed, HerderError, IAError)`, since
   `RateLimited` subclasses `HerderError` and reversing them silently reverts the
   feature. Still on the mutation list, as in phase 1.

Rendering a pause is unchanged from phase 1 — sleep if it fits under `max_wait`,
else checkpoint and exit 0 — including the no-progress guard (amendment R21),
which stays exactly as built.

**That sentence describes touch points 3 and 4 only.** The two RUN-LEVEL pause
sites — the pre-flight gate (1) and the reactive catch around the three
run-level stages (2) — deliberately checkpoint and exit 0 without sleeping,
whatever `--wait` and `--max-wait` say. Both go through `_checkpoint_pause`,
which has no sleep branch; only the show loop sleeps. They behave alike, which
is the property R20 below actually protects.

**The consequence, stated rather than discovered:** this is a `--wait` contract
break relative to phase 1. `llama get --wait` started twenty minutes before a
reset used to enter the run, hit the limit reactively at a show, sleep through
it and finish; it now exits immediately having done nothing, and an unattended
invocation needs a manual `llama run resume`. Closing that needs a re-decide
loop around both run-level sites — see **T7b** in the plan, filed and unbuilt.

### Resolution of the deferred R20 question

Phase 1's spec deferred to phase 2 the question of how an unattended scheduler
learns that a run was *blocked* rather than *idle*, and instructed that the
answer be chosen against a real scheduler integration rather than in the
abstract.

**Resolved 2026-09-05: no new signal is added.** The operator does not run llama
from cron, and confirmed it is not a use case to bend the design around. The
pre-flight gate therefore checkpoints and exits 0 exactly like every other
pause, which keeps the Ctrl-C path and the first-show path identical — the
property the phase-1 spec required, since an operator cannot tell them apart.

`llama run list --json` already reports `state="paused"` with the resume
instant, so a machine-readable surface exists for free if a timer is ever wired
up. No distinct exit code, no stdout protocol.

## CLI and config

`[pacing]` gains two fields:

```toml
five_hour_ceiling = 90
seven_day_ceiling = 90
```

The phase-1 fields (`enabled`, `wait`, `max_wait`, `unknown_reset_wait`,
`reset_skew`) are unchanged. `DEFAULT_CONFIG_TOML` gains the matching commented
block, which `test_config.py::test_default_config_template_matches_defaults`
already pins against the defaults.

Three things the phase-1 spec proposed for phase 2 are **not introduced**;
none of them exist in the code today, so this removes nothing. `--batch` and the
fixed rail existed to pace with no signal at all, and there is now a free one on
the only backend that has a window. `--force` was to override a pre-flight
weekly *refusal*, and the pre-flight gate no longer refuses — it checkpoints like
any other pause (see R20 below). `trust_age` belonged to the staleness ladder,
which the live read makes unnecessary.

The existing `--wait` / `--no-wait`, `--max-wait` and `--no-pacing` flags on
`get`, `run approve` and `run resume` are unchanged. `--no-pacing` now disables
the proactive gate as well as the reactive pause.

### `llama pacing` (new, read-only)

In the shape of the existing `llama pipeline` teaching command: the two meters
that render -- session and weekly -- the learned per-show delta, what `decide()`
would return right now, and
**the forecast** — how many shows fit before the reset. This is the command the
operator runs *before* launching, given that runs are timed around available
capacity by hand today.

The same forecast prints once at the top of a run:

```
pacing: 5h 65% · weekly 7% · est 4.2%/show · ~6 of 13 fit before 17:19
```

A proactive pause says so plainly, so it does not read as a refusal:

```
pausing before the wall: 5h at 87%, est 4.2%/show — resumes 17:19 (1h 04m)
```

When the read fails, one line says so and the proactive rules are skipped for
that boundary, falling back to the reactive backstop:

```
pacing: usage read unavailable — pacing on limit errors only
```

## Testing

Offline and deterministic, per the repo contract: injected runner, injected
`now`, no real `$HOME`, no actual sleeping.

- **Policy tables** over `decide()`: priority order, each ceiling at its
  boundary, projection vs bare percentage before the first delta is learned,
  `max_wait` converting a long weekly pause into a checkpoint.
- **Parser fixtures** from the real captured output, plus: `Showing last-known
  usage`, a missing `Current session` line, a non-zero exit, malformed JSON,
  garbage prose, and an unrecognized per-model line. Every one degrades to
  `None` without raising.
- **Reset parsing**: the dated form, the undated refusal form, a DST boundary in
  `America/New_York` (the zone is named in the message precisely because it is
  not the caller's), and the per-meter bound — a weekly reset seven days out
  accepted, eight days rejected; a session reset five hours out accepted, six
  rejected.
- **EWMA**: a boundary spanning a window rollover contributes nothing; a normal
  boundary updates the estimate; a failed reading at either end contributes
  nothing.
- **Run-level catch**: a `RateLimited` raised from `run_winnow` produces a
  `paused` session and exit 0, not a traceback.
- **Resume costs nothing**: a fake provider with a call counter proves
  already-packaged shows make zero LLM calls on re-entry.

### Constraints to mutate, not merely run

Per the project's "green suite is not pinned" lesson, each of these is a
one-line change a loosely written test would happily keep passing. Flip each,
confirm the suite goes red, restore.

1. **The per-meter reset bound.** Flip the weekly bound back to 5.5 h; every
   weekly reading should be rejected.
2. **The EWMA rollover guard.** Drop the `resets_at` equality check; a rollover
   should poison the estimate toward zero.
3. **`Showing last-known usage` handling.** Treat it as a valid read.
4. **The new run-level `except RateLimited` ordering.** Place it after `except
   HerderError`, which it subclasses, and it is silently swallowed.

Phase 1's four mutations remain in force and are not re-listed here.

## Implementation order

1. **`herder/usage.py`** — `Meter`, `UsageReading`, `read_usage`, the parser,
   and the per-meter reset bound (which touches `limits.parse_reset`). Fully
   unit-testable against fixtures with no llama involvement.
2. **`decide()` in `llama/pacing.py`** — pure policy plus its test tables.
3. **`pacing-state.json`** — EWMA persistence, the rollover guard, the lock.
4. **`_execute` integration** — the pre-flight gate, the run-level catch, the
   before-each-show check and the delta measurement.
5. **Config fields and the forecast line.**
6. **`llama pacing`.**
7. **Mutation pass** over the four constraints above.
