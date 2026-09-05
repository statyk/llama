# Final fix-wave report — usage-pacing phase 1

Branch `usage-pacing`, working directly in `/Users/shawn/projects/llama` (no worktree). Baseline
confirmed clean (`git status --porcelain` empty) before any change.

## Summary

6 of 7 items applied and committed. Item 4 was investigated per the explicit
"verify before you act" instruction and its premise was found **false** — a
5th `_execute` call site does not pass `pace`, so the parameter cannot be made
required. Declined with evidence below; nothing else was touched.

Commits (all on `usage-pacing`, in order):

1. `8587499` — `docs(gather): fix a comment that outlived the pause handler it predicted`
2. `f67a6d2` — `test(herder): pin RateLimited's HerderError subclassing`
3. `a72e42f` — `fix(herder): drop the dead RateLimited/classify/parse_reset re-export`
4. `a8349d5` — `docs(cli): mention paused in run list's docstring`
5. `8ab8dd7` — `docs(spec): correct the status line and a stale audit note's line numbers`

Final suite: `./.venv/bin/python -m pytest -q` → **1742 passed, 7 deselected** (up from the
baseline 1741 by the one new test in item 2). Tree is clean (`git status --porcelain` empty).

## Item 1 — gather.py stale comment (Important) — DONE, commit `8587499`

`packages/llama/src/llama/stages/gather.py:993-1005` (the `except RateLimited:` block in the
`align_structure` fallback). The old comment said the pause handler "does not exist yet" and
that a later task would make the pause real. Verified the handler exists now: `cli.py:263`'s
`except RateLimited as exc:` inside `_process` (checked *before* the broader
`except (TaskFailed, HerderError, IAError)`, since `RateLimited` subclasses `HerderError`),
which marks the session paused with a resume time rather than recording a per-show failure.

Rewrote the comment to describe that behaviour instead of predicting it. No code change —
comment only.

## Item 2 — RateLimited/HerderError subclassing unpinned (Important) — DONE, commit `f67a6d2`

Added `test_rate_limited_is_a_herder_error` to
`packages/herder/tests/test_limits.py`, asserting both `issubclass(RateLimited, HerderError)`
and `isinstance(RateLimited("boom"), HerderError)`. Added the `HerderError` import.

**Order of operations, per the mandate**: committed the test (and item 1) first so
`git status --porcelain` was empty *before* mutating `limits.py`, so a restore could never
silently drop uncommitted work.

RED/GREEN evidence:

```
$ git status --porcelain
(empty)

$ sed -i.bak 's/^class RateLimited(HerderError):/class RateLimited(Exception):/' packages/herder/src/herder/limits.py
$ grep -n "^class RateLimited" packages/herder/src/herder/limits.py
53:class RateLimited(Exception):

$ find /Users/shawn/projects/llama -name __pycache__ -prune -exec rm -rf {} +
$ PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -m pytest -q packages/herder/tests/test_limits.py::test_rate_limited_is_a_herder_error
F                                                                        [100%]
=================================== FAILURES ===================================
_____________________ test_rate_limited_is_a_herder_error ______________________
>       assert issubclass(RateLimited, HerderError)
E       assert False
E        +  where False = issubclass(RateLimited, HerderError)
1 failed in 0.18s
```
→ **RED confirmed.**

```
$ mv packages/herder/src/herder/limits.py.bak packages/herder/src/herder/limits.py
$ grep -n "^class RateLimited" packages/herder/src/herder/limits.py
53:class RateLimited(HerderError):
$ git status --porcelain
(empty)

$ find /Users/shawn/projects/llama -name __pycache__ -prune -exec rm -rf {} +
$ PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -m pytest -q
1742 passed, 7 deselected, 26 warnings in 7.79s
```
→ **GREEN confirmed**, tree still clean after restore.

## Item 3 — dead re-export in herder/__init__.py (Minor) — DONE, commit `a72e42f`

Removed `from herder.limits import RateLimited, classify, parse_reset` from
`packages/herder/src/herder/__init__.py`.

Verification before deleting: `grep -rn "from herder import" packages/` (full listing checked),
then narrowed specifically to the three re-exported names:

```
$ grep -rn "from herder import" /Users/shawn/projects/llama/packages/ | grep -E "RateLimited|classify|parse_reset"
(no output)
```

No consumer anywhere in `packages/` imports `RateLimited`, `classify`, or `parse_reset` from the
top-level `herder` package — every real usage of `RateLimited` (e.g. `cli.py`, `gather.py`,
`test_limits.py`) already imports it from `herder.limits` directly, which is also what herder's
own internal modules must do to avoid a circular import.

