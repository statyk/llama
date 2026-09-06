# Task 8 — scoped RE-REVIEW of the fix diff `a42c051..3693e45`

**Verdict: all eight open findings ADDRESSED. No new Critical or Important
breakage introduced by the fix diff.** 18 mutations run, 18/18 exact
expected-set matches. Full snapshot suite `1859 passed, 7 deselected` —
identical to the caller's independent worktree run.

Scope: the 4 commits `daa0c97`, `df23158`, `2df1de9`, `3693e45`, touching
exactly 5 files (`cli.py`, `pacing.py`, and the three test files). Nothing
outside that diff was re-reviewed.

---

## 1. Harness proof — both outcomes, and the snapshot really shadows

Isolation held: the worktree was never modified and its suite was never run
by me. Everything below ran against a `git archive 3693e45` snapshot at
`$D/work/t8-rereview/snap`, with the worktree venv's **interpreter** invoked
as `python -B -m pytest` (never a `.venv/bin/*` console script) and
`PYTHONPATH` pointing at the snapshot's three `packages/*/src` dirs.

Import provenance (the three packages resolve **inside the snapshot**, not
the worktree):

```
$ PYTHONPATH=<snap>/packages/{llama,herder,emcee}/src <WT>/.venv/bin/python -B \
    -c "import llama, herder, emcee; print(llama.__file__); print(herder.__file__); print(emcee.__file__)"
<snap>/packages/llama/src/llama/__init__.py
<snap>/packages/herder/src/herder/__init__.py
<snap>/packages/emcee/src/emcee/__init__.py
```

**Passing control** (mutation scope = the three test files):

```
$ run.sh -q packages/llama/tests/test_pacing_decide.py \
             packages/llama/tests/test_pace_loop.py \
             packages/llama/tests/test_cli_commands.py
115 passed in 0.53s
```

**Failing control — planted sentinel.** A bare `raise
RuntimeError("SNAPSHOT-SENTINEL")` inserted at the top of
`binding_forecast` **in the snapshot's source**:

```
51 failed, 64 passed in 2.16s
```

Restored → `115 passed`. So a mutation applied to my copy demonstrably
reaches the code under test, and the harness reports both directions.

**Full snapshot suite, control:** `1859 passed, 7 deselected, 26 warnings in
6.97s` — matching the caller's `./.venv/bin/python -m pytest -q` figure at
`3693e45` exactly. Test-count arithmetic checks out too: 6 new in
`test_cli_commands.py`, 9 new functions / 10 items in `test_pace_loop.py`,
8 new in `test_pacing_decide.py` = **24 added, 0 lost** (1835 → 1859), which
reconciles the two rounds' +13 and +11.

Branch state, read-only: `HEAD = 3693e45` on `usage-pacing-phase2`, working
tree clean apart from untracked `.superpowers/`. No commits of my own.

