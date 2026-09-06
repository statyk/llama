# Final fix wave — usage pacing phase 2

**Status: COMPLETE.** All of F1–F5 fixed, in 5 commits on `usage-pacing-phase2`
in `/Users/shawn/projects/llama-wt-pacing2`. Nothing merged, pushed, tagged,
rebased or amended. Working tree clean.

**Interpreter check** (run first and last, into the log):
```
./.venv/bin/python -c "import llama, herder; print(llama.__file__); print(herder.__file__)"
/Users/shawn/projects/llama-wt-pacing2/packages/llama/src/llama/__init__.py
/Users/shawn/projects/llama-wt-pacing2/packages/herder/src/herder/__init__.py
```
Both resolve inside the worktree.

**Baseline / final suite**, `cd /Users/shawn/projects/llama-wt-pacing2 && ./.venv/bin/python -m pytest -q`:
- baseline at `3693e45`: `1859 passed, 7 deselected`
- final at `b628cb2`: `1860 passed, 7 deselected` (+1 = the new F2 test; no tests lost)

## Commits

| sha | subject |
|---|---|
| `39700a4` | test(pacing): pin the weekly bound's reject direction and fix two rollover fixtures |
| `d883885` | docs(pacing): re-cite the boundary reads by symbol, and name the right race |
| `9818508` | docs(claude-md): describe the pacing this branch actually ships |
| `3024bae` | docs(pacing): fix drifted citations and Task 9's wrong expected-red sets |
| `b628cb2` | docs: keep the interpret gap loud, and mark the spec's two unbuilt promises |

Each message names the exact test command and its output.

---

## F1 — CRITICAL. CLAUDE.md documented the feature as not existing.

**Commits `9818508` and `b628cb2`.** File: `CLAUDE.md`, the paragraph formerly
opening "Two boundaries on what phase 1's pause guarantee actually covers".

