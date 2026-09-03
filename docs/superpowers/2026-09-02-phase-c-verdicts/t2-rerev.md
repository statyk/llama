# Task 2 fix round 1 — scoped re-review

Pointer guard: `PTH-GUARD: OK`. Worktree HEAD `06d526e` (one docs-only commit past
`076a990`; `git diff --stat 076a990..06d526e` touches only
`docs/superpowers/plans/2026-09-02-sibling-title-transfer.md`). All mutation work done on a
copy at `.../scratchpad/workc/t2-rerev`, shadowed via `PYTHONPATH` and proven with a planted
`SENTINEL_MARKER` (copy resolved to the copy's `titles.py`, worktree resolved to its own,
sentinel `ABSENT` there). No commits, no writes to the worktree.

## Finding Verdicts

### 1. Census missed a third item (`turkuaz2018-01-18` / `1662`) — **ADDRESSED**

Verified with an oracle that shares no code with the census: a raw walk of all 2,095 iacache
JSONs, no `llama` imports at all, matching `re.fullmatch(r"\d{4}")` against every audio file's
raw `title` field, no junk filtering and no format preference. Result: exactly **3** items.

```
MWatt2013-01-12                     [('1977','Flac'), ('1977','VBR MP3')]
mwatt2012-05-02.Poisson_Rouge.JFCB  [('1970','Flac'), ('1970','VBR MP3')]
turkuaz2018-01-18                   [('1662','Flac')]
```

Re-run with `llama.titles.clean_tag_title` applied (still no junk filter, still all formats):
same 3 items, same 3 values. Targeted check of `md_turkuaz2018-01-18.json`: 14 `VBR MP3`
files, **0** with a non-empty title; 14 tagged `Flac` files, one of which is
`...t10.flac` / title `1662`, amid real titles (`The Mountain`, `Murder Face`,
`Twenty Dollar Bill`, …). So `1662` is genuinely flac-only and was genuinely invisible to the
first census's break-on-first-non-empty-KEPT walk.

The committed script now reproduces it (run against the post-change tree,
`scripts/numeric_title_census.py`): `items_with_pure4_tag_title=3
pure4_tag_titles_total=3 distinct_pure4_values=3: 1977x1, 1970x1, 1662x1`, with turkuaz's
source column reading `{'recovered-via:mp3': ['1662'], 'tags:flac': ['1662']}` — i.e. the
recovery path is exercised, not just the direct-tag path. Corrected figures 3/3/3 confirmed.

`_frozen_recover` (`scripts/numeric_title_census.py:85-101`) is a faithful reimplementation
of `gather._recover_format_titles` (`stages/gather.py:127-142`): same `_RECOVER_BELOW` early
return, same `LOSSLESS_TITLE_FORMATS` loop, same `ordering.get("format")` skip, same
`sibling_format_titles` + `_RECOVER_SIBLING_ABOVE` gate, same `filter_files(files,
want_format=fmt)` signature (`junk.py:179-181` accepts `str | Sequence[str]`).

### 2. Self-invalidating `crosses` arm — **ADDRESSED**

`grep -n is_real_title scripts/numeric_title_census.py` returns only docstring mentions plus
the two local definitions (`_old_is_real_title:73`, `_new_is_real_title:79`) and their five
call sites. Nothing imports `llama.titles.is_real_title`; the import line now pulls only
`clean_tag_titles, sibling_format_titles`.

The decisive test — run the committed script against the **post-change** tree, where the old
arm would have been pinned to 0:

```
title_fraction crosses gather._RECOVER_BELOW (0.5)=0
title_fraction crosses to/from 1.0=3
  MWatt2013-01-12
  mwatt2012-05-02.Poisson_Rouge.JFCB
  turkuaz2018-01-18
```

Non-zero and matching the committed report exactly. The frozen predicate is load-bearing:
the production `title_fraction` (`titles.py:172-174`) calls the live `is_real_title`, so a
script reusing it really would have collapsed old==new.

### 3. Missing stratified-sample caveat — **ADDRESSED**

`titles.py:64-67` reads "Standing caveat: iacache is a random.shuffle(seed=7)
decade-stratified sample of archive.org ITEMS (see junk.py's LOSSLESS_TITLE_FORMATS comment
for the same caveat verbatim), so this is a rate over cached items, not over shows llama
would actually select." Compared against `junk.py:32-35`: same wording, same
seed/stratification/rate-over-cached-items claims, with `iacache` substituted for "that
cache". The working-cache cross-check is separately recorded at `titles.py:69-88` and cites
`docs/2026-08-07-lma-census.md`.

