# t6-rev (Task 6 review, 3cccc05..63c4a4b): DONE

### Spec Compliance
- ✅ Spec compliant. replay.py:329-331 adds exactly `and not gathered.taper_owned` to the stored-`llm` line. Nothing else in replay.py changes, so plan Step 3 holds. The relaxation keys on GatherResult.taper_owned, the in-process field from §4/§7. It does not key on gathered.needs_llm or on any alignment string.
- Every test the brief asked for is present (test_replay.py:160-224, test_reapply.py:1100-1125). The existing pin test_stored_llm_alignment_is_needs_llm (test_replay.py:151) is unchanged.
- Global constraints:
  - `git diff main -- packages/llama/src/llama/setlist.py` is empty.
  - The diff touches no protected names: the only source hunk is replay.py:329-331.
  - No existing test changed: the diff has no `-` lines in tests.
  - The tests are offline: tmp_path only, and the paf2007-10-12 excerpt is a literal.
- ⚠️ Cannot verify from diff: nothing open.

### Named-risk checks
1. **Is taper_owned False on every path that is not taper-owned?** Checked gather.py, compute_gather from line 1051 to its end.
   - It is initialised to False at :1330. The structure-override branch (:1331-1340) never reassigns it.
   - The only assignment is :1381, `taper_owned = decision.placement is not None`, on the non-override path.
   - compute_gather has exactly one `return GatherResult(...)`, at :1696. Every other exit is a raise, which compute_legs does not catch (replay.py:324-327), so no partial result can reach the relaxation.
   - GatherResult.taper_owned defaults to False (gather.py:998).
   - So the relaxation cannot fire by default, and cannot fire on any path Task 4 did not set.
2. **Do the "stays needs-LLM" tests reach the branch, and would they catch a wrong key?** All of them build the stored show with alignment="llm" through library_show and run the real compute_legs. I re-ran the mutants myself. Setup:
   - A git-archive copy of 63c4a4b, run from a scratch cwd with PYTHONPATH shadowing and a per-mutant PYTHONPYCACHEPREFIX.
   - Each run printed `llama.replay.__file__` and the mutated source line, both inside the copy.
   - The unmutated baseline of the copy passed 153 tests (test_replay.py plus test_reapply.py).

   | Mutant | Condition | Result |
   |---|---|---|
   | A | condition removed | KILLED by test_stored_llm_taper_owned_is_replayable and test_reapply_processes_a_taper_owned_stored_llm_show |
   | B | `and gathered.needs_llm` (relax when gather made no LLM call, the key §7 forbids) | KILLED by stored_llm_alignment_is_needs_llm, deterministic_candidate, anchored_candidate, track_title_veto and test_reapply_writes_nothing_on_a_needs_llm_show |
   | C | `and gathered.show.structure.alignment != "deterministic"` | KILLED (5 tests) |
   | D | `and gathered.taper is None` (keying on `taper is not None`) | KILLED (6 tests, including cross_check and anchored) |
   | G | `and gathered.show.structure.alignment != "taper"` (keying on the alignment string) | KILLED by the replayable test and the reapply test. In both, the replayed alignment is not "taper", so the tests separate taper_owned from the string. |
   | I | `and not stored.structure.taper_owned` (the stored show's persisted field instead of the candidate's) | KILLED by test_track_title_veto_keeps_stored_llm_needs_llm and the reapply test |
   | J | `and not (gathered.step1_alignment is not None and gathered.needs_llm == ())` | KILLED (5 tests) |
   | F | `and not gathered.show.structure.taper_owned` | SURVIVES, as expected. It is equivalent by construction: gather.py:1646-1652 stamps StructureInfo.taper_owned from the same local, and that branch always runs when taper_owned is True. Not a finding. |

   Mutant log: `$D/t6-rev/t6-rev.log`.
3. **Does the reapply test show what it claims?** Yes (test_reapply.py:1100-1125).
   - Without the flag the outcome is `skipped: structure changed` with `written == []`. The whole-directory snapshot is byte-identical and build_package is never called.
   - With `allow_structure_change=True` the outcome is `cleared`, package runs, and the persisted structure has taper_owned True and alignment not "llm".
   - Mutant A turns this test red, so it really depends on the relaxation.
   - Every relaxed show is always structure-changed. A replay never yields "llm" once taper-owned, so the alignment entry of shipped_diff is always non-empty (replay.py:226, :232-235). The relaxation therefore can never auto-apply without `--allow-structure-change`. This is a good safety property, and the reapply test exercises it.
4. **Is any other consumer of the string or the ordering affected?**
   - grep finds the string "stored alignment llm" only in replay.py:331, test_replay.py, and scripts/test_replay_holds.py:426,539. The scripts only use it as a literal in synthetic arms, so they are unaffected.
   - The append position is unchanged, so the order documented in the Legs comment at replay.py:281 still holds.
   - reapply.py branches only on the `needs-llm` outcome (:102), never on the reason string.

### Strengths
- The change is a minimal one-line condition matching plan Step 3 exactly.
- The tests separate the spec's three forbidden keys cleanly:
  - "no LLM call", via the deterministic candidate with `needs_llm == ()` asserted (test_replay.py:184-188);
  - the anchored/jerrybase candidate, with the mechanism asserted (:196-203);
  - the §2 cross-check and track-title vetoes, with the decline reason asserted (:209, :222). These prove each test reaches the intended decline rather than passing by accident.
- The replayable test asserts `needs_llm == []`, not just that the string is absent.

### Issues
#### Critical
None.
#### Important
None.
#### Minor
- t6-impl handback.md, "Mutants" B: the reported mutant `and not gathered.needs_llm` is the inverted sense. It appends the reason only when gather needs nothing. It is not the "relax when no LLM call" mutant that §7 forbids. That forbidden mutant (my B) is also killed, by 4 replay tests and the existing reapply pin, so the coverage claim holds. Only the report was inaccurate.
- test_reapply.py:1104: `from fixture_library import IDENT` is a function-local import. The module already imports from fixture_library at line 10, so it could join that line. Cosmetic.

### Assessment
**Spec:** ✅ **Task quality:** Approved
**Reasoning:** The relaxation keys only on GatherResult.taper_owned, which compute_gather sets True on exactly one non-override path and returns from a single exit. Seven independently built mutants, covering every forbidden alternative key, are each killed by targeted tests. The only survivor is provably equivalent.

Status: DONE. No commits, no repo edits. Test command: mutant runs only, `python -m pytest -q -p no:cacheprovider test_replay.py test_reapply.py` from the scratch copy. Baseline 153 passed; A, B, C, D, G, I and J killed; F survived (equivalent).
