# Final re-review — usage pacing phase 2 fix wave (`3693e45..b628cb2`)

Scope: the 5-commit fix diff only. Reviewed against a `git archive b628cb2`
snapshot at `$D/work/final-rereview/snap`; the worktree was never modified
(`git status --porcelain` empty, HEAD `b628cb2` before and after).

## Verdicts

- **F1 (CRITICAL) — ADDRESSED.** All four required parts present and every claim
  in the new text checks out against source at `b628cb2`. Detail below.
- **F2 (IMPORTANT) — ADDRESSED.** New test
  `test_weekly_reset_far_beyond_the_seven_day_bound_is_rejected`
  (`packages/herder/tests/test_usage.py:111`) pins the **reject** direction.
  Mutation MUT-A (widen `SEVEN_DAY_MAX_AHEAD_S` to `30 * 86400`) over the FULL
  suite: `1 failed, 1859 passed` — exactly that test, matching the predicted set.
- **F3 (IMPORTANT) — ADDRESSED.** Both fixtures fixed in place, neither deleted,
  names and comments kept (`test_pacing_state.py:31` `_r(90), _r(92, OTHER_RESET)`;
  `:56` `_r(10), _r(20, OTHER_RESET)`). Mutation MUT-B (delete
  `or b.resets_at != a.resets_at` from `pacing_state.observe`, `pacing_state.py:56`)
  over the FULL suite: `2 failed, 1858 passed` — the failing set is **exactly**
  those two tests. Both new deltas are positive (so the negative-delta guard on
  the next line cannot cover for the deleted clause) and both differ from the
  seeded 4.0 (so `per_show_delta`, not only `samples`, moves) — the two
  properties F3a/F3b demanded.
- **F4 (IMPORTANT) — ADDRESSED.** Every citation the wave changed resolves at
  `b628cb2`; every citation it left in place also resolves. Table below.
- **F5 (MINOR set) — ADDRESSED.** All six items done, and nothing was built:
  `Progress` still carries only `per_show_delta` (`pacing.py:178-183`), no
  call-counting "resume costs nothing" test exists anywhere in
  `packages/llama/tests/`, and `per_model` appears in `packages/llama/` only as a
  test constructor kwarg — never rendered.

## New Critical / Important breakage introduced by the fix diff

**None.** The one shipped-source file the diff touches
(`packages/llama/src/llama/pacing_state.py`) is behaviourally identical: parsing
both revisions and comparing the ASTs with docstrings stripped returns
`AST-IGNORING-DOCSTRINGS IDENTICAL: True`. Everything else is docs plus two test
fixtures and one new test. Baseline full suite on the snapshot: `1860 passed,
7 deselected`, exit 0 — matching the caller's measurement.

## F1, claim by claim

### The four required parts

| Required part | Present | Verified against |
| --- | --- | --- |
| (i) boundary (a), openrouter, kept in substance | yes | `openrouter.py:37` is verbatim `raise HerderError(f"openrouter returned {resp.status_code}: …")`; `openrouter.py` is not in the diff |
| (ii) boundary (b)'s core claim rewritten as false-since-T6/T7 | yes | `cli.py:381-397` — `except RateLimited as exc:` wrapping `run_discover`/`run_search`/`run_winnow`, calling `_checkpoint_pause` and returning |
| (iii) the genuinely remaining gap survives | yes | "It does **not** cover `run_interpret` … filed as **T6b, deliberately UNBUILT**", with the unresumability reason spelled out |
| (iv) the `interpret (run_discover)` parenthetical called out explicitly | yes | "**`interpret` and `discover` are DIFFERENT stages and both exist** — the phrase `interpret (run_discover)`, inherited from phase 1's spec, conflated them and is the origin of every muddle" |
| (also required) T7b run-level-never-sleeps asymmetry | yes | boundary **(c)**, naming both sites and the `llama get --wait` consequence |

### Every statement in the new text, checked

