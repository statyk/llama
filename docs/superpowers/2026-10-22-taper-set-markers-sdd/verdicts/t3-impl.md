# t3-impl handback

Status: DONE, but GATE FAILS the spec's stop condition: ownership ratio 0.333 < 0.5. Controller must stop and go to the operator at CHECKPOINT A.
Commit: feat(scripts): taper yield gate and marker-form probe (scripts/taper_probe.py, scripts/test_taper_probe.py). Nothing else changed (taper.py, setlist.py untouched).
Tests: scripts/test_taper_probe.py 6 passed; full suite 4161 passed, 1 skipped, 8 deselected.
TDD: tests written alongside, implementation written first (deviation); RED shown afterwards by running the test file alone in an empty dir: collection error (no taper_probe module). GREEN: ./.venv/bin/python -m pytest scripts/test_taper_probe.py -q -> 6 passed.

## Step 5 headline (gate_summary.txt)
yes/partial rows: 339
in-scope rows (yes, worded form, 3 primaries): 186 (skipped: 0)
ownership ratio: 62/186 = 0.333
target match rate (exact, owned w/ target, not renum): 33/44 = 0.750; filler-only 10 (own class); match incl. filler-only 43/44 = 0.977; misses 1 (darkstarorchestra-2007-05-17)
owned renum rows 5; owned rows with no target 13 (both listed in gate_summary.txt)
By primary (in scope): desc-set-header owned 41 / unplaced 53 / not-asserted 20; desc-disc-with-set owned 19 / unplaced 17 / not-asserted 30; desc-inline-marker owned 2 / unplaced 1 / not-asserted 3.
In-scope non-owned: 71 unplaced (46 "first/last song matches 0 tracks" + 2 more, 15 "matches 2-3 tracks", 5 non-filler between, 1 also on other side...), 11 no markers, 27 one set, 3 veto encore-like (garajmahal-2007-06-02, philleshandfriends-2001-12-31, moe-2004-01-31), 5 veto track title, 3 void continuation, 1 empty set, 2 set 4+, 1 skipped number.
Observation: many unplaced rows are reader items that are not songs ('=====', ')', '?', '-Disk 2', 'Disc 2:', 's2t01: Ripple', 'Warm Up', 'Drums', '634-5789'), i.e. the first/last item of a set is junk; looks like a reader/item-cleaning defect class worth the Opus reviewer's attention. Also 11 "no markers" + 27 "one set" among rows the classifier called yes+worded (classifier vs reader disagreement; the reader may be missing a form, or the cache description differs from the bundle's).
R4 collateral: gate 0 rows (all yes/partial and in-scope); library 1 show (mogwai-2001-06-16) lost to R4 inputs alone.

## Library pass (library_summary.txt)
3983 shows; skipped 461 (458 operator override, 3 no tracks); evaluated 3522; owned 609 (503 identical labels, 106 differ).
Tiers: songs moved 31, labels renamed 3, encore folded 33, encore added 21, sets merged or split 17, filler only 1. 10-slug samples per tier in the file. (Spec: large encore folded / sets merged is a reader defect to fix before building; 33/17 need the CHECKPOINT A review.)

## forms (forms_summary.txt; 15607 cached items; lines / items)
E/E<digit> header 4867/4236; ENC header 42/40; Encore/Encores header 5301/5127; ordinal encore 35/32; inline-split marker 4328/3797; continuation header 345/285; set-and-encore header 7/7; 1st/2nd/3rd Set 192/99; Disc N (Set M) 612/254; First/Second/Third Set 69/37; Set N/one/I 17753/8685; veto R4(a,c) 24/23; R4(b) 79/70; veto encore word 2082/1696; veto line starts E./E)/E<d>/(E) 205/163; R4(d) 0/0; set 4+ 28/21.
Text-level (description): asserts 8299, no markers 3638, one set 3082, skipped number 185, empty set 64, numbered after encore 62, set 4+ 16, continuation 13, cross-check 10, decreasing 7. Samples (all family hits + 30 random others per form, seed 20261022) in forms_samples.txt.

