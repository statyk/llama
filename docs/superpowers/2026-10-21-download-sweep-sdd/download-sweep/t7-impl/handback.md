# t7-impl handback: Task 7, the sweep (`llama run resume --all`)

Status: DONE_WITH_CONCERNS. The concerns are minor; see "Concerns".

## Commit
- `cc7f121` feat(runs): llama run resume --all sweeps resumable runs in one pass

## What I implemented
- `sessions.sweep_verdict(info, run_dir, now) -> str | None`. It checks in this order:
  1. `running`
  2. `awaiting approval`
  3. `needs attention` when the run has neither criteria.json nor request.json
  4. `needs attention` when any failure's `failure_kind` is not download/archive. A non-list `failures`, or a non-dict record, also counts.
  5. `needs attention` for a marker-less run whose request (read through `read_request`) has an `auto` key that is not `True`
  6. For `paused`: `paused until HH:MM` (local time) when `resume_after` is in the future, and `needs attention` when `resume_after` cannot be parsed
  7. Otherwise `None` (eligible)
- `cli._resume_run(config, ia, ledger, ws, *, auto, full_rationale, pace, record_crash)`:
  - Takes `run_lock(ws.dir, blocking=False)` itself, so `Locked` and `RunMissing` propagate to the caller.
  - Calls `_resume_locked`, which is today's `run_resume` body moved over unchanged. Its request reads stay as `json.loads`, which keeps the loud-failure asymmetry.
  - With `record_crash`, any `Exception` except `typer.Exit(0)` writes `mark_incomplete(ws, outcome=None, failures=[_crash_record(exc)])` inside the lock scope and then re-raises.
  - `_crash_record` is `failure_record(None, exc, kind=KIND_OTHER)`, with `error = "exit <code>"` for a `typer.Exit`.
- `run_resume`:
  - `session` is now an optional `Argument(None)`, and there is a new `--all` option.
  - Giving both or neither prints `give a session to resume, or --all (not both)` and exits 1.
  - `--all --interactive` prints an error and exits 1.
  - The single-session form calls `_resume_run(record_crash=False)` and converts `Locked`/`RunMissing` through a new `_lock_refusal(ws, exc)`. `_run_locked` now uses the same function, so each refusal message exists in one place only.
- `cli._sweep_runs`:
  - Lists `attention_sessions` and prints `skip <id>: <reason>` for each skipped run, or `nothing to resume` (exit 0) when none is eligible.
  - Resumes eligible runs oldest `updated_at` first (parsed as datetimes, not compared as strings), under `== <id>` headers, with `auto=True`.
  - Each run's result is one of:
    - `Locked` → `running`
    - `RunMissing` → `gone`
    - an exception → `error: <msg>`
    - `typer.Exit(0)` → the run's state
    - otherwise `session_state`
  - After a run that ends `paused`, it prints `not reached: <id>` for each remaining eligible run and stops.
  - It then prints `summary:` followed by `  <id>: <result>` lines.
  - Exit is 1 if any result is outside {complete, running, gone}.
  - `--wait` defaults to False when not given. `--max-wait` and `--no-pacing` pass through `_pace`.
- `_execute`: the "no matching artists found" return now writes `mark_complete(ws, "no matching artists found")` first.
- `_print_sessions` prints `(run)` for a failure whose `show` is None.
- `run list` docstring now mentions running sessions (folded from the Task 6 review). I did not change how a running row prints.

## Tests: packages/llama/tests/test_sweep.py (new, 32 tests)
Every test the brief lists is present under its exact name. `test_eligibility_per_state_and_kind` covers all the parametrized cases (18 ids). Some tests check more than the brief asks for:
- `test_crash_marker_for_typer_exit_reads_exit_code` also checks that `typer.Exit(0)` writes no marker and the result is the run's state.
- `test_exit_codes` also checks that an awaiting run is skipped on the next pass.

