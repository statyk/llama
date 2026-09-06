# Task 4 — CODE-QUALITY review

**Verdict: Changes requested** — one Important item, and it is mechanical (a
module docstring the task made false). The policy code itself is sound: the
logic is correct at every boundary I walked, and 51 mutations produced **zero
surviving logic mutants**. Everything below the Important item is optional.

Review is read-only: I made **no commits** and never wrote to
`/Users/shawn/projects/llama-wt-pacing2` (verified `git status --porcelain`
empty, `c79d81d` at HEAD).

## Harness (so the numbers are checkable)

Copy at `$D/work/t4-quality/tree`, imported by `PYTHONPATH` shadowing, run with
the worktree venv's interpreter as `python -u -B -m pytest` (never
`.venv/bin/pytest`), `stdin` from `/dev/null`, `-p no:cacheprovider`. Shadowing
proved by a planted `llama.pacing.__MUT_SENTINEL__ == "T4Q"` plus a per-run
assert that `llama.pacing/config/cli` and `herder.usage` all resolve under the
copy (`packages/llama/tests/test_zz_sentinel.py`, copy-only).

Every mutation ran the **whole suite** — baseline `1783 passed, 7 deselected in
6.6 s` (1782 + my sentinel test). The 600 s cap was never in play; the
implementer's round-2/3 subsetting was unnecessary. Each mutation: re-sync the
three sources from the worktree, assert the copy is byte-identical to the
worktree, assert the mutation text actually applied (`NOT-APPLIED` otherwise),
assert a green baseline first, and require the summary line to contain
`passed`/`failed` (`HARNESS-BROKEN` otherwise — it fired once, on a mutation of
mine that broke syntax, which is the check doing its job). Post-sweep
byte-identity re-asserted: `POST-SYNC identical=True` on both rounds.
Full log: `$D/t4-quality/t4-quality.log`.

## The implementer's claim: VERIFIED

I re-derived all of M1–M20 (including M1b/M3b/M8b/M13b/M18b/M18c/M18d) — 26
mutations — and **every one is caught**, at full-suite scope, including the four
it says it closed with new tests (M1/M1b by
`test_each_window_is_judged_against_its_own_ceiling`, M7 by
`test_a_missing_meter_is_skipped_rather_than_crashing`, M12 by
`test_the_pause_reason_names_the_window_and_the_estimate`, M18 by
`test_default_config_template_documents_every_pacing_knob`). The 24/24 claim
holds. M18d confirms the config test catches the *other* direction too (a field
added to `PacingConfig` with no TOML line), and M18c confirms it protects the
pre-existing knobs, not just the new pair.

I then added 25 mutations of my own, aimed at what the sweep did not touch.
**Total 51 executed, 44 caught, 7 survived.** All 7 survivors are unpinned
defaults/invariants; **none is a logic survivor.** Newly caught by existing
tests (i.e. genuinely pinned, not luck): meter swaps independent of the ceiling
swaps (X24/X25/X26), `enabled=not no_pacing` dropping `cfg.enabled` (X1),
`no_pacing` default flipped (X28), `_pause` returning `Proceed()` instead of
`None` (X29), `_pause` reading the real clock instead of the injected `now`
(X12), the projection subtracted rather than added (X13), `_pause` hardcoding
90 in place of its `ceiling` argument (X15), the estimate suffix rendered
unconditionally (X8) or with `is not None` (X17), `.1f`→`.2f` (X6), the `%`
sign dropped (X7), `PauseUntil(when, reason, scope)` (X10), `decide` returning
`None` (X9), and the `_pace` exit code (M20 — ruling R1 is pinned by execution).

Survivors (all mine, all minor — see findings m2–m4, m6):
X2 `PaceOptions` unfrozen, X3 `PauseUntil` unfrozen, X4 `Progress.per_show_delta`
default `None`→`4.0`, X5 that default removed entirely, X11 ceiling type
`float`→`int`, X14 the projection clamped to `>= 0`, X16 `_pace`'s error to
stdout instead of stderr.

## Ruling: the truthiness argument

**Correctly flagged and correctly left alone.** The ordering is not merely
"documented" — it is pinned by execution from four independent directions (M2
reverses the chain; X24/X25/X26 swap the meters while leaving the ceilings put;
M1/M1b swap the ceilings while leaving the meters put; M11 mislabels the scope).
`PauseUntil` is a three-field frozen dataclass in the same module with no
container or numeric semantics, so the falsy-`__bool__` scenario requires
someone to re-cut it as a collection — at which point M2 fails and tells them.
Restructuring into an explicit loop or `is not None` ladder would cost the
call-site readability that makes the priority order legible against the
docstring's numbered list, in exchange for a hypothetical. Do not restructure.

