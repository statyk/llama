# t11-impl handback: llama deliver and clear-mark take the station lock

Status: DONE_WITH_CONCERNS (concerns are R6 findings and one small brief deviation; no write path changed)
Commit: 4a916ddb llama: deliver and clear-mark take the station lock

## What was implemented
- `cli.py`: imports `station_lock`.
  - `_deliver_one`: inside `file_lock(show_ws.lock)`, after `_awaiting_fix_check`: `target_dir.mkdir(parents=True, exist_ok=True)`, then
    `with station_lock.for_package(out, command=f"llama deliver {entry.slug}")` around a new helper `_deliver_locked` (the old body verbatim:
    `_read_destination_manifest` -> voiced / equal-marked refusals -> gate -> `_sweep_swap_leftovers` -> `_replace_destination` or `shutil.copytree`).
    Ledger record and `_purge_after_delivery` run after release, still under the show lock. The gate refusal moved into a small `_gate_check` helper (same text).
  - `_deliver_batch`: `except station_lock.StationLocked` prints `{slug}: {exc}`, then `not attempted: <this and the rest>`, `raise typer.Exit(1)`. Other errors keep continue-on.
  - `_clear_mark_one`: inside `file_lock`, `with station_lock.for_package(out, command=f"llama clear-mark {slug}")` spans `read_station_manifest` through `clear_mark`, `campaign.add_clear` and any `put_back`; the purge runs after release. `emcee_running()` check kept.
  - Single `deliver <name>` and `clear-mark` refuse via their existing LlamaError handling (exit 1).
  - `_confirm_plan` is never under the station lock (lock only inside `_deliver_one`, after the prompt).
- `station_mark.py` docstring: the brief's replacement text, verbatim.
- `packages/llama/CLAUDE.md`: new "Station lock (shared with emcee)" paragraph after "emcee does not share this locking scheme".
- `packages/llama/tests/test_no_emcee_imports.py` (R11): emcee's guard with names swapped; same regex shape (`from|import emcee` and `__import__/import_module('emcee`), applied to src and tests. emcee's version has no allowance list, so none carried over. No current offenders.

## Deviation from the brief (please rule)
The brief says mkdir the station folder first thing after `_awaiting_fix_check`. Done that way that breaks three existing tests
(`test_held_show_refused`, `test_missing_audio_refused`, `test_unpackaged_show_refused`, all `assert not dest.exists()` after a gate refusal).
Fix kept them green unchanged: when `target_dir` is not a directory, `_gate_check` runs before the mkdir. With no folder there is no destination
manifest, so the gate is the only refusal the locked path could give, and the output is identical; a refused delivery still creates nothing.
The gate then runs a second time under the lock (cheap, library-only).

## Tests (TDD)
RED: `./.venv/bin/pytest packages/llama/tests/test_deliver_cmd.py packages/llama/tests/test_clear_mark.py packages/llama/tests/test_no_emcee_imports.py -q`
-> `8 failed, 105 passed`: both lock-span params, held-lock deliver, batch stop, both lock-order tests, clear-mark span and held-lock: all for lack of a lock
(e.g. `assert ['show'] == ['show', 'station']`). Passing at RED, as non-regression pins: awaiting-fix-takes-no-lock, no-lock-while-confirming,
nested-inbox, and the two import guards.
GREEN: same command -> `113 passed`. `./.venv/bin/pytest packages/llama -q` -> `3928 passed, 7 deselected, 24 warnings` (fork DeprecationWarnings from
multiprocessing tests, not from these tests). Full `./.venv/bin/pytest -q` -> `6853 passed, 1 skipped, 8 deselected, 26 warnings`.
New tests: the nine in the brief (lock-span parametrized overlay/replace; `test_library_show_lock_is_taken_before_the_station_lock` exists in both files),
plus the two import guards. Span tests spy each call and require the lock file to exist and say `tool: llama`, and check `command:` text and release.

## R6 audit: what a SIGTERM/SIGHUP (os._exit, no caller cleanup) leaves behind
Station writes under the lock:
1. `_sweep_swap_leftovers` rmtree of `.{slug}.deliver-*`: a partial dot dir; the next deliver sweeps it again. Safe.
2. `_replace_destination`:
   - during `copytree(pkg, tmp)`: partial `.{slug}.deliver-<uuid>`, `out` untouched; swept next time. Safe.
   - between `out.rename(old)` and `tmp.rename(out)`: **`out` is gone from the station**; the original (possibly voiced) is at `.{slug}.old-<uuid>`,
     the complete new copy at `.{slug}.deliver-<uuid>`. The `except` that puts the original back does not run under os._exit. Both are dot-prefixed,
     so emcee/transmitter don't see the show until someone re-delivers. The next deliver sweeps the `.deliver-*`, warns about (never deletes) the `.old-*`,
     finds no destination manifest and overlays a fresh copy. Recoverable and nothing is lost, but not self-healing, and a voiced original then needs a
     hand restore from `.old-*`. Same window as SIGKILL today.
   - during `rmtree(old)`: a partial `.old-*`; the next deliver warns about it ("may hold voiced audio"). Safe.
3. **Overlay `shutil.copytree(pkg, out, dirs_exist_ok=True)` does NOT meet R6**: it copies in place into the live package (copy2 truncates and rewrites each file).
   An exit mid-copy leaves a mix of new and old files, possibly one truncated (audio or `manifest.json`). A truncated manifest makes the next deliver refuse
   ("cannot read ... check the station copy by hand"); a truncated audio file with an intact manifest is fixed by a re-deliver but could air meanwhile.
   Only reached for an unvoiced, unmarked destination with the same track list or no manifest. Pre-existing and identical under SIGKILL; not changed, per the brief.
4. clear-mark writes (`station_mark._swap_in`, used by `clear_mark` and `put_back`): unique temp `.manifest.json.llama-<hex>.tmp` in the package dir, flushed,
   then `os.replace`. Atomic: an exit leaves at most that stray dot temp, which nothing sweeps.
   Between `clear_mark` and `campaign.add_clear`: the station copy is cleared, `campaign.json` has no `clears` row, no put-back, library audio not purged.
   A rerun says "not marked; nothing to clear". The air state is right; only the audit row and the purge are missing.

## Other notes
- clear-mark when the whole `delivery_path` folder is missing now refuses with `cannot create the station lock at .../.lma-station.lock: [Errno 2] ...`
  instead of `station copy unreadable: no directory ...` (the lock is taken before the read). Still exit 1, nothing written. No test covered that case.
- `_deliver_locked` is a helper I extracted instead of re-indenting the body; the body is unchanged.
- No linter in the venv (no ruff/pyflakes); not run.

## Self-review
Diff checked against the brief: lock order show then station; prompt outside the lock; ledger and purge after release; batch stop text; docs text verbatim
where given. Tests exercise behaviour through the CLI with spies on real functions, not mocks of the lock itself (except the batch test, which forces
`StationLocked` on the 2nd acquire, as the brief specifies).
