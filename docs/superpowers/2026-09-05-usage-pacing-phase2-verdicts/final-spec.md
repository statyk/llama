# Whole-branch SPEC-COMPLIANCE review — usage pacing phase 2

Branch `usage-pacing-phase2`, `ac7c428..3693e45` (32 commits).
Reviewer: final spec-compliance, dispatched by `ae1a6b246987e7c1a`.
Date: 2026-09-06.

# VERDICT: **Spec PASS**

The branch delivers every requirement in the design spec's **Architecture**,
**Policy**, **Integration** and **CLI and config** sections. All four
"constraints to mutate, not merely run" were re-mutated by me and every one
goes red. All six global constraints hold. `openrouter.py` is untouched, no
`--batch`/`--force`/`trust_age` was introduced, and `herder` imports nothing
from `llama`.

The PASS is qualified by **one Important test gap** (the weekly reset bound's
reject direction is unpinned — a 30-day mutation leaves all 1859 tests green)
and **a cluster of documentation defects**, the worst of which is that
`CLAUDE.md` still tells the next reader that the thing this branch built does
not exist. Those are fixable without touching code; none of them is a reason
to reject the implementation.

---

# Environment and method

Per the isolation rule I never ran anything in `/Users/shawn/projects/llama-wt-pacing2`
beyond read-only `git`. Every execution ran against `git archive` snapshots
under `$D/work/final-spec/snaps/<sha>/`, driven by
`"$WT/.venv/bin/python" -B -m pytest -p no:cacheprovider` with `PYTHONPATH`
pointed at the snapshot's three `packages/*/src` dirs.

**Shadowing proven with a planted sentinel** (required before any result is
trusted):

```
$ cd $S && PYTHONPATH=$PP $WT/.venv/bin/python -B -m pytest -p no:cacheprovider -q packages/llama/tests/test_pacing_state.py
24 passed in 0.50s
$ sed -i '' 's/^EWMA_ALPHA = 0.4$/EWMA_ALPHA = 0.9/' $S/packages/llama/src/llama/pacing_state.py
$ ... same command ...
FAILED packages/llama/tests/test_pacing_state.py::test_ewma_alpha_is_pinned_at_point_4
1 failed, 23 passed in 0.48s
$ # restored; `cd $WT && git status --porcelain` -> empty (worktree untouched)
```

A mutation applied to the SNAPSHOT turns a test red, so the runs execute
snapshot code, not the worktree's. Confirming the harness is calibrated: the
full suite in my snapshot at `3693e45` gives **1859 passed, 7 deselected**,
byte-matching the number measured independently in the worktree.

---

# DELIVERABLE 1 — whole-branch spec compliance

## Architecture

| Spec requirement | Status | Evidence |
| --- | --- | --- |
| `herder/usage.py` new, separate from `limits.py` | ✅ | `packages/herder/src/herder/usage.py`, 129 lines, docstring states the separation |
| `Meter(percent, resets_at)` | ✅ | `usage.py:45-48` |
| `UsageReading(five_hour, seven_day, per_model, fetched_at)` | ✅ (see M-1 below) | `usage.py:51-56`; `fetched_at` is `datetime \| None = None`, spec wrote `datetime` |
| `read_usage(runner, now) -> UsageReading \| None`, runner injected | ✅ | `usage.py:107-129` |
| `read_usage` **never raises**; None on non-zero exit / unparseable / missing `result` / missing `Current session:` / `Showing last-known usage` | ✅ | `usage.py:98-104, 116-129, 67-70`; each pinned in `test_usage.py` |
| Line-based defensive parsing of the three lines; analytics prose ignored | ✅ | `_SESSION_RE`/`_WEEK_ALL_RE`/`_WEEK_MODEL_RE`, `usage.py:37-42`; the `(?!all models)` lookahead is pinned by `test_per_model_line_does_not_swallow_the_all_models_line` |
| Reset parsing **extends** `limits.parse_reset`; one parser, two shapes | ✅ | `limits.py:65-68` `_RESET_DATED_RE`, `limits.py:121-172` |
| Reset bound becomes **per-meter**: 5.5 h / 7.5 d; refusal path keeps its value | ✅ | `usage.py:30-31`; `limits.MAX_RESET_AHEAD_S` unchanged at `limits.py:26` and still the default for `classify()` |
| Backend gating: meaningful only on `claude_cli` | ✅ | `cli.py:_meter_applies` (`config.llm_for("default").backend == "claude_cli"` AND `pace.enabled`); `test_gate_is_skipped_entirely_on_a_non_claude_cli_backend` |
| `decide()` pure, in `llama/pacing.py`, IO in the caller | ✅ | `pacing.py:199-230`; no IO, no clock read inside |
| `Progress` is counters only | ⚠️ **M-2** | `pacing.py:177-183` carries only `per_show_delta`; the spec's "shows done, shows remaining" fields do not exist |

## Policy

| Spec rule | Status | Evidence |
| --- | --- | --- |
| 1. Weekly ceiling checked **first** | ✅ | `pacing.py:226-229` — `_pause(seven_day…) or _pause(five_hour…)`; pinned by the ceiling-swap test added in `c79d81d` |
| 2. Session gate on the projection | ✅ | `_pause`: `meter.percent + projected <= ceiling` |
| 3. Otherwise Proceed | ✅ | `pacing.py:230` |
| Before a delta is learned, both degrade to the bare percentage | ✅ | `projected = progress.per_show_delta or 0.0` (`pacing.py:225`) |
| EWMA over `five_hour` deltas across llama's own boundaries | ✅ | `pacing_state.observe`, `EWMA_ALPHA = 0.4` |
| Before/after, not before-N/before-N+1 | ✅ | `cli.py:486` (`reading_before`) and `cli.py:523` (fresh read after the show) |
| Boundary contributes only when both readings succeeded **and** `resets_at` unchanged | ✅ | `pacing_state.py:54`; re-mutated by me, goes red |
| `pacing-state.json` read-modify-write under `file_lock` | ✅ | `pacing_state.record` (`pacing_state.py:112-118`); lock order pinned by `test_record_reads_and_writes_inside_the_lock` |
| One ceiling per window, default 90, no `reserve` knob | ✅ | `config.py` `five_hour_ceiling`/`seven_day_ceiling = 90`; no `reserve` anywhere |

