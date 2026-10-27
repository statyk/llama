# t4b-review handback (Task 4b, BASE c45936ff..HEAD 2ea940c9)

### Spec Compliance

- ✅ Spec compliant. Each clause of task-4b-brief.md checked against the diff:
  - Clause 1: `generate_briefing(..., overrules=())` (stages/brief.py:296-298) splits after each guard run (brief.py ~:330, `held, _overruled = split_overruled(problems, overrules, show)`). Only `held` decides the break and goes into the feedback text. An overruled-only first attempt breaks at once, so it makes 1 call. With the default `()` the path is identical: `split_overruled` with no rules returns every flag as held, in order (overrules.py:87-98), and `flag_key` is total (no raise path, overrules.py:55-73). Notes use `NOTE_PREFIX` via the caller split.
  - Clause 2: both fresh-brief callers pass the rules: `run_brief` (brief.py:367-369) and reapply (reapply.py:136-140). Task 2's post-hoc split stays in both. It is the single point where the returned problems become flags or notes, against the same `show`/`final_show` that `generate_briefing` split with, so no flag is noted twice and none is lost. This is the brief's "stays" option. It is not a no-op, but the binding sentence ("no flag noted twice, none lost") holds.
  - Clause 3: `briefing_reusable(..., *, overrules=())` (replay.py:492) adds exactly one line, `problems, _overruled = split_overruled(problems, overrules, new_show)` (replay.py:539). The tracks-differ, broadcast-fields, narration and Task 15a restored-file/wording refusals (short_kept handling included) are byte-identical. `held ⊆ problems` by construction (overrules.py:90-98), so it can only accept more. The default `()` gives today's verdict and text. On reuse, `compute_legs` (replay.py:643-652) and `briefing_reusable` split against the same `replayed` show and the same rules. `_read_briefing` already normalises (replay.py:549-554), so the guard inputs match and `brief_flags` stays [] by construction. Notes reach notes.json `brief` (reapply.py:130 → :167-169) and the replay row `notes` (replay.py:838-839).
  - Clause 4: the dry run is recorded in the implementer's handback. I checked its claims: no existing assertion moved in the diff. The diff touches tests only by appending new ones.
  - Required tests: all 7 are present by name, plus 3 extra pins/coverage (`test_reuse_without_the_rule_still_writes_a_fresh_brief`, `test_compute_legs_reuses_with_overruled_guard_problems_and_notes_them`, and the 7-case loop inside the never-refuse-more pin). RED evidence is reported for each new branch.
- ⚠️ Cannot verify from diff (cross-task, for the controller): plan line 519, the `mark_plan` rule, marks a row `stored briefing fails today's guard` when `stored_brief_guard` is non-empty. `ShowReplay.stored_brief_guard` (replay.py:820) is still the RAW guard, not overrule-aware. After this task, a delivered show whose only stored-guard problem is overruled would be marked awaiting-fix, yet reapply would then reuse that briefing unchanged (`briefing_reusable` now accepts it). The result is a spurious mark, a station block and a re-process cycle for nothing. The marking task's brief should decide whether that rule uses the held part only (split with the show's overrules). The implementer raised this as concern 2. I confirmed the consumer exists in the plan text. No code consumes it for marking yet (`grep "fails today's guard"` finds only the plan).

### Strengths
- The change is minimal and well placed. The one-line split in `briefing_reusable` is placed after every pre-guard refusal and before the restored-file check. So the "only accept more" property is structural, not incidental (replay.py:538-544).
- The docstrings state the new contract precisely, including the caveat that `generate_briefing` returns all problems and callers must split (brief.py:302-310; replay.py:503-507).
- The `Legs.brief_notes` field defaults to `[]`, so the existing keyword construction (test_replay.py:445) and old callers are unaffected (replay.py:574-576).
- The tests are behavioural, not mock-shaped. They count real FakeProvider calls and assert the retry prompt's text (test_stage_brief.py new block). The never-refuse-more pin enumerates every refusal class and asserts exact equality for the non-guard ones. It also asserts that the restored-wording refusal survives full guard overruling. `test_briefing_reusable_still_refuses_unoverruled_problem` also pins the inert-other-identifier case and the exact refusal text.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. packages/llama/src/llama/stages/brief.py:296-310 (contract). `generate_briefing` splits internally, then each caller re-splits the returned list with the same rules. This is correct today: both callers do it (brief.py:373, reapply.py:144). But it is a two-step contract: a future caller passing `overrules=` without the post-hoc split would hold on overruled problems, and the docstring is the only guard. Fix: return `(briefing, held, notes)`, or have the callers rely on a single helper. Not blocking, since the docstring states the contract and both callers comply. Note for the Task 9/10 `show_unit` rewrite of reapply: it must keep both `overrules=` and the post-hoc split (the implementer's self-review says so too).
2. packages/llama/tests/test_stage_brief.py (new `_songs_briefing`). It duplicates `_x_briefing`'s body (test_stage_brief.py:537-545) except for `mentioned_songs`. A `songs` parameter on `_x_briefing` would avoid the copy. Cosmetic.
3. packages/llama/src/llama/replay.py:539 and brief.py (~:330). The `_overruled` binding is unused in both. Harmless, but `held, _ = ...` or a direct index would read cleaner. Cosmetic.
4. Behaviour note, no fix needed: when some guard problems are overruled, the `briefing guard: ...` refusal text names only the held ones (replay.py:540-541). This is consistent with the docstring. Replay-arm text comparisons between pre- and post-4b arms would differ for such shows. Arms are always same-code in the campaign, so this is moot.

### Checks run
- Untouched-names grep over the diff (`DURATION_TOLERANCE_S`, `purge_package_audio`, `STOP_AFTER_LLM_FAILURES`, `load_list`, junk/`SHORT_FRACTION`/`MIN_PLAUSIBLE`, `audio_reuse`, piece-3 constants `AGREEMENT_FLOOR`/`WRITTEN_DURATION*`/`SHORT_CORE*`/`SHORT_TAG_WINDOW`/`STEM_SUBSTRING*`, `_RESTORED_WORDING`/`_restored_mentions`): no +/- line hits. `briefing_reusable` is the only Untouched name changed, as authorised.
- Named risk "default `()` changes behaviour": checked `split_overruled`/`flag_key` (overrules.py:55-98). They are total, order-preserving and identity when given no rules.
- Named risk "the reuse split diverges from the reusable decision": checked `_read_briefing` normalisation (replay.py:549-554). Both use the normalised briefing, the same show and the same rules.
- Named risk "another `briefing_reusable`/`generate_briefing` caller misses the rules": grepped non-test callers. Only reapply.py:136, replay.py:647 and brief.py:367, all updated.
- Named risk "new replay `notes` content perturbs arm comparison": `notes` is display-only in scripts/replay_holds.py (:618, :631, :663, :1270).
- No tests re-run, and no mutation run: the implementer's RED-before-GREEN evidence covers each new branch.

### Assessment

**Task quality:** Approved

**Reasoning:** The diff is minimal and correctly placed, and it meets every clause. `briefing_reusable` can now only accept more, because of where the split sits and because `split_overruled` is subset-preserving. The tests pin the retry count, the feedback text, the default path and every non-guard refusal. The one open item is cross-task: `stored_brief_guard` marking (plan line 519) should be made overrule-aware in the marking task.
