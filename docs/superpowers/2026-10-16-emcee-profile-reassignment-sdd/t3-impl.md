# Task 3 handback: DONE
Implemented effective_profile, Effective, ProfileSource, profile_label, target_problem, move_target_problem and total manifest accessors in packages/emcee/src/emcee/station.py (verbatim from brief); tests in packages/emcee/tests/test_effective.py (verbatim).
RED: `./.venv/bin/python -m pytest packages/emcee/tests/test_effective.py -q` -> ImportError: cannot import name 'Effective' from 'emcee.station' (collection error; expected, symbols absent).
GREEN: same command -> 22 passed. Full suite `./.venv/bin/python -m pytest -q` -> 3023 passed, 1 skipped, 8 deselected.
No circular import (station imports moves/config/artists fine). Self-review: no concerns; existing station code unchanged.
