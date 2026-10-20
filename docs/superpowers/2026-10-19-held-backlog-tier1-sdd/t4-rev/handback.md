# t4-rev: Task 4 review (compute_legs, briefing_reusable, classify), 383e01a..30461a1

### Spec Compliance

- ✅ Spec compliant, with the orchestrator rulings applied:
  - **Ruling 5 / no-exception needs-LLM**: `classify` returns `needs-llm` first, with no carve-out (replay.py:275-276). "no vetting.json" is appended unconditionally when the file is absent (replay.py:241-244). This matches spec 322-323 and 839-840. It is pinned for held and packaged shows with a real deterministic gather flag (test_replay.py:494-506), and by the synthetic `test_classify_needs_llm_wins_over_every_flag` (test_replay.py:706-713).
  - **M7**: `ShowReplay.date` sits after `city`, and the key order is pinned (test_replay.py:716-724). `classify` and `briefing_reusable` both diff against the vetted show (replay.py:245, 258, 277; `Legs.replayed_show` at 202-205). Both directions are pinned: test_replay.py:572-593.
  - **Gate counts carried package flags**: `flags` includes `carried` before the `if not flags` gate (replay.py:247-254). Pinned with a stored, otherwise-reusable briefing, so the gate is the only thing making `brief == "none"` (test_replay.py:532-540).
  - **Brief-leg reuse rule** (spec slice 6 step 3), in this order: broadcast fields (titles, sets, segues, set_breaks, date, venue, city), then narration, then the guard (replay.py:158-181). `title_source` is correctly excluded, and that is tested (test_replay.py:667-669). A failing guard means "fresh", not a flag, which matches "otherwise one fresh briefing" (spec 842-848).
  - **Vet leg**: `apply_vet(stored extraction, replayed gather show)`; the extraction is never re-run (replay.py:241-242).
  - **Outcome classes and `structure-changed`**: `structure-changed` covers sets, segues, set_breaks and alignment, and nothing else (replay.py:152-155, 284-285, spec 337-340). Non-held shows get clean, clean-changed or newly-held (replay.py:287-291). `"held"` matches `catalog.derive_state`'s literal (checked catalog.py:123).
  - **flag_family** matches the Contracts table entry for entry, and the `research-*` families are tested before the generic ones (replay.py:75-91). Parametrized over every listed prefix (test_replay.py:727-752).
  - **Review Focus 3**: covered by the unit test (test_replay.py:675-681) and end to end from a raw legacy briefing.json (test_replay.py:684-693).
  - **Gather test** with a provider on the extract path: test_stage_gather.py:768-779.
- **Deviation (a): track-count change ⇒ every index in set_changes/segue_changes, so a would-clear show becomes `structure-changed`.** I judge this correct against the spec's intent. The structure-changed list is the hand-check gate before an apply list (spec 337-340). A changed track list is a strictly larger structural change than a relabel, and the alternative is worse: a count change whose labels happen to align positionally would ship as `clears`/`needs-brief` with no hand check. Such a show can never be `clears` anyway, because a count change fails the titles broadcast-field check and is at most `needs-brief` (replay.py:166). See Minor 1 for the payload shape.
- **Deviation (b)**: `Legs.briefing` is set only on reuse (replay.py:260-261), which is the safer contract for Task 19. `replayed_show` is a pure accessor. Both are sound.
- ⚠️ **Cannot verify from this diff:**
  - Task 5 must map an unreadable `overrides.json` to `unreplayable: overrides.json unreadable`. Here it surfaces as a pydantic error from inside `compute_gather` over the scratch copy, or from `read_overrides(ws)` at replay.py:259.
  - The plan's Task 19 step 5 clause ("`legs.vet` is None only on a no-vetting.json show that classify called still-held") is stale under the no-exception ruling. Past `classify`, `legs.vet` is never None. The implementer flagged this too; the controller should amend Task 19's brief.

