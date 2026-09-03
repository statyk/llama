# ADDENDUM 2026-09-02 — invocation correction, full re-verification, and a venv incident

The orchestrator flagged that `./.venv/bin/pytest` run from an out-of-worktree
copy tests the worktree, not the copy. Confirmed here: the copy's
`.venv/bin/pytest` carries the absolute shebang
`#!/Users/shawn/projects/llama/.worktrees/sibling-transfer/.venv/bin/python3.14`.

**Every mutation result in this report has been re-run with
`./.venv/bin/python -m pytest` from the copy root, `__pycache__` purged before
and after each run, against source extracted from the commits under review
(`git show 852e47d:...`). Every result reproduced identically — nothing in the
original report is void, and no finding changed.** Import target verified
immediately before the runs: `llama.junk.__file__` =
`/private/tmp/.../workc/t1-rev-qual/packages/llama/src/llama/junk.py`.

Re-verified table (all `./.venv/bin/python -m pytest -q`, committed state
852e47d, baseline `1560 passed, 7 deselected`):

| Mutant | Result |
|---|---|
| A — dedupe moved below the play-order block | **1560 passed** (unpinned) |
| D — dedupe applied to raw `files` before `_keep_and_exclude` | **1560 passed** (unpinned) |
| B — key drops duration (`key = (base, 0)`) | 1 failed: `test_same_basename_different_duration_both_kept` |
| C — `list(winners.values())`, drop `order` | 1560 passed (redundancy confirmed) |
| E — invert titled-copy preference | 1 failed: `test_duplicate_listing_keeps_the_titled_copy` |
| F — return `dict(...)` copies | 1 failed: `test_clean_item_byte_identical_through_filter_files` |
| G — rename reason to `"duplicate"` | 1 failed: `test_duplicate_listing_keeps_the_titled_copy` |
| H — delete the dedupe call entirely | 1 failed: `test_duplicate_listing_keeps_the_titled_copy` |

Why my earlier `./.venv/bin/pytest` runs happened to be valid anyway: see the
incident below — an accidental editable reinstall had repointed the worktree
venv at my copy, so the worktree interpreter was importing the copy's source.
That is luck, not method; the `-m pytest` form above is the record.

## The Important finding is already being addressed in the working tree

The worktree now carries **uncommitted** changes (`M junk.py`, `M test_junk.py`)
that add `test_dedupe_runs_before_play_order_derivation` and
`test_dedupe_runs_after_junk_filtering`, plus the docstring text from Minor 3
and the sweep-provenance line from Minor 4. Re-verified against that working
state (`./.venv/bin/python -m pytest`, baseline `1562 passed`):

- mutant A → `1 failed: test_dedupe_runs_before_play_order_derivation`
- mutant D → `1 failed: test_dedupe_runs_after_junk_filtering`

So Important #1, Minor #3 and Minor #4 are closed once those changes are
committed. **Still open:** Minor #2 (`order` bookkeeping is dead weight —
mutant C is still green), Minor #5 (cross-directory key vs
`titles._stem_no_ext`'s documented rule), Minor #6 (third test's name and
duplicated name literal), Minor #7 (sweep's `n_pairs` / skipped count).

## Incident: I briefly repointed the worktree's venv at my copy — now clean, one metadata residue

Cause, and it is sharper than the pytest hazard: **`./.venv/bin/pip` in a copied
tree has the same absolute worktree shebang**, so my
`./.venv/bin/pip install -e packages/herder -e packages/llama --no-deps`,
run from the copy to make the copy self-contained, instead rewrote the
**worktree** venv's `_editable_impl_llama_herder.pth` and
`_editable_impl_llama_radio.pth` to point at my scratch copy. For roughly
fifteen minutes, anything importing `llama` or `herder` through the worktree's
venv was importing my scratch tree.

Status now: **repaired** (not by me — my `sed` repair was refused by the
permission classifier, and I did not work around it). All three `.pth` files
read the worktree paths again, and
`./.venv/bin/python -c "import llama.junk, herder, emcee"` resolves all three to
`/Users/shawn/projects/llama/.worktrees/sibling-transfer/...`. I also
resynced my copy's `packages/*/src` to the worktree's current content so any
lingering pointer would have been harmless.