**Line citations verified** by printing them at `3693e45` (grep output in
the log):
`cli.py:203 _meter_applies`, `223 _meter`, `230` its gate, `235
_reset_label`, `255 _pacing_line`, `274` the unavailable return, `284/286`
the forecast clause, `330` the `_execute` gate, `333` `fc.shows < count`,
`337` the reset label in the shortfall clause, `1436` the `pacing` early
return, `1454 if reading is None:`, `1457` the verdict echo;
`pacing.py:226/228` `decide`'s two `_pause` calls in order, `233
shows_that_fit`, `254` its guard, `260 Forecast`, `273 binding_forecast`,
`292` the candidate list, `301` the `min`.

---

## 2. Findings — one line each

**F1 — ADDRESSED.** The three causes are now three different behaviours,
without a reason enum. `_meter_applies(config, pace)` (`cli.py:203`) is
extracted and is the only gate; `_meter` (`223`) calls it. `_execute`
(`330`) wraps the whole line block in it, so `--no-pacing` and a
non-`claude_cli` backend print **nothing**; `llama pacing` (`1436`) returns
early and names the actual reason (`pacing is off ([pacing] enabled =
false) — …` / `no usage window to read on the <backend> backend — pacing
applies to claude_cli only`), branching only *after* the shared gate has
already said no. The genuine-failed-read sentence's claim is byte-for-byte
intact at `274`. Killed by R1, R2, R3 (all exact).

**F2 — ADDRESSED.** `cli.py:284` guards `fc is not None and fc.resets_at is
not None`, and the guard **moved with the forecast** to the *binding*
window rather than staying on `reading.five_hour`. Two tests pin it — a
binding 5-hour meter with `Meter(65, None)` and a binding weekly meter with
`Meter(84, None)` (the shape the live `/usage` prints today). Killed by R4
(exactly those 2).

**F3 — ADDRESSED.** `pacing.py:254` still reads `not per_show_delta`, and it
is now pinned twice: `test_shows_that_fit_treats_a_zero_estimate_as_no_estimate`
and `test_the_forecast_is_none_when_nothing_can_be_forecast`'s `0.0` leg.
Killed by R5 → `per_show_delta is None` reddens exactly those 2 (the second
via `ZeroDivisionError`).

**F4 — ADDRESSED.** All four sub-mutants now die: R6 (delete the verdict
echo) → 2 red; R7 (delete `if reading is None: return`) → 1 red; R8 (invert
the branches) → 4 red; and the persisted state is pinned by R9/F5's test.
Every actual set matched my pre-named prediction exactly.

**F5 — ADDRESSED.** `load_config(None)` no longer survives: R9 reddens
`test_pacing_command_reads_the_learned_cost_from_the_configs_own_root`,
`..._names_pacing_being_switched_off_in_the_config` and
`..._names_the_backend_that_has_no_usage_window` — exactly the 3 predicted.
One caveat worth naming: this mutant's kill depends on the operator having a
real `~/.llama/config.toml` (mine does). Two of the three killers are
config-content tests, so the kill is robust in practice, but a machine with
no `~/.llama/config.toml` would kill it via a different set.

**F6 — ADDRESSED.** `cli.py:333` is `fc.shows < count`. R10 (`<=`) reddens
**only** the equality parametrisation
`test_the_shortfall_clause_stays_quiet_unless_the_run_overruns[12.5-pids0-2]`,
with the room-to-spare case staying green — a true boundary discriminator,
not a direction re-proof.

**G1 — ADDRESSED, fully and to the letter of the author's scoping.**
`binding_forecast` (`pacing.py:273`) computes `shows_that_fit` for **both**
windows, **each against its own ceiling** (`seven_day_ceiling` /
`five_hour_ceiling` — treated as the independent config fields you
required), takes the `min`, and carries **the binding window's own**
`resets_at`. No burn-rate or time-to-exhaustion notion was added; the line
still reports a count and an instant. The weekly form names its window and
carries a date (`~1 fit before the weekly reset, Sep 8 16:00`), the 5-hour
form stays a bare `%H:%M`, and the shortfall clause's reset noun follows the
same scope. Rendered end-to-end here:

```
weekly binds, both resets    pacing: 5h 20% · weekly 84% · est 4.0%/show · ~1 fit before the weekly reset, Sep 8 16:00; the remaining 2 pause until the weekly reset
session binds                pacing: 5h 65% · weekly 7% · est 4.0%/show · ~6 fit before 18:00
weekly binds, no weekly reset pacing: 5h 20% · weekly 84% · est 4.0%/show; the remaining 2 pause until the weekly reset
```

The measured regression is gone: 5h 20% / weekly 84% / 4.0%/show now reports
`~1`, not `~17`. R17 — the direct **revert** of the fix (drop the
`seven_day` candidate) — reddens 8 tests, exactly as predicted, so the fix
is pinned against being undone, not merely against being perturbed. R12
(shared ceiling), R13 (tie order), R14 (`min`→`max`, 13 names), R15
(`_reset_label`'s weekly branch), R16 (bare "the reset"), R18 (carry the
other window's reset) all die exactly.

**G2 — ADDRESSED.** `cli.py:274` now returns `"pacing: usage read
unavailable — pacing on limit errors only"`. The claim after the prefix is
byte-for-byte the original, em dash included (diffed character-for-character
against the spec's copy at
`docs/superpowers/specs/2026-09-05-usage-pacing-phase2-design.md:405`).
R11 (drop the prefix) reddens exactly
`test_a_failed_read_on_a_paced_run_says_the_backstop_is_still_live`.