The cheap 90% of the hardening is free and I do recommend it: give `_pause` a
return annotation (finding m1), which states the `PauseUntil | None` contract
the `or` chain depends on, in the place a future editor of `PauseUntil` looks.

Related and also correct: `if projected` suppressing the estimate at exactly
`0.0` is consistent with `progress.per_show_delta or 0.0` treating `0.0` and
`None` identically, and it is pinned in both directions (X8 and X17 both
caught) — `test_the_pause_reason_names_the_window_and_the_estimate`'s second
case runs `Progress(None)` → `projected == 0.0`, so the 0.0 rendering is
covered, not merely the `None` one.

## Boundary walk (`pacing.py:165-176`, `meter.percent + projected <= ceiling`)

`Meter.percent` is an `int` from `\d+` (`herder/usage.py:47`), so there is no
float-equality hazard at the boundary and `f"{meter.percent}%"` never renders
`90.0%`.

| Case | Result | Correct? | Pinned |
| --- | --- | --- | --- |
| 86 + 4.0 vs 90 (exactly at) | `<=` → Proceed | yes — a ceiling is "may reach, not exceed" | yes (`test_ceiling_boundary_is_strict_greater_than`) |
| 87 + 4.0 vs 90 (a hair over) | Pause | yes | yes (same test) |
| delta `0.0` | reduces to `percent <= ceiling`; pauses only once the meter itself is over | yes — with nothing learned there is nothing to project, and the reactive path is the backstop | yes (M6 caught; `Progress(None)` cases) |
| delta `None` | identical to `0.0` via `or` | yes | yes |
| percent already > 100 | unreachable from `/usage` prose, and would pause anyway | n/a | n/a |
| `meter is None` | skipped, other window still judged | yes | yes (`test_a_missing_meter_is_skipped_rather_than_crashing`) |
| `resets_at is None` | `now + unknown_reset_wait_s` | yes | yes (both branches: M8/M8b/X12) |
| **negative delta** | **unclamped**: lowers the projection and renders `est -3.0%/show` | **no** | **no** (X14 survived) — finding m2 |

A stale `resets_at` already in the past yields a `PauseUntil` in the past, which
`sleep_until` returns from immediately (`pacing.py:76-79`). Benign; no action.

## `_pace` and the removed import (`cli.py:161-169`)

Both verified, not taken on trust. AST walk over `cli.py`: **zero** bare `Name`
nodes for `replace`, zero `ImportFrom` naming it; the two textual survivors are
`Attribute` nodes (`then.replace(tzinfo=…)`, `RESOLVE_PROMPT.replace(…)`). The
removal is safe.

`PaceOptions` is still `@dataclass(frozen=True)` (`pacing.py:88`) and the two
new fields are ordinary non-default fields ahead of nothing that has a default,
so construction stays positional-safe. Ruling R1 is respected and pinned: M20
(`Exit(1)`→`Exit(0)`) is caught by
`test_pace_loop.py::test_a_malformed_max_wait_fails_before_the_run_starts`. The
`_pace` body is now a single `return`, which is a genuine simplification over
the `replace(pace, enabled=False)` round-trip.

## Findings

### Important

**I1 — `packages/llama/src/llama/pacing.py:1-8`: the module docstring is now
false, and false in the specific way that misdescribes the architecture.**
It reads "The proactive half - reading Claude Code's usage cache, projecting
per-show cost, pausing BEFORE a window is exhausted - is phase 2 and
deliberately absent here." `decide()` is that proactive half and it is now in
this file. Worse, "reading Claude Code's usage cache" names the approach
`herder/usage.py:13-18` explicitly **rejects** on measured evidence
(`cachedUsageUtilization` is write-throttled and was observed serving an
already-expired window); a reader who takes this docstring as current will
believe llama reads the cache. This file's docstrings are load-bearing in this
repo — they are quoted as authority in CLAUDE.md — so a flatly wrong one at the
top is worth the two minutes. Suggested replacement for the second paragraph:

```
The reactive half learns the reset time from the backend's own refusal
(herder.limits) and either sleeps through it or checkpoints. The proactive
half is `decide()`: a pure policy over a live meter reading (herder.usage,
which reads `/usage` and deliberately NOT ~/.claude.json's cache) that pauses
at a show boundary BEFORE a window is exhausted.
```

While there, `PacingConfig`'s docstring (`config.py:98`) still says only
"Waiting out an exhausted usage window" — one clause noting it now also carries
the ceilings that stop the run *before* exhaustion would keep it honest.

