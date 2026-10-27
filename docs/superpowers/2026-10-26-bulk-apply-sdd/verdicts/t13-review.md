### Spec Compliance
- ❌ Issues found:
  - `packages/llama/src/llama/cli.py` (the `resume = f"resume with: llama reapply --from-list {path}"` line in `_reapply_list`, unchanged by this diff but now reached by every new stop and pause): the resume command leaves out `--seven-day-ceiling`. A wave paused by the weekly ceiling and resumed with the printed command runs on to `[pacing] seven_day_ceiling` (default 90). That is the spec's anti-goal "the bulk apply eating the weekly LLM window" ("Pacing, ordering and resumability": the weekly limit is a per-run override "so the apply cannot spend the week"). See Important 1.
  - `packages/llama/src/llama/reapply.py` `outcome_retryable`: `needs-llm` is retryable even when the row ran with `--with-gather-llm`. The brief makes it retryable only for "a row run without `--with-gather-llm`", and "every other outcome keeps today's rule" (non-retryable). See Minor 3.
  - `cli.py` trial stop: `raise typer.Exit(1 if failed else 0)`, while the brief says "exit 0". This deviation is deliberate and consistent with the pause path (Minor 4).
- ⚠️ Cannot verify from this diff:
  - Review Focus 2 says "nothing downloads". The named test `test_batch_stops_after_three_unreadable_station_copies` replaces `reapply_show` entirely, so it proves only the CLI streak, exit code and message. That a delivered show's strict reuse raises `StationUnreadable` before any download (and before the brief spend) belongs to Tasks 8/9 and is not exercised end to end at batch level here. The ruling-3 path (a held show, the mount dropping before `record_after`) is exercised for real by `test_a_mount_drop_seen_by_record_after_is_an_unreadable_station_copy`.
  - Whether the trial-report tooling (a later task) reads per-row `meter` from progress rows, which would make Minor 1 harmless, or the printed `trial block done` line.

### Strengths
- The snapshot logic is tight. `fresh_batch` is computed before `batch.mkdir` (`cli.py` `_reapply_list`, the `fresh_batch = not (batch / "progress.jsonl").exists() and not snap.exists()` line). A resumed batch reuses `snapshot/` (ruling 1; the re-run in `test_list_batch_takes_a_snapshot_before_the_first_write` asserts the manifest bytes are unchanged). A failed `take` removes its partial dir (`batch_snapshot.py:236-240`), so the next run is fresh again.
- `record_after` runs inside the show lock through `after_commit`. `test_after_records_follow_each_write` proves this three ways: a non-blocking lock attempt raises `Locked`, no progress row exists yet, and `show.json` is already committed. That is a good test of a timing property.
- Ruling 2's pre-flight runs before the batch dir, the snapshot and any spend. The test asserts the batch dir is absent and that a dry run is not refused.
- Ruling 3's conversion is scoped correctly. Only `LlamaError` with the root no longer a directory becomes `StationUnreadable` (`chained from exc`), and the message follows the contract shape `<slug>: station copy unreadable: <detail>`. The integration test checks that the unit restored each show (`needs_review is True`).
- `except station_mark.StationUnreadable` sits above `except (IAError, LlamaError, …)` and below the LLM arm. `StationUnpaired` stays ordinary and is tested. The streak is reset only by writing outcomes, and that is tested too.
- The meter is read once after each show and shared by the printed line, the row and the trial check. This removes the old second `_meter` call in the print and keeps the per-show read count unchanged. `read_usage` never raises (`herder/usage.py:107-129`), so the post-commit read cannot abort a committed row.
- `test_retryability_per_outcome` is parametrised over every outcome in the brief and also checks that a re-run retries exactly the retryable rows.
- The "Untouched" grep over the diff (DURATION_TOLERANCE, junk constants, `briefing_reusable`, `purge_package_audio`, `STOP_AFTER_LLM_FAILURES =`, `load_list`, `Manifest`, emcee imports) found nothing.
- Named risk: the campaign pin keys. `require_tools` reads only `pin["version"]` (`campaign_gate.py:210-211`), which the list's `{"version", "pin_sha"}` provides. The test mocks `require_tools`, but the key contract holds.
- Named risk: a stale snapshot across a long pause. An operator `fix` between `take` and the batch reaching that show changes `overrides.json`, which is one of the `input_digests` (`replay.py:105-111`). The row is therefore skipped as `inputs changed` with no after-record, and `restore` refuses it (`NO_WRITE`). Operator edits are not silently rewound.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **The resume line drops `--seven-day-ceiling` (and `--with-gather-llm`, `--allow-structure-change`, `--stop-at-points`).**
   - **Where:** `packages/llama/src/llama/cli.py`, `_reapply_list`, `resume = f"resume with: llama reapply --from-list {path}"`. It is printed by the ceiling pause, the `RateLimited` pause, both 3-in-a-row stops and the trial stop.
   - **What's wrong:** The runbook's wave command is `llama reapply --from-list … --allow-structure-change --with-gather-llm --seven-day-ceiling <pct>` (plan line 595). The weekly ceiling works by pausing and printing this line. Resuming with it as printed silently raises the ceiling to the config value (90 by default), the very cap the trial was run to set. The new test shows the effect: in `test_seven_day_ceiling_override_pauses`, the second run without the flag proceeds at 41% weekly. Dropping `--with-gather-llm` and `--allow-structure-change` is only lossy (rows come back retryable). Dropping the ceiling is the anti-goal.
   - **The implementer's rationale does not hold:** the brief does not fix this string. Contracts list no resume line, and every test asserts it with `in`, so appending flags breaks none of them.
   - **Fix:** build `resume` from the flags actually given, appending ` --allow-structure-change`, ` --with-gather-llm` and ` --seven-day-ceiling <pct>`, plus ` --stop-at-points <n>` if a trial resume should continue as a block. Alternatively, persist the run options in the batch dir and refuse a resume that omits the ceiling. Add a test asserting the printed line carries `--seven-day-ceiling 40`.

