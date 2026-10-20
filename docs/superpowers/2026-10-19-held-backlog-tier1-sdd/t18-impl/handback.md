# t18-impl handback — Task 18 (slice 5c)

STATUS: DONE_WITH_CONCERNS (concerns are review notes; nothing is blocked)
Commit: e9e84e1 on held-backlog-tier1 (BASE df602e0)
Suite: ./.venv/bin/python -m pytest -q -> 3691 passed, 1 skipped, 8 deselected (base ~3680 + 11 new)

## Changes
- packages/llama/src/llama/jerrybase.py
  - `_LEADING_PAREN = re.compile(r"^\s*\([^)]*\)\s*")`, `_fold_leading_paren`, `_match_tiers(tracks, closer, fold)`.
    `_closer_candidates` = unfolded exact -> unfolded fuzzy (unchanged behaviour, via `_match_tiers` with identity fold);
    ONLY when both are empty, a third tier: folded exact -> folded fuzzy (ruling M1).
  - `closer_contradictions`: same signature/shape; single hit not at a break and `_followed_only_by_filler` -> skipped (no hard, no soft).
  - `_followed_only_by_filler(tracks, i)`, `filler_tail_closers(tracks, event)` (Contracts 5c.1 text), helper `_filler_excused`.
  - `anchor_numbered_sets(tracks, event, aligned_sets) -> (labels, note) | None` (Contracts 5c.2 text).
