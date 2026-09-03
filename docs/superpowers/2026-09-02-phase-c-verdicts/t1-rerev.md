# Task 1 fix round 1 — scoped re-review

**Verdict: APPROVED.** All four findings ADDRESSED. No new breakage in the fix diff.

## Environment integrity

- `PTH-GUARD: OK` on the worktree venv (all three packages import from
  `/Users/shawn/projects/llama/.worktrees/sibling-transfer`).
- Verification copy: `scratchpad/workc/t1-rerev/copy` (rsync of the worktree, no `.venv`/`.git`).
  Shadowing done per-process with `PYTHONPATH=<copy>/packages/{llama,herder,emcee}/src` and
  `./.venv/bin/python -m pytest` (never `./.venv/bin/pytest`). **Worktree `.pth` files untouched.**
- Shadowing proven twice before trusting any mutation:
  1. `llama.junk.__file__` resolved to the copy, sentinel constant `_RERV_SENTINEL` visible.
  2. Behavioural sentinel: renaming `"duplicate-listing"` -> `"duplicate-listing-SENT"` in the
     copy turned `test_duplicate_listing_keeps_the_titled_copy` RED under `python -m pytest`.
  `__pycache__` purged before and after every run; `junk.py` restored from a pristine copy and
  byte-diffed between mutations (`diff` exit 0), and against the worktree file at the end.

## Findings

### 1. Play-order-on-deduped-list invariant — ADDRESSED
Mutation applied: relocated the `kept, dup_excluded = _dedupe_duplicate_listings(kept)` /
`excluded = excluded + dup_excluded` block from immediately after format selection to
immediately before `return kept, excluded, ordering`.

Red test: `packages/llama/tests/test_junk.py::test_dedupe_runs_before_play_order_derivation`

```
>       assert ordering["order_source"] == "track-tags"
E       AssertionError: assert 'filename' == 'track-tags'
```
Full suite under this mutation: **1 failed, 1561 passed, 7 deselected** — the new test is the
sole detector, and the three original Task 1 tests all stayed green, so it is not a re-assertion
of existing coverage.

### 2. `_keep_and_exclude` placement invariant — ADDRESSED
Mutation applied: inserted `files, dup_excluded = _dedupe_duplicate_listings(files)` at the top
of `filter_files` (before `wanted = ...`), removed the post-filter dedupe, and merged
`dup_excluded` into `excluded` after format selection — i.e. dedupe the raw list before
`_keep_and_exclude`/format selection.

Red test: `packages/llama/tests/test_junk.py::test_dedupe_runs_after_junk_filtering`

```
>       assert [f["name"] for f in kept] == ["band1t01.mp3"]
E       AssertionError: assert [] == ['band1t01.mp3']
```
Full suite under this mutation: **1 failed, 1561 passed, 7 deselected** — again the sole
detector, originals green.

Nuance (not a defect, no action asked): the test pins the placement through a different pathway
than the finding's stated rationale — junk-provenance displacement (a titled `source="mystery"`
duplicate winning the swap and then being filtered away, emptying `kept`) rather than
perturbation of `_keep_and_exclude`'s median input set. It nonetheless kills the exact mutation
the finding named, which is what ADDRESSED requires here. A median-perturbation case would need
a >=5-file tape and would be a strictly additional test, not a replacement.

### 3. `filter_files` boundary docstring — ADDRESSED
New paragraph discloses both the post-junk-filtering dedupe and the `duplicate-listing`
excluded reason, and explicitly frames it as "not a junk verdict about its content".

### 4. Sweep provenance beside the code — ADDRESSED
`_dedupe_duplicate_listings`'s docstring now carries "Measured 2026-09-02 with
scripts/dedupe_sweep.py over 968 cached items (1936 item/format pairs): exactly one item
changes - ymsb2005-12-31.flac16, 56 -> 28 kept files in both mp3 and flac." There is no
constant to hang a comment on in this function, so the docstring is the house-style-equivalent
code-adjacent location.

## Baseline and new breakage

- Unmutated copy: `24 passed` in `test_junk.py`; full suite `1562 passed, 7 deselected`.
- The `junk.py` half of the fix diff is **entirely inside docstrings** — zero executable-code
  change. The `test_junk.py` half adds two tests and touches nothing existing. No new breakage.

## venv repair is not in the commit

`git show --stat 115f0f8` lists exactly two files (`packages/llama/src/llama/junk.py`,
`packages/llama/tests/test_junk.py`); `.venv/` is gitignored (`.gitignore:5`), no `.pth` path is
tracked, and the worktree is clean. The commit message's "repointed .pth files at the copy"
refers to the fix agent's **own** copy venv — verified: `workc/t1-fix1/.venv`'s
`_editable_impl_llama_{radio,herder}.pth` point at `workc/t1-fix1/packages/*/src`, and the
worktree's three `.pth` files all point at the worktree. Nothing shared was left modified.

**Credit where due:** the implementer disclosed, unprompted and in the commit message, that the
worktree venv's `.pth` files had been repointed at a prior reviewer's scratch copy — a fact that
undercut its own earlier green result and would have been invisible to `git status` and to every
later reader. It then repaired the channel and re-verified before proceeding. That is the report
behaving correctly under pressure to stay quiet.