## TDD evidence (all of it in t7-impl.log)
- **RED 1:** `./.venv/bin/pytest packages/llama/tests/test_sweep.py -q` fails at collection with `ImportError: cannot import name 'sweep_verdict'`. That hides the individual tests, so:
- **RED 2:** I added a temporary `sweep_verdict` stub that raises NotImplementedError (nothing else implemented) and ran the same command. Result: 31 failed, 1 passed. The causes:
  - 18 eligibility cases failed with NotImplementedError.
  - 10 CLI tests failed with a usage error (exit 2), because `--all` did not exist yet.
  - `test_keyboard_interrupt` and `test_no_wait` failed because `_execute` was never reached.
  - `test_no_matching_artists` failed with FileNotFoundError on session.json, because no marker was written.
  - The one pass was `test_single_resume_still_refuses_a_live_run_and_records_no_crash_marker`. That is expected: it guards behaviour that already exists, and nothing should ever have made it fail.
- **GREEN:** `./.venv/bin/pytest packages/llama/tests/test_sweep.py -q` gives 32 passed. The full suite, `./.venv/bin/pytest -q`, gives 3934 passed, 1 skipped, 8 deselected. The 26 warnings are the existing multiprocessing fork DeprecationWarnings.
- **Mutation check** (scratch copy made with `git archive`, run through `python -m pytest` with PYTHONPATH shadowing, which I verified via `llama.__file__`; bytecode cleared before each mutant). I wrote down the expected failing test before running each one, and all 11 failed as predicted:
  - catching BaseException
  - no crash marker
  - paused ignoring failures
  - Exit(0) treated as a crash
  - wait defaulting to config
  - no stop on pause
  - `running` counting against the exit code
  - no auto-false check
  - newest-first order
  - no-match run left unmarked
  - no `(run)` label

## Files changed
- packages/llama/src/llama/sessions.py
- packages/llama/src/llama/cli.py
- packages/llama/tests/test_sweep.py (new)

No existing tests were adjusted.

## How I read the brief and spec
1. **Verdict order:** `needs attention` is checked before `paused until` (step 4 before step 6). A paused run with a transport failure says needs attention even when its reset is still in the future, because waiting will not fix it.
2. **Unparseable `resume_after`:** reads as `needs attention`, since the spec allows only "past or absent".
3. **Marker-less `auto` check:** only `auto: true` or a missing key qualifies, read literally. So `"auto": "yes"` needs attention.
4. **Odd failure records:** a non-list `failures`, or a non-dict record, reads as needs attention. That keeps a malformed persisted marker from crashing the whole sweep.
5. **Wording:** the summary format, the `not reached: <id>` lines, the `== <id>` header and the error texts for bad flag combinations are mine. The spec leaves wording beyond the quoted lines to the builder.
6. **`typer.Exit(0)` in the sweep:** it is caught by the sweep's `except Exception`, and the result becomes the run's `session_state`, not an error.
7. **No duplicate error line:** a crashed run's error appears only in the summary, with no separate stderr line.
8. **Body moved, not changed:** the comment "Before reading anything: a live run is another process's to finish" went away with the move. The `_resume_run` docstring now carries that point.

## Concerns
- **A `Locked` from inside the resume body would be misread.** `_execute` catches the `Locked` from its non-blocking show lock, and the blocking path never raises it. If one did escape, the sweep would write a crash marker and then report the run as `running`. The single form would print "in progress in another process". This cannot happen today. Fixing it means telling apart a `Locked` from acquiring the run lock and one from the body; I chose not to, under YAGNI.
- **Exit-only crash markers are terse.** A crash marker from a `typer.Exit(1)` (for example interpret failing inside `_interpret_with_pause`) says only `exit 1`. The reason went to stderr during that run's section. This matches the brief.
- **Docs not updated.** The project CLAUDE.md "Commands" section does not mention `run resume --all` yet. I left docs alone because the brief does not list them; this probably belongs in a docs or final task.
