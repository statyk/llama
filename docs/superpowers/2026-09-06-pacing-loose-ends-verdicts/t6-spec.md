# Task 6 — SPEC-COMPLIANCE review (Opus) — VERDICT: APPROVE

No Critical or Important findings. Four Minor / informational items, one of which
(the brief's Step 7) should be corrected in the ledger.

## Verification performed (commands, not report-reading)

- Suite, in the worktree, with the mandated command:
  `cd /Users/shawn/projects/llama-wt-pacing-loose-ends && ./.venv/bin/python -m pytest -q`
  → **1886 passed, 7 deselected** — matches the expected count exactly.
  Venv proven first: `./.venv/bin/python -c "import llama; print(llama.__file__)"` →
  `/Users/shawn/projects/llama-wt-pacing-loose-ends/packages/llama/src/llama/__init__.py`.
- `test_pace_loop.py` **unedited**, verified from git, not the report:
  `git diff 0589bd3..63e2876 -- packages/llama/tests/test_pace_loop.py` → **empty**, and
  the commit's file list is exactly `cli.py` + `test_sessions.py`. The three named
  pre-flight tests are therefore untouched and green.
- Range is one commit (`63e2876`), message is `feat(pacing): ...` (lowercase
  `type(scope): subject`), body explains why. `pacing.py` / `decide()` untouched.
- Worktree left clean and unmodified by me (`git status --porcelain` empty).

## Brief conformance, step by step

- **Step 1/2** — brief's test kept **verbatim** (config with `backend = "claude_cli"`
  preserved, `read_usage`/`pacing._now`/`pacing._sleep` monkeypatches, invoke args, all
  three assertions), plus two added assertions. `PF_NOW` and `_preflight_reading` are
  module-level in `test_sessions.py` as the brief's "Produces for Task 7" requires.
  `CountingProvider` is defined **once** (line 523, Task 3's) — no second copy.
- **Step 3** — `_preflight_gate` matches the brief's signature and body, including
  `stalled=slept`, the `when=` pass-through, and both explanatory comments. Only
  deviation: `note` defaults to `PREFLIGHT_NOTE` (see ruling below).
- **Step 4** — `_execute` routes through it; the `_meter_applies` print block still reads
  the same bound `reading` and `state`. Behaviour-preserving (the three pre-existing
  pre-flight tests pass unedited, which is the evidence for that claim).
- **Step 5** — `_get_query` gates after the `request.json` write and before
  `_interpret_and_stamp`, with the `if pace is None` resolution the brief specifies.
- **Step 6** — suite green (see above).
- **Step 7** — mutation verified independently, below.
- **Step 8** — commit as specified.

## The scope addition (`run_resume`) — tightly scoped, well implemented

Read from source, not the report: the gate sits **inside** the
`if not ws.criteria.exists():` / `if ws.request.exists()` branch only, immediately before
`_interpret_and_stamp`. The `else:` (ordinary resume) path is untouched and still reaches
`_execute`'s gate with nothing spent ahead of it. `run_resume`'s diff is the gate plus a
comment expansion — **no refactor**; `ws` and `pace` were already in scope, so
`_preflight_gate`'s signature needed nothing. Its new test's docstring correctly names
`calls == 0` as the load-bearing assertion and the paused state as NOT load-bearing.

The re-`mark_paused` concern is genuinely benign: a criteria-less session can only have
been parked by an interpret-time gate, which by construction carries `outcome=None` and
no failures, so the rewrite loses nothing and `request.json` is untouched.

## Mutation checks — every prediction named BEFORE the mutant was applied

All mutation ran in an rsync copy at `.../scratchpad/t6spec-work/copy`, driven by
`<worktree>/.venv/bin/python -m pytest` with `PYTHONPATH` at the copy's three `src` dirs.
Shadowing proven before any mutant, plainly **and under pytest**, with a planted
`_T6SPEC_SENTINEL`: `llama.__file__` and `herder.__file__` both resolved inside the copy
and the sentinel was visible. Copy restored to byte-identical md5 afterwards.

| # | Mutant | Predicted red | Actual |
|---|---|---|---|
| A | `stalled=slept` → `stalled=False` | `test_preflight_sleeps_at_most_once` **hangs**; `-k preflight` → exit 124 | **exit=124**, twice; `-v` run shows it hangs exactly there |
| A' | same mutant, brief's named test ALONE | **PASSES** (exit 0) — the trap | **1 passed, exit=0** |
| B | `run_resume` gate moved AFTER `_interpret_and_stamp` | `test_resuming_a_criteria_less_session_gates_before_re_interpreting` on `calls == 0` | exactly that, 1 failed / 107 passed |
| C | `_get_query` gate removed | `test_the_preflight_gate_runs_before_interpret_is_paid_for` on `calls == 0` | exactly that, 1 failed / 107 passed |
| D | `PREFLIGHT_NOTE` **tail** changed | none (tail unpinned) | **1886 passed** — survives |
| E | `PREFLIGHT_NOTE` **prefix** changed | `test_a_preflight_pause_records_the_meters_reset_and_reason` | exactly that, 1 failed / 1885 passed |
| F | divergent `note=` at the `_get_query` site | none (new sites unpinned) | **1886 passed** — survives |

B and C confirm the two ordering tests discriminate "the gate runs FIRST" from "a gate is
PRESENT", with no collateral failures.

## Finding 1 (Minor, but record it) — the brief's Step 7 names the wrong test: CONFIRMED

Verified independently, and the implementer is right. Under the `stalled=False` mutant,
`-v` output shows:

    test_preflight_re_reads_the_meter_after_the_nap PASSED
    test_preflight_sleeps_at_most_once             <-- hangs here

Mechanism checked in the test source: `_re_reads_the_meter_after_the_nap` feeds 99 then 5,
so the window RECOVERS and there is never a second pause — `stalled` is never consulted.
`_sleeps_at_most_once` feeds `_readings(99)`, which never recovers, so the second pause
fires with `when` already past, `sleep_until` returns without calling `_sleep` (the
`sleep_budget=3` guard is never consumed) and the loop spins hot forever.

**This matters exactly as much as your dispatch feared:** running Step 7 with a `-k`
narrowed to the brief's named test returns **exit 0, 1 passed** — a green result that
would license "the guard is unpinned/unnecessary". The ledger should record
`test_preflight_sleeps_at_most_once` as the hanging test and that `-k preflight` (not a
narrower selector) is what makes the check work.

## Finding 2 (Minor) — the `PREFLIGHT_NOTE` deviation: SOUND, but the pinning claim is overstated

**My read: keep it.** It is a strict superset of the brief's interface (`note=` still
accepted, so Task 7 can pass its own), and the default is not merely convenient but
*semantically tied to the function*: any caller of `_preflight_gate` is by construction a
site where no work has run, which is precisely what the note says. The two other
`_render_pause` sites (the discover/search/winnow catch at cli.py:488 and the show loop at
:661) call `_render_pause` **directly** with their own distinct notes, so the
wrong-default-inherited hazard has no reachable call site.

