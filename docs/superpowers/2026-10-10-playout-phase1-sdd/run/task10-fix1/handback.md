Status: DONE. Commit 4067e90.
1. test_pipeline.py: test_the_second_mismatch_rule_is_per_slug_for_package_changes. Note: a re-plan re-reads every key, so a genuine two-package re-voice never reaches the second package-changed hit; the test injects a stale key for B into the first re-plan's rows (st.extend wrapper) after a frame-count mismatch on A. Mutant exclude=bool(mismatched) (line 241) killed in scratch copy: predicted that test red; only it failed (1 failed, 25 passed); shadowing proven by sentinel module import.
2. read_package_notes: non-UTF-8 briefing and non-dict briefing field both give (manifest, None); 2 tests.
3. build_notes falls back to meta on None too; test.
4. Tests: cut_frame absolute (row at frame 1000), 24h lower bound (exact-edge and just-inside), recent capped at 10 newest first.
Tests: 3.14 repo 2344 passed; 3.11 transmitter 195 passed.