| Claim | Verdict | Evidence at `b628cb2` |
| --- | --- | --- |
| meter is `claude -p "/usage"` via `herder.usage`, a live `GET /api/oauth/usage`, zero tokens, not an inference call | TRUE | `usage.py` module docstring lines 8-11 ("num_turns 0, total_cost_usd 0, every token count 0"); `read_usage` at `usage.py:107` |
| `~/.claude.json`'s cached utilization deliberately not read (measured serving an already-expired window) | TRUE | `usage.py` docstring lines 13-18; no reference to `.claude.json` anywhere in `herder/` |
| cost learned across show boundaries, persisted as an EWMA in `pacing-state.json` (`llama.pacing_state`) | TRUE | `pacing_state.STATE_NAME` / `observe` / `record`; EWMA at `pacing_state.py:63` |
| `pacing.decide()` turns a reading + estimate into `Proceed` or `PauseUntil` | TRUE | `pacing.py:199-230` |
| gates at the top of `_execute` (pre-flight, before the opening burst) … | TRUE | `cli.py:303-317` — `_meter` → `decide` → `isinstance(verdict, PauseUntil)` → `_checkpoint_pause` → `return`, all above the `try` at `cli.py:342` |
| … and before each show's lock | TRUE | `cli.py:486-492` (`reading_before`, `decide`, break) sits above `file_lock(lock_path, blocking=False)` at `cli.py:496` |
| `llama pacing` prints the same picture read-only | TRUE | `cli.py:1427-1458`; reuses `_pacing_line` and `decide`, writes nothing |
| `--no-pacing` opts out of both halves | TRUE | `_meter_applies` gates on `pace.enabled` (`cli.py:220`); both `except RateLimited` arms re-raise / fail the show when `not pace.enabled` (`cli.py:383`, `cli.py:452`) |
| a failed meter read degrades to the reactive backstop alone and says so | TRUE | `decide` returns `Proceed()` on `reading is None` (`pacing.py:223`); `_pacing_line` prints the unavailable sentence (`cli.py:274`), gated on `_meter_applies` so it is only printed where the backstop really is live |
| (a) an openrouter 429 is retried three times by `_with_transport_retry` and then fails the show | TRUE | `openrouter.py:37` raises bare `HerderError`; `RateLimited` (the only class excluded from the retry) is `limits.py:106` and openrouter never raises it |
| (b) the `except RateLimited` arm "must stay above any `except HerderError`, since it subclasses it" | TRUE | `class RateLimited(HerderError)` at `limits.py:106`; MUT-C below demonstrates the reversal is caught |
| (b) it checkpoints the session `paused` with a `resume_after` instead of exiting 1 | TRUE | `_checkpoint_pause` (`cli.py:176-200`) → `mark_paused(…, resume_after=when.isoformat(), …)` (`sessions.py:59-67`) |
| (b) those stages gate on `should_run` at WHOLE-STAGE granularity, so the interrupted one re-runs from the top | TRUE | `discover.py:34`, `search.py:35`, `winnow.py:71` — one `should_run` on the stage's single output artifact |
| (b) `run_interpret` runs in `get` outside `_execute` entirely | TRUE (incomplete, see minors) | `run_interpret` is called only at `cli.py:607` (in `_get_query`, reached from `get`) and `cli.py:2760` (in `profile_add`) — neither inside `_execute` |
| `_PIPELINE_RUN_STAGES` is a third, different triple that excludes `discover` | TRUE | `cli.py:1353` — `["interpret", "search", "winnow"]`, module level |
| T6b: `run_interpret` writes `criteria.json` only on success | TRUE | `stages/interpret.py:13` — `write_artifact` after the task call |
| T6b: `run resume` refuses a session without one | TRUE | `cli.py:875-877` — `if not ws.criteria.exists(): … raise typer.Exit(1)` |
| T6b: a limit during interpret still exits 1 having spent one LLM call | TRUE | unhandled `RateLimited` propagates out of `_get_query`/`get` |
| T6b: `--profile` runs read stored criteria and never call `run_interpret` | TRUE | `_get_profile` (`cli.py:626`) has no `run_interpret` call; the only two call sites are 607 and 2760 |
| (c) both run-level pause sites return after `_checkpoint_pause` even when the wait would fit inside `--max-wait`; only the per-show loop sleeps | TRUE | `cli.py:311-317` and `cli.py:381-397` both `return` immediately; the only `sleep_until` is `cli.py:561`, inside the show loop's pause block, and `_checkpoint_pause` has no sleep branch |

No newly written statement in the paragraph is false.

## F4 — citation table

Every citation the fix wave changed, plus the ones it deliberately kept.

