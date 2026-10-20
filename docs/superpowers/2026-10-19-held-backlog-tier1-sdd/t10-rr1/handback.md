### Finding Verdicts

- **Important 1: 2a re-accepts a position 2b demoted as recording-level junk** — ADDRESSED. `accept_short_tags` has a required keyword `demoted: frozenset[int]` (packages/llama/src/llama/stages/gather.py:874). The loop skips `i in demoted` before reading the tag (gather.py:905). `compute_gather` passes `demoted=frozenset(demoted)` (gather.py:1201). That is the same list that drives 2b's notes (gather.py:1094-1099).
  - **Same set as 2b (checked):** gather.py:1093-1096 calls `tag_layer(kept, format_titles, tag_gate_basis)` and `placeholder_positions(..., corroboration=frozenset(cb.corroboration), item_title=meta.get("title"))`. `resolve_titles` uses exactly the same arguments (gather.py:1138-1140), and inside it demotes `set(placeholder_positions(...))` over `tag_layer(files, format_titles, gate_basis)` (titles.py:389-391). So 2a's `demoted` is resolve_titles' demotion set with the override positions removed.
  - **M9 override filter is harmless:** an override position is stamped `title_source="override"` (gather.py:1142-1146), so 2a's first condition `t.title_source != "unresolved"` skips it whether or not it is in `demoted`. Leaving it out of `demoted` changes nothing in 2a. It only keeps the 2b note off that position, as intended. Positions that sibling-align or setlist-gap filled are no longer `unresolved`, so the skip does not block those rungs. That matches spec 2b.
  - **Unit test:** `test_accept_short_tags_skips_positions_2b_demoted` (test_stage_gather.py, new) uses `["J > J"]*4` with demoted {0,1,2}. Tracks 1-3 stay unresolved; track 4, the control, is accepted; only track 4 gets a note. The brief asked for "none accepted, no notes". This row adds a non-demoted control on top of that, which is stronger.
  - **Wiring test:** `test_2a_does_not_reaccept_a_recording_level_2b_demotion` sets every tnd tag to `J > J`, with the sibling corroborating `J`. It asserts the 2b note is present, that no `accepted short tag title` note appears, and that every track is unresolved.
  - **Optional extras:** the `("F > #","F","F")` and `("1922 $ #","1922","1922")` rows were added to the `tag_core`/`strip_taper_markers` parametrize (test_titles.py:590).
  - **Check I ran (mutant j, scratch copy):** source from `git archive e5e4411`, `PYTHONPATH` shadow proven (`gather.__file__` resolved inside the scratch tree), private `PYTHONPYCACHEPREFIX`. I named the expected failures before flipping: both new tests. Dropping `or i in demoted` failed exactly those 2 of the 10 `-k "short_tags or 2a"` tests. The wiring test failed on its behaviour assertion (`assert not any(... 'accepted short tag title' ...)`), not on setup. The unmutated control was 10/10 green, and the 14 `tag_core_and_shipped` rows passed. The report's mutant (k), the call site passing `frozenset()`, I did not re-run. The wiring test is the only test that can see it, and mutant j shows that test is sensitive to the skip.

### New Breakage in the Fix Diff

None. One wording slip, Minor, not blocking: the docstring at gather.py:885 says "a `J > J` x 3 tape", but the number of tracks is incidental. The rule is recording-level.

### Out-of-Scope Observations

None.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.
