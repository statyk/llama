# Task 19 implementer handback: `llama reapply <show>`, the single-show apply

**Status: DONE_WITH_CONCERNS.** The concerns are minor, listed below.
Implementer model: Opus.

## Commits (on held-backlog-tier1, BASE c851243)
- `5507aa2` refactor(brief,package): extract generate_briefing and build_package for reapply
- `e73eea6` feat(reapply): single-show apply under the show lock, show.json last

## What changed
- `stages/brief.py`:
  - `vetting_summary_text(vr | None)` holds the body of `vetting_summary`, and `vetting_summary(show_ws)` is now a wrapper around it.
  - `generate_briefing(provider, show, research_md, reviews, *, narration, vetting) -> (Briefing, problems)` is today's two-attempt loop. It returns the briefing normalised and narration-stamped, and writes nothing.
  - `run_brief` calls `generate_briefing` and keeps its own writes, so its behaviour is unchanged.
- `stages/package.py`: `build_package(...) -> (pkg, flags)` is `run_package`'s body minus the trailing `show.json` write. An existing manifest returns `(pkg, [])`. `run_package` is now `build_package` followed by the unchanged flags write.
- `reapply.py` (new): `ReapplyOutcome` and `reapply_show`, built to the brief with the binding rulings applied. Under the blocking `file_lock(ws.lock)`, from the `show.json` re-read through the last write, it does the following:
  1. Skips the show if it is not held, or if a given `row`'s digests no longer match.
  2. Runs `compute_legs` with `CacheOnlyIA` and `setlistfm_client(config)`, in a scratch dir from `mkdtemp` that is removed in a `finally`.
  3. Maps the result of `classify(legs, "held")`. A `needs-llm` show writes nothing; `--dry-run` returns `dry-run: cleared|needs-brief|structure-changed|held` and writes nothing.
  4. Builds the final show from `legs.replayed_show` with `review_flags` taken from `legs.flags` (ruling: never from `replayed_show.review_flags`).
  5. On a reuse, takes `legs.briefing`. On a fresh brief, makes one `generate_briefing` call before any write and adds its problems to the flags.
  6. Writes in this order: `vetting.json`, `notes.json`, `briefing.json`, `briefing.md` (rendered from the model on reuse too, never copied: spec 3a).
  7. If there are no flags: `drop_stage_artifacts(ws, "package")`, then `build_package(..., profile=provenance.profile)`, then adds the package flags.
  8. Writes `show.json` once and last.
  - `reviews.json`, `provenance.json`, `research.md` and the ledger are never written.
  - The module imports `compute_legs`, `build_package` and `write_artifact` by name at module level, so the tests' monkeypatches take effect.
- `cli.py`: `llama reapply NAMES... [--dry-run] [--from-list F]` (Fix & ship panel).
  - Each name is resolved with `_resolve_show` and passed to `reapply_show(row=None)`, which calls `reapply_mod.reapply_show` at call time.
  - Prints `reapplied: {slug} -> {outcome}`, plus `  re-deliver with: llama deliver {slug}` (see deviation 1).
  - `LlamaError`/`HerderError`/`IAError`/`TaskFailed` print `FAILED {slug}: {exc}` on stderr and the loop continues; the command exits 1 if any show failed.
  - `--from-list` prints `--from-list: not implemented` on stderr and exits 1. Giving no names exits 1 with a usage line.
- Tests:
  - `tests/test_reapply.py` (new, 25 tests): the brief's 16, adjusted per the rulings, plus the additions listed under deviation 3.
  - `test_stage_brief.py`: `generate_briefing` is added to the top-of-file import line, and the brief's test is appended.
  - `test_stage_package.py`: one appended test. `build_package` returns its flags, never writes `show.json`, and an existing manifest short-circuits with `(pkg, [])`.

## Tests
- Baseline at BASE: 3686 passed, 1 skipped, 8 deselected.
- Red: ImportError `generate_briefing`, plus a collection error in `test_reapply.py` (`llama.reapply` missing).
- After the refactor commit (`./.venv/bin/python -m pytest -q --ignore=packages/llama/tests/test_reapply.py`): 3688 passed, 1 skipped, 8 deselected.
- Final (`./.venv/bin/python -m pytest -q`): **3713 passed, 1 skipped, 8 deselected** (+27: 25 in test_reapply, 1 in brief, 1 in package).
- `llama.__file__` resolves inside the worktree.