One residue remains, metadata only, no effect on imports: two dist-info files
still record my scratch path as the install origin —
`.venv/lib/python3.14/site-packages/llama_radio-0.1.0.dist-info/direct_url.json`
and `llama_herder-0.1.0.dist-info/direct_url.json`. Normalize with, from the
**worktree root**:
`./.venv/bin/pip install -e packages/herder -e packages/llama --no-deps`.

Lesson for the team, worth a line in the worktree note in CLAUDE.md: in a
copied tree, **neither `.venv/bin/pytest` nor `.venv/bin/pip` is safe** — both
are console scripts with an absolute shebang pointing back at the original
venv. `python -m <tool>` is the only form that follows the copy, because
`.venv/bin/python` is a symlink whose venv is resolved from its own location.

---

QUALITY: CHANGES REQUESTED

Task 1 (`filter_files` duplicate-listing dedupe), commits `98d752a..852e47d`.
The implementation is correct, small, well-placed and honestly measured; the
sweep's headline finding holds up under independent verification. One
Important gap: the two placement facts the brief calls load-bearing are not
pinned by any test — I moved the dedupe in both forbidden directions and the
full 1560-test suite stayed green.

All mutation results below were produced on a shadow-proven copy at
`/private/tmp/.../scratchpad/workc/t1-rev-qual` (its venv `.pth` files were
repointed at the copy, verified by `llama.junk.__file__`, and confirmed by a
sentinel edit that turned 22 test_junk tests into 21 failures). `__pycache__`
purged before and after every run. The worktree was not modified
(`git status --porcelain` empty).

---

## Important

### 1. Both placement invariants are unpinned — `packages/llama/src/llama/junk.py:212`

The brief states two ordering constraints: the dedupe runs *after*
`_keep_and_exclude` for the winning format, and *before* play-order
derivation. Neither survives mutation:

- **Mutant A** — move the two-line dedupe block from junk.py:212 to just
  above `return kept, excluded, ordering` (i.e. play order derived from the
  *un*-deduped list): `./.venv/bin/pytest -q` → `1560 passed, 7 deselected`.
  This is a real behaviour change, not a no-op: with duplicates present the
  track-tag numbers are non-unique, so `ordering["order_source"]` silently
  degrades from `track-tags` to `filename` on exactly the items this feature
  targets.
- **Mutant D** — dedupe the raw `files` list at the top of `filter_files`,
  before format selection and `_keep_and_exclude`: `1560 passed`. Real risk
  here too: a junk copy (unknown provenance / convention mismatch) carrying a
  title would win the dedupe and then be dropped by the junk arm, losing the
  track outright.

This is precisely the "reads as binding, isn't" defect the phase is guarding
against, so it should be closed before the rung lands on top of it.

Concrete change — add these two tests to `packages/llama/tests/test_junk.py`.
I ran both: they pass on the committed source, mutant A kills the first
(`assert 'filename' == 'track-tags'`), mutant D kills both.

```python
def test_dedupe_runs_before_play_order_derivation():
    """Play order is derived from the DEDUPED list. With the duplicates still
    present the track tags are non-unique and ordering silently falls back to
    filename order, so this pins the dedupe's position above that block."""
    files = [
        _mp3("band1t02.mp3", track="2", length="300.0"),
        _mp3("band1t01.mp3", track="1", length="180.0"),
        {**_mp3("band99/band1t01.mp3", track="1", length="180.0"), "title": "Alpha"},
        {**_mp3("band99/band1t02.mp3", track="2", length="300.0"), "title": "Beta"},
    ]
    kept, _, ordering = filter_files(files)
    assert ordering["order_source"] == "track-tags"
    assert [f["name"] for f in kept] == ["band99/band1t01.mp3", "band99/band1t02.mp3"]


def test_junk_copy_never_wins_the_dedupe():
    """The dedupe runs AFTER _keep_and_exclude: a titled copy that the junk
    arms would reject must never displace the clean untitled one, or the
    track is lost entirely."""
    files = [
        _mp3("band1t01.mp3", length="300.0"),
        {**_mp3("band99/band1t01.mp3", length="300.0", source="mystery"),
         "title": "Alpha"},
    ]
    kept, _, _ = filter_files(files)
    assert [f["name"] for f in kept] == ["band1t01.mp3"]
```

