# Task 7 — SPEC-COMPLIANCE review

# Spec ✅

The diff (`a3d8cdc..b67b2a1`) does what Task 7 required, at the three places it
required, and nothing outside its scope. Two deliberate deviations are both
within-scope improvements. One raised concern is a real gap that belongs to the
plan, not to this task.

---

## The R3 ruling — verified independently

**Present.** `cli.py:404-405`:

```python
        when = (limited.when if isinstance(limited, PauseUntil)
                else resume_at(limited, pace))
```

and `cli.py:239` passes `when=verdict.when` at the pre-flight site.
`PauseUntil` was **not** given a `resets_at` property (`pacing.py:157-165`
docstring records why, naming the double-skew).

I reproduced both halves of the defect myself in a private copy at
`$D/work/t7-spec/copy`, PYTHONPATH-shadowed and **proven** shadowed with a
planted `_T7SPEC_SENTINEL` (`llama.cli.__file__`, `llama.pacing.__file__` and
`herder.usage.__file__` all resolved inside the copy), byte-identical to the
worktree before each mutation and restored after. Baseline
`test_pace_loop.py`: **44 passed**.

| Mutation | Result |
| --- | --- |
| Drop the `isinstance` guard → `when = resume_at(limited, pace)` | **1 failed, 43 passed** — exactly `test_a_proactive_pause_waits_for_the_meters_reset_not_the_unknown_default`, `resume_after` `2026-09-04T09:00:00+00:00` (now + `unknown_reset_wait_s`) instead of `10:02:00` (the meter's reset + one skew). |
| Drop `when=verdict.when` at the pre-flight site | **1 failed, 43 passed** — exactly `test_a_preflight_pause_records_the_meters_reset_and_reason`, same 09:00 vs 10:02 signature. |

Both mutants are caught, by the intended test, one test each — the "green suite,
feature quietly broken" outcome the ruling was written to prevent is closed at
**both** pause sites, not just the one the ruling named.

---

## The conftest fixture — verified, and verified to actually work

`packages/llama/tests/conftest.py:29-38`: present, `@pytest.fixture(autouse=True)`,
`monkeypatch.setattr(cli, "read_usage", ..., raising=False)`, verbatim from the
brief including the docstring.

I did not take the report's word for "no test can spawn a subprocess". In the
private copy I put a **witness-file `claude` stub** first on `PATH` (it appends
its argv to a file and exits 97; self-tested to prove the witness fires) and ran
`packages/llama/tests packages/herder/tests`:

```
1490 passed, 7 deselected, 24 warnings in 5.86s
WITNESS FILE: No such file or directory
```

**No test in either package spawns `claude`.** The 1490 also matches the
implementer's stated sub-suite baseline exactly. `read_usage` has exactly one
production call site (`cli.py:218`); `herder`'s own tests all inject a runner or
patch `usage._cli_runner`.

---

## Requirement checklist

| Requirement | Status |
| --- | --- |
| Autouse `_no_live_usage_meter` fixture, `raising=False` | ✅ verbatim; proven effective above |
| Imports: `read_usage`, `pacing_state`, `PauseUntil`/`Progress`/`decide` | ✅ `cli.py:16,30,31-33` |
| `shows_that_fit` **not** imported | ✅ absent from `packages/` repo-wide (`grep`: NONE) |
| `_meter` gated on `backend == "claude_cli"` | ✅ `cli.py:216` |
| `_meter` not unified with `pipeline.make_providers` | ✅ `cli.py:211-214` docstring says so explicitly; `make_providers` untouched |
| Gate 1: pre-flight **before** any run-level stage | ✅ `cli.py:229-242`, above `set_capture_dir` and above the `try` holding discover/search/winnow |
| Gate 2: per-show, **before** the show lock | ✅ `cli.py:387-395`, first statement of the loop body, above `lock_path`/`file_lock`; pinned by `test_the_gate_runs_before_the_show_lock_is_taken` |
| `unprocessed.extend(pending[idx:])` — the gated show is NOT dropped | ✅ `cli.py:394`; pinned by `..._leaves_the_gated_show_for_the_resume` ("2 shows left") |
| Gate 3: the delta folds each show's own before/after | ✅ `cli.py:410-418`; `test_the_learned_cost_folds_each_shows_own_before_and_after` pins **exactly five reads in order** and the EWMA (8, 18 → 12.0) |
| The learned cost reaches the next decision | ✅ `state = record(...)` rebinds; `test_the_learned_cost_is_what_stops_the_next_show` (85 under the 90 ceiling, 85 + 12 not) |
| `PauseUntil.__str__` returns `reason` | ✅ `pacing.py:170-174`; asserted by **equality** in three tests, matching T6's tightened `pause_reason` |
| `limited` annotation widened | ✅ `cli.py:332` `RateLimited \| PauseUntil \| None` |
| Pre-flight pause exits **zero**, session on the attention list (R20) | ✅ `_checkpoint_pause` + bare `return`; `test_a_preflight_pause_exits_zero_like_every_other_pause` |
| `count` not reduced | ✅ untouched — `shortlist_size=max(12, count)` and `choose_entries(shortlist, count, ...)` are unchanged context lines |
| `except RateLimited` before any `except HerderError` | ✅ both try blocks unchanged: `cli.py:285` (run-level, T6) and `cli.py:347` above `except (TaskFailed, HerderError, IAError)` at `:357` |
| `openrouter.py` untouched | ✅ 4 files in the stat, none of them herder source |
| No `--batch` / `--force` / `trust_age` | ✅ none added |
| No constant swept | ✅ `pacing.py`'s +14 lines are the docstring and `__str__` only; `EWMA_ALPHA` and both ceilings untouched |
| The brief's four tests, verbatim | ✅ plus `_reading` and the `LLMTaskConfig` import |

## Implemented beyond the brief

`PauseUntil`'s docstring, `_meter`'s second parameter, the `ran` flag, and 8
extra tests. All four serve requirements the brief itself states; none is scope
creep. Nothing in the diff belongs to Task 8.

---

## Ruling: deviation 1 — `_meter(config, pace)` also gates on `pace.enabled`

**Within-scope improvement. Accept.**

The spec says outright that "`--no-pacing` now disables the proactive gate as
well as the reactive pause" (design doc, CLI section). The brief's `_meter(config)`
would honour that in `decide` — which returns `Proceed` on any reading when
`opts.enabled` is False (`pacing.py:225`) — while still spending a
`claude -p "/usage"` subprocess per show to compute the input nothing reads.
That is not a second feature; it is the brief's own gate implemented one
condition short of what the flag promises. Pinned by
`test_no_pacing_never_reads_the_meter`, and the M3 mutant (drop the clause) is
caught. The docstring states both gates and why. Accept as written.

## Ruling: deviation 2 — a `Locked`/deferred show is not a cost boundary

**Within-scope, and required for correctness. Accept.**

The brief's own words are "after `_process(entry)` returns". On the `Locked`
path `_process` is never called, so `reading_before` and the following read
bracket an interval in which this run did no work. Folding it in teaches the
gate a zero-cost show and drags the EWMA down — an **under**-estimate, which is
precisely the direction `pacing_state.observe` already refuses at the source for
window rollovers (`pacing_state.py:38-44`, and its module docstring says so).
Implementing the brief literally here would have contradicted a guarantee the
module below it makes. `ran = False` on the `except Locked` arm is the minimum
change that achieves it. Pinned by `test_a_deferred_show_is_not_a_boundary`,
asserted through `read_state` rather than the artifact — the right assertion,
since "no boundary" and "no file" are the same observable. Accept.

## Ruling: concern 1 — the deferred second pass is ungated

**Correct scoping. Not a Task 7 defect. File it.**

The brief scoped the gate to "the `for idx, entry in enumerate(pending)` loop",
and widening it changes that pass's `deferred[idx:]` arithmetic, which is
phase-1 code with its own pinned semantics. The reactive `RateLimited` backstop
covers it at the cost the spec already accepts ("a boundary the proactive half
could not see costs one refused show, not a wrong multi-hour idle",
`pacing.py:11-13`).

Worth recording for the plan, since it is slightly worse than the report says:
the deferred pass takes a **blocking** lock (`cli.py:422`), so it can sit for an
arbitrary time and then process on a window whose last gate reading is stale by
that whole wait. **Minor**, follow-up not rework.

## Ruling: concern 2 — a pre-flight pause never sleeps, even when it would fit

**Not a Task 7 non-compliance. It IS a real gap, and it is a plan-level item.**
Graded **Important**.

Two readings of the spec, and both matter:

- **R20 itself is about the *signal*, not sleep-vs-checkpoint.** Its resolution
  is "no new signal is added… no distinct exit code, no stdout protocol", and
  the property it protects is that "the Ctrl-C path and the first-show path
  [are] identical". The implementation satisfies that, and it is *identical to
  Task 6's run-level catch* (`cli.py:300-304`), which also checkpoints without
  sleeping. Both run-level pause sites now behave alike. On R20's own terms:
  compliant.
- **But the spec's next sentence after the four touch points is "Rendering a
  pause is unchanged from phase 1 — sleep if it fits under `max_wait`, else
  checkpoint and exit 0"**, and it is not qualified to touch points 3 and 4.

The operator-visible consequence is a `--wait` contract break that phase 1 did
not have: `llama get --wait --max-wait 6h` started twenty minutes before a reset
used to enter the run, hit the limit reactively at a show, sleep, and finish.
With the pre-flight gate it exits immediately having done nothing. An unattended
`--wait` invocation now needs a manual `run resume`.

**Ruling: the brief is what Task 7 was asked to build, and Task 7 built it, so
this is not grounds to fail the task or to rework it now** — closing it needs a
re-decide loop around the pre-flight site that the brief did not scope, and
doing it here without also doing T6's run-level site would replace one asymmetry
with a worse one. I recommend the orchestrator file a single follow-up covering
**both** run-level pause sites (pre-flight and the T6 catch), or amend the spec
to state that run-level pauses deliberately do not sleep and why. It should not
be left as two reviewers' notes in two ledgers.

## Ruling: concern 3 — `state` read once, advanced only by `record`

Correct and already documented. A concurrent run's boundaries land in the file,
not in this run's copy; `pacing_state.record`'s locked read-modify-write keeps
the file right. Re-reading per show would buy little and cost a lock acquire.
No action.

---

## Findings

**Critical:** none.

**Important:**

1. `cli.py:236-242` (and, jointly, `cli.py:300-304` from T6) — the pre-flight
   pause never sleeps even when the wait fits under `--max-wait`. Ruled above:
   brief-compliant, spec-ambiguous, a `--wait` regression relative to phase 1.
   **Plan-level follow-up, not a Task 7 rework.**

**Minor:**

2. `cli.py:416-418` — `pacing_state.record` runs on every packaged show even
   when `pace.enabled` is False or the backend is `fake`/`openrouter`, where
   both readings are `None`. `observe` correctly returns the state unchanged,
   but `record` still does `root.mkdir`, acquires `pacing-state.json.lock` and
   writes `pacing-state.json`. **Measured, not inferred:** I ran `_execute` in
   the private copy under `--no-pacing` and under a `fake` backend and both
   created `pacing-state.json` (and, for the former, `pacing-state.json.lock`).
   Harmless, and the brief's snippet is unconditional too — but it is a lock
   plus an atomic write per show for a boundary nothing consults, and it sits
   slightly against deviation 1's own reasoning ("must not spend a subprocess
   per show on a reading nothing consults"). One-line fix if wanted:
   `if ran and reading_before is not None:`.
3. `cli.py:229-242` sits **above** `set_capture_dir(config.root / "llm-failures")`
   at `:245`, whose comment calls itself "the one place raw-output capture is
   switched on". There is now a `claude -p` subprocess above that line. No live
   effect — `read_usage` never raises and captures nothing — so this is a note
   for whoever next reads that comment, not a change request.
4. Concern 1's blocking-lock staleness, above.

---

## Cannot verify from the diff

- **The implementer's full-suite numbers (1814 → 1826).** I did not run the
  worktree suite, per the isolation rules. In my private copy
  `packages/llama/tests packages/herder/tests` gave **1490 passed, 7
  deselected**, which matches the implementer's stated sub-suite baseline
  exactly; the emcee/scripts remainder I did not run.
- **The 13-mutant sweep as a whole.** I independently reproduced M1 and M13
  (the R3 ruling) and confirmed both are caught by the intended test, one test
  each. M2–M12 I read but did not re-run.
- **Any live behaviour of `read_usage()`.** The real `claude` binary was never
  invoked — deliberately, and a booby-trapped stub on `PATH` proves the test
  suite did not invoke it either.
- **Whether the `--wait` regression in finding 1 matters to the operator in
  practice.** That is a product call, not something the diff can answer.

No tool refused me at any point. No commits made; the worktree is clean
(`git status --porcelain` empty) and was never written to.
