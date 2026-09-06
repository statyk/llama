# Task 6 code-quality review — Approved

`Task quality: Approved`

Scope: `63e2876` over `0589bd3`. All measurement done in an rsync COPY at
`scratchpad/t6qual-copy` (deleted afterwards); the worktree was never modified
(`git status --porcelain` empty before and after).

## Provenance of every number below

- Suite, mandated command, in the worktree:
  `cd /Users/shawn/projects/llama-wt-pacing-loose-ends && ./.venv/bin/python -m pytest -q`
  → **1886 passed, 7 deselected** (expected 1886). Venv identity proven first:
  `./.venv/bin/python -c "import llama; print(llama.__file__)"` →
  `/Users/shawn/projects/llama-wt-pacing-loose-ends/packages/llama/src/llama/__init__.py`.
- Mutation runs used `PYTHONPATH=<copy>/packages/{llama,herder,emcee}/src` with the
  worktree venv's **interpreter** via `-m pytest` (never a `.venv/bin/*` console
  script). Shadowing proven with a planted `_T6QUAL_SENTINEL` both plainly and
  **under pytest** — `llama.__file__` resolved inside the copy in both.

## Constraint checks

- **`test_pace_loop.py` unedited.** `git diff --stat 0589bd3..HEAD -- packages/llama/tests/test_pace_loop.py`
  → empty; the file is not in the commit's file list. All 8 `-k preflight` tests green
  (`8 passed, 64 deselected`). The extraction is behaviour-preserving.
- **`decide()` untouched**; no constants retuned. Commit style conforms.
- **Extraction is faithful.** Old `break` → `return True, reading`; old bare `return`
  → `return False, reading`; `state` still read once in `_execute` and reused for
  the forecast. No control-flow change.

## The dominant invariant: `stalled=slept`

Mutant A: `stalled=slept` → `stalled=False`. Predictions named before applying.

| run | predicted | actual |
|---|---|---|
| A1 `-k test_preflight_re_reads_the_meter_after_the_nap` | exit 0 (PASSES — does not catch) | **exit=0**, `1 passed` |
| A2 `-k test_preflight_sleeps_at_most_once` | exit 124 (hang) | **exit=124** |
| A4 the two NEW `test_sessions.py` tests | exit 0 (blind to the guard) | **exit=0**, `2 passed` |

Restored → `-k preflight` `8 passed`, exit 0.

**The implementer's correction to the brief's Step 7 is CONFIRMED and matters.**
The brief predicts the hang in `test_preflight_re_reads_the_meter_after_the_nap`;
that test *passes* under the mutant. Mechanism verified in source: its meter feeds
99 then 5, so the window recovers and there is never a second pause — nothing for
`stalled` to guard. `test_preflight_sleeps_at_most_once` feeds `_readings(99)`,
which never recovers; after the first nap `_clock` advances `now` to `when`, so
`sleep_until`'s `remaining <= 0: return` (pacing.py:84) fires **without calling
`_sleep`**, the `sleep_budget=3` guard is never consumed, and the loop spins hot.
Anyone re-running Step 7 with a `-k` narrowed to the brief's named test gets GREEN
and concludes the guard is unpinned. `-k preflight` is load-bearing; do not narrow it.

A4 is my own addition and is worth recording: **neither new test pins the guard**
(both drive `--no-wait`, so no nap ever happens). `test_pace_loop.py -k preflight`
is the sole pin. That is correct — the guard is pre-existing behaviour the
extraction preserves — but it means the pin lives in a file this task does not touch.

I found no way to simplify `stalled=slept` away and am not proposing one.

## The ordering bar — met

Predictions named before applying; both mutants relocate the gate to AFTER
`_interpret_and_stamp` (gate PRESENT, wrong place).

| mutant | predicted red | actual |
|---|---|---|
| B — `_get_query` gate relocated | `test_the_preflight_gate_runs_before_interpret_is_paid_for` on `calls == 0` | **`1 failed, 1885 passed`**, `assert 1 == 0`, exactly that test |
| C — `run_resume` gate relocated | `test_resuming_a_criteria_less_session_gates_before_re_interpreting` on `calls == 0`; Task 5's `test_run_resume_reinterprets_a_session_that_never_got_criteria` stays green | **`1 failed, 1885 passed`**, exactly that test; Task 5's test green |

Both tests fail on RELOCATION, not merely on absence. The bar is met, and the
implementer's mutation 2/3 results reproduce.

## Extraction integrity (my own extra probes)

| mutant | predicted red | actual |
|---|---|---|
| E — `return True, reading` → `return True, None` | the `"pacing: 5h 65%"` test near test_pace_loop.py:1044 | **5 failed** — all `test_the_run_start_line_*` / `test_the_shortfall_clause_*`. Held. |
| F — `return False, reading` → `return True, reading` | `test_preflight_gate_pauses_before_any_stage_runs`, `..._still_checkpoints_under_no_wait`, `..._sleeps_at_most_once`, + both new tests | **4 failed**: `..._pauses_before_any_stage_runs`, `test_a_previous_runs_estimate_reaches_the_preflight_gate`, + **both new tests**. Core held; I over-predicted two (recorded honestly). |

The `(proceed, reading)` contract is pinned in both components.

## The `run_resume` gate (the orchestrator's ruling) — implemented well