## Outputs (~/.llama-harness/piece2/gate/)
gate_rows.jsonl, gate_summary.txt, library_rows.jsonl, library_summary.txt, forms_summary.txt, forms_samples.txt. Each run takes seconds (gate 7 s, forms 24 s).

## Judgment calls (each toward the taper owning less)
- Headline match rate counts exact matches only; filler-only reported separately and excluded from numerator.
- Target labels from the adjudicator's flags exactly: breaks split sets, `--set-encore N` starts encore after track N; absent flag means absent (no inherited shipped breaks/encore). "No target" = neither t_breaks nor t_enc.
- Gate tracks/today_sets from the bundle's table (today_sets = its set column, parallel by construction; mismatch -> skipped, none occurred). Unlike sort1.py, the bundle row's right-hand columns are indexed from the end so titles containing ' | ' parse (sort1 read matched from the wrong column then).
- Library: show.json tracks and set labels as stored; shows with overrides.json set_breaks/encore_after or structure.source=="override" skipped (counted). Missing cache -> skipped (none occurred).
- Library tier precedence (one tier per differing show): filler only (labels equal on non-filler tracks) > labels renamed (same grouping, different names) > encore folded / encore added (encore presence differs) > sets merged or split (distinct non-encore label count differs) > songs moved.
- R4 off = probe-local patch of taper._ENCORE_LIKE_END, _ENCORE_LIKE_ITEM, _LEADING_NUMBER to a never-matching regex (restored after); "would be owned" means placement non-None.
- `forms` counts lines per form; void/cross-check are per text (description/notes field), since they are not line rules. Inline-split counted on raw lines pre-split.
- --out refused when overlapping --root or --bundles (exit 2). jerrybase prints "skipped 117 malformed rows" on import (pre-existing).

## Concerns
- Ownership 0.333 triggers the spec's stop rule: operator decision needed; Task 4 should not start.
- The unplaced-by-junk-item pattern and the 38 classifier-yes rows read as no markers/one set deserve checking before concluding the rule has low yield.
# t3-fix1 handback
Changed scripts/taper_probe.py: tier() now decides encore presence (folded/added) before run equality, and "labels renamed" also requires equal encore positions on non-filler tracks. "sets merged or split" split into "sets merged" / "sets split" (numbered-set count over non-filler tracks). New numbered_count/sets_merged helpers; library_rows.jsonl rows carry `sets_merged`; library_summary.txt lists EVERY row whose numbered-set count decreased (any tier) and every row of the "sets merged" tier.
Tests (scripts/test_taper_probe.py, 7 pass): extended tier test (merged/split), new test_encore_changes_are_never_renames_and_merges_are_flagged (encore folded into set 2, stored set 3 -> encore, merge inside an encore-folded tier).
Command: ./.venv/bin/python scripts/taper_probe.py gate --out ~/.llama-harness/piece2/gate. Gate numbers unchanged (62/186 = 0.333; 33/44 = 0.750).
New library tiers: songs moved 31, labels renamed 0, encore folded 34, encore added 23, sets merged 4, sets split 13, filler only 1 (owned 609, 106 differ as before).
Numbered-set count decreased, any tier (8): assemblyofdust-2004-12-31, mymorningjacket-2018-03-05, ryanadams-2008-01-19, tedeschitrucksband-2020-02-21 (sets merged); smashingpumpkins-1998-05-19 (encore folded); joerussosalmostdead-2016-02-10, joerussosalmostdead-2022-04-30, tedeschitrucksband-2019-11-15 (encore added). Note: the two joerusso rows (stored set 3 becomes the encore) count as a numbered decrease by definition though they are an encore change, not a merge.
Full suite: 4162 passed, 1 skipped, 8 deselected.
