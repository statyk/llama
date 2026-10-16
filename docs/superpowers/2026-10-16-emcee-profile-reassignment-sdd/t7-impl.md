# Task 7 handback: The pause before `emcee run`

**Status:** DONE
**Commit:** 441b586 feat(emcee): emcee run prints a plan and asks before any spend (--yes to skip)

## What was implemented
`packages/emcee/src/emcee/cli.py`, exactly as the brief specifies (helpers and `run` copied verbatim from the brief):
- `_presenter_or_marker(config, presenter_id) -> Presenter | str` (new); `_dry_run_marker` refactored onto it (output unchanged).
- New helpers: `_stdin_is_tty`, `_plural`, `_stale_moves`, `_stale_note`, `_plan_tts_cell`, `_echo_plan` (stderr; called via the module global so tests can wrap it).
- `run` rewritten: one `_load_station` scan; error / unsupported / move_problem / ready / missing-tracks-skip rows reported as found; move_problem checked BEFORE the ready check (a ready package with an invalid move target is an error row); plan printed on stderr before any `_process_one`; `--yes/-y` skips the question; no TTY and no `--yes` -> plan, then `error: refusing to voice without confirmation; pass --yes`, exit 1; decline -> `nothing voiced`, exit 1 if any error row else 0; `--dry-run` always wins (rows + plan, never asks); nothing to voice -> no plan/no prompt, stale-move note still printed; voices exactly the planned list from the same scan (never re-scans).

## Tests
- New: `packages/emcee/tests/test_run_plan.py` (19 tests, verbatim from the brief).
- Step 4 edits: `test_run_cmd.py` (`--yes` on every non-dry-run `run` invocation incl. the `--profile Dead` loop; `assert result.stderr == ""` -> `assert "error:" not in result.stderr`), `test_mlx_wiring.py` (`_cmd` and the two direct `run` calls), `test_handshake.py` (one `run` call). `test_profile_readiness.py` and `test_move_cmd.py` needed no change, as the brief said (confirmed: they pass).

Task 5's review request (pin `emcee run`'s per-package error row for an invalid move target while other packages still proceed, spec §3): COVERED by `test_a_move_whose_target_lost_its_entry_is_an_error_row_and_others_still_voice` (exit 1, `error: moved: move target "southern" has no [assign.profiles] entry`, plan shows only 1 package, `voiced: fresh` and not `voiced: moved`), plus `test_a_ready_package_whose_move_lost_its_entry_is_still_an_error_row` (both `run` and `run --dry-run`; manifest untouched).

### RED
`./.venv/bin/python -m pytest packages/emcee/tests/test_run_plan.py -q` -> `19 failed in 0.61s`. Failure reasons (grouped): 9x `AttributeError: module 'emcee.cli' has no attribute '_stdin_is_tty'`; 1x no `_echo_plan`; several exit code 2 (`No such option: --yes`, usage error); `'to voice: 4 packages, 12 clips' in []` (plan missing from stderr); stale note missing; `gregg [missing presenters/gregg.toml] 1 package` missing; forbid_spend tripping (`AssertionError: LLM or TTS spend`) because old `run` voiced without asking. All expected: the feature did not exist.

### GREEN
- `./.venv/bin/python -m pytest packages/emcee/tests/test_run_plan.py -q` -> `19 passed in 2.54s`
- `./.venv/bin/python -m pytest packages/emcee/tests/test_run_plan.py packages/emcee/tests/test_run_cmd.py packages/emcee/tests/test_mlx_wiring.py packages/emcee/tests/test_handshake.py -q` -> `83 passed in 1.78s`
- Full: `./.venv/bin/python -m pytest -q` -> `3129 passed, 1 skipped, 8 deselected, 26 warnings in 44.09s` (3110 + 19 new; warnings are pre-existing llama fork DeprecationWarnings).

## Files changed
- /Users/shawn/projects/llama/.claude/worktrees/emcee-profile-reassignment/packages/emcee/src/emcee/cli.py
- /Users/shawn/projects/llama/.claude/worktrees/emcee-profile-reassignment/packages/emcee/tests/test_run_plan.py (new)
- /Users/shawn/projects/llama/.claude/worktrees/emcee-profile-reassignment/packages/emcee/tests/test_run_cmd.py
- /Users/shawn/projects/llama/.claude/worktrees/emcee-profile-reassignment/packages/emcee/tests/test_mlx_wiring.py
- /Users/shawn/projects/llama/.claude/worktrees/emcee-profile-reassignment/packages/emcee/tests/test_handshake.py

