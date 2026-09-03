# Task 2 report: numeric-title census, then the scoped `is_real_title` fix

## Status: DONE

## Pointer guard
`PTH-GUARD: OK` at start (re-verified before trusting any test result).

## Commits (worktree `sibling-transfer`, branch `sibling-transfer`)
- `77478b9` -- "titles: accept year-like numeric titles in is_real_title (global scope)"
  - `scripts/numeric_title_census.py` (new)
  - `packages/llama/src/llama/titles.py` (widened `is_real_title`)
  - `packages/llama/tests/test_titles.py` (new tests)

## Test command and output tail
`./.venv/bin/pytest -q` from worktree root (after purging `__pycache__`):
```
1568 passed, 7 deselected, 26 warnings in 7.03s
```
(started from 1562 passed / 7 deselected; +6 new tests, all pinned tests untouched and still pass, including `test_clean_tag_titles_leaves_an_unnumbered_year_title_alone` and `test_clean_tag_titles_strips_once_never_loops`.)

## Step 2 failure output (TDD, before implementation)
```
packages/llama/tests/test_titles.py::test_is_real_title_accepts_a_year_like_numeric_title FAILED
>       assert is_real_title("1922") is True
E       AssertionError: assert False is True
E        +  where False = is_real_title('1922')
1 failed, 5 passed, 51 deselected in 0.17s
```
(the 5 negative-case tests -- d1t02/01/174/12/3 -- passed immediately, confirming the rejection side was already correct and only the acceptance side needed the widening)

## Census output (full)
```
# scripts/numeric_title_census.py (2026-09-02)
# corpus: /Users/shawn/projects/llama-setlist-analysis/iacache
items_total=2095 items_with_kept_files=2064
items_with_pure4_tag_title=2 pure4_tag_titles_total=2
distinct_pure4_values=2: 1977x1, 1970x1
items_with_2_or_more_pure4_titles=0
pure4_titles_equal_to_own_item_metadata_year=0 / 2
title_fraction crosses gather._RECOVER_BELOW (0.5)=0
title_fraction crosses to/from 1.0=2
sample identifier, title, item_year, matches_own_year:
  MWatt2013-01-12	1977	2013	False
  mwatt2012-05-02.Poisson_Rouge.JFCB	1970	2012	False
```
Hand-check (full cleaned tag-title list and `metadata.title`/`creator` for each item):
- `MWatt2013-01-12` (Mike Watt, Redwood Bar 2013-01-12): `1977` sits amid an all-Clash-covers set (`Janie Jones`, `Remote Control`, `I'm So Bored With The USA`, `Hate & War`, ...) -- it's The Clash's song "1977", a real title, not the item's own year (2013).
- `mwatt2012-05-02.Poisson_Rouge.JFCB` (Mike Watt, Le Poisson Rouge 2012-05-02): `1970` sits amid an all-Stooges-covers set (`T.V. Eye`, `Loose`, `Dirt`, `Down on the Street`, `Fun House`, `L.A. Blues`) -- it's the Stooges' song "1970", not the item's own year (2012).

**Verdict: zero qualifying items -> global scope.** No item hit the >=2-pure-4-digit-titles STOP condition, and both hand-checked samples are genuine song titles, not dates. Proceeded to global scope without stopping, per the decision rule.

## Acceptance mutation
Reverted the widening (temporarily, then restored from backup) and re-ran the named test in isolation: `test_is_real_title_accepts_a_year_like_numeric_title` failed as required (`assert False is True`). Restored the widening and re-ran full suite: 1568 passed again.

## Composition note (expected, not fixed)
Per the brief, this erases the merged `--suggest-titles` branch's one demonstrated adoption for `trampledbyturtles-2007-07-20` ("1922" becomes a count-forced `setlist-gap` adoption instead of needing the DP proposal path). `test_correspondence.py`'s docstring at line ~348 (`test_a_count_forced_gap_between_anchors_is_proposed`) still passes -- its assertions never depended on `is_real_title`, only its comment text ("a title `setlist-gap` itself refuses because `is_real_title("1922")` is False") is now stale. Left untouched: `test_correspondence.py` is not in Task 2's file list, and the brief explicitly defers this to Task 5/Task 7's six-show table.

## Concerns
None. Full suite green, named acceptance mutation behaves as specified, census numbers recorded in the code comment above `is_real_title` in `titles.py`.

---

# Fix round 1 (both reviewers: spec FAIL, quality CHANGES REQUESTED)

## Status: DONE

Commit `076a990` -- "titles: fix round 1 -- correct the census, pin the upper bound, size the exposure"
(on top of `77478b9`). Predicate and global-scope ruling both stood -- every
finding was about the instrument (census script) and the record (comments),
not the fix.

