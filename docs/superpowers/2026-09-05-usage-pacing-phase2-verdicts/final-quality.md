# Whole-branch CODE-QUALITY review — usage pacing phase 2

Branch `ac7c428..3693e45` (32 commits), worktree `/Users/shawn/projects/llama-wt-pacing2`.
Reviewed from an isolated snapshot; the worktree was never modified and its suite was never run.

## VERDICT: **APPROVED**

No Critical findings. Three Important findings, all cheap and none of them a
behaviour defect — one test whose name over-promises (already pinned elsewhere),
three stale line citations invalidated by a later task on this same branch, and
the SDD review record for Tasks 8–9 not being committed before the worktree goes
away. The shipped behaviour of all nine tasks is, as far as this review could
measure it, correct and load-bearing.

Deliverable 1's headline: **38 of 39 brief-supplied tests pass the audit.** The
one failure is the already-known Task 5 rollover test, reproduced here
independently. No *new* instance of the "green for a reason other than the one its
name claims" class was found.

---

## Harness proof (both outcomes reachable, and the snapshot really shadows)

Snapshot: `git archive 3693e45 | tar -x -C $D/work/final-quality/snap`.
Runner: `"$WT/.venv/bin/python" -B -m pytest -q -p no:cacheprovider` from the
snapshot root, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH` = the snapshot's three
`packages/*/src` dirs. Never `.venv/bin/pytest`.

**Shadowing proved by import path:**

```
llama  -> .../work/final-quality/snap/packages/llama/src/llama/__init__.py
herder -> .../work/final-quality/snap/packages/herder/src/herder/__init__.py
emcee  -> .../work/final-quality/snap/packages/emcee/src/emcee/__init__.py
```

**Shadowing proved by planted sentinel** — a `raise RuntimeError("SENTINEL-SHADOW-PROOF")`
inserted into the *snapshot's* `herder/usage.py:66` produced tracebacks citing
`packages/herder/src/herder/usage.py:66` under the snapshot rootdir, while
`git status --porcelain` in the worktree stayed empty and
`diff -q snap/.../usage.py $WT/.../usage.py` reported identical files after restore.

**Baseline control:** snapshot, unmutated → `1859 passed, 7 deselected` — matching
the caller's own measurement of the worktree exactly.

**The harness reports all three outcomes** (this took two iterations; the first
version was wrong in exactly the way the mandate warns about):

| control | mutation | result |
| --- | --- | --- |
| CONTROL-GREEN2 | inert `_HARNESS_NOOP = 1` | `SURVIVED` (exit 0, 1859 passed) |
| CONTROL-RED3 | `STALE_MARKER` changed to a never-occurring string | `CAUGHT`, naming `test_stale_marker_is_a_failed_read_not_a_number` |
| CONTROL-CRASH | top-level `raise` in `usage.py` | `HARNESS-ERROR (suite did not run cleanly; NOT a survivor)` |
| CONTROL-A | anchor that matches 0 times | `MUTATION-NOT-APPLIED` |

**The v1 harness scored CONTROL-CRASH as `SURVIVED`** — it had no failing-test
names and no summary line, and "found nothing" was indistinguishable from "never
looked". Fixed by requiring, for a `SURVIVED` verdict, exit code 0 *and* a summary
line reading exactly `1859 passed`; anything else is `HARNESS-ERROR`. The v1 run
also printed `FAILING TESTS (0)` beside `1 failed` because `-rf -rE` silently
overrode each other — fixed to `-rfE`. Both defects were caught by the controls,
before a single real result was recorded.

Every mutation asserts its anchor matches **exactly once** and prints the applied
`diff -u` before the suite runs. Every mutation ran the **full** suite, not a
scoped file.

---

## DELIVERABLE 1 — brief-pinned-test audit

39 tests were supplied by the plan's Step-1 blocks (Task 1: 5, Task 2: 6, Task 3: 3,
Task 4: 7, Task 5: 7, Task 6: 2, Task 7: 4, Task 8: 5). All 39 exist in the shipped
tree under their brief names, and all 39 were compared against the brief text —
they are verbatim except `shows_that_fit`'s three, whose arguments changed from a
`UsageReading` to a `Meter` when the Task 8 defect was fixed (the fix is correct and
made the defect unexpressible).

Predictions were written into `final-quality.log` before each batch ran. The
actual failing sets matched every prediction except two, both noted below.

### Task 1 — `parse_reset`

| # | Brief-supplied test | What it claims | Break applied | That test red? | Verdict |
| --- | --- | --- | --- | --- | --- |
| 1 | `test_parse_reset_accepts_the_dated_usage_form` | the dated `/usage` form parses, minutes included | M1.1 `minute = int(minute_s) if minute_s else 0` → `minute = 0` | **YES** (3 fails, this one first) | PASS |
| 2 | `test_parse_reset_accepts_a_dated_form_with_no_minutes` | minutes are optional (`7am`) | M1.2 made `(?::(\d{2}))?` required | **YES** (7 fails) | PASS |
| 3 | `test_parse_reset_bound_is_per_call_not_global` | the bound is per-call, not a shared constant | M1.3 widened the *default* `max_ahead_s` to 7.5 d | **YES** (4 fails) | PASS |
| 4 | `test_parse_reset_dated_rolls_to_next_year_then_fails_the_bound` | a past date resolves next-year, then fails every bound | M1.4 `for year in (local.year, local.year+1)` → `(local.year,)` | **YES** (1 fail — this one alone) | PASS |
| 5 | `test_parse_reset_still_handles_the_refusal_form_unchanged` | the time-only refusal form is untouched | M1.5 time-only branch always rolls +1 day | **YES** (9 fails) | PASS |

### Task 2 — `parse_usage_text`

| # | Brief-supplied test | What it claims | Break applied | That test red? | Verdict |
| --- | --- | --- | --- | --- | --- |
| 6 | `test_parses_all_three_meters_from_the_real_output` | all three meters parse off the captured `/usage` text | M2.1 `mw = _WEEK_ALL_RE.search(text)` → `mw = None` | **YES** (3 fails) | PASS |
| 7 | `test_per_model_line_does_not_swallow_the_all_models_line` | the `(?!all models)` lookahead | M2.2 dropped the lookahead | **YES** (2 fails) | PASS |
| 8 | `test_stale_marker_is_a_failed_read_not_a_number` | a stale banner is a failed read | M2.3 dropped `or STALE_MARKER in text` (the brief's own mutation 3) | **YES** (1 fail — this one alone) | PASS |
| 9 | `test_missing_session_line_is_a_failed_read` | no session line ⇒ `None` | M2.4 returned an empty `UsageReading` instead of `None` | **YES** (3 fails) | PASS |
| 10 | `test_a_meter_with_no_reset_clause_parses_with_resets_at_none` | an unparsed reset yields `resets_at=None`, not a guess | M2.5 `parse_reset(...) or now` | **YES** (3 fails) | PASS |
| 11 | `test_weekly_reset_uses_the_weekly_bound_not_the_session_one` | the weekly meter uses the weekly bound | M2.6 `SEVEN_DAY_MAX_AHEAD_S = 5.5*3600` (the brief's own mutation 1) | **YES** (3 fails) | PASS |

### Task 3 — `read_usage`

| # | Brief-supplied test | What it claims | Break applied | That test red? | Verdict |
| --- | --- | --- | --- | --- | --- |
| 12 | `test_read_usage_parses_the_json_envelope` | the `{"result": …}` envelope is unwrapped | M3.1 `data.get("result")` → `data.get("results")` | **YES** (3 fails) | PASS |
| 13 | `test_read_usage_degrades_to_none_on_every_failure_shape` | every failure shape collapses to `None` | M3.2 unparsed prose returns an empty reading instead of `None` | **YES** (1 fail — this one alone) | PASS |
| 14 | `test_read_usage_never_raises_when_the_runner_explodes` | a raising runner never propagates | M3.3 `except Exception` → `except ValueError` | **YES** (1 fail — this one alone) | PASS |

Extra probe **P1**: deleting the `if not isinstance(text, str): return None` guard —
I suspected #13's `{"result": None}` and `{"no_result": 1}` arms were redundant with
the later `if not text` inside `parse_usage_text`. They are: #13 stayed green and
`test_read_usage_degrades_to_none_on_malformed_envelope_shapes` (a Task-3 self-audit
addition, not a brief test) is what actually kills it. So the guard *is* pinned, just
not by the brief test that looks like it pins it. Recorded, not a finding — the
brief test's claim ("degrades to None on every failure shape") is literally true of
every shape it lists, and it does redden when that property is broken (M3.2).

### Task 4 — `decide()`

| # | Brief-supplied test | What it claims | Break applied | That test red? | Verdict |
| --- | --- | --- | --- | --- | --- |
| 15 | `test_proceeds_when_both_meters_are_low` | low meters ⇒ `Proceed` | M4.1 `decide`'s terminal `Proceed()` → a `PauseUntil` | **YES** (15 fails) | PASS |
| 16 | `test_session_gate_fires_on_the_projection_not_the_bare_percent` | the gate is on `percent + projected` | M4.2 dropped `+ projected` | **YES** (4 fails) | PASS |
| 17 | `test_weekly_ceiling_outranks_the_session_gate` | weekly is checked first | M4.3 swapped the two `_pause` calls | **YES** (2 fails) | PASS |
| 18 | `test_no_reading_proceeds_rather_than_guessing` | a `None` reading proceeds | M4.4 `None` reading ⇒ `PauseUntil` | **YES** (53 fails — broad, as predicted) | PASS |
| 19 | `test_disabled_pacing_never_gates` | `enabled=False` never gates | M4.5 dropped `not opts.enabled` from the guard | **YES** (1 fail — this one alone) | PASS |
| 20 | `test_pause_without_a_known_reset_falls_back_to_the_unknown_wait` | no reset ⇒ `unknown_reset_wait_s` | M4.6 fallback uses `reset_skew_s` | **YES** (1 fail — this one alone) | PASS |
| 21 | `test_ceiling_boundary_is_strict_greater_than` | at-ceiling proceeds, a hair over pauses | M4.7 `<=` → `<` | **YES** (1 fail — this one alone) | PASS |

Extra probe **P2**: `meter.resets_at + timedelta(seconds=opts.reset_skew_s)` → bare
`meter.resets_at`, to test #16's and #17's second conjunct (the `when` value, not
just the scope). CAUGHT, and both #16 and #17 are in the failing set. Their `when`
assertions are load-bearing, not decoration.

### Task 5 — `pacing_state`

| # | Brief-supplied test | What it claims | Break applied | That test red? | Verdict |
| --- | --- | --- | --- | --- | --- |
| 22 | `test_first_observation_seeds_the_estimate` | first boundary seeds `(delta, 1)` | M5.1 `PacingState(delta, 1)` → `(delta, 0)` | **YES** (3 fails) | PASS |
| 23 | `test_later_observations_are_smoothed` | the EWMA formula | M5.2 `smoothed = delta` | **YES** (4 fails) | PASS |
| 24 | `test_a_window_rollover_contributes_nothing` | **a rollover contributes nothing** | M5.3 deleted `or b.resets_at != a.resets_at` (the brief's own mutation 2) | **NO — STAYS GREEN** | **FAIL** |
| 25 | `test_a_failed_reading_at_either_end_contributes_nothing` | a failed reading at either end contributes nothing | M5.4 the failed-reading arm returns a changed state | **YES** (1 fail — this one alone) | PASS |
| 26 | `test_a_negative_delta_contributes_nothing` | a negative delta contributes nothing | M5.5 `if delta < 0` → `if delta < -1000` | **YES** (1 fail — this one alone) | PASS |
| 27 | `test_state_round_trips_through_disk` | `record` persists, `read_state` reads back | M5.6 `record` writes `per_show_delta: None` | **YES** (3 fails) | PASS |
| 28 | `test_unreadable_state_degrades_to_empty` | bad JSON degrades, never raises | M5.7 `except (OSError,)` only | **YES** (4 fails) | PASS |

**FINDING D1-A (Important) — #24 is green for a reason that is not the one its name claims.**
Reproduced independently here. `packages/llama/src/llama/pacing_state.py:54` reads

```python
    if b is None or a is None or b.resets_at != a.resets_at:
```

Delete `or b.resets_at != a.resets_at` and the full suite yields **exactly one**
failure — `packages/llama/tests/test_pacing_state.py::test_a_rollover_with_a_positive_delta_still_contributes_nothing`,
which Task 9 added. The brief's own `test_a_window_rollover_contributes_nothing`
stays green, because its fixture is `observe(_r(90), _r(2, OTHER_RESET), …)`: a
**−88** delta, which the *negative*-delta guard on the next line catches regardless
of the rollover guard. Its name advertises coverage of a guard it cannot see.

Prediction correction, recorded honestly: I predicted M5.5 (relaxing the negative
guard) would also redden #24, exposing the overdetermination from the other side.
It did not — with the rollover guard still present, #24 short-circuits there. So
#24 is green under *either* guard alone and pinned by *neither* specifically. That
is precisely the pathology.

**Recommended fix (one line, not blocking):** change #24's fixture to a positive
delta across a rollover — `ps.observe(_r(90), _r(92, OTHER_RESET), seeded)` — so the
test is pinned by the guard its name names. Task 9's test then becomes a duplicate
and may be folded in or kept. Do **not** simply delete Task 9's test on the grounds
that #24 "already covers it"; today it does not, and that mistake is the whole risk
this finding is about.

### Task 6 — the run-level `RateLimited` catch

| # | Brief-supplied test | What it claims | Break applied | That test red? | Verdict |
| --- | --- | --- | --- | --- | --- |
| 29 | `test_ratelimited_during_winnow_checkpoints_instead_of_exiting` | a limit in winnow checkpoints rather than propagating | M6.1 the run-level catch re-raises unconditionally | **YES** (5 fails) | PASS |
| 30 | `test_run_level_ratelimited_is_caught_before_herdererror` | ordering vs the `HerderError` superclass | M6.2 inserted `except HerderError` **before** it (the brief's own mutation 4) | **YES** (7 fails) | PASS |

Extra probe **P3**: `_checkpoint_pause`'s `getattr(limited, "scope", None)` → `None`,
to test #29's second conjunct (`marker["pause_scope"] == "five_hour"`). CAUGHT, #29
in the failing set. #29's marker assertions are load-bearing.

### Task 7 — the proactive gate

| # | Brief-supplied test | What it claims | Break applied | That test red? | Verdict |
| --- | --- | --- | --- | --- | --- |
| 31 | `test_preflight_gate_pauses_before_any_stage_runs` | the gate fires **before** `run_search` | M7.1 (2 edits) the pre-flight verdict deferred to *after* `run_winnow`, still pausing | **YES** (2 fails; `searched == []` is what breaks) | PASS |
| 32 | `test_per_show_gate_stops_between_shows` | reading order pre-flight / before-a / after-a / before-b | M7.2 the after-show read replaced by the before reading (collapses 4 reads to 3) | **YES** (4 fails) | PASS |
| 33 | `test_gate_is_skipped_entirely_on_a_non_claude_cli_backend` | no meter read on a non-`claude_cli` backend | M7.3 `_meter_applies` → `return pace.enabled` | **YES** (3 fails) | PASS |
| 34 | `test_a_preflight_pause_exits_zero_like_every_other_pause` | `_execute` returns normally | M7.4 pre-flight `return` → `raise typer.Exit(1)` | **YES** (4 fails) | PASS |

M7.1 is the mutation the method requirements exist for: a *deletion* of the gate
would have reddened #31 too and proved nothing about ordering. Relocating it —
gate still fires, session still `PAUSED`, only `searched` changes — is what
isolates the ordering claim. #31 broke on `searched == []`, exactly as predicted.

Caveat on #34, matching deferred minor T7/#46: the test asserts `_execute` returns
without raising and that the session is `PAUSED`; it never inspects a process exit
code, because `_drive` calls `_execute` directly. M7.4 reddens it via the raised
`typer.Exit`, so the claim *is* pinned at the level the test operates at — the name
"exits zero" is a shade broader than the body. Cosmetic; see D2.

### Task 8 — `shows_that_fit` and `llama pacing`

| # | Brief-supplied test | What it claims | Break applied | That test red? | Verdict |
| --- | --- | --- | --- | --- | --- |
| 35 | `test_shows_that_fit_uses_the_ceiling_not_a_hundred` | headroom measured to the ceiling | M8.1 `(ceiling - percent)` → `(100 - percent)` | **YES** (14 fails) | PASS |
| 36 | `test_shows_that_fit_is_unknown_without_an_estimate` | `None` ≠ 0 | M8.2 returns `0` instead of `None` | **YES** (5 fails) | PASS |
| 37 | `test_shows_that_fit_floors_at_zero_when_already_over` | floors at zero | M8.3 dropped `max(0, …)` | **YES** (1 fail — this one alone) | PASS |
| 38 | `test_pacing_command_reports_meters_and_forecast` | `llama pacing` prints `5h N%` and `weekly N%` | M8.4 `5h ` label → `5hr ` | **YES** (5 fails) | PASS |
| 39 | `test_pacing_command_says_so_when_the_meter_cannot_be_read` | it says "unavailable" | M8.5 reworded the sentence | **YES** (3 fails) | PASS |

Extra probe **P4**: dropped the weekly clause from `_pacing_line`, testing #38's
second conjunct. CAUGHT, #38 in the failing set.

The Task 8 defect the caller described (a `UsageReading` is not `None`, so
`not per_show_delta` short-circuited before the argument type mattered) is **fixed
at the type level**: `shows_that_fit` now takes a `Meter`, and #36's second assert
is `shows_that_fit(None, 4.2, 90) is None` on a meter. The shape that permitted the
bug can no longer be written. Good fix — better than a test would have been.

### Audit summary

**38 PASS / 1 FAIL.** The one failure is D1-A, an independent third derivation of the
already-known Task 5 defect. No new instance of the class was found across the other
38, including four extra conjunct probes (P1–P4), all of which came back CAUGHT.

---

## DELIVERABLE 2 — triage of the 61 deferred minors

Verdicts: **FIX** = fix before merge. **LEAVE** = ship as is. **CLOSED** = already fixed on
this branch; the ledger entry is stale. Items I re-graded are marked.

### Task 1 — `limits.py` (11 entries)

| # | Entry | Verdict | Reason |
| --- | --- | --- | --- |
| 1 | M1 dead minute-range check `limits.py:87-88` | LEAVE | Defensive; `int(minute_s)` on a `\d{2}` group can only be 0–99, and the `ValueError` arm below is the real net. Deleting it costs a review argument and buys nothing. |
| 2 | M2 `_dated_target` docstring contradicted by the Jan-2 test | LEAVE | The docstring says a past date "resolves a full year out, which no caller's bound admits"; the Jan-2 case resolves 2 days out because *now* is Dec 31. Both statements are true of their own case. Prose could be sharper; not wrong. |
| 3 | M3 stale `_RESET_RE` header comment | LEAVE | Same text as #11; the comment describes `_RESET_RE`'s own behaviour, which is still accurate at that pattern's level. `parse_reset`'s docstring carries the composite contract. |
| 4 | M4 month regex accepts "Sepxyz"; `month_s[:3]` a no-op | LEAVE | `[A-Za-z]{3}[a-z]*` deliberately admits "September"; the `_MONTHS.get` lookup rejects a genuine non-month. Over-acceptance here degrades to `None`, the safe direction. |
| 5 | M5 ambiguous fall-back hour resolves `fold=0` | LEAVE | One hour, twice a year, resolving to the *earlier* instant — i.e. waking early and retrying. Wrong side by an hour on a multi-hour pause; the reactive backstop covers it. Not worth the DST machinery. |
| 6 | M6 asymmetric branches; time-only path still inline | LEAVE | A refactor with no behaviour change, in a function whose two branches have genuinely different shapes (one infers a year, one infers a day). Merging them would obscure that. |
| 7 | M7 `max_ahead_s` default binds `MAX_RESET_AHEAD_S` at import | LEAVE | Standard Python default-argument semantics. Monkeypatching a module constant to change a default is not a pattern this repo uses. |
| 8 | M8 `classify()` still passes the session bound; dated form unreachable from refusals | LEAVE | Correct as designed: a refusal names a *session* reset, so the session bound is the right one. If the 7-day refusal wording ever appears in `~/.llama/llm-failures/`, this is where it gets revisited — deliberately unbuilt until measured. |
| 9 | M9/M10 two test names/duplications wanting comments | LEAVE | Cosmetic. |
| 10 | spec-minor: dated branch has no fall-through to `_RESET_RE` | LEAVE | `parse_reset`'s docstring now states the one-clause contract explicitly, and `test_dated_form_wins_when_a_text_carries_two_reset_clauses` pins the resolution. Callers slice per-line (`usage.py`'s `(.*)$` tails). Documented, pinned, deliberate. |
| 11 | spec-minor: `_RESET_RE` comment now false at parser level | LEAVE | Duplicate of #3. |

### Task 2 — `usage.py` parser (9 entries)

| # | Entry | Verdict | Reason |
| --- | --- | --- | --- |
| 12 | unused `json`/`subprocess` imports | **CLOSED** | Verified: `usage.py:20,22` are both consumed by Task 3's `read_usage`/`_cli_runner` (lines 99, 102, 123, 124). Stale entry. |
| 13 | `STALE_MARKER` case-sensitive | LEAVE | The marker is a captured literal from the CLI's own output. Case-folding it would be guessing at a string nobody has seen vary. |
| 14 | percent unbounded — "999%" parses | LEAVE | Fails safe: a 999% reading pauses, which is the direction pacing exists to err in. The entry says so itself. |
| 15 | `frozen=True` is shallow; `per_model` dict mutable | LEAVE | No caller mutates it; readings are constructed and read once per boundary. |
| 16 | `UsageReading` unhashable | LEAVE | Nothing hashes one. |
| 17 | "all models" literal duplicated across two regexes | LEAVE | Two regexes, deliberately: one matches it, one excludes it. Factoring the literal out would make the lookahead's purpose harder to read, not easier. |
| 18 | `test_missing_session_line` `""` case redundant; `None` input untested | LEAVE | `parse_usage_text(None)` is off-contract (`text: str`) and `if not text` handles it anyway. |
| 19 | test name at `test_usage.py:31` broader than its body; "(All models)" defeats it silently | LEAVE | Real but narrow: a capitalisation change in the CLI's own output would defeat the lookahead. Same class as #13 — do not defend against unobserved variants of a captured literal. |
| 20 | bound **values** unpinned (5.5 h → 24 h and 7.5 d → 30 d both survive) | **LEAVE, but confirmed by measurement** | I verified both: **V1** `FIVE_HOUR_MAX_AHEAD_S = 24*3600` → SURVIVED (1859 passed). **V2** `SEVEN_DAY_MAX_AHEAD_S = 30*86400` → SURVIVED. Only the *identity* (which meter uses which bound) is pinned, by M2.6. Contrast **V3**: `MAX_RESET_AHEAD_S = 24*3600` in `limits.py` → CAUGHT (3 tests). The magnitudes are a policy sanity bound, not behaviour; a wrong one can only over-admit a reset that the meter itself produced. Leave, but this is the most defensible candidate on the whole list if anyone wants one more test. |

### Task 3 — `read_usage` / `_cli_runner` (7 entries)

| # | Entry | Verdict | Reason |
| --- | --- | --- | --- |
| 21 | no `is_error` guard, unlike `claude_cli.py:139` | **RE-GRADED: borderline, still LEAVE** | This is the closest thing on the list to a real gap — it is the same *class* as `STALE_MARKER` (the command succeeds and the payload lies). But `/usage` is not an inference call, `is_error` is about turn failures, and an `is_error` envelope would carry prose that `parse_usage_text` rejects anyway, collapsing to `None`. Defence in depth, not a hole. Worth a sentence in `read_usage`'s docstring if someone is editing it anyway. |
| 22 | mid-file `import json` at `test_usage.py:129` (E402) | LEAVE | Verified at line **130**, not 129 — the citation is off by one. Brief-mandated placement, no linter in CI. |
| 23 | "every failure shape" test omits the stale banner its own docstring names | LEAVE | The stale banner is pinned one layer down by `test_stale_marker_is_a_failed_read_not_a_number`, which M2.3 confirms is the sole killer of that guard. |
| 24 | `_cli_runner`'s `binary`/`timeout_s` params unused; missing annotations | LEAVE | Both are exercised as defaults by `test_cli_runner_uses_neutral_cwd_and_subprocess_env` (`seen["timeout"] == 60`). Injection points, not dead parameters. |
| 25 | `_cli_runner` does not close the child's stdin | LEAVE | `claude -p "/usage"` reads no stdin. `claude_cli` passes `input=` because it has a prompt to pass. |
| 26 | `_FakeProc` re-declares `test_claude_cli.FakeProc` | LEAVE | Cross-package test-helper sharing (herder tests → herder tests, but different modules) buys coupling for eight lines. |
| 27 | the argv assertion assumes `ISOLATION_ARGS` is `cmd`'s tail | LEAVE | It is, by construction (`*ISOLATION_ARGS` is last in the list literal), and a change would fail loudly. |

### Task 4 — `decide()` / config (5 entries)

| # | Entry | Verdict | Reason |
| --- | --- | --- | --- |
| 28 | int-literal defaults (90) under a `float` annotation | LEAVE | Pydantic coerces on load; `test_default_config_template_matches_defaults` pins the pairing (verified: **P5** `five_hour_ceiling = 80` in the TOML → CAUGHT, exactly that test). |
| 29 | `if projected` omits the estimate at exactly 0.0 | LEAVE | A 0.0 estimate renders no `est` clause, and `shows_that_fit` treats it as "no estimate" (`test_shows_that_fit_treats_a_zero_estimate_as_no_estimate`). Consistent across both renderers. |
| 30 | `reading` untyped in `decide`/`_pause` | LEAVE | Explicitly deliberate — it keeps `llama.pacing` free of a `herder.usage` import, which is the layering the file exists to preserve. |
| 31 | `PaceOptions` frozen-ness unpinned | LEAVE | Cosmetic; the docstring explains why it is frozen and nothing mutates it. |
| 32 | `Progress`'s default is unreachable; window label derived by `else` | LEAVE | Both true and both harmless. Every production call passes the field positionally. |

### Task 5 — `pacing_state` (7 entries)

| # | Entry | Verdict | Reason |
| --- | --- | --- | --- |
| 33 | `samples` validated far looser than `delta` (accepts −3, `true`, `"7"`) | LEAVE | `samples` is display/diagnostic only; nothing branches on it. `delta` is the value `decide` consumes, which is why it is the one hardened. |
| 34 | `PacingState(None, samples>0)` producible by `read_state`, discarded by `observe`'s seed branch | LEAVE | Reachable only from a hand-edited state file; the outcome is one re-seeded estimate. |
| 35 | missing `delta` key unpinned in the under-estimate direction | LEAVE | A missing key yields `None` → no estimate → `projected = 0.0` → the gate falls back to the bare percent, and the reactive backstop still fires. |
| 36 | `_five`'s None-guard is dead code | **LEAVE, confirmed by measurement** | **V5** removing `if reading is not None else None` → SURVIVED (1859 passed). It is genuinely redundant, since `getattr(None, "five_hour", None)` is already `None`. Harmless, and self-documenting about the shape it accepts. |
| 37 | the `resets_at` guard silently no-ops when both are `None` | LEAVE | Both-`None` means two readings with unparsed resets; folding them is the *only* safe reading of that state, and the entry concedes it is the safe direction. |
| 38 | `record`'s docstring names the meter bias where it means lost update | **FIX (trivial, docs-only)** | The docstring's justification for the lock is a read-modify-write race, not the account-wide-meter bias described one paragraph up. Two sentences that read as one argument. Fix while the stale citations below are being fixed — same file, same commit. |
| 39 | three redundant tests; `float(delta)` coercion beyond the ruling's literal text | LEAVE | Redundant tests are cheap; the coercion is correct. |

### Task 6 — the run-level catch (3 entries, one of them a bundle of nine)

| # | Entry | Verdict | Reason |
| --- | --- | --- | --- |
| 40 | bundle: unreachable `getattr` default on `.scope`; `when or` truthiness on a datetime; redundant `failures or []`; a test name promising ordering its body doesn't check; docstring plural "sites"; three params with no caller until T7; pause text split stderr/stdout unlike the loop; no CliRunner-level pause test; leftover local `import json` | LEAVE (all nine) | Every one is cosmetic or was resolved by Task 7 supplying the callers. The one with any teeth — `when or resume_at(...)` treating a datetime as truthy — cannot misfire: a `datetime` is always truthy, and P3/`test_checkpoint_pause_keeps_a_precomputed_instant_verbatim` pins the pass-through. The stderr/stdout split is worth one sentence in a docstring if anyone touches `_checkpoint_pause`; not now. |
| 41 | spec's "### Known gap" H3 spliced between bullets 2 and 3 — **"FLAG AT MERGE"** | **CLOSED** | Verified in `3693e45`: the heading sits at spec line 41, *after* all three bullets (lines 18–39). Fixed on-branch. The flag can be dropped; I am recording the verification so the parent does not chase it. |
| 42 | `cli.py:2556` (profile-creation `run_interpret`) has no local comment | LEAVE as written, but **the line number is now wrong** — see D3-B. The call is at `cli.py:2760` in `3693e45`. |

### Task 7 — the gate wiring (5 entries)

| # | Entry | Verdict | Reason |
| --- | --- | --- | --- |
| 43 | held/failed shows folded while `Locked` is excluded — defensible, undocumented, unpinned | **RE-GRADED: pinned, LEAVE** | Not unpinned: **P6** dropping the `ran` conjunct → CAUGHT by `test_a_deferred_show_is_not_a_boundary`, and **P7** dropping `reading_before is not None` → CAUGHT by two tests. Both halves of `if ran and reading_before is not None:` (`cli.py:508`) are load-bearing. The *documentation* gap (why held/failed count as boundaries but `Locked` does not) is real and is answered by the comment at `cli.py:509-521`, which does say it. Close. |
| 44 | 2N+1 meter reads | LEAVE | A deliberate, documented trade — `pacing_state.py`'s docstring argues it explicitly, and a meter read is not an inference call. Halving it would reintroduce the before-N/before-N+1 attribution error Ruling R14 removed. |
| 45 | `pacing_state.py`'s docstring describes a protocol its only caller doesn't use | **CLOSED** | Fixed by `6db6ed4`; the docstring now describes before/after. But that fix introduced the stale citations in D3-B below. |
| 46 | `test_a_preflight_pause_exits_zero` never checks an exit code | LEAVE | Confirmed in the D1 audit (#34): the name is a shade broader than the body, but M7.4 shows the claim is pinned at the level `_drive` operates at. A `CliRunner`-level test would be the honest version; low value. |
| 47 | the deferred second pass is ungated **and** takes a blocking lock, so its reading can be stale by the whole wait; pre-flight gate sits above the raw-output-capture comment | **RE-GRADED: the ungated deferred pass is the one entry I would call Important-adjacent — but LEAVE** | Real: the second pass (`cli.py:527-532`) processes shows another run had locked, blocking on each lock, with no gate between them. A run that waited an hour on a lock then processes N shows without consulting the meter. Mitigations: it only runs when `limited` is falsy, it processes only shows that were `Locked` (a minority), and the reactive `RateLimited` catch inside `_process` still fires. Cost of the bug is a refused show, which is exactly the failure mode phase 2 accepts as its backstop. Leave, but this is the strongest candidate for a phase-3 line. |

### Task 8 — `llama pacing` and the forecast (11 entries)

| # | Entry | Verdict | Reason |
| --- | --- | --- | --- |
| 48 | commit `ea14004`'s message says "(16 passed)" where the actual was 13 | LEAVE | History is immutable by dispatch rule; the named command reproduces. |
| 49 | spec asks for "the three meters"; only two render (`per_model` never displayed) | LEAVE | Brief/spec gap, not an implementation error — and the right call: the per-model meter is one line of an operator-facing summary with no gate behind it. |
| 50 | the unavailable line has no `pacing:` prefix | **CLOSED** | Fixed by `3693e45` (the branch tip). Verified: `cli.py:274` returns `"pacing: usage read unavailable — …"`. |
| 51 | the shortfall clause can name "the reset" on a line carrying no reset time when `resets_at` is `None` | LEAVE | Reachable only from a meter whose reset clause did not parse. The sentence is then vague rather than wrong. |
| 52 | `astimezone()` is machine-local — CORRECT; flagged so nobody "fixes" it to UTC | LEAVE (informational) | Right call, and the entry exists precisely to prevent the wrong fix. Keep it recorded. |
| 53 | `CLAUDE.md`'s new clause omits the verdict line | **FIX (trivial, docs-only)** | Verified: the clause describes the meters, the learned cost and the forecast, but not the `would proceed` / `would pause: …` line the command also prints. `CLAUDE.md` is this repo's primary orientation document; one clause. |
| 54 | a `five_hour=None` reading is UNREACHABLE in production; `_pacing_line`'s arm and `test_a_window_with_no_meter_does_not_compete`'s only-weekly half are defensive-only AND mutually inconsistent | **RE-GRADED: LEAVE, but it is the most interesting entry on the list** | Correct on both counts: `_SESSION_RE` is mandatory, so `parse_usage_text` returns `None` outright rather than a session-less reading. And the inconsistency is real — `binding_forecast` would forecast a weekly-only reading that `_pacing_line` short-circuits past. Neither can fire today. Consolidating them would mean deleting a guard on the basis that a parser two modules away happens to make it unreachable; that coupling is worse than the redundancy. Leave, and leave the ledger entry as the record of why. |
| 55 | `binding_forecast` computed twice on the `_execute` path | LEAVE | Verified (`cli.py:284` inside `_pacing_line`, `cli.py:332` beside it). Pure and cheap. Threading it through would mean `_pacing_line` returning a tuple, which is worse. |
| 56 | docs drift on G2 — plan `:1496` and spec `:405` still show the unprefixed sentence | **FIX (trivial, docs-only)** | Verified both citations exact and both still stale after `3693e45` prefixed the code. Two one-word edits. Bundle with #53. |
| 57 | a 5-hour reset crossing midnight renders as a bare `02:00` with no date | LEAVE | Ruled on twice; reads as "tonight", which is what it means for a ≤5.5 h window. |
| 58 | the `load_config(None)` mutant's kill is mildly environment-coupled | LEAVE | Two of its three killers are config-content tests. |

### Task 9 — the mutation pass (3 entries)

| # | Entry | Verdict | Reason |
| --- | --- | --- | --- |
| 59 | the Task 9 report's Concern #4 provenance claim is unevidenced | LEAVE | A claim about a report, not about the code. |
| 60 | additional mutation A (`FIVE_HOUR_MAX_AHEAD_S`) is a near-token extension | LEAVE | Accurate self-criticism. Independently relevant: my **V1** shows the *value* of that constant is unpinned entirely (see #20) — so the near-token mutation was not merely easy, it was also testing the identity rather than the magnitude. Recorded together. |
| 61 | PLAN/BRIEF doc corrections, three in Task 9's text alone — Step 1 names a structurally-incapable test, omits two real ones; Step 2 names a test that does not pin the guard; Step 4's wording prescribes the swallowing arm | **FIX (docs-only) — the highest-value entry on this list** | Step 2's error is D1-A itself: the plan told the executor to mutate the rollover guard and expect `test_a_window_rollover_contributes_nothing` to fail, and that expectation is false. The plan is committed (`docs/superpowers/plans/2026-09-05-usage-pacing-phase2.md`) and will be read by whoever does phase 3. Leaving a plan in the tree that names the wrong test for a known-defective pin is how the defect gets re-derived a fourth time. Correct Step 2 to name `test_a_rollover_with_a_positive_delta_still_contributes_nothing`, or fix the fixture per D1-A and leave the name. |

**Triage totals: 4 FIX (all docs/comments: #38, #53, #56, #61) · 53 LEAVE · 4 CLOSED (#12, #41, #45, #50).**
None of the FIX items blocks the merge; all four are one-to-three-line edits in a
single commit. **Re-graded from the ledger's own framing: #20, #21, #36, #43, #47,
#54, #60** — of these only #43 changed verdict materially (it is *pinned*, contrary
to the entry, which I proved with P6/P7).

---

## DELIVERABLE 3 — whole-branch quality

### D3-A (Important) — the SDD review record for Tasks 8 and 9 is not in the repo

`docs/superpowers/2026-09-05-usage-pacing-phase2-verdicts/` contains `t1*`–`t7*` and
`_global-constraints.md`. There is **no `t8*` or `t9*`**. The committed ledger
(`docs/superpowers/2026-09-05-usage-pacing-phase2-sdd-ledger.md`, added by `6f7c126`)
ends with the literal line:

```
=== RUN STOPPED HERE, at a clean boundary, per the parent's instruction. Tasks 8 and 9 NOT started. ===
```

`.superpowers/` is gitignored (`.gitignore:6`), so every Task 8 and Task 9 verdict,
and the ledger's own Tasks 8–9 half, lives only in the worktree's scratch directory.
This repo's own durable rule — recorded after the tail-guard worktree was removed —
is to copy the SDD ledger into the main repo *before* removing a worktree. Two of
nine tasks, including the mutation pass that is the branch's own quality evidence,
are one `rm -rf` from being unreconstructible.

**Fix:** before the worktree is torn down, commit the Task 8 and Task 9 verdict files
and refresh the ledger's tail (in particular, delete the "Tasks 8 and 9 NOT started"
line, which is now false in the committed tree). One commit.

### D3-B (Important) — three line citations, exact when written, invalidated by Task 8

The most consequential is in **shipped source**:

`packages/llama/src/llama/pacing_state.py:4` (module docstring):
> A reading taken AFTER a show minus the one taken before it is exactly that
> show's cost (`cli.py:389` and `cli.py:426`).

Verified: `cli.py:389` in `3693e45` is `# says why wrapping it would not help.`
and `cli.py:426` is `typer.echo(f"Shortlist awaits review: …")`. The lines it means
are **486** (`reading_before = _meter(config, pace)`) and **523** (the after-read
inside `pacing_state.record(...)`).

Two more in the shipped spec, `docs/superpowers/specs/2026-09-05-usage-pacing-phase2-design.md`:
- run_interpret at `cli.py:440` and `cli.py:2556` → actually **607** and **2760**.
- `_PIPELINE_RUN_STAGES` at `cli.py:1186` → actually **1353**.

(Deferred minor #42 reuses the now-stale `2556`.)

I traced the provenance rather than assuming rot: at `6db6ed4`, `cli.py:389/426`
were **exactly** `reading_before = _meter(config, pace)` and the after-read; at
`a3d8cdc`, `cli.py:440/1186/2556` were **exactly** the three lines named. Task 8
then added ~134 lines above them (`cli.py` went 2775 → 2909 lines) and silently
invalidated all five numbers. Nobody wrote anything careless — the branch simply has
no mechanism for noticing this, and it has bitten this project before
(`8ab8dd7 docs(spec): correct the status line and a stale audit note's line numbers`
is on `main`).

**Fix:** update the five numbers; or, better for the source docstring, cite the
symbol instead of the line (`_execute`'s `reading_before` / the `pacing_state.record`
call), which cannot rot.

### D3-C (Minor) — the offline-suite guard can silently lapse

`packages/llama/tests/conftest.py:38`:

```python
    monkeypatch.setattr(cli, "read_usage", lambda *a, **kw: None, raising=False)
```

`raising=False` was correct while the fixture was written ahead of Task 7's import.
It is now a permanent permission to fail silently: if a later refactor renames the
binding (e.g. `from herder import usage` + `usage.read_usage()`), the autouse guard
becomes a no-op, and the whole suite starts spawning `claude -p "/usage"` — a real
subprocess, a real network call, and real usage-window spend, from a suite whose
contract is "offline and deterministic". Dropping the two words makes the lapse loud.

### D3-D (Minor) — `_meter_applies` keys on `llm_for("default")` only

`cli.py:220` gates on `config.llm_for("default").backend == "claude_cli"`.
`Config.llm_for` (`config.py:157`) is `self.llm.get(task) or self.llm.get("default") or LLMTaskConfig()`.
So a mixed config with `[llm.default] backend = "openrouter"` but a per-task
`backend = "claude_cli"` burns a claude_cli window while the meter is never read.
Exotic, and the reactive `RateLimited` backstop still covers it. Noted so the
gate's scope is on the record; no change recommended.

### D3-E (Minor) — the two new ceilings have no range validation

`PacingConfig` validates its three duration strings with `@field_validator`, but
`five_hour_ceiling` / `seven_day_ceiling` take any float. `= 500` silently disables
the proactive gate; `= -5` pauses at every boundary. The first is the silent one.
Both are hand-typed by a single operator into a file this design already expects
them to hand-edit, and both fail visibly on the first run, so this is genuinely
minor — but the asymmetry with the sibling fields is worth a `ge=0, le=100`.

### What is good, and worth saying

- **`shows_that_fit(meter, …)` instead of `shows_that_fit(reading, …)`.** The Task 8
  fix (`2df1de9`) removed the bug by removing the shape that could express it, and
  the docstring records the exact wrong line that shipped (`weekly 84% … ~17 fit`).
  This is the strongest single piece of work on the branch.
- **`_meter_applies` extracted from `_meter`.** The docstring's argument — that
  collapsing three causes of `None` is right for a caller that wants the number and
  wrong for one that has to *say* something about it — is the reason the "pacing on
  limit errors only" sentence is never printed when it would be false. Verified by
  M7.3 (3 tests) and the four run-start-line tests.
- **`PauseUntil.__str__` returning `reason`.** One method that lets `_checkpoint_pause`
  render a `RateLimited` and a `PauseUntil` identically, with a docstring saying what
  a `dataclass` repr would have put in the operator's session marker.
- **No unused imports** across all six changed source files (AST scan). `shows_that_fit`
  was correctly dropped from `cli.py`'s import list when `binding_forecast` replaced it.
- **The `except RateLimited` ordering** is pinned twice over — M6.2 (the brief's own
  mutation, 7 fails) and the ordering comment at the catch site.
- **Every constant this branch adds that is behaviourally load-bearing is pinned**:
  `EWMA_ALPHA` (V4 → CAUGHT), the config ceilings (P5 → CAUGHT), `MAX_RESET_AHEAD_S`
  (V3 → CAUGHT). Only the two `usage.py` bounds' magnitudes are not (V1/V2), and
  that is deliberate — see D2 #20.

---

## Findings by grade

**Critical:** none.

**Important (3):**
1. **D1-A** — `test_a_window_rollover_contributes_nothing` is green under deletion of
   the guard its name claims; only Task 9's test pins it. One-line fixture fix.
2. **D3-A** — Tasks 8 and 9 verdicts and the ledger's Tasks 8–9 half are not committed,
   and `.superpowers/` is gitignored. Commit before the worktree is removed.
3. **D3-B** — five stale `cli.py:NNN` citations (one in shipped source, four in the
   spec), all exact when written and invalidated by Task 8's additions.

**Minor:** D3-C (`raising=False`), D3-D (`llm_for("default")` scope), D3-E (unvalidated
ceilings), plus the four FIX entries from the D2 triage (#38, #53, #56, #61) and the
53 LEAVE entries.

**Blocking:** none. All three Importants are documentation, record-keeping, or a
one-line test fixture; none changes shipped behaviour, and the behaviour they concern
is correct today.

---

## Commands run (all against the isolated snapshot)

```bash
D=/Users/shawn/projects/llama/.superpowers/sdd/2026-09-05-usage-pacing-phase2
WT=/Users/shawn/projects/llama-wt-pacing2
S="$D/work/final-quality/snap"

mkdir -p "$D/final-quality" && touch "$D/final-quality/final-quality.log"
mkdir -p "$S" && cd "$WT" && git archive 3693e45 | tar -x -C "$S"

export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$S/packages/llama/src:$S/packages/herder/src:$S/packages/emcee/src"
cd "$S" && "$WT/.venv/bin/python" -B -m pytest -q -p no:cacheprovider
#   -> 1859 passed, 7 deselected, 26 warnings in 6.79s      (baseline control)

# 55 harness runs via $D/work/final-quality/mutate.py:
#   39 targeted audit mutations  M1.1-M1.5 M2.1-M2.6 M3.1-M3.3 M4.1-M4.7
#                                 M5.1-M5.7 M6.1-M6.2 M7.1-M7.4 M8.1-M8.5
#    7 conjunct/lead probes       P1-P7
#    5 ledger-claim verifications V1-V5
#    4 harness controls           CONTROL-A / -GREEN2 / -RED3 / -CRASH
# Each: assert the anchor matches exactly once, print the diff, run the FULL
# suite, restore, classify CAUGHT / SURVIVED / HARNESS-ERROR / NOT-APPLIED.

cd "$WT" && git status --porcelain      # empty, before and after
diff -r -q "$S/packages" "$WT/packages" # no differing files after restore
cd "$S" && "$WT/.venv/bin/python" -B -m pytest -q -p no:cacheprovider
#   -> 1859 passed, 7 deselected                            (snapshot pristine)
```

Full per-mutation output, including every applied diff and every failing-test list,
is in `$D/final-quality/final-quality.log`. The harness is
`$D/work/final-quality/mutate.py`.

**Isolation honoured:** the worktree was never written to, its suite was never run,
and no `.venv/bin/*` console script was invoked from the snapshot. No commits produced.
No tool refused any call during this review.
