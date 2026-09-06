# Task 7 — CODE-QUALITY review (Opus)

**Verdict: Task quality: Changes requested** — one Important finding, docstring-only.
Everything else is verified clean: the code is correct, the retry loop is sound, the
five new tests are load-bearing against the wrong implementations I built, and no test
was lost.

## Method

All measurement in an rsync copy (`--exclude .venv .git __pycache__ .pytest_cache`),
`find -name '*.pyc' | wc -l` = 0 in the copy, shadowed by `PYTHONPATH` and executed with
`/Users/shawn/projects/llama-wt-pacing-loose-ends/.venv/bin/python -m pytest -p no:cacheprovider`.
Copy proved live under pytest with a planted sentinel:

    packages/llama/src/llama/cli.py:3111: in <module>
    E   RuntimeError: SENTINEL-COPY-IS-LIVE

traceback path resolving inside the copy. The worktree was never modified
(`git status --porcelain` empty before and after). Baseline tree obtained with
`git archive a7839dc | tar -x` (no worktree/branch created). Copies deleted after the run.
Every mutant named its predicted red test BEFORE application; every hot-spin mutant ran
under a hard `timeout`.

## Counts — verified, nothing lost

| point | measured |
|---|---|
| baseline `a7839dc` | `1886 passed, 7 deselected` |
| code commit `7b2e0be` | `1891 passed, 7 deselected` |
| final `b7cc3a6` | `1891 passed, 7 deselected` |

`--collect-only` diff, baseline vs HEAD: exactly **5 added, 0 removed, 0 renamed** —
`test_a_limit_during_interpret_parks_a_resumable_session`,
`..._sleeps_at_most_once`, `..._within_max_wait_sleeps_and_finishes`,
`test_a_limit_while_resume_re_interprets_parks_the_session_again`,
`test_no_pacing_lets_a_limit_during_interpret_fail_the_run`.

## The plan's false claim — independently confirmed FALSE, and the correction is right

The spec's constraint 2 and the brief say dropping `stalled` at this site "HANGS rather
than reddening". Reproduced all three of the implementer's measurements:

| mutant | predicted red (stated first) | observed |
|---|---|---|
| **M-A** `stalled=stalled` → `stalled=False` in `_interpret_with_pause` | `test_a_limit_during_interpret_sleeps_at_most_once`, exit 1 not 124 | `1 failed, 40 passed in 0.57s`, **exit 1**, on `assert 1 == 0 … AttributeError("'NoneType' object has no attribute 'complete'")` |
| **M-B** M-A + the test's `times=99` → `times=10**9` | hang, exit 124 under `timeout 60` | **exit 124**, `Terminated: 15` |
| **M-C** guard restored, `times=10**9` kept | passes fast | `1 passed in 0.16s`, exit 0 |

So: the guard **is** pinned; the *mechanism* in the plan is wrong at this site; and it is
the guard, not the bound, that stops the spin. `times=99` is a deliberate and correct
choice — a red test in 0.2s beats a hung CI — and the implementer's rewritten *test*
docstring states exactly this. The correction is sound and the site-specific difference
from Task 6 is real.

## The inverted test — inversion necessary, property preserved, trap real

`test_request_is_written_even_when_interpret_fails`:

- **Inversion necessary, not convenient.** Its `exit_code != 0` asserted precisely the
  behaviour T6b removes. It could not stay.
- **Original property still pinned.** *M-I (mine)*: moved the `request.json` write from
  before `_interpret_with_pause` to after it. Predicted red: this test plus
  `parks_a_resumable_session`. Observed: `test_request_is_written_even_when_interpret_fails`,
  `test_the_preflight_gate_runs_before_interpret_is_paid_for`,
  `test_a_limit_during_interpret_parks_a_resumable_session`,
  `test_no_pacing_lets_a_limit_during_interpret_fail_the_run` — 4 failed. The
  write-before-the-call property is load-bearing.
- **The sleep trap was real.** *M-H (mine)*: removed the added `--no-wait`. Predicted:
  real 1h sleep → hang, exit 124 under `timeout 25`. Observed: **exit 124**. Config
  defaults confirm the arithmetic (`wait = True`, `unknown_reset_wait = 1h`,
  `max_wait = 6h`; the injected refusal names no reset so `resume_at` falls back to
  `now + 1h`, inside the cap). Left unchanged this test would have hung CI, not failed it.

## "What else produces `exit 0` + `STATE_PAUSED`?" — measured