(Note the first test's expected names: the titled copy wins, and in this
fixture the titled copy is the prefixed one — that asymmetry with the real
ymsb2005 item, where the *top-level* copy carries the tags, is worth a word
in the test docstring.)

---

## Minor

### 2. `order` bookkeeping is dead weight — junk.py:155, 162, 172

`winners` is a plain dict, so it is already insertion-ordered, and the
title-swap writes back under the same key and therefore keeps its slot.
`[winners[k] for k in order]` is provably identical to `list(winners.values())`.
Mutant C (replace with `list(winners.values())`, delete `order`): `1560 passed`.
Drop the list and the two lines that maintain it; three lines less state to
reason about, no behaviour change.

### 3. `filter_files`'s docstring says nothing about the dedupe — junk.py:178-196

That docstring is the boundary contract, and it goes to some length about
format preference and about what `excluded` does and does not cover. This
commit changes both halves of the return value for every consumer (kept can
now be smaller than the winning format's kept set; `excluded` gains a
`duplicate-listing` reason that is not a junk verdict about the file's
content). Add two lines there; the detailed rationale can stay on the helper.

### 4. Measurement provenance lives only in the commit message — junk.py:145-153

House style in this file (`SHORT_FRACTION_OF_MEDIAN`, `LOSSLESS_TITLE_FORMATS`)
records script + date + numbers in the comment, precisely so a later reader
does not re-litigate it from scratch. The helper's docstring cites ymsb2005
but not the sweep. Add: "Measured 2026-09-02 with scripts/dedupe_sweep.py over
968 cached items (1936 item/format pairs): exactly one item changes
(ymsb2005-12-31.flac16, 56→28 in both mp3 and flac)."

### 5. Same-basename-different-directory is treated as duplicate; `titles.py` documents the opposite rule

`titles._stem_no_ext` (packages/llama/src/llama/titles.py:84-88) carries the
explicit docstring "directory component retained - two files sharing a
basename in different directories are different tracks." The new key
`(basename, round(secs))` adopts the opposite default and leans entirely on
the duration to tell them apart. Two consequences, in opposite directions:

- Safe direction: `round()` is exact-second, so a true duplicate pair whose
  lengths straddle a .5 boundary (e.g. 442.49 / 442.51) will not collapse.
  Fails to dedupe — fine.
- Unsafe direction: a genuine `disc1/t01.mp3` / `disc2/t01.mp3` pair (both
  pass the `_stem` convention arm, since `_stem` reads the whole path and
  both yield "disc") whose durations round to the same second loses a track
  silently, with no review flag — the Minutemen failure shape.

I measured this independently of the sweep, straight off the raw cache
metadata: of 968 cached items, exactly **1** has any two audio files sharing
a `(format, basename)` — ymsb2005-12-31.flac16 — and **0** have a
same-duration basename collision that is not a top-level/prefix pair. So this
is theoretical for today's corpus, which is why it is Minor. Either record
that measurement and the `titles.py` tension in the helper's docstring, or
tighten the key's guard to the phenomenon actually observed:
`other == base or other.endswith("/" + base)`.

### 6. `test_clean_item_byte_identical_through_filter_files` — name and duplication — test_junk.py:240-254

The name promises bytes; the test checks the kept-name list, absence of
`duplicate-listing` reasons, and object identity. The six-name literal is a
verbatim copy of `test_keeps_real_tracks_sorted` (test_junk.py:14-19), so a
fixture change now has to be edited in two places. Suggest renaming to
`test_clean_item_passes_through_unchanged` and dropping the duplicated name
literal, keeping the identity loop and the no-reasons assertion (which are
what the test uniquely earns).

### 7. `scripts/dedupe_sweep.py` — two honesty nits, neither invalidating the result

- `n_pairs` (line 103) increments for every item x every format regardless of
  whether the item has any files in that format, so the commit message's
  "1936 item/format pairs" overstates the number of real comparisons (it is
  exactly 2 x 968 by construction). Count only pairs where `audio` is
  non-empty, or describe it as "item/format probes".
- `load_items` (lines 68-74) silently `continue`s past unreadable or
  malformed cache entries without counting them, so a large silent skip would
  shrink the denominator invisibly. Here it did not: `ls ~/.llama/cache/md_*.json
  | wc -l` = 968, exactly the reported n_items. Printing `skipped=` would make
  that self-evident rather than something a reviewer has to check.

