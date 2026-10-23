### Spec Compliance
- ✅ Spec compliant. I read the diff in four passes (lines 1-400, 400-760, 760-1100 and 1100-1532). Then I made one focused check for each named risk:
  - **Orchestrator ruling (1).** Both donor callables return None without raising when the target tracks have no durations. `title_inputs.donor_check` and `sibling_step` (gather.py, `title_inputs` closures) are pinned by `test_donor_closures_return_none_without_durations` (test_title_cascade.py), which also covers `donor_check([])`.
  - **Orchestrator ruling (2).** C writes nothing at an `overrides.titles` position. `_without_override_positions` undoes the change, drops it from `changed` and drops its note. The note-prefix match `lossless title: track {i+1} '` ends with a quote, so track 2 cannot collide with track 23. It is pinned in `test_overrides_survive_every_new_rung_and_anchor_check_3` (`lossless.changed == {}`, no `lossless title: track 2` note).
  - **Orchestrator ruling (3).** I ran an AST source-segment comparison against both `main` and the base `7cacd9d`. These are identical: `compute_gather`, `run_gather`, `best_donor`, `build_canonical`, `_recover_format_titles`, `GatherResult`, `_RECOVER_BELOW`/`_RECOVER_SIBLING_ABOVE`, `_strip_head_banner`, `_strip_footnote_markers` and `show_metadata_norms`. All titles.py protected names (`is_real_title`, `_TRACK_NUM_PREFIX`/`_GLUED_`/`_JOINED_`, `_ENUMERATED_MIN_*`) are identical too. So are the structure.py protected names (`_STRUCTURE_PREFIX`, `fuzzy_norm_title`, `fuzzy_title_eq`, `loosely_same_title`, `LOOSE_TITLE_RATIO`, `_FILLER`, `is_filler`) and siblings `AUTO`/`FLOOR`/`MIN_ANCHORS`/`INDEPENDENT_TITLE_SOURCES`. `hygienic_title` differs from `main` only by Task 4's `require_real` and is identical to the base. `git diff main -- setlist.py` is empty. placeholders/siblings/songs/junk are unchanged from the base. Test-file hunks are append-only, so no existing test was edited.
  - **Named risk: cascade step order.** `title_cascade` (gather.py, diff lines ~430-560) runs: tag_layer → C (in_scope = `format_titles is None and title_fraction(clean_tag_titles(recovery_basis)) >= _RECOVER_BELOW`, the same quantity as `_recover_format_titles`' first gate) → 2b on delivered minus C-changed, with notes minus overrides → 2c/2d notes skipping C-changed → `fetch_siblings` → format-sibling note gated on `not c_changed` → `wholly_untagged` → `s_positions` → `plan_setlist_rung` → `resolve_titles(layer, setlist_fills)` → overrides loop (same `LlamaError` text, pinned by `test_cascade_out_of_range_override_raises_like_gather`) → `sibling_step` → `adopt_gap_titles(declined=plan.declined)` → 2a(`tag_sources`) → slice 4 → D (`kept_donor` when sibling ran, else `donor_check(pre_d)`) → `apply_deferred_setlist`. This matches the brief's "Order inside `title_cascade`".
  - **Named risk: `title_inputs` vs `compute_gather`'s prelude** (current gather.py:1445-1560). Every step is present and in the same order: `filter_files(readmit=…)`, the include warning, `readmitted`/`recovery_basis`, `_recover_format_titles(files, recovery_basis, ordering)`, the exclusion block with both warnings and the `excluded +=`, then `build(kept)` called once on post-exclusion `kept`, then `show_metadata_norms`, `tag_gate_basis`, `frozenset(cb.corroboration)`, `meta.get("title")` and `family_aliases`. The jerrybase event block is caller-side (`events` parameter), as the brief's signature intends. The title block that follows maps to the cascade line for line.
  - **Named risk: per-track-source consumers (spec slice 3).** Each is covered:
    - `resolve_titles` stamping via `layer.sources`.
    - `accept_short_tags` via `tag_sources=sources`.
    - The 2b demotion inside `resolve_titles` is from the delivered layer minus C-changed (`layer_demoted`).
    - The 2c/2d notes skip `c_changed`.
    - The format-sibling note is suppressed when C acted.
    - The 2b notes, the 2a/slice-4 `demoted` and `fetch_siblings`' `or demoted` arm all use the C-filtered set.
  - **Named risk: `"desc-position"` in `TAUTOLOGICAL_TITLE_SOURCES`** (structure.py:1154). I grepped the consumers named in spec slice 2 "Tautology". `_songish_coverage` (used by `align` at structure.py:1129 and `apply_llm_alignment` at :1253), gather's final assembly at gather.py:1841, `taper` at :645 and `vet_research` at :198 all read the constant. No literal source set bypasses it.
  - **Named risk: whether the no-slices equality test is genuine.** It is. `_today` runs the real `compute_gather` and captures its post-2a tracks and notes by wrapping `accept_short_tags` and `_sibling_transfer`. It also asserts `res.notes[:len(notes)] == notes`. The cascade's input comes from `title_inputs` itself (`_inputs_like_gather` only supplies arguments, with `events=[]`, which matches `compute_gather`'s default `jerrybase_enabled=False`). The comparison is a full `model_dump` over 12 fixtures × {as-is, title+exclude overrides}, and `test_cascade_cases_are_not_vacuous` proves every rung and every note class fires.
  - **`gather_cleaner`'s prefix claim.** `_strip_head_banner` returns `items[last+1:][pos:]` and `drop_leading_artist_items` returns `items[n:]`, both suffixes. So `frozenset(range(removed))` is exact.
