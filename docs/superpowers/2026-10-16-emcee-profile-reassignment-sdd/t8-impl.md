# Task 8 report
Status: DONE
Commit: see git log (feat(emcee): status shows effective profiles, recorded TTS and stale moves)
Implemented per brief verbatim: _profile_cell, _status_json_row new keys (delivered_profile, profile_source, tts, move_problem), status_cmd restructured with single exit + stale note on stderr, docstring.
RED: `./.venv/bin/python -m pytest packages/emcee/tests/test_status_profiles.py -q` -> 5 failed, 2 passed (KeyError: 'profile_source' etc.; expected, features absent).
GREEN: same file + test_status_cmd.py -> 31 passed. Full suite `./.venv/bin/python -m pytest -q` -> 3136 passed, 1 skipped, 8 deselected.
Files: packages/emcee/src/emcee/cli.py, packages/emcee/tests/test_status_profiles.py.
Brief/code disagreements: none. Concerns: none.
