Task 1 (Slice D) DONE. Commit: see git log (feat(match): fold curly apostrophes...).
Implemented fold_curly_apostrophes in structure.py (used first in fuzzy_norm_title), _song_tokens in vet_research.py, _song_norm in brief.py, CLAUDE.md clause.
RED: scratch copy of HEAD src + new tests: test_structure import error (fold_curly_apostrophes missing); 7 vet/brief tests failed. GREEN: 10 targeted passed; full suite 3974 passed, 1 skipped, 8 deselected (baseline 3964).
Snippets used verbatim; only added imports. No existing test changed. normalize_song/DEFAULT_ALIASES untouched.

## Fix round 1
Changes: right_show_gate test parametrized both ways; mid-file import moved into top import in test_structure.py; CLAUDE.md clause re-wrapped.
RED (scratch copy, only research_known line reverted to normalize_song(s).split()): tape1/research1 (straight tape, curly research) FAILED; tape0 passes as expected (tape fold intact).
GREEN: test_stage_vet.py + test_structure.py 318 passed; full suite 3975 passed, 1 skipped, 8 deselected.
