# Task 9 verification — independent reproduction of the mutation pass

## Verdicts

**Mutation-report verdict: VERIFIED.**
All six mutations were re-run independently on a fresh snapshot of `3693e45`, with the
expected red set written down before each run. **Every numeric claim and every named test
in `$D/t9/report.md` reproduced exactly.** No fabricated result, no rounded-to-CAUGHT
mutant, no unreproducible claim.

Two non-falsifying corrections (details in Findings): the report never ran a full suite
under any mutation, so its mutation-6 blast radius (16) is the in-file figure — the
whole-suite figure is **18**; and the "brief's own contingency" it quotes is not in
`$D/briefs/task-9-brief.md`.

**Spec-compliance verdict: PASS.** A no-commit outcome is the correct discharge of this
brief. Nothing was skipped.

## Harness proof (both outcomes, and that my snapshot really shadowed the source)

Isolation as mandated: the worktree was never modified and its suite was never run by me.
Snapshot: `git archive 3693e45 | tar -x -C $D/work/t9-verify/snap`, then `git init` inside
the snapshot so every mutation could be shown by `git diff` and reverted by `git checkout`.

Runner (`$D/work/t9-verify/run.sh`) — never a `.venv/bin/*` console script:

```
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$SNAP/packages/herder/src:$SNAP/packages/llama/src:$SNAP/packages/emcee/src"
cd "$SNAP" && exec "$WT/.venv/bin/python" -B -m pytest -p no:cacheprovider "$@"
```

The worktree venv turned out to use plain path-append `.pth` files
(`_editable_impl_llama_radio.pth` = one line, `/Users/shawn/projects/llama-wt-pacing2/packages/llama/src`),
not a `MetaPathFinder`, so `PYTHONPATH` can shadow them — but I proved it rather than
assuming it.

**Provenance check:**
```
llama:  .../work/t9-verify/snap/packages/llama/src/llama/__init__.py
herder: .../work/t9-verify/snap/packages/herder/src/herder/__init__.py
emcee:  .../work/t9-verify/snap/packages/emcee/src/emcee/__init__.py
```

**Planted-sentinel proof** (a `raise` prepended to each of the three modules I would
mutate; the traceback cites the SNAPSHOT path, so the snapshot is what runs):
```
packages/herder/src/herder/usage.py:1: in <module>
    raise RuntimeError('SNAPSHOT-SENTINEL-HERDER-USAGE')
packages/llama/src/llama/pacing_state.py:1: in <module>
    raise RuntimeError('SNAPSHOT-SENTINEL-PACING-STATE')
packages/llama/src/llama/cli.py:1: in <module>
    raise RuntimeError('SNAPSHOT-SENTINEL-CLI')
```

**Control (passing):** unmutated snapshot, full suite → `1859 passed, 7 deselected, 26
warnings in 7.02s` — identical to the orchestrator's own worktree measurement.
**Control (failing):** the sentinels above, and every mutation below, produced named
`FAILED ...` lines.
**Final control:** after all seven mutations were reverted, full suite → `1859 passed, 7
deselected` again, and `git status --porcelain` in the snapshot is empty.

Every mutation was applied by a Python edit that **asserts the anchor matched exactly
once** and was then shown by `git diff` before any test ran. For the two `cli.py` sites I
anchored on `"\n    except RateLimited as exc:\n"` (leading newline + 4 spaces), which
cannot match the 8-space per-show arm — verified by printing both counts (4-space anchor: 1;
8-space arm: 1, untouched) and by re-grepping the arm line numbers after each edit.

Worktree state before and after my work: `git rev-parse --short HEAD` = `3693e45`,
`git status --porcelain` empty. I ran only read-only git there.

## Line citations verified

| Citation | Printed line | OK |
| --- | --- | --- |
| `pacing_state.py:54` | `    if b is None or a is None or b.resets_at != a.resets_at:` | yes |
| `usage.py:67` | `    if not text or STALE_MARKER in text:` | yes |
| `usage.py:79` / `usage.py:83` (the two `SEVEN_DAY_MAX_AHEAD_S` call sites) | both `max_ahead_s=SEVEN_DAY_MAX_AHEAD_S` | yes |
| `usage.py:30/31` (the two constants) | `FIVE_HOUR_MAX_AHEAD_S = 5.5 * 3600` / `SEVEN_DAY_MAX_AHEAD_S = 7.5 * 86400` | yes |
| `cli.py:382` run-level arm, `cli.py:444` per-show arm | `except RateLimited as exc:` at 4 and 8 spaces respectively | yes |