Scoped exactly as instructed: inside `if not ws.criteria.exists()` / `if ws.request.exists()`
only. The ordinary resume path is untouched and still reaches `_execute`'s gate
with nothing spent ahead of it. `ws` and `pace` were already in scope; no signature
churn.

**"Is re-marking an already-`paused` session correct, and is anything lost?"
Measured, not reasoned.** A probe test in the copy captured the marker before and
after the resume:

    BEFORE resume_after='2026-09-06T07:10:00+00:00' pause_reason='limit'
    AFTER  resume_after='2026-09-06T10:02:00+00:00' pause_reason='5h window at 99%'
           outcome=None  failures=[]  state='paused'   (exit 0)

Correct, and nothing is lost. `_write` rewrites `session.json` wholesale, but the
only fields that could carry information — `outcome` and `failures` — are
necessarily `None`/`[]` on a criteria-less session (it has run no shows), and
`_render_pause` passes exactly those. The stale 07:10 instant is *replaced* by the
window the operator must now actually wait for, which is the point: a `run list`
reader acts on `resume_after`, and leaving the passed-over instant would be worse
than rewriting it. `request.json` is untouched, so the run is resumable again.

## Findings

**1. Minor — dangling cross-reference introduced by this diff.** `cli.py:478-480`
still says run_interpret "runs in `get` outside _execute entirely; the comment at
its call site says why wrapping it would not help." This diff **deleted that
call-site comment** (replaced with the gate comment), so the reference now points
at nothing; and since Task 5 it is doubly stale — `run_interpret` has a second call
site in `run resume`. Task 7 wraps that call and will falsify the claim outright,
so Task 7 should own the rewrite.

**2. Minor — three decorative assertions in the `run_resume` test, and the one
behaviour I asked about is unpinned.** In `test_resuming_a_criteria_less_session_gates_before_re_interpreting`,
`state == STATE_PAUSED` and `ws.request.exists()` are both **true before the command
runs** (the test's own `mark_paused` + `write_artifact` setup writes them), and
`not ws.criteria.exists()` is implied by `calls == 0`. No false claim — the
docstring says outright that only `calls == 0` is load-bearing, which is the
discipline I want. But the re-marking decision measured above is pinned by nothing
in the diff. One line would fix it and would make the paused assertion
non-vacuous:

    assert json.loads(ws.session.read_text())["resume_after"] == "2026-09-06T10:02:00+00:00"

Mitigated by `_render_pause`'s own coverage (`test_a_preflight_pause_records_the_meters_reset_and_reason`
pins the same arithmetic through `_execute`), which is why this is Minor.

**3. Minor — the brief's test docstring narrates the pre-fix world in the present
tense.** "The gate lives at the top of `_execute`, which in query mode runs AFTER
run_interpret" is a description of the code as it *was*; post-fix it reads as a
false statement about the code as it is. Verbatim from the brief and the assertions
themselves are sound (mutant B), so this is prose only — "used to live" fixes it.

**4. Minor — `_get_query`'s `if pace is None: pace = pace_options(config)` is
unreachable.** `get` is the sole caller and always passes a non-None `pace`.
Brief-prescribed, and the implementer's Task 7 note treats it as an explicit local
invariant, which is a fair justification for keeping it. Recorded, not requested.

**5. Minor / informational — two meter subprocesses at query-mode run start where
there was one.** I agree with the implementer's call not to thread the reading
through `_execute`'s signature for the benefit of one of five entry points. I'd go
further than the implementer did: the second read is arguably *correct* rather than
merely tolerable, since interpret spends tokens between the two gates and
`_execute`'s pacing line must describe the post-interpret window. Cost is a process
spawn on a 0-token call.

**6. Minor — the note text is pinned only on its prefix.** Measured: replacing
`PREFLIGHT_NOTE` wholesale reddens `test_a_preflight_pause_records_the_meters_reset_and_reason`
(G1, `1 failed`); changing only the tail to `"nothing has run yet; come back
whenever"` is **green** (G2, `1886 passed`). Pre-existing — the brief's three
literals were pinned to exactly the same depth — and not a regression.

No Critical or Important findings.

## Ruling requested: `PREFLIGHT_NOTE` — I endorse the deviation

- **Strict superset: yes, confirmed.** `note: str = PREFLIGHT_NOTE` keeps `note`
  keyword-only and still accepts an explicit value, so anything Task 7 wants to
  pass is unaffected.
- **Sound, because there is no site that could silently inherit a wrong note.**
  Every `_preflight_gate` caller is by construction a "nothing has run yet" site.
  The other two pause sites — the run-level `RateLimited` catch (cli.py:488) and the
  per-show loop (cli.py:661) — pass their own distinct notes to `_render_pause`
  **directly** and never route through the gate. The usual objection to a defaulted
  note (a future site quietly getting the wrong text) has no population here, and
  the constant's name binds it to the gate.
- **It strengthens pinning rather than weakening it.** With three literals, the
  single assertion at `test_pace_loop.py:743` pinned one of them and left the other
  two free to drift — the precise hazard `_render_pause`'s own docstring exists to
  document. With the constant, that one assertion covers all three sites. The
  residual (prefix-only pin, finding 6) is unchanged from the brief's version.

Keep it as written.
