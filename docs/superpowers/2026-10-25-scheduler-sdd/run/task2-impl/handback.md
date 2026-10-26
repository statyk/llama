Task 2 DONE. Commit: see git log (transmitter: plan lock around plan and render).
RED: test_locks.py collection failed: ImportError cannot import name 'PlanLocked'.
GREEN: ./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q -> 592 passed, 1 skipped.
Files: locks.py (new), errors.py (PlanLocked), workspace.py (plan_lock_path), service.py (plan/render steps wrapped; _step treats PlanLocked like PublishLocked), cli.py (plan, render hold lock), tests in test_locks/test_cli/test_service.
Note: CliRunner tests assert on result.exception (main_cli prints the error, not CliRunner). Service test spies publish_all to prove publish still ran.
Concerns: none.
