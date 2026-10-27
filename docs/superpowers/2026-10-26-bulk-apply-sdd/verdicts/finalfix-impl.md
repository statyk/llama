# finalfix-impl report
Status: DONE_WITH_CONCERNS (one: M1, below). Suite: `./.venv/bin/python -m pytest -q` -> 6353 passed, 1 skipped, 8 deselected.
Dispatches: none (no subagents).

## I3 RED (before changing cli.py)
`./.venv/bin/python -m pytest packages/llama/tests/test_redo_cmd.py -k before_any_llm -q`
-> `AssertionError: assert ['run_gather', 'run_brief'] == []` for both [gather] and [brief] params; `2 failed, 61 deselected`.
(First draft failed for a wrong reason, a stub returning None / show.json dropped; fixed the test to delegate to stub_stages(monkeypatch, OLD2) and re-ran RED for the right reason.)
GREEN: same command passes (`133 passed` with test_deliver_cmd.py). Test `test_redo_of_a_delivered_show_refuses_strict_reuse_before_any_llm_call` (parametrized from gather, brief), station dir removed, asserts `station copy unreadable: no directory ...` + HINT, zero gather/brief calls, tree unchanged. Uses recording wrappers on pipeline.run_gather/run_brief (no provider ladder involved because stages are stubbed).
Impl: `audio_reuse.check_pairs(reuse, show_ws)` right after `plan_reuse` in `_redo_show_locked` (new `from llama import audio_reuse` in cli.py). check_pairs is a no-op when non-strict and side-effect free. No existing test expectation changed.

## Fixes
- I1 CLAUDE.md deliver bullet reworded: library campaign record awaiting (unreadable included) is refused by name and in selectors; a station copy carrying awaiting_fix whose library show is processed is replaced wholesale, clearing the mark. Fixed strings after it kept. Checked the other docs-commit sentences (line ~664 awaiting_fix paragraph, clear-mark, status): no same confusion.
- I2 reapply.py module docstring now: processed -> after_commit -> purge, with reason. Inline comment at ~380 was already correct.
- M1 `_deliver_batch`: on passing under-lock re-check, `marks.pop(slug, None)` and echo `<slug>: processed since the plan was listed; delivering`. Test `test_batch_deliver_does_not_report_a_show_processed_meanwhile_as_refused`.
- M2 `_fixed_for_delivery` docstring: `_deliver_one` re-checks only awaiting-fix under the lock.
- M3 plan Appendix B: three bullets added (exact torn-line text from batch_snapshot: `<path> line N is not an after-record; nothing restored`; then `NO_WRITE` refusal).

## Concern
M1: the "(refused: awaiting fix)" text is on the plan listing printed by `_confirm_plan` BEFORE any lock/re-check, so `marks.pop` after the fact cannot change it; marks isn't read later. I added the explicit "processed since ... delivering" line so the output is no longer misleading, and the pop per the brief. Pre-plan reporting would need a re-scan; not done.

## Commits
two (code+tests; docs), each with the Opus 5.5 trailer and the test command.
