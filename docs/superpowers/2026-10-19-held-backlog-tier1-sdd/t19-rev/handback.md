### Spec Compliance

- ✅ Spec compliant. I checked the brief's Interfaces and the five binding rulings against the diff. Line numbers below are positions in the diff file `review-c851243..e73eea6.diff`.
  - **`build_package`** (diff 374-407): `run_package`'s body minus the `show.json` write. An existing manifest returns `(pkg, [])`. `run_package` (410-418) is `build_package` plus the unchanged flags write.
  - **`vetting_summary_text` / `generate_briefing`** (254-323): `run_brief` (326-356) keeps its writes. It now reads `vetting.json` itself and passes the result in; the behaviour is the same.
  - **`reapply_show`, steps 1-4.**
    - The lock is taken first (161). The `show.json` re-read, the not-held skip and the digest skip all happen inside it (162-169).
    - `compute_legs` gets `CacheOnlyIA` and `setlistfm_client(config)`, with a scratch dir created by `mkdtemp` and removed in a `finally` (171-176).
    - It maps `classify`'s outcome and never re-derives needs-LLM (178-185).
    - Dry-run predictions come from `_PREDICTED` (125-131).
  - **`reapply_show`, step 5 (ruling).** `final_show = legs.replayed_show`, and the flags are `legs.flags` (190-193), never `replayed_show.review_flags`. The fresh brief runs before any write, and its problems are added to the flags (195-205).
  - **`reapply_show`, step 6, write order.** `vetting.json`, `notes.json`, `briefing.json`, `briefing.md`, then `drop_stage_artifacts(ws, "package")` and `build_package` with the provenance profile (only when there are no flags), then `show.json` once and last (213-232).
  - **3a ruling.** On reuse, both briefing files are written from the model (220-221). `legs.briefing` is normalised by `replay._read_briefing` (replay.py:263-268).
  - **Never written.** `reviews.json`, `provenance.json`, `research.md` and the ledger are not written; `_delivered` (146-148) only reads the ledger.
  - **CLI** (33-74): the names form, the four exception types reported as FAILED with the loop continuing, exit 1 on any failure, and `--from-list` reporting not implemented.
  - **Do-not-retune constants:** grepped the diff for every name in the Global Constraints list, plus `conflicts`, `review_flags.append` and `VettingResult(`. None appear.
- ⚠️ **Cannot verify from the diff alone:** the briefing-reuse rule (broadcast fields and narration agree, and the guard passes) lives in `replay.briefing_reusable`, from an earlier task. `test_reapply.py` has no test where reuse is declined on a narration or broadcast-field mismatch while gather and vet are clean. The controller should confirm that the Task 3/4-era tests of `briefing_reusable` cover the spec's "Testing" bullet for this.

**Implementer concerns and deviations**
- **C1 (a refusal in the names form prints FAILED and the loop continues): accepted.** This is what the brief specifies. The spec's stop-on-refusal, the 3-consecutive-failure stop and the pacing gate belong to Task 20's batch form. Task 20's review must hold it to all three.
- **C2 (no `llm-failures/` capture): valid.**
  - Confirmed: `set_capture_dir` is called only in `cli._execute` (cli.py:452, inside `_execute` at cli.py:408), so `redo` has the same gap.
  - This is cheap to fix and matters before Checkpoint G's roughly 250 Opus briefs. See Minor 2.
- **C3 (an old-titled audio file is left behind): accepted as pre-existing.** `redo --from package` behaves the same way. Minor, and not this task's to fix.
- **D1 (the re-deliver reminder prints only on `cleared`, diff 71): accepted.**
  - On `held`, a dry-run or a skip, the deliver gate would refuse the show, or nothing has changed. `ReapplyOutcome.delivered` stays the plain ledger fact on every outcome.
  - The orchestrator should record this as a ruling, since the spec's wording is "on a show the ledger records as delivered".
- **D2 (extra tests): accepted, and they add value.**
  - The `_stale` helper (diff 470-476) closes a real blind spot: a premature `vetting.json` or `notes.json` write would otherwise be byte-identical on the fixture and invisible to the snapshot comparison.
  - The B6 `.lock` touch is in `_snapshot` (464-467).

