### Spec Compliance

- ✅ Spec compliant. Every file the brief lists has its hunk: cli.py (`_deliver_one`, `_deliver_batch`, `_clear_mark_one`), the station_mark.py docstring (verbatim), packages/llama/CLAUDE.md, and both test files with all nine named tests. The R11 guard is added too.
- R12 accepted deviation verified. cli.py:2700-2704: when `target_dir` is not a directory, `_gate_check` runs before the `mkdir`. With no folder, `_read_destination_manifest(out)` returns None inside the lock, so voiced and marked are False and the only refusal left is the gate. `_gate_check` raises the same text as the old inline block (diff `_gate_check` vs removed lines), so the output is identical. The gate runs again under the lock (cheap; library-only; `catalog.deliver_refusals` catalog.py:138). Paths that create the folder and then refuse: none deterministic. Only these remain: (a) `acquire` failing with a non-EEXIST OSError (`cannot create the station lock`, station_lock.py acquire) in the folder it just created, e.g. EACCES on the share; (b) a concurrent writer creating the lock or `out` in that instant; (c) library state changing between the two gate runs, which nobody can do while llama holds the show lock. All are races or environment failures, not refusals of the show.
- ⚠️ Cannot verify from this diff: CLAUDE.md says `bulk_apply` mark/unmark take the lock. That is brief-mandated text, and bulk_apply's own change belongs to a later task. The controller should confirm it lands.

### Named-risk checks

1. Station reads/writes outside the `with`. Deliver: `_read_destination_manifest`, the voiced and equal-marked checks, `_sweep_swap_leftovers`, `_replace_destination` and the overlay `copytree` are all inside `_deliver_locked`, called within `for_package` (cli.py:2706-2707). The awaiting-fix read is library-only: `campaign.read_record(show_ws)` (cli.py:2608-2611). That makes it correct outside, and `test_deliver_takes_the_lock_after_the_awaiting_fix_refusal` pins it. The ledger record and `_purge_after_delivery` run after release as the brief requires. The purge only reads the station copy to verify it (`catalog.purge_package_audio(show_ws, out)`) and writes nothing there, which meets "through the last station write". Outside the lock remain the `target_dir.is_dir()` stat and the `mkdir`, which are brief/R12-sanctioned, and the batch's planning reads (`_destination_is_voiced`, `_fixed_for_delivery`), which must stay outside because they precede the prompt. Clear-mark: the lock is the first thing inside `file_lock` (cli.py:2969-2970), before `read_station_manifest`, and spans clear_mark, add_clear and put_back. The purge comes after it. The span tests pin both commands, including the put-back path.
2. Nesting/re-entry. The only callers of `_deliver_one` are cli.py:2826 (batch) and cli.py:2897 (by name). Neither holds a station lock. The batch's awaiting re-check takes only `file_lock` and releases it before `_deliver_one`. The only `for_package` uses are cli.py:2706 and cli.py:2970, and neither callee acquires again. `StationLockReentry` is a RuntimeError, not a LlamaError, so a bug would crash rather than be swallowed by the batch's `except LlamaError`. Correct.
3. Batch stop. The `except station_lock.StationLocked` precedes `except LlamaError` (cli.py:2827), and `StationLocked` subclasses LlamaError, so the order matters and is right. `rest = kept[i:]` is exactly this show and every later one. See Minor 1 for the unreadable or awaiting slugs it can include.
4. Prompt inside lock. `_confirm_plan` (cli.py:2808) runs before the loop, and no lock is held there. `test_deliver_batch_takes_no_lock_while_confirming` asserts `_held is None` and no lock file. Neither by-name deliver nor clear-mark prompts.
5. Relative `--dest`. `for_package` uses `Path(out).absolute().parent`, where `out = target_dir / name`, so the folder is `abs(target_dir)`. `--dest .` gives `Path(name)`, whose `.absolute().parent` is cwd. Correct.
6. Multi-line `str(exc)` in the batch line. `StationLocked`'s message is a header line, then two-space-indented holder lines, then the hint (station_lock.py `StationLocked.__init__`). Prefixed with `{slug}: `, it reads `s2: the station is locked by another writer (<path>):` followed by indented holder lines and the emcee hints, then `not attempted: ...`. Sensible. The holder text is control-character-escaped (`holder_text`).
7. R11 guard. I ran it: `./.venv/bin/pytest packages/llama/tests/test_no_emcee_imports.py -q` gives 2 passed, so it is collected, and `llama.__file__` resolves inside this worktree. I probed the regex: it matches `import emcee`, `from emcee.x import y`, an indented `import emcee.cli`, `import_module('emcee.x')` and `__import__("emcee")`. It does not match `import os, emcee` (a comma-list), `import emceex` or a comment. Both statement forms are caught. The comma-list gap is the same as in emcee's guard (Minor 3). The guard file does not match itself.