| Where | Old | New | Resolves at `b628cb2`? |
| --- | --- | --- | --- |
| `pacing_state.py` module docstring | `cli.py:389` / `cli.py:426` | prose: "`cli._execute`'s show loop: the `reading_before` bound just above the show lock, and the second `_meter` call passed straight into `record` once `_process` has returned" | YES — `reading_before` `cli.py:486`, lock `cli.py:496`, `_process` `cli.py:497`, `record(…, _meter(config, pace))` `cli.py:522-523` |
| `pacing_state.record` docstring | "two concurrent runs would otherwise each fold the other's burn…" (wrong: that is the meter bias) | "What the lock prevents is a LOST UPDATE… Not the same thing as the account-wide meter bias" | YES — correct description of a read-modify-write under `file_lock` (`pacing_state.py:110-114`) |
| plan T6 known gap | `cli.py:440` | `cli._get_query` | YES — call at `cli.py:607`, `def _get_query` at `cli.py:590` |
| plan T6 known gap | `cli.py:2556` | `cli.profile_add` | YES — call at `cli.py:2760`, `def profile_add` at `cli.py:2733` |
| plan T6 known gap | `stages/interpret.py:13` | "`stages/interpret.py`'s `run_interpret`" | YES |
| plan T6 known gap | `cli.py:708-710` | "the `ws.criteria.exists()` guard at the top of `cli.run_resume`" | YES — `cli.py:875-877`, first guard in the body |
| plan T6 known gap | `_PIPELINE_RUN_STAGES` (`cli.py:1186`) | "`cli.py`'s module-level `_PIPELINE_RUN_STAGES`" | YES — `cli.py:1353`, module level |
| plan T6b scope | `cli.py:440`, `cli.py:2556` | `cli._get_query`, `cli.profile_add` | YES (as above) |
| plan T7b pre-flight site | `cli.py:236-242` | "`cli._execute`'s `isinstance(verdict, PauseUntil)` branch above the try" | YES — `cli.py:311`, try at `cli.py:342` |
| plan T7b reactive site | `cli.py:300-304` | "`_execute`'s `except RateLimited` arm" | YES — `cli.py:381` |
| plan T7b deferred pass | `cli.py:422` (**never correct**) | "`file_lock(…)` with no `blocking=False`, unlike the first pass" | YES — deferred pass `cli.py:528` takes a blocking lock; first pass `cli.py:496` passes `blocking=False`. Re-derived, not shifted. |
| spec `_PIPELINE_RUN_STAGES` | `cli.py:1186` | "`cli.py`'s module-level `_PIPELINE_RUN_STAGES`" | YES |
| spec run_interpret call sites | `cli.py:440`, `cli.py:2556` | `cli._get_query`, `cli.profile_add` | YES |
| spec run resume guard | `cli.py:708-710` | "the `ws.criteria.exists()` guard at the top of `cli.run_resume`" | YES |
| spec, KEPT as-is | `stages/interpret.py:13` | (unchanged) | YES — line 13 is `write_artifact(ws.criteria, criteria)` |
| spec, KEPT as-is | `openrouter.py:37` | (unchanged) | YES |
| spec, KEPT as-is | `limits.py:26` | (unchanged) | YES — line 26 is `MAX_RESET_AHEAD_S = 5.5 * 3600` |
| spec + plan, KEPT as-is | `2026-09-04-usage-pacing-design.md:346-348` | (unchanged) | YES — those lines carry the literal `` `interpret` (`run_discover`) `` phrase |
| CLAUDE.md, KEPT as-is | `packages/herder/src/herder/openrouter.py:37` | (unchanged) | YES |

No re-cited-but-still-wrong reference found. No line-number citation was left
pointing at `cli.py`, the file whose numbering drifted.

## Mutation table

Harness: snapshot copy shadowed via `PYTHONPATH` at the three
`snap/packages/*/src` dirs, run with `"$WT/.venv/bin/python" -B -m pytest -p
no:cacheprovider -q` from the snapshot root, `PYTHONDONTWRITEBYTECODE=1`.
**Never** `$WT/.venv/bin/pytest`.

Harness proofs, both directions, before any mutation was believed:
- resolution: `llama.pacing_state.__file__`, `herder.usage.__file__`,
  `emcee.__file__` all under the snapshot;
- RED: a planted `raise RuntimeError("SENTINEL-SNAPSHOT-REACHED")` produced a
  traceback citing `packages/llama/src/llama/pacing_state.py:129` collected from
  the snapshot root;
- GREEN: unmutated full suite exits 0 with an explicit
  `1860 passed, 7 deselected` summary line. A SURVIVED verdict here requires
  both.

Every mutation applied through a helper that aborts unless the anchor matches
**exactly once** (`ANCHOR-OK: 1 match`), with the applied `diff` printed, and
each was restored and re-diffed clean. Every run is the FULL suite.

