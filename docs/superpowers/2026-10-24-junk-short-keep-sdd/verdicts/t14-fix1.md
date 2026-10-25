# t14-fix1 handback
Status: DONE. Commit 94e6f98.
Changes (scripts/short_keep_probe.py): refuses (exit 2) when delivery_path is not an existing directory; _guard_out runs before load_config (so a bad --config says "no such config"); report tallies exclusions (unreplayable rows, no station copy, voiced, station manifest unreadable, library show.json unreadable, track list unchanged), changed shows with a metadata cache miss, and uncovered files with no readable size; sample section reports duration-check fallbacks among paired files (count and metadata bytes); the single plan_reuse call per sampled show is the timed one; header says library-side audio is ignored so the figure errs high; import order fixed.
Tests added (5): missing delivery root, missing config, every exclusion class, station-file-missing and no-metadata-length branches, sample selection (exact N and which, via Random(seed)) plus wall-time regex.
RED: with the old implementation the 5 new tests failed (5 failed, 41 passed); GREEN: scripts/test_short_keep_probe.py 46 passed.
Full: ./.venv/bin/python -m pytest -q -p no:cacheprovider -> 5074 passed, 1 skipped, 8 deselected.
Note: RED was recorded by reverting the source file temporarily after the fix was written (patch re-applied), not strictly test-first.
Not run against the real library or station.
