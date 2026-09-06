# Task 8 — CODE-QUALITY review

## Verdict

**CHANGES REQUESTED**

The code is clean, well-commented and does what R15/R16/R17 required. Three
things stop it being an approval: one measured, reachable wrong number in the
operator-facing forecast (F-I1), two production-reachable crash guards that no
test pins (F-I2, F-I3), and the implementer's own Concern 1, which I confirm is
a real defect. The `llama pacing` command — the task's headline deliverable —
has its entire second half unpinned: I deleted it, inverted it and removed its
early return, and the suite stayed green three times.

Scope note: 35 mutants, 21 CAUGHT, 14 SURVIVED, 0 EQUIVALENT. Every kill was
checked against a named expected test *before* running; every match is recorded
below.

---

## Harness proof (both outcomes, and that the snapshot shadowed the real source)

I never touched `/Users/shawn/projects/llama-wt-pacing2` and never ran a
`.venv/bin/*` console script. Worktree verified clean and still at `a42c051`
after every run.

Snapshot: `git archive a42c051 | tar -x -C $D/work/t8-quality/snap`.
Runner (`$D/work/t8-quality/run.sh`) — bytecode caching off, PYTHONPATH
shadowing, `python -m pytest`:

```
export PYTHONPATH="$S/packages/llama/src:$S/packages/herder/src:$S/packages/emcee/src"
export PYTHONDONTWRITEBYTECODE=1
cd "$S" && exec "$WT/.venv/bin/python" -B -m pytest -p no:cacheprovider "$@"
```

**Import-level shadowing:**

```
$ "$WT/.venv/bin/python" -c "import llama; print(llama.__file__)"
/Users/shawn/projects/llama-wt-pacing2/packages/llama/src/llama/__init__.py   # unshadowed
$ PYTHONPATH=... "$WT/.venv/bin/python" -B -c "import llama, herder, emcee; ..."
SNAP llama:  .../work/t8-quality/snap/packages/llama/src/llama/__init__.py
SNAP herder: .../work/t8-quality/snap/packages/herder/src/herder/__init__.py
SNAP emcee:  .../work/t8-quality/snap/packages/emcee/src/emcee/__init__.py
```

**Under pytest — the decisive proof.** A sentinel `raise
RuntimeError("SNAPSHOT-SHADOW-SENTINEL")` planted in the SNAPSHOT's
`pacing.py` only:

```
--- sentinel planted ---
40 failed, 51 passed in 1.96s
--- restored ---
91 passed in 0.74s
```

The worktree was untouched throughout, so those 40 failures can only have come
from the snapshot's source. **The harness reports failure.**

**The harness also reports success on a benign change** — mutant `M0`, a
comment appended to the guard line of `shows_that_fit`, applied and reverted by
the same machinery as every other mutant: `91 passed in 0.44s`. A check that
returns nothing and a check that never looked are therefore distinguishable
here.

Baselines on the snapshot: three target files `91 passed`; whole suite
`1835 passed, 7 deselected` — matches the orchestrator's measurement at
`a42c051`.

Snapshot integrity after all 35 mutants: `cli.py`, `pacing.py`,
`test_pace_loop.py`, `conftest.py` and `herder/usage.py` all `diff`-identical
to `git show a42c051:<path>`. No mutation leaked into a later measurement.

---

## `conftest.py::_no_live_usage_meter` — confirmed by experiment, not by reading

The diff does not touch `conftest.py` (confirmed by `diff` against
`a42c051`, and it is absent from the changed-files list). But the mandate asked
for an experiment, so I made a live read impossible to miss and ran the whole
llama suite both ways. Tripwire: `herder.usage.read_usage` raises
`BaseException("LIVE-METER-READ-ATTEMPTED")` when called with `runner=None`
(i.e. the real subprocess path) — `BaseException` because `read_usage` swallows
`Exception`.

```
fixture INTACT   : 1368 passed, 7 deselected            # nothing reaches a live read
fixture NEUTERED : 54 failed, 1314 passed, 7 deselected # e.g. test_sessions.py::test_a_usage_limit_pauses_the_run_instead_of_failing_the_show
restored control : 1368 passed, 7 deselected
```

The fixture is intact, load-bearing, and 54 tests depend on it. Not weakened.

