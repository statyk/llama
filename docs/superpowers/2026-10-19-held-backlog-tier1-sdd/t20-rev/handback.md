### Spec Compliance

- ✅ Spec compliant (slice 6 "Batch state", "Predicted lists are tied to what produced them", "Acceptance", and the binding rulings M3, M5, capture, lock-pin, per-row ValidationError/OSError, pacing reuse), with one strict-surface gap: a `-dirty` code identity is compared by string equality (Important 1).
  - Batch dir + contract: `reapply.py:282-285` gives `root/reapply/sha256(bytes)[:16]`. `record_progress` writes `{"slug","outcome","retryable","at"}` (`reapply.py:309-310`), matching plan "Reapply batch state" (plan line 119). `list.json` is copied once (`cli.py:94-95`).
  - Finished rows are never re-applied: `cli.py:97,115-117`. A failure other than a refusal is recorded `retryable=True` (`cli.py:111`, `fail()`). `missing` is retryable (`cli.py:132`).
  - Usage-limit refusal: stops at the show boundary, records nothing, prints the resume line, exits 0 (`cli.py:143-148`). The arm sits above `HerderError` (`cli.py:149`).
  - 3-consecutive-LLM-failure stop: `cli.py:149-155`. M5's `_sleep` patch is in the test (`test_reapply.py:409`).
  - Pacing gate: before the row's work, using `_meter`/`decide`/`Progress(state.per_show_delta)`/`pace_options` exactly as the show loop does (cf. `cli.py:614-620` in the `_execute` loop). It never calls `pacing_state.record`, and the test patches `record` to raise (`test_reapply.py:626-628`).
  - SHA/config refusal: `reapply.py:275-278`, with the brief's message verbatim.
  - M3: entries are built per row inside the try (`cli.py:137-139`); `iter_shows` is unused.
  - Capture: switched on in both forms, never in dry-run (`cli.py:40-42, 91-92`), and pinned by `test_reapply.py:559-575`.
  - Lock-pin test (mutant h): `test_reapply.py:578-594`.
  - Per-row `ValueError`/`OSError` arm that does not touch `consecutive`: `cli.py:156-161`, pinned by `test_reapply.py:540-556`.
- ⚠️ Cannot verify from the diff: the strict-surface claim "a refusal leaves the show uncommitted". It rests on `reapply_show` making the brief call before its first `put` (pre-existing T19 code, `reapply.py:111-121` before `:127`). I checked it read-only and it holds. The pilot's log-verified "zero LLM calls outside fresh briefs" is a Checkpoint G check.

### Strengths

- M3 is done properly. `derive_state` + `CatalogEntry` per row inside the try (`cli.py:134-142`), with a test that damages one show's `overrides.json` and proves the next row still applies (`test_reapply.py:521-537`).
- The non-LLM arm (`ValueError` ⊇ pydantic `ValidationError`, plus `OSError`) is deliberately kept out of the LLM-stop count. A test fails three corrupt `show.json` rows in a row and asserts the stop does not fire (`test_reapply.py:540-556`).
- `record_progress` repairs a torn last line before appending (`reapply.py:312-319`), and `read_progress` skips unparseable lines in the safe direction (not finished). Both are pinned (`test_reapply.py:597-606`).
- The meter test pins the order: one gate read before the show, one read after, and `decide` is consulted once (`test_reapply.py:609-632`).
- `test_a_success_resets...` scripts `reapply_show` directly, so the counter logic is tested in isolation from provider retry counts (`test_reapply.py:430-451`).
- The mutation table names a predicted test per mutant, and each mutant was caught by its predicted test.
- The deviations are mostly sound:
  - D1: held rows package nothing, so excluding them from the download and fresh-brief counts is more accurate.
  - D4: shape validation up front turns a mid-batch `KeyError` into an up-front refusal (`reapply.py:271-274`).
  - D5: torn-line tolerance, as above.
  - D2 (dry-run skips finished rows and runs no gate) is reasonable. D3 is mostly reasonable (see Minor 3).

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)

1. **`reapply.py:275-276`: a `-dirty` identity is accepted by any other dirty tree (C1, judged).**
   - What is wrong: `code_identity()` returns `<HEAD>-dirty` for ANY uncommitted change, untracked files included (`replay.py:135-138`, `git status --porcelain`). `load_list` compares the strings with `!=`. So a list written from a dirty tree at HEAD X is accepted by a run on the same HEAD with *different* uncommitted edits. That is code the list's predictions were never computed for.
   - Why it matters: this is the named strict surface, "a list from another code sha … is refused". The implementer's C1 covers only the dirty-vs-clean direction, which is correctly refused. Dirty-vs-dirty is the silent hole, and it is the realistic development scenario: compare is run in a worktree, code is edited, then reapply runs.
   - Fix:
     - Simplest: in `load_list`, refuse when either identity ends in `-dirty`, with a message to commit first. One test pins it.
     - Alternative: make `code_identity` hash `git diff HEAD` plus the untracked file list into the suffix. That touches T2/T5's harness identity too, so the first is cheaper.

#### Minor (Nice to Have)

