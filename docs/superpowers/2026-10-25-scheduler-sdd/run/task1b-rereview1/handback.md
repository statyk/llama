# task1b-rereview1: re-review of fix round 1 (30a359a..cd80cbe)

### Finding Verdicts

1. **(Important) File-set key not exercised: FIXED.**
   - `mark_awaiting_fix` (helpers.py:342) now rewrites manifest.json in place and `os.utime`s only that file. `time`/`os` are already imported.
   - The in-place write creates no file and renames nothing, so the package directory's mtime and every broadcast.m3u entry's mtime are untouched.
   - `file_set_key_and_sizes` (station.py:99) hashes `[rel, size, mtime_ns]` over the m3u entries only, and manifest.json is not one of them. So the key really is unchanged.
   - The key assertion compares against the planned row's key, not a value recomputed on both sides. `victim = rows[1]`, where `rows` is the return value of `pipeline.plan_step(st, NOW)`, which ran before the mark. Only the left-hand side is recomputed after marking.
   - Mutation check: scratch copy at cd80cbe, with `transmitter`/`tests_transmitter` proven to resolve inside it. I restored the old `set_age(pkg, age_s)` helper and predicted `test_render_step_drops_a_planned_show_marked_awaiting_a_fix` would go red at that assertion. It did: `AssertionError: assert '1b186e87d1520c00b822' == '53fb1392b193716e20c7'`. The other two pipeline mark tests stayed green, which is the expected result.
   - The comment at test_pipeline.py:1264 ("manifest only") is now true.
   - Quiet period: `_evaluate` takes `newest` over manifest.json, broadcast.m3u and dj-audio/*. The manifest is aged `age_s` (3600 s) and the rest keep build_package's 3600 s age, so the quiet_s=600 tests in test_station still see a quiet package. In the null-mark case this means eligible, not held as "changed Ns ago".
   - The other helper users (test_station 341/351/357/367/376/385, test_pieces 200/207, test_pipeline 1283) all pass. Their reasons[0] asserts and slug-list asserts pin the awaiting-fix reason itself, not a side effect of the key changing.
   - `test_render_step_lets_a_marked_show_already_on_air_finish_as_planned` is now stronger. With the key unchanged, the only thing it isolates is the awaiting_fix leg.

2. **(Minor) Reason cap: FIXED.**
   - `MAX_REASON_CHARS = 200`. When the whitespace-normalized reason is longer than 200, it becomes `reason[:199] + "…"`, exactly 200 characters including the ellipsis. Exactly 200 passes through unchanged.
   - Tests: a 999-char reason gives exactly 200 characters after the prefix and ends with `…`; an exactly-200 reason is untouched.
   - Scratch mutants, each with its red test predicted in advance and each going red as predicted:
     - `>` changed to `>=`: the exactly-200 test fails.
     - `[:MAX-1]` changed to `[:MAX]` (201 characters): the capped test fails.
     - Cap disabled: the capped test fails.
   - Nit, not blocking: the truncation can land on a space, giving "word …". This is cosmetic only.

### New Breakage in the Fix Diff
None.
- The full transmitter suite in the worktree, using the worktree's own interpreter (`transmitter.__file__` resolves in the worktree), gives 861 passed, 1 skipped.
- The working tree is clean after the run.

### Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage.
