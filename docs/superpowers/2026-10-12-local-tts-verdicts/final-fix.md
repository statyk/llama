final-fix: DONE. Commits a6763a0 (F1+F2+F4 code), 3e84438 (F3 docs).
F1: wav_to_mp3 raises SpeechError for width != 2 (names the bit width) and for wave.Error/EOFError (malformed). Tests in tests/test_mlx_audio.py: 8-bit/24-bit/garbage RED before, GREEN after; 16-bit encodes.
F2: _draft_transcript uses Path(clip).expanduser(). Test in tests/test_presenter_edit.py with tmp HOME; RED (cannot read ~/clip.wav) then GREEN.
F3: README rollback item 9 got clauses (a)(b)(c).
F4: test_calibration_measured.py pins verify thresholds and full Qwen calibration (asdict) exactly; all values matched the code as committed. Mutants in scratch copy (python -m pytest, PYTHONPATH shadow verified): MISS_FRACTION 0.35 -> red; EXTRA_FRACTION 0.6 -> red; max_s_per_char 0.12 alone -> collection error (ModelCalibration requires cap==max; not a test red); max+cap 0.12 -> red.
Suite: ./.venv/bin/pytest -q -> 2907 passed, 1 skipped, 8 deselected.