1. **`cli.py:143-161`: an uncaught exception type aborts the batch with a traceback, and the next run wedges on the same row.**
   - Concrete paths I checked:
     - `audio.tag_audio` → `mutagen.flac.FLAC(path)` raises `MutagenError`, an `Exception` and not `OSError`. I verified the MRO in the worktree venv. It is reachable from `build_package` (`stages/package.py:51`) on a FLAC that mutagen rejects when archive.org gave no md5.
     - `generate_briefing` gets a raw `read_json(ws.reviews)` (`reapply.py:116`). A wrong-typed `reviews.json` raises `TypeError`/`AttributeError`.
   - Mitigation: the codebase convention is narrow catches. The `_execute` show loop catches only `(TaskFailed, HerderError, IAError)` (`cli.py:582`). Shows that crash inside `compute_legs` would already have failed the harness and not reached the predicted list.
   - Why it is still worth fixing: the spec line "one bad show must never abort the batch" is strict, and a deterministic crash re-hits the same unfinished row on every re-run.
   - Fix: a last-resort `except Exception` arm after the existing ones. It goes through `fail()`, is retryable, and leaves `consecutive` alone. `RateLimited` and the LLM arms stay above it.
2. **`cli.py:169`: any success resets `consecutive`, including rows that made no LLM call (brief-mandated).**
   - Which rows: `briefing == "reuse"`, `needs-llm`, `skipped: not held`, `skipped: inputs changed`.
   - Effect: with a broken backend (openrouter 429, an unrecognised refusal), reuse rows interleaved among fresh rows keep resetting the counter. The batch then never stops, and each fresh row spends its full transport-retry budget.
   - Suggested fix: reset only when `out.briefing == "fresh"`, a real LLM success. This is labelled brief-mandated: the brief says "on success → consecutive = 0". The human decides.
3. **`cli.py:126, 148`: a pause returns exit 0 even when earlier rows in the same invocation failed (D3).**
   - The FAILED lines are on stderr, but a script checking `$?` sees success. Use `raise typer.Exit(1 if failed else 0)` on both pause paths, or document the choice.
4. **`cli.py:167`: the dry-run download count uses a manifest proxy (C2, judged).**
   - What reapply actually downloads: it drops only `package/manifest.json` (`workspace.py:99`, `drop_stage_artifacts("package")`). `build_package` then downloads exactly the tracks whose `dest` is absent (`stages/package.py:48-50`).
   - When the proxy is wrong:
     - It overcounts a never-delivered show that was once packaged and then redone from gather (manifest dropped, audio kept).
     - It undercounts only a manifest-present show with purged audio. Deliver refuses held shows, so that needs a delivered show re-held at package stage, which re-downloads in that redo. That case is effectively empty.
   - Verdict: the proxy errs on the safe side for a cost estimate, and the spec's "about 175 MB … per cleared show" is coarse. Still, counting rows whose `package/audio/` has no audio files would match what `build_package` decides, at the same cost.
5. **Coverage gaps in `test_reapply.py`.**
   - No test for D2: a dry-run over an existing batch should count `already finished` and skip those rows.
   - No test for D1: `held`/`needs-llm` predictions should be excluded from `fresh` and `downloads`. The only summary test has `fresh` = 0 and one row.
   - The 3-failure-stop test does not assert `exit_code == 1` (`test_reapply.py:426-427`).
6. **Concurrent runs of the same list (`cli.py:170`).**
   - What happens: two concurrent `--from-list` runs of the same list serialize on the show lock. The second records `skipped: inputs changed` (or `skipped: not held`) as that slug's LAST row, overwriting the first run's `cleared`/`held` outcome in `read_progress`.
   - Effect: finished-ness is unaffected; only the outcome record is lost.
   - Fix: document a single writer per list, or take a non-blocking batch lock for the whole run.

Test output: the implementer reports `26 warnings` on the full suite (handback line 49). It does not say whether any come from the new tests. The controller should check that the T20 tests emit none, e.g. with `-W error` on `test_reapply.py` alone.

Checks I ran (read-only):
- `drop_stage_artifacts("package")` deletes only the manifest (`workspace.py:92-112`). `build_package` downloads only absent tracks (`stages/package.py:48-50`).
- `download_file` wraps `httpx` errors as `IAError` (`ia_client.py:141-146`).
- `mutagen.MutagenError` MRO is `(MutagenError, Exception)`, and `CalledProcessError` is not an `OSError`. Python one-liner output is logged in `t20-rev.log`.
- `read_usage` never raises (herder `usage.py:118`).
- The show loop's gate shape matches (`cli.py:611-620`).
- `code_identity` uses `git status --porcelain` (`replay.py:129-141`).
- The harness writes the list's `sha` from the candidate arm (`scripts/replay_holds.py:687-689`).

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The batch mechanics are correct and well tested on every strict leg the orchestrator named: resumability, refusal leaving the show uncommitted, the 3-failure stop, the pacing gate without EWMA recording, M3 per-row isolation, and the capture switch. However, `load_list` accepts any list stamped `<sha>-dirty` from any other dirty tree. That silently defeats "a list from another code sha is refused", and the fix is a small refusal in `load_list` plus a test.