*M-D (mine)*: replaced the shared-renderer call with a naive catch —
`mark_paused(ws, None, [], _pacing._now().isoformat(), scope, str(limited))` plus the
same three echoes. Predicted red: `parks_a_resumable_session` on the `resume_after`
assertion, plus `within_max_wait` and `sleeps_at_most_once`. Observed: 4 failed, and the
discriminating line in `parks_a_resumable_session` is exactly

    >   assert info.resume_after.startswith("2026-09-07T14:02")
    E   where '2026-09-06T08:00:00+00:00'.startswith

**The brief's own assertion set (`exit_code == 0`, `STATE_PAUSED`, `failures == []`,
`query == "GD 1973"`, `"run resume interp" in output`) passes against that wrong
implementation in full.** The implementer's four added assertions —
`providers["interpret"].calls == 1`, `not ws.criteria.exists()`,
`resume_after.startswith(...)`, and after the Step-5 resume `ws.criteria.exists()` +
`read_model(...).query` — are what make this test constrain what it claims. That is
precisely the dominant defect class of this run, caught and pre-empted by the implementer
rather than shipped.

Same for `within_max_wait_sleeps_and_finishes`: the brief's `calls >= 2` is satisfied by a
loop that never sleeps; the added `clock["now"] >= PF_NOW + 2h` is what pins the wait.

## Remaining mutants — all reproduced exactly as the implementer reported

| mutant | predicted red (stated first) | observed |
|---|---|---|
| M-E delete `if not pace.enabled: raise` | `test_no_pacing_lets_a_limit_during_interpret_fail_the_run`, alone | exactly that, `1 failed, 40 passed` |
| M-F `run_resume` reverts to bare `_interpret_and_stamp` | `test_a_limit_while_resume_re_interprets_parks_the_session_again`, alone | exactly that, `1 failed, 40 passed` |
| M-G delete `_get_query`'s `if criteria is None: return` | `..._parks_a_resumable_session`, `..._sleeps_at_most_once`, `test_request_is_written_even_when_interpret_fails` | exactly those three, `3 failed, 38 passed` |

## Control flow and design

- **Retry loop sound.** At most two interpret calls under `--wait`: refuse → nap →
  refuse → `stalled=True` → checkpoint. The `stalled` guard is load-bearing (M-A/M-B) and
  I make no suggestion to simplify it.
- **Shared helper for both call sites: right call.** `_interpret_with_pause` mirrors
  `_preflight_gate`'s established `proceed=False → caller returns` contract
  (`None` return), keeps one copy of an invariant whose duplication is the documented
  historical failure, and matches `_interpret_and_stamp` already being one copy for both
  entry points. Scope is correct — `run_resume` is otherwise untouched, and the wrap sits
  only inside the criteria-less branch (cli.py:1050-1071).
- **Not over-built.** No new flags, no new state, `decide()` untouched, no constants
  retuned. `profile_add` (cli.py:2961) remains the sole uncovered `run_interpret` call
  site, correctly documented as such.
- **Commit hygiene.** `feat(pacing): …` / `docs(pacing): …`, lowercase `type(scope):
  subject`, bodies explain why, test command quoted. The code commit's "1891 passed"
  claim is true at `7b2e0be` (measured).

## Findings

### Important 1 — `_interpret_with_pause`'s docstring still ships the claim this task measured false

`packages/llama/src/llama/cli.py:737-743`:

> the pause becomes a hot spin, which HANGS the suite rather than reddening it. No
> sleep-budget assertion can see that mutation; it is caught only by running these tests
> under a hard timeout and reading the exit code.

Half of that is true (a sleep-budget assertion cannot see it — `_sleep` is never reached).
The rest is measurably false **for the tests that ship**: M-A reddens
`test_a_limit_during_interpret_sleeps_at_most_once` in 0.57s at exit 1, with no timeout
harness anywhere. The implementer found this, corrected the *test* docstring in `b7cc3a6`
(the "`times=99` is load-bearing" paragraph), and left the copy-pasted source docstring —
the text a maintainer of this function reads first — asserting the opposite.

