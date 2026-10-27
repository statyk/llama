# t1-impl handback: DONE
Commit 717bef24 fix(emcee): sentence splitter keeps dotted abbreviations (U.S., D.C.) whole
Files: packages/emcee/src/emcee/audio.py (_DOTTED_ABBREV_RE + pre-pass in _split_sentences before the merge loop), packages/emcee/tests/test_audio.py (3 tests, 8 cases).
RED: `./.venv/bin/python -m pytest packages/emcee/tests/test_audio.py -q -k "dotted or outro"` -> 8 failed (expected: no rule yet).
GREEN: `./.venv/bin/python -m pytest packages/emcee -q` -> 951 passed, 1 deselected (baseline 943 + 8).
Mutation A (pre-pass moved after merge loop): predicted outro test fails first. Observed: 8 failed incl. the outro test and all dotted cases. Restored, tree clean.
Mutation B ({2,} -> {3,}): predicted the parametrized dotted test. Observed: 8 failed incl. all 6 parametrized cases (plus the harmless-D.C. and outro tests). Restored, tree clean.
Self-review: no concerns. Note: a trailing part ending in a dotted abbreviation with nothing after it is kept as-is.
