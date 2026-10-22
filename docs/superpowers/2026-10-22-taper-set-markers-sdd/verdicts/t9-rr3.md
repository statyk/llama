ALL ADDRESSED, NO NEW BREAKAGE

# t9-rr3: scoped re-review of the final-review fix (8ed8d0c -> ec0fb6a)

## Verdicts
- **I1: ADDRESSED.** No record blob at ec0fb6a matches any blob outside docs/ at any commit reachable from a9016b5. No `pytest.ini`, `conftest.py`, `LICENSE`, `CLAUDE.md`, `.github/`, `packaging/` or `packages/` mirror is left. The 74 kept `.py` files are reviewer-written runners, probes, patch scripts and test literals, not copies. All 497 deletions are under `evidence/`, and the README drop list matches them exactly: same paths, sha256 and sizes. R22 holds: `git diff a9016b5 ec0fb6a -- . ':!docs' ':!CLAUDE.md'` is 0 bytes, and CLAUDE.md is the same blob 3f35413 at 8ed8d0c and ec0fb6a. Suite: 4474 passed, 1 skipped, 8 deselected.
- **M2: ADDRESSED.** The new sentence is correct against `~/.llama-harness/piece2/accept3/score/score_rows.jsonl` and `score_summary.txt` (check 5).

## Check results
1. **No repo-source copies remain.**
   - Blob comparison: I ran `git ls-tree -r` over every commit in `git rev-list a9016b5` and kept every non-docs blob: 3065 unique. Intersected with the record's 220 blobs at ec0fb6a: **0 matches**. Against all blobs reachable from a9016b5 at any path, the only matches are earlier docs commits of the same record files (mutation.md, spec-review/*) and one `run.rc` equal to another record's `suite.rc`.
   - Name scan: the only hit is the record's own README.md. Extensions: 74 py, 73 md, 56 txt, 9 jsonl, 4 json, 2 sh, 1 rc, 1 out.
   - Verbatim-line overlap of each kept `.py` with a9016b5's `packages/` and `scripts/` `.py` lines (lines of 30+ chars):
     - Top scorers: `orch-r1/literals.py` 60/60, `dso.py` 10/10, `fix1_tests.py` 30/35, `p3.py` 40/55, `patch.py` 74/103, `p2.py` 14/30. Everything else is 0.34 or lower.
     - I read all six. `literals.py` and `dso.py` are description string literals, taken from cached item metadata and used as test data that later landed in `test_taper.py`. `fix1_tests.py` is a proposed test snippet. `p2.py`, `p3.py` and `patch.py` are `rep(old, new)` patch scripts that edit `scripts/replay_holds.py`, so they share lines with what they produced.
     - None is a modified copy of repo source.
     - Non-py files: highest overlap is 1/33 lines.
2. **Nothing that should stay was dropped.**
   - Outside `evidence/`, `git diff --name-status 8ed8d0c ec0fb6a` shows only: M README.md, M orch-r2/ledger.md, A orch-r2/deferred-minors.md, A verdicts/final-rev.md, A verdicts/t9-docs.md. No deletions.
   - Kept: orch/, orch-r1/ and orch-r2/ ledger.md, mutation.md, spec-review/ (12 files), acceptance/ (7 files), evidence/LARGE-FILES.txt.
   - Verdicts: 55 at ec0fb6a (53 at 8ed8d0c, plus t9-docs and final-rev). Every one is byte-identical to the live `$D/<task>/handback.md`. Every live task dir with a handback.md has a verdict, except t9-rewrite, which postdates the record.
   - Drop list: the README's per-file list has 497 entries, with the same paths as `git diff --diff-filter=D 8ed8d0c ec0fb6a` (PATHS-IDENTICAL). Each sha256 and size matches the 8ed8d0c blob (0 mismatches). The table rows sum to 497 files and 8,654,718 bytes, which equals the list total.
   - Every deleted path is under a `packages/` mirror or is a repo top-level file, except taper.orig x2, gather.full/head, test.head, test_stage_gather.full, tests_head/tail and versions/taper_*.py x8. All of these are whole or partial source copies.
   - Mutant definitions survive:
     - T6 mutants: in the kept `orch-r1/t6-rev/mut.sh`.
     - T12 mutant: the dropped `t12-rev/mut` taper.py differs from 569b88c by one line, `today_sets[placed.boundaries[-1] + 1:]`, which is quoted verbatim in `verdicts/t12-rev.md:62`. Its gather.py equals c139a65.
