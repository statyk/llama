# task10-fix2 handback
Status: DONE. No library access, no re-runs, no background jobs.
1. Bends relabelled "offered by the bounded search" + undercount note (dead-family 35/35, c funk 30/337, _blocksearch first-show selection; Task 8 follow-up; reviewer probe figures).
2. Funk root cause added (14:00-20:00, 8 shows >=183 min, 307/351 blocks, max_shows=3 probe: 221/221, min 45 d, median 60 d; marked reviewer probe).
3. +-15 bluegrass concentration added, with the operator design question.
4. Dead-blocks table now names dead-am/dead-pm (a) and dead-morning/dead-evening (b, c) for every full and excl-17 row, all from committed JSON; "only own shows" sentence limited to single-show landings.
5. naive_filler.load_shows checks (root, library, pause_samples, extra) and refuses mismatch; measure_scheduler cache key likewise; two tests added (tests first, red then green). Existing scratch pickles lack the new keys and would be refused; no re-run done.
Tests: ./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q
