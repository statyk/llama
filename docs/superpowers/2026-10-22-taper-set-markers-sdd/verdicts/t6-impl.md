# t6-impl handback: DONE
Commit: 63c4a4b feat(replay): a taper-owned candidate no longer needs the stored LLM structure
Change: replay.py compute_legs, one condition: `... alignment == "llm" and not gathered.taper_owned`. Nothing else in replay.py. setlist.py diff vs main empty.
Tests: test_replay.py 89 passed (before commit run); test_reapply.py new test passes; full `./.venv/bin/python -m pytest -q`: 4408 passed, 1 skipped, 8 deselected.
Brief test -> location (test_replay.py unless noted): test_stored_llm_taper_owned_is_replayable; test_stored_llm_deterministic_candidate_stays_needs_llm (pin); test_stored_llm_anchored_candidate_stays_needs_llm (pin; jerrybase lookup monkeypatched, alignment=="jerrybase" asserted); test_cross_check_failure_keeps_stored_llm_needs_llm (asserts reason startswith "cross-check:"; paf2007-10-12 excerpt as literal); test_track_title_veto_keeps_stored_llm_needs_llm (asserts reason "veto: track title"); test_reapply.py::test_reapply_processes_a_taper_owned_stored_llm_show. Existing test_stored_llm_alignment_is_needs_llm unchanged.
Replayable test failed on pre-change code (verified before implementing).
Mutants (scratch git-archive copy, PYTHONPATH shadow; llama.__file__ proven inside scratch):
A remove `and not gathered.taper_owned`: killed by test_stored_llm_taper_owned_is_replayable, test_reapply_processes_a_taper_owned_stored_llm_show
B `and not gathered.needs_llm`: killed by replayable test, test_cross_check_failure_keeps_stored_llm_needs_llm, reapply test
C `and alignment != "deterministic"`: killed by test_stored_llm_alignment_is_needs_llm, deterministic_candidate, cross_check, track_title_veto, test_reapply_writes_nothing_on_a_needs_llm_show
Note: the anchored-candidate test was not killed by B/C (not required); it pins the jerrybase path directly.
Deviations: none. Reapply test needed no new fixture: edits cache description + stored alignment on build_library's show.
Concerns: none.
