# Task 2 — SPEC COMPLIANCE REVIEW

# SPEC ❌

The code change is correct and the **global** ruling is the right one — I re-derived it
independently and it survives. What fails is the *evidence*: the census numbers recorded in
the constant's comment are provably wrong (2 items, should be 3), and one arm of the script
cannot reproduce its own recorded output against the committed tree. In a codebase whose
discipline is "constants pinned by a cited measurement", a wrong cited number in the constant's
comment is the defect the discipline exists to prevent. Fix is comment + script only; **the
one-line widening and the global scope should stand as committed.**

`PTH-GUARD: OK` (worktree, before anything else).

## Per-requirement

| Brief requirement | Verdict | Location |
|---|---|---|
| Step 1: census script walks cache; per-item + total `^\d{4}$` after `clean_tag_title`; distinct values; `_RECOVER_BELOW`/1.0 crossings; cite-style output | **PARTIAL** — all arms present, two defective (F1, F2) | `scripts/numeric_title_census.py` (new, 157 ln) |
| Step 2: run it, record output, apply decision rule | **MET (ruling) / PARTIAL (evidence)** | report §"Census output"; ruling re-derived correct below |
| Step 3: failing tests `1922`/`2001` True, `d1t02`/`01`/`174` False | **MET** | `test_titles.py:+104..+134`, both new tests; TDD failure output in report |
| Step 3: pinned tests pass **untouched** | **MET** | `git diff fd0f92d..77478b9 \| grep -E '^[-+].*(unnumbered_year_title_alone\|strips_once_never_loops)'` → **NONE**. Diff adds only two `def test_` lines, removes none. |
| Step 4: implement per scope; full suite green | **MET** | 1568 passed / 7 deselected in my shadowed copy, matching the report |
| `_TRACK_NUM_PREFIX` `\d{1,3}` not widened to `\d+` | **MET** | appears as unchanged context only; grep for `^[-+].*_TRACK_NUM_PREFIX` → NONE |
| Census numbers in constant's comment, house citation style (script + date + numbers) | **NOT MET** — style is right, numbers are wrong and unqualified (F1, F3) | `titles.py:24-35` |
| Named mutation kills `test_is_real_title_accepts_a_year_like_numeric_title` | **MET** | see Mutation evidence |
| Composition note honored, not "fixed" | **MET** | no correspondence/setlist-gap code touched; I confirmed `_hygienic("1922")` is now `True`, i.e. the erasure is real and accepted |
| YAGNI | **MET** | production delta is 1 predicate + 1 regex; script extras (`--sample`, own-year match) are each demanded by the brief's STOP rule |

## Findings

### F1 — Important. The census misses one of the three real items, and misses it on the exact rung the widening most affects.
`census()` tries formats `("mp3", "flac")` and **breaks on the first non-empty kept set**. That
hides any pure-4-digit title carried only by the lossless copy. An independent raw scan of all
2,095 items for `^\d{4}$` titles finds **three** items, not two:

```
MWatt2013-01-12                     '1977'   (Flac + VBR MP3)
mwatt2012-05-02.Poisson_Rouge.JFCB  '1970'   (Flac + VBR MP3)
turkuaz2018-01-18                   '1662'   (Flac ONLY)   <-- census never saw it
```

`turkuaz2018-01-18` is not an edge case to wave off — it is the `sibling-format` recovery case
in its purest form. Measured with the real `filter_files`/`clean_tag_titles`:

```
turkuaz2018-01-18  mp3   n=13  title_fraction 0.000   (every mp3 tag title is empty)
turkuaz2018-01-18  flac  n=13  title_fraction 0.923 -> 1.000 with the widening
```

mp3 0.000 is below `gather._RECOVER_BELOW` (0.5) and flac 0.923 is above
`_RECOVER_SIBLING_ABOVE` (0.9), so recovery **fires** and `1662` reaches the tag rung in
production. The census computed `title_fraction` on the empty mp3 side and reported nothing.
Corrected figures: **3 items / 3 pure-4-digit titles / 3 distinct values**, not 2/2/2.

Re-running the STOP rule on the corrected population: still **zero** items with >=2 such titles;
`1662` != that item's year (2018) and sits among Turkuaz originals in an otherwise fully-titled
flac setlist. **Global scope remains the correct ruling** — the implementer got the right answer
from an incomplete instrument. The comment's numbers need correcting, not the code.

### F2 — Important. The `crosses` arm is self-invalidating; the committed script cannot reproduce the committed report.
`old_frac = title_fraction(titles)` calls the live `is_real_title`, which is the very thing this
commit mutates. Re-running the committed script against the committed tree reproduces **every
line except one**:

```
recorded in task-2-report.md:  title_fraction crosses to/from 1.0=2
re-run now (same corpus):      title_fraction crosses to/from 1.0=0
```

The `crosses` measurement is only obtainable pre-widening and is dead as committed. (I computed
the honest pre-widening value with a local letters-only predicate: **3** items cross 1.0 — the
two Watt items and turkuaz — so even the recorded 2 was low, by the same F1 cause.) The script
should hold its own letters-only baseline rather than calling the function under test. Worth
noting the crossing number is *not* in `titles.py`'s comment, so F2 pollutes the report/ledger
rather than the source.

