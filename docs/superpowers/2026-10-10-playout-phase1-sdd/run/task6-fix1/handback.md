# task6-fix1: handback

Status: DONE
Commit: 48565c9 fix(transmitter): corrupt plan is a PlanError; 0-frame show is a skip; pin recovery-cut boundary (on top of 6a65436)

## Changes
1. read_plan: each non-blank line goes through `_parse_row`. Any ValueError or TypeError raises
   `PlanError(f"{path}: line {i}: {exc}") from exc`. That covers invalid JSON, a non-object line, a
   missing field, and a wrong-typed field. The type checks: seq, start_frame and frames must be int
   (bool rejected); slug, dir and key must be str; run_start must be bool; cut_frame must be int or null.
   A corrupt plan still fails loudly and is never read as an empty plan. Line numbers are 1-based and
   count blank lines.
2. cut_for_recovery: no code change. A new test, test_cut_for_recovery_drops_a_row_starting_exactly_at_the_boundary,
   uses gap 323 so that row 1 starts at 13*441. It checks that kept == rows[:1] and that the result passes validate_rows.
3. extend: if frames_of returns <= 0, the code raises `PlanError(f"{slug} measures {frames} frames")` inside
   the per-show try, so the show goes through on_skip.

## TDD evidence
- RED (`./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_planner.py -q`): 5 failed, 14 passed.
  - The 0-frame test failed with `LayoutError: plan row 2 (bravo) has no frames`.
  - The 4 corrupt-plan cases failed with raw JSONDecodeError and TypeErrors (`argument after ** must be a mapping, not list`;
    `missing 4 required positional arguments`; `'<=' not supported between instances of 'str' and 'int'`).
  - The boundary test passed on the original code, as expected, because it pins existing behaviour.
- GREEN: 146 passed on both venvs.
- Mutant m3 (`>=` changed to `>`):
  - Run in a scratch cp of src and tests_transmitter, from the scratch cwd, with `python -m pytest`, `PYTHONPATH` shadowing,
    `PYTHONDONTWRITEBYTECODE=1`, no cacheprovider, and fresh __pycache__.
  - `transmitter.__file__` resolved inside the scratch copy.
  - I predicted the new boundary test would fail. Result: that test failed (KILLED), and the other 33 planner and layout tests passed.

## Tests
- py3.14: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`: 146 passed.
- py3.11: `./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q -p no:cacheprovider`: 146 passed.
- Full repo suite (`./.venv/bin/python -m pytest -q`): 2295 passed, 7 deselected.

## Files
- packages/transmitter/src/transmitter/planner.py
- packages/transmitter/tests_transmitter/test_planner.py (adds `from transmitter.layout import validate_rows`, which is used)

## Concerns
None. Reviewer minors 4-7 (retry memo, the "all skipped" message, a skip-on-first-row test, AdtsError) were not
ruled, so I did not address them.
