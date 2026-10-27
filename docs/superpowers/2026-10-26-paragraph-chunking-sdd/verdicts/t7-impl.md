# Task 7 handback
Status: DONE. Commit 675d16e5 feat(emcee): scriptwriter writes paragraphs; unescape literal \n in script text.
Implemented: prompt sentences verbatim in prompts/scriptwrite.md (after "no separate show intro or set-break segments.", before {{encore_note}}; wrapped so "never a raw line break" is on one line) and prompts/rephrase.md (bullet); scriptwrite._unescape_breaks; applied via model_copy to set_intros values and outro before script_guard in write_script (inside the retry loop), and to result.text before .strip() in rephrase_segment. 5 tests added to test_scriptwrite.py.
RED: 4 failed, 1 passed (round-trip passes pre-implementation, as expected: real \n\n already survives).
GREEN: ./.venv/bin/python -m pytest packages/emcee -q -> 1017 passed, 1 deselected.
Mutations (predictions logged before each run):
A drop unescape in write_script -> predicted test_write_script_unescapes_double_escaped_breaks; observed exactly that (1 failed).
A2 drop unescape in rephrase_segment -> predicted test_rephrase_segment_unescapes_literal_breaks; observed exactly that.
B unescape after script_guard -> predicted no failure; observed 1017 passed (observation: guard verdict doesn't depend on the break escapes; not a gap).
Each restored with git checkout; tree clean.
Concerns: none. One caveat: a prompt-wrap line break would break the "never a raw line break" assertion, so keep that phrase on one line.