This matters beyond tidiness, and is self-invalidating in a specific way: the sentence
tells a future reader the pin needs an unbounded provider and a hard timeout. M-C shows
that change (`times=99` → `times=10**9`) keeps the suite green while converting the
mutant from a red test into a hang — i.e. acting on this docstring degrades the pin the
docstring exists to protect. It is also exactly the defect the `b7cc3a6` commit body
names as its own reason for existing ("a branch must not ship a comment asserting the
opposite of what its code does").

Note the identical sentence in `_preflight_gate` (cli.py:350-356) is **true** at that
site, so the fix is to make this one site-specific rather than to touch both. Suggested
replacement for the last two sentences: *"No sleep-budget assertion can see that
mutation, because `_sleep` is never reached. It is pinned by
`test_a_limit_during_interpret_sleeps_at_most_once`, whose provider is bounded so the
mutant reddens in 0.2s instead of hanging; unbounded, the same mutant hangs (measured,
exit 124). Do not 'simplify' `stalled=stalled` away, and do not unbound that provider."*

The same false sentence also appears in `7b2e0be`'s commit body — immutable history, no
action, recorded only so the record is complete.

### Minor 1 — the interpret pause's operator note is unpinned

*M-J (mine)*: dropped `note=INTERPRET_NOTE` from the `_render_pause` call. Predicted: no
test red. Observed: **`1891 passed`** — fully green. Its sibling `PREFLIGHT_NOTE` is
pinned by `packages/llama/tests/test_pace_loop.py:743`. The note is the only thing in the
terminal that tells the operator *what* did not complete, and the only thing
distinguishing this pause's output from the pre-flight gate's. One `assert "interpret did
not complete" in result.output` in `parks_a_resumable_session` closes it.

### Minor 2 — the request dict is spelled twice, and nothing pins that the two agree

`cli.py:778-781` writes `request.json` from one literal; `cli.py:791-793` passes a second,
separately-spelled literal to `_interpret_with_pause`; `run_resume` (cli.py:1068) then
re-interprets from the *persisted* one. A flag added to the write and not to the direct
call (or vice versa) would make a resumed run interpret with different flags than the
original, silently — no test would notice. The duplication is Task 5's, but Task 7 edited
the second literal, so it is fair to record here. Cheapest fix: pass the written dict
itself — `_interpret_and_stamp` reads by key, and `run_resume` already hands it the
`auto`/`plan` extras harmlessly.

### Minor 3 — one inaccurate row in the implementer's report

The report's table says "after code commit `1890 passed` (4 tests in at that point)".
Measured at `7b2e0be`: **1891**, and all five tests are in that commit — `b7cc3a6` touches
`test_sessions.py` only to rewrite one docstring. The commit body's number is right; the
report's intermediate row is not. No test was lost either way.

### Minor 4 — `config` untyped in the new signature

`_interpret_with_pause(config, ws: RunWorkspace, req: dict, pace: PaceOptions)` leaves
`config` bare where `_preflight_gate` types it `Config`. Matches its immediate sibling
`_interpret_and_stamp`, so this is consistency with local style rather than a defect.

## The `--no-pacing` guard (parent's open ruling) — endorse it

**The reasoning is right and the placement is right. Keep it.**

- **The premise is measured, not assumed.** M-E: delete the two lines and
  `test_no_pacing_lets_a_limit_during_interpret_fail_the_run` goes red — i.e. without the
  guard, `llama get --no-pacing` really does pause at interpret, falsifying `CLAUDE.md`'s
  pre-existing sentence "`--no-pacing` opts out of both halves". That is a pre-existing
  documented promise, so honouring it is a correctness requirement of the new site, not
  new scope.
- **Placement is exactly the sibling's.** `if not pace.enabled: raise` as the first
  statement of the `except RateLimited` arm, before `_render_pause` — byte-for-byte the
  shape at `cli.py:489-490` (`_execute`'s run-level catch) and `cli.py:544` (the per-show
  loop). All three catch sites now re-raise identically, which is what makes the
  four-sites-one-renderer claim in `CLAUDE.md` true rather than aspirational. A bare
  `raise` also preserves the traceback.
- **It costs nothing to the operator.** `request.json` is still written before the call
  under `--no-pacing`, and `run_resume` keys only on `criteria.json` / `request.json`
  existence, not on session state — so a `--no-pacing` run that exits 1 at interpret is
  still resumable by hand. The guard restores the pre-pacing exit code without
  surrendering T6b's resumability.
- **The alternative is worse.** Omitting it would make this the sole pause site where
  `--no-pacing` does not opt out, and the drift would sit in the one function whose
  docstring argues against exactly that.

Two lines and one test, with the deviation flagged in the report rather than buried.
Correct call.