---

## Line-citation verification (every one printed before use)

| citation | verified |
| --- | --- |
| `pacing.py:233` `def shows_that_fit` | YES (`sed -n '233p'` via the 225-250 print) |
| `cli.py:221` `def _pacing_line` | YES |
| `cli.py:265` `reading = _meter(config, pace)` | YES |
| `cli.py:280-284` the forecast line + suffix + echo | YES |
| `cli.py:1372` `def pacing` | YES |
| `cli.py:216` `_meter`'s two-clause gate | YES |
| `cli.py:389-396` the show-loop `except RateLimited` / `not pace.enabled` arm | YES |
| `pacing.py:190-191` `_pause` handles `meter.resets_at is None` | YES |
| `conftest.py:28` `def _no_live_usage_meter` | YES — the implementer's correction of the dispatch's `:26` is right |
| implementer's "13 not 16" in `ea14004` | YES — `test_pacing_decide.py` alone is `13 passed` |

No citation in the implementer's report had drifted.

---

## Findings

### Critical

None.

### Important

**F-I1 — the forecast ignores the weekly window, which `decide` checks FIRST.
Measured wrong number, reachable, and the wrong reset is named.**
`shows_that_fit` is defined only over `five_hour` and `five_hour_ceiling`, and
`_pacing_line` renders `before {five_hour.resets_at}`. `decide` checks
`seven_day` first (`pacing.py:205-207`) and both ceilings default to 90
(`config.py:121-122`). So whenever the weekly window is the binding one, the
line is confidently wrong. Probed on the real formatter through `_execute`:

```
5h 20%, weekly 84%, est 4.0%/show
LINE -> 'pacing: 5h 20% · weekly 84% · est 4.0%/show · ~17 fit before 06:00'
weekly headroom in shows = int((90-84)//4) = 1
```

`~17` where `1` fits, and `before 06:00` where the binding reset is three days
out. The pre-flight gate does **not** cover this: at `84 + 4 = 88 <= 90` it
returns `Proceed`, so the line prints. The operator is shown `weekly 84%` on the
same line as the contradicting forecast.

Recommendation: bound the forecast by both windows and name the reset of
whichever binds — e.g. keep `shows_that_fit`'s shape and take the `min` of a
five-hour and a seven-day call at each of the two call sites, with the rendered
`before {...}` taken from the window that produced the minimum. If that is
judged out of scope for phase 2, the minimum acceptable alternative is an
explicit docstring/comment at both call sites saying the number is a 5-hour
bound only — but a line that prints `weekly 84%` next to `~17 fit` will still
mislead.

**F-I2 — `_pacing_line`'s `resets_at is not None` arm is unpinned, and the
state it guards is reachable in production.** Mutant M11 drops that arm:
`91 passed`. Without it, a `Meter(percent, None)` makes
`reading.five_hour.resets_at.astimezone()` raise `AttributeError` — crashing
`llama get` at run start and `llama pacing` outright. That meter shape is real:
`herder.limits.parse_reset` returns `None` on an unrecognised clause, an
unknown zone, an out-of-range minute and an out-of-bound target
(`limits.py:145-166`), and `pacing._pause` explicitly branches on
`meter.resets_at is None` (`pacing.py:190-191`) — the codebase already treats
it as a live state everywhere except here, where only an untested `and` clause
stands between it and a traceback. Add a test rendering `_pacing_line` with
`five_reset=None`.

**F-I3 — `not per_show_delta` vs `per_show_delta is None` is unpinned, and
`0.0` is producible.** Mutant M4 swaps the guard for `is None`: `91 passed`.
`shows_that_fit`'s own docstring says the guard exists because `0.0` "would
divide by zero", yet no test passes `0.0`. And `0.0` is not hypothetical:
`pacing_state.observe` returns `PacingState(0.0, 1)` for any boundary whose
delta is zero (an integer-percent meter plus a cheap show is the ordinary
case), and `_valid_persisted_delta` accepts `0` on the read path. One added
assertion — `shows_that_fit(_reading(five=65), 0.0, 90) is None` — pins the
sentence the docstring already makes.

**F-I4 — the whole second half of `llama pacing` is untested.** Four mutants,
all green:

