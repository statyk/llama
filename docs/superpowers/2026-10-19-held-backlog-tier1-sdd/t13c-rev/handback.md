# t13c-rev: Task 13c review (4826487..b6f353a)

### Spec Compliance

- ✅ Spec compliant.
  - Flag: `--no-repro-gate`, store_true, exact help text (scripts/replay_holds.py:703-704).
  - With the flag the ratio is still computed, the stderr line matches the brief verbatim, and exit 3 is unreachable (replay_holds.py:615-618, `if skipped:` precedes the `elif` gate).
  - summary.txt line 1 with the flag is `base reproduces {ok}/{n} (held, not needs-LLM; gate skipped: --no-repro-gate)` (replay_holds.py:658-659). Without the flag the string concatenates to the same text as before.
  - No-flag behaviour is byte-identical: the `elif` condition and its message, the `return 3` and the summary text are unchanged (replay_holds.py:619-622, 658-659). The focused suite confirms it: test_compare_writes_the_report_set_and_the_lists still asserts `base reproduces 1/1 (held, not needs-LLM)` (scripts/test_replay_holds.py:342).
  - `_gates` still runs first and is untouched (replay_holds.py:605). Moved-library with the flag exits 2 (test_replay_holds.py:409-416).
  - Parse check: grepping `base reproduces` across scripts/ and packages/ finds only the producer and the test at test_replay_holds.py:342. No parser to keep working.
  - Docs: both `cmp-$X-slice-*` commands carry `--no-repro-gate`, and the sentence is verbatim (plan lines ~1185-1188 in the diff).
  - Tests: all three required tests are present (test_replay_holds.py:389-416). For the no-flag case the implementer correctly names the existing pins (test_compare_refuses_a_baseline_that_does_not_reproduce at :379) and adds one more that asserts no summary or predicted list is written.
- ⚠️ Cannot verify from diff: the mutation table (m1/m2/m3) is the implementer's claim, and I did not re-run it. The design of the tests supports it. m2 is caught because the moved-library test uses `held_for_real=False`, so skipping `_gates` would let compare reach exit 0. m1 is caught by the `== 0` assertion. m3 is caught by the existing exit-3 tests. The 3574-passed full suite is also the implementer's claim; per the template I did not re-run it.

### Strengths
- Minimal, surgical change. Putting `if skipped:` before the unchanged `elif` makes the no-flag path textually identical to before.
- `getattr(args, "no_repro_gate", False)` keeps `compare()` callable with a hand-built Namespace.
- The moved-library test is built so that it actually discriminates m2. A base that reproduced would have made m2 survive. Choosing `held_for_real=False` was deliberate and correct.
- The new tests check exact strings (the full summary line 1 and the full stderr line), not substrings like "skipped".
- They also check that every OUTPUT_FILES entry exists under the flag, which covers "everything else written as for a passing compare".

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
- docs/superpowers/plans/2026-10-19-held-backlog-tier1.md:991: the plan's description of summary.txt still lists only `base reproduces N/M (held, not needs-LLM)`. It does not mention the `; gate skipped: --no-repro-gate` variant. The brief did not require this, but a future reader of that line would not expect the variant. A one-clause addition would fix it.
- scripts/test_replay_holds.py:415: the moved-library test asserts the generic `"arms differ"` prefix rather than `"digests differ"`. That is enough to separate exit 2 from 0, so it is not a coverage gap, just a slightly weaker pin than it could be. It matches the existing tests at :352/:362.
- Behaviour note, not a defect: with the flag and a base that would pass anyway (≥99 %), the lines still say "gate skipped". That matches the brief, which conditions the text on the flag, not on the ratio.

### Checks run
- Focused: `./.venv/bin/python -m pytest scripts/test_replay_holds.py -q -k compare` gave 14 passed, 33 deselected, with no warnings. Import resolved to the worktree (`.../held-backlog-tier1/packages/llama/src/llama/__init__.py`).
- Grepped scripts/, packages/ and docs/ for `base reproduces` and `no_repro_gate` (parse risk). The only consumer is the test at :342.
- `_two_arms` (test_replay_holds.py:294-309): mutate_cand is the 2nd positional, so `touch` changes only cand's digest, which is a true one-arm library move.
- Do-not-retune constants: the diff touches none (only scripts/replay_holds.py, its test, and the plan doc).

### Assessment

**Task quality:** Approved

**Reasoning:** The flag does exactly what the brief asked, and the no-flag path is textually unchanged. The three new tests are exact and each one discriminates one of the listed mutants. The only findings are a stale line in the plan doc and a slightly loose assertion.
