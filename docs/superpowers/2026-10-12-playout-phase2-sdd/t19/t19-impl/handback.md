# t19-impl handback
Part A (f94a4ef): publish.py guard_blocks_publishing: added `except ValueError: offair = True` before generic except (with comment). Test: added b'{not json' and b'' to the parametrized worker-parity test (test_publish.py); watched both fail red (None is True), then green. Failed-GET test (offair None) unchanged and green.
Gates: .venv pytest -q 2615 passed/1 skipped; .venv311 transmitter tests 459 passed/1 skipped; test-in-debian12.sh 460 passed.
Part B (see final reply for details): CLAUDE.md + spec notes; commit second. Gates: pytest 2615 passed; antenna npm test 14 files/236 tests.