Rewritten in two parts. A new lead paragraph describes what ships — reactive
plus proactive halves, the `claude -p "/usage"` meter via `herder.usage` (zero
tokens, not an inference call; `~/.claude.json`'s cache deliberately not read),
the learned EWMA in `pacing-state.json`, `pacing.decide()` returning
`Proceed`/`PauseUntil`, the two gate sites (pre-flight at the top of `_execute`,
per-show before each show's lock), `llama pacing`, and `--no-pacing` opting out
of both halves. Then **three** boundaries that remain:

- **(a) claude_cli-specific — substance kept.** `openrouter.py:37` still raises a
  plain `HerderError`, a 429 is still retried three times by
  `_with_transport_retry` and then fails the show. Re-verified by reading the
  file; also verified `git log origin/main..HEAD -- openrouter.py` is empty, so
  "deliberately untouched" is true of the branch, not just of intent.
- **(b) three stages, not four.** Says the catch covers `run_discover`,
  `run_search`, `run_winnow` (the three inside `_execute`'s try), that the arm
  must stay above any `except HerderError` since it subclasses it, and that the
  resume re-runs the whole interrupted stage (`should_run` is whole-stage). Then
  the surviving gap: `run_interpret` runs in `get` outside `_execute`, filed as
  **T6b, deliberately UNBUILT**, because it writes `criteria.json` only on
  success and `run resume` refuses a session without one — covering it is a
  resumability design (persist the raw query and stamped flags at run-claim
  time), not a catch. Bounded by the note that `--profile` never calls
  `run_interpret` (verified: `_get_profile` uses `profile.criteria`).
- **(c) run-level pause sites checkpoint but never sleep**, even under
  `--max-wait`; only the show loop sleeps. Operator consequence stated:
  `llama get --wait` shortly before a reset exits having done nothing and needs
  a manual `llama run resume`. Filed as **T7b, deliberately UNBUILT**.

Per the mid-task correction, the paragraph now also calls out explicitly that
**`interpret` and `discover` are different stages and both exist**, naming
`interpret (run_discover)` as the inherited phrasing that caused the muddle, and
that `_PIPELINE_RUN_STAGES` is a third triple excluding `discover`.

Every claim was read against source before writing: `_execute`'s try region and
its `except RateLimited` arm (cli.py 342–399), the `run_interpret` call site in
`_get_query` (cli.py:607), `_checkpoint_pause` (cli.py:176–200, no sleep
branch), the `pacing` command body (cli.py:1427–1456), `_get_profile`
(cli.py:629–638) and `openrouter.py:30–41`.

Covering test: none — documentation. Command: full suite, `1860 passed`.

## F2 — IMPORTANT. The weekly bound's reject direction.

**Commit `39700a4`.** File `packages/herder/tests/test_usage.py`, new test
`test_weekly_reset_far_beyond_the_seven_day_bound_is_rejected`: a weekly meter
whose reset is ~13.6 days ahead of the fixture clock must parse to
`Meter(7, None)`.

### Mutation evidence

**Named before running:** widen `usage.SEVEN_DAY_MAX_AHEAD_S` from `7.5 * 86400`
to `30 * 86400`; expected red set = exactly
`packages/herder/tests/test_usage.py::test_weekly_reset_far_beyond_the_seven_day_bound_is_rejected`.

**Actual:** exit 1, `1 failed, 1859 passed, 7 deselected`, failing set exactly
that one test. `expected_set_match=True`, verdict CAUGHT.

Anchor asserted to match exactly once; diff printed; source restored and the
restore byte-compared. Harness ran the **full** suite. Control (unmutated) run
in the same harness: exit 0 with the summary line `1860 passed, 7 deselected` —
so the harness demonstrably distinguishes GREEN from RED, and a SURVIVED verdict
requires exit 0 **and** a passed-count summary line.

## F3 — IMPORTANT. Two badly chosen rollover fixtures.

**Commit `39700a4`.** File `packages/llama/tests/test_pacing_state.py`. Names and
comments kept; only the data changed.

- **F3a** `test_a_window_rollover_contributes_nothing`: `_r(90), _r(2, OTHER_RESET)`
  → `_r(90), _r(92, OTHER_RESET)`. Was a −88 delta the *negative*-delta guard
  catches on its own, so the test was green under either guard alone.
- **F3b** `test_a_rollover_with_a_positive_delta_still_contributes_nothing`:
  `_r(10), _r(14, OTHER_RESET)` → `_r(10), _r(20, OTHER_RESET)`. At delta 4.0
  against a seeded 4.0 the EWMA was unchanged and the assertion failed on
  `samples` alone.

Divergence under the mutant, computed directly (both fields now move):
```
F3a: PacingState(per_show_delta=3.2, samples=4) vs seeded PacingState(4.0, 3)
F3b: PacingState(per_show_delta=6.4, samples=4) vs seeded PacingState(4.0, 3)
```

### Mutation evidence

**Named before running:** delete `or b.resets_at != a.resets_at` from
`pacing_state.observe`'s guard; expected red set = exactly
`test_a_window_rollover_contributes_nothing` **and**
`test_a_rollover_with_a_positive_delta_still_contributes_nothing`, both in
`packages/llama/tests/test_pacing_state.py`.

**Actual:** exit 1, `2 failed, 1858 passed, 7 deselected`, failing set exactly
those two. `expected_set_match=True`, verdict CAUGHT. Neither test was deleted;
both are now in the failing set, which is what the finding asked for.

## F4 — IMPORTANT. Stale line citations.

**Commits `d883885` (shipped source) and `3024bae` (spec + plan).** Every cited
line was printed before and after the change. Where the reference is to a
function or call site it is now a **symbol**, which cannot drift.

Shipped source, `packages/llama/src/llama/pacing_state.py` module docstring:
`cli.py:389` / `cli.py:426` (actual 486 / 523) → "`cli._execute`'s show loop:
the `reading_before` bound just above the show lock, and the second `_meter`
call passed straight into `record`".

Spec (`docs/superpowers/specs/2026-09-05-usage-pacing-phase2-design.md`) and plan
(`docs/superpowers/plans/2026-09-05-usage-pacing-phase2.md`):

| cited | actual | replaced with |
|---|---|---|
| `cli.py:440` | 607 | `cli._get_query` |
| `cli.py:2556` | 2760 | `cli.profile_add` |
| `cli.py:708-710` | 875–877 | the `ws.criteria.exists()` guard in `cli.run_resume` |
| `cli.py:1186` | 1353 | `cli.py`'s module-level `_PIPELINE_RUN_STAGES` |
| `cli.py:236-242` (plan, T7b) | 310–315 | `_execute`'s `isinstance(verdict, PauseUntil)` branch |
| `cli.py:300-304` (plan, T7b) | 382–399 | `_execute`'s `except RateLimited` arm |
| `cli.py:422` (plan, T7b) | never correct | re-derived: the deferred second pass's `file_lock(...)`, identified by the **absent** `blocking=False` that distinguishes it from the first pass (actual line 528) |
| `stages/interpret.py:13` | correct | still made a symbol reference |

Two citations were re-verified and left alone because they still resolve:
`limits.py:26` (`MAX_RESET_AHEAD_S = 5.5 * 3600`) and `openrouter.py:37` (the
non-200 `raise HerderError`). Pre-existing citations elsewhere in the codebase
(`gather.py`, `structure.py`, `emcee/*`) were not touched — out of this branch's
scope.

## F5 — MINOR (the four marked FIX, plus the two added mid-task).

**Commits `d883885`, `9818508`, `3024bae`, `b628cb2`.**

1. **`pacing_state.record`'s docstring** named the meter bias where it meant a
   lost update. Now says the lock prevents a lost update (both runs read the
   same state, later write discards the earlier boundary), and explicitly
   distinguishes that from the account-wide meter bias no lock can fix.
2. **CLAUDE.md's `llama pacing` clause** now includes the verdict line —
   `would proceed` / `would pause: <reason>`.
3. **`pacing: ` prefix drift**: spec (:405→408) and plan (:1496) now show
   `"pacing: usage read unavailable — pacing on limit errors only"`, matching the
   shipped string.
4. **Task 9's three wrong test references, and ruling R4.** All corrected, and
   every step is now **measured, not predicted** (I ran each; my own first
   prediction for Step 4 was wrong — see below):
   - **R4**: named two expected-red tests where there are **three** — the third
     is `test_per_model_meter_parses_percent_reset_and_strips_whitespace`, via
     the constant's second call site (the per-model meter's `parse_reset` call in
     `parse_usage_text`). Also now states *why*
     `test_parse_reset_bound_is_per_call_not_global` is structurally incapable of
     seeing the mutation: `test_limits.py` never imports `herder.usage`.
   - **Step 1**: rewritten as 1a (narrow to `5.5*3600` → 3 red, measured
     `3 failed, 1857 passed`) and 1b (**widen** to `30*86400` → 1 red, measured
     `1 failed, 1859 passed`), the widening direction being the dangerous one and
     unpinned until F2. Says to run the full suite, and why.
   - **Step 2**: expected red is now **both** rollover tests (measured
     `2 failed, 1858 passed`), and the text records the two conditions a fixture
     must meet — positive delta across the rollover, and a delta different from
     the seed — with what goes wrong if either is dropped.
   - **Step 4**: the prescribed mutant body is now a bare `raise`, not
     "catch and report as a stage failure". A reporting body cannot even run
     (`failures` is not bound until below the try), and a swallowing body
     additionally reddens
     `test_an_ordinary_stage_failure_is_not_turned_into_a_pause` and
     `test_pacing_disabled_lets_a_run_level_limit_propagate` — failures about the
     body, not the ordering. Measured for both candidates: swallowing body →
     **7 red** (2 of them unrelated to ordering); bare `raise` → **exactly 5 red**,
     all genuinely about which arm sees a `RateLimited`, with the two
     "propagate" tests staying green. Step 4 now names those five.
5. **Spec's "the three meters"** for `llama pacing` → "the two meters that
   render — session and weekly", since `per_model` is parsed but never
   displayed. The third meter was **not** added to the command; that stays
   parked. (Spec:91's "returns all three meters at once" is about `/usage`'s own
   output and is accurate — left alone.)
6. **(mid-task addition) the spec's other two unbuilt promises**, now marked
   filed-and-unbuilt in the same style as T6b/T7b rather than silently dropped:
   `progress` described as "shows done, shows remaining, learned per-show delta"
   when the shipped `Progress` carries only `per_show_delta`; and the
   "Resume costs nothing" test with a call-counting fake provider, which was
   never written (the property is `should_run`'s and predates this phase).
   Neither was built.

### Method note: my own Step-4 prediction was wrong, and the discipline caught it

For the swallowing-body mutant I named a 4-test expected set and measured 7.
Two of the three extras (`test_an_ordinary_stage_failure_is_not_turned_into_a_pause`,
`test_pacing_disabled_lets_a_run_level_limit_propagate`) were exactly the
"failures unrelated to the ordering" the finding predicted — which is what led to
the bare-`raise` candidate that isolates ordering cleanly. Had I checked only
"non-zero failures", the bad mutant would have scored CAUGHT and I would have
written the wrong prescription into the plan.

---

## REPORT ONLY — the three wrong commit messages. Nothing changed.

Recorded, not amended; history rewriting is not mine to do and the branch is
under review.

- **`cbaad44` "fix(cli): a limit during interpret/search/winnow now checkpoints"**
  — the subject overstates what landed. `interpret` is **not** covered; the catch
  covers `run_discover`/`run_search`/`run_winnow`. The commit's own body says so.
  This subject is a first-class instance of the `interpret`-vs-`discover`
  conflation F1 now calls out in CLAUDE.md.
- **`ea14004` "feat(pacing): shows_that_fit forecasts against the ceiling, not 100%"**
  — body says "(16 passed)"; the tree at that commit gives **13**.
- **`daa0c97` "fix(cli): the pacing line only speaks when there is a meter to speak about"**
  — body claims **1848**; the tree at that commit gives **1835**. Per the plan
  author's note, record this as a **forward reference rather than a fabrication**:
  the commit is code-only, its own body says "covering tests land in the next
  commit", and 1848 is its successor's count. It is still a number that does not
  reproduce at the commit that states it.

Three non-reproducing messages out of thirty-two swept is a **measured rate**,
not an anecdote.

## Declined / out of scope

Built nothing from the parked list: rendering the `per_model` meter in
`llama pacing`; the two `Progress` counters; the "resume costs nothing"
call-counting test. Per the mid-task correction, the spec sentences promising
those were **corrected or marked filed-and-unbuilt** instead (F5 items 5 and 6) —
documentation, not new surface.

Also untouched: T6b and T7b (stay UNBUILT), `openrouter.py`, the three commit
messages above, Task 9's Step 3 (not flagged and still accurate), and
pre-existing line citations outside this branch's files.

No tool refused me at any point; there is nothing to classify as a mechanical
guard or a permission denial.

## Files changed

- `CLAUDE.md`
- `packages/llama/src/llama/pacing_state.py` (docstrings only, no behaviour)
- `packages/herder/tests/test_usage.py`
- `packages/llama/tests/test_pacing_state.py`
- `docs/superpowers/specs/2026-09-05-usage-pacing-phase2-design.md`
- `docs/superpowers/plans/2026-09-05-usage-pacing-phase2.md`

Mutation harness kept at `/Users/shawn/projects/llama/.superpowers/sdd/2026-09-05-usage-pacing-phase2/work/final-fix/mutate.py`, `mutate2.py`,
`mutate3.py`; full transcript in `/Users/shawn/projects/llama/.superpowers/sdd/2026-09-05-usage-pacing-phase2/final-fix/final-fix.log`.