**Deviation, benign and unflagged in the spec:** the spec writes rule 1 as
`PauseUntil(seven_day.resets_at)` (no skew) and rule 2 as
`PauseUntil(five_hour.resets_at + reset_skew)`. The shipped `_pause` applies
`reset_skew` to **both**. Symmetric skew is the safer of the two and I do not
consider it a defect, but the spec was not amended to say so.

## Integration — the four touch points

| # | Spec | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Pre-flight, after criteria resolution, before `run_discover` | ✅ | `cli.py:302-316` — reads state, one `_meter` call, `decide`, `_checkpoint_pause` on a `PauseUntil` |
| 2 | `except RateLimited` wrapping `run_discover`/`run_search`/`run_winnow` | ✅ | `cli.py:344-401`; one `try` spans the whole region, arm at `cli.py:382` |
| 3 | Before each show, top of the loop | ✅ | `cli.py:484-492`, **before the show lock** (pinned by `b67b2a1` after a mutation showed the in-lock placement is silently wrong) |
| 4 | Around `process_show`, unchanged, `RateLimited` before `HerderError` | ✅ | `cli.py:444` before `cli.py:454`; re-mutated by me, goes red |
| — | Run-level sites checkpoint and exit 0 **without sleeping** | ✅ | `_checkpoint_pause` (`cli.py:176-201`) has no sleep branch; only the show loop calls `sleep_until` |
| — | No-progress guard (R21) stays exactly as built | ✅ | `cli.py:546-556` unchanged |
| — | R20 resolution: no new signal, no distinct exit code | ✅ | `_checkpoint_pause` exits 0 through the normal `return`; nothing writes an exit-code protocol |

## CLI and config

| Spec | Status | Evidence |
| --- | --- | --- |
| `[pacing]` gains `five_hour_ceiling`/`seven_day_ceiling`, default 90 | ✅ | `config.py:120-121` |
| `DEFAULT_CONFIG_TOML` gains the matching block | ✅ | `config.py:271-275`, and `c79d81d` added `test_default_config_template_documents_every_pacing_knob` after finding the existing template test could not catch an omitted key |
| No `--batch`, no `--force`, no `trust_age` | ✅ | `git diff ac7c428..3693e45 \| grep -E '^\+.*(--batch\|trust_age\|--force)'` returns only prose in briefs/verdicts, no code |
| `--wait`/`--no-wait`/`--max-wait`/`--no-pacing` unchanged on `get`, `run approve`, `run resume` | ✅ | all three still declare them; `pace` threaded into `_execute` at `cli.py:845` and `cli.py:879` |
| `--no-pacing` now disables the proactive gate too | ✅ behaviourally, ⚠️ **D-6** in help text | `pace_options(no_pacing=…)` sets `enabled=False`; `decide` returns `Proceed`, `_meter_applies` returns False. The `--help` string was never updated |
| `llama pacing`, read-only, shape of `llama pipeline` | ✅ | `cli.py:1424-1461`, registered in `_COMMAND_ORDER` |
| …showing **the three meters** | ❌ **M-3** | only `5h` and `weekly` render; `per_model` is parsed and never displayed anywhere in llama |
| …the learned per-show delta, `decide()`'s verdict, the forecast | ✅ | `est N%/show`, `would proceed`/`would pause: …`, `~N fit before …` |
| Run-start forecast line | ✅ shipped, ⚠️ **D-2** spec example stale | measured output below |
| Unavailable line | ✅ shipped, ⚠️ **D-1** spec example stale | measured output below |

Measured, through the real formatters (`$D/work/final-spec/render.py`):

```
RUN-START LINE : pacing: 5h 65% · weekly 7% · est 4.2%/show · ~5 fit before 13:19; the remaining 8 pause until the reset
PAUSE reason   : 5h window at 87%, est 4.2%/show
PAUSE rendered : paused after 3 shows: 5h window at 87%, est 4.2%/show
UNAVAILABLE    : pacing: usage read unavailable — pacing on limit errors only
```

## Deliberately unbuilt work

| Item | Filed as UNBUILT? | Half-implemented anywhere? |
| --- | --- | --- |
| **T6b** — checkpoint a limit during `run_interpret` | ✅ plan §"Task T6b (FILED, NOT IMPLEMENTED)", bold "Do not implement as part of phase 2"; spec `### Known gap` says the same | **No.** `run_interpret` at `cli.py:607` and `cli.py:2760` sits outside every `try`; the only artifact is a 4-line comment at `cli.py:603-606` saying why |
| **T7b** — let the run-level sites honour `--wait` | ✅ plan §"Task T7b (FILED, NOT IMPLEMENTED)"; spec's amended Integration paragraph names it | **No.** `_checkpoint_pause` has no sleep branch and no `wait`/`max_wait` reference at all. T7b also correctly folds in the ungated deferred pass (`cli.py:527-529` — verified: no `decide` call, blocking `file_lock`) |

## Non-goals held

- **`openrouter` pacing** — `git diff --stat ac7c428..3693e45 -- packages/herder/src/herder/openrouter.py` is **empty**. Untouched. ✅
- **Burn-rate history log** — no rate-over-time notion anywhere. ✅
- **Cheap resume of a partial winnow** — not attempted; the honest limit is stated in the `cli.py:391-394` comment. ✅
- **Shrinking `count`** — `count` is read for the shortfall clause only; `a42c051` explicitly mutation-tested "trim count to what fits" and kills it. ✅
- **Mid-stage pausing** — decisions only at run and show boundaries. ✅

