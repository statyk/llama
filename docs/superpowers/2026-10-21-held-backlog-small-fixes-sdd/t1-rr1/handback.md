### Finding Verdicts
1. **ADDRESSED.** `packages/llama/tests/test_stage_vet.py` (the hunk at old line 786): `test_right_show_gate_counts_curly_and_straight_apostrophes_both_ways` is now parametrized both ways, `[tape0-research0]` with curly on the tape and `[tape1-research1]` with curly in the research. It asserts `info["asserted"] == 4 and info["unknown"] == []`. I checked the RED claim with my own mutant. In a scratch `git archive` copy, I reverted only `vet_research.py:193` to `research_known = [normalize_song(s).split() for s in vetting.asserted_songs]`. Run with `PYTHONPATH` shadowing (`llama.__file__` confirmed inside the scratch copy) and the bytecode cache off, `[tape1-research1]` FAILED and `[tape0-research0]` passed. That matches the fix report.
2. **ADDRESSED.** `packages/llama/tests/test_structure.py:22-23`: `contains_sequence` and `fold_curly_apostrophes` now sit in a top-level `from llama.structure import (...)` that replaced the old `fuzzy_norm_title, fuzzy_title_eq, title_components` line. The mid-file import and its `# noqa: E402` are removed. Both names are still used bare, at lines 2080 and 2088, so neither import is unused.
3. **ADDRESSED.** `CLAUDE.md:778-780`: the inserted clause is re-wrapped across three lines of 78 columns or fewer, which matches the paragraph. The text is the same as before, word for word: "folding `&`→`and`, and curly apostrophes (`’`/`‘`) to `'` (`structure.fold_curly_apostrophes`, also applied by vet_research's and brief's song matchers on both sides),".

Fix report evidence: it names the covering test (the parametrized right_show_gate test, and which case went RED) and gives the GREEN results: test_stage_vet.py + test_structure.py 318 passed; full suite 3975 passed, 1 skipped, 8 deselected. That is one more than the 3974 baseline, which fits one test turning into two parametrized cases. It does not state the literal command line.

### New Breakage in the Fix Diff
None.

### Out-of-Scope Observations
- Minor: the fix report gives results but no literal pytest command. It would help if later fix reports stated it.

### Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage.
