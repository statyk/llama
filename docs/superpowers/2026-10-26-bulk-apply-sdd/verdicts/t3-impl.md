# t3-impl handback
Status: DONE. Commit: see `git log -1` (feat(campaign): per-show campaign record, processed on a committed re-gather).
Implemented: packages/llama/src/llama/campaign.py (new); workspace.py (campaign, reuse_anchor); replay.py (VISIBLE_FIELDS, visible_changes, row_visible_changes, row_label_only); cli.py `_redo_show_locked` (read_record before any spend; mark_processed after process_show when from_stage <= last mark's start_stage, held=pkg is None); stages/package.py (campaign.after_package as the last step after the manifest write).
Dry-run list: none; no existing test expectation changed.
TDD: RED = tests copied into a `git archive HEAD` scratch copy: `ImportError: cannot import name 'campaign' from 'llama'`. GREEN: tests/test_campaign.py + test_replay.py pass (10 new campaign tests, 1 new replay test); full suite `./.venv/bin/python -m pytest -q`: 6038 passed, 1 skipped, 8 deselected.
Notes: awaiting_fix compares parsed datetimes (not strings); unparseable `at` counts as awaiting. CampaignUnreadable message is single-line. Unreadable record also raises from after_package (inside build_package, unit restores). Timestamps written with microseconds.
