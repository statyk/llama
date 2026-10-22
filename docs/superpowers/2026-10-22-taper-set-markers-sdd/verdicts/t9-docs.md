STATUS: DONE_WITH_CONCERNS

Commits (branch held-backlog-taper-markers, base a9016b5):
- b95a099 docs: taper markers SDD record (ledgers, verdicts, evidence, acceptance run 3)
- second commit: acceptance.md + spec section 2 wording ("with no numbered step-1 break before that hit, the taper still owns the structure")
- third commit: "docs: taper markers in CLAUDE.md; acceptance record" (one bullet after the venue tie-break paragraph)
(acceptance.md was kept in its own commit, not folded.)

Test: ./.venv/bin/python -m pytest -q -> 4474 passed, 1 skipped, 8 deselected (run before each commit).

Record: docs/superpowers/2026-10-22-taper-set-markers-sdd/ now 742 files, 12936 KB (du). 53 verdicts, 3 ledgers, evidence/orch and evidence/orch-r1 (<=256 KB), acceptance/ (7 files), README.md. evidence/LARGE-FILES.txt: 17 entries plus a 3-line header.

Concerns:
- score_summary.txt disagrees with itself on misses: the in-scope line says miss 1 of 64 graded, the all-rows block and by-primary table say 4 misses of 67 (all desc-set-header). Not reconciled; acceptance.md gives both and lists all 4.
- Run-1 explanations (acc-explain, pre2-cleared, pre3-*) are cited for run 3; flags/structures were unchanged by the fixes except as noted (rescreen2 covers run 2; run 3 had none, ruling R20).
- step3.txt does not print run 3's replayable not-owned row count (run 2: 3355); acceptance.md says so.
- Per-state counts for "needs-llm not owned" are not available (count-only tier).
