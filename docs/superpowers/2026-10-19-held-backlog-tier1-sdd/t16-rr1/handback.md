### Finding Verdicts

- **[Important] No test makes the tape-fraction clause the only reason right_show_gate declines** — ADDRESSED. packages/llama/tests/test_stage_vet.py:552 adds `(10, 0, 4, ["1973-06-10"], False)  # 0.4: only the tape fraction fails`; the brief's row at :551 is kept with the corrected comment `# fewer than 4 asserted`. Checked against vet_research.py:183-191: for that row resolved=10, asserted=4 (passes RIGHT_SHOW_MIN_ASSERTED=4), unknown=2 <= 4, unresolved_n=0, date_flags_raw=[], own_full True; only `4 >= 0.5*10` fails. Ran the gate read-only on the live tree: `(False, {'asserted': 4, 'resolved': 10, 'ratio': 0.4, 'unknown': ['Alpha','Beta'], 'date_text': '1973-06-10'})`, so deleting the clause (f1) or making it vacuous (f2, `0.5 * len(asserted)`) necessarily flips this row to True. The fix report's mutation table (handback.md:56-60) shows both caught by `test_right_show_gate_table[10-0-4-dates2-False]` only, as predicted; consistent with the reading.
- **[Minor] `_guard_prose` docstring non-raw with `\s+` (SyntaxWarning)** — ADDRESSED. packages/llama/src/llama/stages/brief.py:168 now opens `r"""`; wording unchanged in the diff (one-line change). The only backslash in the docstring is `\s+`, so raw-ness changes no other text. Check run: `python -W error -c "compile(open('.../brief.py').read(),...)"` -> compiles clean (only a ResourceWarning from the one-liner's own unclosed open()).

### New Breakage in the Fix Diff

None. Diff is 3 insertions / 2 deletions (one test row + one comment, one docstring prefix).

### Out-of-Scope Observations

None.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.
