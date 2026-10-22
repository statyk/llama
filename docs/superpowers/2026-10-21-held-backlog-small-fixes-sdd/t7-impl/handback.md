# t7-impl handback
Status: DONE. Implemented triage edits as restoring units (cli.py _interactive_resolve, _metadata_editor now returns kwargs dict|None and writes nothing), 8 new tests in test_triage.py, CLAUDE.md sentence.
RED: `./.venv/bin/python -m pytest packages/llama/tests/test_triage.py -q` on unmodified cli.py: 6 failed, 42 passed (the two pin tests passed, as expected).
GREEN: same command + test_cli.py: 97 passed; full suite: 4040 passed, 1 skipped, 8 deselected.
Notes: all names/signatures matched the brief. Metadata "override updated" echo and the unexclude routing note are emitted inside the unit before the redo. [u] wrapped in same try; [u] uses the session view.

## Fix round 1
Added test_a_failed_untitled_resolution_restores_and_returns_to_the_prompt (RED in a scratch copy with the [u] try/except removed: exit_code 1, LlamaError escapes; scratch llama.__file__ verified inside scratch). Tightened the removed-show test ("no show matches" + slug) and the metadata test (exit 0, 2 prompts; input already answered correctly). capture_view now taken before the per-turn re-resolve. Command: ./.venv/bin/python -m pytest -q -> 4041 passed, 1 skipped, 8 deselected.
