# t4-impl handback: Task 4 (compute_legs, briefing_reusable, classification)

Status: DONE_WITH_CONCERNS (concerns are notes for later tasks; nothing blocking)

Commits (branch held-backlog-tier1):
- 0b3ece1 feat(replay): compute_legs, briefing reuse rule and outcome classification
- 30461a1 test(replay): pin the brief leg to the vetted show; refuse an overlapping scratch

## What was implemented (packages/llama/src/llama/replay.py)
- `flag_family(flag)`: the Contracts table as an ordered (family, predicate) list; first match wins; `other` otherwise.
- `shipped_diff(stored, new)`: keys title_changes, venue, city, set_changes, segue_changes, set_breaks, alignment, date. `[]`/`None` when equal. title_changes rows fire on a title OR title_source change.
- `briefing_reusable(stored_show, new_show, briefing, narration)`: first failing reason among `broadcast fields changed: <titles, sets, segues, set_breaks, date, venue, city>` (in that order, only those that changed), `narration differs: briefing <x>, overrides <y>`, `briefing guard: <p1>; <p2>`. title_source is not a broadcast field.
- `Legs` dataclass (fields per the brief) plus a `replayed_show` property (`vet.show` when vet ran, else `gather.show`).
- `compute_legs(ws, *, config, ia, slfm, scratch)`: recreates scratch empty, copies overrides.json only, LlamaError on missing provenance.json/show.json, `compute_gather(... provider None, align_provider None ...)`, needs_llm = gather verdicts + "stored alignment llm" + "no vetting.json"; apply_vet over the stored extraction against the replayed show; carried = stored `package`-family flags; brief leg only when gather + vet + CARRIED flags are empty (explicit in code comment); reuse/fresh/none per the brief; `flags = gather + vet + carried + brief_flags`. CacheMiss propagates.
- `classify(legs, stored_state)`: needs-LLM first with NO exception (ruling); held: still-held-package, still-held, then would_be (`clears` on reuse, `needs-brief` otherwise), `("structure-changed", would_be)` when set/segue labels, set_breaks or alignment differ; non-held: newly-held, clean-changed (any shipped field), clean. Diffs `legs.stored` against `legs.replayed_show` (ruling M7).
- `ShowReplay` dataclass with the Contracts' keys plus `date` after `city` (ruling M7), `to_dict()` = `dataclasses.asdict`. All fields but slug/state have defaults.
- Scratch safety guard (self-review addition): a scratch that is, contains or lies inside `ws.dir` raises LlamaError before the rmtree.

