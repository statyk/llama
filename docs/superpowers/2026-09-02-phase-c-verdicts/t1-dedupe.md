# Task 1: `filter_files` duplicate-listing dedupe — report

## Status: DONE

## Commits (branch `sibling-transfer`, worktree `/Users/shawn/projects/llama/.worktrees/sibling-transfer`)

- `f943909` — `junk: dedupe duplicate-listed tracks in filter_files`
  Implements `_dedupe_duplicate_listings` in `packages/llama/src/llama/junk.py`,
  wired into `filter_files` right after format selection (after
  `_keep_and_exclude` for the winning format, before play-order derivation).
  Adds three Step-1 tests to `packages/llama/tests/test_junk.py`.
- `852e47d` — `tools(scripts): add the filter_files duplicate-listing dedupe sweep`
  Adds `scripts/dedupe_sweep.py`. No production code changed in this commit.

Baseline before this task: `1557 passed, 7 deselected`.
Suite after this task: `1560 passed, 7 deselected` (baseline + 3 new tests).

## Exact test command and output tail

```
$ ./.venv/bin/pytest -q
...
1560 passed, 7 deselected, 26 warnings in 5.38s
```

`test_junk.py` alone:

```
$ ./.venv/bin/pytest packages/llama/tests/test_junk.py -q
......................                                                   [100%]
22 passed in 0.07s
```

## Step 2 — recorded failure output (before implementation)

Ran the three Step-1 tests against the pre-fix `junk.py` (i.e. before adding
`_dedupe_duplicate_listings`). Two of the three passed immediately (they are
regression guards for behaviour that doesn't change: different-duration
same-basename files were never touched, and a clean item was already
untouched). The dedupe-content test failed exactly as expected — both
copies kept instead of one:

```
_________________ test_duplicate_listing_keeps_the_titled_copy _________________

    def test_duplicate_listing_keeps_the_titled_copy():
        ...
        files = [
            _mp3("band1t01.mp3", length="300.0"),
            {**_mp3("band99/band1t01.mp3", length="300.0"), "title": "Alpha"},
        ]
        kept, excluded, _ = filter_files(files)
>       assert len(kept) == 1
E       AssertionError: assert 2 == 1
E        +  where 2 = len([{'name': 'band1t01.mp3', 'format': 'VBR MP3', 'source': 'original', 'length': '300.0'}, {'name': 'band99/band1t01.mp3', 'format': 'VBR MP3', 'source': 'original', 'length': '300.0', ...}])

packages/llama/tests/test_junk.py:224: AssertionError
=========================== short test summary info ============================
FAILED packages/llama/tests/test_junk.py::test_duplicate_listing_keeps_the_titled_copy
1 failed, 21 passed in 0.10s
```

Note on test fixture design: the synthetic duplicate pair uses filenames
`band1t01.mp3` / `band99/band1t01.mp3` rather than the brief's literal
`d1t01.mp3` / `ident/d1t01.mp3` example, because `_keep_and_exclude`'s
filename-convention arm (`_stem`, "text up to the first digit") scans the
whole name including any directory prefix. A prefix whose own leading text
doesn't match the basename's leading text (e.g. `ident/d1t01.mp3` -> stem
`"ident/d"` vs `d1t01.mp3` -> stem `"d"`) gets excluded as "filename
convention mismatch" before dedupe logic ever runs on it, which would make
the test exercise the wrong code path. `band99` was chosen so its text
before its own first digit (`"band"`) matches the basename's
(`band1t01.mp3` -> stem `"band"`) - mirroring why real archive.org items
(ymsb2005: `ymsb2005-12-31.../ymsb2005-12-31d1t01.mp3`) don't hit this
mismatch either: the identifier's own leading digits coincide with the
filename's.

## Implementation

