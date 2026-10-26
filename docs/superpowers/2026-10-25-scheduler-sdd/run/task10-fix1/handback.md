# task10-fix1 handback

Status: DONE. Re-ran at 9260dbd; evidence.md rewritten; stale results replaced; new variants added. Commits 29635e1 (script/test/17-slug list/clock-a-sym), then results+evidence commit (see git log). Tests: ./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q -> 805 passed, 1 skipped.

Script: repeat_gap_days_by_profile, distinct_aired_by_profile, fill_share_by_block, keyed scan cache (refuses mismatch), --exclude-slugs, weeks by LOCAL dates (starts now 1150/2100/1050). Smoke test asserts per-profile figures. doubled-dead.txt committed.

Floor check (clock a, full): scheduler 0/1150 = 0.0% vs naive overran 15 + not fillable 17 of 1100 = 2.9% (unchanged). PASS.

| run | Dead aired/pool | misses | fill share | Dead gap min / median (d) |
|---|---|---|---|---|
| a full | 384/413 | 0 | 7.1% | 1.0 / 13 |
| a excl-17 | 396/396 | 0 | 25.7% | 45 / 52.4 |
| a +-15 full | 396/413 | 0 | 3.8% | 1.0 / 18 |
| b full | 404/413 | 0 | 0% | 2.0 / 47 |
| b excl-17 | 395/396 | 0 | 0% | 4.3 / 46.5 |
| c delivered full | 403/413 | 0 | 0% | 1.0 / 10 |
| c delivered excl-17 | 384/396 | 0 | 23.3% | 45 / 50.5 |
| c eligible full | 113/113 | 0 | 13.4% | 1.0 / 32.5 |
| c eligible excl-17 | 112/112 | 0 | 21.1% | 1.0 / 30 |

(before fix, a: 39/413.) Excluding the 17 removes sub-week Dead repeats (the 12-hour dead-pm / dead-evening blocks can then only be filled structurally: dead-pm fill 40.9%, dead-evening 46.5% delivered); dead-am stays 0% fill.

Surprising: funk now concentrates on clock c delivered (91/221 aired, median gap 21 d, 230 repeats within a week; multi-artist pool so the exemption does not apply; not investigated). Zero misses everywhere. Caveats kept (not like-for-like, estimates, no interstitials).
