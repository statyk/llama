# t9-rewrite handback

**Status: DONE**

## Backup ref
`backup/taper-markers-record-8ed8d0c` -> `8ed8d0cfe4e33feb916ff083587a54515e3c0b56` (created before the reset).

## New commits (a9016b5..HEAD)
- `b358726` docs: taper markers SDD record (ledgers, verdicts, evidence, acceptance run 3), the rewritten b95a099
- `e4075f3` docs: taper markers acceptance record (run 3); spec 2 wording on B4's window, cherry-pick of 783e753, clean
- `cc991f0` docs: taper markers in CLAUDE.md; acceptance record, cherry-pick of 8ed8d0c, clean
- `ec0fb6a` docs: taper markers acceptance: reconcile the 1-vs-4 miss counts (M2)

HEAD = `ec0fb6acf858f7b420bc2dd8381f05ab69fc6b64`. Each commit's suite run: 4474 passed, 1 skipped, 8 deselected. Nothing pushed or merged.

## Drop set: 497 files, 8,654,718 bytes (8.7 MB), all under `evidence/`
| Directory | Files | Bytes |
|---|---:|---:|
| orch/t12-rev/mut/ (copy of packages/llama src and tests, mutated taper.py/gather.py) | 162 | 3,005,054 |
| orch/t12-rev/c_025e713/, c_3d1c1e7/, c_67291bd/ (packages/llama/src at those commits) | 3 x 62 | 2,415,125 |
| orch/cpa2-tiers/versions/ (taper.py at 8 commits, each byte-identical to `git show <sha>:…/taper.py`, all ancestors of a9016b5) | 8 | 227,725 |
| orch-r1/mut/, red/, red2/ (repo top level: CLAUDE.md, LICENSE, README, .gitignore, pytest.ini, .github/, packaging/) | 3 x 11 | 595,707 |
| orch-r1/t6-rev/m_{A,B,base0,C,D,F,G,I,J}/ (same top-level copies; mutants live in kept mut.sh) | 9 x 11 | 1,787,121 |
| orch-r1/t4-fix1/M0/pytest.ini | 1 | 220 |
| orch-r1/cpa3-rev/taper.orig, cpa3-rr1/taper.orig (taper.py copies) | 2 | 76,583 |
| orch-r1/{gather.full,gather.head,test.head,test_stage_gather.full,tests_head,tests_tail}.py | 6 | 547,183 |

The record README has a new "Dropped from the record" section: a table by directory (count, bytes, reason), the full per-file list (sha256, size, path) in a collapsible `<details>` block per directory, and where the bytes survive (the backup ref, and `.superpowers/sdd/taper-markers/<orch>/evidence/`). I also checked by blob hash which record files are identical to any blob reachable from a9016b5 outside docs/. Every match is in the drop set: the 8 versions, both taper.orig, gather.full/head, test.head, test_stage_gather.full, and M0/pytest.ini.

Judgment calls:
- **Kept** `orch-r1/conftest_probe.py` (112 B), a 2-line probe the reviewer wrote, not a conftest copy. Also kept `literals.py`, `dso.py` and `fix1_tests.py`: test literals and snippets the reviewers wrote, not copies of repo files.
- **Dropped** `tests_head.py`/`tests_tail.py` because the procedure lists them by name. They are snippets of test text that now lives in `packages/llama/tests/test_taper.py`, not whole-file copies.
- **Dropped** `cpa2-tiers/versions/taper_*.py` as whole-file copies. They are unmutated historical versions, all recoverable from git.
- **Left `evidence/LARGE-FILES.txt` unedited.** Four of its lines (`set_breaks.csv` copies) name files inside the dropped `t12-rev/{mut,c_*}` trees, and the README says so.

Refreshed so the record is final:
- `orch-r2/ledger.md` re-copied with `cp` (`cmp` OK).
- Added `orch-r2/deferred-minors.md`.
- Added `verdicts/t9-docs.md` and `verdicts/final-rev.md`. t9-fix1 has no handback.md, which the README notes.
- README bullets updated for the above.

## Kept .py files (74)
evidence/orch-r1: conftest_probe.py, cpa3-rev/{cachescan,cachescan2,gateenc,mut,show,sweep}.py, cpa3-rr1/mut.py, dso.py, dump6.py, fix1_tests.py, gen.py, literals.py, p2.py, p3.py, patch.py, probe_test.py, t4-rev/mut.py, t5-rev/{mut,probe_tests}.py, t7a-rr1/check_renum.py, t8-fix1/{gen,runner,score}.py, t8-impl/{gen,inspect_m,runner,score,sentinels}.py, t8-rev/run.py, t8-rr1/rr.py
evidence/orch: cpa-decl/tools/{checks,classify,difflib2,dumpgate,dumplib,flip2,fliptest,vetogate,vetowiden}.py, cpa-forms/{ablate,corpus,dec,inline_ablate}.py, cpa2-forms/{an2,corpus2,ctext,inspect_show,libvar,showtext,summ,variants}.py, cpa2-tiers/tools/{attrib,breaklike,dcost,dump,dump2,gatedump,gatedump_old,headers,q2gate,setlike}.py, t12-rev/{cmp,dump,hdr,p1,p2,p3,p4,p7,pairs}.py, t3-rev/{classify,desc,spot}.py