- packages/llama/src/llama/stages/gather.py: when `anchor_breaks` is None and event is not None, tries `anchor_numbered_sets(tracks, event, result.sets)`; on success feeds its labels into the EXISTING anchoring branch (so alignment="jerrybase", "set breaks anchored from jerrybase" (+ " (was ...)") to local structure notes exactly as before, LLM/low-coverage elif skipped); the 5c.2 note -> `op_notes` (GatherResult.notes). Closer tripwire: `op_notes += jerrybase.filler_tail_closers(tracks, event)` (never local `notes`).
- scripts/replay_holds.py: `_closest` gains "5c.3 second closer candidates" (`_second_closer_candidates`) and "5c.1 short-track arm (not adopted): N show(s)" (`_short_track_arm`, `SHORT_TRACK_SEC = 420`), both read stored show.json from the cand arm's `root` read-only and import `llama.jerrybase` from the running tree. N counts distinct shows; rows are one per (show, closer).
- Tests: test_jerrybase.py (brief's 5 tests with B5 "Casey Jones" fix; plus `test_5c3_the_fold_is_a_fallback_tier_only_when_the_unfolded_tiers_miss` and `test_5c2_declines_when_the_numbered_closers_are_out_of_order`); `test_closer_matching_preserves_a_leading_parenthetical` left byte-identical and passing; brief's REWRITE dropped per M1. test_stage_gather.py: brief's 5c.2 gd73 test + `test_5c1_filler_tail_note_goes_to_notes_json_never_to_structure_conflicts`. scripts/test_replay_holds.py: brief's header test + `test_closest_calls_5c_subsections_list_the_stored_tracks_rows` (content rows and the 420 s boundary).

## Red before green
Before implementation: test_jerrybase.py ImportError on `anchor_numbered_sets`; gather 5c.2 test `'deterministic' == 'jerrybase'`; replay header test missing subsections.

## Mutation table (MROOT=/var/folders/yn/jlwxryrj1ds7jpvw931jk1jm0000gn/T/mut-t18-impl-nteFW1, removed afterwards; shadowing proven per mutant; predictions logged before flips)
| mutant | predicted | caught by |
|---|---|---|
| (a) `_followed_only_by_filler` any() | test_jerrybase::test_5c1_closer_followed_only_by_filler_is_an_operator_note_not_a_soft_note | same |
| (b) numbered closer with 2 candidates accepted (`not cands`, take cands[0]) | test_jerrybase::test_5c2_declines_without_an_encore_row_or_on_an_ambiguous_numbered_closer | same |
| (c) strictly-increasing check dropped | brief tests: SURVIVED (predicted); added test_jerrybase::test_5c2_declines_when_the_numbered_closers_are_out_of_order | that added test |
| (d) fold on closer only | test_jerrybase::test_5c3_leading_parenthetical_folds_on_both_sides | same |
| (e) 5c.1 note to local `notes` | brief tests: SURVIVED (predicted: the gd73 fixture has no filler track and anchors, so the tripwire never runs); added test_stage_gather::test_5c1_filler_tail_note_goes_to_notes_json_never_to_structure_conflicts | that added test |
| (f) fold as first tier | test_jerrybase::test_closer_matching_preserves_a_leading_parenthetical | same + test_5c3_the_fold_is_a_fallback_tier_only_when_the_unfolded_tiers_miss |
Note on (b): the variant taking cands[-1] is caught by the strictly-increasing check on that test's shape (Deal at 1 and 3, Playin at 2), so cands[0] is the meaningful "accepts" mutant.

## Deviations
1. Brief REWRITE test dropped, fallback-tier test added (ruling M1). B5 applied ("Casey Jones" for "JBG" in sub-cases 1 and 3).
2. 5c.2 encore labelling: the brief says tracks after the last numbered closer are "encore" where `aligned_sets[i] == "encore"`; I apply it as a TRAILING RUN (from the tape's end backwards while aligned says encore), like `anchor_breaks`' encore guard, and only when `len(aligned_sets) == len(tracks)`. Per-track would allow "encore" followed by a set-2 track. Same result on every brief case; a subset of "only where the alignment said encore", so it never invents an encore. Flagging for review.
3. The 5c.1 gather test monkeypatches `jerrybase.is_filler` (the gd73 fixture has no filler track); `structure._FILLER`/`is_filler` themselves are untouched.

## Concerns for review / Checkpoint F
- 5c.3 also reaches `closer_contradictions`: a closer that was "not found" (soft note) and now has a single folded candidate that is not at a break becomes a HARD flag. Inherent to spec 5c.3 applying "on both sides"; Checkpoint F's flags.txt should show any such adds under `structure`.
- 5c.3 fold is applied to the whole track title before `title_components`, so a merged track whose LAST component has a leading paren ("Jam > (I Can't Get No) Satisfaction") is not folded. Literal to the brief; noted.
- No do-not-retune constant touched (structure.py not in the diff).

## Fix round 1

STATUS: DONE. Commit: 6c7aeef

- Added test_stage_gather.py::test_5c2_note_goes_to_notes_json_never_to_structure_conflicts: monkeypatches gather_mod.align to wrap the real align and relabel "encore" -> "2", so the gd73 tape's trailing "Johnny B. Goode" stays in set 2. With the RFK event (closers I Know You Rider / Eyes of the World / encore Casey Jones), it asserts alignment "jerrybase", sets ["1","1","1","2","2","2"], and that the Contracts 5c.2 string "set breaks anchored from jerrybase numbered sets (encore row 'Casey Jones' unmatched; 1 trailing track(s) stay in set 2)" is in res.notes and NOT in res.show.structure.conflicts.
- Mutation (prediction logged before the flip; MROOT=/var/folders/yn/jlwxryrj1ds7jpvw931jk1jm0000gn/T/mut-t18-impl-r1-X90Ma4, shadowing proven: llama.__file__ = $MROOT/g/tree/packages/llama/src/llama/__init__.py; private PYTHONPYCACHEPREFIX; path removed afterwards):

| mutant | predicted | caught by |
|---|---|---|
| (g) gather `op_notes.append(numbered_note)` -> `notes.append(numbered_note)` | test_stage_gather::test_5c2_note_goes_to_notes_json_never_to_structure_conflicts | same ("1 failed, 201 passed") |

- Commands / results:
  - ./.venv/bin/python -m pytest packages/llama/tests/test_stage_gather.py packages/llama/tests/test_jerrybase.py -q -> 202 passed
  - ./.venv/bin/python -m pytest -q -> 3692 passed, 1 skipped, 8 deselected, 26 warnings
- No other changes.
