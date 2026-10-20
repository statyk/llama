### Spec Compliance

- ✅ Spec compliant (Slice 7 + brief + the orchestrator's amending ruling), verified against the diff:
  - Precondition is exact: `_untitled_counts` (cli.py ~1609-1616) counts `title_source != "unresolved"`; `Track.title_source` is a required `str` (models.py:157), so there is no None/missing case. Refusal `{slug}: --untitled applies only when every track is unresolved ({k} of {n} resolved)` matches the brief verbatim (cli.py ~2795-2799).
  - Combination refusals: the loop at cli.py ~2774-2786 covers all 16 other `fix` options (checked against the full `fix` signature, cli.py:2712-2760: exclude, unexclude, include, set_venue, set_city, set_date, set_title, clear_title, set_breaks, clear_set_breaks, set_encore, clear_encore, suggest_titles, narration, overrule, no_run). The ruling's `--clear-set-breaks`/`--clear-encore`/`--clear-title` are present with the same message. All refusals, the show.json and provenance checks run before `_untitled_resolution`, i.e. before the prompt and any write.
  - One confirmation precedes every write (`_untitled_resolution`, cli.py ~1624-1650): track list printed, `typer.confirm(..., default=False)`, then `_edit_overrides(titles, narration="vague", set_breaks=[])`, redo from gather; on None `_clear_hold` + redo from brief. Re-resolves the entry before each redo, as the brief specifies.
  - Sequencing matches spec steps 2-4: `process_show` (pipeline.py:85-91) runs gather -> research -> vet unconditionally and checks the hold only after vet, so "redo from gather through vet", then clear, then brief -> package is what actually happens.
  - Triage `[u]`: offered only when total > 0 and resolved == 0 (and provenance exists, matching fix's refusal), inserted before `[s]kip` by replacement from `RESOLVE_PROMPT` (cli.py ~1529-1533, ~1680-1688, ~1754-1761).
  - Only Task 21 writes overrides.json, and only after the confirmation: satisfied.
- ⚠️ Cannot verify from diff / accepted gap: the spec acceptance "end state (packaged, not held, narration: vague) on a fixture whose gather AND vet raise flags" is pinned only with `_redo_show` stubbed (test_fix.py `test_untitled_overrules_remaining_flags_then_continues_from_brief` simulates a gather flag; no vet flag is simulated, and no real `process_show` run reaches package). The orchestrator's pre-flight note acknowledges this. I checked the named risk that the brief redo could re-run vet and re-flag forever: `should_run` is artifact-existence only (workspace.py:66-67) and `drop_stage_artifacts("brief")` drops only brief-and-later stages (workspace.py:103-112), the same route `fix --narration vague` has always used, so the risk does not materialise. A real end-to-end test remains the controller's call.

Deviations:
- D1 (refuse `--set-venue/--set-city/--set-date`): ACCEPT. The untitled branch returns before the general edit path, so these would otherwise be silently dropped; refusing is the conservative choice on a strict operator-data surface, and it is in the parametrized test.
- D2 (zero-track refused "(0 of 0 resolved)", `[u]` not offered): ACCEPT. "Every track unresolved" is vacuously true on zero tracks, and the route would clear the hold and package an empty show. Untested (Minor 2).
- D3 (overrides.json byte snapshot to tell decline from still-held): ACCEPT behaviourally. A false "declined" needs a confirmed write that is byte-identical to the existing file, which requires `Untitled (track N)` override titles already applied, so `title_source == "override"`, so the precondition refuses first. In practice it cannot happen. The design is a workaround for the brief's `Path | None` interface (Minor 1).

### Strengths

- The refusal test (test_fix.py `test_untitled_refuses_every_combination`) feeds `input="y\n"` and asserts the prompt text is absent, overrides.json does not exist and no redo ran. That pins "refuses before the prompt and before any write", not just the exit code.
- The mutation follow-up was handled properly: mutant (b) survived the brief's 1-track test, and the implementer added `test_untitled_is_refused_when_only_some_tracks_are_resolved` (1 of 3) plus the triage partial-resolution test.
- `test_untitled_gather_makes_no_align_structure_call` discriminates. I probed real `compute_gather` on gd73 (probe in a scratch dir, output in t21-rev.log): with the same `Untitled` titles but `set_breaks` unset, the `Boom` align provider IS called ("RAISED align_structure called", and `needs_llm == ('align_structure',)` with no provider). With `set_breaks=[]` it is not called and the result is one set. Dropping `set_breaks=[]` therefore fails this test.
- The prompt variant is derived by replacement, not copied, and `test_resolve_prompt_untitled_is_inserted_before_skip` pins that it is a pure insertion.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. cli.py ~1758-1762 and ~2800-2805: the snapshot / compare / echo block is duplicated in triage and fix, and the decline-vs-held disambiguation sits outside the function that knows the answer. Having `_untitled_resolution` return a small status (e.g. `("declined", None)` / `("held", None)` / `("packaged", pkg)`) would remove `_overrides_snapshot` and the duplication. This is a brief-interface deviation, so it is the controller's call.
2. Untested branches:
   - The zero-track refusal (`total == 0`, cli.py ~2795): deleting `total == 0 or` would survive the suite.
   - The fix decline output: `test_untitled_lists_filenames_and_declining_writes_nothing` asserts neither `declined; nothing written` nor exit 0.
   - The triage decline's "back to the prompt": `test_triage_u_declined_writes_nothing_and_returns_to_the_prompt` would also pass if the branch `return`ed instead of `continue`d. Assert the prompt appears twice to pin it.
3. cli.py ~1638-1641: `_edit_overrides` keeps any pre-existing `overrides.encore_after`. If an operator had set `--set-encore` earlier, `set_breaks=[]` plus that encore gives sets {"1","encore"}, not the spec's "every track in one set". It also leaves a set label under vague narration. It is rare, and the ruling refuses `--clear-encore` alongside `--untitled`, so the operator has no one-shot remedy. Consider passing `clear_encore=True`, or refusing when `encore_after` is set. Ruling-level question.
4. Pre-existing pattern, not introduced here: `_edit_overrides` and `_clear_hold` run outside the per-show lock (only `_redo_show` takes `file_lock`). The untitled path inherits the same window as `fix --narration vague` and `--overrule`.

### Assessment

**Task quality:** Approved

**Reasoning:** Every spec, brief and ruling requirement on the strict surface (exact precondition, all refusals before the prompt, no write before the single confirmation) is implemented and pinned by discriminating tests. The three deviations are conservative and sound. The remaining items are untested minor branches, a small duplication from the brief's ambiguous return type, and an encore-override edge case.