### Strengths
- **The write path follows the strict surface closely.**
  - One `put` helper records the order (209-211), and `show.json` is the only write after the package (231-232).
  - The fresh brief happens before any write (187-205), so a refusal leaves every file byte-identical. `test_reapply_writes_nothing_on_a_refusal_mid_show` (diff 614-622) pins this against stale vetting and notes files.
- **Defensive checks.** An outcome `classify` should never return raises a `LlamaError` instead of falling through (diff 181-182). A missing `show.json` is a `LlamaError`, and `CacheMiss` subclasses `LlamaError` (replay.py:32), so a cache miss is reported as FAILED and the loop continues; it does not crash.
- **The lock test covers three points.** It asserts the lock is held at `compute_legs`, inside `build_package` and at the `show.json` write, and that it is released afterwards (diff 683-711).
- **The test for mutant (g)** (diff 531-549) reproduces the Checkpoint D case: a stored `briefing.md` with an empty `## Encore` heading.
- **The carried package flag** (diff 590-599) and **still-held after vet** (diff 577-587) tests pin the spec's "never clears one" rule and its "new flags written, no package" outcome.
- **Profile parity with `redo`.** Checked: `redo` passes `profile=prov.profile` (cli.py:2252), and `reapply` reads the same field (diff 191).
- **Inputs to a fresh brief match `process_show`.** `research.md` text and `reviews.json` are read the same way as pipeline.py:86 and :93. The show passed in has `review_flags == []`, as in `process_show`'s not-held path.
- **`drop_stage_artifacts(ws, "package")` removes only `package/manifest.json`** (workspace.py:99).

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)

1. **No test pins the lock across the still-held and digest checks** (`reapply.py`, diff 161-169).
   - The code is correct: the lock comes first. But the spec names this ordering as strict ("from before the still-held check"), and nothing pins it.
   - I ran it as mutant (h): moved the `show.json` re-read, the not-held skip and the digest skip above `with file_lock(ws.lock):`.
     - Predicted outcome: SURVIVED.
     - Shadowing proven: `llama.reapply` resolved under the copy.
     - Result: `test_reapply.py` gave 25 passed, so the mutant **survived**.
     - Log: `$D/t19-rev/t19-rev.log`. The copy has been removed.
   - This is a time-of-check/time-of-use gap that only a refactor could introduce. It is cheap to pin before Checkpoint G runs this against `~/.llama`.
   - Fix: in a test, monkeypatch `reapply_mod.input_digests` (with a `row` given) or `reapply_mod.read_model` with a spy that asserts `Locked` under `file_lock(ws.lock, blocking=False)`.
2. **Failed `claude -p` output is not captured** (cli.py `reapply`, diff 55-56; this is C2).
   - CLAUDE.md states that every failed `claude -p` is captured under `~/.llama/llm-failures/`. `reapply`'s only LLM call is the fresh Opus brief, and its failures are lost.
   - Fix: add one line, `set_capture_dir(config.root / "llm-failures")`, after `_setup()`. It can land here or in Task 20, but before Checkpoint G. `redo` has the same pre-existing gap.
3. **An applied structure-changed show prints only `-> cleared`** (diff 70, 233).
   - The spec gates structure-changed shows on a hand-check before they join an apply list. In the names form, the operator who named such a show sees no sign that its set or segue labels changed. Only `--dry-run` says `structure-changed`.
   - Fix: consider adding ` (structure changed)` to the line, or leave the gating to Task 20's list form. This is advisory; the brief's outcome set does not include it.
4. **Other errors abort the whole loop with a traceback** (diff 66).
   - A pydantic `ValidationError` from a corrupt `show.json`, `provenance.json` or `vetting.json`, or a bare `OSError`, is not one of the four caught types.
   - This matches the brief. It is noted for Task 20, where the batch form must record such a failure as retryable rather than crash.

### Assessment

**Task quality:** Approved

**Reasoning:** `reapply_show` maps `classify`'s outcome without re-deriving needs-LLM. It writes nothing before the one LLM call, writes `show.json` once and last under the lock, and drops a stale manifest before packaging. The listed mutants (a) to (g) each have a test that catches them. The one gap I found, an unpinned lock across the still-held check (mutant (h) survived), affects test coverage only: the code is correct.
