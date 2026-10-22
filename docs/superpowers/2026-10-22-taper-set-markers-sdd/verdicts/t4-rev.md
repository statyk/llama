# t4-rev: Task 4 review (spec + quality), 6cf03ea..19b0ad2

**Status: DONE.** Read-only review: no commits and no repo edits. The mutants ran in scratch copies under `.../scratchpad/t4-rev/m/`. Each copy imported itself, which I proved with a per-mutant `llama.stages.gather.__file__` check. A planted sentinel mutant was caught, and the M0 copy was green.

### Spec Compliance

- ✅ **Spec compliant** with §2 (track-title veto, via `decide_taper`), §4 and §6, and with every brief item.
  - **Step order** (gather.py:1300-1371):
    - Step 1 (align + anchoring) is unchanged.
    - `decide_taper` is called through the module with `today_sets=step1_sets`.
    - `today_sets` is parallel to the tracks: asserted at :1333, and spy test `test_today_sets_is_step_one_parallel_to_tracks`.
  - **Owned branch:**
    - No LLM call.
    - The low-confidence flag uses the four-clause conjunction (:1352).
    - `StructureInfo.coverage` is the reader's coverage.
    - Segues and `matched` come from step 1 (:1424-1427).
    - The anchor note is dropped, since it is only appended when not owned (:1365-1367).
    - The `merge_conflicts` flag is dropped (:1449).
    - `alignment = "taper"` and the "was" op note go to `op_notes`, never `conflicts` (:1359-1363).
    - `StructureInfo` is created when owned and carries `taper_owned` (:1591-1597).
  - **Not owned:** today's path. The `elif anchor_note` preserves the old note position. The LLM branch is untouched.
  - **Override path:** never calls `decide_taper`; `taper`/`step1_alignment` are None.
  - **New fields** are defaulted and last: `StructureInfo.taper_owned` (models.py:150) and the three `GatherResult` fields (gather.py:953-955).
  - **Ruling R2:** the `_sans_taper` pins compare every other field, including `step1_alignment` and `taper_owned`.
  - **Global constraints:**
    - `git diff main -- packages/llama/src/llama/setlist.py` is empty (0 lines).
    - A protected-name grep over the diff finds only imports and uses of `normalize_song` and `is_filler`. No definition is edited.
    - No test line was removed (`git diff ... -- packages/llama/tests | grep -c '^-[^-]'` = 0).
    - No new config keys or CLI flags.
  - **Commits:** both end with the mandated trailer lines, the last carries the plan subject (R1), and the Step 4 grep result is recorded in 19b0ad2's message.
  - **Umphreys deviation:** the test adds setlist.fm set names copied from the cache (reasoned in the handback). This is acceptable. The test still embeds verbatim literals and reproduces the shipped show's canonical source.
- ⚠️ **Cannot verify from this diff: Task 5 territory, interim behaviour on `HEAD`.**
  - The closer tripwire (gather.py:1556) still keys on `alignment != "jerrybase"`, with two consequences:
    - An owned show whose step 1 was `jerrybase` and whose taper differs now has `alignment == "taper"`. The tripwire runs on the taper's labels and can raise hard `jerrybase set closer …` flags. Today it was skipped.
    - An owned show that agrees with anchoring still skips it, although spec §5 says it runs on owned shows.
  - `structure has N sets but jerrybase shows M` (:1572-1576) still fires as a hard flag on owned shows. Example: `test_taper_beats_jerrybase_anchoring`'s result carries it, and the test does not assert on it.
  - The controller should make sure Task 5's brief covers both. Task 5 should also include a test that the tripwire skip is keyed on ownership plus mechanism, not on the `alignment` string.

### Strengths

- **Minimal, readable restructure.** Step 1 is kept as a value (`step1_sets`/`step1_alignment`). Ownership is a single predicate, `decision.placement is not None`. The not-owned path's LLM branch is unchanged except for its `elif` line.
- **Oracle-based pins** (`_oracle`/`_sans_taper`) are the right instrument. They test "exactly today" on the whole `GatherResult`, not on hand-picked fields.
- **Override-path pin** uses a raising `decide_taper` stub, which proves the taper is never consulted.
- **The parallel `today_sets` requirement** is pinned twice: a spy test, and an in-code check.
- **Mutation check:** I ran 8 mutants against the task's tests.
  - A sentinel `taper_owned = False` failed 6 tests.
  - Re-adding the anchoring note on owned shows (M5) was caught by `test_taper_beats_jerrybase_anchoring`.
  - Recording step-1 coverage instead of the reader's (M6) was caught by `test_owned_low_confidence_uses_reader_coverage`.