## Global constraints (`$D/briefs/global-constraints.md`)

| Constraint | Verdict | Evidence |
| --- | --- | --- |
| Offline/deterministic: no wall-clock, no real `$HOME`, no subprocess, no sleep | ✅ | `decide` takes `now`; `read_usage` takes `runner`; `test_usage.py` monkeypatches `subprocess.run` and never spawns; full suite runs in 7.0 s |
| `read_usage`/`parse_usage_text` never raise | ✅ | bare `except Exception` on the runner, typed except on `json.loads`; `test_read_usage_never_raises_when_the_runner_explodes` |
| Backend gating to `claude_cli` | ✅ | `_meter_applies`; plus an autouse conftest fixture stubbing `cli.read_usage` to None so no test can shell out |
| Every new `except RateLimited` ordered before `except HerderError` | ✅ | both sites; re-mutated by me (see D2 method proof and M4 below) |
| `openrouter.py` untouched | ✅ | empty diffstat |
| No `--batch`/`--force`/`trust_age` | ✅ | grep over the whole diff |
| `herder` must not import `llama` | ✅ | `grep -rn "import llama\|from llama" packages/herder/src/` → no hits; `test_no_llama_imports.py` (herder + emcee) → 4 passed |
| Four policy constants are not tuning targets | ✅ | `FIVE_HOUR_MAX_AHEAD_S`, `SEVEN_DAY_MAX_AHEAD_S`, `EWMA_ALPHA`, both ceilings all at their designed values; `EWMA_ALPHA` is now pinned by a literal-value test |
| `_meter` not unified with `pipeline.make_providers` | ✅ | `_meter` calls `read_usage()` directly; docstring records why |

**One deviation from a brief instruction, and it is correct:** the brief says
"if a task's test needs a workspace fixture that `test_pace_loop.py` does not
already have, add it to that file rather than to `conftest.py`". The autouse
`_no_live_usage_meter` fixture went into `packages/llama/tests/conftest.py`.
That is the right call — it is a suite-wide *safety* guard (without it any test
reaching `_execute` shells out to the real `claude` binary), not a workspace
fixture. Noting it so it does not read as an unnoticed violation.

## The spec's four mutation constraints — re-run by me, all four RED