`_dedupe_duplicate_listings(kept)` in `junk.py`:
- Key: `(basename, round(duration or 0))`, basename = `name.rsplit("/", 1)[-1]`.
- Keeps the first copy encountered (by iteration order of the already
  name-sorted `kept` list) unless a later duplicate carries a title
  (`f.get("title")`, stripped) the current winner lacks - then it swaps in.
- Every collapsed copy goes into a new `excluded` entry with
  `reasons: ["duplicate-listing"]`.
- Runs in `filter_files` after `chosen`/`fallback` selection picks the
  winning format's `(kept, excluded)`, and before the track-tag play-order
  derivation block - so ordering is derived from the deduped list, per the
  brief.
- For an item with no key collisions, the function returns the same list of
  the same objects in the same order (verified by identity, not just
  equality, in `test_clean_item_byte_identical_through_filter_files`).

## Step 4 — the sweep

`scripts/dedupe_sweep.py`: walks `~/.llama/cache/md_*.json`, and for each
cached item x `{mp3, flac}` runs both the real pre-fix `filter_files`
(loaded straight from git history at commit
`98d752ab36b7370e8ec042fffe5a76c95409dfed`, the parent of the dedupe fix
commit, via `importlib` - not a reimplementation) and the current
`llama.junk.filter_files`, and prints every `(identifier, format)` pair
whose kept-name list changed.

Full run over the real `~/.llama/cache` (968 cached items):

```
$ ./.venv/bin/python scripts/dedupe_sweep.py --progress 100
...
# items=968 item/format pairs=1936 changed pairs=2 changed items=1
```

Raw sweep output (both changed rows - full item, both formats):

```
ymsb2005-12-31.flac16  mp3   before=56  after=28  dropped=[... 28 identifier-prefixed .mp3 names ...]  added=[]
ymsb2005-12-31.flac16  flac  before=56  after=28  dropped=[... 28 identifier-prefixed .flac names ...]  added=[]
```

(Full dropped-name lists are in
`/private/tmp/claude-501/-Users-shawn-projects-llama/e82f7960-4d8a-417d-83fc-8132225b6186/scratchpad/workc/t1-dedupe/sweep-out.tsv`
and the session log at
`/private/tmp/claude-501/-Users-shawn-projects-llama/e82f7960-4d8a-417d-83fc-8132225b6186/scratchpad/sdd-phasec/t1-dedupe/t1-dedupe.log`.)