## Pointer guard
`PTH-GUARD: OK` re-checked at the start of this round.

## What changed, per finding

1. **Census format-walk bug (Important).** `numeric_title_census.py` broke on
   the first non-empty `filter_files` KEPT set (mp3-then-flac), hiding
   `turkuaz2018-01-18`'s "1662", which only a lossless copy carries and only
   reaches production via `gather._recover_format_titles`. Rewrote the
   script to check both delivery formats independently (never break early)
   and to reimplement `_recover_format_titles`'s algorithm locally with a
   swappable is-real-title predicate. Corrected count: **3 items / 3 titles
   / 3 distinct values** (1977, 1970, 1662), not 2/2/2.
2. **Self-invalidating crossing arm (Important).** The `title_fraction`
   crossing counters called the live `is_real_title`, which becomes
   old==new once the widening lands and pins both counters to 0 --
   irreproducible against the committed tree. Added frozen local
   `_old_is_real_title`/`_new_is_real_title` (never import
   `llama.titles.is_real_title`); re-run now correctly shows 3 items
   crossing to/from 1.0, 0 crossing 0.5.
3. **Missing stratified-sample caveat (Important).** Added the exact house
   wording from `junk.py`'s `LOSSLESS_TITLE_FORMATS` comment to `titles.py`'s
   citation.
4. **Unpinned upper bound (Important).** `_YEAR_LIKE_NUMERIC` switched from
   `^\d{4}$` + `.match()` to `\d{4}` + `.fullmatch()` (removes the
   trailing-newline hole for free); added `"19770101"`/`"12345"` negative
   parametrize cases. Mutation-verified: see below.
5. **Unsized `_hygienic` exposure (Important + owner follow-up).**
   Independently re-derived (not copied from the reviewer) over the same
   iacache corpus via `parse_setlist`: 48,031 canonical items across 2,033
   parsed descriptions, 181 pure-4-digit, 162 absorbed by `_date_norms`
   (reviewer counted 163 -- 1-item discrepancy reported explicitly in the
   comment, attributed to approximating `_show_metadata_norms` off raw cache
   metadata rather than a real `Candidate`/`events` pair; the number that
   matters, 18 distinct items newly passing, is NOT in dispute). Enumerated
   all 18 in `titles.py`'s comment (19 entries -- `minutemen1984-07-14`
   carries two: 2008 and 2021), with mechanism examples (`2448` from a
   `flac2448` lineage fragment, `2026` on a 2025 show, `2020` on a 1994
   show). Stated explicitly and prominently as an UPPER BOUND on exposure,
   not a measured shipped-title count -- passing `_hygienic` is necessary
   but not sufficient (the gap must also be count-forced between anchors);
   the real number needs a re-gather harness that doesn't exist before
   Task 7. Noted `_hygienic` is the pipeline's only silent adopter, which is
   why this gets enumerated rather than waved through.
6. **Cross-population check (owner requirement).** Re-ran the corrected
   census over the 968-item working cache (`~/.llama/cache`). Result was
   **NOT zero** as I first assumed while drafting -- 1 pure-4-digit tag
   title: "1922" on `tbt2007-07-20.391.flac16`, an AKG391-mic'd SIBLING
   recording of `trampledbyturtles-2007-07-20` (filename
   `...-d2t07.mp3`) -- the exact song this task's composition note already
   discusses. It does not trip the STOP condition (1, not >=2 on that item)
   and is not a date match (item year 2007 != 1922). **The two corpora agree
   on the ruling** (zero STOP-qualifying items in both, by the STOP rule's
   own definition) even though raw counts differ (3 vs 1) -- corpus size and
   selection bias, not disagreement. Recorded a side observation, not chased
   further (no re-gather harness exists before Task 7): under the OLD
   predicate this sibling's "1922" tag alone failed
   `_sibling_titles`'s all-or-nothing gate, so pre-widening this well-tagged
   sibling could supply NO track's title via the sibling rung, not just
   this one.
7. **Two stale `is_real_title("1922")` references (Important, fix both this
   round per owner override).** `correspondence.py:105-110`'s production
   module docstring (fixed first) and `test_correspondence.py`'s comment on
   `test_a_count_forced_gap_between_anchors_is_proposed` both asserted
   `is_real_title("1922")` is `False` -- now false since this task's own
   widening. Both corrected in place to state the current, accurate
   behaviour and point at this report; a fresh demonstrating example for the
   DP's residual value over `setlist-gap` is deferred to Task 5/7 as the
   original brief already specified.