| # | Mutation applied to the snapshot | Result |
| --- | --- | --- |
| 1 | `usage.SEVEN_DAY_MAX_AHEAD_S = 7.5*86400` → `5.5*3600` | **RED, 3 failures**: `test_weekly_reset_uses_the_weekly_bound_not_the_session_one`, `test_parses_all_three_meters_from_the_real_output`, `test_per_model_meter_parses_percent_reset_and_strips_whitespace` |
| 2 | delete `or b.resets_at != a.resets_at` from `pacing_state.observe` | **RED**: `test_a_rollover_with_a_positive_delta_still_contributes_nothing` (1 failed, 1858 passed on the full suite) |
| 3 | delete `or STALE_MARKER in text` from `parse_usage_text` | **RED**: `test_stale_marker_is_a_failed_read_not_a_number` |
| 4a | run-level arm `except RateLimited` → `except HerderError` | **RED**: `test_an_ordinary_stage_failure_is_not_turned_into_a_pause` |
| 4b | insert an `except HerderError` arm *before* the `RateLimited` arm (the brief's literal wording) | **RED**: 7 failures incl. `test_run_level_ratelimited_is_caught_before_herdererror` |

## MISSING against the spec (named)

- **M-1 (Minor).** `UsageReading.fetched_at` is `datetime | None = None`; the
  spec's Architecture block writes `fetched_at: datetime`. Harmless — nothing
  reads it — but the spec block is now a slightly inaccurate schema.
- **M-2 (Minor).** `Progress` carries only `per_show_delta`. The spec says
  "`progress` is counters only — shows done, shows remaining, learned per-show
  delta". Two of the three named fields do not exist. The policy does not need
  them, so this is a spec-not-amended defect rather than a functional hole.
- **M-3 (Minor, functional; must-fix as documentation).** `llama pacing` is
  specified to show "the three meters" and shows two. `per_model` is parsed,
  tested at the parser level, and never rendered by any llama code
  (`grep -rn per_model packages/llama` finds only test fixtures). Either render
  it or amend the spec; do not leave the spec claiming a third meter.
- **M-4 (Important).** The spec's Testing section requires "a weekly reset
  seven days out accepted, **eight days rejected**". Only the accept direction
  is pinned. Measured:

  ```
  $ sed -i '' 's/SEVEN_DAY_MAX_AHEAD_S = 7.5 \* 86400/SEVEN_DAY_MAX_AHEAD_S = 30 * 86400/' .../usage.py
  $ ... full suite ...
  1859 passed, 7 deselected, 26 warnings in 7.67s
  ```

  Widening the weekly bound to thirty days leaves the entire suite green. This
  is the one direction that matters: the bound exists so a mis-parsed or
  clock-skewed reset cannot manufacture a long sleep, and a 30-day-out
  `resets_at` would flow straight through `pacing._pause` into a
  `PauseUntil` a month out. The equivalent reject direction for the *session*
  bound **is** pinned (`test_session_reset_far_beyond_the_five_hour_bound_is_rejected`),
  which is what makes the asymmetry look like an oversight rather than a
  decision. **One test closes it.**
- **M-5 (Minor).** The spec's Testing section lists "**Resume costs nothing**:
  a fake provider with a call counter proves already-packaged shows make zero
  LLM calls on re-entry." No such test exists. I searched the whole llama test
  tree for a provider call counter asserted to zero on re-entry and found none;
  the nearest thing is the generic unit test `test_workspace.py::test_should_run`.
  The behaviour is unchanged from phase 1 and pinned at the unit level, so this
  is a checklist item not built, not a regression.

## EXTRA — delivered beyond the spec (all defensible, none unsanctioned)

- `binding_forecast` / `Forecast` / `shows_that_fit(meter, …)` / `_reset_label`
  (`2df1de9`). The spec asks only for "how many shows fit before the reset";
  what shipped forecasts **both** windows against their own ceilings and names
  the binding one. This fixes a real shipped bug (`weekly 84% … ~17 fit` where
  the weekly headroom was one show). Strictly better than the spec; the spec's
  own example line was never updated to match — see D-2.
- The two explanation branches in `llama pacing` for "pacing is off" and "no
  usage window on the `<backend>` backend" (`daa0c97`). Not in the spec, and
  the right call: the spec's single unavailable sentence promises a reactive
  backstop that neither of those states has.
- `_meter_applies` as an extracted predicate — refactor, no behaviour beyond
  the above.
- The shortfall clause `"; the remaining N pause until the reset"` — the spec's
  example folds this into `~6 of 13 fit`; the shipped form separates it.

---

# DELIVERABLE 2 — the commit-message numeric sweep

## Proof the method can return a failure

Before believing any green result I ran the harness against `ea14004`, whose
claim is known wrong:

```
$ $W/sweep.sh ea14004 packages/llama/tests/test_pacing_decide.py
13 passed in 0.17s          # message claims "(16 passed)"
```

The harness returns a contradiction where one exists. Separately, the sentinel
mutation above proves the harness is executing snapshot code rather than
silently reporting on the worktree. Both checks were run before the sweep.

## The sweep — all 32 commits

Every commit is listed. "Claim" is the strongest verifiable numeric/command
assertion in the message. Every ✅ row is a command I ran at that commit.

| # | Commit | Claim | Repro | Evidence |
| --- | --- | --- | --- | --- |
| 1 | `eef3081` | "Verified **red** via test_limits.py -k 'dated or per_call or refusal_form'" | ✅ | `4 failed, 1 passed, 22 deselected` |
| 2 | `9ee737b` | test_limits.py → **27 passed** | ✅ | `27 passed in 0.06s` |
| 3 | `94f8c6c` | "Last green: pytest -q → **1747** passed at 9ee737b" | ✅ | full suite at `9ee737b` = `1747 passed, 7 deselected` |
| 4 | `3b16e42` | test_limits.py → **28 passed** | ✅ | `28 passed` |
| 5 | `e2ada6a` | test_limits.py → **29 passed** | ✅ | `29 passed` |
| 6 | `8c0a56d` | test_usage.py → **6 passed** | ✅ | `6 passed` |
| 7 | `6901427` | test_usage.py → **11 passed** | ✅ | `11 passed` |
| 8 | `f53678d` | test_usage.py → **14 passed** | ✅ | `14 passed` |
| 9 | `7b3e474` | test_usage.py → **17 passed** | ✅ | `17 passed` |
| 10 | `816d00a` | test_usage.py → **22 passed**; "adds five tests" | ✅ | `22 passed`; 22−17 = 5 ✓. "all 10 proposed mutations now go red" — **unverifiable** (private mutation copy, deleted) |
| 11 | `2686d0a` | full suite **1778**, 7 deselected | ✅ | exact |
| 12 | `c79d81d` | **1782**, 7 | ✅ | exact |
| 13 | `5739217` | **1782**, 7 (unchanged) | ✅ | exact |
| 14 | `cb87790` | **1796**, 7 (= 1782 + 14 new) | ✅ | exact; arithmetic holds |
| 15 | `f980ebe` | **1803**, 7 (= 1782 + 21 pacing_state tests) | ✅ | exact; 1803−1796 = 7 new here, cumulative 21 ✓ |
| 16 | `ef6ad14` | **1806**, 7 (= 1803 + 3) | ✅ | exact |
| 17 | `cbaad44` | **1811**, 7 | ✅ count | **❌ SUBJECT WRONG** — see F-1 |
| 18 | `4aef34a` | **1814**, 7; "17 mutants, 16 caught" | ✅ count | mutation figures **unverifiable** (private copy) |
| 19 | `a3d8cdc` | **1814**, 7; "the repr mutant survives the old form (**32 passed**)"; "Every line citation in both documents was checked against the current tree"; "19 mutants, 18 caught" | ✅ | `1814 passed`; `test_pace_loop.py` = **32 passed** at both `4aef34a` and `a3d8cdc` ✓; **citation claim verified true at that commit** — `cli.py:440` = the `run_interpret` call, `:2556` = the profile-path call, `:708-710` = the `criteria.json` refusal, `:1186` = `_PIPELINE_RUN_STAGES`, all exact. Mutation counts unverifiable |
| 20 | `0ca7e1a` | **1824**, 7 | ✅ | exact |
| 21 | `b67b2a1` | **1826**, 7 | ✅ | exact |
| 22 | `dda7948` | **1828**, 7 | ✅ | exact |
| 23 | `61a314e` | "Tests unchanged: **1828**, 7" | ✅ | exact |
| 24 | `6db6ed4` | "**1828** passed either side"; "cli.py takes `reading_before` at **:389** and a fresh reading after the show at **:426**" | ✅ | `1828 passed`; **both citations exact at that commit** (`:389` = `reading_before = _meter(...)`, `:426` = `_meter(config, pace))`). Both have since drifted — see D-4 |
| 25 | `6f7c126` | "the **380-line** ledger"; "**28 reports**"; "all **14** rulings"; "**46** deferred minors"; "verified byte-identical with `cmp`" | ✅ all five | `wc -l` ledger = **380**; verdicts dir = 29 files = 28 reports + `_global-constraints.md` ✓; rulings R1..R14 = **14** ✓; `grep -c "minor (deferred)"` = **46** ✓; my own `cmp` of all 29 committed copies against their live sources → **identical=29 differs=0** |
| 26 | `ea14004` | test_pacing_decide.py → **(16 passed)** | ❌ **WRONG** | **13 passed.** See F-2 |
| 27 | `07dfc6e` | **1833**, 7 | ✅ | exact |
| 28 | `a42c051` | **1835**, 7 | ✅ | exact |
| 29 | `daa0c97` | **1848**, 7 | ❌ **WRONG** | **1835 passed, 7 deselected.** See F-3 |
| 30 | `df23158` | **1848**, 7; "Thirteen tests for six findings" | ✅ | `1848 passed`; 1848−1835 = **13** ✓ |
| 31 | `2df1de9` | **1859**, 7 | ✅ | exact |
| 32 | `3693e45` | **1859**, 7; "all nine are substring `in`/`not in`" | ✅ count | the "nine assertions" figure is **unverified** (I did not enumerate them) |

**Score: 29 of 32 commits fully reproduce. 3 carry a claim that does not.**

### F-1 (Important) — `cbaad44`'s subject is wrong in both directions

> `fix(cli): a limit during interpret/search/winnow now checkpoints`

The commit covers `run_discover`, `run_search`, `run_winnow`. It names
`interpret`, which it does **not** cover, and omits `discover`, which it does.
Its test count (1811) is correct. This is already acknowledged: `a3d8cdc`'s
message says so, and the plan carries a "**Correction, post-review**" block.
**Do not amend** — `4aef34a` sits on top and the review verdicts hold both
SHAs. The correction is properly recorded; I am reporting it as reproduced,
not as an outstanding action.

### F-2 (Important) — `ea14004` claims 16 where the tree gives 13

> `Tests: ./.venv/bin/python -m pytest packages/llama/tests/test_pacing_decide.py -q` / `(16 passed)`

Measured at that exact commit: **13 passed**. The full suite at `ea14004` is
`1831 passed, 7 deselected`, which is internally consistent (1828 + 3 new
`shows_that_fit` tests), so only the per-file figure is wrong. Most likely a
count pasted from a later state of the file — `df23158` later adds 7 more to
`test_pacing_decide.py`. Wrong, not merely unverifiable.

### F-3 (Important, **NOT previously reported**) — `daa0c97` claims 1848 where the tree gives 1835

> `Tests: ./.venv/bin/python -m pytest -q (1848 passed, 7 deselected)`

Measured at `daa0c97`: **1835 passed, 7 deselected** — identical to its parent
`a42c051`, which is exactly right, because `git show --stat daa0c97` shows the
commit touches **only** `packages/llama/src/llama/cli.py` (+47/−8) and adds no
tests. Its own body even says *"Covering tests land in the next commit."* Those
13 tests land in `df23158`, which reaches 1848. So `daa0c97`'s message reports
its **successor's** suite count as its own, and the number it quotes was
unreachable at that commit by construction. This is the same failure mode as
F-2 and is the third one; a sweep that stopped at the two known cases would
have missed it.

### Claims I could not verify, named as such

- All private-copy mutation tallies (`816d00a` "all 10 go red", `4aef34a`
  "17 mutants, 16 caught", `a3d8cdc` "19 mutants, 18 caught, 0 harness errors",
  `f980ebe` "14 mutants, 8 survivors", `df23158` "eleven mutants",
  `ef6ad14` "flips its target mutant from SURVIVED to CAUGHT"). The mutation
  copies were deliberately deleted. I re-ran the **four spec-mandated**
  mutations myself and all four go red; the per-commit sweep tallies I take on
  the author's assertion, and say so.
- `3693e45`'s "all nine are substring `in`/`not in`" — I did not enumerate the
  nine assertions.
- `816d00a`'s prose about `ISOLATION_ARGS`/`_neutral_cwd` isolation semantics —
  read, not independently re-derived.
- `6f7c126`'s "R10's OverflowError crash and R13's `--wait` contract break being
  the two that bear on merge" — a judgement, not a number; the ledger does carry
  R10 and R13 with those subjects.

---

# DELIVERABLE 3 — documentation accuracy

## The four reported items — all four confirmed

### D-1 (must-fix) — the spec's unavailable line lacks the shipped `pacing: ` prefix

`design.md:404-406` and the plan both show:

```
usage read unavailable — pacing on limit errors only
```

The shipped line, measured through `cli._pacing_line`, is:

```
pacing: usage read unavailable — pacing on limit errors only
```

`3693e45` deliberately added the family prefix (G2) and did not update either
document. **Confirmed. One-word fix in two files.**

### D-2 (must-fix) — the spec's run-start example is not what ships

`design.md:392`:

```
pacing: 5h 65% · weekly 7% · est 4.2%/show · ~6 of 13 fit before 17:19
```

Shipped (measured):

```
pacing: 5h 65% · weekly 7% · est 4.2%/show · ~5 fit before 13:19; the remaining 8 pause until the reset
```

Three differences: there is no `of <count>` in the forecast; the shortfall is a
separate appended clause; and after `2df1de9` the forecast may name the
**weekly** window and carry a date (`~1 fit before the weekly reset, Sep 8 16:00`),
a form the spec's example cannot express at all. **Not in my brief's list — an
additional finding of the same kind.**

**D-2b (leave, but note).** The same section's proactive-pause example,
`design.md:398`:

```
pausing before the wall: 5h at 87%, est 4.2%/show — resumes 17:19 (1h 04m)
```

Shipped: `paused after 3 shows: 5h window at 87%, est 4.2%/show` followed by
`  resumes 17:19 (1h 04m)`. The substance is all present, but the spec's stated
intent — "A proactive pause **says so plainly, so it does not read as a
refusal**" — is met only weakly: the prefix `paused after N shows:` is
byte-identical to the reactive path's, and only the reason clause distinguishes
them. I would leave the code alone this late and correct the spec's example,
but the design intent behind that sentence deserves a conscious "yes, this is
enough" rather than being quietly overtaken.

### D-3 (must-fix) — "the three meters" is two

`design.md:384`. Confirmed: `per_model` is never rendered. Same finding as M-3.
Cheapest correct fix is to amend the spec to "both account-wide meters" and add
a line saying the per-model sub-meter is parsed but not displayed because it is
account-dependent.

### D-4 (must-fix) — every line citation in the `### Known gap` section has drifted

All four were **correct when written** at `a3d8cdc` (verified above, sweep row
19) and are **all wrong at HEAD**, because `0ca7e1a` inserted ~167 lines into
`cli.py` above them:

| Citation | Says | Actually at HEAD (`3693e45`) | Real location |
| --- | --- | --- | --- |
| `cli.py:440` (`run_interpret` in `get`) | — | `setlistfm=setlistfm,` inside `_process` | **`cli.py:607`** |
| `cli.py:2556` (profile-creation path) | — | `pid = _resolve_pid(config, ledger, name)` | **`cli.py:2760`** |
| `cli.py:708-710` (`run resume` refuses no-criteria) | — | `pace=pace)` / `return` / `_get_query(...)` | **`cli.py:875-877`** |
| `cli.py:1186` (`_PIPELINE_RUN_STAGES`) | — | a comment about M3 adoption | **`cli.py:1353`** |
| `stages/interpret.py:13` | `write_artifact(ws.criteria, criteria)` | ✅ **still correct** | — |
| `limits.py:26` (`MAX_RESET_AHEAD_S`) | ✅ **still correct** | — | — |

The **plan** carries the same four stale citations in its "Known gap" block and
in T6b's scope line. **T7b's citations are additionally stale, and one was
never right:**

| T7b citation | At HEAD | Note |
| --- | --- | --- |
| `cli.py:236-242` (pre-flight gate) | `_reset_label`'s docstring | correct at `61a314e`, drifted |
| `cli.py:300-304` (run-level catch) | comments inside the pre-flight block | correct at `61a314e`, drifted |
| `cli.py:422` (the deferred pass's blocking lock) | `artist_cap=criteria.artist_cap,` | **wrong when written too** — at `61a314e` the line was 430 |

The committed SDD ledger adds a **third** number for the same symbol:
`cli.py:1177` for `_PIPELINE_RUN_STAGES` (ledger line 288), against the spec's
1186 and the real 1353.

**This is the exact hazard the method requirements name, and it recurred inside
the same branch that documented it.** The durable-record cost is real: the
`### Known gap` section's whole purpose is to let a future reader confirm the
gap is still where it was said to be, and every pointer it offers now lands on
unrelated code. **Must fix before merge**, and I would recommend replacing the
numbers with symbol names (`run_interpret`'s call site in `_get_query`) rather
than re-pinning line numbers that will drift again on the next commit.

### D-5 (fixed, no action) — the `### Known gap` heading splice

Confirmed as **introduced** by `a3d8cdc` (heading sat between bullets 2 and 3,
orphaning "There is no way to plan a run against the window" under an H3 about
`run_interpret`) and **fixed** by `61a314e`, whose message calls it out
explicitly. At HEAD the heading follows all three bullets. Nothing to do.

## Task 9 brief — the three reported defects, all confirmed by execution

**Step 1 (confirmed).** The brief expects mutation 1 to turn
`test_weekly_reset_uses_the_weekly_bound_not_the_session_one` **and**
`test_parse_reset_bound_is_per_call_not_global` red. The second is
**structurally incapable** of failing:

```python
def test_parse_reset_bound_is_per_call_not_global():
    assert limits.parse_reset(text, now=now, max_ahead_s=7.5 * 86400) is not None
```

It passes the bound as a **literal** and never reads `usage.SEVEN_DAY_MAX_AHEAD_S`.
Measured, the mutation reddens **three** tests, two of which the brief omits:
`test_parses_all_three_meters_from_the_real_output` and
`test_per_model_meter_parses_percent_reset_and_strips_whitespace`.

**New sub-finding:** the plan's **ruling R4**, written to correct exactly this,
is itself now incomplete — it names only `test_parses_all_three_meters_...` as
the omitted red. It was accurate when written at `94f8c6c`; the second omitted
test arrived later, in `6901427`. Worth a one-word amendment if R4 is kept.

**Step 2 (confirmed).** The brief credits
`test_a_window_rollover_contributes_nothing`. Measured, dropping the guard
reddens **`test_a_rollover_with_a_positive_delta_still_contributes_nothing`**
instead — the named test uses a negative delta, which the separate `delta < 0`
arm catches anyway, so it cannot see the rollover guard at all. The constraint
**is** pinned, by a test `f980ebe` added after a mutation sweep found precisely
this hole. The brief credits the wrong test.

**Step 4 (confirmed).** The brief says to add an `except HerderError` arm
"catching and reporting as a stage failure". Measured, that produces **7**
failures, of which only `test_run_level_ratelimited_is_caught_before_herdererror`
is about ordering; the rest — including
`test_an_ordinary_stage_failure_is_not_turned_into_a_pause` and
`test_pacing_disabled_lets_a_run_level_limit_propagate` — fail because the
*added arm's own body* swallows ordinary failures and the `--no-pacing`
re-raise. **And a sharper point the brief misses entirely:** under the
*minimal* form of the mutation (`except RateLimited` → `except HerderError` on
the existing arm), the brief's named test **stays green** — a `RateLimited`
still gets caught and still checkpoints. The test that actually pins the
ordering constraint is `test_an_ordinary_stage_failure_is_not_turned_into_a_pause`.
Constraint pinned; brief's expected-red naming wrong twice over.

Verdict on Task 9's brief: **leave the brief, correct the plan.** The brief is
a spent execution artifact; but if any of its Step 1/2/4 text is carried into
the plan or the spec as the record of what pins these constraints, it must be
corrected first, because all three would send a future reader to a test that
does not do the job.

## Additional documentation findings (mine, not in the brief's list)

### D-6 (Critical for the durable record) — `CLAUDE.md` still says this branch's main feature does not exist

`CLAUDE.md:275-290`, unchanged on this branch, reads:

> **(b) it is per-show, not per-run.** … A `RateLimited` raised during any of
> those three run-level stages **is not caught anywhere** and escapes
> `_execute` as an ordinary unhandled exception: exit 1, no checkpoint, no
> `paused` state, no `resume_after` … **phase 1 has no such gate, so a limit
> hit during those stages fails the run outright.**

Every clause of that is now false. Task 6 (`cbaad44`) added the catch; Task 7
(`0ca7e1a`) added the pre-flight gate the paragraph says does not exist. The
branch *did* touch `CLAUDE.md` — it added the `llama pacing` entry — so this is
an omission inside an edited file, not an untouched one.

Relatedly, `CLAUDE.md:29-36`'s `llama get` bullet still describes pacing as
purely reactive ("**when** the claude_cli backend **refuses** …") and mentions
neither the proactive gate, the two new ceilings, nor the run-start `pacing:`
line.

`CLAUDE.md` is the first thing every future session reads. Of everything in
this deliverable this is the one I would block a merge on. Note that boundary
**(a)** in the same paragraph — openrouter — remains true and should be kept.

### D-7 (must-fix) — `pacing_state.py`'s module docstring cites drifted lines

`packages/llama/src/llama/pacing_state.py:4` says the boundary readings are at
"`cli.py:389` and `cli.py:426`". Correct when `6db6ed4` wrote them; at HEAD
those lines are a comment fragment and a `typer.echo` about shortlist review.
The real sites are **`cli.py:486`** and **`cli.py:523`**. Same class as D-4, but
in shipped source rather than a doc — so it will be read more often. Symbol
names (`_execute`'s `reading_before` / the `pacing_state.record` call) would not
rot.

### D-8 (leave) — `--no-pacing`'s help text under-describes the flag

All three declarations (`cli.py:679`, `:821`, `:865`) still read
`"Disable usage pacing: a limit fails the show as it did before"` — unchanged
from phase 1. The spec explicitly states "`--no-pacing` **now disables the
proactive gate as well as** the reactive pause". The help text says only the
reactive half. Cosmetic, one string, three sites; safe to leave for a follow-up.

## Must-fix-before-merge vs leave

| Finding | Verdict |
| --- | --- |
| **D-6** `CLAUDE.md` phase-1 boundary paragraph is now false | **must fix** |
| **D-4** stale line citations in spec + plan (`### Known gap`, T6b, T7b) | **must fix** |
| **D-7** `pacing_state.py` docstring's `cli.py:389/:426` | **must fix** |
| **D-1** spec/plan unavailable line missing `pacing: ` | **must fix** (trivial) |
| **D-2** spec's run-start example line is not what ships | **must fix** (trivial) |
| **D-3** "the three meters" is two | **must fix** (one sentence) |
| **M-4** weekly reset bound's reject direction unpinned | **must fix — code** (one test) |
| D-2b proactive pause wording vs spec's "says so plainly" | leave, note in the ledger |
| D-8 `--no-pacing` help text | leave |
| D-5 heading splice | already fixed |
| Task 9 brief Steps 1/2/4 | leave the brief; correct plan ruling R4 if kept |
| **F-1/F-2/F-3** wrong commit-message numbers | **report only, do not amend** — history rewriting is out of scope and the branch is under review |
| M-1, M-2, M-5 spec/code schema and checklist drift | leave, or fold into the same spec pass |

---

# Findings by grade

**Critical**
- **D-6** — `CLAUDE.md:275-290` states that a `RateLimited` in
  discover/search/winnow "is not caught anywhere", that there is "no such
  gate", and that such a limit "fails the run outright". All false as of this
  branch. The project's primary orientation document actively denies the
  feature that just shipped.

**Important**
- **M-4** — the weekly reset bound's reject direction is unpinned; widening
  `SEVEN_DAY_MAX_AHEAD_S` 7.5 d → 30 d leaves all 1859 tests green, against a
  spec Testing item that names it explicitly. One test closes it.
- **D-4** — six of eight line citations in the spec's `### Known gap`, T6b and
  T7b are wrong at HEAD; one (`cli.py:422`) was never right. The ledger adds a
  third value (`1177`) for a symbol the spec calls `1186` and that lives at
  `1353`.
- **F-3** — `daa0c97` reports its successor's suite count (1848) as its own; the
  tree gives 1835. Previously unreported.
- **F-2** — `ea14004` claims 16 where the file gives 13.
- **F-1** — `cbaad44`'s subject names the wrong stages (already corrected in the
  plan and in `a3d8cdc`'s message; report only).

**Minor**
- **D-7** `pacing_state.py` docstring line citations drifted.
- **D-1 / D-2 / D-2b / D-3** — four spec/plan passages describing output the
  code no longer produces.
- **M-3** `per_model` parsed but never rendered.
- **M-1 / M-2** — `fetched_at` optionality and `Progress`'s two missing counters
  vs the spec's Architecture blocks.
- **M-5** — the "resume costs nothing" call-counter test was never built.
- **D-8** — `--no-pacing` help text.
- Task 9 brief Steps 1, 2 and 4 name expected-red tests that do not do the job;
  plan ruling **R4** has itself gone stale by one test.

# Things I could not verify, named

- Every private-copy mutation tally quoted in commit messages (`816d00a`,
  `4aef34a`, `a3d8cdc`, `f980ebe`, `ef6ad14`, `df23158`). The copies were
  deleted by design. I independently re-ran only the **four spec-mandated**
  mutations; those four are mine, measured, and all red.
- `3693e45`'s "all nine are substring `in`/`not in`".
- Whether `read_usage` genuinely costs zero tokens against a live account —
  the spec's 2026-09-05 measurement is taken on the author's word; I did not
  spawn `claude -p "/usage"` (and must not, from an offline review).
- The reviewer verdict documents under `docs/superpowers/…-verdicts/` — I read
  none of them, per instruction, and formed this verdict from the spec, the
  plan, the briefs and the diff only.

---

# Commands run (complete)

```bash
D=/Users/shawn/projects/llama/.superpowers/sdd/2026-09-05-usage-pacing-phase2
WT=/Users/shawn/projects/llama-wt-pacing2
S="$D/work/final-spec/snap"
PP="$S/packages/llama/src:$S/packages/herder/src:$S/packages/emcee/src"

mkdir -p "$D/final-spec" "$D/work/final-spec" && touch "$D/final-spec/final-spec.log"
cd "$WT" && git log --oneline ac7c428..3693e45         # 32 commits
cd "$WT" && git status --porcelain                      # empty, before and after
cd "$WT" && git diff --stat ac7c428..3693e45            # 47 files, +7914/-92
cd "$WT" && git diff -U3 ac7c428..3693e45 -- packages/llama/src/llama/cli.py packages/llama/src/llama/config.py
cd "$WT" && git diff ac7c428..3693e45 -- docs/superpowers/specs/2026-09-05-usage-pacing-phase2-design.md
cd "$WT" && git diff ac7c428..3693e45 -- docs/superpowers/plans/2026-09-05-usage-pacing-phase2.md
cd "$WT" && git diff ac7c428..3693e45 -- CLAUDE.md packages/llama/tests/test_config.py packages/llama/tests/conftest.py
cd "$WT" && git diff --stat ac7c428..3693e45 -- packages/herder/src/herder/openrouter.py   # EMPTY
cat packages/herder/src/herder/{usage,limits}.py packages/llama/src/llama/{pacing,pacing_state}.py

# citation verification (printed every cited line, at HEAD and at the citing commit)
for n in 389 426 440 2556 708 709 710 1186 236 300 422; do sed -n "${n}p" packages/llama/src/llama/cli.py; done
git show a3d8cdc:packages/llama/src/llama/cli.py | sed -n '440p;1186p;2556p;708,710p'
git show 61a314e:packages/llama/src/llama/cli.py | sed -n '236,242p;300,304p;420,424p'
git show 6db6ed4:packages/llama/src/llama/cli.py | sed -n '389p;426p'
grep -n "run_interpret\|_PIPELINE_RUN_STAGES\|come back and wait" packages/llama/src/llama/cli.py

# snapshot + shadowing proof
mkdir -p "$S" && cd "$WT" && git archive 3693e45 | tar -x -C "$S"
PYTHONPATH="$PP" "$WT/.venv/bin/python" -B -c "import llama,herder,emcee; print(llama.__file__)"
# -> resolves inside the snapshot
sed -i '' 's/^EWMA_ALPHA = 0.4$/EWMA_ALPHA = 0.9/' "$S/packages/llama/src/llama/pacing_state.py"
cd "$S" && PYTHONPATH="$PP" "$WT/.venv/bin/python" -B -m pytest -p no:cacheprovider -q packages/llama/tests/test_pacing_state.py
# -> FAILED test_ewma_alpha_is_pinned_at_point_4  (sentinel proven); restored

# per-commit sweep harness ($D/work/final-spec/sweep.sh): git archive <sha> -> snap, PYTHONPATH, python -B -m pytest
sweep.sh ea14004 packages/llama/tests/test_pacing_decide.py     # METHOD PROOF -> 13, claim says 16
sweep.sh <sha> [test files]                                      # x32, table above
sweep.sh 3693e45                                                 # 1859 passed, 7 deselected (matches the worktree)

# the four spec-mandated mutations, applied to the snapshot and restored from git after each
SEVEN_DAY_MAX_AHEAD_S 7.5*86400 -> 5.5*3600   -> 3 failed, 48 passed
observe: drop "or b.resets_at != a.resets_at" -> 1 failed (full suite: 1 failed, 1858 passed)
parse_usage_text: drop "or STALE_MARKER in text" -> 1 failed, 21 passed
run-level arm RateLimited -> HerderError       -> 1 failed, 57 passed
run-level arm: insert except HerderError above -> 7 failed, 51 passed

# extra probe: is the weekly bound's UPPER end pinned?
SEVEN_DAY_MAX_AHEAD_S 7.5*86400 -> 30*86400    -> 1859 passed, 7 deselected  (NOT PINNED)

# 6f7c126's countable claims
wc -l docs/superpowers/2026-09-05-usage-pacing-phase2-sdd-ledger.md          # 380
ls docs/superpowers/2026-09-05-usage-pacing-phase2-verdicts/ | wc -l          # 29 (28 reports + global-constraints)
grep -oE "\bR[0-9]+\b" .../sdd-ledger.md | sort -u -V                        # R1..R14
grep -c "minor (deferred)" .../sdd-ledger.md                                 # 46
cmp each committed verdict against its live source                           # identical=29 differs=0

# global constraints
grep -rn "import llama\|from llama" packages/herder/src/                     # no hits
sweep.sh 3693e45 packages/herder/tests/test_no_llama_imports.py packages/emcee/tests/test_no_llama_imports.py  # 4 passed
git diff ac7c428..3693e45 | grep -E '^\+.*(--batch|trust_age|--force)'       # prose only, no code
grep -rn "per_model" packages/llama packages/emcee                            # test fixtures only

# real rendered output (never asserted from memory)
$WT/.venv/bin/python -B $D/work/final-spec/render.py
```

Worktree `/Users/shawn/projects/llama-wt-pacing2` was never modified;
`git status --porcelain` was empty at the start and at the end. No commits were
made. Nothing was amended.
