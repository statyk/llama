# t4-impl handback
Status: DONE. Commit: c45936ff feat(cli): awaiting-fix shows in status, refused by deliver
Implemented: campaign.FROZEN_FILE, frozen_slugs, is_awaiting (unreadable -> True); CatalogEntry.awaiting_fix; select_shows/Selector/build_selector/selector_active/apply_selector awaiting_fix; status --awaiting-fix, [awaiting-fix] mark, JSON awaiting_fix; _AwaitingFix + _awaiting_fix_check (first check under show lock in _deliver_one, before voiced check); batch marks "  (refused: awaiting fix)" and skips them (re-checks under lock to print the same refusal text).
Dry-run list: no existing test expectation changed.
Tests: new 5 deliver, 1 status, 1 cli_select. RED: first test run (-x) failed test_deliver_refuses_awaiting_fix_by_name (exit 0 != 1) before implementation. GREEN: 3 files 101 passed; full suite 6045 passed, 1 skipped, 8 deselected.
Files: campaign.py, catalog.py, cli.py, cli_select.py, tests test_cli_select/test_deliver_cmd/test_status_cmd.
Concerns: RED was shown with -x (first failure only). Batch awaiting rows are not voiced-checked (skipped). Nothing wired for deliver --awaiting-fix selector (not requested).