- M25 delete the `would proceed` / `would pause: …` echo → `91 passed`
- M26 delete the `if reading is None: return` early return → `91 passed`
- M27 invert the Proceed/pause branches → `91 passed`
- M28 replace `pacing_state.read_state(config.root)` with an empty
  `PacingState()`, so the command ignores the learned cost its own help text
  advertises → `91 passed`

The two brief-supplied tests assert only `"5h 65%"`, `"weekly 7%"` and
`"unavailable"` — i.e. exactly the part `_pacing_line` already owns and that
`test_pace_loop.py` already covers. Nothing the `pacing` command adds over the
formatter is measured. M26 is the sharpest: with the early return gone the
unavailable path prints `unavailable` **and then** `would proceed`, and
`assert "unavailable" in result.stdout` is still satisfied. Add two assertions
(`"would proceed" in stdout` on the good path; `"would proceed" not in stdout`
on the unavailable path) and one test with a persisted `pacing-state.json`
asserting the `est …%/show` part reaches the command.

**F-I5 — the CLI tests do not pin that `pacing` honours `--config`.** M29
replaces `load_config(_config_path)` with `load_config(None)`: `91 passed`. The
command would then read the operator's real `~/.llama/config.toml` and
`~/.llama/pacing-state.json`. `_cfg_file`'s docstring claims this isolation
("so the command never reads the real `~/.llama/config.toml`") but nothing
enforces it, and "no real `$HOME`" is a global constraint. Cheapest pin: write
a `pacing-state.json` under `tmp_path` and assert its `est` value appears —
that assertion fails under M29 *and* closes half of F-I4.

**F-I6 — the `fits < count` boundary is unpinned.** M15 (`<` → `<=`):
`91 passed`. At `fits == count` the mutant emits the operator-facing
`"; the remaining 0 pause until the reset"`. The one shortfall test uses
`fits=2, count=3`, which cannot separate `<` from `<=`. One parametrised case at
`fits == count` fixes it. (M16, `<` → `>`, is CAUGHT, so the direction is
pinned; only the boundary is not.)

**F-I7 — the implementer's Concern 1 is a real defect.** See the dedicated
ruling below.

### Minor

- M3 (`//` → `/`) SURVIVED and is **not** equivalent: a float sweep over the
  realistic domain (pct 0-100 × ceiling {90,95} × delta 1.0-15.0 step 0.1)
  found 225 of 28,482 points differ, always by +1 (`80 // 0.1 == 799.0` but
  `80 / 0.1 == 800.00000000000006`). The shipped `//` is the conservative one;
  nothing pins it.
- M12 (drop `astimezone()`) SURVIVED — deliberate per the implementer's Concern
  3, and the right call: the tests stay zone-independent. Keep the comment that
  says so.
- M13 (` · ` → `, `) SURVIVED — the separator is unpinned. Every label string
  around it *is* pinned (M31-M35 all CAUGHT), so this is cosmetic only.
- M5 (drop `reading.five_hour is None` in `shows_that_fit`) SURVIVED. Defensive
  only: `parse_usage_text` always sets `five_hour` when it returns non-`None`
  (`usage.py:69-73`), so the state is unreachable from `read_usage`. It mirrors
  a state `decide` genuinely models, so keeping it is right; not worth a test.
- M23 (move the echo above the `PauseUntil` check) SURVIVED. The mutant is
  benign — a paused pre-flight would print the pacing line as well as its own
  `paused:` line — so this is a low-value constraint, not a gap worth a test.
- M30 (`pace_options(config)` → `pace_options(Config())` in the command)
  SURVIVED — the command's honouring of config-level pacing options is
  unpinned. Subsumed by F-I5's fix if that test uses a non-default ceiling.
- `shows_that_fit` is computed twice for identical arguments (`_pacing_line`
  and again at `cli.py:281`). The comment justifies keeping the formatter
  count-free, which I accept; noting it only so a future reader does not think
  they disagree.
