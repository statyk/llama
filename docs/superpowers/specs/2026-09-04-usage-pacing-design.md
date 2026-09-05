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

**4. The 5-hour limit's error signature, captured from a live run.** A
`llama get --profile dead` run on 2026-09-04 (13 shows: 3 packaged, 2 held, 8
failed) recorded, identically, for every show after the fifth:

```
claude exited 1: You've hit your session limit · resets 11:10am (America/New_York)
```

Three properties follow, and they are load-bearing for the classifier:

- **Exit code 1**, so it enters `claude_cli._run` via the `proc.returncode != 0`
  branch and is rendered by `_error_detail` (`claude_cli.py:85-105`). The
  message is well short of that function's 500-char truncation.
- **"session limit" names the window.** This matches the usage cache's own
  vocabulary, where `limits[]` carries `kind: "session"` for the 5-hour bucket
  and `kind: "weekly_all"` for the 7-day one — so the text discriminates
  *which* window was hit, not merely that one was.
- **The reset instant is in the message.** It is a 12-hour wall-clock time plus
  an IANA zone name, not an ISO instant. So `RateLimited.resets_at` is
  parseable from the error alone, and the reactive path does **not** depend on
  the undocumented cache file at all.

The same run confirms the failure mode this design exists to fix: the limit hit
after five shows, and the remaining eight failed in sequence, each first
burning three transport retries and their 2 s / 8 s backoff.

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
- Classification matches the message text against a small ordered pattern list,
  overridable in config. The measured 5-hour signature is `hit your session
  limit` → `scope="five_hour"`; the 7-day variant's wording is not yet observed
  (see "Open questions"). A structured check on `api_error_status` is added as
  the *preferred* discriminator if task 1's capture shows it carries an HTTP
  status, demoting the pattern list to a fallback.
- `parse_reset(text) -> datetime | None` reads the message's
  `resets 11:10am (America/New_York)` form: a 12-hour time plus an IANA zone,
  resolved via `zoneinfo` to the **next future occurrence** of that wall-clock
  time in that zone. `am`/`pm` is explicit, so there is no 12-hour ambiguity.
  **Sanity bound:** a 5-hour window's reset is always within ~5 hours, so a
  resolved instant more than 5.5 h out means the parse or the clock is wrong —
  return `None` and fall back to the cache, then to `unknown_reset_wait`.
  Parsing must never be able to manufacture a 24-hour sleep.
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
| ~~Same, but no show has run yet~~ | ~~Refuse to start, exit non-zero~~ — **deferred to phase 2**, see below |

**Amendment (R20, 2026-09-04): the third row is phase 2, and phase 1 does the
opposite** — a limit on the very first show checkpoints and exits 0 like any
other, leaving the session `paused` on the attention list.

*The argument for the original row is real and is not being dismissed.* A
cron-driven `llama get --profile … --auto` that packages nothing and exits 0 is
indistinguishable, to the thing that scheduled it, from a successful no-op — no
shows were due, or every candidate was already in the library. A window that was
already exhausted before the run started is the one case where the run genuinely
did nothing at all, and a non-zero exit is how a scheduler is told to look.

*Why it loses in phase 1.* This spec already mandates exit 0 for the Ctrl-C
checkpoint, "so an interrupted wait resumes with exactly the same command as a
planned one" (see *Interrupts and signals*). A limit on the first show is
near-identical to a limit on the seventh: nothing is wrong, nothing is lost, the
session is checkpointed, and `llama run resume <name>` finishes it. Exiting
non-zero there would contradict the exit-0 rule for a difference of one show,
and would make an unattended `--auto` run look **failed** when it is merely
paused, resumable, and already on the attention list — which is the louder
error of the two, because a "failed" nightly run gets investigated by a human
while a paused one gets resumed by the next run.

*Instruction for phase 2.* Revisit this deliberately; do not inherit the
silence. The information the scheduler actually wants is "this run was blocked,
not idle", and the exit code is only one way to carry it — a distinct code (not
1, which already means an error), a machine-readable line on stdout, or the
existing `run list --json` attention list are all candidates, and the choice
should be made against a real scheduler integration rather than in the
abstract. Whatever phase 2 picks, the Ctrl-C path and the first-show path must
end up with the same answer, since an operator cannot tell them apart.

`max_wait` (default 6 h) and the **no-progress guard** are the two mechanisms
governing whether a pause is waited out; nothing else overrides `--wait`.

**Amendment (R21, 2026-09-04): `max_wait` is no longer the *single* mechanism.**
The implementation added a second gate: if a whole pause cycle produced no
progress at all — no show packaged, held, or failed since the previous pause —
the next pause **checkpoints instead of sleeping again**, whatever `--wait` and
`max_wait` say. Without it, a backend that keeps refusing inside the cap naps
indefinitely: each refusal names a reset, the run sleeps to it, is refused
again, and never terminates. The guard is deliberately one cycle deep, so a run
that is merely slow (real progress between windows) keeps its right to another
sleep; it bounds a *stuck* run, not a slow one. **Do not delete it on the
strength of an unamended reading of the sentence above.**

The 7-day window is not special-cased:
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