**Correction to the implementer's justification.** The report says "the note text stays
pinned by the existing `test_pace_loop.py:743` assertion". Measured (mutants D/E), that
assertion is `assert "nothing has run yet" in captured.out` — a **prefix substring at one
site**. It pins the first four words; the tail `"; resume when the window resets"` is
**unpinned** (mutant D survives the full suite), and the note at the two NEW sites is
unpinned entirely (mutant F survives). So the constant is not justified by a test — it is
justified by *construction*, which is the stronger argument: with three literals the
drift the brief invited would be untestable at two of the three sites, whereas one
constant makes drift impossible without a deliberate `note=`. Approve the deviation, but
fold in the accurate reason, not the test-based one.

## Finding 3 (informational, no action) — the double meter read is already spec-sanctioned

The implementer flags "two `claude -p /usage` subprocesses at run start where there used
to be one" as a behaviour change awaiting a decision. It is not a new deviation: spec
section 1(a) has an **"Accepted cost, stated rather than engineered away"** paragraph
saying exactly "a query-mode run start now performs two meter reads instead of one" and
rejecting the threading-a-reading alternative for the same reason the implementer gives.
Measured to confirm conformance rather than mere plausibility: an instrumented query-mode
`get` in the copy reports `METER_READS 2`. Verified `_meter` is a pure `read_usage()` with
no `pacing_state` write, so the extra read cannot perturb the learned EWMA.

## Finding 4 (Minor, brief defect not implementation defect) — stale expected count

Brief Step 6 predicts `1882 passed`; actual is `1886`. Baseline drift plus the ruling's
extra test. The implementer predicted 1886 up front and did not adjust anything to reach
it. No action beyond correcting the brief at ratification.

## Process note worth carrying forward (my own near-miss)

`rsync -a` of the worktree also copies `__pycache__`, and pytest's assertion-rewritten
`.pyc` files bake in the ORIGINAL path in `co_filename`; because rsync preserves mtime and
size, Python reuses them. My first mutant-B run therefore printed a traceback with the
**worktree's** test path even though the copy was what was collected. The source was
byte-identical so no result changed, but a mutation run that trusted that path would have
concluded it was testing the wrong tree — or, worse, a run that mutated only a TEST file
would have silently executed the stale bytecode and scored an uncaught mutant. I purged
all `__pycache__` and `.pytest_cache` in the copy and re-ran every mutant clean; all table
rows above are from the post-purge runs. **Add `--exclude '__pycache__'` to the copy step
in the delegation mechanics.**

## ⚠️ Cannot verify from diff

None. Every claim above was checked against source, git, or a measured run.
