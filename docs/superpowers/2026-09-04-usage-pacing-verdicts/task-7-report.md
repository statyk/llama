# Task 7 report — pause and resume the show loop

Status: **DONE_WITH_CONCERNS** (concerns are scope observations, not defects in the delivered work)

Commits, oldest first, all on `usage-pacing`:

| sha | subject |
|---|---|
| `8d6ca73` | feat(llama): add PaceOptions, pace_options and resume_at |
| `08bf139` | feat(llama): pause and resume a run when the usage window runs out |
| `636aa1c` | feat(llama): surface a paused run's resume time in the JSON views |
| `980e02b` | test(llama): pin the two loop constraints a mutation pass found unpinned |

## What was done

**1. `pacing.py` (`8d6ca73`)** — `PaceOptions` (frozen), `pace_options(config, wait, max_wait)`,
`resume_at(err, pace)`, per the brief. Two deliberate departures, both explained below and in
docstrings.

**2. `_execute` (`08bf139`)** — the loop restructure, verbatim from the brief including all three
amendments (the `if limited:` check *after* the `try/except Locked` block, the two extra assertions
in the sleep-and-finish test, and the `done_before_pause`/`stalled` no-progress guard). `RateLimited`
is caught in its own arm ahead of `except (TaskFailed, HerderError, IAError)`, which it subclasses.
`set_capture_dir(config.root / "llm-failures")` is called once after `make_providers`. The clock is
read as `_pacing._now()` via `from llama import pacing as _pacing`.

**3. CLI flags (`08bf139`)** — `--wait/--no-wait`, `--max-wait`, `--no-pacing` on `get`,
`run approve` and `run resume`, threaded through `_get_query`/`_get_profile` into `_execute`.
Factored into one `_pace(config, wait, max_wait, no_pacing)` helper so the three commands cannot
drift; it does the eager `ValueError` → `typer.Exit(1)` validation. `_redo_run_level`'s `_execute`
call is left on the default (`pace=None` → config defaults), which is the pre-existing behaviour for
a stage replay.

**4. JSON views + a hint fix (`636aa1c`)** — see the `_session_json` decision below, plus
`pacing.duration_arg`.

**5. Extra pins (`980e02b`)** — two mutation survivors closed.

## Test commands and output

```
./.venv/bin/python -m pytest packages/llama/tests/test_pacing.py -q     → 19 passed
./.venv/bin/python -m pytest packages/llama/tests/test_pace_loop.py -q  → 21 passed
./.venv/bin/python -m pytest -q                                         → 1736 passed, 7 deselected, 26 warnings in 5.79s
```

