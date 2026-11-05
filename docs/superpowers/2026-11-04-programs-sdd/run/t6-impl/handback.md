# t6-impl handback: emcee `run` and `voice` take the station lock per package

Status: DONE_WITH_CONCERNS (the concerns are minor and outside the brief's file list)
Commit: 840e74fe emcee: run and voice take the station lock per package

## What was implemented
- `packages/emcee/src/emcee/cli.py`
  - `run`: each `_process_one(...)` runs inside `with station_lock(status.path.absolute().parent, command="emcee run")`. The `with` sits inside the loop, after the `Proceed?` question, so the lock is held for one package and released before the next. `except StationLocked` comes before the generic handler. It prints `error: {slug}: {exc}`, the indented `exc.details` (the holder lines and the lock show/clear hint), then `not attempted: <this slug and the remaining ones>`, sets failed and breaks, so the run exits 1. Every other exception keeps today's handling, `MAX_CONSECUTIVE_FAILURES` included.
  - `voice_cmd`: `_process_one` runs inside `with station_lock(pkg.dir.absolute().parent, command="emcee voice")`. `StationLocked` (an EmceeError) reaches the existing `error: <slug>:` boundary, details included, and exits 1.
  - `_process_one` stays lock-free. Its manifest re-read is the first thing under the lock. The docstrings for `run` and `voice` now describe the lock.
- Docs:
  - Root `CLAUDE.md` rule now reads as the brief gives it.
  - `packages/emcee/CLAUDE.md`: the "Single-writer station, no lock" paragraph is replaced by "The station lock, per package". It covers: the lock is held from the re-read through the last write and never across `Proceed?`; a held lock stops `run` or refuses `voice`; on SIGTERM or SIGHUP emcee releases the lock and exits at once (`os._exit`), which is safe only because writes are temp-plus-rename; SIGKILL leaves the lock for `emcee lock clear`; move, say, dry-run and read-only commands don't take it; two concurrent runs are still unsupported (double spend).
  - `emcee lock show|clear` added to Commands, with the agent rule (show, report, `clear --yes` only after Shawn approves, in a separate tool call).

## R6 / atomic-write check (strict surface)
Every station write done inside the lock is an atomic temp-plus-rename or an unlink:
- the manifest: `package_io.rewrite_manifest` -> `atomic_write_text`;
- `dj-notes.md` and `broadcast.m3u`: `process.py` uses `atomic_write_text`;
- clips and `segments.json`: `audio.py` uses `atomic_write_bytes` / `atomic_write_text`, including in `adopt_clips`;
- the `--fresh` clip unlink and orphan-clip pruning are plain unlinks.

`workspace.atomic_write_bytes` is mkstemp in the target dir followed by `os.replace`. So an `os._exit` mid-package leaves at most a stray `<name>.<rand>.tmp` file in the package dir, plus the same package state as SIGKILL would. That state is pending (dj_audio cleared, or the kept script with dj_audio null). No torn file and no stuck lock.

## Tests: packages/emcee/tests/test_run_lock.py (10 tests, all named as in the brief)
- The "held lock on the 2nd package" test is realistic, not a mock of acquire. `sl.release` is wrapped so that, after the real release of pkg1, a foreign llama lock file appears. pkg2's real `acquire` then raises `StationLocked`. The test asserts:
  - pkg1 is voiced;
  - the error line, the holder lines and the show/clear hint are on stderr;
  - `not attempted: pkg2, pkg3` appears exactly once, and there is no `error: pkg3`;
  - the pkg2 and pkg3 manifests are byte-identical;
  - the foreign lock is unchanged.
- The token test records the lock file on `_process_one` entry: present for all 3 packages, 3 distinct tokens, no lock file afterwards.
- The TTY test patches `typer.confirm` to assert there is no lock file and `_held is None`.

RED: `./.venv/bin/pytest packages/emcee/tests/test_run_lock.py -q` -> 8 failed, 2 passed. The two that passed are dry-run and status/move/say, as expected, since they assert the absence of the lock. The failures were all "no lock present" (e.g. `assert [('pkg1', False)] == [('pkg1', True)]`) and voice-refuses getting `LLM or TTS spend` instead of a lock refusal.
GREEN: same command -> 10 passed. `./.venv/bin/pytest packages/emcee -q` -> 1213 passed, 1 deselected (1203 + 10). Full `./.venv/bin/pytest -q` -> 6703 passed, 1 skipped, 8 deselected (26 warnings, none from the new file).

Mutation check: run in a scratch copy under the scratchpad, with shadowing verified via `emcee.__file__`, bytecode off and a fresh copy per mutant. The expected red test was named before each run.
- M1 (voice without `.absolute()`) -> the dot test fails. CAUGHT.
- M2 (`continue` instead of `break` on StationLocked) -> SURVIVED at first. I strengthened the test (one `not attempted`, no `error: pkg3`), and it now fails as predicted. CAUGHT.
- M3 (no lock in run) -> 5 run tests fail. CAUGHT.
- M4 (`not attempted` omits the current slug) -> the stop test fails. CAUGHT.

## Self-review / concerns
1. `README.md` (around line 633) still says "Single-writer station, no lock." The brief's file list didn't include the README, so I left it. Update it with the release docs, or tell me to.
2. Pre-existing, not changed: `emcee voice .` prints `voiced: .`. An error there reads `error: : ...` because `pkg.dir.name` of `Path(".")` is empty. The lock itself lands correctly (tested). A one-word fix (`pkg.dir.absolute().name`) is available if wanted.
3. `voice_cmd` still reads the manifest and validates moves before taking the lock (read-only validation). `_process_one` re-reads under the lock, as the brief says.
4. A non-StationLocked error from acquire (e.g. EACCES creating the lock) is treated as an ordinary per-package failure in `run`, and the run continues. That follows the brief ("every other exception keeps today's handling").
