# Task 1 handback: the filter rule (t1-impl)

**Status: DONE_WITH_CONCERNS** (the concerns are observations for review, not blockers)
**Commit:** `fdd7f1d` feat(junk): keep short files that belong to the show (piece 4 rule)
**Tests:** `./.venv/bin/python -m pytest -q` -> `4844 passed, 1 skipped, 8 deselected` (baseline 4788; +54 in the new file, +2 for the new `furthur-19` cascade case)

## What I implemented (`packages/llama/src/llama/junk.py`)
- `SPAM_REASON = "spam-shaped name or tag"`. Spec 2.3's nine regexes and `parts` / `short_tag_is_junk` / `short_is_spam` were extracted from the spec's code block by script, not retyped. I checked them against that block by `exec`: pattern and flags for each regex; bytecode, names, consts and nested code for each function. All identical. The only edits are the type annotations from the brief's interface and blank lines between the functions.
- `basename_without_extension` (exactly the global-constraints form), `short_filename_is_junk`, and `short_verdict(..., *, interior)` deciding spam -> tagged (`junk`/`keep`) -> untagged (`filename`, else `keep`/`edge`).
- `_keep_and_exclude(files, audio, *, short_keep, orig_tracks)` now returns `(kept, excluded, names the rule kept)`.
  - The reasons loop and the floor are unchanged. The loop now also records each excluded entry's source dict.
  - With `short_keep`, `_apply_short_rule` re-decides entries whose reasons are exactly `["implausibly short"]`:
    - The tag is the own `title`, else the original's `title`. The original is looked up among `files` for a derivative.
    - spam: reasons become `[SPAM_REASON]`. tagged non-junk: kept. untagged non-filename-junk: candidate.
    - Play order is taken over kept, tagged-kept and untagged candidates: `_track_number` order when every number is non-None and unique, else name order.
    - An untagged candidate is kept when a kept or tagged-kept file lies on each side of it. The final call is `short_verdict(..., interior=...)`.
    - Kept files rejoin `kept`, which is sorted by name as today.
- `filter_files(..., short_keep=True)`:
  - `orig_tracks` is built before the format loop and passed in.
  - The format loop, dedupe, readmit and the ordering block are otherwise untouched.
  - `ordering["short_kept"]` is the sorted list of rule-kept names that are in the final `kept`. It is in both ordering dicts and is `[]` with `short_keep=False`.
- Global-constraint names are untouched; the removed lines in the diff are only signatures, tuples and ordering dicts. `grep -rn short_keep packages scripts`: no non-test caller passes `short_keep=False`.

## Files changed
- M `packages/llama/src/llama/junk.py`
- A `packages/llama/tests/test_short_keep_rule.py`
- A `packages/llama/tests/fixtures/short_keep_corpus.jsonl` (**3547 rows, sha256 `4ed4fb943dded69aff42fbd166261f7ad16811d2f0d817a22b569c0a0c659e10`**; fields slug, name, tag, pos, r1_dec, in source order; read-only from `~/.llama-harness/piece45/spec/r1/r1_files.jsonl`)
- A `packages/llama/tests/fixtures/junk_v2_17_0.py`: e37f670's junk.py verbatim under a 5-line header naming the commit. Its only import, `from llama.util import length_seconds`, loads as-is, so no import lines were changed. A diff of the body against `git show e37f670:...` is empty.
- M `packages/llama/tests/test_junk.py`, `test_stage_gather.py`, `test_title_cascade.py`, `scripts/test_title_hygiene_probe.py` (the dry-run updates below)

## TDD evidence
- RED: `./.venv/bin/python -m pytest packages/llama/tests/test_short_keep_rule.py -q` -> `ImportError: cannot import name 'SPAM_REASON' from 'llama.junk'` (1 error during collection).
- GREEN: same command -> `54 passed in 0.29s`. Full suite -> `4844 passed, 1 skipped, 8 deselected, 26 warnings in 76.00s`.
- Corpus totals asserted both ways and passing:
  - by `r1_dec`: 2822 keep/keep-untagged, 685 drop-junk/drop-nonperf, 3 drop-filename, 37 drop-edge;
  - by verdict: 2822 keep, 685 junk, 5 filename, 35 edge.
