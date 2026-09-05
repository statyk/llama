# Task 8 report: mutation pass and documentation

## Pre-flight

`git status --porcelain` was empty at start. Branch `usage-pacing`, working
directly in `/Users/shawn/projects/llama` (no worktree, no venv creation, per
instructions).

## BASELINE

`./.venv/bin/python -m pytest -q` → **1741 passed, 7 deselected** (matches
the expected baseline exactly).

## Mutation pass

All five mutations were applied one at a time, `__pycache__` cleared before
and after each, restored immediately after its run, and confirmed
byte-identical via `git diff --stat` (empty) after restoring. Every mutation
was **KILLED** (RED) — no unpinned constraints found.

| # | Mutation | Command | Exit code | Result |
|---|---|---|---|---|
| 1 | `cli.py`: `except RateLimited` moved below `except (TaskFailed, HerderError, IAError)` | `./.venv/bin/python -m pytest packages/llama/tests -q -k rate_limit` | 0 (1 passed) | **See caveat below — the literal command is misleading.** Genuinely killed when run against the actual behavioral tests: `pytest packages/llama/tests/test_pace_loop.py packages/llama/tests/test_sessions.py -q` → 17 failed, 31 passed. |
| 2 | `tasks.py:36` (actually line 40 in this checkout): removed `RateLimited` from `_with_transport_retry`'s no-retry tuple | `./.venv/bin/python -m pytest packages/herder/tests/test_llm_tasks.py -q -k rate_limit` | 1 | KILLED — `assert 3 == 1` in `test_rate_limit_is_not_retried_as_transport_noise`, plus `test_rate_limit_propagates_from_a_research_task` (2 failed) |
| 3 | `limits.py`: `MAX_RESET_AHEAD_S` raised to `48 * 3600` | `./.venv/bin/python -m pytest packages/herder/tests/test_limits.py -q` | 1 | KILLED — 3 failed incl. `test_reset_past_today_rolls_to_tomorrow_only_within_the_bound` (named in the brief), also `test_reset_just_over_the_bound_is_refused` and `test_reset_exactly_now_rolls_to_tomorrow` |
| 4 | `limits.py`: added `(re.compile(r"error", re.I), None)` to `_SIGNATURES` | `./.venv/bin/python -m pytest packages/herder/tests -q` | 1 | KILLED — 2 failed: `test_dropped_connection_stays_a_plain_herder_error` (test_claude_cli.py) and `test_dropped_connection_is_not_a_rate_limit` (test_limits.py), exactly the dropped-connection guard the brief names |
| 5 | `stages/gather.py`: deleted `except RateLimited: raise`, leaving only `except (TaskFailed, HerderError)` | `./.venv/bin/python -m pytest packages/llama/tests/test_stage_gather.py -q -k rate_limit` | **1** (verified, not 4) | KILLED — `test_gather_rate_limit_during_llm_alignment_propagates_and_does_not_flag`: `DID NOT RAISE RateLimited`, log shows `WARNING gather.py:994 align_structure failed: ...` confirming the swallow-and-flag defect the test guards against. Path sanity-checked: `test_stage_gather.py` exists in this checkout (`test_gather.py` does not), 1 test collected, genuine failure not a collection error. |

### Mutation 1 finding — the brief's literal `-k rate_limit` command is a false-negative risk, not a source defect

Running exactly the command given in the brief (`pytest packages/llama/tests
-q -k rate_limit`) selects **one** test — `test_stage_gather.py::
test_gather_rate_limit_during_llm_alignment_propagates_and_does_not_flag` (the
mutation-5 test) — because none of the tests that actually exercise `cli.py`'s
catch ordering (`test_pace_loop.py`, `test_sessions.py`) have "rate_limit" in
their names (e.g. `test_a_usage_limit_pauses_the_run_instead_of_failing_the_show`,
`test_the_show_that_hit_the_limit_is_retried_not_dropped`). That one selected
test is untouched by the cli.py mutation and passes, so the literal command
reports "1 passed" — which looks like a clean run and would have certified
mutation 1 as pinned without ever touching the code path it was meant to
exercise. This is the same class of instrument risk the brief flags for
mutation 5 (a `-k` filter or bad path silently not running the intended
test), just manifesting as "selects the wrong one test" rather than "selects
zero tests." I verified the constraint is genuinely pinned by running the
correct files directly (`test_pace_loop.py` + `test_sessions.py`, 17 of 48
failing under the mutation). Restored file is byte-identical to HEAD;
no source change is proposed — flagging the brief's example command as
imprecise, not the implementation.

