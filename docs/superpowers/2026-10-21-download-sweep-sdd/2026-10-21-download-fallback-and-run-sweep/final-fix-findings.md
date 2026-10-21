# Final-review fix wave — findings and operator ruling (llama-db, 2026-10-21)

Base: 3f48bc0. Full final verdict: .superpowers/sdd/download-sweep/final-rev/handback.md

## F1 (final I1) — pin the per-show LLM-call baseline (LLM-spend strict surface)
`packages/llama/tests/test_pace_loop.py`: nothing pins that `_execute` compares `llm_calls()` against the PER-SHOW `calls_before` (cli.py ~632/646). Mutant M1 (`llm_calls() > 0`, a run-level baseline) survives the suite.
- Add a mixed-run test: `_drive(..., ["a", "b"], llm=lambda p: p == "a")` records exactly one boundary; and the reverse order (`["b", "a"]`, same predicate) also records exactly one. Verify M1 is caught (scratch copy only).
- Remove the vacuous `assert not (tmp_path / "pacing-state.json").exists()` assertions in `test_a_download_only_resume_records_no_boundary` and `test_an_already_packaged_show_records_no_boundary` (`record` is monkeypatched by `_boundaries`, so the file can never exist). Keep `recorded == []` and the read-count assertion. The already-packaged test may be kept or folded into the mixed-run test.

## F2 (final I2, OPERATOR RULING) — the sweep must not make human decisions
`sessions.sweep_verdict` returns `needs attention` for:
(a) any run whose request (via `sessions.read_request`) has `auto` present and not `True` — in ANY state (paused, incomplete, marker-less). Today only marker-less runs check `auto`.
(b) any human-gated run. Record `human_gate` in `request.json` going forward: `_get_profile` writes `"human_gate": profile.human_gate`; `_get_query` writes `"human_gate": false`. When the key is absent (runs written before this change): a `mode: "profile"` request falls back to loading that profile and reading its `human_gate`; if the profile cannot be loaded (missing, unreadable, invalid) the run is `needs attention` (the safe direction). A query-mode request with no key is not gated.
No new resume behaviour: `_resume_locked`'s `human_gate=False` stays; this only changes eligibility.
Tests: parametrized eligibility cases for (a) paused+auto:false, incomplete+auto:false; (b) human_gate:true in request; key absent + profile with human_gate=true; key absent + profile not gated (eligible); key absent + profile missing/unloadable (needs attention); query mode without key (eligible). A test that `get --profile` and `get` write the key.

## F3 (OPERATOR RULING) — a malformed updated_at must not crash the sweep
`cli._sweep_runs` sorts by `updated_at` via `datetime.fromisoformat` (`_instant`, cli.py ~330/359). A malformed or unparseable `updated_at` (or non-string) currently raises before any run is resumed. That run must instead be skipped as `needs attention` (decide it in `sweep_verdict` or before sorting — either way, it must not reach the sort and must print `skip <id>: needs attention`), and the rest of the sweep proceeds. Test it.

## F4 — keep spec and docs true
- Spec `docs/superpowers/specs/2026-10-21-download-retry-and-run-sweep-design.md` §6 eligibility: add F2 (a)/(b) and F3 as operator rulings (dated 2026-10-21, "final review").
- `CLAUDE.md` `run resume --all` text (Commands bullet) and `README.md` if it lists eligibility: state F2/F3.

## Deferred (do NOT do): body-raised Locked/RunMissing in _resume_run; stubbed turned-live test; all other deferred minors.
