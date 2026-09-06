# Task 1 spec-compliance review — render the `per_model` meter (render-only)

**Verdict: Spec ✅**

Reviewer: spec-compliance (Opus). Diff reviewed: `cb5ff4e..8933fdb`
(`packages/llama/src/llama/cli.py` +5, `packages/llama/tests/test_pace_loop.py` +46;
2 files, 51 insertions, 0 deletions — independently confirmed with
`git diff --stat cb5ff4e..8933fdb`, so the review package is faithful).

## Requirement-by-requirement

| Requirement (brief / spec §2) | Verdict |
|---|---|
| `_pacing_line` gains one conditional part rendering `per_model` | ✅ diff matches the brief's Step 3 snippet verbatim, including the comment |
| Inserted after the `seven_day` block, before the `per_show_delta` block | ✅ exactly there (cli.py:317-321) |
| Entries sorted by key | ✅ `sorted(reading.per_model.items())` |
| Part omitted entirely when the dict is empty | ✅ loop over `{}` appends nothing; `per_model` is `field(default_factory=dict)` in `herder.usage.UsageReading` and `parse_usage_text` always builds a dict, so the value is never `None` |
| Rendered in **both** `llama pacing` and the run-start line (spec scope item 2) | ✅ both go through the single `_pacing_line` (cli.py:385 run-start, cli.py:1521 `llama pacing`) — verified in unchanged code, no second renderer exists |
| **`decide()` untouched — render-only boundary** | ✅ `pacing.py` is not in the diff at all; only `cli.py` and the test file changed |
| Test pinning `decide` verdicts `Proceed` on a 99% per-model meter | ✅ `test_decide_ignores_the_per_model_meter`, kept (not deleted) as a pin, and called out as such in the commit body per Step 2 |
| Three tests added verbatim from the brief | ✅ all three byte-identical to the brief, placed beside the other `_pacing_line` tests |
| No scope creep | ✅ nothing else touched; no constants, no `decide` rule chain, no `herder` change |
| Commit style `type(scope): subject`, lowercase, body explains *why* | ✅ `feat(pacing): render the per-model usage meter (render-only)`; body gives the operator-visibility rationale and the account-dependent-key reason for not binding |

## Test-result auditability

- The report names the mandated command explicitly:
  `cd /Users/shawn/projects/llama-wt-pacing-loose-ends && ./.venv/bin/python -m pytest -q`
  (not a bare `pytest`, not a `.venv/bin/<script>` console entry point). ✅
- It records the worktree-import check
  (`./.venv/bin/python -c "import llama; print(llama.__file__)"` →
  `/Users/shawn/projects/llama-wt-pacing-loose-ends/packages/llama/src/llama/__init__.py`). ✅
- **Independently reproduced by me** with that exact command:
  `1874 passed, 7 deselected, 26 warnings in 6.56s` — matches the predicted
  1871 + 3 exactly, and the import check resolves inside this worktree.
- Working tree is clean at `8933fdb` (`git status --porcelain` empty), so both
  mutants were genuinely restored.

## Mutation-check audit (the "name the red test first" rule)

Both mutants state a predicted red test name **before** application and an
observed red test name, and the two match:

1. Delete the `sorted()` wrapper → predicted `test_per_model_meters_render_in_a_stable_order`;
   observed the same, and it was the **only** failure (1 failed, 2 passed). ✅
2. Make `decide()` consult `per_model` (an extra `_pause(max(...))` in the rule
   chain) → predicted `test_decide_ignores_the_per_model_meter`; observed the
   same, sole failure, with the failing verdict reported concretely as
   `PauseUntil(scope='five_hour', reason='5h window at 99%, ...')` instead of
   `Proceed()`. ✅ This is the mutant that matters: it demonstrates the
   render-only boundary is held by a test, not by intent.

No "some failure appeared" scoring: each check names one test and reports it as
the sole failure with a count.

## Findings

None at Critical or Important severity.

- **Minor (observation, not a defect):** `test_the_line_renders_the_per_model_meter`
  asserts `startswith` rather than full-line equality, so it does not pin the
  tail of the line. This is exactly what the brief specified (the forecast part
  follows), and `test_the_missing_reset_guard_follows_the_binding_window` already
  pins full-line equality for the empty-`per_model` case — so the pair is
  adequate. Recorded only so a later reader does not mistake it for an oversight.
- **Minor (observation):** the per-model `Meter.resets_at` is parsed but not
  rendered. The spec's own example line (`Fable 42%`) omits it too, so this is
  compliant, not a gap.

## ⚠️ Cannot verify from diff

- **`llama pacing`'s rendering** is verified from unchanged code (the shared
  `_pacing_line` at cli.py:1521), not from the diff itself. It holds, but the
  diff alone does not show it.
- **The spec's "evidence bar" for binding `per_model` later** (a captured
  refusal under `~/.llama/llm-failures` naming the per-model window) is a
  future-work condition; nothing in this task can or should implement it. The
  cli.py comment points at it, which is all the brief asked for.
