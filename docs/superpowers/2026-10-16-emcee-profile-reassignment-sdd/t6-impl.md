# Task 6 report: emcee move
Status: DONE
Commit: see `git log -1` (feat(emcee): emcee move to record, clear and list one-off profile moves)
Implemented: `move` command (record/--delivered/--clear/--list), `_utc_now`, `_echo_moves`, `_COMMAND_ORDER` with "move", imports; brief's code verbatim. Tests: new test_move_cmd.py (verbatim from brief), boundary order updated.
RED: `pytest test_move_cmd.py test_cli_boundary.py -q` -> 36 failed, 12 passed (No such command 'move'; boundary order).
GREEN: same command -> 48 passed. Full suite `./.venv/bin/python -m pytest -q` -> 3110 passed, 1 skipped, 8 deselected.
Files: packages/emcee/src/emcee/cli.py, packages/emcee/tests/test_move_cmd.py, packages/emcee/tests/test_cli_boundary.py.
Notes: new code sits immediately before `_usage` (right after status_cmd). No brief/code disagreements found. No concerns.