## Item 4 — dead default in cli.py `_execute`'s `pace` parameter — DECLINED, premise false

Instructed to verify before acting: "find every call site of `_execute` yourself (including the
`redo --run` path) and confirm each passes a `PaceOptions`. If any does not, do NOT make it
required — report that instead."

Found **5** call sites of `_execute` in `packages/llama/src/llama/cli.py`, not 4:

| line | caller | passes `pace=`? |
|------|--------|------------------|
| 403 | `_criteria_run` (plain `get`) | yes — `pace=pace` |
| 420 | `_get_profile` (`get --profile`) | yes — `pace=pace` |
| 627 | `run_approve` | yes — `pace=pace` |
| 661 | `run_resume` | yes — `pace=pace` |
| 2055 | `_redo_run_level` (`redo --run … --from search\|winnow`) | **no** — no `pace=` kwarg at all |

`_redo_run_level` (line 2034) is exactly "the `redo --run` path" the instructions named to check.
It calls `_execute(config, ia, ledger, ws, criteria, criteria.count, True, human_gate=False,
force=False, force_stage=None, full_rationale=False)` — no `pace` argument — so `pace` is `None`
there and `_execute`'s `if pace is None: pace = pace_options(config)` branch (`cli.py:180-181`)
is exactly what runs for that call. This matches the task's own "Everything else is
deliberate" list, which separately backlogs "`redo --run` funnel lacking pacing flags" — i.e.
this is the known, deliberately-unfinished wiring, not dead code.

**Declined**: did not touch `_execute`'s signature or the `if pace is None` branch. Making
`pace` a required parameter would break `_redo_run_level`'s call with a `TypeError` at
`redo --run --from search|winnow` time — a real behaviour change and regression, the opposite
of the "no behaviour change is intended" premise for this fix wave.

## Item 5 — spec's audit note has wrong line numbers/description — DONE, commit `8ab8dd7`

`docs/superpowers/specs/2026-09-04-usage-pacing-design.md` (was line ~368). Verified against
the current branch point:

- `cli.py:2030` is the `except (LlamaError, TaskFailed, HerderError, IAError)` clause inside
  `_redo_batch`'s per-show loop (`packages/llama/src/llama/cli.py:2007-2031`) — the batch form
  shared by a plain selector `redo` and `redo --run`'s state-based batch. Not `fix`/`triage`.
- `cli.py:2643` is `main_cli`'s global error boundary (`except (LlamaError, HerderError) as exc:`
  inside `def main_cli()` at line 2630) — which **does** wrap `_execute` (it's the outermost
  catch-all for anything that escapes every stage- and run-level handler), not a site "outside
  `_execute`".

Rewrote the parenthetical to name the current line numbers and describe both sites accurately.

## Item 6 — spec's status line says "not yet implemented" — DONE, commit `8ab8dd7`

Changed line 3 from `Status: approved design, not yet implemented.` to state that phase 1 (the
reactive pause/resume path) is implemented and phase 2 (the proactive pre-flight gate) is not —
matching the phase-1/phase-2 language already used throughout the rest of the document (e.g.
the R20/R22 amendments).

## Item 7 — `run list` docstring omits `paused` — DONE, commit `a8349d5`

`packages/llama/src/llama/cli.py:579` (`run_list`). Changed `"""List sessions awaiting approval
or incomplete (the attention-list); complete sessions never show here."""` to add `paused`,
matching `_ATTENTION_LABELS` (`cli.py:2306-2307`) which lists `STATE_AWAITING`,
`STATE_INCOMPLETE`, and `STATE_PAUSED` as the three attention states.

## Things deliberately left alone

Per the "do NOT touch" list: `pause_scope` write-only, `TimeoutExpired` not captured, the
`_fail` helper refactor in `claude_cli._run`, `llm-failures/` pruning, local-vs-UTC instant
rendering, continuation indents, the missing end-to-end seam test, and the `redo --run` funnel
lacking pacing flags (this last one is exactly what makes item 4's premise false — confirmed,
not re-opened).

## Test commands used throughout

- `find /Users/shawn/projects/llama -name __pycache__ -prune -exec rm -rf {} +` before every
  run touching mutated/restored files.
- `PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -m pytest -q` (repo root) — never
  `.venv/bin/pytest`.
- All runs green at 1742 passed / 7 deselected except the deliberate RED check in item 2's
  proof (1 failed, scoped to the single new test, immediately restored to GREEN).

## Concerns

- Item 4 could not be applied as specified; see above. This should go back to the orchestrator
  as a finding, not a completed fix — the "four call sites" claim in the review was inaccurate
  by one, and that one is load-bearing.
- No other concerns. Suite green, tree clean, no unintended behaviour changes.