---

## 3. New breakage introduced by the fix diff

**None at Critical or Important.** What I checked and found clean:

- `shows_that_fit` is no longer imported into `cli.py`, and `grep` confirms
  no remaining reference there — `binding_forecast` is the only entry point
  `cli.py` has, which is the property the signature change was for.
- `_execute`'s pre-flight `decide`/`_checkpoint_pause` path is **above** the
  new gate and is untouched; the gate only suppresses the informational
  line. The three other `_meter` call sites (`cli.py:307, 486, 523`) are
  unchanged and still get `None` under `--no-pacing`, as before.
- `_reset_label` dereferences `fc.resets_at` but is only ever called from
  inside the `fc.resets_at is not None` guard — R4 confirms the guard is the
  only thing standing between it and an `AttributeError`, and the guard is
  now pinned.
- `min(live, key=lambda c: c[0])` compares only the key, so the `Meter` in
  the tuple is never compared — no ordering hazard from a non-comparable
  dataclass.
- No test was deleted or weakened out of the suite (24 added, 0 lost).
- I ran the **whole** snapshot suite, not just the scope, so breakage in an
  untouched file would have shown: `1859 passed`.

---

## 4. The three items asked for extra scrutiny

### (a) The `shows_that_fit` signature change — the reason holds, and the three brief tests were not weakened

The brief did pin `shows_that_fit(reading, per_show_delta, ceiling)`
(`briefs/task-8-brief.md:9, 77`) — **and the brief's own `_pacing_line`
sketch at lines 102-105 is where the G1 bug came from**, calling
`shows_that_fit(reading, …, pace.five_hour_ceiling)` and rendering
`reading.five_hour.resets_at`. So the implementer's argument is not
retrospective rationalisation: the pinned shape's `.five_hour`-in-the-body
is demonstrably what made the wrong-window call the obvious one, and it was
the brief itself that wrote it. Judgement: **the reason holds**, the change
was declared with it as authorised, and per-window is the shape that cannot
express the bug.

Were the three brief tests weakened? **No.**

- `test_shows_that_fit_uses_the_ceiling_not_a_hundred` — `(90-65)//4.2 == 5`,
  same number, same intent, one attribute access longer.
- `test_shows_that_fit_floors_at_zero_when_already_over` — likewise.
- `test_shows_that_fit_is_unknown_without_an_estimate` — its second leg,
  `shows_that_fit(None, 4.2, 90) is None`, changed meaning from "no reading"
  to "no meter". That is not weaker; it is the arm `binding_forecast` now
  relies on to let a half-populated reading still forecast, and it is
  independently pinned by `test_a_window_with_no_meter_does_not_compete`.

Coverage is in fact **up**: the old guard's third arm (`reading.five_hour is
None`) had **no** test at `a42c051`; its successor (`meter is None`) has two.

### (b) The claimed accidental passes — VERIFIED, and it is a real finding

I checked this mechanically rather than reading it. Reverting all four
`shows_that_fit` call sites in `test_pacing_decide.py` to pass a whole
`UsageReading` (i.e. what the tests would have looked like had the
implementer *not* updated them), against the shipped per-meter
implementation:

```
FAILED test_shows_that_fit_uses_the_ceiling_not_a_hundred   AttributeError: 'UsageReading' object has no attribute 'percent'
FAILED test_shows_that_fit_floors_at_zero_when_already_over AttributeError: 'UsageReading' object has no attribute 'percent'
2 failed, 2 passed, 17 deselected
```

The two that **passed** are exactly the two named:
`test_shows_that_fit_is_unknown_without_an_estimate` and
`test_shows_that_fit_treats_a_zero_estimate_as_no_estimate`. The mechanism
is as claimed — a `UsageReading` is not `None`, so `not per_show_delta`
short-circuits before anything touches `.percent`, and the wrong argument
type never surfaces. **The claim is accurate**, it was self-reported rather
than discovered by review, and the fix (updating those two along with the
other two) is the right one: their green is now type-carrying rather than
type-blind.

### (c) The tie-break — CORRECT, checked against `decide`, not the report

`pacing.py:226-229`:

```python
    return (_pause(reading.seven_day, opts.seven_day_ceiling, "seven_day",
                   projected, now, opts)
            or _pause(reading.five_hour, opts.five_hour_ceiling, "five_hour",
                      projected, now, opts)
            or Proceed())