### 4. Upper bound unpinned — **ADDRESSED** (independently mutation-verified)

Applied the mutation myself on the copy: `_YEAR_LIKE_NUMERIC = re.compile(r"\d{4}")` ->
`re.compile(r"\d{4,}")` at `titles.py:24`, purged `__pycache__`, ran
`packages/llama/tests/test_titles.py`:

```
FAILED packages/llama/tests/test_titles.py::test_is_real_title_still_rejects_non_year_numeric_residue[19770101]
>       assert is_real_title(cleaned) is False
E       AssertionError: assert True is False
E        +  where True = is_real_title('19770101')
FAILED packages/llama/tests/test_titles.py::test_is_real_title_still_rejects_non_year_numeric_residue[12345]
2 failed, 54 passed in 0.11s
```

(assertion at `packages/llama/tests/test_titles.py:140`.) The named acceptance mutation was
re-verified too: removing the numeric arm entirely reds
`test_is_real_title_accepts_a_year_like_numeric_title` (`test_titles.py:126`), 1 failed /
55 passed.

**Anchoring genuinely holds**, checked directly against the shipped predicate rather than
inferred from a green suite:

```
'1922' True   '2001' True
'x1977' False  '1977x' False  ' 1977' False  '1977 ' False  '1977\n' False
'19770101' False  '12345' False  '3' False  '01' False  '174' False  '' False
```

`fullmatch` closes the trailing-newline hole `^\d{4}$` had (`'1977\n'` would have matched
under the old anchors); prefix and suffix contamination are both rejected.

### 5. `_hygienic` exposure unsized — **ADDRESSED**, with the numeric discrepancy adjudicated below

Independently re-measured over the same iacache corpus (`parse_setlist` over every item
description, `_date_norms` from `stages/gather.py`, `fuzzy_norm_title` for the comparison):

```
items=2095 parsed_descriptions=2052 pure4_canonical_items=181
absorbed_by_date_norms=162 junk=0 newly_passing_entries=19 distinct_items=18
```

The 19 entries / 18 distinct items I get are **identical, item for item and value for value**,
to the list enumerated at `titles.py:96-114`, including `minutemen1984-07-14` carrying two
(`2008`, `2021`).

**Ruling on 162 vs 163: 162 is right, and the difference is an entry-vs-item granularity
artifact, not a measurement disagreement.** The population is 181 *entries*. 181 − 19
entries = **162**; 181 − 18 *distinct items* = **163**. The one item carrying two values
(`minutemen1984-07-14`) is exactly the boundary that makes those two subtractions differ by
one, and both parties already agree the passing set is "19 entries on 18 items". So the
reviewer's 163 is arithmetically consistent with subtracting the distinct-item count from an
entry-level total.

Two consequences worth recording:
- The **number the comment commits to (162) is correct**, and the decision-driving figure
  (18/19 newly passing) is confirmed by a third independent measurement.
- The comment's **attribution** of the discrepancy is not supported. `titles.py:86-89`
  blames "approximating `_show_metadata_norms` off raw cache metadata rather than a real
  `Candidate`/`events` pair". I ran the measurement under two different date-source
  approximations (`metadata.date` only; and `metadata.date` with identifier-embedded-date and
  `metadata.year` fallbacks) and got **162 under both** — the date-source approximation moves
  nothing here. Minor documentation inaccuracy, not a wrong number.

On the dispatch's two structural requirements: the enumeration is complete (18 lines covering
all 19 values, verified against my list), and the measured-vs-bound statement is in one
sentence — `titles.py:118`: "THIS 18/19 IS AN UPPER BOUND ON EXPOSURE, NOT THE EXPOSURE:
passing `_hygienic` is necessary but not sufficient for a title to ship". **"A mechanism each"
is not met**: `titles.py:115-118` gives three exemplar mechanisms (`2448` from a `flac2448`
lineage fragment, `2026` on a 2025 show, `2020` on a 1994 show) plus a general
characterization, not a per-item mechanism for all 18. Minor, non-blocking — the finding as
originally raised asked for sizing and enumeration, both of which are delivered.

### 6. Two stale `is_real_title("1922")` references — **ADDRESSED**

`correspondence.py:105-120` (production module docstring) now states the old claim explicitly
as false and gives the current behaviour; `test_correspondence.py:346-356` likewise.
Repo-wide grep for `is_real_title("1922")` returns three hits, all correct: the two corrected
comments and `test_titles.py:126`'s `assert is_real_title("1922") is True`. No stale claim
survives.

