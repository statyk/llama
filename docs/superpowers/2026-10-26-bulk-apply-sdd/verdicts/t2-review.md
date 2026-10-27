# Task 2 review (t2-review): Overrules take effect and are recorded

Reviewer model: Opus. Range 11a22de3..16cf2b3d (one commit, 15 files, +488/-25).

### Spec Compliance

- ✅ Spec compliant. Every brief item is in the diff:
  - `compute_gather` splits last: gather.py:2236-2243 `_apply_overrules`, called after `show` is built. It extends `op_notes`, which is the list returned as `GatherResult.notes`, so the notes reach notes.json `gather`.
  - `apply_vet(..., *, overrules=())` splits only vet's own flags (vet_research.py:321). `kept` (vet_research.py:328) is untouched. `run_vet_research` passes `read_overrides(show_ws).overrules`.
  - `run_brief` splits `problems` (brief.py:359) before both flag writes. It writes `ShowNotes.brief` read-modify-write (brief.py:325, :368). The line `flags = [... not startswith(FLAG_PREFIX)] + problems` therefore drops an overruled briefing flag a previous run had added.
  - reapply's fresh brief splits (reapply.py:141). The written `ShowNotes` carries `brief=brief_notes`.
  - `compute_legs` passes overrules to vet. Gather sees them through the scratch copy of overrides.json (replay.py `shutil.copyfile(ws.overrides, ...)`, checked).
  - `ShowNotes.brief: list[str] = []` is defaulted and permissive (models.py).
  - `_clear_hold(show_ws, *, record=None)` (cli.py:1665): `records_for(..., at=UTC isoformat)` → `_edit_overrides(add_overrules=...)`, then the flags are cleared. Callers: fix `--overrule` → "fix", triage `[o]` → "triage", `_untitled_resolution` → "untitled" (covers `fix --untitled` and triage `[u]`). Both narration-vague callers pass nothing.
  - `_edit_overrides` stores `merge_rules(ov.overrules, add_overrules)`, so every other edit preserves the rules.
- All 10 brief-named tests are present, plus 9 more: the fix and triage pins, a no-write case for a package-only flag, a double-overrule idempotence case, and inert-on-another-identifier cases in gather, vet and brief.
- Spec "Matching" (identifier-scoped; titles by subset; kind-only when no subject) is Task 1's `rule_matches`. Task 2 calls it consistently with `show.identifier` in all five sites. Gather tests cover the subset rule both ways (wider ⊇ covers; one more unresolved file holds).
- Dry run reported: one changed expectation, `test_show_cmd.py::test_json_carries_notes_and_empty_lists_without_notes_json` (`"brief": []`). It is explained by Global Constraints "New persisted fields … `ShowNotes.brief`". That is consistent with the diff, which changes no other existing assertion.
- ⚠️ Cannot verify from diff: the commit trailer reads `Co-Authored-By: Claude Opus 5.5 (1M context)` and has no `Claude-Session:` line. The controller should check this against the trailer it specified to the implementer (Global Constraints: "the attribution trailer the orchestrating session specifies").

### Named-risk checks run
- Flags raised outside gather/vet/brief would re-hold despite a record. Grepped every `review_flags` writer in `src/llama`. The only others are package.py:151 (package family, not overrulable by contract) and reapply.py:197 (writes the already-split `flags`). The select-stage-looking flags (`tape spans`, `unassigned multi-event`, `multi-event date`) are raised in gather.py:2010, so the gather split covers them.
- Replay's brief leg could resurrect an overruled briefing flag. Checked: `compute_legs` sets `brief_flags = briefing_guard(...)` only on `reuse`, which `briefing_reusable` grants only when the guard passes ("[] by construction"). No unsplit path.
- `test_overrule_survives_a_regather` might pass on a stale manifest. Checked: `show_stage_artifacts["package"]` is `manifest.json`, so `redo --from gather` deletes it, and the final `manifest.json exists` assertion is meaningful.
- `_edit_overrides` side effects when called with only `add_overrules`. Read the body (cli.py:1483-1567). With no positional args `to_file` is never called, and lists, narration, titles, set_breaks and encore_after are copied unchanged. The `_legacy_message` refusal now applies to overrule recording. That is acceptable post-migration, and the implementer disclosed it.
- Lock and rollback: `_clear_hold`'s overrides write is inside the existing `show_unit`, whose `.txn` covers overrides.json.
- Untouched names: grepped only the +/- lines of the review package for `briefing_reusable`, `DURATION_TOLERANCE_S`, `STOP_AFTER_LLM_FAILURES`, `load_list`, `purge_package_audio`, the junk constants and functions, `plan_reuse`, the piece-3 constants, `class Manifest` and `awaiting_fix`. No hits.
- Targeted run, the 8 touched test files: `./.venv/bin/python -m pytest <8 files> -q -p no:cacheprovider` gave 1066 passed. `llama.__file__` resolves inside the worktree.

### Strengths
- There is one split site per stage, each a single named call. Gather's is the last statement before `GatherResult`, with a comment saying to keep it last. That is what Tasks 9 and 10 need.
- `_write_brief_notes` replaces a stale `brief` list, and `test_a_clean_brief_replaces_stale_brief_notes` pins it. It writes before briefing.json, the done-marker, so a crash leaves the stage re-runnable.
- The tests exercise real behaviour. `test_overrule_survives_a_regather` drives the real pipeline (redo → held → fix --overrule → redo → packaged). `test_replay_sees_overrules` builds its rules with `records_for` from the replay's own flags, so the record/match round trip is tested end to end.
- The implementer reports a 9-mutant check with a predicted catching test per mutant.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. brief.py:359 (split after `generate_briefing`). An overruled guard problem still triggers `generate_briefing`'s feedback retry, a second brief LLM call, before the split discards it. The brief puts the split after generation, so this complies. But on a show held for a recurring overruled `briefing …` flag, every fresh brief costs 2 calls instead of 1. It also tells the LLM to "fix" something the operator ruled acceptable. This matters for spec Goal 1 ("lowest LLM spend") only to the extent that briefing-family overrules are common in the backlog. Fix if wanted: pass the rules into `generate_briefing` and split inside its loop. This is the implementer's concern 1; relay to the human.
2. vet_research.py:321 / test_stage_vet.py `test_vet_overrule`. No test pins "split its own flags only". A mutant that also splits `kept` (other stages' flags) passes every test. The brief's show has a kept flag (`low-confidence setlist`) but no rule for it. In the pipeline the effect would be duplicate `overruled:` notes in `vet` for gather flags already noted. Adding a matching `low-confidence-setlist` rule to `test_vet_overrule` and asserting the flag is still in `out.show.review_flags` would pin it.
3. vet_research.py:3 imports `Sequence` from `typing`; cli.py uses `collections.abc`. gather.py:2236 `_apply_overrules(show, rules, op_notes)` leaves `rules` unannotated. Both are cosmetic.
4. cli.py:2266-2268 (`llama show` prints `notes.brief`) is outside the brief's file list for cli.py. It is small, tested (`test_show_prints_brief_notes`), and needed for the spec's "becomes an operator note" to be visible to the operator, so it is not scope creep worth reverting. It is listed only because it is Extra.

### Assessment

**Spec:** ✅ compliant (one ⚠️: the commit trailer; the controller should check it).

**Task quality:** Approved.

**Reasoning:** The wiring is minimal and placed where the brief and spec say. Each stage splits only its own flags. Recording goes through the one `_edit_overrides` path inside the existing transactional unit, and the tests cover record, match, inertness and survival through a real re-gather. The remaining items are a spend inefficiency the brief's ordering implies and one unpinned edge.
