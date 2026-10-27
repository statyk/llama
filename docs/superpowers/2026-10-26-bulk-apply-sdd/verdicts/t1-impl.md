# t1-impl handback
Status: DONE. Commit 11a22de3 feat(overrules): overrule records and per-family flag keys.
Implemented: models.Overrule + Overrides.overrules (after encore_after); new llama/overrules.py (NOTE_PREFIX, FlagKey, flag_key, rule_matches, split_overruled, records_for, merge_rules); imports only models + structure.fold_curly_apostrophes.
Fixture: packages/llama/tests/fixtures/arm_flags.json, 2016 strings, sha256 3e29c306953e5bf4531f5c0f172b7e5e8f8de26342fad4fa34d4dad0d1cd64e4.
Tests: packages/llama/tests/test_overrules.py (8 tests incl. the two pins).
RED: pytest test_overrules.py -> ImportError: cannot import name 'Overrule' from 'llama.models'.
GREEN: 8 passed; full suite `./.venv/bin/python -m pytest -q` -> 6008 passed, 1 skipped, 8 deselected.
Notes: the real merged-tracks flag text is "merged track(s) N span a set break" (stages/gather.py:2003); the pattern handles it and a test pins it (first commit draft missed it; amended before handback). "research asserts wrong date: D" subject is D as written (stripped, not case-folded), per contract [D]. Titles key with no unresolved tracks gives empty subject (subset of anything).
Concerns: none.
