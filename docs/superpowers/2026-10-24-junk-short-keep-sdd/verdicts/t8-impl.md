# Task 8 report: DONE
Commit 76c1830 on held-backlog-junk-filter (scripts/short_keep_probe.py, scripts/test_short_keep_probe.py).
Tests: the four new tests first failed (`pytest scripts/test_short_keep_probe.py -k "packet or score or sibvocab"`: 4 failed, invalid subcommand), then
`./.venv/bin/python -m pytest -q` -> 4984 passed, 1 skipped, 8 deselected.
Design: packets/score/sibvocab subcommands each take --config and use _guard_out (packets also guards --cand/--ref-dir; score guards packet and answers).
packets: root from config; identifier from <root>/shows/<slug>/show.json; neighbours (+-2, play order by track tag else name, port of p4.play_order) and description[:3000] via CacheOnlyIA on <root>/cache. Kept = filename in cand with short_kept; a file in the cand show but not short_kept is skipped (not a "dropped"). Stratum priority for kept: placeholder-tagged (tagged false and rp_tagged true), then untagged-interior (r1_dec keep-untagged), then kind. rule_would is derived from candidate membership (keep/drop), not r1_dec. Rows shuffled with random.Random(seed) and numbered 1..N; a short stratum takes what exists and the count is printed.
score: right/wrong from rule_right (falls back to decision==rule_would); missing answers fail the bar; exit 1 on FAIL. first10.md includes the grader's answer next to the row.
sibvocab: header comment line "# n of m ..." then id<TAB>name<TAB>tag lines.
Concerns: dropped_today in neighbours is true only for files in r1_files (short drops), other drops unknown. Real-data run is Task 9; not exercised on ~/.llama-harness data.
