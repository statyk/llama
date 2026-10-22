### Finding Verdicts
1. **An operator venue override takes no tie-break, so no tie-break city leaks** — ADDRESSED. gather.py:1407 is now `tie = venue_tie_break(candidate, sel) if overrides.venue is None else None`. Every use of `tie` (gather.py:1423, 1432-1435, 1453) already guards on `is not None`. The override block (gather.py:1472-1478) is unchanged, so a venue-only override now ships the vote's city. Test: test_stage_gather.py `test_an_operator_venue_override_takes_no_tie_break_city`. It is a true tie as grouping counts it: `_cand` builds through `_make_candidate`, with raw strings "Frogs Hall" and "Frogs Hall Theatre" at one each. Its cities differ only in case, which is the jackiegreene shape. Check run: in a scratch copy at a9d9c78 with 36473d8's gather.py and cli.py, `llama.__file__` resolved inside the scratch tree, and the test FAILED with `'angels camp, california' != 'Angels Camp, California'`. The city-only pin `test_a_city_only_override_keeps_the_tie_broken_venue` passes both before and after the fix, as a pin should.
2. **After a ShowChanged refusal, triage re-resolves, re-captures and re-prints the show** — ADDRESSED. cli.py:1978-1985 (edit unit) and cli.py:1956-1960 (`[u]`) catch `ShowChanged` before the generic arm and call `return _interactive_resolve(config, ia, ledger, entry)`.
   - Ordering: the re-entry captures the view at cli.py:1837 BEFORE it re-resolves at cli.py:1842.
   - Lock: no prompt runs under the show lock. `ShowChanged` is raised inside `show_unit`'s `file_lock` before the yield (show_unit.py:127-134), so the lock is released before the handler runs.
   - Scope: only `ShowChanged` takes this path. Every other `LlamaError`/`HerderError` still prints the error and continues to the same prompt.
   - Removed show: `not entry.ws.provenance.exists()` leads to `continue`, which is the old handling.
   - Caller semantics: unchanged. The function still returns None, `q` still raises `typer.Exit`, and a show no longer held after the re-resolve prints and returns, as on first entry.
   - Test: `test_a_changed_show_refuses_once_then_the_retry_on_the_reprinted_prompt_applies`. It FAILED on the pre-fix cli.py in the scratch check.
3. **Triage [m]/[i] print "updated" or the routing note only after the unit succeeds** — ADDRESSED. The `lines` echo moved out of the `with show_unit(...)` body to cli.py:1989-1990, after the except arms, so it runs only on success.
   - Every success path still prints once: only [m] (cli.py:1914) and [i] (cli.py:1906) fill `lines`, and the [u] path has its own after-unit echo (cli.py:1826-1827).
   - No edit path lost its message: `_edit_overrides` and `_clear_hold` contain no echo.
   - No new "restored"/"left as it was" wording was added.
   - Tests: `test_a_failed_metadata_edit_restores_the_overrides` (absence asserted), the new success test, and the new `[i]` failure test. Both failure tests FAILED on the pre-fix cli.py; the existing `test_include_on_an_operator_excluded_row_un_excludes_instead` (test_triage.py:545) still pins the success-path routing note.
4. **A track-number --exclude/--unexclude with no show.json names the remedy** — ADDRESSED. cli.py:1496-1497 appends `; rebuild it with: llama redo <slug> --from gather`, the same wording as the existing refusal at cli.py:3009. test_fix.py:995 asserts it and FAILED on the pre-fix cli.py.
5. **Docs** — ADDRESSED. brief.py:121-122 now names `_song_norm`, curly apostrophes folded first. show_unit.py:14-15 adds the "cannot remove leftover snapshot" refusal to limitation 3, matching `_discard_leftover` (show_unit.py:115-122).

Check run: scratch copy `git archive a9d9c78`, with 36473d8's cli.py and gather.py swapped in. Tests: the 2 gather tests, test_triage.py and the test_fix no-show.json test. Result: 5 failed (exactly the new and extended tests), all others passed. This matches the implementer's RED claim. The implementer's report names the covering tests and the full-suite count (4046 passed, 1 skipped, 8 deselected) but shows no raw output. I did not re-run the full suite, per scope.

### New Breakage in the Fix Diff
- Minor, test gap: test_triage.py:765-777 does not pin the "re-print" half of item 2. A mutant that re-captures `view` and then `continue`s gets the same counts: PROMPT==2, one refusal, calls==["gather"], overrides merged. The test cannot tell it from the real fix. Asserting the show entry header is printed twice would pin the re-print. The removed-meanwhile branch (cli.py:1958-1959 and 1980-1981) also has no triage test.
- Minor, docs wording: CLAUDE.md:62 says the refusal path "re-resolves, re-captures and re-prints". The code captures first and then re-resolves (cli.py:1837 then 1842), the ordering slice C settled. The words name the right steps in the wrong order.
- Minor, edge: the removed-or-changed test at cli.py:1958 and 1980 is `not entry.ws.provenance.exists()`, not show_unit's own condition (`expect.provenance and not now.provenance`). A held show captured with no provenance.json whose overrides change meanwhile therefore still takes the old `continue` path, and the dead end remains. This needs a held show with no provenance, which is close to unreachable.
- Cosmetic: the re-entry runs inside the `except` block, so a later Ctrl-C or `typer.Exit` traceback chains "During handling of ShowChanged". Recursion depth equals the number of consecutive refusals. Neither has a behavioural effect.

### Out-of-Scope Observations
- The CLAUDE.md "Venue tie-break" bullet (the slice B paragraph) lists where the tie-break applies but does not say an operator venue override now suppresses it. It remains accurate as written, since the override arm was never listed, but one clause would make item 1's rule discoverable.

### Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage. Only Minor items remain: the test gap, the CLAUDE.md step order and the edge case above. None blocks.
