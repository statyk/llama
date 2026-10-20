# t9-impl handback: Task 9 (slice 2b, placeholder demotion at the tag rung)

Status: DONE. Commit de14749 on held-backlog-tier1.

## What was implemented
- `titles.tag_layer(kept_files, format_titles, gate_basis) -> (titles, source)`: a straight extraction of resolve_titles' tag layer (`sibling-format` when format_titles is not None, else `tags`). resolve_titles calls it.
- `titles.placeholder_positions(tag_titles, *, corroboration, item_title) -> list[int]`: skips blank tags and tags whose `fuzzy_norm_title` is in `corroboration`. Otherwise it demotes on any of: `is_placeholder(t) or is_timestamp(t)` (no is_real_title gate), `recording_level_junk(tag_titles, item_title)`, or `is_real_title(t) and is_residue(t)` (the gate from ruling d is kept).
- `resolve_titles(..., *, corroboration=frozenset(), item_title=None)`: a demoted position becomes `title=f["name"]`, `title_source="unresolved"`. It sits ahead of the `is_real_title` branch, so a demoted position never reaches the `setlist` rung.
- `compute_gather`:
  - passes `corroboration=frozenset(cb.corroboration)` and `item_title=meta.get("title")`;
  - computes `demoted` from `tag_layer(kept, format_titles, tag_gate_basis)`, filtered to drop positions in `overrides.titles` (ruling M9);
  - emits one Contracts-2b note per demoted track (`raw` = the tag-layer title);
  - sets `fetch_siblings = bool(kept and (title_fraction(clean_tag_titles(kept)) < 1.0 or demoted))`;
  - adds the format-sibling note in the brief's exact wording. Notes go to `GatherResult.notes` (op_notes) only, never conflicts, flags or the LLM.
- `placeholders.is_placeholder_title`: docstring only. Callers must pre-gate on `is_real_title` (spec 576-577), and 2b uses `placeholder_positions` instead. No behaviour change.
- Fixture `packages/llama/tests/fixtures/furthur2012-07-15.json` was cut with `capture_fixture.py --from-cache` (28 KB, no audio). It has 19 kept mp3s all tagged `tmp`, and FLACs carrying real tags.
- Comment block above `fetch_siblings` reordered: the tag_gate_basis comment and line moved up beside the 2b block. The "at 1.0 there are no unresolved tracks" sentence was updated for 2b's demotions.

## TDD evidence
- test_titles.py RED: `ImportError: cannot import name 'placeholder_positions'`.
- test_stage_gather.py -k 2b RED (before implementation): 4 failed, 1 passed. These are assertion failures because the gather tests don't import the new names; the passing one is the real-tagged negative.
- GREEN after implementation. Logged in t9-impl.log.

## Tests added
test_titles.py:
- the brief's 5 tests, verbatim;
- `test_placeholder_positions_residue_judges_only_titles_the_tags_rung_would_adopt`. It covers `d1t02` and `x`/`01`, which are not demoted by the residue arm, plus real-title residue `buckethead2004-06-04d2t05`, which is demoted;
- `test_placeholder_positions_word_plus_date_residue_breadth_is_pinned`: `Jam 12-31-99`, `Ripple 1970-09-20` and `Drums 1977-05-08` are demoted (the P5 limitation); `Scarlet Begonias 1977-05-08` is not;
- `test_resolve_titles_non_real_placeholder_skips_the_setlist_rung`: `Tr-02` and `05:27` become unresolved, and `d1t02` still takes the setlist rung;
- `test_resolve_titles_demotes_a_sibling_format_placeholder`;
- `test_resolve_titles_item_title_arm`;
- the corroborated-tag test, extended with a `Track 01` case that actually discriminates. The brief's `Song #1` row is never demoted, with or without corroboration.

test_stage_gather.py:
- the brief's 2 tests (plus a no-format-note assertion on gd73);
- `test_2b_files_the_format_sibling_it_does_not_recover_from`: the exact note `format sibling tagged: Flac title fraction 1.00 (recovery not triggered; filed, not acted on)`, and no note text in conflicts or flags;
- `test_2b_recomputes_fetch_siblings_over_demoted_titles` (patches `_sibling_transfer`);
- `test_2b_never_judges_an_override_title` (M9): positions 1 and 3 are overridden, so there are 17 notes and none for tracks 1 or 3;
- `test_2b_demotes_a_recovered_sibling_format_placeholder_and_files_no_sibling_note`;
- `test_2b_a_sibling_description_naming_the_tag_exempts_it`: corroboration reaches gather;
- `test_2b_item_title_reaches_the_recording_level_class`: the item title is spelled two ways that agree only under fuzzy_norm_title.