### F3 — Important. The cited number names its corpus but carries no stratified-sample caveat.
`titles.py:25-26` says "over the 2,095-item iacache corpus". Per the orchestrator's correction
(and `docs/2026-08-07-lma-census.md` + the `LOSSLESS_TITLE_FORMATS` comment in `junk.py`, which
does carry it), `iacache` is a **decade-stratified sample, not a rate over shows llama would
select**. An unqualified "2 of 2,095" in a constant's comment will be read as an archive-wide
rate by the next person. Same omission in the new test's docstring. I did **not** file the
iacache-vs-`~/.llama/cache` population difference as a defect — confirmed settled: working cache
answers Task 1's "did anything llama gathered change", stratified sample answers Task 2's "how
common is this in the wild"; both corpora are right for their question.

### F4 — Important. A second stale `is_real_title("1922")` reference exists, in **production source**, and was not disclosed.
The report flags only `test_correspondence.py:348`. The load-bearing one is
`packages/llama/src/llama/correspondence.py:105-110` — the docstring that states the *entire
residual value* of `llama fix --suggest-titles` over the `setlist-gap` rung:

> "`trampledbyturtles-2007-07-20` track 21 is a count-forced, two-side-anchored gap over the
> canonical item `1922`, which `is_real_title` rejects (no three ASCII letters) and
> `setlist-gap` therefore refuses to adopt."

Verified now false on both clauses: `is_real_title("1922") is True` and `_hygienic("1922", set())
is True`, so `setlist-gap` no longer refuses. **Deferring the edit is correct** — both files are
outside the brief's named file list and the brief routes this composition to Tasks 5/7 — but a
production docstring asserting a false justification for a shipped command is a live
inconsistency, not cosmetic, and must be carried into Task 5/7 as an explicit item covering
**both** sites. Judgement on the implementer's deferral: right call, incomplete disclosure.

### F5 — Note (favourable). No gate flips anywhere.
I measured all three items against `_RECOVER_BELOW` (0.5) and `_RECOVER_SIBLING_ABOVE` (0.9):
**zero crossings at either threshold**; only 1.0 crossings. Total measured production effect of
this change across 2,095 items: 3 titles become usable, no recovery-gate behaviour changes. The
blast radius is genuinely as small as claimed.

### F6 — Note. The widening has exactly one test holding it.
The mutation kills one test and nothing else in 1568. Expected (the brief names this mutation and
defers the downstream expectation to Task 7's six-show table) — recorded so it is not mistaken
for redundant coverage.

## Census-validity (how I proved the instrument can return non-empty)
Three independent controls, because "2 out of 2,095" is exactly the shape of a census that never
looked:
1. **Schema check.** The field the script reads (`files[].title`) exists and is populated:
   1,962 of 2,095 items carry >=1 audio-file `title`; 73,837 of 82,556 audio file entries have
   one. Not an extraction failure.
2. **Planted positive control.** Built a synthetic two-item cache and ran the *committed,
   unmodified* script against it. It reported both items, the correct distinct values, tripped
   `items_with_2_or_more_pure4_titles=1` on the planted STOP item, and correctly matched a
   planted date-stamp against `metadata.year` (`1970/1970 True`). Every arm the decision rests
   on fires when there is something to find.
3. **Independent oracle.** A from-scratch regex scan over every file entry in the corpus,
   sharing no code with the script, found the two reported items **and one more** — which is F1.
   The instrument works; its format-selection loop is too narrow.

**Outcome: the "2" is a real reading of a slightly-too-narrow instrument, not a silent zero.**

## Mutation evidence
Copy at `.../workc/t2-rev-spec/copy` (rsync of the worktree, `.venv` excluded; worktree never
written). Shadowing proven **before** trusting anything: a planted `_SENTINEL_T2REV` resolved to
the copy under `PYTHONPATH` and to `ABSENT-WORKTREE-WINS` without it; a planted failing test in
the copy's `test_titles.py` went red under `python -m pytest`, confirming collection from the
copy. `__pycache__` purged before and after every run. No `pip`, no `.venv/bin/*` console script.

Command:
```
# revert the widening in the copy: restore `return sum(...) >= 3` (drop the `or _YEAR_LIKE_NUMERIC` arm)
cd <copy> && PYTHONPATH=<copy>/packages/llama/src:<copy>/packages/herder/src:<copy>/packages/emcee/src \
  /Users/shawn/projects/llama/.worktrees/sibling-transfer/.venv/bin/python -m pytest -q
```

Test that went red — name matches the brief exactly:
```
FAILED packages/llama/tests/test_titles.py::test_is_real_title_accepts_a_year_like_numeric_title
>       assert is_real_title("1922") is True
E       AssertionError: assert False is True
E        +  where False = is_real_title('1922')
1 failed, 1567 passed, 7 deselected, 26 warnings in 6.30s
```
Restored (`diff` vs `git show HEAD:...titles.py` byte-identical) and re-ran: **1568 passed,
7 deselected**. The acceptance mutation is real.

## Required to clear ❌
1. Correct `titles.py`'s comment (and the new test's docstring) to **3 items / 3 titles /
   3 distinct values (`1977`, `1970`, `1662`)**, naming the third item and why it was missed.
2. Add the stratified-sample caveat to the citation (F3).
3. Fix the census's format walk to consider every delivery + lossless-title format rather than
   first-non-empty mp3, and give the `crosses` arm its own letters-only baseline so the script
   reproduces its numbers against the post-change tree (F1, F2). Re-run and record.
4. Carry F4 forward as an explicit Task 5/7 item naming **both** stale sites, the production
   docstring first.

None of these touch the shipped predicate or the global ruling.
