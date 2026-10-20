# t1-impl handback: Task 1 (compute_gather / GatherResult / needs_llm / notes.json)

Status: DONE
Commit: dd0bf7c feat(gather): compute_gather with a needs-LLM verdict and notes.json

## Implemented
- models.ShowNotes(BaseModel): gather/vet list[str], default empty (plain BaseModel: persisted artifact, permissive like show.json).
- ShowWorkspace.notes = dir/"notes.json"; show_stage_artifacts(ws,"gather") == [show, reviews, notes].
- gather.CanonicalBuild gains trailing `needs_llm: bool = False`; build_canonical sets it when best is None, the longest description is non-blank, and provider is None (branch restructured so the provider path is unchanged).
- gather.GatherResult(NamedTuple): show, reviews, notes, needs_llm (tuple, "extract_setlist" then "align_structure", each at most once).
- gather.compute_gather(show_ws, ia, provider, candidate, identifier, *, audio_format, align_provider, setlistfm, structure_cfg, jerrybase_enabled): former run_gather body minus should_run and writes; reads only overrides.json from show_ws. `op_notes` is a new list (empty for now), separate from the local `notes` that still flows into structure.conflicts. align_structure recorded in an `else:` on `if align_provider is not None:` inside the weak-alignment branch; the low-confidence flag is still appended exactly as before.
- run_gather: same signature/return; should_run, compute_gather, then writes notes.json (ShowNotes(gather=res.notes, vet=[])), show.json, reviews.json.
- cli: `_read_show_notes(sws)` helper; `_print_show_entry` prints `notes:` + `  - line` for gather+vet after the needs-review block, before --tracks, only when non-empty; `_print_show_json` adds `"notes": {"gather": [...], "vet": [...]}` (empty lists when absent).
- M6: the three 3-tuple unpacks in test_stage_gather.py (~2020, ~2072, ~2112) switched to attribute access (~2121 was a call inside pytest.raises, not an unpack). No other tuple unpack exists in src/tests/scripts (cli.py's _propose_titles_for_show already uses `.setlist`; test_cli.py spies pass the result through).

## TDD evidence
RED: `./.venv/bin/python -m pytest packages/llama/tests/test_stage_gather.py packages/llama/tests/test_workspace.py packages/llama/tests/test_show_cmd.py -q`
  -> collection error `ImportError: cannot import name 'ShowNotes' from 'llama.models'` (test_stage_gather.py)
  workspace+show_cmd alone -> `AttributeError: 'ShowWorkspace' object has no attribute 'notes'` x2; `2 failed, 43 passed`
  (test_show_without_notes_json_prints_no_notes_heading passes pre-implementation, as it must: it is a negative pin.)
Intermediate after gather/workspace: `1 failed, 150 passed` (test_show_prints_notes_json_under_a_notes_heading: no "notes:").
GREEN (same command): `152 passed in 3.45s` (includes the extra JSON test below).
Full suite: `./.venv/bin/python -m pytest -q` -> `3163 passed, 1 skipped, 8 deselected, 26 warnings in 52.15s` (baseline 3153 + 10: gather 6, show_cmd 3, workspace 1).
`llama.__file__` resolves inside the worktree (checked).

## Deviations from the brief (with reasons)
1. B1 ruling applied: extract_setlist test description is "An amazing night of music, seeded with love." (comment in the test cites the ruling).
2. Write order: run_gather writes notes.json FIRST, then show.json, then reviews.json (brief listed show, reviews, notes). Reason: show.json is should_run's done-marker; writing notes after it means a crash between the two leaves a fresh show.json beside a stale (or missing) notes.json that no rerun would replace. Notes-first means a crash leaves gather to re-run. Not observable otherwise. Reorder trivially if the orchestrator disagrees.
3. Added one test not in the brief: test_show_cmd.py::test_json_carries_notes_and_empty_lists_without_notes_json — the brief requires the `--json` "notes" key but gave no test for it. (show_cmd count therefore rises by 3, not 2.) Written after the impl, so no RED observed for it; it depends directly on the new key.

## Self-review
- Do-not-retune constants: untouched (diff touches none of the Global Constraints list).
- Behaviour with providers: extract_setlist branch identical (only the `max(descriptions)` now also computes when provider is None — pure); align branch identical (new else only when align_provider is None). The 3153 pre-existing tests pass unchanged except the M6 unpack edits.
- compute_gather has no write_artifact call and touches show_ws only via read_overrides.
- `op_notes` is always [] in this task, by design (later tasks append).
- `llama show` reads notes.json strictly (read_model); a malformed notes.json would raise, consistent with how show.json is read. Not hardened; flag if triage needs leniency.
- The text path prints no notes for a pre-show.json show (notes.json is only written alongside show.json); JSON always carries the key.

## Concerns
None blocking. Deviation 2 (write order) is the only judgment call.
