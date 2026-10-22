# t6-qual: CODE-QUALITY review of Task 6 (4284fa5..3e3c8ef)

### Strengths
- Every write in `fix` is inside `with show_unit(sws, view)` (cli.py ~3141-3202): token resolution, the clash check, `_split_include_targets`, all `_edit_overrides`, `_clear_hold`, and `_redo_show_locked`. No `_edit_overrides`/`_clear_hold` escapes before the `with`. The same holds in `_untitled_resolution` (cli.py ~1813-1830). I grepped `cli.py` for `file_lock`: none of `_edit_overrides`, `_clear_hold`, `_resolve_*_tokens`, `_split_include_targets` or `_resolve_show` takes a lock, so the show lock is taken once per invocation. `process_show` stays lock-free.
- Argument-only refusals (the `--untitled` combination list, `--set-title`/`--clear-title`/`--set-breaks`/`--set-encore` parse errors, `--suggest-titles` with file flags, `nothing to fix`) keep the same text and order, before any lock. The only text change is the intended no-`show.json` remedy suffix, which `refuse_no_show_json` now holds in one place instead of three copies.
- `typer.Exit(1)` raised inside the unit leaves the show byte-identical. I checked this with an out-of-tree probe in the scratchpad (not committed), run through the worktree venv. Both cases pass, with `.txn/` gone and `tree_bytes` equal:
  - a track-number `--exclude` on a show with no `show.json` (it keeps `_resolve_exclude_tokens`' own message);
  - the `--exclude`/`--include` clash.
- Nothing inside a unit writes to stdout. The edit lines are collected in `lines` and printed after the block. The `err=True` refusals go to stderr and come before any write. `process_show` logs to stderr (`status.configure_logging`).
- `_split_include_targets` is skipped when `inc` is empty, so `--exclude <file>` works without `show.json`.
- The failure tests are real pipeline runs (`packaged_gd73`, the ymsb tape with the fake backend, `SETLISTFM_API_KEY` scrubbed by conftest). They check whole-tree byte identity, including `.txn/` removal.
- The do-not-retune grep over the diff matches nothing. Both commits carry the orchestrator's trailer and the test result.

### Issues
#### Critical
None.
#### Important
None.
#### Minor
1. **Three failure tests can pass without reaching the failure they name** (test_fix.py, new block):
   - `test_failed_overrule_restores_every_file` asserts only `exit_code == 1` and byte identity. Any refusal that exits early and writes nothing would satisfy both, for example a `ShowChanged` or a future state gate.
   - `test_untitled_failure_after_the_overrule_restores_everything` has the same gap. It never checks that the gather stage, and then the brief stage, were actually called.
   - `test_a_failed_first_edit_removes_the_overrides_file_it_created` has the same gap.

   Fix: add `isinstance(r.exception, IAError)` / `"brief failed" in str(r.exception)` / `"boom" in str(r.exception)`, plus a call list in the untitled stub, as the sibling tests already do.
2. **A lone `--overrule` on a show that is not held now takes the show lock and snapshots** (cli.py ~3184-3190). Before, it printed `not held; nothing to overrule` at once. Now it waits silently, possibly for minutes, behind a `get` holding the show lock, then refuses `changed by another command`, or snapshots and discards for nothing. Fix: decide "not held" before the unit when `overrule` is the only flag, or leave it as a known cost. More broadly, `--no-run` edits now block silently on the lock with no "waiting" line. That follows from the spec's C1 step 2, but a waiting message would keep it from looking like a hang. It is outside this task's diff (`show_unit`/`file_lock`).
3. **Output order changed on a successful run without `--no-run`.** The edit lines (`metadata override updated`, `overrides.exclude = ...`) now print after the redo's stderr progress, where before they printed before it. During a long redo the operator gets no echo that the edit was taken. This is plan-mandated and harmless, noted only so it is not mistaken for a regression.
4. **`fix` is about 305 lines** (cli.py 2909-3212). The unit body (about 60 lines of the old edit-application code, re-indented) is a natural `_apply_fix_edits(sws, entry, ...) -> (lines, real_edit)`. That would also let Task 7's triage paths share the "collect lines, print after the unit" pattern. Not merge-blocking: the diff is mostly re-indentation with unchanged logic, and factoring now would widen Task 6's surface.
5. **No in-suite test pins the "typer.Exit inside the unit is byte-identical" claim** for the clash refusal or a track-number `--exclude` on a show with no `show.json`. My probe passes, so this is coverage only. Consider adding the two short tests.

### Assessment
**Task quality:** Approved
**Reasoning:** The restructure keeps every existing refusal and message. Every write and the redo sit inside one `show_unit`, with no nested lock and no stdout inside the unit, and a refusal inside the unit restores byte-identical (probed). The remaining items are weak test assertions and small behaviour or maintainability notes.