- **No unpacking breakage:** no call site unpacks `GatherResult` positionally. I checked `replay.py:324-356`, `run_gather` (gather.py:1661-1673), and the test_replay/test_fix constructions. All use attribute access or keywords, so the appended fields are safe.
- **No consumer switches on the new values:** `StructureInfo` does not reach the manifest, emcee or transmitter (grep of `stages/package.py`, `emcee/*.py`, `transmitter/*.py`). `replay.briefing_reusable` compares fields, not bytes. So the new persisted key and the `"taper"` value need no reader changes outside Task 6/7.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **packages/llama/tests/test_stage_gather.py:3348-3374 (`test_owned_low_confidence_uses_reader_coverage`): three of the four clauses gating the owned-show low-confidence flag (gather.py:1352) are unpinned.**
   - **The brief's own sub-case does not test its clause.** "No canonical items → no flag" (the `bare` case, :3370) runs with reader coverage 1.0, so it passes whether or not `canonical.items` is checked.
   - **Mutants that survive the task's tests** (predicted SURVIVE before running, and all survived):
     - M1 drops `canonical.items and`.
     - M2 drops `anchored is None and`.
     - M3 drops `result.coverage < threshold and`.
   - **Why it matters:** these clauses are the spec §4 rule "only when today's path would have reached the LLM branch". Under the plan's rule "every behavioural change gets a test that fails on today's code", that sub-case asserts nothing about its subject.
   - **Fix:** keep reader coverage below the threshold in three extra cases, and assert no flag in each:
     - (a) no canonical items: put the `weak_desc` text in `notes` with an empty description;
     - (b) jerrybase anchoring succeeds;
     - (c) step-1 coverage is at or above the threshold (setlist.fm matching the tape) while the reader's items are weak.

#### Minor (Nice to Have)
1. **gather.py:1333, `assert` in production code.** It is stripped under `-O`, and if it fails it surfaces as an opaque per-show `other` failure. If the check is wanted at runtime, raise `LlamaError` with a message. Otherwise rely on the spy test.
2. **gather.py:1359-1360, the filler exclusion in the "differs" test is unpinned.** Mutant M4, `if True`, survived. The implementer argues that a filler-only difference cannot be reached through `decide_taper`. That holds while Task 2's filler rule stands; Task 8's mutation run should note it, or a unit test with a patched `decide_taper` returning a filler-only difference could pin it.
3. **test_stage_gather.py:3281, a vacuous absence assertion.** "No `setlist evidence shows multiple sets…`/`single-set…` flag" passes on the oracle too: 7×5 min is below `guard_min_minutes` (150), and setlist.fm shows one set. The test does not show that ownership removed anything here. To make it discriminate, use a canonical whose evidence would flag, or lengths over 150 min.
4. **Interim `HEAD` state (see ⚠️ above):** owned shows can carry hard jerrybase set-count and closer flags until Task 5 lands. Don't run acceptance arms on Task 4's `HEAD` alone.
5. **Umphreys test:** "identical to today" holds only with setlist.fm present. Without it, today ships 1/encore and the taper ships 1/2/encore. This is intended behaviour, but it is worth stating in the acceptance notes so the arm's diff is not read as a defect.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The implementation is correct, minimal and spec-faithful, and the oracle pins are well built. However, the owned-show low-confidence gate, a spec "my call" rule, has three conjuncts that no test exercises, including the brief-mandated "no canonical items" case. Adding three short test cases closes it; no production change is needed.

**Checks run:**
- Scratch-copy mutants M0-M6 plus the sentinel, each with an import-path proof. Results are in `$D/t4-rev/t4-rev.log`.
- `git diff main -- setlist.py` (empty).
- The protected-name grep over the diff (uses only).
- A grep for removed test lines (0).
- Call sites of `GatherResult`/`compute_gather` (no positional unpacking).
- `briefing_reusable`/`input_digests`, for byte sensitivity to the new key (none).
- Consumers of `StructureInfo` in emcee, transmitter and the package stage (none).
