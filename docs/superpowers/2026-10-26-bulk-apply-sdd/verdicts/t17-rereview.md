# Task 17 fix round 1: re-review (t17-rereview)

Head 09742a80, fix base cce3309e. I read the diff file once and ran 4 mutants plus 2 probes in a scratch copy (`git archive 09742a80`) at /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-bulk-apply/6d6081a6-72bc-4b0b-afbd-ff5351b19e6a/scratchpad/t17rr/. Settings: PYTHONPATH shadowing, PYTHONDONTWRITEBYTECODE=1, `-p no:cacheprovider`. `bulk_apply.__file__` resolved inside the copy. Log: $D/t17-rereview/t17-rereview.log.

## Finding (Important 1): a block's meter delta included other kinds' spend. Verdict: ADDRESSED

- **Detection.** scripts/bulk_apply.py:1605-1613 `_spending_rows` returns every spending row with its list kind, sorted by `at`. `_block_rows` at :1616-1618 filters it by kind. `_foreign_inside` at :1621-1628 counts spending rows of another kind with `lo <= at <= hi`, where lo and hi are the block's first and last counted rows.
- **Refusal.** cmd_trial_report at :1671-1675 prints `<shape>-<kind>: not contiguous: N spending row(s) of another kind inside it; re-run as one block per kind` and `continue`s before `kept.append`. That is the wording the finding asked for.
- **Kept out of the ratio and the projection.** `sum5`/`sum7`, `ratio` and `cost[kind]` are all built from `kept` only (:1690-1712), so the refused block reaches none of them.
  - If every block is refused, the report prints `no usable block: no projection` (pinned by the new test).
  - If only one kind's block is refused, that kind gets no cost, so `per_show` returns None and its shows are added to `unmeasured`. The report then prints `note: no usable block for kind fresh; its shows are left out of the projection`. The kind is not silently costed at 0. Probe output: refused fresh plus kept needs-llm gave `projection dead: 0.6 points` from the needs-llm shows only, followed by that note.
- **Boundaries.** The window is inclusive (`<=` at :1628), so another kind's row whose `at` equals the block's first or last `at` counts as inside. That is the conservative direction. `at` is always `datetime.now(timezone.utc).isoformat()` (reapply.py:467), so comparing it as a string follows time order, including when the microseconds part is left out.
- **Same slug or batch under two kinds.**
  - `kinds` is a slug-to-kind dict and the last entry wins, so each progress row goes to exactly one kind. It can never count for both, or count as foreign to its own block.
  - The same batch passed as both kinds: if the two kinds are interleaved, both blocks are refused. If their windows are disjoint, each block measures its own window once, so there is no double count.
- **Tests.**
  - `test_interleaved_spend_of_another_kind_means_no_measurement` pins the refusal for a spending row inside the window.
  - The rewritten `test_non_spending_and_other_kind_rows_are_not_counted` pins two things: a spending row outside the window is neither counted nor treated as foreign, and a non-spending row inside the window does not refuse.
- **Mutants.** I predicted the red test before each run. Baseline: 7 passed.

| Mutant | Predicted | Result |
|---|---|---|
| M1: kind filter removed in `_block_rows` (:1618) | RED in test_non_spending only | CAUGHT, as predicted (`shows=21`) |
| M2: the `if foreign:` refusal disabled | RED in test_interleaved | CAUGHT, as predicted |
| M3: window made exclusive (`<`) | survives | SURVIVED, as predicted (see Minor 2) |
| M4: window check dropped (any foreign spending row refuses) | RED in test_non_spending | CAUGHT, as predicted |

## New breakage in the fix diff

Critical: none. Important: none.

### Minor 1: a retried row of another kind hides spend inside the window
`_spending_rows` reads `reapply.read_progress`, which keeps only each slug's last row. A row of another kind that failed inside the window still spent: `fail()` records `retryable=True` with `llm_calls` (cli.py:4320-4323). If that row is later re-run and its final row lands outside the window, the block is still measured, and the failed attempt's spend is inside the delta.

Probe: a fresh block of 20 shows plus a needs-llm slug with a failed row at 10:05:30 (`llm_calls` 3) and a success at 12:00. The block measured `shows=20 delta5=10`, with no "not contiguous" line.

This is the same defect class, but only through a narrow path: a failure, then a re-run, and no other interleaved spend. Fix: have `_spending_rows` read every parsed line of progress.jsonl, not the last row per slug. Recommended, not blocking.

### Minor 2: the inclusive boundary is not pinned
M3 survived. A test with a spending row of another kind whose `at` equals the block's first or last `at` would pin it.

## Deferred minors (out of scope)
- The same last-row collapse also affects a block's own kind. An earlier failed attempt of a slug in the block is in the meter delta, but `n` counts the slug once. This predates the fix.
- The `align_reproduced` tally (:1735-1741) still takes rows from a block that was refused as not contiguous. The values are per-row booleans, not meter readings, so nothing is contaminated, but the tally covers blocks the report otherwise discards.
- The `not contiguous` line is the only per-block line without the `block ` prefix. That is the wording the finding required, so I left it alone.

Verdict: all findings addressed