## Self-review
- Brief and code agreed on every earlier-task interface (PackageStatus fields `voiced`, `profile_reason`, `missing_tracks`, `clips`, `move_problem`, `performance_id`; `Moves.entries`; `_load_station`; `_process_one(config, moves, pkg, force)`); no imports needed adding. Only discrepancy: test_run_cmd.py line numbers were off by about 1 from the brief's list; the edit was by pattern (every non-`--dry-run` `["run", ...]` invoke), so nothing was missed.
- EOF at the prompt: `typer.confirm` raises Abort, so exit 1 ("Aborted!"), nothing spent; the test asserts only non-zero.
- No README/CLAUDE.md/`--help` doc changes beyond the `run` docstring and option help in the brief. I assume the rollout/docs task covers `emcee run --yes` in README and CLAUDE.md (CLAUDE.md's `emcee run` bullet does not mention the pause yet).

## Concerns
None blocking. Documentation of `--yes` and the new exit codes outside the CLI help is left to the docs task.

---

# Fix report, round 1

**Status:** DONE
**Commit:** 16fc790 test(emcee): forbid_spend records attempts so run's error rows cannot swallow a spend
No production code changed.

## Changes
- `packages/emcee/tests/helpers.py`: `forbid_spend(monkeypatch) -> list[str]` still raises `AssertionError("LLM or TTS spend")`, and now also appends one entry per attempt to a list it returns. Existing callers that ignore the return value are unaffected (test_move_cmd.py, test_recording.py and test_profile_readiness.py are unchanged).
- `packages/emcee/tests/test_run_plan.py`: all 11 `forbid_spend` calls are now `spent = forbid_spend(monkeypatch)`, and each of those tests asserts `spent == []`. That covers the plan, declined, EOF, no-TTY, dry-run, nothing-to-voice, the error-row `[declined]`/`[nothing]` modes, the ready-move error row, the stale note, the presenter marker, and the malformed-manifest test.
  - `test_eof_at_the_prompt_spends_nothing` now also asserts `exit_code == 1`, `"Aborted" in result.stderr`, `"error:" not in result.stderr` and `"voiced:" not in result.stdout` (the reviewer's option (a)).
  - `test_any_error_row_exits_1`, non-proceeded modes: also asserts no `voiced:` line, and for `declined` that `nothing voiced` is printed.

## Covering tests
- `./.venv/bin/python -m pytest packages/emcee/tests/test_run_plan.py packages/emcee/tests/test_move_cmd.py packages/emcee/tests/test_recording.py packages/emcee/tests/test_profile_readiness.py -q` gives `105 passed in 1.41s`.
- `./.venv/bin/python -m pytest -q` gives `3129 passed, 1 skipped, 8 deselected, 26 warnings in 44.86s`.

## Mutant proof (scratch copy only)
Setup:
- The copy came from `git archive HEAD | tar -x` at 16fc790, into `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-emcee-profile-reassignment/eb75daa6-4117-4f2c-a82b-07d987d6b499/scratchpad/t7-mut/tree`.
- Tests ran from an empty cwd (`/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-emcee-profile-reassignment/eb75daa6-4117-4f2c-a82b-07d987d6b499/scratchpad/t7-mut/empty`), with `PYTHONPATH=<copy>/packages/emcee/src:<copy>/packages/herder/src`, `PYTHONDONTWRITEBYTECODE=1` and a fresh `PYTHONPYCACHEPREFIX`.
- Shadowing check: `emcee.cli.__file__` and `herder.__file__` both resolved inside the copy, and the loaded `cli.py` contained the mutant marker.

Command: `<worktree>/.venv/bin/python -m pytest -c <copy>/pytest.ini --rootdir <copy> -p no:cacheprovider <copy>/packages/emcee/tests/test_run_plan.py -q`

**Mutant M1 (the reviewer's):** at the confirm, `typer.Abort` is caught and treated as proceed (`_ok = True`).
- Prediction, logged before the run: exactly 1 failure, `test_eof_at_the_prompt_spends_nothing`, first failing at `"Aborted" in result.stderr`. The exit code is still 1, because the swallowed spend errors become error rows. The other 18 tests pass.
- Result: `1 failed, 18 passed`. The failure was `FAILED test_eof_at_the_prompt_spends_nothing` at test_run_plan.py:208, `assert 'Aborted' in 'to voice: 4 packages, 12 clips ... error: ttb2: AssertionError: LLM or TTS spend\n'`. This matches the prediction.

**Variant M1b:** the same mutant, plus the copy's EOF test stripped of the three (a) assertions, so only `spent == []` can catch it.
- Prediction: the EOF test fails at `spent == []` with 4 entries.
- Result: `1 failed, 18 passed`, at test_run_plan.py:209: `assert ['spend', 'sp...end', 'spend'] == []`, "Left contains 4 more items". This matches the prediction: the attempt list catches what run's per-package `except Exception` swallows.

**Control:** the unmutated copy (cli.py and the test file re-extracted from HEAD) gives `19 passed`.

Scratch dir: /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-emcee-profile-reassignment/eb75daa6-4117-4f2c-a82b-07d987d6b499/scratchpad/t7-mut. The live worktree was never mutated.