Baseline was 1703 passed / 7 deselected; the 33 new tests are 7 in `test_pacing.py`, 21 in the new
`test_pace_loop.py`, 3 in `test_sessions.py` (the brief's three, verbatim) and 2 in
`test_run_namespace.py`. Two pre-existing tests needed a one-word edit: the `fake_execute` stubs in
`test_get_cmd.py` and `test_run_namespace.py` gained `pace=None`, and `test_status_cmd.py`'s exact
key-set assertion gained the two new keys (that test is what caught the JSON change — it was doing
its job).

## The `cli.py:2505` finding — the spec's audit note is wrong

`cli.py:2505` is **`main_cli`**, the single global error boundary, not `fix`/`triage`. It wraps
`app()`, so it sits above `_execute` on every path. What it does to the two things this task can
send through it:

- **A `RateLimited` propagating out of `_execute`** hits `except (LlamaError, HerderError)` — since
  `RateLimited` is a `HerderError` — and becomes `error: You've hit your session limit …` plus
  `SystemExit(1)`. No traceback, but also **no pause marker and no resume hint**: the run is simply
  lost with an exit 1. This is why catching at the show boundary matters, and it is the shape of the
  residual gap in "Concerns" below.
- **A `typer.Exit(1)` from `_pace`** never reaches `main_cli`'s handlers at all. Click runs the app
  in standalone mode, converts its own `Exit` into `SystemExit`, and `SystemExit` is not an
  `Exception`, so it passes through untouched — as the docstring claims. Verified for real, not just
  by reading: `llama get q --auto --max-wait soon` through `main_cli` prints
  `not a duration: 'soon' (use forms like 6h, 90m, 5h30m)` and exits 1, with no traceback.

It did **not** change the design — `_execute` returning normally after `mark_paused` gives exit 0,
which is what the brief wants and what the tests assert — but it did confirm that the eager
`--max-wait` validation had to be a `typer.Exit`, not a raised `LlamaError`, to avoid the `error: `
prefix on what is a usage message.

## The `_session_json` decision: **add both keys** (`636aa1c`)

`_session_json` now emits `resume_after` and `pause_reason` alongside the existing fields. Reasoning:

- The JSON view is the machine-readable **equivalent** of the table, not a subset of it, and
  `_print_sessions` already prints `resumes <instant>` for a paused row (`cli.py:567-568`). Leaving
  the JSON short makes it strictly less informative than the human output for precisely the state
  that was just added.
- The only thing an automated consumer can do with `state: "paused"` is decide when to retry it. The
  state alone cannot answer that; `resume_after` is the answer, and it is already persisted and
  already on `SessionInfo`. The precedent is `failures`, which was added to the JSON for the same
  reason in the incomplete-state work.
- Cost is nil and the shape is stable: both keys are **always present, null off a pause**, exactly
  like the nullable `outcome`, so no row gains or loses fields depending on state. `run list --json`
  and `status --json` share the function, so they stay consistent for free.
- **`pause_scope` is deliberately NOT added.** It is in the marker but not on `SessionInfo`, and
  adding it would mean widening a dataclass nobody asked to widen; the reason text names the window
  ("session limit") anyway. If a consumer ever needs to branch on five_hour vs seven_day, that is the
  moment to add it, with a caller to justify it.

Pinned by two new tests in `test_run_namespace.py` (a paused row carries both values; an unpaused row
carries both keys as null).

## Evidence the constraints are pinned (mutation results)

Every mutant below was applied to the working tree, `packages/llama/tests` run, then
`git checkout --` reverted. Script kept at `<scratchpad>/sdd/t7/mutate.py`, log at
`<scratchpad>/sdd/t7/t7.log`.

| # | mutation | result |
|---|---|---|
| M1 | `unprocessed.extend(pending[idx:])` → `pending[idx + 1:]` | KILLED |
| M2 | move the `if limited:` check to the **top** of the `for` body (the original defect, verbatim) | KILLED |
| M3 | no-progress guard removed (`stalled = False`) | KILLED |
| M4 | `unprocessed.extend(deferred[idx:])` → `deferred[idx + 1:]` | KILLED |
| M5 | the `except RateLimited` arm deleted (falls through to the `HerderError` arm) | KILLED |
| M6 | `unprocessed.extend(deferred)` dropped on the limited branch | KILLED (after `980e02b`; **survived** before) |
| M7 | reset skew dropped from `resume_at` | KILLED |
| M8 | unknown-reset fallback ignores the configured duration | KILLED |
| M9 | resume hint uses `format_delta` again | KILLED |
| M10 | `set_capture_dir(...)` removed | KILLED (after `980e02b`; **survived** before) |
| M11 | `pace.wait` ignored (always sleeps) | KILLED |
| M12 | `max_wait` cap ignored | KILLED |
| M13 | `pace.enabled` ignored (a limit never fails a show) | KILLED |
| M14 | `_pacing._now()` → `datetime.now(timezone.utc)` (the rebound-name trap) | KILLED, 3 tests |

The dropped-show and no-progress constraints specifically (M1, M2, M3, M4, M6) are all dead, and the
two that were alive are the two `980e02b` exists to close.

**Why a multi-show fixture was necessary.** The end-to-end fixture in `test_sessions.py` processes
one show, and with one show `pending[idx:]`, `pending[idx + 1:]` and "check at the top of the loop"
all collapse to the same observable outcome for most assertions — the brief's amendment (2) is what
rescues that test, via `brief.calls >= 2` and `outcome == "1 packaged"`. The new
`packages/llama/tests/test_pace_loop.py` drives `_execute` directly with three synthetic shortlist
entries and a scripted `process_show`, so the *exact set and order* of shows that come back after a
pause is observable: `test_the_show_that_hit_the_limit_is_retried_not_dropped` asserts
`seen == ["a", "b", "b", "c"]`, which no off-by-one can satisfy. Its docstring says so, so a future
reader does not "simplify" it back to one show.

## Deliberate departures from the brief's literal code (both small, both tested)

1. **`resume_at` declines a naive `resets_at`** and returns the unknown-reset default rather than
   returning the naive value. The brief returns it, which would hit `sleep_until`'s new guard and
   raise `ValueError` out of `_execute` — turning a pause into a crash. It cannot come from
   `herder.limits.parse_reset` (always UTC), so a naive value means some other producer guessed, and
   guessing again here risks a multi-hour wake-time error. This is the "fix the source, don't coerce"
   instruction taken literally: nothing coerces, and nothing naive can reach `sleep_until`.
2. **`pacing.duration_arg` for the resume hint.** The brief's hint prints
   `--max-wait {format_delta(wait_s)}`, i.e. `--max-wait 2h 0m` — which `parse_duration` **rejects**
   on the space, so the copy-pasteable command it hands the operator does not run. `duration_arg`
   renders `2h` / `2h1m` / `12m` (no space) and **rounds up** to the minute, because a floored value
   can be shorter than the wait it was printed for, which would checkpoint again for the same reason.
   The prose line above it still uses `format_delta` — that one is prose, and reads better with the
   space.

## Surprises

- **A one-line clock mutation (M14) is killed only by the checkpoint-branch tests.** Today's real
  date happens to be 2026-09-04, the same day the tests freeze, so a wall-clock read lands *after*
  the frozen `NOW` and the sleeping branch degenerates to zero sleeps rather than an obvious error.
  Three checkpoint tests still catch it. Worth knowing that this particular trap is date-sensitive in
  its failure *mode*, though not in whether it is caught.
- The `_clock` helper's sleep budget is load-bearing, not cosmetic: without the no-progress guard the
  loop naps forever, and a hanging test is a far worse report than a failing one. Its docstring says
  so. Resets in the loop tests are minutes out rather than hours so that one pause costs one `_sleep`
  call — `sleep_until` chunks at 900 s, and a budget denominated in chunks would not measure pauses.
- Mangled-import near-miss during the edit: a `str.replace` on `from herder import FakeProvider`
  also hit a function-local import of the same line inside `test_sessions.py`. Caught immediately by
  an `IndentationError` at collection; noted only because the same hazard applies to anyone scripting
  edits to that file.

## Concerns

1. **A `RateLimited` from a run-level stage still loses the run** (exit 1, no checkpoint). `interpret`
   runs in `_get_query` outside `_execute` entirely; `search` and `winnow` run inside `_execute` but
   *before* the loop. A refusal in any of them propagates to `main_cli` and prints `error: …`. This is
   in the brief's scope wording ("at the show boundary") and out of this task's file scope, but it is a
   real hole in "a usage limit never costs you a run": the pause machinery does not cover the first
   three stages. Worth a filed follow-up — the design question it needs answered is what `mark_paused`
   should record for a run with no shortlist yet.
2. **`set_capture_dir` is a module-level global set per `_execute` call**, so in a process running two
   runs against different roots the second wins. Correct for the CLI (one run per process) and pinned
   by a test, but it is a shared mutable and the tests now depend on `_execute` having set it — a test
   that asserts capture is *off* must reset it itself.
3. **The no-progress guard is one cycle deep by design.** A backend that alternates refuse/succeed
   forever would keep sleeping, since each cycle shows progress. That is the intended behaviour (real
   progress deserves another window), but it means the guard bounds a *stuck* run, not a *slow* one.
4. **`run approve`'s pacing flags are validated before its prompt**, so `--max-wait soon` fails
   before the shortlist prints. Deliberate (fail before the run starts) and pinned, but it means the
   flag error appears without any context about which session it belonged to.

---

# Task 7 — fix round 1

Status: **DONE**. All five items addressed; the ten deferred Minor findings untouched.

| sha | subject |
|---|---|
| `3578fcb` | fix(pacing): tolerate whitespace in a duration, and pin three loop constraints |
| `8c98dc8` | docs(spec): amend the pause-rendering rules for what phase 1 actually does |

Code and spec committed separately, as asked. Tree clean.

```
./.venv/bin/python -m pytest -q   → 1741 passed, 7 deselected, 26 warnings in 7.61s
```
(1736 → 1741: five new tests. The mutation runs below use the
`packages/llama/tests` subset, whose baseline is 1304.)

## Item 1 — `mark_paused(…, failures, …)` pinned, on **both** call sites

New `test_a_checkpoint_carries_the_failures_the_run_had_already_taken` in
`test_pace_loop.py`: three shows, `a` raises `TaskFailed`, `b` then hits a limit with
`--no-wait`. Asserts `state == paused`, `[f["show"] for f in info.failures] == ["a"]`, the error
text survives, and `outcome == "1 failed"`.

The first mutation pass then showed **the same defect on the Ctrl-C path** (`cli.py:341`'s sibling
inside the `except KeyboardInterrupt` block) — `F1b` survived. The existing interrupt test had no
prior failure to carry. Rewrote its fixture so `a` fails, `b` limits, and the interrupt lands during
the nap, and added the same `failures == ["a"]` assertion. Both call sites are now dead under
mutation.

## Item 2 — all three terms of the no-progress guard pinned

Two new tests, one per unpinned term, both built so the term is the **only** progress between two
pauses:

- `test_a_held_show_between_pauses_counts_as_progress` — `a` refuses, sleeps; `a` comes back
  **held** and `b` refuses; the run must sleep again and finish `1 packaged, 1 held`.
- `test_a_failed_show_between_pauses_counts_as_progress` — same shape with `a` failing; ends
  `incomplete`, `1 packaged, 1 failed`.

`packaged` was already pinned by `test_progress_between_pauses_still_earns_another_sleep`; the
mutation table below confirms it rather than assuming it.

## Item 5 — fixed at both ends

**(a) `parse_duration` tolerates internal whitespace.** Implemented as
`re.sub(r"\s+", "", text or "")` **before** the match, so the `$` anchor the earlier review pinned is
literally unchanged. Verified every listed rejection still raises — `""`, `"   "`, `"\t\n"`,
`"6h banana"`, `"5h30m!"`, `"6s30m"`, `"6"`, `"-2h"`, `"6x"`, plus `"6 h banana"` to show the
tolerance does not rescue trailing garbage. The whitespace-only case is caught by the existing
`any(m.groups())` guard, exactly as the finding suspected, and now has a test rather than an
assumption. The existing rejection test was extended in place, not replaced.

Two mutants were run for this, not one: reverting the tolerance (`F5a`), and — the more interesting
one — getting the same acceptance by **weakening the anchor** instead (`F5a2`, dropping the `$`).
Both are killed; the second is what proves the anchor's own tests still bind.

**(b) Round-trip property test**, `test_format_delta_output_always_parses_back`. The property, stated
precisely in the test's docstring and asserted over 18 values:

> `parse_duration(format_delta(x)) == 60 * (max(int(x), 60) // 60)`

i.e. round-trip is to the minute; `format_delta` floors twice (it truncates seconds and clamps at one
minute), so the result equals `x` only for a whole number of minutes, is the minute below otherwise,
and is **60 for every `x < 60`** — the one-minute floor, called out explicitly because it is the part
a naive `== x` property would get wrong.

**`cli.py:356` — kept `format_delta`, deliberately.** With (a) in place, the prose line's
`exceeds --max-wait 6h 0m` now parses, so it is no longer a trap, and the space reads better in
prose. The copy-pasteable command one line down keeps `duration_arg`, because there the load-bearing
property is not the spacing but that it rounds **up**: a floored value can be shorter than the wait it
was printed for, so pasting it would checkpoint again for the same reason. The hint test now asserts
both — `parse_duration("1h 0m") == 3600` for the prose, and `>= wait_s` for the command.

## Mutation proof

Script `<scratchpad>/sdd/t7fix1/mutate.py`, log `<scratchpad>/sdd/t7fix1/t7fix1.log`. Each mutant:
clear `__pycache__` → apply → run `.venv/bin/python -m pytest -q packages/llama/tests` under
`PYTHONDONTWRITEBYTECODE=1` with a **180 s timeout** (a timeout is reported as `TIMEOUT`, never as a
kill) → `git checkout --` → clear `__pycache__` again. Baseline and restored runs bracket the set.

```
BASELINE (code=0) -> 1304 passed, 7 deselected
KILLED   F1  mark_paused given [] instead of the failures it took     -> 1 failed, 1303 passed
KILLED   F1b mark_paused given [] on the Ctrl-C path too              -> 1 failed, 1303 passed
KILLED   F2a guard drops `held`                                       -> 1 failed, 1303 passed
KILLED   F2b guard drops `len(failures)`                              -> 1 failed, 1303 passed
KILLED   F2c guard drops `packaged`                                   -> 1 failed, 1303 passed
KILLED   F5a parse_duration whitespace tolerance reverted             -> 3 failed, 1301 passed
KILLED   F5a2 anchor weakened instead of stripping first              -> 1 failed, 1303 passed
RESTORED (code=0) -> 1304 passed, 7 deselected
```

7 of 7 killed, no timeouts.

**One process note worth recording.** The first proof run reported `F1b SURVIVED` *and* ended with
`RESTORED -> 3 failed`. The survivor was real and is now fixed. The bad restore was my own error: the
`parse_duration` fix was still **uncommitted** when the script ran, so `git checkout --` on
`pacing.py` reverted the mutation *and the fix together*, and the trailing failures were the fix's own
tests. Caught by the bracketing restore run, which is exactly why it is in the script. Re-applied the
fix, committed it, and re-ran the whole set against a committed tree — that is the table above. The
rule this earns: **never mutate a file with uncommitted work in it**, since the revert mechanism
cannot tell your edit from the mutant's.

## Items 3 and 4 — spec amendments (`8c98dc8`, docs only)

Both in `docs/superpowers/specs/2026-09-04-usage-pacing-design.md`, in the "Rendering a pause"
section.

**R20.** The third rendering row is struck through and marked deferred to phase 2, followed by three
labelled parts, as required:

- *The argument for the original row is real and is not being dismissed* — a cron-driven
  `llama get --profile … --auto` that packages nothing and exits 0 is indistinguishable, to the
  scheduler, from a successful no-op (nothing due, or everything already in the library). An
  already-exhausted window is the one case where the run genuinely did nothing, and a non-zero exit is
  how a scheduler is told to look.
- *Why it loses in phase 1* — the spec itself mandates exit 0 for the Ctrl-C checkpoint "so an
  interrupted wait resumes with exactly the same command as a planned one", and a first-show limit is
  near-identical to a seventh-show limit. Exiting non-zero would contradict that rule over a
  difference of one show and would make an unattended `--auto` run look **failed** when it is merely
  paused, resumable and already on the attention list — the louder of the two errors, since a failed
  nightly run gets investigated by a human while a paused one gets resumed by the next run.
- *Instruction for phase 2* — revisit deliberately, do not inherit the silence. Notes that the exit
  code is only one carrier for "blocked, not idle" (a distinct code — not 1, which already means an
  error — a machine-readable stdout line, or the existing `run list --json` attention list), that the
  choice should be made against a real scheduler integration, and that whatever is picked, the Ctrl-C
  path and the first-show path must end up with the same answer because an operator cannot tell them
  apart.

**R21.** The sentence now reads "`max_wait` (default 6 h) and the **no-progress guard** are the two
mechanisms governing whether a pause is waited out; nothing else overrides `--wait`", followed by an
amendment paragraph stating what the guard does, why it exists (a backend refusing inside the cap
would otherwise nap indefinitely — each refusal names a reset, the run sleeps to it, is refused
again), that it is one cycle deep on purpose so a merely-slow run keeps its right to another sleep,
and an explicit "do not delete it on the strength of an unamended reading of the sentence above".

## Not done, by instruction

Task 8 (the mutation pass and docs) not started. The ten deferred Minor findings not touched.

## Concerns

- **The Ctrl-C survivor is the interesting result of this round.** Item 1 named one call site; the
  same defect existed on the other, and only mutation found it. Both `mark_paused` call sites now
  duplicate the same six arguments, which is how they drifted apart in review coverage in the first
  place. A single `_checkpoint(when, scope, reason)` closure would make a future divergence
  impossible — deliberately not done here, since it is a refactor and this round is a fix round, but
  worth a Minor for Task 8 or later.
- The three earlier concerns from the first report stand unchanged, in particular that a
  `RateLimited` from `interpret`/`search`/`winnow` still exits 1 with no checkpoint. Note that the
  R20 amendment is *adjacent* to that gap but not the same thing: R20 is about how a first-**show**
  pause is reported, whereas a first-**stage** refusal never reaches the pause machinery at all.
