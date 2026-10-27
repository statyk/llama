### Finding Verdicts

- **Critical, reapply.py:116-127/246: `_CallCounter` wraps a provider ladder as ONE provider (list.complete -> AttributeError; escalated rung never reached)**: ADDRESSED. `_CallCounter` is deleted. reapply.py:232-233 now uses `pipeline.count_llm_calls({"align": providers["align_structure"]})`, and `_CountedProviders.__getitem__` (pipeline.py:63-70) wraps each rung of a list or tuple with one shared counter, and wraps a single provider too. `counted["align"]` goes to `compute_legs` (reapply.py:238), and `align_calls()` drives `align_reproduced` (reapply.py:244). I checked this directly: a ladder of three distinct providers wrapped by `count_llm_calls`, with rungs 1 and 2 returning invalid JSON, reaches the escalated rung 3 through `run_json_task` and returns its result (calls=3, per-rung [1,1,1]). An all-HerderError ladder raises `HerderError`, not `AttributeError`, and the counter still counts (it increments before delegating). Required tests are present:
  - `test_align_ladder_of_providers_is_counted_and_reproduced_is_set` (test_reapply.py:2055)
  - `test_align_ladder_where_every_rung_raises_is_a_retryable_failure_not_a_crash` (test_reapply.py:2069). It asserts `HerderError` and a byte-identical show dir at the `reapply_show` level. The list runner's `except (TaskFailed, HerderError)` arm (cli.py:4253) turns that into a retryable row, already pinned end to end by the round-1 CLI test `test_with_gather_llm_align_failure_is_a_retryable_row_failure` (test_reapply.py:1947-1976, `retryable` asserted).
  - Mutation in a scratch copy (`align_calls()` -> `0`, PYTHONPATH shadow, `llama.__file__` verified in the copy): the ladder test, `test_align_reproduced_true_and_false` and `test_align_reproduced_is_set_when_an_extract_only_show_calls_align_in_the_recompute` all fail. So the counting is pinned, including on a ladder.

- **Round-1 fixes still hold**: YES.
  - `align_reproduced` is still set iff the stored alignment was llm or align was really called (reapply.py:243-245, now via the shared counter).
  - The round-1 HerderError/TaskFailed row-failure test (parametrized), the extract_setlist failure test (test_reapply.py:2040-2051) and the extract-only align-count test are unchanged by the fix diff.
  - Targeted run, live worktree (`-k "ladder or align_reproduced or align_failure or extract_setlist_failure or refusal_on_the_align"`): 9 passed.

### New Breakage in the Fix Diff

None.
- Minor, non-blocking: the ladder tests reuse one `FakeProvider` for all three rungs, so they do not show that a distinct escalated rung is reached. My direct check above covers it.
- Note, not this fix's defect: herder's `_with_transport_retry` retries a `HerderError` on rung 0 and raises without escalating. That is herder's existing behaviour and unchanged here.

### Out-of-Scope Observations

None.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.