**Amendment (R22, 2026-09-05): only call sites 2 and 3 are phase 1. Call site
1 — the pre-flight check — is the proactive gate and belongs to phase 2,
which is not built.** The numbered list above reads as though all three ship
together, and a Task 8 review caught that it does not: this spec's own
"Out of scope (phase 2)" list (and the phase-1 task brief) name "Proactive
percent thresholds... and the pre-flight projection warning" as unbuilt, so
item 1's "covers the opening burst that show-boundary checks would miss" is
true of the *design* but describes a check phase 1 never installs.

**Consequence, stated plainly: in phase 1, a `RateLimited` raised during
`interpret` (`run_discover`), `search` (`run_search`) or `winnow`
(`run_winnow`) is not caught anywhere.** All three run before the per-show
loop that call site 3 wraps, and call site 2's before-each-show check does
not exist either — it is also part of the unbuilt proactive gate, not a
reactive catch. Such a `RateLimited` therefore propagates out of `_execute`
as an ordinary unhandled exception: the process exits 1, no session marker
is written, there is no `paused` state and no `resume_after` instant. The
operator sees a failure, not a pause — the exact case call site 1 is
*supposed* to cover once phase 2 builds it. Only a limit raised inside the
per-show loop (call site 3, and by extension `gather`'s re-raise reaching
it) gets phase 1's pause treatment.

**`cli.py` is not the only ordering hazard — `gather.py` is a second swallow
site.** Corrected 2026-09-04 during implementation. `stages/gather.py:992`
wraps the `align_structure` LLM fallback in `except (TaskFailed, HerderError)`
and merely logs a warning, so a `RateLimited` raised there is swallowed:
`gather` completes, appends a `low-confidence structure alignment` review flag
the recording did not earn, and writes that flag to disk. Stage-level
`should_run` then means the resume never recomputes it, so a transient window
exhaustion leaves a permanent, wrong review flag on a show — which contradicts
this section's own guarantee that nothing about the show is wrong. `gather`
must re-raise `RateLimited` explicitly (`except RateLimited: raise` **above**
the broad clause, rather than narrowing that clause, so the intent is legible
at the call site), and that re-raise joins the mutation list. Every `except
HerderError` on the `_execute` path is an ordering hazard by construction,
because `RateLimited` subclasses it; these two are the only ones on that path
(audited 2026-09-04: `setlistfm.py:96`, `jerrybase.py:128`,
`correspondence.py:307` and `audio.py:37` are not LLM call sites, and
`cli.py:1902`/`cli.py:2505` belong to `fix`/`triage`, outside `_execute`).

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
  multi-hour idle. The positive fixture is the measured string, verbatim:
  `claude exited 1: You've hit your session limit · resets 11:10am (America/New_York)`
  — note the U+00B7 middle dot, which must survive as a literal rather than
  being normalized into the pattern.
- **Reset parsing**, including the sanity bound: a message whose parsed reset
  resolves more than 5.5 h out yields `None`, not a long sleep. Test with a
  frozen `now` on both sides of the named wall-clock time, and across a DST
  boundary in `America/New_York` — the zone is named in the message precisely
  because it is not the caller's.
- **False-positive cross-check**: `RateLimited` raised while a fresh snapshot
  reads 12% is demoted to a transport error and retried normally.
- **Resume-after-pause costs nothing**: a fake provider with a call counter
  proves already-packaged shows make zero LLM calls on re-entry.

Four constraints are to be **mutated, not merely run** — per the project's
"green suite ≠ pinned" lesson, each is a one-line change a loosely written test
would happily keep passing:

1. `RateLimited` caught before `HerderError` in `_execute`.
2. `RateLimited` in `_with_transport_retry`'s no-retry set.
3. `RateLimited` re-raised ahead of the broad clause in `gather`'s
   `align_structure` fallback (added 2026-09-04 — see the swallow-site note
   under "Integration").
4. Stale-cache disabling of the percent rules. *(Phase 2 — the percent rules do
   not exist in phase 1; phase 1 substitutes the reset sanity bound and the
   negative classification of the dropped-connection message, which are the two
   one-line constraints its own code actually carries.)*

Flip each, confirm the suite goes red, then restore.

## Open questions

Both are open by design; neither blocks implementation.

1. **The 5-hour signature is now measured** (see "Measured signals" item 4) and
   is pinned by test. Three narrower unknowns remain, none blocking:
   - **The 7-day variant's wording.** Presumed to differ from "session limit"
     — the cache calls it `weekly_all` — but unobserved. Until it is seen, a
     limit message that matches no known scope classifies as `RateLimited` with
     `scope=None`, which pauses on the reactive path but cannot pick a window;
     it falls back to the cache, then `unknown_reset_wait`.
   - **Whether `api_error_status` carries an HTTP status.** Success envelopes
     carry `null`. Task 1's raw capture answers it on the next hit, and a 429
     would make classification structural rather than text-based.
   - **Whether the limit is model-scoped** — i.e. whether a `low`-tier haiku
     call still succeeds while opus is refused. `probe-ratelimit.sh` tries both
     models for exactly this reason. It matters because `vet_research` runs on
     the `low` tier and might survive a limit that stops `brief`.
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
7. **Mutation pass** over the constraints above.
