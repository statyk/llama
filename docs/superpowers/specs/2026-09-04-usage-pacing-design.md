# Usage pacing — design

Status: approved design, not yet implemented.
Date: 2026-09-04.

## Problem

A large profile run (`llama get --profile dead`, `count = 13`) makes enough
`claude_cli` calls to exhaust the account's 5-hour usage window partway
through. Today that failure is invisible until it happens, and when it
happens it is handled badly:

- Every LLM failure collapses into a flat `HerderError`
  (`packages/herder/src/herder/claude_cli.py:118-136`) — nonzero exit, unparseable
  stdout, `is_error` envelope, and missing `result` are indistinguishable.
- `_with_transport_retry` (`packages/herder/src/herder/tasks.py:11-43`) then treats a
  window exhaustion as network noise and retries the identical prompt 3× with
  2 s / 8 s backoff, spending three more calls against a window that has none left.
- The show is recorded as a failure (`cli.py:243`) with an opaque, 500-char
  truncated `str(exc)`, the run ends `incomplete`, and the remaining shows in
  the shortlist fail the same way in sequence.
- Collateral damage: the same window is shared with the operator's interactive
  Claude Code sessions, so an unattended llama run takes those down too.

Reducing `profile.count` is not an acceptable workaround: the count feeds
`choose_entries`' artist and year distribution caps (`pipeline.py:31-42`), so
shrinking it changes *which* shows get picked, not just how many.

## Goals

- A long run survives window exhaustion: it pauses at a recoverable boundary
  and continues, rather than failing every remaining show.
- Pausing is proactive where a trustworthy signal exists, and reactive where it
  does not.
- The 7-day window, which cannot be slept through in the general case, is
  handled without ever silently idling for days.
- No new behavior on the `openrouter` or `fake` backends; the offline suite
  stays deterministic.

## Non-goals

- Mid-stage pausing. Decisions happen at run and show boundaries only.
- Pacing `emcee`'s package loop. emcee inherits the herder-level changes
  (notably: a rate limit stops being retried as transport noise) but gets no
  pacing loop in this work.
- Calibrating a %-per-dollar constant for the usage window (see "Measured
  signals" — the API does not expose the dollar limit, and other sessions
  pollute every observation).

## Measured signals

All three were measured on 2026-09-04 against Claude Code 2.1.252.

**1. The per-call result JSON carries spend, not headroom.**
`claude -p --output-format json` returns `total_cost_usd`, full token counts
including cache reads/writes, and a `modelUsage` map. It carries no field
describing the 5-hour or 7-day window. `claude_cli._run` currently parses this
envelope and discards everything except `result` (`claude_cli.py:130-136`).

**2. `~/.claude.json` → `cachedUsageUtilization` carries headroom.**

```json
"five_hour":  { "utilization": 74, "resets_at": "2026-09-04T20:09:59Z" },
"seven_day":  { "utilization": 75, "resets_at": "2026-09-05T10:59:59Z" }
```

with a sibling `fetchedAtMs`. `limit_dollars`, `used_dollars` and
`remaining_dollars` are **null** on this account, so utilization is available
only as a bare percent — there is no constant converting `total_cost_usd` into
a fraction of the window. This is why the policy's arithmetic is in
Δ-utilization-percent per show, and the dollar figure is used only as a
relative per-show weight and for reporting.

The file is an undocumented internal of another tool. Every read must degrade
to "no signal" on a missing file, malformed JSON, or an unrecognized shape.

**3. Cache freshness is periodic, not per-call.** Observed on 2026-09-04: the
cache sat 22 min stale; a headless `claude -p` completed and did **not**
refresh it; it later refreshed on its own during an interactive session
(3% → 74%), then aged to 19 min stale again. So an interactive session keeps it
roughly fresh on a cadence of tens of minutes, and a headless call does not
appear to refresh it at all. See "Open questions" — this is the single
assumption most worth confirming, because it decides how much of the proactive
half is load-bearing.

## Architecture

Approach: policy in `llama`, signals in `herder`. The irreducible parts (error
classification, cache reading, cost capture) live in `herder` where both
binaries benefit; the *policy* is a pure, unit-testable module in `llama`, and
it only ever pauses at boundaries the existing resume machinery already
recovers from for free.

### herder changes

