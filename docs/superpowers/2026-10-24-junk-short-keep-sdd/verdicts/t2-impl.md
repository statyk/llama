# Task 2 handback (t2-impl)
Status: DONE. Commit 679357f feat(gather): short_kept tracks, coverage clause, wholly-junk note.
Tests: `./.venv/bin/python -m pytest -q` -> 4856 passed, 1 skipped, 8 deselected (baseline 4848; +8 new tests).

Implemented: Track.short_kept (models.py, after included); resolve_titles(short_kept=frozenset()) stamps it (titles.py); title_cascade passes frozenset(inp.ordering.get("short_kept", ())) (gather.py); _songish_coverage gains `and not t.short_kept` (structure.py); junk note appended after the slice5 block, before Show(...), once per short_kept track whose final title short_tag_is_junk judges junk. gather imports short_tag_is_junk.

TDD: RED = `pytest -q <titles/structure/gather -k "short_kept or wholly_junk">` -> 7 failed (resolve_titles unexpected kwarg / no attribute short_kept); the pin test_short_kept_file_votes... passed once corrected (pin; see decision). GREEN: same selection passes; full suite above.
Decision: the include-pin cannot use a short-kept file as the "operator-included" file, because a file the rule keeps is not in ordering["readmitted"] (it votes). The pin includes a junk-tagged short file (Crowd Noise) that the rule drops, and checks it is out of both bases while the short-kept Murph is in.

Dry run (before editing existing tests): only 2 failures: test_gather_recovers_structure_from_sibling and test_align_result_matched_reaches_the_track (windsor coverage 27/28 -> 1.0; spec 3). Updated both, comment names spec 3. Nothing unexplained. No other existing test changed.
Track( grep (packages/llama/src): titles.py:534 (resolve_titles; stamped), title_hygiene.py:582 (internal neighbours list for the S check, never shipped; no stamp needed), package.py:62 is ManifestTrack. Later rungs copy with model_copy (override loop confirmed; survival tested through align(), structure-override path, taper ownership).
Windsor: structure.conflicts still lists ['Weather Report Suite Part 1'] (coverage 1.0). No second filter added, per spec 3.
Furthur: junk note fires: "short-kept track 10 'Tuning Up': its final title is wholly junk" (D fills desc-position). No existing test pinned notes there; added test_furthur_tuning_up_short_kept_is_noted_wholly_junk.
New tests: test_resolve_titles_stamps_short_kept; test_songish_coverage_ignores_short_kept; test_unmatched_short_kept_track_does_not_lower_coverage; test_short_kept_survives_to_show_json (incl. ManifestTrack pin); test_old_show_json_reads_short_kept_false; test_wholly_junk_final_title_notes; test_short_kept_file_votes_like_any_kept_file; test_furthur_tuning_up_short_kept_is_noted_wholly_junk.
Files: models.py, titles.py, structure.py, stages/gather.py; tests test_titles.py, test_structure.py, test_stage_gather.py.
Concerns: windsor conflicts still shows Part 1 (reviewer may want it noted); none else.