- Mutation check, in a scratch copy shadowed by PYTHONPATH (`llama.junk.__file__` checked to be inside the copy), against `test_short_keep_rule.py` and `test_junk.py`. All six caught:
  - untagged candidates counted as neighbours (Task 21 mutant (e)): `test_untagged_interior_kept_edge_dropped`;
  - no original-title fallback: `test_tag_falls_back_to_the_original_title`;
  - spam keeps the old reason: three tripwire tests;
  - `short_keep=False` ignored: `test_short_keep_false_reproduces_today` and two others;
  - interior always in filename order: `test_interior_uses_track_tag_order_only_when_complete_and_unique`;
  - `short_kept` not intersected with the final kept: `test_short_kept_names_survive_dedupe_only`.

## Step 5 dry run (full suite run with no existing test edited; written to the log before any edit)
21 failed / 4821 passed. Every failure ties to a spec clause and none is unexplained. What the rule keeps in the fixtures matches the brief's expected list exactly:
- dso `d3t08 Announcements`;
- furthur `10.tuningup.mp3` (`tmp`);
- gd70 spans and gd74 miller `Introduction` (mp3 and flac);
- windsor `D3_T02 Weather Report Suite Part I >`;
- rre `08peterRowanBanter` and `24toddBanter` (mp3 and flac).

gd73 is unchanged and none of its tests moved.

| Failing test | Clause | Update |
|---|---|---|
| test_junk: `test_unique_track_tags_reorder`, `test_track_tags_agreeing_with_filenames_not_flagged`, `test_duplicate_track_tags_fall_back_to_filename_order`, `test_derivative_inherits_original_track_number` | 2.5 (`ordering["short_kept"]` always present) | added `"short_kept": []` |
| gather `test_gather_recovers_structure_from_sibling` | 1, 2.3 (windsor keeps WRS Part I at track 17) | 28 tracks, set 2 is 16 tracks, breaks [11, 27], coverage 27/28. `Part I` does not match the canonical `Part 1`; Task 2's coverage clause (spec 3) should bring it back to 1.0 |
| gather `test_align_result_matched_reaches_the_track` | same | coverage 27/28; the only unmatched track is index 17 (`[t.index for t if matched is not True] == [17]`) |
| gather `test_gather_setlistfm_wins_with_lma_segues` | same | breaks [11, 27] |
| gather `test_2b_demotes_a_whole_tmp_tape_and_notes_each_track` | 2.2 (`tmp` is tagged, so 10.tuningup.mp3 is kept) | The 20 files match the description's 20 entries, so D fills every track 2b demoted: 20 demotion notes, all `desc-position`, no unresolved flag |
| gather `test_2b_demotes_a_recovered_sibling_format_placeholder_and_files_no_sibling_note`, `test_2b_item_title_reaches_the_recording_level_class` | 2.2 | `{"desc-position"}`. This still shows 2b fired: without the demotion the sources would be `sibling-format` / `tags` |
| gather `test_2b_files_the_format_sibling_it_does_not_recover_from` | 2.2 + 2.3 (mp3 `tmp` kept, FLAC `Tuning Up` junk) | The stem bijection fails (20 vs 19), so the captured tape files no note. The test now runs on the 19-file shape (new helper `_furthur_without_short_tuning`) and also asserts the note is absent on the captured tape |
| gather `test_2c_strips_railroad_earths_glued_numbers_and_notes_each`, `test_2d_strips_joined_numbers_and_notes_each` | 1, 2.3 (stage banter is kept) | 23 -> 25 notes |
| gather `test_2c_ships_and_notes_railroad_earths_titles_without_footnote_marks` | same | note track numbers 19 -> 20 and 21 -> 22 |
| gather `test_umphreys_2004_04_14_taper_owned_identical_to_today` | 1 (synthetic tape keeps the 01:14 `Front Porch >`) | breaks [11, 19] |
| gather `test_sibling_transfer_split_is_identical` | 1 (windsor has 28 tracks) | the "no anchors" case blanks `range(28)` |
| cascade `test_cascade_cases_are_not_vacuous` | 1 / 2.2+2.3 | Two causes. (a) Windsor's 28 files count-match its description, so the S rung fills the blanks before sibling-align: `_gd74_blank_ia` drops D3_T02 to restore the 27-file shape. (b) The format-sibling note no longer fires on the captured furthur tape: added a `furthur-19` case and kept the captured `furthur` case |
| cascade `test_c_changed_stems_leave_2b_and_fetch_and_notes`, `test_wholly_untagged_evaluated_after_c` | 2.2 + 2.3 | `_furthur_19` now also drops `10.tuningup.*`, which was its premise ("19 files") |
| cascade `test_c_declines_without_a_reference_and_2b_stands` | same | runs on the 19-file item with the full 20-entry description, keeping its premise |
| probe `scripts/test_title_hygiene_probe.py::test_gate0_parity_on_fixtures` | 1 | the library's windsor mapping drops D3_T02, matching `_gd74_blank_ia` |
| *(not failing, mis-pointed)* gather `test_override_path_leaves_matched_unmeasured` | 1 | `encore_after=26` -> `27`, so it stays on D4_T06, with the comment `re-keyed by filename in Task 3` |