3. **The cherry-picks are faithful.**
   - Outside the record dir, `git diff --stat 8ed8d0c ec0fb6a` shows only acceptance.md (1+/1-). The changed line is the M2 sentence.
   - `git patch-id --stable`: 783e753 == e4075f3 and 8ed8d0c == cc991f0.
   - Commit messages are identical, trailers included, for both cherry-picks. b358726 keeps b95a099's subject and trailers and adds one paragraph explaining the rewrite.
   - Parent chain is linear: a9016b5 <- b358726 <- e4075f3 <- cc991f0 <- ec0fb6a.
   - Outside the record, `git diff --stat a9016b5 8ed8d0c` and `git diff --stat a9016b5 ec0fb6a` differ only by that sentence: both show CLAUDE.md +1, acceptance.md +139, spec 1+/1-.
4. **R22 and the suite.**
   - R22a: `git diff a9016b5 ec0fb6a -- . ':!docs' ':!CLAUDE.md' | wc -c` gives 0.
   - R22b: `git diff 8ed8d0c ec0fb6a -- CLAUDE.md | wc -c` gives 0. The blob is 3f354138 on both sides.
   - Suite: `./.venv/bin/python -m pytest -q` at HEAD ec0fb6a: **4474 passed, 1 skipped, 8 deselected**. `llama.__file__` resolves inside this worktree.
5. **M2 against score_rows.jsonl** (339 rows):
   - `darkstarorchestra-2007-05-17`: in_scope=True, taper_explicit=yes.
   - `furthur-2012-07-08`, `greenskybluegrass-2014-02-28`, `thenewdeal-2005-04-29`: in_scope=False, taper_explicit=partial.
   - All four misses are desc-set-header. The in-scope set is 186 rows, all `yes`, with exactly 1 miss.
   - In `score_summary.txt`, "counts by primary (in scope)" covers 313 of the 339 yes/partial rows, excluding the 26 filename/track-tag rows, and shows miss=4 under desc-set-header. The gate line is "IN SCOPE (yes, worded form, 3 desc primaries...)". So the sentence's two senses of "in scope" are accurate.
   - The record's acceptance/score/score_summary.txt is byte-identical to the harness copy.
6. **Backup ref:** `refs/heads/backup/taper-markers-record-8ed8d0c` points at 8ed8d0cfe4e33feb916ff083587a54515e3c0b56. No remote branch contains 8ed8d0c or b358726, and the branch has no upstream, so nothing is pushed.
   - Spot check of the README's survival claim: `$D/orch/evidence/t12-rev/mut/.../taper.py`, `$D/orch-r1/evidence/t6-rev/m_A/pytest.ini`, `gather.full.py` and `versions/taper_025e713.py` are all present.

## New breakage
None. No Critical, Important or Minor issues.

## Deferred minors (informational, not defects in the fix)
- The live `$D/orch-r2/ledger.md` has two entries the record does not: t9-rewrite DONE and the t9-rr3 dispatch. There are also no `verdicts/t9-rewrite.md` or `t9-rr3.md`. This is expected because they postdate the record commit. Refresh at Finish if the record should be final through re-review.
- `tests_tail.py` was dropped as a copy, but 10 of its 80 long lines are not in `test_taper.py`. This is a defensible judgment call: they are snippet text, and the bytes survive in the backup ref and `.superpowers/`.
- Kept files (LARGE-FILES.txt, and some verdicts and ledgers) still name paths inside the dropped trees. The README's drop section documents this.
