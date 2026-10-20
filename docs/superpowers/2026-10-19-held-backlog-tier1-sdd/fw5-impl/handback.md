# fw5 handback: DONE_WITH_CONCERNS (concern = measurement exposure only)

Commit: see `git log -1` on held-backlog-tier1 ("fix(brief): comma-merged track titles contribute their parts to the known-song set").
Changed: packages/llama/src/llama/stages/brief.py (new `song_comma_components`; `briefing_guard` components union), tests appended to packages/llama/tests/test_stage_brief.py (4 tests: merged-tease shape, Mayonaise still flagged, paren commas never split + Phil Lesh flagged, single-part returns []). Existing tests untouched.
Suite: `./.venv/bin/python -m pytest -q` -> 3769 passed, 1 skipped, 8 deselected.

Call sites of `song_components(` in packages/ and scripts/ (non-test): brief.py known_song, briefing_guard (2 uses). scripts/replay_holds.py and llama/replay.py do not build the component set (no matches), so nothing else to change.

Mutation table
- M1 drop union -> test_comma_merged_title_parts_are_known_songs -> caught by it (only failure)
- M2 split every comma -> test_commas_inside_parentheses_never_split -> caught by it (only failure)
- M3 remove <2 check -> test_single_part_title_has_no_comma_components -> caught by it, and also by test_commas_inside_parentheses_never_split (its single-part paren title)
Shadowing proven per mutant (llama.__file__ under the scratch tree). Scratch removed.

Measurement (read-only, ~/.llama/shows/*/show.json)
- 694 tracks across 511 shows have a top-level comma that yields comma components; 457 distinct titles.
- Examples (15): It's All Over Now, Baby Blue | Lordy, Lordy | Into the Morning, Into the Night | Wild, Free, & Reckless | audience, donor rap, intros | Talk To Me Devil, Again | Lawyers, Guns and Money | Ray Parker, Part 2 | Mama, He Treats Your Daughter Mean | Honey, I've Been Thinking About You | Tell Me Mama, Tell Me Right | Man Smart, Women Smarter | So Close, So Far Away | O, Valencia | Eli, The Barrow Boy
- Most commas are inside single song titles, so the loosening exposure is real: 318 distinct (single-word component, title) pairs. A briefing naming that one word as a song now passes. Examples: 'Again' (Talk To Me Devil, Again), 'Baby' (Baby, We All Gotta Go Down), 'Adored', 'Arf', 'Atlanta', 'Albuquerque' (Albuquerque, New Mexico), 'Banter', 'Audience', 'Blah', numerals ('1','2','3','1975','1983' from 'Passaic, 1975', 'Sept 15, 1983', 'Pts 1, 2, &3'). Rule left unchanged per brief.

## Fix round 1 (review I1: adopt G2b gate)
Changed `song_comma_components`: returns [] unless there are >=2 parts AND every part has its own trailing parenthetical (`_BRIEF_PAREN.search(_BRIEF_TRAILING.sub("", p))`); docstring updated. New test `test_unannotated_comma_titles_never_split` (Talk To Me Devil, Again / Lawyers, Guns and Money (Warren Zevon) -> []; mention `Again` still flagged). Existing fw5 tests pass unchanged (the smashingpumpkins title is fully annotated).
Suite: 3781 passed, 1 skipped, 8 deselected.
Mutant M5 (drop the all(...) clause) -> predicted test_unannotated_comma_titles_never_split -> caught by it (only failure). Shadowing proven; scratch removed.
