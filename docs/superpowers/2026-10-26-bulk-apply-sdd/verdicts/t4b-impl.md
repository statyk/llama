# t4b-impl handback

Status: DONE_WITH_CONCERNS
Commit: 2ea940c9 feat(overrules): overruled briefing problems skip the guard retry and allow reuse

## What was implemented
- `stages/brief.py` `generate_briefing(..., overrules: Sequence[Overrule] = ())`: after each guard run, `split_overruled(problems, overrules, show)`. Only the HELD problems decide whether to retry and go into the retry feedback. An attempt with only overruled problems breaks at once, so it costs 1 LLM call. Return contract kept as a 2-tuple: `problems` is still every guard problem of the accepted attempt, overruled ones included, so with the default `()` the behaviour is exactly today's.
- `run_brief` and reapply's fresh brief now pass `overrules=overrides.overrules`. Task 2's post-hoc `split_overruled` in both callers STAYS, and it is the single place where the returned problems become hold flags (held) or `overruled: <flag>` notes. No note is doubled and none is lost. The brief offered "harmless no-op or folded"; this is neither. I chose it so the return arity is unchanged for every caller (two existing tests unpack 2).
- `replay.briefing_reusable(..., *, overrules=())`: guard problems are split against `new_show`. The refusal fires only on held problems and names only those. Nothing else in the function changed: the tracks-differ, broadcast-fields, narration and Task 15a restored-wording refusals (short_kept handling included) are as before. This is the one authorised change to it.
- `compute_legs` reads overrides once in the brief block and passes the rules. On reuse it computes `brief_flags, brief_notes = split_overruled(briefing_guard(stored, replayed), rules, replayed)`. `brief_flags` is still [] by construction. `Legs.brief_notes` is a new field (defaulted `[]`).
- `reapply_show`: on reuse, `brief_notes = list(legs.brief_notes)` is written to notes.json `brief`. `replay_show`: `r.notes` now ends with `legs.brief_notes`.

## Dry run (before any edit)
No existing test expectation moves.
- test_stage_brief::test_brief_overrule_goes_to_notes_brief queues 2 completions. Under clause 1 only 1 is consumed. It asserts no call count, so it is not moved.
- test_stage_brief::test_brief_overrule_on_another_recording_still_holds: the rule is on another identifier, so the problem is held and the retry runs as today. Not moved.
- test_reapply::test_reapply_fresh_brief_overrule_goes_to_notes_brief: same as the first (2 queued, 1 consumed). Not moved.
- test_replay::test_replay_sees_overrules: its rules are gather and vet flags only. Not moved.
- test_replay.py:445 builds `Legs(...)` by keyword, and the new field is defaulted. Not moved.
- Every existing briefing_reusable test calls with the default `()`. Not moved.

## Tests added (10)
test_stage_brief.py:
- test_overruled_guard_problem_triggers_no_retry
- test_held_guard_problem_still_retries_with_only_held_feedback
- test_generate_briefing_without_rules_unchanged (pin)

test_reapply.py:
- test_reapply_fresh_brief_passes_rules
- test_reuse_notes_overruled_problems
- test_reuse_without_the_rule_still_writes_a_fresh_brief (pin)

test_replay.py:
- test_briefing_reusable_accepts_all_overruled
- test_briefing_reusable_still_refuses_unoverruled_problem (it also checks that a rule on another identifier is inert)
- test_briefing_reusable_overrules_never_refuse_more (pin). Seven cases: reusable, guard, narration, broadcast field, tracks differ, restored name, restored wording plus a guard problem. Adding rules never turns a reusable verdict into a refusal, and leaves every non-guard refusal unchanged. Explicit check: the restored-wording refusal still refuses with every guard problem overruled.
- test_compute_legs_reuses_with_overruled_guard_problems_and_notes_them. It covers the Legs.brief_notes path and the replay_show notes.

## TDD evidence
RED, live tree, before any source edit:
`./.venv/bin/python -m pytest -q packages/llama/tests/test_stage_brief.py packages/llama/tests/test_reapply.py packages/llama/tests/test_replay.py -k "..."`
-> `8 failed, 1 passed`. The pass is the reuse-without-rule pin. The failures:
- test_overruled_guard_problem_triggers_no_retry
- test_generate_briefing_without_rules_unchanged (TypeError on the `overrules=` kwarg)
- test_reapply_fresh_brief_passes_rules
- test_reuse_notes_overruled_problems
- briefing_reusable accepts / still_refuses / never_refuse_more (TypeError)
- test_compute_legs_reuses... (`'fresh' == 'reuse'`)

Plus `-k held_guard_problem_still_retries` -> 1 failed: `assert 'briefing mentions unknown song: X' not in retry_prompt`.

GREEN: `./.venv/bin/python -m pytest -q packages/llama/tests/test_stage_brief.py packages/llama/tests/test_reapply.py packages/llama/tests/test_replay.py` -> 470 passed.

Full suite: `./.venv/bin/python -m pytest -q` -> 6055 passed, 1 skipped, 8 deselected (70 s). That is the baseline of 6045 plus 10 new. `llama.__file__` resolves inside the worktree.

## Files changed
- packages/llama/src/llama/stages/brief.py
- packages/llama/src/llama/replay.py
- packages/llama/src/llama/reapply.py
- packages/llama/tests/test_stage_brief.py
- packages/llama/tests/test_reapply.py
- packages/llama/tests/test_replay.py

## Self-review
- The guard-path change sits inside `generate_briefing` (brief.py) and `briefing_reusable`/`compute_legs` (replay.py). reapply only passes the rules and copies `legs.brief_notes` into the notes it already writes, so the Task 9/10 `show_unit` rewrite carries it as long as it keeps (a) `overrules=` on the fresh-brief call, (b) the post-hoc split, and (c) `legs.brief_notes` on reuse.
- No other Global Constraints "Untouched" name is in the diff.
- No mutation run was done. RED-before-implementation covers each new branch: the retry decision, the feedback text, the reusable split, and the reuse notes.

## Concerns
1. The generate_briefing contract differs from the brief's literal options. It returns ALL problems and leaves the held/notes split to the caller. That keeps the 2-tuple, but a future caller that passes `overrules=` without splitting would hold on overruled problems. The docstring says so.
2. `ShowReplay.stored_brief_guard` (replay_show) is still the raw guard, not overrule-aware. If the marking task builds `stored briefing fails today's guard` from it, a show whose only stored-guard problem is overruled would still be marked. That is out of my scope; flagging it for the marking task.
3. The `briefing guard: ...` refusal text now lists only the held problems when some are overruled. The text is unchanged when no rule matches.