## Mutation table
Recipe: fresh rsync copy per mutant under $TMPDIR, PYTHONPATH shadow, private PYTHONPYCACHEPREFIX, the worktree's python `-m pytest`. Shadow was proven for each mutant: `llama.__file__` printed under `$M/tree`. Predictions were written in scratchpad/mutants.py before any flip. Files run: test_titles.py and test_stage_gather.py.

| mutant | predicted test | result |
|---|---|---|
| (a) drop corroboration exemption | test_titles::test_placeholder_positions_exemptions | CAUGHT by it; also test_resolve_titles_never_demotes_a_corroborated_tag and test_2b_a_sibling_description_naming_the_tag_exempts_it |
| (b) demote a blank tag | test_titles::test_placeholder_positions_classes | CAUGHT by it; also test_resolve_titles_demotes_a_placeholder_... and 18 more |
| (c) gate placeholder/timestamp on is_real_title | test_titles::test_placeholder_positions_classes | CAUGHT by it; also test_resolve_titles_non_real_placeholder_skips_the_setlist_rung |
| (d) drop is_real_title from the residue arm | test_titles::test_placeholder_positions_residue_judges_only_titles_the_tags_rung_would_adopt | CAUGHT by it; also test_placeholder_positions_exemptions and test_resolve_titles_non_real_placeholder_skips_the_setlist_rung |
| (e) demoted position falls through to the setlist rung | test_titles::test_resolve_titles_demotes_a_placeholder_and_never_lets_it_fall_to_the_setlist_rung | CAUGHT by it; also test_resolve_titles_non_real_placeholder_... and test_gather_low_coverage_uses_llm_alignment (its `Track N` tags are correctly demoted) |
| (f) gather: drop the overrides.titles filter | test_stage_gather::test_2b_never_judges_an_override_title | CAUGHT (only it) |
| (g) fetch_siblings without `or demoted` | test_stage_gather::test_2b_recomputes_fetch_siblings_over_demoted_titles | CAUGHT (only it) |
| (h) format note without `format_titles is None` | test_stage_gather::test_2b_demotes_a_recovered_sibling_format_placeholder_and_files_no_sibling_note | CAUGHT (only it) |
| (i) gather passes empty corroboration | test_stage_gather::test_2b_a_sibling_description_naming_the_tag_exempts_it | CAUGHT (only it) |
| (j) gather passes item_title=None | test_stage_gather::test_2b_item_title_reaches_the_recording_level_class | CAUGHT (only it) |

No survivors.

## Full suite
`./.venv/bin/python -m pytest -q` gives 3401 passed, 1 skipped, 8 deselected. The baseline was 3383; this task adds 18 tests.

## Files changed
- packages/llama/src/llama/titles.py
- packages/llama/src/llama/stages/gather.py
- packages/llama/src/llama/placeholders.py (docstring only)
- packages/llama/tests/test_titles.py
- packages/llama/tests/test_stage_gather.py
- packages/llama/tests/fixtures/furthur2012-07-15.json (new)

## Self-review
- Do-not-retune constants (is_real_title, title_fraction, _TRACK_NUM_PREFIX, _RECOVER_*, _ENUMERATED_MIN_*, normalize_song, DEFAULT_ALIASES, GD_SHORTHAND) are byte-identical: the diff grep is empty.
- Demotion only ever produces title=filename/unresolved. No other text is written, and a real tag is never overwritten with another title.
- resolve_titles and the gather notes use the same `placeholder_positions` call on the same `tag_layer` output with the same arguments, so the notes and the demotions cannot drift apart. The only difference is the override filter, which is gather-only and output-equivalent.

## Deviations and concerns
1. **Format-sibling note gated on `format_titles is None`.** The brief has no such gate. Without it, when recovery DID fire and the recovered FLAC titles are placeholders (`Track NN`), the loop would find that same FLAC format and file "recovery not triggered", which is false. The note's own wording implies the gate. It is pinned by test, and mutant (h) is caught by it.
2. **M9 is implemented in compute_gather, not resolve_titles.** Override positions are filtered out of `demoted` (no note, no effect on fetch_siblings or the format note). resolve_titles has no access to overrides, and its demotion at that position is overwritten wholesale by the overrides loop, so the shipped track is identical.
3. **One untouched caller changes behaviour.** `scripts/blind_tag_gapfill.py:241` calls resolve_titles with the defaults (empty corroboration, no item title), so that analysis script now demotes placeholders with no corroboration exemption. It is not a pipeline path.
4. **The brief's `test_resolve_titles_never_demotes_a_corroborated_tag` row (`Song #1`) does not discriminate**, because `Song #1` is never a placeholder. I added a `Track 01` row that does.
5. **The format-sibling loop re-runs `filter_files` per lossless format**, but only on tapes with demotions. The cost is negligible.