- ⚠️ Cannot verify from the diff:
  - Library-wide parity of the two preludes (gate 0 is Task 13's).
  - The full-suite figure (4678 passed, 1 skipped, 8 deselected, 26 warnings). The 26 warnings predate this task: t10's log shows the same 26.

### Strengths
- The seams are minimal and default-preserving.
  - `resolve_titles`' `layer`/`setlist_fills` branch only replaces the computation it names (titles.py diff ~L497-L517).
  - `adopt_gap_titles`' `declined` is a two-line skip (structure.py:~1437).
  - `_sibling_transfer` is a thin wrapper whose split is pinned against literals captured from the pre-split code (`test_sibling_transfer_split_is_identical`).
- The cascade cannot drift from what it claims to reproduce. The equality test compares against `compute_gather` itself, and a non-vacuity test backs it.
- `test_s_declines_are_what_stop_setlist_gap` is a proper control. On the exact tracks setlist-gap saw, removing `declined` fills 3, 5 and 6, so `gap_filled == ()` is not passing vacuously.
- D's donor reuse is pinned by a call counter, with both a passing donor and a rotated donor (`test_d_reuses_the_sibling_donor`).

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **Plan-mandated, transitional: verbatim duplication of logic blocks.** gather.py `title_inputs` (the whole prelude, including the exclusion block and its warnings) and `title_cascade` (the 2c/2d note loop, the format-sibling note loop and the overrides loop) are line-for-line copies of `compute_gather`'s blocks (current gather.py:1445-1475 and 1590-1640).
   - Why it matters: until they are removed, a fix to one copy silently diverges from the other.
   - Why it is not fixable here: the plan forbids editing `compute_gather` before Task 16.
   - Action: Task 16 must delete `compute_gather`'s copies rather than keep both, and its reviewer should check that.

#### Minor (Nice to Have)
1. **C1 decisions can still be driven by an override position.** gather.py `_without_override_positions` filters override positions only after `apply_lossless` has decided. Two effects:
   - A show-level `C1 unconfirmed` decline whose triggering target is an override position still declines C for the whole show, and its note may name that overridden track.
   - `c1_verdicts` still lists override positions, although the `CascadeRecord` docstring says the record has "any overrides.titles position filtered out".

   This is conservative (it can only decline more) and was disclosed as judgement call 1. Fix: either pass the override positions into `apply_lossless` so they are never targets, or narrow the docstring to `changed`/`notes`/`titles`/`sources`.
2. **2b demotions for `wholly_untagged`/`tag_real` include override positions (`layer_demoted`), while the brief says "minus C-changed and override positions".** The effect: a `tmp` tag at an override position does not count as a real tag toward wholly-untagged.
   - This reading is more faithful to the spec's "Real tag" definition, and it is needed for `resolve_titles`' equality.
   - It departs from the brief's literal wording without a pin of the wholly-untagged consequence.
   - Fix: add a one-line test, or record it as a plan reading for Checkpoint A.
3. **`test_accept_short_tags_default_sources_unchanged`** (test_stage_gather.py, new) uses synthetic tracks, while the brief asks for "the short-tag fixtures". Its default-vs-`None` comparison is the same code path, so the literals carry the pin. The tnd fixture is covered indirectly by the cascade equality test (with `tag_sources=` passed). Low risk.
4. **The equality harness reads `op_notes` out of `compute_gather`'s frame** (test_title_cascade.py `_today`, `sys._getframe(1).f_locals["op_notes"]`). It breaks silently, with a KeyError, if the local is renamed. That is acceptable for a harness Task 16 retires, but worth a comment naming that dependency.
5. **Commit hygiene.**
   - 5d0b6c3's subject says "step 1 of 3", but the task landed in 2 commits.
   - The plan asks for one commit per task.
   - dd3a513's body says "eleven fixtures"; there are 12.

   All cosmetic.

### Assessment
**Task quality:** Approved
**Reasoning:** Every seam defaults to today's behaviour, and all three orchestrator rulings hold. `compute_gather` and every protected name are byte-identical. The cascade order and the per-track-source consumers match the brief and the spec, and the no-slices equality genuinely runs against `compute_gather`. The one Important item is plan-mandated, transitional duplication that Task 16 must remove, so nothing in Task 11 itself needs fixing.
