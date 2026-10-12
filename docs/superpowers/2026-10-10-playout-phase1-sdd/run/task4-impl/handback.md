# task4-impl report
Status: DONE. Implemented layout.py (PlanRow, Piece, validate_rows, pieces, segment_pieces, rows_overlapping, FrameStore) verbatim from the brief; appended fake_frame/write_fake_show/payloads to helpers.py (added `from transmitter import adts` at module top, no duplicate Path import); test_layout.py with 10 tests.
TDD: RED = test_layout.py collection error `ModuleNotFoundError: No module named 'transmitter.layout'`; GREEN = 10 passed.
Tests: py3.14 full repo 2271 passed, 7 deselected; py3.11 transmitter suite 122 passed.
Files: packages/transmitter/src/transmitter/layout.py, tests_transmitter/test_layout.py, tests_transmitter/helpers.py.
Self-review: no unused imports; 3.11-compatible. Concerns: none.