## Mutation table
Recipe: one rsync copy per mutant under `MROOT=/var/folders/yn/jlwxryrj1ds7jpvw931jk1jm0000gn/T//mut-t19-impl-T9nCTQ` (echoed into the log). Each copy ran with PYTHONPATH shadowing and its own PYTHONPYCACHEPREFIX, and shadowing was proven per mutant: both `llama` and `llama.reapply` resolved under the copy. Each run covered `test_reapply.py`, `test_stage_package.py` and `test_stage_brief.py`. Predictions were written to the log before any flip. MROOT has been removed (that exact path only).

| mutant | predicted test | caught by |
|---|---|---|
| (a) show.json written before build_package | test_show_json_is_not_rewritten_before_the_package_is_built | that test, plus test_a_package_failure_leaves_the_show_held_and_a_rerun_completes_it, test_package_flags_land_in_the_one_final_show_json_write, and the two written-order tests |
| (b) lock released before the writes (held only through classify) | test_reapply_holds_the_show_lock_throughout | that test (only) |
| (c) vetting.json written before the needs-LLM check | test_reapply_writes_nothing_on_a_needs_llm_show | that test, plus test_reapply_writes_nothing_on_a_refusal_mid_show and test_dry_run_predicts_and_writes_nothing |
| (d) build_package's flags dropped | test_package_flags_land_in_the_one_final_show_json_write | that test (only) |
| (e) stale manifest not dropped | test_a_stale_manifest_never_short_circuits_the_package | that test (only) |
| (f) slfm built unconditionally | test_reapply_passes_no_setlistfm_client_when_no_key_is_configured | that test (only) |
| (g) briefing.md copied from the stored file on reuse | test_a_reused_briefing_is_rewritten_normalised_never_copied | that test (only) |

There were no survivors.

## Deviations
1. **The re-deliver reminder prints only when the outcome is `cleared`.** The brief says to print it "when delivered". `ReapplyOutcome.delivered` is still the plain ledger fact on every outcome, so only the CLI print is gated. Printing it on a dry-run, a skip, or a `held` show would point at a `deliver` the gate then refuses.
2. **The snapshot tests make two fixes to the comparison:**
   - Per B6, they touch `.lock` before snapshotting (the `_snapshot` helper).
   - The new `_stale(ws)` helper first rewrites `vetting.json`'s flags and `notes.json` to stale values. The replay never reads either, and the digests use only the extraction. Without this, a premature `vetting.json` or `notes.json` write would rewrite byte-identical content on the fixture and be invisible: mutant (c) would only be caught through `written`.
3. **Tests beyond the brief:**
   - the 3a reuse re-render;
   - still-held after vet: writes only `vetting.json`, `notes.json` and `show.json`, with no brief and no package;
   - a carried package flag is never cleared;
   - `show.json` is still held while the package builds;
   - a row whose digests match is applied;
   - dry-run predicting needs-brief and held;
   - an undelivered show is not flagged for redelivery;
   - the CLI failure path continuing and exiting 1;
   - the CLI dry-run.

   The lock test also asserts the lock is held inside `build_package` and at the `show.json` write, and released afterwards.
4. **No fixture adjustment was needed.** A probe on the current tree gave:
   - `gratefuldead-1973-06-10`: `clears`, briefing `reuse`, no flags, no notes.
   - `held_for_real=True`: `still-held` with `research asserts wrong date: 1974-01-01`.
5. **`ReapplyOutcome.flags`:** on `needs-llm` and on dry-run it is `legs.flags`, the flags the replay computed; on skips it is `[]`.

## Concerns (minor; none block)
- **A usage-limit refusal does not stop the names loop.** In the names form, a `RateLimited` (a `HerderError`) on a fresh brief prints FAILED and the loop moves to the next name, as the brief specifies. Stopping on a refusal, the 3-consecutive-failure stop and the pacing gate all belong to Task 20's batch form.
- **Failed `claude -p` output is not captured** under `llm-failures/` in `reapply`: `set_capture_dir` is called only in `_execute`, and `redo` is the same. Worth considering before the real Checkpoint G apply, since every fresh brief there is an Opus call.
- **Old audio files can be left behind.** When a reapply changes a track title, the old-named audio file stays in `package/audio`, because packaged filenames include the title. `redo --from package` behaves the same way; nothing new here.
- **`compute_legs` and `classify` were used unchanged.** I found no reason to question either for reapply.
