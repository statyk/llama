# t5-impl report
Status: DONE. Commit: see `git log -1` (fix(pacing): record a show boundary only when the show called an LLM).
Implemented pipeline.count_llm_calls (lazy Mapping view; ladder->list of wrappers, provider->wrapper, None->None; counter incremented before delegating), _execute uses it and records a boundary only if ran and reading_before is not None and llm_calls() > calls_before. _drive: FakeProvider defaultdict, llm= kwarg (default True). Cleanups: stale comment updated; failure-test asserts error startswith "download of " (stub already carried it).
Tests: new tests test_a_show_that_called_the_llm_records_a_boundary, test_a_download_only_resume_records_no_boundary, test_an_already_packaged_show_records_no_boundary, test_count_llm_calls_wraps_defaultdict_and_ladders.
RED: two no-boundary tests failed `assert [(UsageReading...)] == []` (one boundary recorded); unit test failed ImportError (count_llm_calls). GREEN: ./.venv/bin/pytest -q -> 3884 passed, 1 skipped, 8 deselected.
Files: packages/llama/src/llama/{pipeline,cli}.py, packages/llama/tests/test_pace_loop.py.
Concerns: the two no-boundary tests share a helper (_boundaries) and assert reads == llm-run reads - 1 for the skipped after-read; existing tests unedited.