### R6 audit (implementer's description)
It is accurate against the code. `_replace_destination` (cli.py:2528-2550) does move `out` aside and then rename the temp in. An `os._exit` between the two renames skips the put-back `except`, so the show is hidden under dot names. `_sweep_swap_leftovers` deletes `.deliver-*` and only warns about `.old-*`. The overlay `copytree(..., dirs_exist_ok=True)` copies in place, as described. The clear-mark window between `clear_mark` and `add_clear` is as described. I found nothing worse. One addition worth ledgering beside them: station_lock.py's module docstring asserts "every station write is an atomic rename … Station writes must stay atomic renames", and the overlay path contradicts it today. Fix the docstring or the overlay when the ledgered item is handled. A SIGTERM after release but before `ledger.record` falls under the restored default disposition: the station copy is delivered with no ledger row and no purge. That is the same as before this task and is fixed by re-delivering, so it is not worse.

### Strengths
- Extracting `_deliver_locked` keeps the old body intact and makes the lock span obvious: one `with` line covers it (cli.py:2706-2707).
- R12's pre-check is minimal and keeps the existing `assert not dest.exists()` tests green, unchanged.
- The tests spy real functions and check that the lock file exists with `tool: llama` at each station call, plus the `command:` text and release. They check lock order through both wrappers, held-lock refusals with an untouched tree, ledger and library audio, and the exact `not attempted` list.
- The batch's `StationLocked` handler sits ahead of the generic `LlamaError` handler with a comment, and re-entry bugs are not swallowed.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. cli.py:2829 `rest = [x.slug for x in kept[i:]]` includes later slugs in `unreadable`, which the plan already listed as refused and the loop would skip. It also includes `awaiting` slugs, which may refuse. "Not attempted" is literally true for them, but they appear twice in the operator's view. Optionally filter `unreadable` out, or leave as is. It is exact per the brief's wording ("this and the remaining slugs").
2. clear-mark with a missing `delivery_path` folder now refuses with `cannot create the station lock at …: [Errno 2] …` instead of `station copy unreadable` (the implementer noted this). It still exits 1 and writes nothing, but the message is less direct and no test covers it. Consider a test pinning exit 1 and no write.
3. test_no_emcee_imports.py:12-16 does not catch `import os, emcee`. This has parity with emcee's guard, so if it is fixed, fix both.
4. packages/llama/CLAUDE.md: the new "Station lock (shared with emcee)" paragraph sits directly after "**`emcee` does not share this locking scheme**". Read quickly, the two contradict each other. Something like "does not share this flock scheme" would remove the ambiguity.
5. test_clear_mark.py: the second scenario of `test_clear_mark_lock_spans_read_through_clear_and_put_back` re-wraps already-spied functions, so the first list keeps being fed (the comment says so). That is harmless but fragile. Splitting it into two tests would be cleaner.

### Assessment

**Task quality:** Approved

**Reasoning:** The station lock spans the first station read through the last station write in both commands, and it sits inside the show lock. It is never held across the prompt, and there is no re-entry. The batch stops correctly with an exact list. R12 keeps the output identical, and no deterministic path creates the folder and then refuses. The findings are cosmetic or about coverage.