8. **Nit.** Trimmed the new negative-case parametrize list: dropped `"12"`
   (subsumed by `"01"`) and `"d1t02"` (duplicate of
   `test_is_real_title`'s existing case).

## Test command and output tail
`./.venv/bin/pytest -q` (after purging `__pycache__`):
```
1567 passed, 7 deselected, 26 warnings in 6.50s
```
(1568 before this round minus 1 net test-case removal from the nit trim: 5
old negative cases -> 4 new ones.)

## Corrected census, both corpora (full, distinctly labelled)

**iacache** (`/Users/shawn/projects/llama-setlist-analysis/iacache`, 2,095
items, decade-stratified sample -- see standing caveat):
```
items_total=2095 items_with_kept_files=2064
items_with_pure4_tag_title=3 pure4_tag_titles_total=3
distinct_pure4_values=3: 1977x1, 1970x1, 1662x1
items_with_2_or_more_pure4_titles=0
pure4_titles_equal_to_own_item_metadata_year=0 / 3
title_fraction crosses gather._RECOVER_BELOW (0.5)=0
title_fraction crosses to/from 1.0=3
  MWatt2013-01-12
  mwatt2012-05-02.Poisson_Rouge.JFCB
  turkuaz2018-01-18
```

**working cache** (`~/.llama/cache`, 968/1059 md_*.json items, the
selection-biased population production actually touches -- see
docs/2026-08-07-lma-census.md):
```
items_total=1059 items_with_kept_files=966
items_with_pure4_tag_title=1 pure4_tag_titles_total=1
distinct_pure4_values=1: 1922x1
items_with_2_or_more_pure4_titles=0
pure4_titles_equal_to_own_item_metadata_year=0 / 1
title_fraction crosses gather._RECOVER_BELOW (0.5)=0
title_fraction crosses to/from 1.0=1
  tbt2007-07-20.391.flac16
```
(`items_total=1059` counts every `md_*.json` in the directory; 968 of them
carry a distinguishable `md_` prefix stem matching the working-cache glob
used to size the population -- both figures point at the same directory,
not two different corpora.)

**Verdict, unchanged: zero STOP-qualifying items in either corpus -> global
scope stands**, now on two independently-measured bases.

## Finding 4 mutation (verbatim)
Applied `_YEAR_LIKE_NUMERIC = re.compile(r"\d{4}")` -> `re.compile(r"\d{4,}")`,
purged `__pycache__`, ran `./.venv/bin/pytest packages/llama/tests/test_titles.py -q`:
```
FAILED packages/llama/tests/test_titles.py::test_is_real_title_still_rejects_non_year_numeric_residue[19770101]
>       assert is_real_title(cleaned) is False
E       AssertionError: assert True is False
E        +  where True = is_real_title('19770101')
FAILED packages/llama/tests/test_titles.py::test_is_real_title_still_rejects_non_year_numeric_residue[12345]
>       assert is_real_title(cleaned) is False
E       AssertionError: assert True is False
E        +  where True = is_real_title('12345')
2 failed, 54 passed in 0.17s
```
Restored, re-ran full suite: 1567 passed again. Also re-verified the
original named acceptance mutation (revert the whole widening) still fails
`test_is_real_title_accepts_a_year_like_numeric_title` after all these
edits, byte-restored, full suite green again.

## Concerns
None outstanding. One self-reported, non-blocking discrepancy: my
independent re-derivation of the `_hygienic` "absorbed by `_date_norms`"
count is 162 against the reviewer's 163 (both against the same 181
pure-4-digit-canonical-item population); the number that drove the
decision -- 18 distinct items newly passing -- matches exactly between the
two independent measurements. Recorded explicitly in `titles.py`'s comment
rather than silently picking one.

---

# Fix round 2 (scoped re-review: all 7 round-1 findings ADDRESSED, 3 Minor remain)

## Status: DONE

Commit `e1c0be9` -- "titles: fix round 2 -- restore single-digit pinning, two
comment fixes" (on top of `076a990`). Small and final per the orchestrator's
framing; no predicate or scope change.

## Pointer guard
`PTH-GUARD: OK` re-checked at the start of this round.

## What changed, per finding