Other overrides I checked stay on their files: gather `:2453` (furthur titles 1 and 3, before the insertion at 10); probe `titles {1,4}, set_breaks [10]`; and the cascade wiring test's `titles {1,2}` on every case. The other override tests use gd73, tnd or synthetic tapes, none of which change.

## Decisions (brief vs spec)
- **`test_tripwire_drop_records_its_own_reason`:** the brief names the file `follow-me-now.mp3`. A bare name like that fails the filename-convention arm too, so it is not a short-only drop and the tripwire never sees it. I used `band1t09 follow-me-now.mp3`, which carries the item's dominant stem (docstring says why).
- **`http://` in a stem:** the brief lists it among the stem examples, but it cannot fire there, because `basename_without_extension` cuts at the last `/`. I tested it on a tag instead and the test says so.
- **Tag fallback is a raw `or`:** `own_title or original_title`, as measured (`dump_r1`/`r1_files`) and as the brief says. A whitespace-only own title therefore does not fall back to the original's.
- **Original lookup only for derivatives:** the original's title is looked up only when `source == "derivative"`, as in both measured scripts. An original-source file with an `original` key is ignored.
- **Non-string titles:** a non-string `title` is passed through `str()` before the normative functions. This matches `clean_tag_title`'s own `str(raw)`, so a stray list cannot raise in `SPAM.search`.
- **Extra tests beyond the brief's list:**
  - `test_tripwire_reads_no_album_or_artist`: venue `@`, taper domain and `www.` in album/artist/creator do not trip the tripwire;
  - `test_spam_tag_on_an_interior_tagged_file_drops`;
  - `test_interior_ignores_spam_and_filename_junk_neighbours`;
  - `test_short_keep_true_changes_some_fixture`: guards the false-pin from being vacuous;
  - `test_short_keep_false_returns_no_names`.

## Self-review findings / concerns
1. **Format choice now sees the rule.** The code is untouched, but `filter_files` picks the first format whose kept set is non-empty, and that set now includes files the rule kept. A format whose only kept files are tagged short ones can therefore now win: in practice a lossless format with fewer than 5 durations, all under the absolute 90 s floor. This follows from spec 2.5 putting the rule inside `_keep_and_exclude`. The reviewer may want to confirm it is intended.
2. **Format asymmetry on furthur.** The mp3 `10.tuningup.mp3` is kept because its own tag `tmp` is a placeholder and so counts as tagged (2.2). The FLAC original `Tuning Up` drops as junk (2.3).
   - Net effect on the captured tape: the mp3 delivery is whole and D titles it `Tuning Up`, which is good.
   - The cost: format recovery / C cannot pair 20 mp3s with 19 FLACs, and the format-sibling note is lost.
   - Task 2's junk note should fire on it, since its final title `Tuning Up` is wholly junk. That looks like what the note is for, but it is worth confirming in Task 2.
3. **Interim coverage dips on gd74 windsor.** Coverage is 27/28 and `conflicts=['Weather Report Suite Part 1']` until Task 2 adds `and not t.short_kept` to `_songish_coverage`. Task 2's dry run should move `test_gather_recovers_structure_from_sibling` and `test_align_result_matched_reaches_the_track` back to 1.0. `conflicts` may still list the unmatched item, so Task 2 should check that too.
4. **Restored fixture shapes.** Several tests about the old 19/27-file shapes now remove the short file from their input, so they keep testing their own subject (2b note, C, sibling-align non-vacuity). The captured tapes are still covered by the updated gather tests and by the `furthur` cascade case.
