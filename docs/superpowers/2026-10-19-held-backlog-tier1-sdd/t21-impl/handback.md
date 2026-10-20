# T21 handback: DONE_WITH_CONCERNS (minor)
Commits: 5b004fc (feature + tests), then a follow-up test commit (see git log, "pin partial-resolution refusal").
Changed: packages/llama/src/llama/cli.py (`_untitled_counts`, `_overrides_snapshot`, `_untitled_resolution`, `fix --untitled`, `_resolve_prompt(untitled=)`, triage `[u]`); tests in test_fix.py, test_triage.py, test_cli.py.
Tests: full suite `./.venv/bin/python -m pytest -q` -> 3761 passed, 1 skipped, 8 deselected.
Ruling applied: --clear-set-breaks/--clear-encore/--clear-title refused (in the parametrized test); all refusals precede the prompt and writes (test asserts no prompt text, no overrides, no redo).
Mutation (scratch under $TMPDIR/mut-t21-impl-XXXX, removed):
- (a) overrides written before confirm -> test_untitled_lists_filenames_and_declining_writes_nothing -> CAUGHT by it
- (b) `resolved >= total` (partial allowed) -> predicted test_untitled_is_refused_when_any_track_is_resolved -> SURVIVED (that test has a 1-track show); added test_untitled_is_refused_when_only_some_tracks_are_resolved (+ triage partial test); re-run CAUGHT by it
- (c) _clear_hold skipped -> test_untitled_overrules_remaining_flags_then_continues_from_brief -> CAUGHT by it
- (d) [u] offered with <=1 resolved -> test_triage_offers_u_only_when_every_track_is_unresolved -> CAUGHT by it
Deviations/concerns:
- Also refuse --set-venue/--set-city/--set-date with --untitled (otherwise silently dropped); same message format.
- Zero-track show is refused with "(0 of 0 resolved)"; [u] not offered then.
- Decline detection uses an overrides.json byte snapshot (None return is ambiguous between decline and still-held). Triage decline returns to the prompt; fix prints "declined; nothing written", exit 0.
- Spec end-state acceptance (tape ends packaged) is met only with _redo_show stubbed, except test_untitled_gather_makes_no_align_structure_call, which runs the real compute_gather.