```

`seven_day` is evaluated first and short-circuits, so on a tie the run really
does pause on the weekly window — the docstring's "Checked FIRST because a
weekly exhaustion cannot be slept off at the 5-hour reset" is the shipped
behaviour, not just prose. `binding_forecast` lists the `seven_day`
candidate first and Python's `min` returns the **first** minimal element, so
a tie yields `scope="seven_day"` and the weekly reset instant — agreeing
with `decide`. R13 (flipping the candidate order) reddens exactly
`test_a_tie_goes_to_the_weekly_window_because_that_is_where_decide_pauses`,
so the alignment is pinned, not incidental.

---

## 5. Mutation table

Every expected set was written into the runner **before** the mutant was
applied; the runner diffed the actual `FAILED` set against it and printed
MATCH/MISMATCH mechanically. Full transcript in
`t8-rereview/t8-rereview.log`.

| # | mutation | expected RED | actual RED | match | verdict |
| --- | --- | --- | --- | --- | --- |
| R1 | `_execute`'s `if _meter_applies(...)` → `if True` | `no_pacing_prints_no_run_start_line_at_all`, `a_backend_with_no_window_prints_no_run_start_line_at_all` | same 2 (`2 failed, 113 passed`) | **yes** | CAUGHT (F1) |
| R2 | delete the `_meter_applies` block from `llama pacing` | `pacing_command_names_pacing_being_switched_off_in_the_config`, `pacing_command_names_the_backend_that_has_no_usage_window` | same 2 | **yes** | CAUGHT (F1) |
| R3 | swap the two explanations (`not pace.enabled` → `pace.enabled`) | same 2 as R2 | same 2 | **yes** | CAUGHT (F1) |
| R4 | drop `and fc.resets_at is not None` | `the_line_survives_a_meter_that_named_no_reset`, `the_missing_reset_guard_follows_the_binding_window` | same 2 | **yes** | CAUGHT (F2) |
| R5 | `not per_show_delta` → `per_show_delta is None` | `shows_that_fit_treats_a_zero_estimate_as_no_estimate`, `the_forecast_is_none_when_nothing_can_be_forecast` | same 2 | **yes** | CAUGHT (F3) |
| R6 | delete the `would proceed`/`would pause` echo | `..._reports_the_verdict_the_next_show_would_get`, `..._reports_a_pause_verdict_and_names_the_window` | same 2 | **yes** | CAUGHT (F4) |
| R7 | delete `if reading is None: return` | `pacing_command_gives_no_verdict_when_it_could_not_read_the_meter` | same 1 | **yes** | CAUGHT (F4) |
| R8 | invert the Proceed/pause branches | those 2 **plus** `..._reports_meters_and_forecast`, `..._reads_the_learned_cost_from_the_configs_own_root` (4) | same 4 (`4 failed, 111 passed`) | **yes** | CAUGHT (F4) |
| R9 | `load_config(_config_path)` → `load_config(None)` | `..._reads_the_learned_cost...`, `..._names_pacing_being_switched_off...`, `..._names_the_backend...` | same 3 | **yes** | CAUGHT (F5) |
| R10 | `fc.shows < count` → `<=` | `..._stays_quiet_unless_the_run_overruns[12.5-pids0-2]` only | same 1, `[5.0-pids1-5]` stayed green | **yes** | CAUGHT (F6) |
| R11 | drop the `pacing: ` prefix from the unavailable line | `a_failed_read_on_a_paced_run_says_the_backstop_is_still_live` | same 1 | **yes** | CAUGHT (G2) |
| R12 | both windows measured against `five_hour_ceiling` | `each_window_is_measured_against_its_own_ceiling` | same 1 | **yes** | CAUGHT (G1) |
| R13 | candidate order flipped (tie → `five_hour`) | `a_tie_goes_to_the_weekly_window_because_that_is_where_decide_pauses` | same 1 | **yes** | CAUGHT (G1/c) |
| R14 | `min` → `max`: forecast the roomier window | 13 named tests (enumerated in full before the run) | same 13 (`13 failed, 102 passed`) | **yes** | CAUGHT (G1) |
| R15 | `_reset_label` loses its weekly branch | `the_line_names_the_weekly_window_and_dates_its_reset` | same 1 | **yes** | CAUGHT (G1) |
| R16 | shortfall suffix always says a bare "the reset" | `the_shortfall_clause_names_the_weekly_reset_when_the_weekly_binds` | same 1 | **yes** | CAUGHT (G1) |
| R17 | **revert the fix**: drop the `seven_day` candidate entirely | `the_forecast_follows_the_weekly_window...`, `a_tie_goes_to_the_weekly_window...`, `each_window_is_measured_against_its_own_ceiling`, `a_window_with_no_meter_does_not_compete`, `the_binding_windows_missing_reset_is_carried_not_swapped`, `the_line_names_the_weekly_window_and_dates_its_reset`, `the_missing_reset_guard_follows_the_binding_window`, `the_shortfall_clause_names_the_weekly_reset_when_the_weekly_binds` (8) | same 8 (`8 failed, 107 passed`) | **yes** | CAUGHT (G1) |
| R18 | `Forecast` carries the OTHER window's `resets_at` | `the_binding_windows_missing_reset_is_carried_not_swapped`, `the_forecast_follows_the_weekly_window...`, `a_tie_goes_to_the_weekly_window...`, `the_line_names_the_weekly_window_and_dates_its_reset`, `the_missing_reset_guard_follows_the_binding_window` (5) | same 5 | **yes** | CAUGHT (G1) |

**18 of 18 exact matches.** Every mutant that mattered was killed, and every
kill was by the tests I named before running it — no "12 failures, must be
caught" scoring anywhere.

### Spot-check of the implementer's own tables: **accurate**

I re-ran the mutants behind every finding I verdicted, and the account holds
up under independent execution:

- **Round 1.** R1/R2/R3/R6/R7/R9/R10 reproduce M1/M2/M3/M7/M6/M10/M11 with
  identical actual sets. **M8's self-reported miss is real and honestly
  described**: R8 gives exactly 4 red, exactly the 4 they named after the
  fact, and the mechanism (`Proceed` has no `.reason` → `AttributeError` →
  non-zero exit → every `exit_code == 0` assertion on the proceeding path
  fails) is what I observed. They reported it as a prediction failure rather
  than rounding it to CAUGHT; that is the correct call.
- **One divergence, benign and explained.** Their M5 predicted and got 1 red
  for the `not per_show_delta` mutant; my R5 gets 2. The extra test —
  `test_the_forecast_is_none_when_nothing_can_be_forecast` — did not exist
  in round 1. Their number was right for their tree.
- **Round 2.** R12/R13/R14/R15/R16/R11 reproduce N1/N2/N3/N5/N6/N7 exactly.
  N3's thirteen-name enumeration is the one I would most have expected to be
  hand-waved, and it is **exactly right** — I derived the same 13 names
  independently from each test's data before running, and the actual set
  matched both. N4 (their `resets_at` guard mutant) is my R4, also exact.
- R17 and R18 are mine, not theirs, and both die cleanly.

I found no fabricated or rounded row.

---

## 6. Deferred minors (out of scope — these do not extend the fix loop)

1. **A `five_hour=None` reading is unreachable in production, so two paths
   are dead.** `herder/usage.py:parse_usage_text` returns `None` outright
   when the session line is missing (`_SESSION_RE` is mandatory), so
   `five_hour` is never `None` on a non-`None` reading. That makes
   `_pacing_line`'s `reading.five_hour is None` arm (pre-existing, `cli.py:273`)
   and `test_a_window_with_no_meter_does_not_compete`'s `only_weekly` half
   defensive-only. They are also mutually inconsistent: `binding_forecast`
   would forecast a weekly-only reading, but `_pacing_line` short-circuits to
   the unavailable sentence before ever calling it. Harmless today; worth a
   line of comment if the `/usage` format ever changes.
2. **`binding_forecast` is computed twice on the `_execute` path** — once
   inside `_pacing_line` (`cli.py:284`) and once beside it (`332`). Pure and
   cheap, but the two could in principle be threaded from one call.
3. **Docs drift on G2**: `docs/superpowers/plans/2026-09-05-usage-pacing-phase2.md:1496`
   and `docs/superpowers/specs/2026-09-05-usage-pacing-phase2-design.md:405`
   still show the sentence without the `pacing: ` prefix. Historical
   artifacts; noting only so the whole-branch sweep can decide.
4. **A 5-hour reset crossing midnight renders as a bare `02:00` with no
   date.** The implementer flagged this themselves as an accepted edge; I
   agree with the call (it reads as "tonight") and record it so it is not
   rediscovered.
5. **`ea14004`'s "(16 passed)" commit trailer** is still wrong (the run was
   13). Already parked for the whole-branch sweep; unchanged here.
6. **R9's kill is mildly environment-coupled** — see F5 above.

---

## 7. Exact commands run

```bash
D=/Users/shawn/projects/llama/.superpowers/sdd/2026-09-05-usage-pacing-phase2
WT=/Users/shawn/projects/llama-wt-pacing2
S="$D/work/t8-rereview/snap"