**`herder/failures.py` (new) — raw failure capture.** On any failed
`claude -p`, write the untruncated stdout, stderr and exit code to a capture
file. Independently useful for debugging any backend failure, and it is what
turns the next natural rate-limit hit into evidence rather than a truncated
string. **This is task 1** — see "Implementation order".

**`herder/limits.py` (new) — classification and signal reading.**

- `RateLimited(HerderError)` with `scope: "five_hour" | "seven_day" | None` and
  `resets_at: datetime | None`. Raised from `claude_cli._run`'s existing
  failure paths.
- Classification is a small ordered list of signature patterns, overridable in
  config, plus a structured check on `api_error_status` if it proves to carry
  an HTTP status (unverified — see "Open questions").
- `read_usage_snapshot(path) -> UsageSnapshot | None`, parsing
  `cachedUsageUtilization` from `$CLAUDE_CONFIG_DIR/.claude.json` (falling back
  to `~/.claude.json`). Returns per-window utilization, `resets_at`, and
  `fetched_at`; the path is injectable so tests never touch a real home
  directory. Never raises.

**`herder/tasks.py` — retry exclusion.** `RateLimited` joins `TaskFailed` and
`ResearchNotSupported` in the no-retry set at `tasks.py:36`. This is a bug
fix worth landing on its own merits.

**`herder/claude_cli.py` — cost capture.** An optional injected `UsageMeter`
records `total_cost_usd`, token counts and model per call. With no meter
injected, behavior is byte-identical to today.

**False-positive guard.** Misreading a transient error as a window exhaustion
would idle a run for hours, which is worse than the failure being fixed. So a
`RateLimited` classification is cross-checked against a *fresh* snapshot: if
the cache is fresh and reads far below the threshold, the classification is
demoted back to an ordinary transport error and retried normally.

### llama changes

**`llama/pacing.py` (new) — pure policy.** Same shape as `siblings.py` and
`structure.py`: pure functions, IO in the caller.

```
decide(now, snapshot, progress, config) -> Proceed | PauseUntil(when, scope, reason)
```

`progress` is counters only: shows done since the last pause, shows remaining,
and the learned per-show utilization delta. No clock reads, no IO.

## Policy

Rules in priority order; the first that fires wins.

1. **Weekly ceiling.** `seven_day >= seven_day_stop` (default 90) →
   `PauseUntil(seven_day.resets_at, "seven_day")`. Checked both pre-flight and
   before each show; the same rule serves both.
2. **Five-hour gate.** Snapshot fresh and
   `five_hour + projected_next_show > five_hour_threshold` (default 85) →
   `PauseUntil(five_hour.resets_at + reset_skew, "five_hour")`. Gating on the
   projection rather than the bare percentage is what prevents starting a show
   that cannot finish. Before any delta has been observed, it degrades to
   gating on the bare percentage.
3. **Fixed rail.** `shows_per_batch > 0` and that many shows since the last
   pause → `PauseUntil(five_hour.resets_at if known else now + batch_pause)`.
   Requires no signal at all, and is the only rule that works on any backend.
4. Otherwise `Proceed`.

A **pre-flight projection warning** (not a pause) fires when the projected run
cost would cross `seven_day_warn` (default 75) without current usage being over
a stop threshold. Projection at run start is the weakest number available, so
it warns and proceeds rather than refusing.

**The reactive path is not a rule.** A `RateLimited` raised from inside a show
is caught at the show boundary, cross-checked as above, and converted to the
same `PauseUntil` a boundary check would have produced — from the exception's
`resets_at`, else the cache's, else `now + unknown_reset_wait` (default 1 h)
followed by a re-probe. The partially processed show is abandoned where it
stands; its completed stage artifacts persist and resume redoes only what is
missing.

### Rendering a pause (caller's job, not the policy's)

The policy emits one `PauseUntil`. The caller renders it three ways, from facts
the pure function should not know:

| Condition | Behavior |
| --- | --- |
| `wait` and `when - now <= max_wait` | Sleep, then continue |
| Cap exceeded, or `--no-wait` | Checkpoint and exit 0 |
| Same, but no show has run yet | Refuse to start, exit non-zero |