Spot-checked the corrected claim rather than taking it on trust:
`is_junk_title("1922")` is `False`, and `_hygienic("1922", _date_norms("2007-07-20"))` is
`True` (while `_hygienic("2007", ...)` is `False` — the `_date_norms` veto still bites on the
show's own year). So the docstring's new assertion is accurate.

### 7. Cross-population check over the working cache — **ADDRESSED**

Re-ran the committed census against `~/.llama/cache` and reproduced the report exactly:

```
items_total=1059 items_with_kept_files=966
items_with_pure4_tag_title=1 pure4_tag_titles_total=1
distinct_pure4_values=1: 1922x1
items_with_2_or_more_pure4_titles=0
title_fraction crosses to/from 1.0=1
  tbt2007-07-20.391.flac16
```

`ls ~/.llama/cache/*.json | wc -l` = 1059, `md_*.json` = 968 — the report's reconciliation of
those two figures to one directory is correct. One occurrence, below the >=2-on-one-item STOP
threshold, item year 2007 != 1922. Both corpora support global scope.

## Additional Finding (not in the original list) — the `"3"` coverage question

**Confirmed, and the orchestrator's split reading is exactly right on both halves.**

- `d1t02` needs no action: it is retained at `packages/llama/tests/test_titles.py:98` inside
  `test_is_real_title`'s parametrize (line 96-99 reads `("Deal", True), ("Jam", True),
  ("Here Comes Sunshine", True), ("d1t02", False), ("", False), ("A B", False)`), with the
  cross-reference at line 138 pointing there. Correct relocation, documented in source.
- `"3"` is genuinely uncovered: `grep` for a `"3"` case across the whole file returns nothing.
  The line-96 list has no single-digit entry, and the line-130 negative parametrize is
  `["01", "174", "19770101", "12345"]`.

I did not stop at reading. **Mutation evidence that the pin loss is real:**
`_YEAR_LIKE_NUMERIC = re.compile(r"\d{4}|\d")` — a predicate that accepts every single digit
as a real title — passes `test_titles.py` (56 passed) **and the entire suite**:

```
1567 passed, 7 deselected, 26 warnings in 6.32s
```

So nothing anywhere pins single-digit rejection. Restored and re-verified afterwards.

Severity: **Minor**. Shipped behaviour is unchanged (`is_real_title("3")` is `False`, checked
directly above), and the realistic mutations of this constant — `\d{1,4}`, `\d{2,4}` — are all
caught by the retained `"01"`. Only a disjunctive predicate slips through. But this phase is
being strict about lost pinning, so: **restore `"3"`**. Adding it to the line-130 negative
parametrize is the right place — that test asserts `is_real_title(cleaned) is False` directly,
which is the predicate in question, and it is where the other pure-digit lower-bound cases
already live. (The dispatch asked me to confirm the restored case lands in a parametrize that
exercises the predicate: line 130's does, via `assert is_real_title(cleaned) is False` at line
140 — the same assertion that caught my `\d{4,}` mutation.) One line.

## New Breakage in the Fix Diff

**None** at Critical or Important.

Minor, all non-blocking:
- `scripts/numeric_title_census.py:170-175` — the recovery-side `crosses_1_0` increment fires
  only when *both* `rec_old` and `rec_new` are non-`None`. A case where recovery newly fires
  and lands at 1.0 is counted under `crosses_0_5` instead (the code comments this
  deliberately). No effect on the reported numbers; all three iacache crossings are direct-tag.
- `titles.py:115-118` characterizes the exposure shape as "lineage/tour-tag/date-adjacent
  junk, not real songs", while the same comment block's own census section establishes that
  `1977` (MWatt) and `1662` (turkuaz) — both members of the 19 — are real song titles. Mild
  internal tension in the prose; the "upper bound" framing above it is what carries the
  argument, and a real title adopted is not the harm being sized.

## Out-of-Scope Observations

- `\d` in Python matches Unicode decimal digits, so `is_real_title("١٩٧٧")` (Arabic-Indic) is
  `True`. Pre-existing in the pre-fix `^\d{4}$` form too — **not introduced by this fix diff**,
  and of no practical consequence for archive.org tag titles. Noted only so it is not
  rediscovered as a regression later.

## Verdict

**Fix round: all seven findings ADDRESSED, no new Critical/Important breakage.**

One outstanding item, raised by the orchestrator and confirmed here with suite-wide mutation
evidence: restore `"3"` to `test_titles.py:130`'s negative parametrize (one line). Plus two
optional Minor documentation touch-ups if that round is opened anyway — the 162-vs-163
attribution at `titles.py:86-89` (the cause is entry-vs-item granularity, not metadata
approximation) and the "not real songs" phrasing at `titles.py:115-118`.
