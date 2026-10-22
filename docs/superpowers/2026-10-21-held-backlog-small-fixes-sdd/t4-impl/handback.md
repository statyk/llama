Task 4 DONE. Commit 1fe9109 feat(show_unit): snapshot-and-restore unit under the show lock (slice C core).
Implemented llama/show_unit.py (names per brief; docstring has the 4 limitations) and helpers.tree_bytes; 12 tests in test_show_unit.py.
RED: ./.venv/bin/python -m pytest packages/llama/tests/test_show_unit.py -q -> ModuleNotFoundError: llama.show_unit (collection error), expected.
GREEN: same command -> 12 passed. Full suite: 4000 passed, 1 skipped, 8 deselected.
Brief's fixture adapted: _show writes provenance.json via write_artifact with a dummy dict. No other deviations.
Concerns: none.

## Fix round 1 (c9d770c)
Added tests: lock inode unchanged; ghost leftover not resurrected; unremovable leftover refuses before body (new _discard_leftover raising LlamaError); take_snapshot failure (KeyboardInterrupt, OSError) discards+re-raises, body not run; audio check moved inside body. restore (a)/(c) use unlink(missing_ok=True).
Mutants (scratch copy, llama.__file__ verified in scratch): .lock->True: lock test red; initial discard removed: ghost + refuse tests red; handler Exception-only: KeyboardInterrupt case red; handler removed: both red; refuse check disabled: refuse test red. Base 17 passed.
Full suite: 4005 passed, 1 skipped, 8 deselected.
