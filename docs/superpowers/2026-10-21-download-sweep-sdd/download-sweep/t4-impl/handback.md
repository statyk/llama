# t4-impl report
Status: DONE. Implemented KIND_* constants, classify_failure, failure_record, failure_kind in packages/llama/src/llama/sessions.py; cli._execute uses failure_record at both failures.append sites (imported in cli.py).
Tests added: test_classify_failure_follows_the_order, test_failure_record_stamps_kind_and_utc_at, test_legacy_record_kind (test_sessions.py); test_execute_records_kind_for_a_failed_show (test_pace_loop.py, via unchanged _drive).
RED: ./.venv/bin/pytest -q packages/llama/tests/test_sessions.py packages/llama/tests/test_pace_loop.py -> collection ImportError: cannot import name 'KIND_ARCHIVE' from llama.sessions.
GREEN: same command -> 145 passed; full ./.venv/bin/pytest -q -> 3880 passed, 1 skipped, 8 deselected.
No existing whole-dict assertions needed changing (they feed hand-built dicts to mark_incomplete, or compare show/error only).
Note: sessions.py now imports herder and llama.ia_client (no cycle observed; suite green).