| Mutation | Expected red set (declared before running) | Actual | Match |
| --- | --- | --- | --- |
| **MUT-A** `usage.SEVEN_DAY_MAX_AHEAD_S` `7.5*86400` → `30*86400` (F2, widening) | exactly 1: `test_usage.py::test_weekly_reset_far_beyond_the_seven_day_bound_is_rejected` | `1 failed, 1859 passed` — that test | **EXACT** |
| **MUT-B** delete `or b.resets_at != a.resets_at` from `pacing_state.observe` (F3) | exactly 2: `test_pacing_state.py::test_a_window_rollover_contributes_nothing`, `::test_a_rollover_with_a_positive_delta_still_contributes_nothing` | `2 failed, 1858 passed` — those two | **EXACT** |
| **MUT-C** insert `except HerderError: raise` above `_execute`'s `except RateLimited` (plan Step 4 as now written) | exactly 5: `test_pace_loop.py::test_run_level_ratelimited_is_caught_before_herdererror`, `::test_ratelimited_during_discover_checkpoints_too`, `::test_ratelimited_during_winnow_checkpoints_instead_of_exiting`, `::test_a_run_level_pause_records_the_reset_plus_skew_once`, `::test_a_run_level_pause_says_what_a_resume_will_redo` | `5 failed, 1855 passed` — those five | **EXACT** |
| **MUT-D** same insertion with a swallowing body (`return`) — spot-check of the wave's self-report | 7: MUT-C's five plus `::test_an_ordinary_stage_failure_is_not_turned_into_a_pause` and `::test_pacing_disabled_lets_a_run_level_limit_propagate` | `7 failed, 1853 passed` — exactly those seven | **EXACT** |
| **MUT-E** `SEVEN_DAY_MAX_AHEAD_S` → `5.5*3600` (plan Step 1a / ruling R4) | exactly 3, all `test_usage.py`: `::test_weekly_reset_uses_the_weekly_bound_not_the_session_one`, `::test_parses_all_three_meters_from_the_real_output`, `::test_per_model_meter_parses_percent_reset_and_strips_whitespace` | `3 failed, 1857 passed` — those three | **EXACT** |

Snapshot verified pristine afterwards: `diff -r` of a fresh `git archive b628cb2`
extraction against the mutated-and-restored snapshot → 0 lines, exit 0.

### Self-reported method finding — CONFIRMED

The wave reported predicting 4 and measuring 7 for the swallowing-body Step-4
mutant, "the three extras being failures unrelated to ordering". MUT-D reproduces
`7 failed, 1853 passed` exactly, and two of the extras over the bare-`raise`
mutant are precisely
`test_an_ordinary_stage_failure_is_not_turned_into_a_pause` and
`test_pacing_disabled_lets_a_run_level_limit_propagate` — the two the report and
the corrected plan both name as body-not-ordering failures. The bare-`raise`
replacement it wrote into the plan does isolate ordering: MUT-C leaves those two
green. One nuance for the record: of the three tests beyond the wave's 4-test
prediction, only two are body-related; the third was an ordering failure it had
simply not predicted (MUT-C's five are all ordering). The wave's own text is
careful about this — it says "2 of them unrelated to ordering" in the numbered
list, and the looser "three extras" phrasing appears only in the prose method
note. The substance of the finding stands.

Also confirmed: `packages/herder/tests/test_limits.py` imports only
`datetime`, `zoneinfo`, `herder.limits` and `herder.provider` — it never imports
`herder.usage`, so R4's structural-incapability claim about
`test_parse_reset_bound_is_per_call_not_global` (`test_limits.py:195`) is exact.

## Out-of-scope checks the brief asked for

- **Nothing outside scope was built.** Diff touches 6 files only. `openrouter.py`
  untouched. No `--batch`, no `--force` pacing flag, no `trust_age` anywhere in
  `packages/`. T6b unbuilt (`run_interpret` still uncovered at `cli.py:607` /
  `cli.py:2760`). T7b unbuilt (no `sleep_until` at either run-level site).
  `per_model` never rendered by `_pacing_line` or `llama pacing`. `Progress` has
  one field. No "resume costs nothing" test.
- **No amend or rebase.** Linear chain `3693e45 → 39700a4 → d883885 → 9818508 →
  3024bae → b628cb2`; `cbaad44`, `ea14004`, `daa0c97` and `3693e45` all still
  exist and are ancestors of `b628cb2` under their original SHAs.
- **The three wrong commit messages were left alone.** `cbaad44` still reads
  "fix(cli): a limit during interpret/search/winnow now checkpoints"; `ea14004`
  and `daa0c97` unchanged. Recorded in the fix report, not amended, as required.

## Deferred minors (do not extend the loop)

1. `CLAUDE.md`: "A limit during interpret still exits 1 having spent one LLM call
   and **written nothing**" — `claim_run_dir` (`cli.py:600`, `workspace.py:129-138`)
   has already `mkdir`'d the run directory by then, so an empty run dir is left
   behind. "Written no artifacts" would be exact.
2. `CLAUDE.md` (b): "`run_interpret`, which runs in `get` outside `_execute`
   entirely" omits the second call site, `profile_add` (`cli.py:2760`). The spec
   and plan both name it; only CLAUDE.md's one-clause version is partial.
3. Plan Step 3 (`plan:1629`) still says `Run: pytest packages/herder/tests/test_usage.py -q`,
   contradicting the new "run the **full** suite for every mutation below"
   instruction added at Step 1. Steps 1, 2 and 4 were converted; Step 3 was not.
4. Plan Step 6 (`plan:1664`) still says "Expected: PASS, **1742** baseline plus
   the new tests" — that is the phase-1 baseline; the branch is at 1860.
5. Plan Step 1b's "Measured: 1 failed, 1859 passed" and Step 2's "2 failed, 1858
   passed" are stated without a date on the Step-1b line (Step 2 and R4 carry
   "measured 2026-09-06"). Cosmetic consistency only; both numbers reproduce.