---

## Is the sweep's "exactly one changed item" an artifact? No.

Checked four ways:

1. `git rev-parse f943909^` == `98d752ab36b7...` — the OLD code really is the
   parent commit's `junk.py`, loaded via `git show` + `importlib`, not a
   paraphrase.
2. The comparison is on the ordered kept-*name* list, so a wrong-copy
   survivor, a lost track, or even a pure reordering would all be reported
   (a reordering would print `dropped=[] added=[]`, which is legible).
3. `filter_files` does not mutate its input (`_keep_and_exclude` sorts a new
   list, the dicts are never written to), so running old-then-new on the same
   `files` object cannot contaminate the second call.
4. Independent replication from the raw metadata, not through `filter_files`
   at all: exactly one cached item (ymsb2005-12-31.flac16) has any two audio
   files sharing a `(format, basename)`. That matches the sweep's answer
   exactly, which is strong evidence the script is measuring the corpus and
   not itself.

Only real limitation, already stated by the implementer: the corpus is the
local cache, so this bounds the blast radius for items already fetched, not
for items never fetched.

---

## Test hygiene — what edit kills each new test

All three new tests are binding; none is hollow. Evidence (test_junk.py alone,
22 tests, on the shadow-proven copy):

| Test | Killing edit | Observed |
|---|---|---|
| `test_duplicate_listing_keeps_the_titled_copy` (:210) | (a) delete the `_dedupe_duplicate_listings` call at junk.py:212; (b) invert the preference to `if incumbent_title and not candidate_title:`; (c) rename the reason string to `"duplicate"` | (a) 21 failed / 1 passed; (b) `assert [''] == ['Alpha']`, 1 failed; (c) 1 failed |
| `test_same_basename_different_duration_both_kept` (:229) | drop duration from the key (`key = (base, 0)`) | 1 failed, 1559 passed |
| `test_clean_item_byte_identical_through_filter_files` (:240) | return copies: `[dict(winners[k]) for k in order]` | 1 failed |

Note the third test is binding but thin: only the `f is by_name[f["name"]]`
loop earns it a mutant of its own; its name-list half is dead weight (see
Minor 6). The gaps are coverage gaps, not hollow assertions — the two
placement mutants (A and D above) are what nothing catches.

The brief's named acceptance mutation (invert the tagged-copy preference)
reproduces exactly as the implementer reported: the assertion that fires is
the string one, and a `len(kept) == 1` assertion alone would have stayed green.

---

## Scope and process

- **No scope creep.** The diff touches exactly the three files the brief
  names: junk.py (+33), test_junk.py (+48), scripts/dedupe_sweep.py (+129).
  No unrelated edits, no drive-by refactors, no new constants (so the
  do-not-retune trio is untouched).
- **The two-pass median is not perturbed.** The dedupe runs strictly after
  `_keep_and_exclude` returns, so `clean_secs` and `floor` are computed over
  exactly the same input set as before — verified by reading and by the sweep
  (a perturbed floor would have changed far more than one item). Worth
  noting that a duplicated listing would not move a median anyway (duplicating
  every element leaves the median unchanged), which is why mutant D is
  near-inert on that axis and dangerous only on the junk-copy axis.
- **Excluded-entry shape matches** the existing arms exactly:
  `{"filename": ..., "reasons": [...]}`, appended to the same list the
  winning format's exclusions live in, consumed by
  `models.Show.excluded_files` and `gather` the same way `operator-excluded`
  is. No consumer branches on the reason string, so the new value is inert
  downstream.
- **No O(n^2) or mutate-while-iterating.** One pass over `kept`, dict lookups,
  appends to fresh lists; the input list is never mutated and the returned
  list is new.
- **Commit messages state the test command and result** in both commits
  (`Test command: ./.venv/bin/pytest -q` -> `1560 passed, 7 deselected`), plus
  the sweep summary and the spot checks. This meets the project's auditability
  bar.

## What I did not do

Did not re-run the full suite to confirm the implementer's green baseline
(only as the control/mutant arms above, which reproduced 1560 passed on the
unmutated copy). Did not touch the worktree. Made no commits.
