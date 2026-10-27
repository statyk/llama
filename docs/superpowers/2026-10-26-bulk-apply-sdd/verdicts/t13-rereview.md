### Finding Verdicts
- **IMPORTANT: the resume line dropped `--seven-day-ceiling`, `--with-gather-llm`, `--allow-structure-change` and `--stop-at-points`.** ADDRESSED. `packages/llama/src/llama/cli.py:4266-4271` now builds `resume` from every option that was given (`--seven-day-ceiling` formatted with `:g`, so 40.0 prints `40`). There is still one `resume` string, built before the loop, so all five sites that print it pick up the change: ceiling/pacing pause :4316, RateLimited :4341, 3 LLM failures :4347, 3 unreadable station copies :4357, trial stop :4420. Tests:
  - `test_the_resume_line_carries_the_ceiling_that_paused_the_run`: a 41% weekly meter with `--seven-day-ceiling 40 --stop-at-points 3` pauses and prints both flags.
  - `test_the_resume_line_carries_the_allow_flags`: the 3-unreadable stop prints `--allow-structure-change --with-gather-llm`.
- **SPEC: `needs-llm` was retryable even under `--with-gather-llm`.** ADDRESSED. `packages/llama/src/llama/reapply.py:453-459`: `(outcome == "needs-llm" and not with_gather_llm) or outcome == "skipped: structure changed"`. `outcome_retryable` has only one caller, `cli.py:4394`, and it passes the run's `with_gather_llm`. The other `record_progress` calls (:4284 failures, :4323 `skipped: missing`) hard-code `retryable=True`, which is correct. The default `with_gather_llm=False` keeps the old behaviour for any other caller. `test_retryability_per_outcome` now covers `needs-llm` both ways: `(needs-llm, False, gather_llm=True)` and `(needs-llm, True, gather_llm=False)`. The re-run passes the same flag, so the retry check matches.

### New Breakage in the Fix Diff
- **Minor:** `packages/llama/tests/test_reapply.py`, the parametrize of `test_retryability_per_outcome`. The `("cleared", False)` case was replaced rather than kept: the new first row (`needs-llm`, gather_llm) took its place. `cleared` → not retryable is no longer in this test, though the brief lists it among the committed outcomes. The behaviour itself is unchanged, since `cleared` is not in the retryable set. Fix: restore the row.

### Out-of-Scope Observations
- The resume line puts `{path}` in unquoted (this predates the fix), so a list path with spaces would print a command that doesn't paste. Every real path is under `~/.llama-harness`, so low risk.
- After a trial stop, the resume line now repeats `--stop-at-points N`, so pasting it runs a second trial block rather than the full wave. This is exactly what the finding asked for. Note it in the runbook so the operator drops the flag once the trial is accepted.

### Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage. One Minor: the dropped `cleared` row in the retryability test.