`max_wait` (default 6 h) is the **single** mechanism governing whether a pause
is waited out. No rule overrides `--wait`. The 7-day window is not special-cased:
it simply tends to produce a wait longer than the cap, so it checkpoints by
default, and `--max-wait 30h` sleeps through a weekly reset that is within a day.
This also caps the damage from a garbage or far-future `resets_at`.

The message on a capped pause names the escape hatch:

```
weekly window resets in 26h 12m — exceeds --max-wait 6h
paused: 6 of 13 shows packaged
resume and wait it out:  llama run resume dead-2026-09-04 --max-wait 30h
```

### Degradation ladder

When the snapshot is missing, unparseable, or older than `trust_age` (default
30 min), rules 1 and 2 are **disabled outright**, not estimated. The run says so
once, and falls back to rule 3 plus the reactive backstop:

```
usage cache 2.4 h stale — pacing on show count and limit errors only
```

A stale cache reading 40% while the truth is 95% must never be allowed to
authorize a show.

### Learned per-show cost

An EWMA over Δ-utilization observed across show boundaries where the cache was
fresh at both ends, persisted in a workspace-level `pacing-state.json` so a new
run starts calibrated rather than blind.

**Known bias, accepted:** the delta cannot separate llama's spend from the
operator's concurrent interactive sessions, so a run paced while the operator
works will over-estimate per-show cost and pause earlier than strictly
necessary. That is the safe direction. Do not "fix" this by subtracting llama's
own measured dollar spend — the dollar-to-percent conversion does not exist
(see "Measured signals").

### Backend gating

Rules 1 and 2 require `[llm] backend = "claude_cli"`. Under `openrouter` or
`fake` there is no window to read, the snapshot is never consulted, and the
`fake` backend never pauses — which is what keeps the existing offline suite
deterministic. The fixed rail (rule 3) works on any backend when explicitly
configured.

## Integration

Three call sites in `_execute` (`cli.py:155-278`), and no others:

1. **Pre-flight**, after criteria resolution and before `run_search` /
   `run_winnow`. This covers the opening burst that show-boundary checks would
   miss: winnow calls `light_research` once per shortlisted candidate and
   `score_reviews` in batches of 5 (`winnow.py:114-156`), all before the first
   show exists.
2. **Before each show**, at the top of the `for entry in chosen` loop
   (`cli.py:253-262`).
3. **Around `process_show`**, catching `RateLimited` **before** the existing
   `except (TaskFailed, HerderError, IAError)` at `cli.py:237`. `RateLimited`
   subclasses `HerderError`, so the ordering is load-bearing and gets its own
   test. A limit hit is **not** appended to `failures[]` — nothing about the
   show is wrong.

**Session state.** `STATE_PAUSED = "paused"` joins the states at
`sessions.py:13-16`, with `mark_paused(ws, outcome, failures, resume_after,
scope, reason)` following the existing wholesale-rewrite discipline (`_write`,
`sessions.py:19-26`) so a later `mark_complete` erases the pause block the same
way it erases stale failures. `attention_sessions` already surfaces anything
non-`complete`, so `llama run list` needs no change beyond rendering the
resume time.

**Resume needs no new machinery.** `run resume` re-enters `_execute`;
stage-level `should_run` (`workspace.py:66-67`) skips every artifact already on
disk, so a completed show costs a few `stat` calls rather than an LLM call.
Pacing re-evaluates from the top; if the window is still exhausted it pauses
again. Idempotent by construction.

**Ctrl-C during a pause is a clean checkpoint**, not a traceback: it marks the
session paused and exits 0, so an interrupted wait resumes with exactly the
same command as a planned one.

## CLI and config

Flags on `get`, `run resume` and `run approve` (all three funnel into
`_execute`):

- `--wait / --no-wait` — default wait
- `--max-wait 30h` — the cap above
- `--batch N` — the fixed rail, overriding config
- `--no-pacing` — full escape hatch
- `--force` — override the pre-flight weekly refusal

Durations parse as `6h`, `90m`, `5h30m`; a small parser with its own test.

`[pacing]` follows the `WinnowConfig` recipe exactly — nested `BaseModel` with
`Field(default_factory=...)`, plus the matching block in `DEFAULT_CONFIG_TOML`
(`config.py:144-255`), which `test_config.py::test_default_config_template_matches_defaults`
already pins against the defaults:

