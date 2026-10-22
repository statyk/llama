### Finding Verdicts
1. **ADDRESSED.** All three tests now pin the intended failure, not just any refusal that writes nothing:
   - `test_failed_overrule_restores_every_file` asserts `isinstance(r.exception, IAError) and "archive down" in str(r.exception)` (packages/llama/tests/test_fix.py, fix diff hunk at ~L903-905).
   - `test_untitled_failure_after_the_overrule_restores_everything` records `stages`, then asserts `stages == ["gather", "brief"] and "brief failed" in str(r.exception)` before checking `tree_bytes` (~L950-962).
   - `test_a_failed_first_edit_removes_the_overrides_file_it_created` asserts `"boom" in str(r.exception)` (~L918-920).
2. **ADDRESSED.** Both new tests reach the in-unit refusal, not one taken before the lock:
   - (a) `test_a_typer_exit_inside_the_unit_leaves_the_show_byte_identical` asserts "name the same file(s): a.mp3". That message is produced only at cli.py:3145-3147, which sits inside `with show_unit(sws, view):` (cli.py:3134).
   - (b) `test_a_track_number_exclude_without_show_json_refuses_and_changes_nothing` asserts "resolving a track number needs show.json", which is `_resolve_exclude_tokens`' own message (cli.py:1496). Its only callers are at cli.py:3137-3138, inside the unit. The C4 pre-lock gate (cli.py:~3127) refuses only narration/overrule/include, so `--exclude 3` gets past it.
   - Both tests assert `tree_bytes` is equal (helpers.py:43 excludes only the top-level `.lock`) and that there is no `.txn/`. `show_unit` catches `BaseException` and restores (show_unit.py:137-143), so `typer.Exit` is covered.
3. **ADDRESSED.** The text now sits inline right after the `llama fix <name> <edit-flags>` entry, under "**One unit (2026-10-21):**" (CLAUDE.md:65). I compared the body mechanically against the removed bullet and it is byte-identical. The redo entry now reads "`llama redo <name> --from <stage>` (one unit, above)" (CLAUDE.md:66), and the text it refers to is directly above it, so the pointer is correct. The old standalone bullet is gone.

Fix report: it names the covering tests and gives the literal command `./.venv/bin/python -m pytest packages/llama/tests/test_fix.py packages/llama/tests/test_triage.py -q`. It quotes the result only as a summary ("134 passed"; full suite "4032 passed, 1 skipped, 8 deselected"), not verbatim output. That is acceptable, and the count matches the +2 tests.

### New Breakage in the Fix Diff
None at Critical or Important. One Minor:
- CLAUDE.md:65-66: the fix entry used to end `` `--include`), `` and run straight on into the comma-separated command list. It now ends `` `--include`). **One unit…** ``, so `llama redo …` begins after a full stop, as a sentence fragment. This is cosmetic and the meaning is intact.

### Out-of-Scope Observations
- The implementer's fix section says round 1's red check "reverted cli.py in the live worktree (restored, git clean)". That breaks mandate 5, which allows deliberate breakage only in a scratch copy. My own check found nothing left behind: the session-start git status was clean and HEAD is f616ea5. Still, the manager should restate the mandate to future implementers.
- `test_a_failed_first_edit_removes_the_overrides_file_it_created` checks the message but not the exception type (`LlamaError`). This is non-blocking, since "boom" is unique to the stub.

### Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage.