- The unavailable line has no `pacing: ` prefix while every other return does
  (the implementer's Concern 2). Agreed, and it is the one line in the run-start
  block with nothing marking it as pacing output. Fix alongside F-I7.
- Commit `ea14004`'s trailer says `(16 passed)`; I measured `13 passed` for
  `test_pacing_decide.py` at that tree. Implementer's Concern 4, verified.
  Message-only; no amend needed on my account.
- The dispatch's `conftest.py:26` citation for `_no_live_usage_meter` is off by
  two (the `def` is at `:28`). Implementer already corrected it; recorded so the
  ledger's copy is right.

### Deviations — all three APPROVED

- **`rich_help_panel="Watch"` + `_COMMAND_ORDER`.** Correct. Rendered
  `llama --help` puts `pacing` in the Watch panel immediately after `pipeline`,
  which is what "in the shape of `llama pipeline`" means; a bare
  `@app.command()` would have dropped it into an unnamed group below the named
  panels. No test covers `_COMMAND_ORDER` (I confirmed), so the blast radius is
  the help screen only.
- **`from conftest import cli_invoke`.** Correct and idiomatic: the same import
  appears in `test_cli.py:8`, `test_triage.py:14`, `test_show_cmd.py:15` and
  `test_fix.py:11`. It kept the brief's test bodies verbatim.
- **Two extra `test_pace_loop.py` tests + the `choose=` parameter.** Correct,
  and I verified the implementer's account rather than taking it. See below.

---

## Verifying the implementer's `choose=` account

Claim: `_drive` sets `cli.choose_entries` *after* the caller's monkeypatches and
silently clobbers one, so its first version of the `count` assertion "read as
green while measuring nothing".

**(a) Is the parameter load-bearing?** M24 reverts `_drive` to the old
hard-coded `monkeypatch.setattr(cli, "choose_entries", lambda entries, *a, **k:
entries)`. Expected red: `test_the_run_start_line_names_the_shortfall_without_
shrinking_the_run`. Actual: exactly that one test, failing at
`assert counts == [3]` with `E assert [] == [3]`. Match. The parameter is
required and the assertion is not vacuous.

**(b) Would the old shape really have read green?** I wrote a throw-away probe
(run, then deleted) that patches `cli.choose_entries` from the caller *before*
calling `_drive`, exactly as a test without `choose=` would have to:

```
assert "the remaining 1 pause until the reset" in out   # still passes
assert counts == []                                     # the spy never ran
1 passed
```

So the output assertions stay green while the `count` spy records nothing —
the implementer's description is accurate, and the fix is the right one.

---

## Ruling on the implementer's Concern 1

**The factual claim is true. It is a real defect. Severity: Important. Take
option (a).**

Verified against source, then measured:

- `_meter` returns `None` on three distinct conditions in one expression
  (`cli.py:216`): `not pace.enabled`, `backend != "claude_cli"`, and
  `read_usage()` itself returning `None`.
- Under `--no-pacing` there is demonstrably **no** pacing on limit errors:
  `cli.py:393-396` — `if not pace.enabled:` inside `except RateLimited` prints
  `FAILED …` and appends to `failures`. The run-level catch at `cli.py:340` has
  the same arm. The sentence's second half is flatly false there.
- Under `openrouter` it is false for a different reason: nothing raises
  `RateLimited` on that backend at all (project CLAUDE.md; `openrouter.py`
  raises a plain `HerderError`), so the promised fallback cannot fire. Same for
  `fake`.

Measured, by driving `_execute` on each path:

```
NO-PACING LINE   -> 'usage read unavailable — pacing on limit errors only'
OPENROUTER LINE  -> 'usage read unavailable — pacing on limit errors only'
READ-FAILURE LINE-> 'usage read unavailable — pacing on limit errors only'
```

Three paths, one sentence, true on one of them. This is not cosmetic: on
`--no-pacing` the line tells the operator a safety net is in place at the exact
moment they have turned it off, and a limit hit will then kill every remaining
show with `FAILED`. That inverts the operator's model of what is protecting the
run.

**Shape I want — option (a).** Extract the predicate `_meter` already computes:

```python
def _meter_applies(config: Config, pace: PaceOptions) -> bool:
    return pace.enabled and config.llm_for("default").backend == "claude_cli"
```

`_meter` returns `None` unless it holds; `_execute` prints the pacing line only
when it holds. Then the sentence is printed only where it is both true and
useful (a genuine read failure on `claude_cli` with pacing on), and the two
false statements disappear without a second `_meter` call and without
duplicating the gate — the duplication being the only real cost of (a), and
extraction removes it. ~4 lines, and it keeps the warning that (b) throws away.

Not (b): silently printing nothing when the meter fails on `claude_cli` loses
the one message that matters — that the proactive gate is blind this run.
Not (c): rewording to something vacuously true in all three cases makes
`llama pacing`, whose entire job is to answer this question, answer it vaguely.

While there, give that early return the `pacing: ` prefix (Concern 2) so the
run-start block has one identifiable owner per line. And add a test for each of
the three paths — the current suite pins none of them.

---

## Mutation table

Target for every run unless noted:
`packages/llama/tests/test_pacing_decide.py packages/llama/tests/test_cli_commands.py packages/llama/tests/test_pace_loop.py`
(baseline `91 passed`). Expected red named before running, in every case.

| # | mutation | expected red | actual failing set | match | verdict |
| --- | --- | --- | --- | --- | --- |
| M0 | control no-op (comment appended to the guard line) | none | none (`91 passed`) | yes | CONTROL-PASS |
| S | control sentinel: `raise` in snapshot `shows_that_fit` | many | 40 failed, 51 passed | yes | CONTROL-FAIL |
| M1 | `ceiling` → literal `100` | `..._uses_the_ceiling_not_a_hundred` (+ floors, + shortfall) | those exact 3 | yes | CAUGHT |
| M2 | drop `max(0, …)` | `..._floors_at_zero_when_already_over` | that one | yes | CAUGHT |
| M3 | `//` → `/` | none expected (suspected equivalent) | none | yes | **SURVIVED** (not equivalent — 225/28482 realistic points differ by +1) |
| M4 | `not per_show_delta` → `per_show_delta is None` | none (no `0.0` test exists) | none | yes | **SURVIVED** |
| M5 | drop `reading.five_hour is None` from `shows_that_fit` | none (no such test) | none | yes | **SURVIVED** (unreachable via `read_usage`) |
| M6 | `_pacing_line` early-return string → `"pacing: no meter"` | `test_pacing_command_says_so_when_the_meter_cannot_be_read` | that one | yes | CAUGHT |
| M7 | drop the `weekly …` append | `test_pacing_command_reports_meters_and_forecast` | that one | yes | CAUGHT |
| M8 | drop the `est …%/show` append | `..._names_the_shortfall...` | that one | yes | CAUGHT |
| M9 | drop the `~N fit before …` append | `..._names_the_shortfall...` | that one | yes | CAUGHT |
| M10 | drop the `fits is not None` arm | `..._forecasts_nothing_before_a_boundary_is_observed` | that one | yes | CAUGHT |
| M11 | drop the `resets_at is not None` arm | none expected | none | yes | **SURVIVED** (F-I2) |
| M12 | drop `.astimezone()` | none expected | none | yes | **SURVIVED** (deliberate) |
| M13 | separator ` · ` → `, ` | none expected | none | yes | **SURVIVED** |
| M14 | drop the `"pacing: "` prefix | both `test_the_run_start_line_*` | those exact 2 | yes | CAUGHT |
| M15 | `fits < count` → `fits <= count` | none expected (no `fits == count` case) | none | yes | **SURVIVED** (F-I6) |
| M16 | `fits < count` → `fits > count` | `..._names_the_shortfall...` | that one | yes | CAUGHT |
| M17 | `{count - fits}` → `{count}` | `..._names_the_shortfall...` | that one | yes | CAUGHT |
| M18 | `{count - fits}` → `{fits}` | `..._names_the_shortfall...` | that one | yes | CAUGHT |
| M19 | delete `typer.echo(line)` | both `test_the_run_start_line_*` | those exact 2 | yes | CAUGHT |
| M20 | drop the shortfall suffix (`pass`) | `..._names_the_shortfall...` | that one | yes | CAUGHT |
| M21 | trim `count = fits` after the echo | `..._names_the_shortfall...` (the `counts == [3]` assert) | that one | yes | CAUGHT |
| M22 | R16: a **second** `_meter(config, pace)` for the line | task-6's read-order tests | `..._folds_each_shows_own_before_and_after`, `..._is_what_stops_the_next_show` | yes — and for the right reason: `AssertionError: more meter reads than the boundary protocol calls for`, raised from `cli.py:218 read_usage()` | CAUGHT |
| M23 | move the echo above the `PauseUntil` check | none expected | none | yes | **SURVIVED** (benign mutant) |
| M24 | `_drive` ignores `choose=` (pre-change body) | `..._names_the_shortfall...` | that one, at `assert [] == [3]` | yes | CAUGHT |
| M25 | delete the `would proceed`/`would pause` echo | none expected | none | yes | **SURVIVED** (F-I4) |
| M26 | delete `if reading is None: return` in the command | none expected | none | yes | **SURVIVED** (F-I4) |
| M27 | invert the Proceed/pause branches | none expected | none | yes | **SURVIVED** (F-I4) |
| M28 | command ignores persisted `pacing_state` | none expected | none | yes | **SURVIVED** (F-I4) |
| M29 | command uses `load_config(None)` (ignores `--config`) | none expected | none | yes | **SURVIVED** (F-I5) |
| M30 | command uses `pace_options(Config())` | none expected | none | yes | **SURVIVED** |
| M31 | `5h ` label → `session ` | 3 line tests | those exact 3 | yes | CAUGHT |
| M32 | `weekly ` label → `7d ` | `test_pacing_command_reports_meters_and_forecast` | that one | yes | CAUGHT |
| M33 | `est {x:.1f}%/show` → `est {x:.2f} per show` | `..._names_the_shortfall...` | that one | yes | CAUGHT |
| M34 | `~N fit before` → `~N fits until` | `..._names_the_shortfall...` | that one | yes | CAUGHT |
| M35 | suffix wording → `" (N will wait for the reset)"` | `..._names_the_shortfall...` | that one | yes | CAUGHT |

No mutant produced a failure set larger than predicted, so no kill in this table
rests on "any failure counts". The one mutant whose kill could plausibly have
been for an unrelated reason (M22, a second subprocess-shaped call) I opened and
read: the assertion that fired is the read-counter, from the `read_usage` line
inside `_meter`.

**Summary: 21 CAUGHT, 14 SURVIVED, 0 EQUIVALENT.** The surviving 14 cluster in
two places — the `llama pacing` command body (6 of them) and the guards whose
inputs no test constructs (4).

---

## Exact commands

```
# snapshot
mkdir -p "$D/work/t8-quality/snap"
cd /Users/shawn/projects/llama-wt-pacing2 && git archive a42c051 | tar -x -C "$D/work/t8-quality/snap"

# runner (all pytest runs went through this; never .venv/bin/pytest)
PYTHONPATH="$S/packages/llama/src:$S/packages/herder/src:$S/packages/emcee/src" \
PYTHONDONTWRITEBYTECODE=1 \
  "$WT/.venv/bin/python" -B -m pytest -p no:cacheprovider <args>

# baselines
run.sh packages/llama/tests/test_pacing_decide.py packages/llama/tests/test_cli_commands.py \
       packages/llama/tests/test_pace_loop.py -q          -> 91 passed in 0.47s
run.sh -q                                                  -> 1835 passed, 7 deselected in 6.91s
run.sh packages/llama/tests -q                             -> 1368 passed, 7 deselected in 5.50s
run.sh packages/llama/tests/test_pacing_decide.py -q       -> 13 passed in 0.13s

# mutation driver (applies one anchored text patch, runs pytest, always restores)
$D/work/t8-quality/mut.py <label> <relfile> <old-fragment> <new-fragment> -- <pytest targets>
# it hard-fails with PATCH-ANCHOR-COUNT unless the anchor matches exactly once,
# so no mutant was silently a no-op.

# integrity after the run
diff <(git -C $WT show a42c051:packages/llama/src/llama/cli.py) $S/packages/llama/src/llama/cli.py   # clean
# (same for pacing.py, test_pace_loop.py, conftest.py, herder/usage.py)
git -C $WT status --porcelain   # empty; HEAD still a42c051
```

Full transcript with every mutant's output: `$D/t8-quality/t8-quality.log`.
Patch fragments and the driver: `$D/work/t8-quality/`.

## Blocked / refused actions

None. No tool refused anything and no permission was denied.
