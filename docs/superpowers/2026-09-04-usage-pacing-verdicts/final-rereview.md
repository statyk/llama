# Final re-review — usage-pacing phase 1 fix wave

Scope: re-review of the 5-commit fix diff (`8ac1e3c..8ab8dd7`) against the 7 items from the
final whole-branch review. Read-only; no edits or commits made. `git status --porcelain`
confirmed empty before starting and again at the end (see below). One deliberate,
proven-and-restored mutation was applied to `packages/herder/src/herder/limits.py` for item 2's
RED/GREEN check; it was restored and verified byte-identical to the original before continuing.

## Per-item verdicts

1. **`stages/gather.py:993-1005` stale comment — ADDRESSED**, with a flagged imprecision.
   Read the new comment and `cli.py`'s `except RateLimited as exc:` (now at `cli.py:262-269`,
   inside `_process`). The core claim is true for the mainline path: `RateLimited` is caught
   before the broader `except (TaskFailed, HerderError, IAError)` (subclass ordering,
   confirmed), and when `pace.enabled`, the show is *not* added to `failures` — `limited = exc`
   is set instead, driving the pause/resume machinery in `_execute`'s loop. So the comment is
   no longer predicting nonexistent code; it describes real, shipped behaviour.
   **However**, the comment's unqualified claim "not recorded as a per-show failure" is only
   true when `pace.enabled`. The same `except RateLimited` block has an
   `if not pace.enabled:` branch (`cli.py:264-267`) that **does** append to `failures` and
   print `FAILED ...`, exactly the pre-pacing behaviour `PaceOptions.enabled`'s own docstring
   describes ("`False` restores the pre-pacing behaviour: a limit fails the show"). The new
   comment doesn't mention this fallback, so read literally and unconditionally it overclaims.
   This is a comment-precision gap, not a functional bug — no code changed here — so it does
   not change the verdict, but it is worth relaying: a tighter version would say "...not
   recorded as a per-show failure (unless pacing is disabled)".

2. **`herder/limits.py:53` unpinned subclassing — ADDRESSED**, `herder/tests/test_limits.py`
   (new `test_rate_limited_is_a_herder_error`), commit `f67a6d2`.
   Independently reproduced the RED/GREEN: mutated `class RateLimited(HerderError):` →
   `class RateLimited(Exception):`, cleared `__pycache__`, ran the new test alone with
   `PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -m pytest -q packages/herder/tests/test_limits.py::test_rate_limited_is_a_herder_error`
   — got `1 failed` (`assert issubclass(RateLimited, HerderError)` → `AssertionError`).
   Restored the file, `diff -q` confirmed byte-identical to the pre-mutation original,
   `git status --porcelain` empty, full suite green (1742 passed / 7 deselected). The test
   would genuinely catch a base-class regression; it is a real pin.

3. **`herder/__init__.py:2` dead re-export — ADDRESSED**, commit `a72e42f`.
   Ran `grep -rn "from herder import" packages/` myself (full listing, not just the three
   names) and checked every hit: none imports `RateLimited`, `classify`, or `parse_reset` from
   the top-level `herder` package — every real consumer of `RateLimited` already goes through
   `herder.limits` directly (`cli.py`, `gather.py`, `test_limits.py`), and `herder/limits.py`
   itself imports `HerderError` from `herder.provider`, not the top-level package, so there is
   no circular-import dependency on the deleted re-export either. `TIER_MODELS`/`HerderError`/
   etc., which some tests import from the multi-line `from herder import (...)` form
   (`test_model_tiers.py`), are untouched — only the three dead names were removed. No
   breakage.

4. **`cli.py:180-181` `_execute`'s `pace` default — CORRECTLY DECLINED.**
   See the independent verification below; the fixer's decline is correct.

5. **Spec audit-note line numbers — ADDRESSED**, commit `8ab8dd7`.
   Checked the current working tree directly: `cli.py:2030` is
   `except (LlamaError, TaskFailed, HerderError, IAError) as exc:` inside `_redo_batch`
   (confirmed by line context — the per-show loop shared by a plain selector `redo` and
   `redo --run`'s batch form), and `cli.py:2643` is
   `except (LlamaError, HerderError) as exc:` inside `main_cli()` (`def main_cli()` at line
   2630), the global boundary that does wrap `_execute`. Both exact line numbers and both
   descriptions in the corrected spec text match the working tree precisely.

6. **Spec status line — ADDRESSED**, commit `8ab8dd7`. `docs/superpowers/specs/2026-09-04-usage-pacing-design.md:3-4`
   now reads "phase 1 (the reactive pause/resume path) implemented; phase 2 (the proactive
   pre-flight gate) not yet" — matches shipped state.

7. **`cli.py:578-579` `run list` docstring — ADDRESSED**, commit `a8349d5`.
   Docstring now reads "List sessions awaiting approval, incomplete, or paused..." Verified
   `STATE_PAUSED` is a real attention state: `_ATTENTION_LABELS` (`cli.py:2306-2307`) maps
   `STATE_PAUSED: "paused"` alongside `STATE_AWAITING`/`STATE_INCOMPLETE`, and
   `attention_sessions` surfaces it, so the docstring is accurate.

## Item 4 — independent verification (the item that matters most)

Enumerated every `_execute(` call site in `cli.py` myself (`grep -n "_execute("`), independent
of the fixer's table:

| line | caller | passes `pace=`? |
|------|--------|------------------|
| 403  | `_criteria_run` (plain `get`) | yes — `pace=pace` |
| 420  | `_get_profile` (`get --profile`) | yes — `pace=pace` |
| 627  | `run_approve` | yes — `pace=pace` |
| 661  | `run_resume` | yes — `pace=pace` |
| 2055 | `_redo_run_level` | **no `pace=` kwarg** |

Read `_redo_run_level` in full (`cli.py:2034-2055`): its own docstring identifies it as
`redo --run SESSION --from search|winnow`, and its `_execute` call
(`_execute(config, ia, ledger, ws, criteria, criteria.count, True, human_gate=False,
force=False, force_stage=None, full_rationale=False)`) has no `pace` argument at all, so
`pace` is `None` there and `_execute`'s `if pace is None: pace = pace_options(config)`
(`cli.py:180-181`) is exactly what resolves it.

**My independent verdict: the decline is correct.** There are 5 call sites, not 4 as the
original review's premise assumed, and the 5th is real, reachable production code
(`llama redo --run <session> --from search` or `--from winnow`), not dead code. Making `pace`
a required parameter would raise `TypeError` at that call site — a genuine regression, which
would violate this fix wave's own "no behaviour change intended" constraint. The code at
`cli.py:180-181` is unchanged, confirmed by `git diff --stat 8ac1e3c..8ab8dd7` (only the
docstring at `cli.py:578-579` and comment-only touch counted in `cli.py`'s 4-line diff).

**The surviving-mutation question.** The original review's claim rested on making the branch
raise (or similarly break) and observing the suite stay green at 1741. Given the above, that
surviving mutation does **not** mean the branch is unreachable — it plainly is reached, every
time someone runs `redo --run --from search` or `--from winnow`. It means **no test exercises
that branch in a way that would notice its removal**: I grepped `test_redo_cmd.py` (which
extensively exercises `redo --run ... --from {package,search,winnow}`) for `RateLimited` and
found zero hits, and grepped `test_pace_loop.py` (which does test pacing behaviour) for
`redo` and also found zero hits. So the `redo --run` path is functionally tested (its
redo-and-package behaviour is covered), but its **pacing behaviour specifically is not** —
consistent with the wave's own "deliberately left alone" list item, "the `redo --run` funnel
lacking pacing flags": that command never exposes `--wait`/`--max-wait`/`--no-pacing`, so
nothing in the test suite has reason to probe what `pace` value it resolves to. This is a
real, if narrow, test-coverage gap on `redo --run`'s pacing behaviour, separate from (and not
fixed by) declining item 4 — declining was still the right call, since the fix for the gap is
"add pacing flags and tests to `redo --run`," not "make an already-passed-`None`-by-design
parameter required."

## Scope and breakage check

- Files touched by the fix diff: exactly `docs/superpowers/specs/2026-09-04-usage-pacing-design.md`,
  `packages/herder/src/herder/__init__.py`, `packages/herder/tests/test_limits.py`,
  `packages/llama/src/llama/cli.py`, `packages/llama/src/llama/stages/gather.py` — confirmed via
  `git diff --stat 8ac1e3c..8ab8dd7`, matching the review package's own file list exactly. No
  other file was touched.
- `cli.py`'s 4-line diff is docstring-only (item 7); `gather.py`'s diff is comment-only inside
  the `except RateLimited:` block (item 1) — both confirmed by reading the diff, no logic
  changed.
- Item 3's deletion doesn't break any import: verified above (no consumer of the three dead
  names via the top-level package, and `herder.limits` itself imports `HerderError` from
  `herder.provider`, not the top level, so no circular-import dependency was introduced or
  broken).
- Full suite re-run from repo root (`PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -m pytest -q`,
  `__pycache__` cleared first): **1742 passed, 7 deselected, 26 warnings** — matches the
  fixer's report exactly, +1 over the reported 1741 baseline, exactly item 2's new test.
- No new breakage found anywhere in the fix diff.

## Tree state

`git status --porcelain` confirmed empty before any work, and empty again now (the one
mutation, to `limits.py`, was restored via `mv` from the `.bak` and independently diffed
byte-identical before continuing). No edits, no commits made by this review.

## Deferred (out of scope, not affecting verdict)

Nothing new to add beyond what both final reviewers already triaged as deliberate
(`pause_scope` write-only, `TimeoutExpired` uncaptured, the `_fail` helper refactor,
`llm-failures/` pruning, local-vs-UTC instant rendering, continuation indents, the missing
end-to-end seam test, `redo --run` lacking pacing flags). The test-coverage gap surfaced under
item 4 above is the same "`redo --run` funnel lacking pacing flags" item already on that list,
not a new finding — I'm reporting the *reasoning* behind why the surviving mutation doesn't
imply dead code, per the instructions, not opening a new item.

## Overall verdict

**PASS.** 6 of 7 items ADDRESSED and verified true of the code (with one flagged
comment-precision nuance on item 1 that doesn't change its verdict); item 4's decline is
independently verified CORRECT — the premise was genuinely false, a 5th call site
(`_redo_run_level` / `redo --run --from search|winnow`) does not pass `pace`, and forcing the
parameter required would have been a real regression. No new breakage, all touched files
in scope, suite green at the reported count, tree clean.
