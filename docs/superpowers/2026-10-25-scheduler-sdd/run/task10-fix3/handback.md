# task10-fix3 handback
DONE. Probe figures labelled (committed 300 within-7d vs probe 295/301; 350 vs 351 blocks); funk wording "primarily a library/clock limitation" + max_shows=3 side effect (Dead 406/413, 441 repeats within 7 d vs 403); naive cache test now covers pause_samples and library; scratch mutants dropping root/library/pause/extra from the key each fail it; "What was run" cache keying text fixed.
Tests: ./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q -> 807 passed, 1 skipped.