mkdir -p "$D/t8-rereview" && touch "$D/t8-rereview/t8-rereview.log"
mkdir -p "$S" && cd "$WT" && git archive 3693e45 | tar -x -C "$S"

cd "$WT" && git log --oneline a42c051..3693e45
cd "$WT" && git diff --stat a42c051 3693e45
cd "$WT" && git diff a42c051 3693e45 -- packages/llama/src/llama/{pacing,cli}.py
cd "$WT" && git diff a42c051 3693e45 -- packages/llama/tests/
cd "$WT" && git status --porcelain ; git rev-parse HEAD
cd "$WT" && for c in daa0c97 df23158 2df1de9 3693e45; do git show --stat --oneline $c; done

# runner (never a .venv/bin console script)
cat "$D/work/t8-rereview/run.sh"
  export PYTHONDONTWRITEBYTECODE=1
  export PYTHONPATH="$S/packages/llama/src:$S/packages/herder/src:$S/packages/emcee/src"
  cd "$S" && "$WT/.venv/bin/python" -B -m pytest -p no:cacheprovider "$@"

# provenance + controls
PYTHONPATH=... "$WT/.venv/bin/python" -B -c "import llama,herder,emcee; ..."
run.sh -q <three test files>                      # 115 passed
# planted `raise RuntimeError("SNAPSHOT-SENTINEL")` in binding_forecast
run.sh -q <three test files>                      # 51 failed, 64 passed
# restored
run.sh -q                                         # 1859 passed, 7 deselected

# 18 mutations, each via work/t8-rereview/mut.py (applies, runs
# `run.sh -q --no-header -rf <three files>`, diffs FAILED set vs the
# expectation given on the command line, restores the file)
python3 mut.py "R1 ..." packages/llama/src/llama/cli.py    <old> <new> <expected>
   ... R2 R3 R4 R5 R6 R7 R8 R9 R10 R11 R12 R13 R14 R15 R16 R17 R18

# claim (b): revert the four shows_that_fit call sites to whole readings
run.sh -q --no-header -rf packages/llama/tests/test_pacing_decide.py -k shows_that_fit
   # 2 failed (ceiling, floors_at_zero — AttributeError), 2 passed

# rendering sweep of four meter shapes through cli._pacing_line + the
# shortfall clause (output quoted under G1 above)
```

No tool refused anything. No permission was denied. No commits produced. The
worktree was not modified and its suite was not run by me.