## RESTORED

After all five mutations were reverted and pycache cleared:
`./.venv/bin/python -m pytest -q` → **1741 passed, 7 deselected** — matches
BASELINE exactly. Instrument confirmed sound; no discrepancy to investigate.

`git status --porcelain` was empty again after the mutation pass, confirming
no source files were left mutated.

## Docs changes

Committed as `a17b647` on `usage-pacing`:

- **`CLAUDE.md`**
  - `## Commands`: extended the `llama get` entry with the exact text from
    the brief (`--wait/--no-wait`, `--max-wait`, `--no-pacing`, pause-at-show-
    boundary behavior, `should_run` skip on resume).
  - Architecture / LLM-layer bullet: added the brief's `RateLimited`
    classification paragraph verbatim, plus **two boundary notes** requested
    beyond the brief:
    - **(a) openrouter gap**: `packages/herder/src/herder/openrouter.py:37`
      raises a plain `HerderError` on any non-200 (confirmed by reading the
      line), so a 429 there is retried three times by `_with_transport_retry`
      like ordinary transient noise and then fails the show — phase 1's pause
      guarantee is `claude_cli`-specific.
    - **(b) run-level stages gap**: `_execute`'s only pause handling lives in
      the per-show loop (`cli.py`'s `_process`, wrapping `process_show`);
      `run_discover` (interpret), `run_search` and `run_winnow` all run
      earlier in `_execute` with no RateLimited handling at all (verified by
      reading `cli.py:174-253` — no try/except around any of the three).  A
      limit hit there is an unhandled exception: exit 1, no session marker,
      no `paused` state, no `resume_after`. Phase 2's pre-flight gate is what
      is meant to cover this and does not exist yet.
- **`docs/workflow.md`**: in the `llama run list` section, added a paragraph
  after the `usage limit reached` example table noting that example is now
  the `--no-pacing` picture — with pacing on (default), the same refusal
  pauses the run instead of recording a per-show failure, session state
  becomes `paused`, and the marker carries `resume_after` (verified field
  names against `sessions.py`: `STATE_PAUSED`, `mark_paused(...,
  resume_after, ...)`).
- **`docs/superpowers/specs/2026-09-04-usage-pacing-design.md`**: added
  Amendment (R22, 2026-09-05) to the `## Integration` section (following the
  doc's existing R20/R21 amendment convention). States plainly that only call
  sites 2 and 3 (before/around `process_show`) are phase 1; call site 1
  (pre-flight) is the phase-2 proactive gate and is not built — contradicting
  the surrounding numbered list's framing that all three ship together.
  Spells out the consequence: a `RateLimited` during interpret/search/winnow
  escapes `_execute` uncaught in phase 1, and traced that call site 2 ("before
  each show") also does not exist as a separate check in the current
  implementation (verified by reading the `while pending` loop in `cli.py`:
  the only RateLimited handling is inside `_process`, call site 3).

## Anything surprising

The mutation-1 `-k rate_limit` false-negative-risk finding above was the one
surprise — worth flagging loudly per the task's instructions even though it
is not a source defect. Everything else in the mutation pass behaved exactly
as the brief predicted, including mutation 5's exit-code discipline (genuine
1, not a 4 from a bad path).

## Concerns

None blocking. The one open item is advisory: the brief's mutation-1 example
command (`pytest packages/llama/tests -q -k rate_limit`) should probably be
corrected in any future re-run of this plan to target
`test_pace_loop.py`/`test_sessions.py` (or drop the `-k` filter) so it
actually exercises the cli.py catch-ordering constraint instead of
incidentally re-running the mutation-5 test.

## Commit

`a17b647` — `docs: record usage pacing and the measured rate-limit signature`
(3 files changed, 64 insertions, 1 deletion). Working tree clean after
commit; `1741 passed, 7 deselected` confirmed post-commit run already
included above (RESTORED run was taken before the docs edit; a further run
was taken after the docs edit and before commit, also 1741/7 — both recorded
in the tee'd log at
`/private/tmp/claude-501/-Users-shawn-projects-llama/f837f2ba-0078-43a2-bff3-c0a07ce36ae0/scratchpad/sdd/t8/t8.log`).

## Status

DONE.
