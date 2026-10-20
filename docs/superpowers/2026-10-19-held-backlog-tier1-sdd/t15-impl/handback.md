# Task 15 handback: DONE
Commits:
ab6f708 test(vet): pin month-first-wins when both readings are valid (mutant d)
248a193 feat(vet): 4c date ranges (day-first fallback), 4b adjacent-day context, 4d prompt wording
Changes: vet_research.py (_valid_ymd, range-checked normalize_date with day-first fallback incl. yearless; ADJACENT_DAY_WINDOW=1 + _within_window; grounding_flags: mismatched_raw for adoption, own_full-windowed mismatched for flags, raw_date_flags local kept for Task 16; run_vet_research writes show, notes, then vetting.json LAST, with order-pinning test via monkeypatched write_artifact); vet_research.md item 1 reworded; tests per brief plus imports at top, import pytest added.
Suite: 3637 passed, 1 skipped, 8 deselected (base 3621).
Deviation: existing test_prompts::test_vet_research_prompt_excludes_context_mentions asserted "AT THIS SHOW"; item-1 rewording removes it, so updated to "at this show, on this date".
Mutation (shadowing proven per mutant):
a window=2 -> test_4b_two_days_off_still_flags -> caught by that test
b window without own_full -> test_4b_without_the_own_date_an_adjacent_date_still_flags -> caught by that test
c adoption reads windowed mismatched -> (no test possible) -> SURVIVED, EQUIVALENT: adoption requires len(full)==1; own_full requires show.date in full; together mismatched_raw is empty, so windowing cannot change it. (First attempt had a NameError typo, discarded.)
d month-first valid swapped to day-first -> test_4c_normalize_date_ranges -> originally only caught by pre-existing test_normalize_date_common_forms; added row 10/11/08 -> 2008-10-11, now also caught by test_4c_normalize_date_ranges[10/11/08-2008-10-11]
Concerns: none. Mutation scratch dir under $TMPDIR/mut-t15-impl-ULkw11 left in place (rm -rf blocked by safety check); safe to delete.

## Fix round 1
Commit: 1d22a8b fix(vet): date_flags_raw built by the same _date_flags helper as the flags
Changes: extracted _date_flags(mismatched, yearless, show, placeholder, adopted); grounding_flags calls it once with mismatched_raw (local date_flags_raw, renamed, unused until Task 16) and once with windowed mismatched for flags. Raw now includes yearless, placeholder text, empty on adoption. vet_research.md item 1 re-wrapped (line breaks only).
Test: test_4b_raw_date_flags_keep_what_the_window_hides_and_yearless_mismatches (helper direct + end to end).
Commands: pytest test_stage_vet.py test_prompts.py -q -> 62 passed; pytest -q -> 3638 passed, 1 skipped, 8 deselected.
