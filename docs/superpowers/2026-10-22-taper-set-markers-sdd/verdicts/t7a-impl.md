# t7a-impl handback: DONE_WITH_CONCERNS

Commit a8950fa `feat(harness): taper record fields, override stripping and scoring` (on 63c4a4b).

## Tests
- ./.venv/bin/python -m pytest packages/llama/tests/test_replay.py -q -> 90 passed
- ./.venv/bin/python -m pytest scripts/test_replay_holds.py -q -> 58 passed
- ./.venv/bin/python -m pytest scripts/test_taper_probe.py -q -> 11 passed
- full ./.venv/bin/python -m pytest -q -> 4414 passed, 1 skipped, 8 deselected. setlist.py diff vs main empty.

## Brief test -> location
- test_record_carries_taper_fields: packages/llama/tests/test_replay.py (end)
- test_show_replay_to_dict_has_the_contract_keys_plus_date: updated in place (only existing test changed)
- test_strip_mode_removes_only_structure_overrides: scripts/test_replay_holds.py (plus an unstripped-stamp test)
- test_compare_refuses_mixed_strip_arms_and_writes_no_lists_for_stripped: scripts/test_replay_holds.py
- test_score_counts_matches_against_adjudicator_targets: scripts/test_taper_probe.py (plus test_score_refuses_an_unstripped_arm_and_scores_the_known_disagreements)

## Design
- replay.py: six fields set in replay_show from legs.gather (sets/filler of gathered.show, pre-vet).
- replay_holds.py: `_shadow` copies provenance/show/vetting/briefing files + overrides.json minus set_breaks/encore_after into <scratch>/.shadow/<slug>; `replay_show` runs on the shadow ws; the row's state and digests are then reset to the REAL show's (so stripped vs unstripped arms pass the digest gate). Arm always carries `structure_overrides_stripped` (bool); compare `_gates` refuses a mismatch (missing key = False, exit 2); stripped pair writes none of the three *_list.json (stale ones deleted by the existing unlink) and summary says so. Live show dir/overrides untouched (test hashes it). --out/--scratch library-overlap refusals unchanged.
- taper_probe.py `score --arm A [--evidence D] --out O`: refuses an arm not stamped stripped (exit 2) and an --out overlapping the arm's root. Rows = yes/partial of classified.jsonl; classes: match / filler-only / miss (via arm `filler` flags, song level, same target_labels/breaks_of as gate), declined (not owned, with taper_reason), owned-no-target, owned-renumbered (not graded, as gate), owned-target-does-not-fit, unreplayable/absent; filename-set and track-title-set-label primaries reported apart as out of scope. Outputs score_rows.jsonl, score_summary.txt (by primary, every miss listed).

## The 8 known disagreements (excluded from headline match/miss; own section, verdict "as expected" / "UNEXPECTED")
- derektrucksband-2005-01-09, darkstarorchestra-2007-05-08, thedead-2009-04-29: "the disputed boundary is an encore the taper did not label: if the taper owns the show its last set runs to the end of the tape (no encore label ships); if not owned it is computed as today". Owned with an "encore" label in sets = UNEXPECTED.
- gratefuldead-1970-05-15-spans: "stays held by `tape spans`": expected iff outcome is still-held/still-held-package and a gather flag starts "tape spans"; else UNEXPECTED.
- deadandcompany-2018-06-16, gratefuldead-1981-12-31, stevekimockband-2003-03-11, ekoostikhookah-2009-12-31: "where the taper owns the structure its structure ships, an expected disagreement with the adjudicator; if not owned it is computed as today". Always "as expected"; detail notes whether owned shipped equals/differs from target.

## Deviations / concerns
- The brief gave no precise wording for the 8; I derived the checkers from spec lines ~96-101 ("its structure ships... last set runs to the end unless veto"). The last four can never be UNEXPECTED by construction (the spec only says disagreement is expected); Task 9 may want a stricter check.
- Renumbered (renum) rows are not graded, mirroring the gate (targets use the adjudicator's own include/exclude numbering, which stripped mode does not reproduce).
- `filler` and `sets` are of the gathered show before vet; step1_alignment/taper_* are None for override-path shows (not applicable in strip mode).
- Not run against the real library (per instructions).
Status: DONE_WITH_CONCERNS
