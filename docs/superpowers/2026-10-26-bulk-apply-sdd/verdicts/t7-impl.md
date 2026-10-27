# T7 handback
Status: DONE_WITH_CONCERNS (minor, see below)
Implemented: station.AWAITING, awaiting_fix_reason (ported from transmitter), PackageStatus.awaiting_fix, package_status returns awaiting-fix before readiness (identity kept); cli: _STATUS_STATES, JSON "awaiting_fix", summary "awaiting fix" column (before "voiced on"), run skip line, _process_one re-read + refusal. rewrite_manifest needed no change (already raw-dict); pinned by test_rewrite_manifest_preserves_awaiting_fix.
Dry-run list (existing tests changed): test_status_cmd.py::test_status_summary_rows_counts_labels_and_order -- spec clause "the summary gains an `awaiting fix` column (per profile and total)". No others.
Tests: full suite 6128 passed, 1 skipped, 8 deselected. emcee tests 1035 passed.
TDD: RED seen for test_run_skips_a_marked_package_and_spends_nothing (AssertionError: spend on a marked package, exit 1) with -x, so the other new tests were not individually shown RED before implementing; all green after.
Files: emcee station.py, cli.py; tests helpers.py, test_station/status_cmd/run_cmd/voice_cmd/package_io.
Concerns: RED evidence partial (-x stopped at first failure). Helper mark_awaiting_fix added to tests/helpers.py.
