# Task 2 — code-quality review

QUALITY: CHANGES REQUESTED

Pointer guard: `PTH-GUARD: OK`. All verification done on a copy at
`scratchpad/workc/t2-rev-qual`, shadowed via `PYTHONPATH` (sentinel-proved:
`llama.titles` resolved to the copy and carried a planted `SENTINEL_MARKER`),
run with `./.venv/bin/python -m pytest`, `__pycache__` purged before and after
each run. Worktree untouched, no commits.

## Verified good

- `_TRACK_NUM_PREFIX` (`\d{1,3}`) **untouched**; the diff shows only context
  lines around it. `test_clean_tag_titles_leaves_an_unnumbered_year_title_alone`
  and `test_clean_tag_titles_strips_once_never_loops` pass unchanged (57 passed
  in `test_titles.py` at baseline). The new predicate cannot interact with the
  prefix rule: a bare 4-digit string has no trailing `\s+\S`, so it was already
  out of that rule's reach — which is exactly what its comment claims.
- **The census is not an extraction failure.** Independently re-derived over the
  same corpus with my own script: 2,064 items with kept files yield **39,873
  cleaned tag titles, 33,640 non-empty**, and pure-digit titles at lengths
  1/2/3/4 = 1/43/3/2. The instrument plainly looked; "2" is a finding about the
  corpus, not silence. `filter_files(files, FORMAT_BY_AUDIO[k])` is a correct
  use of the documented `Sequence[str]` preference-list API, and `data["files"]`
  / `data["metadata"]` are the real cache schema keys.
- Commit message **does** state the test command and result
  (`./.venv/bin/pytest -q -> 1568 passed, 7 deselected`).
- Named acceptance mutation confirmed by me, not just claimed: reverting the
  widening fails `test_is_real_title_accepts_a_year_like_numeric_title`
  (`test_titles.py:117`), 1 failed / 56 passed.
- No scope creep: three files, all in the brief's list.

## Findings

### 1. Important — the census script self-invalidates; two of its headline numbers are now irreproducible
`scripts/numeric_title_census.py:112-113`. `old_frac = title_fraction(titles)`
calls the **live** `is_real_title`, and `new_titles_real` ORs the same live
predicate with the pure-4 test. Once the widening lands, old and new are the
same function, so both crossing counters are structurally pinned to 0.

Verified: re-running the committed script on the committed source prints
`title_fraction crosses to/from 1.0=0`, where `task-2-report.md` records **2**.
A future reader re-running the script to check the constant's provenance gets a
different answer with no error — the failure mode this repo's citation
convention exists to prevent.

Change: define the pre-widening predicate locally in the script and use it for
the "old" side, e.g.

```python
def _old_is_real_title(t: str) -> bool:   # the pre-2026-09-02 rule, frozen
    return sum(ch.isascii() and ch.isalpha() for ch in t) >= 3
old_frac = (sum(map(_old_is_real_title, titles)) / len(titles)) if titles else 0.0
```
and drop `title_fraction` from the imports. Then note in the script's docstring
that it is a frozen before/after instrument, not a live one.

### 2. Important — the scope decision was made on the tag population, but "global" also opens the pipeline's *only silent adopter*, whose population was never measured
`titles.py:36-41`. `is_real_title` has three call sites, not one:
`resolve_titles` (tag rung), `gather._sibling_titles`/`_recover_format_titles`
(via `title_fraction`), and — the one that matters —
`structure._hygienic` (`structure.py:1104`), whose own docstring says
"**this is the only silent adopter in the pipeline**". `_hygienic` filters
**canonical setlist items**, not tag titles, and that population is far denser
in date-shaped strings.

Measured by me over the same 2,095-item iacache corpus, using `parse_setlist`:

```
parsed descriptions 2052, canonical items 48031
pure-4-digit canonical items: 181 on 171 items
  == item's own year (already vetoed by _date_norms): 163
  caught by is_junk_title:                              0
  SURVIVE every other _hygienic clause -> newly adoptable: 18
```
The 18 include `2448` (out of a `flac2448` lineage string),
`2026` on a 2025 show, `2020` on a 1994 show, `2008`/`2021` on a 1984 show —
lineage/date junk, not song titles. It is an upper bound on *newly-passing
items*, not on adoptions (a gap must also be count-forced and anchored), and the
`_date_norms` clause is doing real work by absorbing 163 of the 181. But the
brief's STOP condition — "a taper's year stamp getting promoted" — is *denser*
in the population the census skipped than in the one it measured, and the
commit message's "**safe corpus-wide**" is not supported by a tag-only census.

