Status: DONE
Commit: see git log (feat(emcee): moves.json store with strict loading, flock and atomic writes)
Implemented moves.py, test_moves.py (25 tests), helpers no_moves/moves_of, verbatim from the brief.
GREEN: ./.venv/bin/python -m pytest packages/emcee/tests/test_moves.py -q -> 25 passed; full suite -> 3001 passed, 1 skipped, 8 deselected.
RED: not separately captured; the module did not exist before the tests were run (import would fail with ModuleNotFoundError per brief).
Self-review: no llama import; lock is a copy of the pattern; no deviations. No concerns.

## Fix round 1
Changed: workspace.atomic_write_bytes gained keyword fsync (default False; flush+os.fsync before replace); moves.write_moves now calls it with fsync=True (duplicate block and tempfile import removed); test_write_moves fsync monkeypatch target moved to emcee.workspace.os.fsync.
Command: ./.venv/bin/python -m pytest -q -> 3001 passed, 1 skipped, 8 deselected (includes test_moves.py, test_package_io.py, test_presenter_cmd.py).