```toml
[pacing]
enabled = true
wait = true
max_wait = "6h"
shows_per_batch = 0        # 0 = off; the fixed rail
batch_pause = "5h"
five_hour_threshold = 85
seven_day_stop = 90
seven_day_warn = 75
trust_age = "30m"
unknown_reset_wait = "1h"
reset_skew = "2m"
```

**New read-only command `llama pacing`**, in the shape of the existing
`llama pipeline` teaching command: prints the snapshot, its age, whether it is
trusted, the learned per-show estimate, and what the pacer would decide right
now. Without it, a stale cache silently disables half the feature with nothing
in the UI saying so.

## What the operator sees

```
pacing: 5h 3% (fresh 2m) · weekly 68% · est 4.2%/show · 13 shows
```

At a pause, and periodically while sleeping so the terminal is not a dead
prompt for hours:

```
paused after 6 shows: 5h window at 86% — resumes 20:12 (4h 12m)
  … waiting, 3h 42m left
```

## Testing

Offline and deterministic, per the repo contract: no wall-clock reads, no real
`$HOME`, no actual sleeping. `decide()` takes `now`; the snapshot reader takes a
path; the sleep is injected the way `tasks.py` already injects `_sleep`.

- **Policy tables** over `decide()`: priority order, each threshold at its
  boundary, `max_wait` converting a long pause to a checkpoint, projection vs
  bare percentage before the first delta is learned.
- **Snapshot reader** against captured fixtures of the real
  `cachedUsageUtilization` shape (account UUID scrubbed), plus missing file,
  malformed JSON, a renamed key, and all-`null` sections — every one degrading
  to `None` without raising.
- **Classification, with a negative set that matters**: the `CLOSED_MID`
  fixture already in `test_claude_cli.py` must classify as transport noise, not
  a limit. That test is what stands between a dropped connection and a
  multi-hour idle.
- **False-positive cross-check**: `RateLimited` raised while a fresh snapshot
  reads 12% is demoted to a transport error and retried normally.
- **Resume-after-pause costs nothing**: a fake provider with a call counter
  proves already-packaged shows make zero LLM calls on re-entry.

Three constraints are to be **mutated, not merely run** — per the project's
"green suite ≠ pinned" lesson, each is a one-line change a loosely written test
would happily keep passing:

1. `RateLimited` caught before `HerderError` in `_execute`.
2. `RateLimited` in `_with_transport_retry`'s no-retry set.
3. Stale-cache disabling of the percent rules.

Flip each, confirm the suite goes red, then restore.

## Open questions

Both are open by design; neither blocks implementation.

1. **The rate-limit error signature is unknown.** Deliberately not bought by
   burning a window. Ships as a conservative pattern list plus the cross-check;
   the raw-failure capture log (task 1) records the true text on the first
   natural hit, and it gets pinned by test afterward. The specific fields to
   look for, in priority order: `api_error_status` (success envelopes carry
   `null`, which implies a status on failure — a 429 would demote the pattern
   list to a fallback), the process exit code (it decides which of
   `claude_cli._run`'s branches produces the message), whether the message body
   names a reset time and in what format, and `subtype` / `terminal_reason`.
   Also worth capturing: whether a `low`-tier haiku call still succeeds while
   opus fails, i.e. whether the limit is model-scoped.
2. **Whether a headless-only run refreshes the usage cache.** Measured once,
   negatively, on 2026-09-04. If headless calls *do* refresh it on some cadence,
   the staleness ladder is mostly decoration and the proactive rules get
   substantially stronger. Cheap to settle: two probes with a cache check
   between, with no interactive session running.

A third number is worth capturing opportunistically: **the `five_hour`
utilization reading at the moment a limit actually fires.** If the error arrives
short of 100%, `five_hour_threshold`'s default of 85 should move.

## Implementation order

1. **Raw failure capture** (`herder/failures.py`). Smallest, independently
   useful, and it is what makes the next natural limit hit yield evidence.
2. **`RateLimited` + retry exclusion.** The standalone bug fix.
3. **Snapshot reader + `UsageMeter`.**
4. **`llama/pacing.py`** — pure policy plus its test tables.
5. **`_execute` integration**, session `paused` state, CLI flags, config.
6. **`llama pacing`** command.
7. **Mutation pass** over the three constraints above.
