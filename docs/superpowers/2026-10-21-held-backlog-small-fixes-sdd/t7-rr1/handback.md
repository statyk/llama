### Finding Verdicts
1. ADDRESSED. `test_a_failed_untitled_resolution_restores_and_returns_to_the_prompt` (packages/llama/tests/test_triage.py:748-759) makes every track unresolved so `[u]` is offered, makes `_redo_show_locked` raise `LlamaError("boom")`, and feeds `u\ny\ns\n`. It asserts exit 0, `error: boom`, `[u]ntitled` printed twice (that string occurs only in the prompt text, cli.py:1716, so this is a return to the same show's prompt), and `tree_bytes(ws.dir) == before`. I checked that it fails without the wrapper: in a scratch `git archive` copy I removed the try/except around `[u]` (cli.py:1951-1956) and confirmed `llama.__file__` resolved inside the scratch copy. The test then FAILED at test_triage.py:757 (`exit_code == 0`), which matches the implementer's claim.
2. ADDRESSED. test_triage.py:736-737 now asserts `"no show matches"` and `"gratefuldead-1974-01-01"`, and it still asserts exit 0 and one PROMPT.
3. ADDRESSED. test_triage.py:744-746 asserts exit 0 and `count(PROMPT) == 2`. The input really does answer the returned prompt: `_metadata_editor` has exactly five prompts (venue, city, date, titles, breaks; cli.py:1746-1751). `m`, `New Hall` and four blanks answer the first prompt and the editor, and `s` answers the second PROMPT. If the editor took more or fewer inputs, the second prompt would hit EOF and abort, so the run would not exit 0.
4. ADDRESSED. cli.py:1835 calls `view = capture_view(entry.ws)` before the `_resolve_show` re-resolve at cli.py:1840 and before `_print_show_entry` at cli.py:1844. On the specific doubt:
   - **Same directory.** `catalog.resolve_show` turns an existing path into its basename (catalog.py:344-346) and looks it up in `iter_shows(root, …)`. The re-resolved `entry.ws.dir` is therefore `root/shows/<slug>`, the same directory the old entry came from. That is also the directory the unit protects (`show_unit(entry.ws, view)`, cli.py:1966).
   - **Removed show.** `capture_view` cannot crash: `provenance.exists()` returns False, and `_read` catches `FileNotFoundError`, which a missing parent directory raises (show_unit.py:50-60). The re-resolve then raises `LlamaError` ("no show matches"), which is printed before the return, so the skip behaviour is unchanged. The tightened finding-2 test covers this path.

### New Breakage in the Fix Diff
None. One Minor, non-blocking point: no test pins finding 4's ordering. If `capture_view` moved back below the re-resolve, a change landing between the two reads would go unnoticed, and nothing would fail. The finding did not ask for a test, and the window can only be hit by a concurrent process.

### Out-of-Scope Observations
None.

### Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage. The fix report names the covering test and the literal command `./.venv/bin/python -m pytest -q`, with output `4041 passed, 1 skipped, 8 deselected`. That is the previous 4040 plus the one new test.