## M2
acceptance.md line 32: replaced "I could not reconcile it from the files, so both are given" with one sentence that reconciles the counts. The in-scope line's 1 miss is darkstarorchestra-2007-05-17 (`taper_explicit: yes`). The other 3 (furthur-2012-07-08, greenskybluegrass-2014-02-28, thenewdeal-2005-04-29) are `taper_explicit: partial`: outside the gate's yes-only set, but inside `counts by primary (in scope)`, where "in scope" means only "not filename or track-tag". I checked this against ~/.llama-harness/piece2/accept3/score/score_rows.jsonl: the three have `in_scope: false`, `taper_explicit: partial`, and DSO has `in_scope: true`, `yes`.

## Verification outputs
```
$ git diff a9016b5 HEAD -- . ':!docs' ':!CLAUDE.md'
[empty: 0 bytes]

$ git diff a9016b5 HEAD -- . ':!docs'
diff --git a/CLAUDE.md b/CLAUDE.md
index 6a4ccd5..3f35413 100644
@@ -625,6 +625,7 @@
+- **The taper's set/encore markers win** (held-backlog part 1, piece 2; ...)   <- the one 8ed8d0c bullet, nothing else

$ git diff 8ed8d0c HEAD -- CLAUDE.md
[empty: 0 bytes]

$ git diff --stat 8ed8d0c HEAD
 docs/superpowers/2026-10-22-taper-set-markers-evidence/acceptance.md     |   2 +-
 docs/superpowers/2026-10-22-taper-set-markers-sdd/README.md              | 673 ++++++++-
 docs/superpowers/2026-10-22-taper-set-markers-sdd/orch-r2/deferred-minors.md | 32 +
 docs/superpowers/2026-10-22-taper-set-markers-sdd/orch-r2/ledger.md      |  12 +-
 docs/superpowers/2026-10-22-taper-set-markers-sdd/verdicts/final-rev.md  | 160 +++
 docs/superpowers/2026-10-22-taper-set-markers-sdd/verdicts/t9-docs.md    |  17 +
 + 497 deletions under docs/superpowers/2026-10-22-taper-set-markers-sdd/evidence/orch*
 503 files changed, 891 insertions(+), 175859 deletions(-)
 (only file outside the record dir: docs/superpowers/2026-10-22-taper-set-markers-evidence/acceptance.md)

Record size (tracked): 8ed8d0c: 714 files, 10,756,663 bytes -> HEAD: 220 files, 2,204,368 bytes
du -sh record dir: 2.6M (includes git-ignored __pycache__ left in cpa-forms/, cpa2-forms/)
.py files remaining: 74 (listed above)

$ git log --oneline a9016b5..HEAD
ec0fb6a docs: taper markers acceptance: reconcile the 1-vs-4 miss counts
cc991f0 docs: taper markers in CLAUDE.md; acceptance record
e4075f3 docs: taper markers acceptance record (run 3); spec 2 wording on B4's window
b358726 docs: taper markers SDD record (ledgers, verdicts, evidence, acceptance run 3)

$ ./.venv/bin/python -m pytest -q
4474 passed, 1 skipped, 8 deselected, 26 warnings in 60.44s

$ git diff main -- packages/llama/src/llama/setlist.py
[empty: 0 bytes]

$ git diff --shortstat a9016b5 HEAD
 210 files changed, 22708 insertions(+), 1 deletion(-)

$ git rev-list --objects a9016b5..HEAD | git cat-file --batch-check (blobs)
208 blobs, 2,262,791 bytes            (record commit alone, a9016b5..b358726: 204 blobs, 2,089,043 bytes)
old history for comparison, a9016b5..8ed8d0c: 226 blobs, 3,297,786 bytes
```

## Concerns
- The new-object saving is smaller than the tree saving: 3.30 MB to 2.26 MB of new blobs, against 10.8 MB to 2.2 MB of tree content. Most of the dropped copies were byte-identical to blobs git already stored, so they cost little object storage. They still showed up in main's tree, which is what I1 was about. That is now fixed.
- Until the backup ref and the orphaned b95a099/783e753/8ed8d0c objects are pruned, the dropped bytes stay in this local repo's object store. They cannot reach main unless that ref is pushed. Delete `backup/taper-markers-record-8ed8d0c` only when the operator says so.
- I left the git-ignored `__pycache__` dirs under `evidence/orch/cpa-forms/` and `cpa2-forms/` in place, since I am not allowed to run `git clean -x`. Ignored pycache under the dropped dirs was removed by hand along with those directories.