#### Minor (Nice to Have)
1. **The trial `n` counts rows that spent nothing.**
   - **Where:** `cli.py`, the trial block: `block[1] += 1` for every non-exception outcome.
   - **What's wrong:** `skipped: processed`, `skipped: inputs changed`, `skipped: re-selection`, `skipped: structure changed` and `needs-llm` (a needs-LLM block run without the flag) are all counted, while failed rows are not. The printed `moved <d> points over <n> shows` is the per-show cost the spec divides by. The bias is both ways: zero-spend skips lower it, and a failed row that spent a brief raises it. Failure rows also carry no `meter`, so the record cannot repair the gap.
   - **Fix:** count only committed outcomes (`cleared`, `held`, `label-only`, `unchanged`), and give failure rows a `meter` too.
2. **`--stop-at-points` and `--seven-day-ceiling` are silently inert when the meter does not apply.**
   - **What's wrong:** if `_meter_applies` is false (`[pacing] enabled = false`, or a non-claude_cli backend), the trial never ends (it runs the whole list) and the ceiling is ignored.
   - **Fix:** refuse either flag up front when `_meter_applies(config, pace)` is false.
3. **`needs-llm` is retryable even with `--with-gather-llm`.**
   - **Where:** `reapply.py`, `outcome_retryable`.
   - **What's wrong:** with the flag, a `needs-llm` row can never become runnable, yet every re-run re-replays it. This costs no LLM call, but it deviates from the brief's parenthetical.
   - **Fix:** pass `with_gather_llm` to `outcome_retryable` and return `outcome == "needs-llm" and not with_gather_llm`.
4. **The trial stop exits 1 after an earlier failure; the brief says exit 0.**
   - **Where:** `cli.py`, the trial stop.
   - **Why it's defensible:** the choice matches the pause path.
   - **Fix:** record it as an accepted deviation, or follow the brief.
5. **The resume check tests only that `snapshot/` exists.**
   - **Where:** `cli.py`, `after_hook` / `fresh_batch`.
   - **What's wrong:** a snapshot dir without `manifest.json` counts as a snapshot. `take` can leave one when it cannot remove its partial dir; the message says to remove it by hand. In that state every write's `record_after` raises in `_load_manifest`, and the unit restores. Every show in the wave then pays its fresh brief and is rolled back, with no stop: it is an ordinary `LlamaError`, counted by neither streak.
   - **Fix:** on a non-fresh batch with `snap.exists()`, load or verify the snapshot manifest once before the first show and refuse (exit 1) if it is unusable.
6. **A flaky mount surfaced by the hook is not counted.**
   - **Where:** `cli.py`, `after_hook`.
   - **What's wrong:** only a root that is no longer a directory is converted. In two cases a mid-wave mount fault becomes an ordinary failure that neither streak counts: `_station_sha` raising `_Unfit` for an EIO/ETIMEDOUT read while the root still stats as a directory, and `Path.is_dir()` itself raising a non-ENOENT `OSError` inside the except arm (which propagates as `OSError`). The spec's "station manifest unreadable … counts toward stopping" would cover both.
   - **Severity:** low, since ruling 3 scoped the conversion narrowly.
7. **The names-form refusal is untested.**
   - **Where:** `cli.py`, `"--seven-day-ceiling and --stop-at-points take --from-list"`.
   - **Fix:** add a test.
8. **Test hygiene in `packages/llama/tests/test_reapply.py`.**
   - `test_list_batch_takes_a_snapshot_before_the_first_write` assigns `real = reapply_mod.build_package` and never uses it.
   - The `test_a_mount_drop…` comment says "no package manifest left by the failed unit" but does not assert it.
   - `seven_day_ceiling: float = typer.Option(None, …)` should be annotated `float | None` (`stop_at_points` likewise).
9. **`retire_rekey_restore` errors are uncaught.**
   - **What's wrong:** an `OSError` from `_write_json` (`campaign_gate.py:275`) escapes `_reapply_list` as a traceback rather than an `error:` line and exit 1.

### Assessment
**Task quality:** Needs fixes
**Reasoning:** The snapshot, after-record, station pre-flight, mount-drop conversion, streak and retryability logic are correct and well tested against the brief and the orchestrator's rulings. However, the printed resume command drops `--seven-day-ceiling`, so the normal recovery from a weekly-ceiling pause silently runs the wave on to the config ceiling: exactly the anti-goal the override exists to prevent. The fix is small and breaks no existing assertion.