File sizes, for the arithmetic below: `test_usage.py` 22, `test_limits.py` 29 (51
together), `test_pacing_state.py` 24, `test_pace_loop.py` 58. Every pass/fail split the
report quotes adds up against these.

## Mutation table

Full-suite figures throughout (I ran `pytest -q` over the whole snapshot for every
mutation, not just the brief's named files). Baseline 1859 passed.

| # | Mutation | My expected RED (written before the run) | Actual RED | Report's claim | All three agree? |
| --- | --- | --- | --- | --- | --- |
| 1 | `SEVEN_DAY_MAX_AHEAD_S` `7.5*86400` → `5.5*3600` | 3: `test_parses_all_three_meters_from_the_real_output`, `test_weekly_reset_uses_the_weekly_bound_not_the_session_one`, `test_per_model_meter_parses_percent_reset_and_strips_whitespace`. Explicit GREEN prediction: `test_parse_reset_bound_is_per_call_not_global` | exactly those 3 (`3 failed, 1856 passed`) | same 3; same green | **YES** |
| 2 | delete `or b.resets_at != a.resets_at` (`pacing_state.py:54`) | 1: `test_a_rollover_with_a_positive_delta_still_contributes_nothing`. Explicit GREEN prediction: `test_a_window_rollover_contributes_nothing` | exactly that 1 (`1 failed, 1858 passed`) | same 1; same green | **YES** |
| 3 | delete `or STALE_MARKER in text` (`usage.py:67`) | 1: `test_stale_marker_is_a_failed_read_not_a_number` | exactly that 1 | same | **YES** |
| 4A | reorder: add `except HerderError as exc: raise` **above** the run-level `except RateLimited` | 5: `..._during_winnow_checkpoints...`, `test_run_level_ratelimited_is_caught_before_herdererror`, `..._during_discover_checkpoints_too`, `..._pause_records_the_reset_plus_skew_once`, `..._pause_says_what_a_resume_will_redo`. Explicit GREEN: `test_an_ordinary_stage_failure_is_not_turned_into_a_pause`, `test_pacing_disabled_lets_a_run_level_limit_propagate` | exactly those 5 (`5 failed, 1854 passed`) | same 5; same 2 green | **YES** |
| 4B | same reorder, but the added arm echoes and `return`s (the brief's literal wording) | those 5 **+ 2**: the two "expected green" above, both purely because the body swallows | exactly 7 (`7 failed, 1852 passed`) | same 7, same 2 extras | **YES** |
| 5 | `FIVE_HOUR_MAX_AHEAD_S` `5.5*3600` → `7.5*86400` | 1: `test_session_reset_far_beyond_the_five_hour_bound_is_rejected` | exactly that 1 | same | **YES** |
| 6 | swap the per-show `except RateLimited` / `except (TaskFailed, HerderError, IAError)` arms | 16 named tests in `test_pace_loop.py`. Explicit GREEN: `test_pacing_disabled_records_the_limit_as_a_show_failure` | **18** whole-suite: the 16 I named, **plus** `test_sessions.py::test_a_usage_limit_pauses_the_run_instead_of_failing_the_show` and `::test_a_usage_limit_within_max_wait_sleeps_and_then_finishes`. `test_pacing_disabled_records_the_limit_as_a_show_failure` stayed green as predicted | 16 **in `test_pace_loop.py`** — true as scoped, but it never looked outside that file | **Yes within the report's scope**; my own prediction and the report's figure both undercount the whole-suite radius by the same 2 |

No mutation survived. That reproduces.

## Adjudication of (A), (B), (C)

### (A) Mutation 1's third test — **HOLDS, with a wording correction**

`test_per_model_meter_parses_percent_reset_and_strips_whitespace` is independently
sensitive to the constant, exactly as claimed: `SEVEN_DAY_MAX_AHEAD_S` is used at a
**second** call site, `usage.py:83`, inside the `per_model` comprehension, and that test's
`EXTRA_MODEL` fixture adds a `Current week ( Codex ): 31% used · resets Sep 12 at 7am`
line whose reset is ~6.6 days out. Under a 5.5 h bound it parses to `None` and the
assertion `Meter(31, datetime(2026,9,12,11,0))` fails. Confirmed by running.

The report's claim that `test_parse_reset_bound_is_per_call_not_global` did **not** fail is
also correct, and stronger than the report states: `test_limits.py` does not import
`herder.usage` at all (`from herder import limits` only), and the test passes `7.5 * 86400`
as a literal. It is structurally incapable of seeing this mutation.

**Correction:** the actual failing set is *not* "a superset of the brief's named two."
One of the brief's two never fails. It is a superset of the report's own corrected
expectation (`test_weekly_reset_...` + `test_parses_all_three_meters_...`), which is what
the report's body actually says; only its one-line label in Concern #1 overstates it. The
same overstatement is inherited in my dispatch prompt.

**The real finding here is a defect in the brief, not in the work:** the brief's Step 1
names a test that cannot fail under the mutation it prescribes, and omits two that do.

### (B) The rollover guard's real pin — **HOLDS. First-class finding.**

Mechanically confirmed, twice: by the mutation run (only
`test_a_rollover_with_a_positive_delta_still_contributes_nothing` went red) and by calling
`observe` directly with both fixtures while the mutation was applied:

```
guard line under mutation: ['if b is None or a is None:']
test_a_window_rollover_contributes_nothing fixture (90->2, delta=-88): PacingState(4.0, 3) == seeded? True
test_a_rollover_with_a_positive_delta       fixture (10->14, delta=+4): PacingState(4.0, 4) == seeded? False
```

Precisely:

- **Does NOT pin the guard:** `test_pacing_state.py::test_a_window_rollover_contributes_nothing`
  (the brief's own named test, `pacing_state.py` lines 30-35). Its fixture is `_r(90)` →
  `_r(2, OTHER_RESET)`, delta `-88`. With the `resets_at` clause deleted, control simply
  falls through to the **separate** `if delta < 0: return state` at `pacing_state.py:57`,
  which returns the identical seeded state. It is green under the mutation for a reason
  that has nothing to do with the constraint its name and docstring claim. **This is the
  third measured instance on this branch of a test that is green for a reason other than
  the one it is named for.**
- **Does pin the guard:** `test_pacing_state.py::test_a_rollover_with_a_positive_delta_still_contributes_nothing`
  (lines 50-55), `_r(10)` → `_r(14, OTHER_RESET)`, delta `+4`, which clears the
  negative-delta guard and folds. Its own docstring states the reason correctly.
- **Also does not pin it:** `test_a_negative_delta_contributes_nothing` (same-reset,
  negative delta) and `test_a_failed_reading_at_either_end_contributes_nothing` (the
  `b is None`/`a is None` clauses) — neither touches `resets_at`. No other test in the
  file varies `resets_at` at all; every remaining fixture uses the module-level `RESET`.

So the guard is pinned by exactly **one** test, and it is not the one the brief credits.

**Sub-finding (Minor, new — the report does not note it):** that single pin is thinner
than it looks. Under the mutation it yields `PacingState(4.0, 4)` against a seeded
`PacingState(4.0, 3)` — the `per_show_delta` field is **numerically identical**, because
the fixture's delta (4.0) happens to equal the seeded estimate (4.0). The test only fails
on the `samples` field, via dataclass equality. Any refactor that compared
`out.per_show_delta` instead of the whole state, or that stopped incrementing `samples` on
a fold, would silently unpin this guard. Choosing a fixture delta different from the seed
(e.g. `_r(10) → _r(20, OTHER_RESET)`) would make the pin robust. Recorded for triage; not
a defect in Task 9, which was not asked to strengthen a passing pin.

### (C) The Mutation 4 redo — **HOLDS in full**

Both forms reproduced.

- **Form B** (the first attempt: `except HerderError as exc: typer.echo(...); return`) →
  **7 failed, 1852 passed**. The 7 are exactly the ones the report names.
- **Form A** (the redo: `except HerderError as exc: raise`) → **5 failed, 1854 passed**,
  exactly the five ordering-sensitive tests.

The 7-vs-5 difference is confirmed, and the two extras are confirmed to be body effects,
not ordering effects, by direct evidence rather than inference:

```
E       Failed: DID NOT RAISE HerderError     # test_an_ordinary_stage_failure_is_not_turned_into_a_pause
E       Failed: DID NOT RAISE RateLimited     # test_pacing_disabled_lets_a_run_level_limit_propagate
```

Both fail with `DID NOT RAISE` — i.e. because the arm swallowed the exception, which is a
property of its body. The decisive one is the first: it raises a **plain `HerderError`,
never a `RateLimited`**, so the relative order of the two arms cannot affect it at all;
under Form A, with the identical ordering, it passes. Stderr under Form B shows
`stage failed: provider blew up` — the plain HerderError being eaten.

The implementer's self-catch is genuine and correctly reasoned. Worth noting for the
whole-branch review: **Form B is closer to the brief's literal instruction** ("add one if
the block has none, catching and reporting as a stage failure"), so the brief as written
prescribes the trap. The implementer departing from the brief here was the right call.

## Claims I could not reproduce, or that are wrong

None of the report's mutation results. Two secondary items:

1. **Misattributed quotation.** The report opens with *"Per the brief's own final
   contingency ('If no mutation survives, there is no production change to make and
   possibly no commit at all — say so plainly rather than manufacturing one')"*. That
   sentence does **not** appear anywhere in `$D/briefs/task-9-brief.md`, nor anywhere else
   under `$D` except the report itself. It appears verbatim in my own dispatch prompt, so
   it almost certainly came from the orchestrator's dispatch message to the implementer,
   not the brief file. Not fabrication — the text is the orchestrator's own — but the
   report cites the wrong source, and a reader checking the brief will not find it. The
   brief's Step 6 in fact contains an unconditional `git add -A && git commit` block with
   no stated contingency.
2. **Provenance of the pins is asserted.** Concern #4 says the pinning tests come "mostly
   from Tasks 5-8's own mutation sweeps." I did not verify that and the report offers no
   evidence for it. It is plausible (the in-file comments are explicitly labelled "Self-audit
   (mutation sweep) additions", "F1/F2/F3 fix round"), but it is an unevidenced claim.

## Assessments the review asked for

**Was no-commit the correct discharge?** Yes. Steps 1-4 were all executed and all went red;
Step 5 is vacuous when nothing survives; Step 6's full-suite run was done (1859 passed) and
its `git commit` message — *"test(pacing): pin the four phase-2 constraints by mutation"* —
presupposes new tests that were not needed. Committing anyway would have meant either an
empty commit or a manufactured test. Nothing in the brief was skipped. The one thing the
brief literally asks for and the report does not do is `git commit`, and not doing it is
correct.

**Was "the four are a floor, not a ceiling" a real extension?** *Half real.*

- **Additional B (per-show ordering swap) is a genuine extension.** Different site from
  the brief's, required an anchored swap of two pre-existing arms rather than inventing an
  arm, and its result is informative on its own terms (the largest blast radius on the
  branch).
- **Additional A (`FIVE_HOUR_MAX_AHEAD_S`) is close to token.** The test that catches it,
  `test_session_reset_far_beyond_the_five_hour_bound_is_rejected`, *names this exact
  mutation in its own docstring* ("F3: swapping FIVE_HOUR_MAX_AHEAD_S for
  SEVEN_DAY_MAX_AHEAD_S..."). The outcome was knowable by reading, and it re-derives an
  already-documented pin.

Higher-value unswept candidates existed. The most obvious is the `record`-placement
ordering at `cli.py:505-509`, whose comment explicitly claims to be load-bearing ("hence
the record sitting below the `if limited` break, not above it"). **I ran it as a seventh
mutation** — hoisting the `pacing_state.record(...)` block above the `if limited: … break`
— and it is pinned: `1 failed, 1858 passed`, exactly
`test_pace_loop.py::test_a_rate_limited_show_is_not_a_boundary`. So this is a note about
mutation *selection*, not a hole in the branch. Other untried candidates for the
whole-branch review: `_meter_applies`'s `claude_cli` backend gate, the two new config
ceilings, and the `ran and reading_before is not None` condition.

**Asserted rather than evidenced.** See Important-1 below.

## Findings

### Critical
None.

### Important

**I-1. The report contains no raw tool output anywhere.** Every result is prose
(`"3 failed, 48 passed"`), with zero pasted `FAILED …` lines, zero `git diff` hunks, and
zero pytest tails. Its "verified applied via `git diff` (exact string anchor, match count
asserted == 1)" and "diff confirmed a genuine reorder (arm inserted above … not deleted)"
are assertions about evidence the report does not show. This is the same artifact class
that was fabricated earlier on this branch — a table of counts with nothing behind it —
and prose counts are indistinguishable between a real sweep and an imagined one.
**Everything reproduced, so there is no correctness consequence**; the finding is that the
artifact is not self-verifying, and pasting six `FAILED` blocks would have cost nothing.

**I-2. No mutation was ever run against the full suite.** Each was scoped to the brief's
named file(s). A mutation's failing set is a whole-suite property, and here that under-reports
one result: mutation 6's true radius is **18**, not 16 — `test_sessions.py::test_a_usage_limit_pauses_the_run_instead_of_failing_the_show`
and `::test_a_usage_limit_within_max_wait_sleeps_and_then_finishes` (phase 1's own pause
tests) also break. The report's "16 of 58 in `test_pace_loop.py`" is true as worded, and the
direction of the error is harmless *here* — but the general risk is not: a narrow run can
also miss the case where the only test that would have caught a mutation lives in an
unscoped file, which reads as a survivor when it is not, or vice versa. For mutations 1, 3,
4A, 4B and 5 I confirmed the full-suite set equals the in-file set, so those are unaffected.
(My own pre-run prediction for mutation 6 made the same mistake, for the same reason.)

### Minor (recorded for whole-branch triage, not for fixing now)

**M-1.** The report attributes its no-commit contingency to "the brief"; the sentence is not
in `$D/briefs/task-9-brief.md`. Source is the dispatch message. See "Claims" #1.

**M-2. The brief itself is wrong in two places, and this is worth carrying forward as a doc
correction.** Step 1 names `test_parse_reset_bound_is_per_call_not_global` as expected-red
under a mutation it is structurally incapable of seeing, and omits the two tests that do
fail. Step 2 names `test_a_window_rollover_contributes_nothing` as the pin for a guard it
does not pin. Step 4's wording ("catching and reporting as a stage failure") prescribes the
swallowing arm that produced the false 7.

**M-3.** Mutation 2's sole real pin fails only on the `samples` field, because its fixture's
delta equals the seeded estimate. See the sub-finding under (B).

**M-4.** Concern #1's one-line label calls mutation 1's failing set "a superset of the
brief's named two"; it is not, since one of those two never fails. The report's body states
it correctly.

**M-5.** Additional A is a near-token extension — the mutation it applies is named in the
catching test's own docstring. Additional B is a real one.

**M-6.** Concern #4's provenance claim ("mostly from Tasks 5-8's own mutation sweeps") is
unevidenced.

## Commands run (with results)

```
# snapshot + harness
mkdir -p $D/work/t9-verify/snap
cd /Users/shawn/projects/llama-wt-pacing2 && git archive 3693e45 | tar -x -C $D/work/t9-verify/snap
cd $SNAP && git init -q . && git add -A && git commit -qm "snapshot of 3693e45"
cat $WT/.venv/lib/*/site-packages/_editable_impl_llama_radio.pth
    -> /Users/shawn/projects/llama-wt-pacing2/packages/llama/src        (plain path .pth, no MetaPathFinder)
$WT/.venv/bin/python -B -c "import llama, herder, emcee; print(...)"
    -> all three resolve under $SNAP

# controls
run.sh -q packages/herder/tests/test_usage.py packages/herder/tests/test_limits.py \
       packages/llama/tests/test_pacing_state.py packages/llama/tests/test_pace_loop.py
    -> 133 passed in 0.32s
run.sh -q                                        -> 1859 passed, 7 deselected, 26 warnings in 7.02s
<sentinel raise planted in usage.py / pacing_state.py / cli.py>
    -> RuntimeError: SNAPSHOT-SENTINEL-HERDER-USAGE   (traceback cites the snapshot path)
    -> RuntimeError: SNAPSHOT-SENTINEL-PACING-STATE
    -> RuntimeError: SNAPSHOT-SENTINEL-CLI

# mutation 1
sed: SEVEN_DAY_MAX_AHEAD_S = 7.5 * 86400 -> 5.5 * 3600      (assert count == 1; git diff shown)
run.sh -q -> 3 failed, 1856 passed, 7 deselected
   FAILED test_usage.py::test_parses_all_three_meters_from_the_real_output
   FAILED test_usage.py::test_weekly_reset_uses_the_weekly_bound_not_the_session_one
   FAILED test_usage.py::test_per_model_meter_parses_percent_reset_and_strips_whitespace

# mutation 5
FIVE_HOUR_MAX_AHEAD_S = 5.5 * 3600 -> 7.5 * 86400           (assert count == 1)
run.sh -q -> 1 failed, 1858 passed
   FAILED test_usage.py::test_session_reset_far_beyond_the_five_hour_bound_is_rejected

# mutation 3
"    if not text or STALE_MARKER in text:" -> "    if not text:"   (assert count == 1)
run.sh -q -> 1 failed, 1858 passed
   FAILED test_usage.py::test_stale_marker_is_a_failed_read_not_a_number

# mutation 2
"    if b is None or a is None or b.resets_at != a.resets_at:" -> "    if b is None or a is None:"
run.sh -q -> 1 failed, 1858 passed
   FAILED test_pacing_state.py::test_a_rollover_with_a_positive_delta_still_contributes_nothing
   (direct observe() call with both fixtures, output quoted in section (B))

# mutation 4, Form A (bare re-raise)
anchor "\n    except RateLimited as exc:\n" count = 1 ; 8-space arm count = 1 (untouched)
insert  "    except HerderError as exc:\n        raise\n"  above it
grep after edit -> 382: except HerderError as exc: / 384: except RateLimited as exc: / 446: (8-space, intact)
run.sh -q -> 5 failed, 1854 passed
   FAILED test_pace_loop.py::test_ratelimited_during_winnow_checkpoints_instead_of_exiting
   FAILED test_pace_loop.py::test_run_level_ratelimited_is_caught_before_herdererror
   FAILED test_pace_loop.py::test_ratelimited_during_discover_checkpoints_too
   FAILED test_pace_loop.py::test_a_run_level_pause_records_the_reset_plus_skew_once
   FAILED test_pace_loop.py::test_a_run_level_pause_says_what_a_resume_will_redo

# mutation 4, Form B (echo + return)
same anchor; body = typer.echo(f"stage failed: {exc}", err=True); return
run.sh -q -> 7 failed, 1852 passed   (the five above, plus:)
   FAILED test_pace_loop.py::test_an_ordinary_stage_failure_is_not_turned_into_a_pause
   FAILED test_pace_loop.py::test_pacing_disabled_lets_a_run_level_limit_propagate
   both with "E  Failed: DID NOT RAISE ..."; stderr shows "stage failed: provider blew up"

# mutation 6 (per-show arm swap)
swapped the two full arm bodies (assert each count == 1, assert adjacency)
grep after edit -> 444: except (TaskFailed, HerderError, IAError) / 452: except RateLimited
run.sh -q -> 18 failed, 1841 passed
   16 in test_pace_loop.py (the exact 16 the report names)
   + test_sessions.py::test_a_usage_limit_pauses_the_run_instead_of_failing_the_show
   + test_sessions.py::test_a_usage_limit_within_max_wait_sleeps_and_then_finishes
   test_pacing_disabled_records_the_limit_as_a_show_failure stayed GREEN, as predicted

# reviewer's 7th mutation (record placement, cli.py:505-509)
hoisted the pacing_state.record block above "if limited: unprocessed.extend(...); break"
run.sh -q -> 1 failed, 1858 passed
   FAILED test_pace_loop.py::test_a_rate_limited_show_is_not_a_boundary

# final
git checkout -- .  ; git status --porcelain -> empty
run.sh -q -> 1859 passed, 7 deselected, 26 warnings in 7.04s
cd $WT && git status --porcelain -> empty ; git rev-parse --short HEAD -> 3693e45
```

Per-file counts used to check the report's arithmetic:
`test_pace_loop.py` 58, `test_pacing_state.py` 24, `test_usage.py` 22, `test_limits.py` 29.
Every split the report quotes (3+48=51, 1+23=24, 1+21=22, 5+53=58, 16+42=58) is consistent.

No tool refused me at any point. I produced no commits and did not touch the worktree.
Full log: `$D/t9-verify/t9-verify.log`. Harness: `$D/work/t9-verify/run.sh`.
