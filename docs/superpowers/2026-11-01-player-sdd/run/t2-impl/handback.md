Status: DONE. Implemented site.parse_briefing, CAUTIONS_PREFIX, ARCHIVE_PREFIX, archive_link; build_notes gains "sections" (briefing unchanged). Extended test_notes_from_a_package; added all brief tests.
RED: test_site.py -> 15 failed, 18 passed (AttributeError / KeyError on new names).
GREEN: ./.venv/bin/pytest packages/transmitter/tests_transmitter -q -> 901 passed, 1 skipped.
Files: packages/transmitter/src/transmitter/site.py, packages/transmitter/tests_transmitter/test_site.py.
Self-review: render_show_page untouched; Python 3.11-safe. Minor: a blank line between two bullet lists does not split the ul (merged into one); not specified by brief.
