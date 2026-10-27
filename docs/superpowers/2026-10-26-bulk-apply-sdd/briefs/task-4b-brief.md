# Task 4b (parent-directed addition, Shawn-approved): brief overrules act inside the guard path

Context: Task 2 (commit 16cf2b3d) splits overruled flags in `run_brief` and in reapply's fresh brief AFTER `generate_briefing` returns. So an overruled briefing-guard problem still triggers the guard's feedback retry: a second LLM call whose feedback asks the model to fix a problem the operator accepted. And `briefing_reusable` (replay.py) never reuses a stored briefing whose guard problem is overruled. Shawn approved fixing both.

Semantics (binding):
1. `generate_briefing` (stages/brief.py) takes the show's recorded overrules (`read_overrides(ws).overrules`). The new parameter defaults to `()`, which keeps every other caller exactly as today. After EACH guard run, split its problems with `overrules.split_overruled(problems, rules, show)`. Only the HELD problems decide anything: they alone trigger the feedback retry, they alone appear in the retry feedback, and they alone become hold flags. Overruled problems never trigger a retry or a hold. They are noted in `ShowNotes.brief` as `overruled: <flag>`, Task 2's note format (`overrules.NOTE_PREFIX`). A first attempt whose only problems are overruled is accepted at once, so the brief costs one LLM call.
2. Every fresh-brief caller passes the rules: `run_brief`, and reapply's fresh brief (reapply.py). Task 2's post-hoc split in those callers either stays as a harmless no-op or is folded into the new path. Either way, no flag is noted twice and none is lost.
3. `briefing_reusable` (replay.py): a stored briefing that fails today's guard is reusable when every guard problem is overruled for the show (same `split_overruled`, against the show's identifier). **Overrules may only make it accept MORE, never less.** Every other refusal stays exactly as it is, including:
   - the inputs/digest mismatch refusal,
   - the Task 15a restored-file / exclusion wording (`_RESTORED_WORDING`),
   - the short_kept handling.
   On reuse, the overruled problems are noted in `ShowNotes.brief` wherever the reuse path writes notes (reapply/replay).
   This change to `briefing_reusable`, a Global Constraints "Untouched" name, is authorised by the parent. It is the only authorised change to it.
4. Dry run first. Before any edit, list every existing test whose expectation moves, each with the clause above that moves it. An unexplained change is BLOCKED.

Tests to write (failing first, RED shown in the live tree):
- `test_overruled_guard_problem_triggers_no_retry`: a fake brief provider records calls. The guard reports only `briefing mentions unknown song: X`, and a matching `briefing-song` rule exists. Expect exactly 1 brief call, the show not held, and notes.brief `["overruled: briefing mentions unknown song: X"]`.
- `test_held_guard_problem_still_retries_with_only_held_feedback`: one overruled problem and one held problem. Expect 2 calls; the retry feedback names the held problem and not the overruled one; the held flag holds after the retry.
- `test_generate_briefing_without_rules_unchanged` **(pin)**: default `()` gives today's retry behaviour.
- `test_briefing_reusable_accepts_all_overruled` and `test_briefing_reusable_still_refuses_unoverruled_problem`.
- `test_briefing_reusable_overrules_never_refuse_more` **(pin)**: for the existing reusable/refused cases, adding rules never turns a reusable verdict into refused. In particular, the restored-wording refusal still refuses even with every guard problem overruled.
- `test_reapply_fresh_brief_passes_rules` (reapply's fresh-brief path makes one call for an overruled-only problem).
- `test_reuse_notes_overruled_problems`.

Commit message: `feat(overrules): overruled briefing problems skip the guard retry and allow reuse`.
