# t16bc-impl handback
Status: DONE
Commits: 04c4896 (16b), e59a6d8 fix(replay): 4b closest-calls rows read vetting.json's nested asserted_dates (Checkpoint E) (16c)
16b: vet_research.py: factored normalize_date's body into _parse_date(text, day_zero); normalize_date unchanged output; day_unknown_date shares it. grounding_flags builds day_unknown (first surface text per value); _date_flags takes it (default None) and emits wrong-date flags after full-date, before yearless, only when not placeholder; in both date_flags_raw and windowed flags. 9 tests appended to packages/llama/tests/test_stage_vet.py.
16c: scripts/replay_holds.py reads v["vetting"]["asserted_dates"] (guards dict/dict/list); test in scripts/test_replay_holds.py failed on unfixed code first.
Tests: full suite 3676 passed after 16b, 3677 passed after 16c (1 skipped, 8 deselected).
Mutation (16b), copies under a private mktemp dir, shadowing proven per mutant:
a day-unknown flags on placeholder -> test_16b_placeholder_show_ignores_day00 -> caught by it
b skip date_flags_raw -> test_16b_day00_makes_the_right_show_gate_decline -> caught by it
c accept month 0 -> test_day_unknown_date[1991-00-00-None] -> caught by it (+ [0/0/91-None])
d same year-month not flagged -> test_16b_day00_next_to_the_show_date_is_not_windowed_away -> caught by it (+ billycorgan_shape, right_show_gate_decline)
Deviations: none. Note "0/5/08" from the brief reads as day-first 2008-05-00 (a valid day-unknown), so month-0 slash case pinned with "0/0/91" instead. Scratch dir deleted.