6. `pacing_state.py`'s `test_a_window_rollover_contributes_nothing` comment still
   reads "the delta spans a reset and is meaningless… would drag the estimate
   toward zero", written for the old negative fixture. It remains true of the new
   `90 → 92` fixture (delta 2.0 < seed 4.0 still drags downward), so this is a
   note, not a defect.

## Commands run (all teed to `final-rereview.log`)

```
mkdir -p $D/final-rereview && touch $D/final-rereview/final-rereview.log
ls $D/TAKEN_OVER $D/taken-over/final-rereview            # both absent, checked twice
cd $WT && git log --oneline -8 && git status --porcelain # clean, HEAD b628cb2
mkdir -p $D/work/final-rereview/snap
cd $WT && git archive b628cb2 | tar -x -C $D/work/final-rereview/snap
cat $WT/.superpowers/sdd/2026-09-05-usage-pacing-phase2/review-3693e45..b628cb2.diff
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=$S/packages/herder/src:$S/packages/llama/src:$S/packages/emcee/src
cd $S && $WT/.venv/bin/python -B -c "import llama.pacing_state, herder.usage, emcee; print(...)"
# → all three __file__ under the snapshot
# sentinel: append raise RuntimeError("SENTINEL-SNAPSHOT-REACHED") to pacing_state.py
$WT/.venv/bin/python -B -m pytest -p no:cacheprovider -q packages/llama/tests/test_pacing_state.py
# → ERROR collecting … packages/llama/src/llama/pacing_state.py:129 … SENTINEL-SNAPSHOT-REACHED ; restored clean
$WT/.venv/bin/python -B -m pytest -p no:cacheprovider -q
# → EXIT=0 ; 1860 passed, 7 deselected, 26 warnings in 7.01s
# MUT-A  → EXIT=1 ; 1 failed, 1859 passed  (test_weekly_reset_far_beyond_the_seven_day_bound_is_rejected)
# MUT-B  → EXIT=1 ; 2 failed, 1858 passed  (the two rollover tests)
# MUT-C  → EXIT=1 ; 5 failed, 1855 passed  (the five test_pace_loop ordering tests)
# MUT-D  → EXIT=1 ; 7 failed, 1853 passed  (those five + the two body tests)
# MUT-E  → EXIT=1 ; 3 failed, 1857 passed  (the three test_usage tests of R4)
# each preceded by "ANCHOR-OK: 1 match" and a printed diff, each restored and re-diffed clean
cd $WT && git archive b628cb2 | tar -x -C $D/work/final-rereview/verify
diff -r verify snap        # → exit 0, 0 lines
$WT/.venv/bin/python <ast-strip-docstrings compare of pacing_state.py @3693e45 vs @b628cb2>
# → AST-IGNORING-DOCSTRINGS IDENTICAL: True
cd $WT && git status --porcelain   # → empty ; git rev-parse HEAD → b628cb2…
```

No tool refused any call during this review.
