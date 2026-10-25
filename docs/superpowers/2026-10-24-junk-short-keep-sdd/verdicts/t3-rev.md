### Spec Compliance

- ✅ Spec compliant (spec 4.1, the translation part of 4.2, and the Task 3 brief). I read the diff in one pass, 2451 lines. I read cli.py 1470-1495 (`_edit_overrides`' tail, cut off in the hunk) and 1775-1835 (`_metadata_editor`) outside the diff.
  - Model types match the brief: models.py:155-157.
  - `override_keys` matches the brief's interface: `POSITIONAL_KEYS`, `legacy_int`, `classify`, `filename_values`, `rekey_raw`, the frozen `Positions`, `resolve_positions` (override_keys.py:210-343).
  - `title_inputs(..., slug)` resolves once, after the exclusion and before `build(kept)` (gather.py diff 449-451).
  - `compute_gather` passes `slugify(candidate.performance_id)` (diff 594-597). Every positional read is `positions.*`/`forced_titles` (diff 497-575, 613-648).
  - `_validate_structure_override` and `_sets_from_breaks` are unchanged.
  - `_edit_overrides` keeps its signature, refuses before writing, translates through `show.json` with `no track N (show has M tracks)`, and names `llama redo <slug> --from gather` when show.json is missing (cli.py diff 76-122).
  - Every Step 1 test is present, with extras (test_override_keys.py, test_catalog.py:721, test_stage_gather.py diff 1903-1947, test_fix.py diff 1348-1427).
- Fixed strings: legacy, mixed and dangling match global-constraints.md character for character (override_keys.py:286-300). They are pinned by exact `==` asserts in test_resolver_refusals (diff 1591-1609), test_edit_overrides_refuses_a_legacy_file and test_gather_refuses_a_legacy_overrides_file. In the dangling message, `--clear-title <file>` is kept as a literal placeholder (Decision 2). That is a reasonable reading, because the message can name several files.
- Decision 1 (`_legacy_message` returns the mixed text for a mixed file): I agree with the orchestrator's ruling on the merits. A mixed file holds a legacy value, and spec 4.1 says writers refuse "any legacy value". Returning None would let `fix --no-run` write into a file that gather then refuses. Pinned by test_legacy_message (diff 1413-1427).
- Process deviation: there are two commits (08a35fd, 853239a). Global constraints and brief Step 7 ask for one commit per task. Each commit is green on its own (the handback reports the staged-tree run), so this is the orchestrator's call: accept it or squash.
- ⚠️ Cannot verify from this diff:
  - Writers still prompt before refusing a legacy file. `fix --untitled` and `--suggest-titles` ask for confirmation, and only then does `_edit_overrides` refuse. Spec 4.1 says "before any prompt", which is Task 4's `_refuse_legacy`. Task 4 should call `_legacy_message` at entry.
  - There is no staleness check yet. Until Task 4's `_stale` lands, a number is translated through whatever `show.json` holds. After Task 1's rule change that can be the pre-rule list. The branch is unreleased, so this is acceptable only if Task 4 lands before any release.
  - The 4 strict xfails in test_triage.py (diff 2145-2202) are right for Task 5. Two of them fail on the fixture shape, not only on display: `9,17` against a 1-track show.json gives `no track 9`. Task 5 needs a multi-track show.json there, not just a display change.

### Strengths

- `legacy_int` is v2.17.0's own rule (`TypeAdapter(int).validate_json(json.dumps(v))`), not Python's `int()`. The test uses the vendored model as the oracle for both a set_breaks item and a titles key, and also hard-pins the spec 4.1 list, so a pydantic upgrade fails loudly.
- The vendored fixture is verbatim e37f670. I diffed it against `git show e37f670:packages/llama/src/llama/models.py`: identical apart from the rename.
- The resolver orders its checks mixed, then legacy, then dangling, and puts every dangling key in one de-duplicated message (override_keys.py:325-343). It runs before the canonical build, so a refused file costs nothing.
- `[]` versus None presence holds in all three places: the model, `Positions` (test_resolver_maps_filenames_onto_the_kept_list), and `_edit_overrides` (set_breaks=[] is not translated, diff 119 and test diff 1382).
- The slug choice (library slug, not `show_ws.dir.name`) is explained at the call site and pinned by test_gather_refuses_a_legacy_overrides_file, whose workspace dir is `show`.
- The test_cli conversions read titles back through `_titles_by_track`, which asserts that every stored key is a show.json filename. That is stronger than the old number-keyed asserts.
- test_filename_title_follows_its_file_across_an_insertion exercises the real motivating case (windsor D3_T02 inserted at track 17), including the encore keyed by filename landing at 27.

### Named-risk checks run

1. **Every positional reader goes through the resolver or is a writer/display.**
   - I grepped `packages/llama/src` and `scripts` for `overrides.(titles|set_breaks|encore_after)`, `ov.*` and `.overrides`.
   - gather.py has no remaining positional read. Lines 74/79/82/1386 are message text; 1079-1134 and 1886-2029 are include/exclude/venue/city/date.
   - cli.py:1462 is the writer. cli.py:1791-1830 is triage [m] (Task 5). I traced it: an unchanged default writes nothing, and an edit clears the old filename keys "as given" and sets translated numbers, so nothing mis-points. cli.py:2110-2115 and 2183-2185 are displays.
   - replay.py:506-508 only validates the model.
   - scripts/taper_probe.py:403 tests presence only (works for either form). scripts/taper_probe.py:717 compares stripped `set_breaks` with taper ints; that is harness rows, Task 6, as the handback says.
   - `.overrides.json` has one writer, cli.py:1491; the replay and harness copies are not writers.
2. **The library slug reaches replay and reapply.** `compute_gather` is called only from replay.py:327 and gather.py:2095, and reapply goes through replay. The slug is `slugify(candidate.performance_id)`, the same as `RunWorkspace.show_ws` (workspace.py:128-129).
3. **`legacy_int` matches v2.17's lax JSON int for a titles key.** I probed it in the worktree venv (`llama.__file__` inside the worktree), from the scratchpad. Raw-file `classify` and `model_dump` `classify` agree on all of these: `true`/`false` (bool becomes 1/0, legacy), `"7"` (kept as str, legacy), the key `"true"` (filename), `"1e1"`, `"0x10"`, `"٣"` (filename), `"-0"` (legacy, 0). So `_legacy_message` (raw file) and the resolver (model) cannot disagree on those inputs.
4. **`rekey_raw`.** It deep-copies, keeps top-level and titles key order, keeps unknown keys, never maps a filename value, and keeps `null`/`[]` as they are (override_keys.py:262-283; tests at diff 1543-1575).
5. **Protected names.** I grepped the diff for every "Untouched, byte-identical" name and every piece-3 constant. The only hit is the probe's unchanged `FORMAT_BY_AUDIO[cfg.audio_format]` argument line (diff 2439-2440). `git diff --stat` over junk/structure/titles/package/catalog is empty.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
- **override_keys.py:333-335: a duplicate filename in the kept list maps to its first position without a word.** On this strict surface an ambiguous mapping should refuse. The case is unreachable today, because archive paths are unique and `_dedupe_duplicate_listings` keys on basename plus duration. A one-line `LlamaError` when `len(index) != len(kept_names)` would make that assumption explicit instead of silent.
- **override_keys.py:278: `rekey_raw` collapses colliding title keys.** `{"7": "A", "07": "B"}` collapses to one filename key, the last one winning. That matches how v2.17 itself read such a file (as `{7: "B"}`), so nothing is mis-pointed relative to what the operator saw. Still, the migration (a later task) should detect the collision and refuse or report it, not inherit it silently. A legacy plus filename collision is a mixed file, which the migration must refuse before calling this.
- **gather.py diff 569-572: the cascade's `overrides.titles: no track k` check is unreachable from gather.** The resolver dangles first (Decision 4). After the conversion, test_cascade_out_of_range_override_raises_like_gather (test_title_cascade.py diff 2031-2041) compares two errors that both come from `title_inputs`, so it no longer exercises the cascade's own check. Either drop the check or test it on a hand-built `TitleInputs`.
- **override_keys.py:315-322: `Positions` is `frozen=True` but holds a dict and a list, so it is only shallowly immutable.** No caller mutates it. Cosmetic.
- **Two commits instead of one** (see Spec Compliance).

### Assessment

**Task quality:** Approved

**Reasoning:** The resolver, the legacy test, the model types and the writer translation follow spec 4.1 and 4.2 exactly. The fixed strings are pinned verbatim and the presence semantics survive end to end. The only gaps are explicitly Task 4's and Task 5's: the up-front `_refuse_legacy` before any prompt, the staleness check, `--clear-title <filename>` at the CLI, and triage display. Nothing in this diff would make those tasks wrong.