### Minor

**m1 — `pacing.py:165`: `_pause` is the only unannotated function in the
module.** `parse_duration`, `format_delta`, `duration_arg`, `sleep_until`,
`pace_options`, `resume_at` and `decide` are all annotated; `_pause(meter,
ceiling, scope, projected, now, opts)` has none. Add
`-> PauseUntil | None` (and ideally `meter: Meter | None, ceiling: float,
scope: str, projected: float, now: datetime, opts: PaceOptions`). This is the
cheap half of the truthiness hardening: the `or` chain's correctness *is* the
`PauseUntil | None` contract, and stating it in the signature puts it where
someone re-cutting `PauseUntil` will read it.

**m2 — `pacing.py:196`: a negative `per_show_delta` is passed through
unclamped.** X14 (`projected = max(0.0, progress.per_show_delta or 0.0)`)
survives the whole suite, so nothing pins the sign. Task 5's EWMA runs over
per-show *deltas* of an account-wide meter, and a window rolling over mid-run
makes a delta negative — at which point the projection *lowers* the sum and the
gate becomes more permissive near the wall, while the operator reads
`est -3.0%/show`. Either clamp here (one call, `max(0.0, …)`, plus a test with
`Progress(-3.0)` at percent 89) or state the non-negative precondition in
`Progress`'s docstring so Task 5 owns it. My preference is the clamp: `decide()`
is the policy, and a policy should not be sensitive to a producer's sign
discipline.

**m3 — frozen-ness of the new dataclasses is unpinned.** X2 (`PaceOptions`
unfrozen) and X3 (`PauseUntil` unfrozen) both survive. `PaceOptions`'
docstring at `pacing.py:89-94` gives frozen a *reason* ("a run must not change
its own mind mid-loop"), which makes it a stated invariant with no test. The
repo already has the pattern to copy —
`test_cli_select.py:143 test_selector_is_frozen_dataclass`. One test
asserting `pytest.raises(dataclasses.FrozenInstanceError)` on a `PaceOptions`
and a `PauseUntil` closes both.

**m4 — `pacing.py:161`: `Progress.per_show_delta`'s default is unreachable.**
X4 (default → `4.0`) and X5 (default removed) both survive: no test or caller
constructs a bare `Progress()`. Harmless today, but the default is exactly the
"nothing learned yet" case, so it deserves the one-line assertion
`decide(NOW, _reading(five=99), pacing.Progress(), _opts())` in the missing-
estimate test rather than being carried unexercised into Task 5.

**m5 — `pacing.py:172`: the window label is derived by an `else` rather than a
mapping.** `f"{'weekly' if scope == 'seven_day' else '5h'}"` renders any scope
that is not `seven_day` as `5h`. There are exactly two windows today, so this
is not a live bug — but a third scope (a per-model meter; `UsageReading.per_model`
already exists) would be silently mislabelled `5h` in the operator-facing pause
line. A `{"seven_day": "weekly", "five_hour": "5h"}[scope]` fails loudly
instead, at no cost in lines.

**m6 — noted, no action asked.** X11 (`five_hour_ceiling: float` → `int`) and
X16 (`_pace`'s error to stdout instead of stderr) also survive. X11 means a
fractional ceiling (`87.5`) is a documented-by-type capability nothing
exercises; X16 is pre-existing phase-1 behaviour that this task only re-shaped.
Both are fine to leave.

## Test hygiene

No tautologies, no name/body mismatches, no incidental coupling that I would
change. `test_ceiling_boundary_is_strict_greater_than` does describe the
comparison it checks; `test_a_missing_meter_is_skipped_rather_than_crashing`'s
"rather than crashing" is real (a crash fails the assert);
`test_each_window_is_judged_against_its_own_ceiling` checks *both* directions,
which is what makes it kill a swap rather than accidentally pass one. The two
exact-string assertions on `reason` are deliberate and earn their coupling —
they are the only thing standing between an operator and a pause line that
names the wrong window (M12/X27). `test_default_config_template_documents_every_pacing_knob`
is written over `PacingConfig.model_fields` rather than a hardcoded pair, and
M18b/M18c/M18d confirm all three directions it claims. Its documented
`[pacing]`-only scope is the right call for this task.

No duplication, dead code or YAGNI found in the diff. `_pause` taking `ceiling`
explicitly (rather than deriving it from `opts` and `scope`) is the right
choice — it is what makes the meter/ceiling pairing visible at the call site,
and it is what M1/M1b/X15 can bite on.