### Checks run
- **Do-not-retune constants**: grepped the whole diff for every name in Global Constraints (is_real_title, title_fraction, _TRACK_NUM_PREFIX, normalize_song, DEFAULT_ALIASES, GD_SHORTHAND, _RECOVER_*, tail-guard, junk-duration, align_coverage_threshold, _ENUMERATED_MIN_*, _STRUCTURE_PREFIX, _FOOTNOTE_TAIL). There were no hits.
- **Named risk: vet flags double-counted or gather flags lost.** Read `apply_vet` (vet_research.py:168-181). `result.flags` holds only vet's own `research asserts` flags, and `vet.show.review_flags` = gather's kept flags + vet flags. `Legs.flags` is therefore gather + vet with no duplication. Note for Task 19: `replayed_show.review_flags` does NOT carry the package flags, so its final show must add `carried_flags`.
- **Named risk: the scratch rmtree reaching the library.** Read the call patterns in the plan:
  - The harness uses `scratch/<slug>` (plan 953) with `--scratch` operator-supplied (plan 799).
  - reapply uses mkdtemp (plan 2691).
  - With the `scratch/<slug>` convention, the only library path a mis-pointed `--scratch` can resolve to is the same show's own dir (e.g. `--scratch ~/.llama/shows`), and the guard refuses that by resolved path, as well as a scratch inside or above it (replay.py:218-220). It is tested for all three relations, with the tree byte-checked unchanged (test_replay.py:448-457).
  - Residual: see Minor 2.
- **Mutation table plausibility**: traced (f), (j) and (l) by hand against the tests that claim them, and all three are caught as claimed:
  - (f): the gate without carried flags reaches a reusable stored briefing, so `brief == "reuse"`, which fails test_replay.py:538.
  - (j): stored alignment "override" vs replayed deterministic, so dropping alignment yields `clears`, which fails test_replay.py:560.
  - (l): the stored date is research-adopted and the gather show's is not, so the titles/date check reports `date` and reuse fails at test_replay.py:592.
  - I did not re-flip a mutant, since no claim looked doubtful.

### Strengths
- `classify` is short and ordered exactly as the spec's precedence. The needs-LLM short-circuit is one line, with nothing for Tasks 5 and 19 to re-derive.
- The tests build library shows with the real `run_gather` over the gd73 fixture, so `compute_legs` is exercised end to end rather than against mocks. The "writes nothing" test byte-compares the whole show dir (test_replay.py:423-433).
- The implementer found a survivor (l) and closed it with a test that pins a real production path (placeholder-date adoption).
- `Legs.briefing` is None unless reused, so a rejected briefing cannot be shipped by a later task.
- The scratch guard is a sensible unrequested safety addition on a strict surface. It is small and tested.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **Count-change rows report `new: None` even where the replayed show has a value** (replay.py:124-130).
   - For titles this is brief-mandated. Extending it to set_changes and segue_changes means compare's structure_changed.txt and title-source list show `set 2 -> None` for every track of exactly the shows that most need a careful hand check.
   - Suggestion for the controller: populate `new` and `new_source` from `new.tracks[i]` when `i < len(new.tracks)`, keeping every index listed. This is the plan's call, since it amends the brief's title_changes shape.
2. **The scratch guard protects only `ws.dir`** (replay.py:218-222).
   - A scratch that resolves to a different library path (another show's dir, `cache/`, `runs/`) would still be rmtree'd. Current callers cannot produce that (see Checks), so this is defence-in-depth only.
   - Cheap hardening: also refuse a scratch at or inside `ws.dir.parent` (the shows/ directory). Tests put scratch at `<root>/scratch`, so this would not break them.
3. **`brief_flags` is [] by construction** (replay.py:262). It re-runs the same guard that `briefing_reusable` just passed. This is harmless now.
   - Task 14 will insert `normalize_briefing` before the guard. It must apply it at both guard calls, and to the briefing that is reused, or the reuse decision and `brief_flags` diverge.
   - Suggestion: have `briefing_reusable` and this call share one helper.
4. **The held branch gives carried package flags precedence over remaining gather/vet flags** (replay.py:279-282). A show with both is `still-held-package`. The Contracts do not order these, and the choice is defensible (reapply never clears a package flag), but it is not pinned by a test with both kinds of flag present.
5. **Mid-file imports appended under the Task 4 banner** (test_replay.py:348-356), including a second `from pathlib import Path` block. This is cosmetic and follows from the brief's "append" instruction.

### Assessment

**Task quality:** Approved

**Reasoning:** The needs-LLM verdict and outcome classification match spec slice 0, slice 6 and the Contracts, with all three orchestrator rulings applied and pinned by tests that drive the real gather. The deviations are conservative on strict surfaces. The remaining items are payload-shape and defence-in-depth polish, plus forward notes for Tasks 5, 14 and 19.
