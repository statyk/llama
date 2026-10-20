### Spec Compliance

- ✅ Spec compliant. Every interface in task-3-brief.md is present:
  - `grounding_flags` returns `(flags, adopted, notes)` with `notes == []` (vet_research.py:102, :113, :159).
  - `VetOutcome(NamedTuple)` has `show`, `result` and `notes` (:162-165).
  - `apply_vet` is pure (:168-180). It works on a `model_copy(deep=True)`, applies the placeholder-date adoption (`item_date`, `date`, `date_source="research"`), keeps the non-`research asserts ` flags and adds the new ones, recomputes `needs_review`, and returns `VettingResult(vetting, flags, adopted_date)`. Nothing in it writes or calls an LLM.
  - `run_vet_research` (:184-202) keeps its signature. It writes `show.json` from `out.show` and `vetting.json` from `out.result`, then reads `notes.json` (empty `ShowNotes` if absent), sets `vet`, and writes it. That matches the Contracts entry "updated by run_vet_research (sets vet)" and spec ruling 6.
  - Invariant held: given a provider, the flag logic, the adoption and the `show.json`/`vetting.json` contents and write order are unchanged; the only addition is the `notes.json` write.
- ✅ Equivalence of grounding against `read_model(show_ws.show)` instead of the `show` argument. Named risk: the disk show differs from the argument. Checks:
  - The only caller is pipeline.py:88. Its `show` comes from `run_gather`, which returns either `read_model(show_ws.show)` on skip or `res.show` just after `write_artifact(show_ws.show, res.show)` (gather.py ~1287-1301). Both equal the disk copy.
  - `run_research`, which runs in between, never writes `show_ws.show` (grep of research.py: no hits).
  - A prior vet adoption on disk was already visible in the old `show` argument, because it came from the same disk read. So the grounding inputs are identical on every path.
- ✅ Grep of the diff for do-not-retune constants: the only hit is `normalize_song`, at vet_research.py import and :113. Both are unchanged context lines, so no protected constant was touched.
- ⚠️ Cannot verify from the diff (cross-task): Tasks 4, 15, 16 and 19 consume `apply_vet`, `VetOutcome` and the 3-tuple. Check this when they land.

### Strengths
- `apply_vet` is a faithful extraction of the old body, with no behaviour drift. The deep copy makes purity structural, not incidental.
- The old 2-tuple unpack was internal to vet_research.py, and the call-site grep confirms there are no other unpacks in src or tests (the brief's update step really was a no-op).
- The new tests are discriminating even though RED was never observed. I flipped two mutants in scratch copies (shadowing proved by `llama.__file__` printing a path under the copy; private pycache for each):
  - **Mutant 1**, `out = show` with no copy. Predicted: both apply_vet tests fail. Caught by `test_apply_vet_is_pure_and_replaces_only_its_own_flags` and `test_apply_vet_adopts_a_placeholder_date_on_the_copy` (2 failed, 33 passed).
  - **Mutant 2**, the notes.vet assignment and the notes write removed. Predicted: the notes test fails. Caught by `test_run_vet_research_writes_vet_notes_into_notes_json` (1 failed, 34 passed).
  - Against the old code the notes test would also fail on substance, not only on the import: the stale `vet=["stale"]` would survive.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. vet_research.py:197-202, write order. `notes.json` is written after `vetting.json`, which is the stage's `should_run` done-marker. A crash between the two writes leaves `vet` notes from a previous vet in place. A later non-forced run then skips (it hits the :190 early return) and never refreshes them.
   - This is harmless now (`notes` is always `[]`), but it matters from Task 16, when 4a notes become non-empty.
   - The reachable case is `redo --from vet` (it drops only `vetting.json`) followed by a crash.
   - Fix: write `notes.json` before `vetting.json`, the same marker-last discipline run_gather documents at gather.py ~1296.
2. vet_research.py:184-186. The `show` parameter of `run_vet_research` is now dead: the body grounds against disk only. The brief mandates both the signature and the disk read, so this is not a defect. But a future caller that passes a show different from disk would be silently ignored, and only the comment at :193-195 says so. Consider noting it in the docstring, or dropping the parameter in a later cleanup.
3. test_stage_vet.py:412-424. The purity test asserts that the input is untouched, but no `apply_vet` unit test covers `needs_review` going True→False when the vet flag was the only flag. Existing `run_vet_research` tests cover the re-vet-clears path end to end, so this is coverage breadth only.

### Assessment

**Task quality:** Approved

**Reasoning:** This is a clean, behaviour-preserving extraction. The pure step matches the brief exactly, the disk-versus-argument grounding is equivalent on every path that reaches it, and the new tests catch the two most plausible regressions. The Minor issues can be left for later; the write order (Minor 1) is worth fixing before Task 16 makes vet notes non-empty.
