### Spec Compliance

- ✅ Spec compliant (spec 2.5, 3; brief Task 2). Every brief item has its hunk:
  - `Track.short_kept: bool = False` sits right after `included`, with a comment saying it is show.json only (models.py:181-184). `ManifestTrack` is untouched, and a test pins that (test_stage_gather.py `test_short_kept_survives_to_show_json`, the last two lines).
  - `resolve_titles(..., short_kept: frozenset[str] = frozenset())` stamps `short_kept=f["name"] in short_kept` at the one place it builds a `Track` (titles.py:451, 538). The stamp is set where the cascade builds tracks, before `align()`, per spec 2.5.
  - `title_cascade` passes `frozenset(inp.ordering.get("short_kept", ()))` (gather.py:1366-1367).
  - `_songish_coverage` gains only `and not t.short_kept` in the same comprehension. No second filter was added (structure.py:1196-1198).
  - The junk note sits after the `if "slice5" in enabled_slices:` block (outside it) and before `Show(...)` (gather.py:2028-2032). It fires once per short-kept track whose final title `short_tag_is_junk` judges junk.
  - The note string matches the fixed string exactly: `short-kept track <n> '<title>': its final title is wholly junk`.
  - All 7 brief tests are present. One extra: `test_furthur_tuning_up_short_kept_is_noted_wholly_junk`, a fixture-backed instance of the same clause, which is fine.
- ✅ Byte-identical constraint. I grepped the changed (+/-) lines for every "Untouched" name. The only hits are references: `FORMAT_BY_AUDIO`/`LOSSLESS_TITLE_FORMATS` in the extended import line, `is_filler`/`TAUTOLOGICAL_TITLE_SOURCES` in the comprehension's unchanged first line, and `ManifestTrack` in a comment and a test. None of them is modified.
- ✅ Named risk 1: does every rung after `resolve_titles` preserve `short_kept`?
  - Check: grep for `Track(`, `__class__(`, `type(t)(`, `Track.model_validate`, `model_construct` and `**t.` over packages/llama/src.
  - Result: there are only two `Track(` constructions. One is titles.py:535 (stamped). The other is title_hygiene.py:582, the `neighbours` list inside `plan_setlist_rung`, which only feeds `_s_check` and never flows into the shipped tracks.
  - Every other rung therefore copies with `model_copy`, and the stamp survives.
- ✅ Named risk 2: does every coverage computation see the clause?
  - Check: grep for coverage computations in structure.py, taper.py and stages/gather.py.
  - `align()` (structure.py:1129) and the LLM fallback `apply_llm_alignment` (structure.py:1257) both go through `_songish_coverage`.
  - The taper's reader coverage is `align(tracks, reader, ...).coverage` (gather.py:1731), on the same stamped tracks.
  - So all three see the clause, with no extra site needed.
  - `cli._sibling_donor_coverage` is a donor-row display figure, not show coverage, so it is out of scope.
- ✅ Single exit: `compute_gather` has one return after the note (gather.py:2054), so no path skips it.
- ⚠️ Cannot verify from diff: that `op_notes` → `GatherResult.notes` → `notes.json` lands on disk. The tests assert `res.notes`, and the write path is unchanged code.

### Strengths
- The change is minimal and exactly in the shape the brief specified: one field, one keyword, one comprehension clause, one note loop, and no speculative extras.
- Mutation check run by monkeypatch from a scratch cwd, checkout untouched: I swapped `_songish_coverage` for the pre-change comprehension. Both `test_unmatched_short_kept_track_does_not_lower_coverage` and the updated windsor test `test_gather_recovers_structure_from_sibling` fail on the coverage assertion. So the coverage assertions really fail without the clause; the RED was not only the missing attribute.
- The dry run touched only the two windsor coverage expectations (27/28 → 1.0), each tied to spec 3 in its comment. That matches the implementer's report.
- The include-pin decision is sound: a short-kept file is never in `ordering["readmitted"]`, so the pin re-admits a rule-dropped `Crowd Noise` and checks it is out of both bases while `Murph` is in.
- The windsor `structure.conflicts` concern raised in the handback is a non-issue. Spec 3 says "`matched` is still measured and shown". Only coverage drops the track.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. test_stage_gather.py `test_short_kept_survives_to_show_json`: `plain` (sub="a") and `owned` (sub="c") run identical inputs (same `md`, no overrides), so both are taper-owned. The docstring's "through align()" leg is not a separate path; it duplicates the taper leg.
   - The non-owned deterministic align path is still covered indirectly by the updated windsor tests: their coverage 1.0 depends on the stamp surviving `align()`.
   - Fix: drop `plain`, or point it at a non-taper fixture (e.g. the windsor gd74 one) so the three legs really are three paths.
   - The test also checks the in-memory `Show` rather than a written/read show.json. Pydantic makes the round-trip trivial, but the name overstates what it checks.
2. gather.py:2029-2032: the note also judges `unresolved` tracks, whose `title` is the filename. Probe: `short_tag_is_junk("tuning.mp3")` is True, while `tb1999-07-04t08.mp3`, `10.tuningup.mp3` and `d1t03.mp3` are False.
   - Spec 2.4's filename-junk arm drops untagged short files with a junk stem, so this is reachable only for a short-kept file whose tag fell through to `unresolved` and whose filename is junk. It would then print a note quoting a filename as its "final title".
   - That is harmless and arguably informative. The implementer could add `t.title_source != "unresolved"` if the operator wants the note limited to titles a rung actually produced. This is optional, and spec 2.5's "from any rung" supports either reading.
3. test_stage_gather.py `test_short_kept_file_votes_like_any_kept_file` does a function-local import from a sibling test module (`from test_title_cascade import _inputs_like_gather`). It works because llama's tests are top-level modules, but it couples two test files. Hoisting the helper into a shared conftest/helper would be cleaner. Cosmetic.

### Assessment

**Task quality:** Approved

**Reasoning:** The implementation is the four-line contract the brief and spec 2.5/3 define. Every coverage path sees the clause through `_songish_coverage`. No rung rebuilds `Track`, so the stamp survives. My mutation check confirms the coverage assertions are load-bearing. The remaining findings are test-shape polish and one optional narrowing of the note.