This is not a request to re-scope: the spec deliberately wants TBT's `1922`
adopted via `setlist-gap`, which requires `_hygienic` to accept it. The ask is
that the constant's comment and the commit line stop over-claiming and record
the second population as a sized, accepted exposure — one sentence, e.g.
"tag titles only; the same predicate also gates `structure._hygienic`, where
181/48,031 canonical items are pure-4-digit and 18 survive that function's other
clauses (the rest are absorbed by `_date_norms`) — accepted, since the
`setlist-gap` adoption of `1922` is the intended composition." Numbers above are
reproducible with the script in the log.

### 3. Important — the constant comment names the corpus but omits its provenance caveat
`titles.py:26-35` says "the 2,095-item iacache corpus" (good) but not that it is
a `random.shuffle(seed=7)` decade-stratified sample of archive.org **items**,
not a rate over shows llama would select. Both neighbouring measured constants
carry exactly that caveat (`LOSSLESS_TITLE_FORMATS` in `junk.py:31-37`, the
junk-duration block). Unlabelled, "2 of 2,095" reads as an archive-wide rate.
Change: append the one-line standing caveat, matching `junk.py`'s wording.

### 4. Important (test hygiene) — the widening's UPPER bound is unpinned
Mutation run on my copy: `_YEAR_LIKE_NUMERIC = r"^\d{4}$"` -> `r"^\d{4,}$"`
leaves **all 57 tests in `test_titles.py` green**. That mutation admits
`is_real_title("19770101")` — a bare `yyyymmdd` date stamp, precisely the junk
class the function exists to reject, straight into the most-trusted rung. Every
new negative case (`01`, `174`, `12`, `3`) constrains only the *lower* bound
(confirmed: `^\d{2,4}$` fails 3 of them).
Change: add `"19770101"` and `"12345"` to
`test_is_real_title_still_rejects_non_year_numeric_residue`'s parametrize list.
(Optional, same defect one layer down: `_YEAR_LIKE_NUMERIC.match` with a `$`
anchor also accepts `"1922\n"`; `re.fullmatch(r"\d{4}", cleaned)` states the
intent exactly and removes the trailing-newline hole.)

### 5. Minor — the report's stale-reference survey is incomplete, and the deferral is right only for the half it found
The deferral itself is **correct**: `test_correspondence.py:346-348` is a
docstring, its assertions never touched `is_real_title`, and the file is outside
Task 2's list — Task 5/7 owns it.
But the report states that is the only stale reference. It is not:
`packages/llama/src/llama/correspondence.py:107-108` — a **production module
docstring**, and the stated justification for `--suggest-titles`' residual value
— now asserts something false about shipped behaviour:
"the canonical item `1922`, which `is_real_title` rejects (no three ASCII
letters) and `setlist-gap` therefore refuses to adopt."
(`correspondence.py:204` is fine — the DP does still agree with the forced gap.)
Change: no edit needed in Task 2; add both sites to Task 5/7's checklist and
correct the claim in `task-2-report.md` so the next owner isn't working from a
survey that missed the source file.

### 6. Nit — redundant parametrize cases
`test_titles.py:120-126`: `"d1t02"` duplicates the case already in
`test_is_real_title` at line 97, and `"12"` is subsumed by `"01"` (both only
constrain `\d{2,}`). Harmless; trim if touching the file for finding 4.

## Test-hygiene section — what edit makes each new test fail?

Six new test cases, one function + five parametrize cases. All verified by
mutation on my copy, not by reading.

| test | source edit that fails it | status |
|---|---|---|
| `test_is_real_title_accepts_a_year_like_numeric_title` (`:112`) | revert the `or bool(_YEAR_LIKE_NUMERIC.match(...))` clause | **binding** (verified: 1 failed / 56 passed) |
| `...still_rejects_non_year_numeric_residue["01"]` | `^\d{4}$` -> `^\d{2,4}$` | **binding** (verified) |
| `..."12"` | same as `01` | binding but **redundant** with it |
| `..."174"` | `^\d{4}$` -> `^\d{3,4}$` (or `\d{2,4}`) | **binding** (verified) |
| `..."3"` | `^\d{4}$` -> `^\d+$` | binding (subsumed by the two above) |
| `..."d1t02"` | any change letting a letter+digit mix through | binding, but **duplicates** `test_is_real_title[d1t02]` at `:97` |

None hollow. The gap is not a hollow pin but an **unpinned direction**: nothing
in the file constrains the upper bound (finding 4), so `^\d{4,}$` ships green.

## What I would need to approve
Findings 1, 3 and 4 are small, local edits (script, comment, parametrize list).
Finding 2 is a comment/commit-claim correction, not a redesign. Finding 5 is a
report correction plus a note handed to Task 5. None require re-running the full
suite beyond `test_titles.py`.
