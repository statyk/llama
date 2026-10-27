### Finding Verdicts
- **Progress rows record no spend marker, so `progress.jsonl` cannot reproduce the trial's `n`** — ADDRESSED.
  - `fail()` now takes `calls: int` (cli.py:4312-4323). It writes `"llm_calls": calls` into `extra` next to `meter`, and the trial gets `calls > 0`.
  - All four `fail(...)` call sites pass `calls=llm_calls() - calls_before`: cli.py:4385 (TaskFailed/HerderError), :4394 (StationUnreadable), :4405 (IAError/LlamaError/ValueError/OSError) and :4411 (last-resort Exception). The diff leaves no `spent=` keyword anywhere.
  - The success `record_progress` (cli.py:4435) gains `"llm_calls": llm_calls() - calls_before`. Its `trial(...)` still uses `llm_calls() > calls_before`, which is the same predicate.
  - Test `test_trial_count_excludes_shows_that_spent_nothing` (test_reapply.py ~2498):
    - Now has 7 rows: `n_clones=6`, plus a zero-spend `(False, IAError)` row at `slugs[4]`. One extra meter pair is scripted for that row.
    - Expected `n` stays 3 ("moved 6 points over 3 shows").
    - Asserts `llm_calls > 0` on the spending failed row and on a committed row, `== 0` on the zero-spend failed row and on a skip row, and exactly 3 rows with `llm_calls > 0`. That last check ties the progress file to `n`.
  - This also covers the prior review's Minor 1: a mutant that forces `fail()` to count as spent would now push `n` to 4 and fail the output assertion.
  - Ran it once: 1 passed.

### New Breakage in the Fix Diff
None.

### Out-of-Scope Observations
- The `skipped: missing` progress row (cli.py:4363) is written before `calls_before` is taken, and it carries neither `llm_calls` nor `meter`. It is zero-spend by construction, so a reader that treats a missing `llm_calls` key as 0 still reproduces `n`. Non-blocking.

### Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage.