Only one item in the entire 968-item cache changed, and it is exactly the
item named in the design spec
(`docs/superpowers/specs/2026-09-02-sibling-title-transfer-design.md`,
ymsb2005's donor: 56 files for 28 tracks). `added=[]` on both rows - every
run dropped exactly the duplicate copies, added nothing, i.e. no track was
lost, only collapsed.

### Spot checks (>=10 required; 24 performed - all 24 dropped/kept pairs across both formats, verified programmatically then hand-read)

For every one of the 28 mp3 pairs and 28 flac pairs, the dropped filename's
basename matches its surviving twin's full name exactly, the durations agree
to rounding, the dropped copy carries no title, and the surviving copy does.
A representative sample (first 12 of each format, hand-read):

mp3:
```
dropped ymsb2005-12-31.flac16/ymsb2005-12-31d1t01.mp3 len=02:14 title=None  -> kept ymsb2005-12-31d1t01.mp3 len=02:14 title='Intro'
dropped .../d1t02.mp3 len=04:30 title=None -> kept d1t02.mp3 len=04:30 title='Granny Woncha Smoke Some >'
dropped .../d1t03.mp3 len=04:36 title=None -> kept d1t03.mp3 len=04:36 title='Ride The Wild Turkey'
dropped .../d1t04.mp3 len=07:11 title=None -> kept d1t04.mp3 len=07:11 title='On The Run >'
dropped .../d1t05.mp3 len=04:49 title=None -> kept d1t05.mp3 len=04:49 title='Postcard To My Son From Jail [tentative title] >'
dropped .../d1t06.mp3 len=05:23 title=None -> kept d1t06.mp3 len=05:23 title='On The Run'
dropped .../d1t07.mp3 len=07:40 title=None -> kept d1t07.mp3 len=07:40 title='Steep Grade Sharp Curves *'
dropped .../d1t08.mp3 len=04:52 title=None -> kept d1t08.mp3 len=04:52 title='Howard Hughes Blues *'
dropped .../d1t09.mp3 len=07:22 title=None -> kept d1t09.mp3 len=07:22 title='Polly Put The Kettle On * ^ >'
dropped .../d1t10.mp3 len=05:33 title=None -> kept d1t10.mp3 len=05:33 title='Jenny Run Away In the Mud & Rain * ^'
dropped .../d1t11.mp3 len=07:20 title=None -> kept d1t11.mp3 len=07:20 title='Peace Of Mind * >'
dropped .../d1t12.mp3 len=04:54 title=None -> kept d1t12.mp3 len=04:54 title='King Ebenezer Rap * >'
```

flac (same 12 tracks, slightly different raw length strings that round to
the same duration - e.g. `270.55` vs `270.54`, `442.11` vs `442.1` - the key
uses `round()` so these still collapse correctly):
```
dropped ymsb2005-12-31.flac16/ymsb2005-12-31d1t01.flac len=134.45 title=None -> kept d1t01.flac len=134.45 title='Intro'
dropped .../d1t02.flac len=270.55 title=None -> kept d1t02.flac len=270.54 title='Granny Woncha Smoke Some >'
dropped .../d1t03.flac len=276.13 title=None -> kept d1t03.flac len=276.13 title='Ride The Wild Turkey'
dropped .../d1t04.flac len=431.33 title=None -> kept d1t04.flac len=431.33 title='On The Run >'
dropped .../d1t05.flac len=289.61 title=None -> kept d1t05.flac len=289.61 title='Postcard To My Son From Jail [tentative title] >'
dropped .../d1t06.flac len=323.92 title=None -> kept d1t06.flac len=323.92 title='On The Run'
dropped .../d1t07.flac len=460.67 title=None -> kept d1t07.flac len=460.66 title='Steep Grade Sharp Curves *'
dropped .../d1t08.flac len=292.4 title=None -> kept d1t08.flac len=292.4 title='Howard Hughes Blues *'
dropped .../d1t09.flac len=442.11 title=None -> kept d1t09.flac len=442.1 title='Polly Put The Kettle On * ^ >'
dropped .../d1t10.flac len=333.28 title=None -> kept d1t10.flac len=333.28 title='Jenny Run Away In the Mud & Rain * ^'
dropped .../d1t11.flac len=440.48 title=None -> kept d1t11.flac len=440.48 title='Peace Of Mind * >'
dropped .../d1t12.flac len=294.69 title=None -> kept d1t12.flac len=294.69 title='King Ebenezer Rap * >'
```

Every one of the 24 spot-checked pairs (and, by the identical structural
pattern, all 28+28 = 56 pairs) is a genuine same-basename/same-duration
collapse of a duplicate listing - none is a false positive. No other cached
item's kept set changed, so "no library show's kept set changes except the
known duplicate-listing item" holds trivially: there is exactly one such
item, and it is named above.

## Named mutation check (acceptance requirement, not committed)

Inverted the tagged-copy preference in `_dedupe_duplicate_listings`
(`if not incumbent_title and candidate_title:` -> `if incumbent_title and
not candidate_title:`), re-ran only `test_duplicate_listing_keeps_the_titled_copy`:

```
>       assert clean_tag_titles(kept) == ["Alpha"]
E       AssertionError: assert [''] == ['Alpha']
E
E         At index 0 diff: '' != 'Alpha'
```

The test fails on the string content exactly as the brief specifies - a
count-based test (`len(kept) == 1`) would have stayed green under this
mutation. Reverted the mutation immediately after (`cp` from a
pre-mutation backup in the scratchpad work dir), confirmed `git diff` on
`junk.py` is empty relative to commit `f943909`, and re-ran `test_junk.py`
(22 passed) before proceeding.

## Bulk output location

`/private/tmp/claude-501/-Users-shawn-projects-llama/e82f7960-4d8a-417d-83fc-8132225b6186/scratchpad/workc/t1-dedupe/`:
- `sweep-out.tsv` - full sweep stdout (3 lines: 2 changed rows + summary).
- `sweep-err.log` - progress stderr + summary.
- `junk.py.orig` - pre-mutation backup used for the mutation-check revert.

## Concerns

None. The dedupe is scoped exactly as specified (post-`_keep_and_exclude`
for the winning format, pre-ordering), the corpus sweep found only the one
named item changed corpus-wide (968 cached items, 1936 item/format pairs),
all spot-checked pairs are genuine collapses, the mutation-kill property is
verified, and the full suite is green (1560 passed, 7 deselected).

One scope note for the reader, not a defect: the sweep's cache
(`~/.llama/cache`, 968 items) is this machine's real archive.org metadata
cache, not a synthetic fixture - so this result is empirical for the
current cache contents, not a guarantee about items never yet fetched. That
is inherent to any corpus sweep of this kind and matches how the project's
other sweep scripts (e.g. `title_source_census.py`) are scoped.

---

# Fix round 1 addendum (review findings addressed)

## Status: DONE

## New commit

- `115f0f8` — `junk: pin the dedupe's two placement invariants + document the reason`

## Findings addressed

1. **(Important, both reviewers) Play-order-on-deduped-list invariant unpinned.**
   Added `test_dedupe_runs_before_play_order_derivation` to
   `packages/llama/tests/test_junk.py`: two duplicate pairs share track
   tags (`1,1` and `2,2`) before dedupe, so `ordering["order_source"]` can
   only read `"track-tags"` once the duplicates collapse to unique tags.
2. **(Important, quality reviewer) `_keep_and_exclude`-placement invariant
   unpinned.** Added `test_dedupe_runs_after_junk_filtering`: a titled
   duplicate of bad provenance (`source="mystery"`) must never win the
   swap and displace the clean original, or the track is junk-filtered
   away entirely instead of surviving as the clean copy.
3. **(Minor) `filter_files`'s boundary docstring never mentioned the
   dedupe or `duplicate-listing`.** Added a paragraph disclosing both.
4. **(Minor) sweep provenance lived only in the commit message.** Added
   to `_dedupe_duplicate_listings`'s docstring: "Measured 2026-09-02 with
   scripts/dedupe_sweep.py over 968 cached items (1936 item/format
   pairs): exactly one item changes - ymsb2005-12-31.flac16, 56 -> 28
   kept files in both mp3 and flac."

Deferred to the whole-branch review per the orchestrator's explicit
scoping (not touched): the redundant `order` list, the
`(basename, round(secs))` key vs `titles.py`'s different-dirs-note, the
`test_clean_item_byte_identical_through_filter_files` name/duplication,
and the sweep script's `n_pairs`/skip-counting nits.

## New tests: verified PASS on shipped code, RED under mutation

Both new tests were:
1. Added to the worktree and run against the (correct) shipped code —
   confirmed PASS (`./.venv/bin/pytest packages/llama/tests/test_junk.py
   -q` -> `24 passed`).
2. Verified RED under their respective mutation **on a copy outside the
   worktree** (`scratchpad/workc/t1-fix1`), per the orchestrator's
   correction to the verification method (see "Housekeeping" below for
   why in-worktree mutate-and-revert was avoided this round).

### Mutation for finding 1 — move dedupe to after play-order derivation

Command: relocated the two-line
`kept, dup_excluded = _dedupe_duplicate_listings(kept); excluded =
excluded + dup_excluded` block from immediately after format selection to
immediately before `return kept, excluded, ordering`, in the copy at
`scratchpad/workc/t1-fix1/packages/llama/src/llama/junk.py`.

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_junk.py -q`
(from the copy root, `__pycache__` purged before and after).

Verbatim RED:

```
________________ test_dedupe_runs_before_play_order_derivation _________________
...
        kept, _, ordering = filter_files(files)
>       assert ordering["order_source"] == "track-tags"
E       AssertionError: assert 'filename' == 'track-tags'
E
E         - track-tags
E         + filename

packages/llama/tests/test_junk.py:258: AssertionError
=========================== short test summary info ============================
FAILED packages/llama/tests/test_junk.py::test_dedupe_runs_before_play_order_derivation
1 failed, 23 passed in 0.18s
```

### Mutation for finding 2 — dedupe the raw `files` list before format selection/junk filtering

Command: inserted `files, _pre_dup_excluded =
_dedupe_duplicate_listings(files)` at the top of `filter_files` (before
the `wanted = ...` line) and merged `_pre_dup_excluded` into `excluded`
after format selection instead of deduping `kept`, in the same copy.

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_junk.py -q`.

Verbatim RED:

```
____________________ test_dedupe_runs_after_junk_filtering _____________________
...
        kept, _, _ = filter_files(files)
>       assert [f["name"] for f in kept] == ["band1t01.mp3"]
E       AssertionError: assert [] == ['band1t01.mp3']
E
E         Right contains one more item: 'band1t01.mp3'
E         Use -v to get more diff

packages/llama/tests/test_junk.py:274: AssertionError
=========================== short test summary info ============================
FAILED packages/llama/tests/test_junk.py::test_dedupe_runs_after_junk_filtering
1 failed, 23 passed in 0.17s
```

After each mutation, `junk.py` in the copy was restored via `cp` from the
worktree's committed file and byte-diffed (`diff` exit 0) before the next
mutation; the copy's full suite was re-run after the final restore and
confirmed `1562 passed, 7 deselected`.

## Housekeeping: stale venv shadow found and fixed (worktree, not the copy)

Before starting the mutation work, `cat`-ing the worktree's own
`.venv/lib/python3.14/site-packages/_editable_impl_llama_{radio,herder}.pth`
showed both pointing at a **prior reviewer's scratch copy**
(`scratchpad/workc/t1-rev-qual/packages/{llama,herder}/src`), not at the
worktree. That means `./.venv/bin/pytest -q` run from the worktree
between the review round ending and this fix round starting (including
my own first `pytest -q` invocation of this round) was silently
importing `llama`/`herder` from outside the worktree rather than from
the worktree's own source — the exact shadowing hazard the spec reviewer
documented, but on the *worktree's* venv this time, not a reviewer copy.

Verified via `./.venv/bin/python -c "import llama.junk;
print(llama.junk.__file__)"` before the fix (printed the scratch-copy
path) and confirmed the only functional difference between the shadow
copy's `junk.py` and the worktree's at that moment was my not-yet-applied
docstring additions (`diff` showed only those two hunks) - so no result
already reported was actually wrong, but the verification channel itself
was compromised and had to be fixed before it could be trusted again.
Repointed both `.pth` files back to
`/Users/shawn/projects/llama/.worktrees/sibling-transfer/packages/{llama,herder}/src`,
re-verified with the same `__file__` check (now correct), purged
`__pycache__`, and re-ran the full suite from the worktree (`1562 passed,
7 deselected`) before proceeding. This is now noted in the commit
message so a future session isn't caught by the same stale pointer.

## Exact final test command and output

```
$ ./.venv/bin/pytest -q
...
1562 passed, 7 deselected, 26 warnings in 7.10s
```

## Concerns

None outstanding for this round. The venv-shadow discovery is flagged
above for visibility, not because it changed any prior conclusion — the
prior report's claims were re-verified correct once the channel was
fixed. Other reviewer scratch copies under `scratchpad/workc/` may carry
similarly stale `.pth` pointers *inside their own copies*, which is
expected and harmless (they're throwaway); the only one that mattered was
the worktree's own, which is now fixed.