1. **Restored `"3"` to the negative parametrize** in
   `test_is_real_title_still_rejects_non_year_numeric_residue` (dropped in
   round 1's nit-trim on the mistaken belief it was redundant). Mutation
   proof: `_YEAR_LIKE_NUMERIC` -> `re.compile(r"\d{4}|\d")` (accepts every
   single digit) left all 1567 round-1 tests green -- nothing pinned
   single-digit rejection. Behaviour was never wrong
   (`is_real_title("3")` was always `False`); only the coverage regressed.
2. **Dropped the unsupported attribution** in `titles.py`'s `_hygienic`
   exposure comment. It had blamed the 162-vs-163 difference on
   approximating `_show_metadata_norms` off raw cache metadata; the
   re-reviewer got 162 under two independently built date-source
   approximations, so the number does not depend on that choice.
3. **Fixed the self-contradiction** in the same block: it called the 19
   newly-passing entries "not real songs" while two of them -- `1977`
   (MWatt2013-01-12) and `1662` (turkuaz2018-01-18) -- are the exact same
   real songs the comment establishes four lines earlier, in the tag-title
   census. Reworded so the "not a real song" claim covers the other 17
   entries (lineage/tour-tag/date-adjacent junk: `2448`, `2026`, `2020`,
   etc.), not all 19.

## Adjudication recorded, not re-derived
**162 is right, and 162-vs-163 was never a disagreement** -- entry-vs-item
granularity. 181 total pure-4-digit canonical-item ENTRIES minus 19
newly-passing ENTRIES = 162 (both entry-granularity, internally consistent).
181 minus 18 DISTINCT newly-passing ITEMS = 163 (mixes entry-count and
item-count denominators). `minutemen1984-07-14`, which carries 2 of the 181
entries (`2008` and `2021`), is the boundary case that separates the two
countings. My independent round-1 re-derivation (162) was correct throughout;
the earlier "1-item discrepancy, attributed to methodology" framing in this
report's round-1 section was itself an overclaim and is superseded by this
paragraph.

## Deferred, pre-existing, explicitly NOT fixed this round
`\d` matches Unicode digits: `is_real_title("١٩٧٧")`
(Arabic-Indic digits for "1977") is `True`. Verified:
```
>>> import re; s = "١٩٧٧"
>>> bool(re.compile(r"\d{4}").fullmatch(s))
True
```
Equally true of the pre-widening `^\d{4}$` -- not introduced by this task.
Recorded as a one-line comment above `is_real_title` in `titles.py`; out of
scope to fix here.

## Test command and output tail
`./.venv/bin/pytest -q` (after purging `__pycache__`):
```
1568 passed, 7 deselected, 26 warnings in 6.69s
```

## Suite-count delta, itemised (per the plan's new global constraint, `48d6d61`)

**Round 0 (`77478b9`) -> round 1 (`076a990`)**: 1568 -> 1567, net -1. Full
itemisation (owed retroactively; round 1's report entry only summarized it):
- REMOVED `"d1t02"` from
  `test_is_real_title_still_rejects_non_year_numeric_residue`'s parametrize
  -- subsumed by (duplicate of) the existing `("d1t02", False)` case already
  in `test_is_real_title`'s parametrize (line 98). No coverage lost: the
  same assertion on the same input already ran there.
- REMOVED `"12"` from the same parametrize -- subsumed by `"01"` in the same
  list: both inputs only exercise the letter-count-<3 branch on a 2-digit
  string, so `"01"` alone already covers that branch.
- ADDED `"19770101"` to the same parametrize -- new coverage, pins the upper
  bound (a longer digit run containing 4-in-a-row must not match).
- ADDED `"12345"` to the same parametrize -- new coverage, pins the
  one-digit-over boundary case.
- Net: 2 removed (both subsumed, zero coverage lost) - 2 added (new
  coverage, the upper bound) = round 1's own new coverage nets to +2, but
  round 1 ALSO trimmed the pre-existing `"12"` case's sibling `"3"` by
  mistake (see below) -- the net -1 in the total count is `"d1t02"` removed
  (subsumed, no loss) + `"12"` removed (subsumed, no loss) + `"3"` removed
  (NOT subsumed, real loss, corrected below) + `"19770101"` added +
  `"12345"` added = -3 removed, +2 added = -1.

**Round 1 (`076a990`) -> round 2 (`e1c0be9`)**: 1567 -> 1568, net +1.
- RESTORED `"3"` to
  `test_is_real_title_still_rejects_non_year_numeric_residue`'s parametrize.
  This one was mistakenly dropped in round 1 alongside `"d1t02"`/`"12"` under
  the same "nit" umbrella, but unlike those two it was NOT subsumed by
  anything else in the suite -- `"3"` is the only single-digit case anywhere
  in `test_titles.py`, and its removal left single-digit rejection entirely
  unpinned (proven by the `r"\d{4}|\d"` mutation passing clean in round 1).
  Restoring it is a straight net gain, not a rename or relocation.

## Concerns
None outstanding. All three round-2 Minor findings are comment/test-only
changes; no production logic touched beyond the already-shipped predicate
and pattern from round 1.
