# gb-fix handback: DONE
Commits: 12af7eb fix(gather): operator venue override takes no tie-break city (item 1); a9d9c78 items 2-5.
Item 1: gather.py `tie = venue_tie_break(candidate, sel) if overrides.venue is None else None`. Tests (test_stage_gather.py): operator_venue_override (RED on HEAD: city 'angels camp, california' != 'Angels Camp, California'; note the tie needs differing raw venue strings), city_only_override pin.
Item 2: cli.py `_interactive_resolve`: `except ShowChanged` (edit unit and [u]) prints error; if provenance gone keeps old handling (continue), else `return _interactive_resolve(...)` which re-captures view BEFORE re-resolving, re-prints show and prompt. Test: refuses once (picker changes overrides once), retry applies on re-printed prompt, PROMPT count 2, overrides merged.
Item 3: [m]/[i] `lines` now echoed after the unit succeeds. Tests: failed [m] asserts no "metadata override updated"; new success test; new failed [i] un-exclude test asserts no "was operator-excluded".
Item 4: `_resolve_exclude_tokens` suffix "; rebuild it with: llama redo <slug> --from gather"; test_fix assertion extended.
Item 5: brief.song_components docstring, show_unit limitation 3, CLAUDE.md triage sentence.
RED: ran the new/changed tests from a scratch `git archive HEAD` copy (PYTHONPATH shadowing, llama.__file__ verified in scratch): 5 failed, 311 passed (the 5 new/extended tests; the 2 plain pins passed as expected). GREEN: `./.venv/bin/python -m pytest -q` -> 4046 passed, 1 skipped, 8 deselected.
Concerns: none. Retry uses recursion (depth = number of consecutive changes). Existing changed-meanwhile test unchanged and passing.