Gather test (carried Minor from Task 1's review): `test_stage_gather.py::test_compute_gather_extract_with_a_provider_is_not_needs_llm` — FakeProvider returns a valid ParsedSetlist for "An amazing night of music, seeded with love."; asserts the provider was called and "extract_setlist" not in needs_llm. Mutant (i) below confirms it goes red when `needs_llm = True` moves above the provider check.

## Orchestrator rulings applied
- M7: `date` in ShowReplay and shipped_diff; classify/shipped_diff compare against the VETTED show. Brief's structure test now diffs against `legs.vet.show`. New tests: `test_shipped_diff_compares_against_the_vetted_show` (stored show carries a vet-adopted date; vs vetted -> clean; vs gather -> date diff) and `test_briefing_reuse_compares_against_the_vetted_show`.
- No vetting.json is needs-LLM always: `test_missing_vetting_json_is_needs_llm` (brief's test renamed; old name said "only when gather clears") and `test_missing_vetting_json_is_needs_llm_even_when_gather_flags_remain` (replay with jerrybase ON gives a deterministic gather flag `structure has 2 sets but jerrybase shows 3`, gather.needs_llm == (), outcome needs-llm for held and packaged).
- Brief-leg gate counts carried package flags: code comment + `test_carried_package_flag_is_still_held_package` (now with a stored reusable briefing, so the gate is what makes brief == "none").
- Review Focus 3: `test_reuse_refused_when_recorded_narration_differs` (unit) plus `test_legacy_briefing_on_a_vague_show_is_needs_brief` (end to end: raw legacy briefing.json, overrides vague -> brief "fresh", reason `narration differs: briefing full, overrides vague`, classify needs-brief).

## TDD evidence
- RED: `./.venv/bin/python -m pytest packages/llama/tests/test_replay.py -q` -> `ImportError: cannot import name 'Legs' from 'llama.replay'` (1 error during collection).
- First GREEN run: 51 passed, 1 failed (my "gather flags + no vetting" test used exclude-all overrides, which also reached align_structure); switched to jerrybase-on replay -> 52 passed.
- Final: test_replay.py 56 passed.
- `llama.__file__` resolves inside the worktree (checked).

## Full suite
`./.venv/bin/python -m pytest -q` -> 3225 passed, 1 skipped, 8 deselected (baseline 3174; +51 tests). Teed into t4-impl.log.

## Mutation table (recipe: fresh rsync copy under $TMPDIR per mutant, PYTHONPATH shadow proven per mutant — every SHADOW line printed a path under $M/tree — private PYTHONPYCACHEPREFIX, worktree interpreter `-m pytest`, files test_replay.py + test_stage_gather.py; predictions written into the mutant table file before the run)
| mutant | predicted | caught by |
|---|---|---|
| (a) classify checks flags before needs-LLM | test_classify_needs_llm_wins_over_every_flag | test_classify_needs_llm_wins_over_every_flag (+ test_missing_vetting_json_is_needs_llm_even_when_gather_flags_remain) |
| (b) classify re-adds the overruled "no vetting.json alone with gather flags" exception (inverted per ruling) | test_missing_vetting_json_is_needs_llm_even_when_gather_flags_remain | that test (+ test_classify_needs_llm_wins_over_every_flag) |
| (c) compute_legs omits "stored alignment llm" | test_stored_llm_alignment_is_needs_llm | test_stored_llm_alignment_is_needs_llm |
| (d) briefing_reusable skips the narration comparison | test_briefing_reusable_reasons | test_briefing_reusable_reasons (+ test_reuse_refused_when_recorded_narration_differs, test_legacy_briefing_on_a_vague_show_is_needs_brief) |
| (e) needs-LLM short-circuit removed | test_stored_llm_alignment_is_needs_llm | that test (+3 others) |
| (f) brief-leg gate ignores carried flags | test_carried_package_flag_is_still_held_package | test_carried_package_flag_is_still_held_package |
| (g) flag_family `package` prefix "duration mismatch on " -> "... at " | test_flag_family[duration mismatch ...-package] | that param (+ test_carried_package_flag_is_still_held_package) |
| (h) classify diffs against gather.show, not the vetted show | test_shipped_diff_compares_against_the_vetted_show | that test |
| (i) gather: `needs_llm = True` above `if provider is not None` | test_stage_gather::test_compute_gather_extract_with_a_provider_is_not_needs_llm | that test |
| (j) structure-changed check drops alignment | test_alignment_change_on_a_would_clear_show_is_structure_changed | that test |
| (k) count-change rows over stored indices only | test_shipped_diff_track_count_change_reports_every_index_with_new_none | that test |
| (l) briefing_reusable fed gathered show, not vetted | none predicted on first run | SURVIVED -> added test_briefing_reuse_compares_against_the_vetted_show; rerun: caught by it |
| (m) scratch-overlap guard removed | test_compute_legs_refuses_a_scratch_overlapping_the_show_dir[show] | all three params |

## Files changed
- packages/llama/src/llama/replay.py
- packages/llama/tests/test_replay.py
- packages/llama/tests/test_stage_gather.py

## Deviations / decisions (with reasons)
1. `ShowReplay` is defined here (Task 5's plan text also says it "produces" it). The orchestrator's task title and M7 named it in Task 4. Task 5 should reuse it and add only `replay_show`, not redefine it.
2. shipped_diff on a track-count change: rows for every index up to the LONGER show (not just the stored show's indices), `new`/`new_source` None, `old` None past the stored end. Reason: with stored indices only, a stored show with 0 tracks ("no playable tracks") replaying to N tracks would report no change (mutant k). I also report every index in set_changes and segue_changes on a count change (brief specified only title_changes), so a count change on a would-clear held show is `structure-changed` (hand-checked) and not a silent `clears`. Conservative direction; flag if you want it narrower.
3. `Legs.briefing` holds the stored briefing only when brief == "reuse" (None on fresh/none), so Task 19 cannot ship a briefing that was rejected.
4. The brief leg is gated on flags only (as the brief says), so it can run on a needs-LLM show with no flags; harmless, since classify decides needs-LLM first.
5. `Legs.replayed_show` property added (Task 19's `final_show` line can use it).
6. Scratch-overlap guard in compute_legs (not in the brief): rmtree on a mis-passed scratch would delete library data, a strict surface.

## Concerns (for later tasks)
- Plan Task 19 step 5 says "`legs.vet` is None only on a `no vetting.json` show that `classify` called still-held". Under the no-exception ruling, such a show is always needs-llm and stops at step 3, so that clause is stale: in Task 19 `legs.vet` is never None past classify.
- `read_overrides` on an unreadable overrides.json raises a pydantic ValidationError from inside compute_gather (scratch copy) — Task 5 must map it to `unreplayable: overrides.json unreadable` (not a CacheMiss/LlamaError).

## Self-review
- Protected constants: grep of the diff since 383e01a finds none.
- compute_legs reads ws.dir only; asserted byte-identical before/after; scratch holds overrides.json only (tested with a stale file present).
- No new flags, notes or StructureInfo.conflicts writes.
