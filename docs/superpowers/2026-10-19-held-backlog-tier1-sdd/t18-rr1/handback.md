### Finding Verdicts

- **[Important] gather.py ~1278-1279: the 5c.2 note's routing to notes.json is untested; mutant `op_notes.append(numbered_note)` -> `notes.append(numbered_note)` would survive** — ADDRESSED. `packages/llama/tests/test_stage_gather.py:3018-3042` (`test_5c2_note_goes_to_notes_json_never_to_structure_conflicts`) wraps the real `align` (gather imports it by name, `gather.py:20`, so `monkeypatch.setattr(gather_mod, "align", ...)` takes effect) and relabels `encore` -> `2`, so the trailing track is NOT in `encore`. It asserts `alignment == "jerrybase"`, the exact labels `["1","1","1","2","2","2"]`, and the exact Contracts 5c.2 string (brief line 62) `in res.notes` and `not in res.show.structure.conflicts`. Trace of the named mutant: `res.notes` is `op_notes` (`gather.py:1544`) and the local `notes` reach `structure.conflicts` via `gather.py:1500` (`_dedupe_ordered(conflicts + notes)`, the non-override branch this test takes), so the mutant fails both assertions. Implementer's mutation record (prediction logged, shadowing proven via `llama.__file__`, private pycache prefix) shows it CAUGHT by exactly this test ("1 failed, 201 passed"); consistent with the trace.
- Check run: `./.venv/bin/python -m pytest packages/llama/tests/test_stage_gather.py::test_5c2_note_goes_to_notes_json_never_to_structure_conflicts -q` -> 1 passed (worktree venv resolves `llama` inside the worktree). Fix report names the covering tests with output (gather+jerrybase 202 passed; full suite 3692 passed, 1 skipped).

### New Breakage in the Fix Diff

None. Diff is test-only (+26 lines, one new test); no source changed. The `align` wrapper's relabeling would also apply to any other `align` call in that `compute_gather` run, but the test pins the resulting labels and note exactly, so it cannot pass vacuously.

### Out-of-Scope Observations

None.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.
