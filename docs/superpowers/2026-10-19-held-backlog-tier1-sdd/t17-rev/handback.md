### Spec Compliance

- ✅ Spec compliant. `structure._ENCORE_MARKER` (structure.py:1179) and `encore_lost` (structure.py:1182-1195) match the brief's Interfaces exactly: an encore item must exist; then True if any encore item's `fuzzy_norm_title` is missing from the tape's `title_components`, or any track title matches the marker. `compute_gather` (gather.py:1461-1466) builds `evidence = {i.set for i in canonical.items}` and discards `"encore"` unless `encore_lost(tracks, canonical, family_aliases)`. `structure_guard` is unchanged, as Step 3 requires. Spec 5a (spec:772-784): the marker is local and `_STRUCTURE_PREFIX` is untouched; the exception covers both arms the spec lists.
- ✅ Ruling B4 is honoured. The new helpers are `_titled_tracks` and `_encore_items` (test_structure.py:2068-2075), and the existing `_tracks(n, dur)` is untouched (it is still used at test_structure.py:218,225).
- ✅ Global constraints: no do-not-retune constant appears in the diff. No new note, flag, conflict or VettingResult entry is added (ruling 6). The task is LLM-free.
- ⚠️ Cannot verify from diff: spec 5a acceptance (spec:810-811). That is the harness's list of cleared shows with canonical set count, minutes and a description excerpt, each checked by hand. It belongs to the harness/Checkpoint, not to this task. The controller should make sure it is produced before 5a ships.

### Strengths

- The change is small and well placed. `family_aliases` is the same alias table `align()` uses (gather.py:1204,1259), so the matching-layer fold stays consistent with alignment. `normalize_song`/`DEFAULT_ALIASES` are not touched.
- There is only one `structure_guard` call site in `llama/src` (checked: grep for `structure_guard` outside structure.py finds only gather.py). So the harness and `reapply`, which go through `compute_gather`, pick up 5a without a second copy of the logic.
- The gather test checks the exact set `{"1","2"}` in the matched case. Its second half makes the sixth file a real tag, so the count-equal `setlist` rung cannot copy the replaced title. That is test data placed where the decision is actually made.
- The unit tests include the spec's three named prototype cases (`E] Willin' >`, `E: Rilly Wut?`, `Crowd Encore Call > ...`) and a negative case with no encore item. The `Crowd Encore Call > B` row is the only one where the marker leg alone decides, which is why mutant (a) is caught by it. That matches the reported mutation table: all three mutants were caught by their predicted tests.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)

1. structure.py:1192-1193: "unmatched" is whole-tape component membership, not placement in the encore position. Suppose an encore item repeats a song also played in a numbered set (a reprise, or a song played twice), and the tape lost the encore. The earlier occurrence still satisfies `have`, so `encore_lost` returns False and the multi-set flag is dropped. This is the brief's definition and probably rare, so it is not a defect against the brief. The harness's hand-check of 5a clears should look out for it.
2. structure.py:1179: the bare `\bencore\b` arm also fires on ordinary filler tracks such as `Encore Break` or `Encore Applause`. On such tapes the old multi-set flag is kept, which is the conservative direction and exactly what the spec asks for ("or the word `encore`"). It is still worth listing in the harness output, since it may hold back some clears the prototype counted.
3. test_structure.py:2078-2088: the `aliases` parameter is not exercised (for example, an encore item `Scarlet` against a family track `Scarlet Begonias`), and neither is the `e\d?` digit form (`E1:`). The membership fold is a straight pass-through to `title_components`/`fuzzy_norm_title`, so the risk is low. One assertion each would pin them.
4. In two of the spec's named rows (`E] Willin' >` and `E: Rilly Wut?`, test_structure.py:2082-2085), the unmatched leg already fires: "E] Willin'" normalizes to a component that is not "willin". So those rows do not exercise the marker arm on its own; only the Crowd row does. This is informational; the mutation result already confirms the Crowd row covers the arm.
5. test_structure.py:2063: a module-level import in the middle of the file (`from llama.structure import encore_lost`). The brief mandated it, and it is harmless.

### Assessment

**Task quality:** Approved

**Reasoning:** The implementation follows the brief's interface line for line. It is confined to one predicate placed beside the guard plus one call-site change, and `structure_guard` and the protected constants are untouched. The tests cover each decision arm, and the three mutants were each caught by their predicted test. The remaining points are definition-level edge cases for the harness's hand-check, not code defects.
