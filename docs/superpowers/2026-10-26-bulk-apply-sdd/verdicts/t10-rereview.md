# Task 10 fix round 1 re-review (t10-rereview), 120b0405..6e91a0c7

### Finding Verdicts
- **1. `align_reproduced` decided from the first pass's verdicts, not from real align calls**: ADDRESSED. reapply.py:244-257 now wraps the align provider in `_CallCounter` and sets `align_reproduced` iff `stored alignment llm` was in the first verdicts or `align_counter.calls > 0`. New test `test_align_reproduced_is_set_when_an_extract_only_show_calls_align_in_the_recompute` (test_reapply.py:2023) asserts first pass `needs_llm == ["extract_setlist"]`, one align call, `align_reproduced is not None`. Check run: a mutant in a scratch copy that restores the old first-pass condition fails exactly that test (1 failed, 3 passed), so the test pins the fix.
- **2. Row-failure test should use HerderError, plus an extract_setlist failure test**: ADDRESSED. test_reapply.py:1946-1960 is parametrized `herder`/`task`, and the `herder` case queues `HerderError("boom")` on the align provider. New `test_with_gather_llm_extract_setlist_failure_writes_nothing` (test_reapply.py:2041) makes the extract_setlist provider raise HerderError in the recompute, then asserts that it raises, that the provider was called, and that the snapshot is unchanged.

### New Breakage in the Fix Diff
- **Critical: reapply.py:116-127, 246.** `_CallCounter(providers["align_structure"])` assumes a single provider. Production `make_providers` (pipeline.py:30-32) returns a ladder per task: `herder.resolve.provider_ladder` returns `list[LLMProvider]`. `run_json_task` sees the counter as a non-list, makes it `[counter]` and calls `counter.complete`. That reaches `list.complete` and raises `AttributeError: 'list' object has no attribute 'complete'`. So on the real CLI, every `--with-gather-llm` recompute that reaches `align_structure` crashes. It also bypasses the escalation rung. The AttributeError is not caught as a TaskFailed/HerderError row failure, so it is not a retryable counted row.
  Check run, in scratch copies with a PYTHONPATH shadow: probe test `test_zz_ladder_align_provider` (the align provider given as `[align]*3`). At HEAD 6e91a0c7 it FAILS with the AttributeError above. At pre-fix 120b0405 it PASSES. This is a regression from the fix round.
  Every test misses it because every test (including the CLI one, which monkeypatches `make_providers` to `_gl_providers`) passes a bare FakeProvider.
  Fix direction: wrap each rung, like `pipeline._CountedProviders` (pipeline.py:55-70: ladder -> list of wrappers sharing one counter), or reuse `pipeline._CountedProvider` with a shared counter. Add a test that passes a ladder for `align_structure`.

### Out-of-Scope Observations
None.

### Verdict
**Fix round:** Findings 1 and 2 are addressed, but the fix introduced a Critical regression: `_CallCounter` breaks ladder providers, so `reapply --with-gather-llm` crashes in production whenever align is called. Another fix round is needed.
