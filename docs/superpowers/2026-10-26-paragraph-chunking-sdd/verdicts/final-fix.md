Status: DONE. Commits: 278c1757 (fix + tests + comments), 3aa6d279 (test fix: set_intros={} so only the outro is sent).
Tests: packages/emcee 1021 passed, 1 deselected; full repo 5998 passed, 1 skipped, 8 deselected (the known wall-clock transmitter failure did not occur this run).
I1: test_script_paragraph_breaks_reach_the_packer (test_audio.py) + test_say_keeps_script_paragraph_breaks (test_say_cmd.py), ceiling 110, [X, Y]. Literals verified (X 52, Y 81 chars); the plain-packing result is [X + " Listen for the long jam after Truckin' tonight.", "It stretches out and turns quiet."], as stated.
M1: new test_plan_chunks_paragraph_break_forms_split_where_packing_would_not (ceiling 110; separators \n\n, \r\n\r\n, "\n \n", \n\n\n, "\r\n \r\n"; no \r). The original crlf test is kept.
M2: test_say_no_chunk... now uses a >250-char 8-sentence passage and asserts one call.
M3: room_tone.py now np.clip(np.rint(out), ...). ROOM_TONE_VERSION stays "v1". Pin test_fill_rounds_to_int16_so_a_crossfade_leaves_no_1ms_dropout (pool frames alternating +3/-3): truncation gives a 40-sample zero run, rounding 20 (< 24). My first fixture (RMS-2 floor) did not discriminate (run-length identical either way); I replaced it after measuring.
M5: loudness.py:3 "sentence chunks" -> "chunks"; provider.py:79 "concatenate sentences" -> "concatenate chunks".
Mutations (predictions logged first, restored, status clean):
M23 (speech_text return -> " ".join(text.split())): predicted and observed the two I1 tests fail (2 failed).
M8 (re.split r"\n\n"): predicted and observed the M1 test fails (1 failed).
M11 (enabled=True): predicted and observed the M2 test fails (1 failed).
M3 revert (no rint): predicted and observed the M3 pin fails (1 failed).
Note: the M23 line in speech_text.py is now `return _MULTISPACE.sub(" ", text).strip()` (not at ~67 as `text.split()`); the mutant replaced that return. Log: final-fix.log.
