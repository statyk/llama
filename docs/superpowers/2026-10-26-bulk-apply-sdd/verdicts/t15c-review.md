### Spec Compliance
- ✅ Spec compliant. Checked against the Task 15c brief:
  - `REASON_NEWLY_HELD = "newly held by today's checks"` sits beside the other four constants and is appended to `_REASON_KINDS` (scripts/bulk_apply.py:508-510).
  - The trigger is the last check in `_plan_one_mark`, after the guard check (bulk_apply.py:700-701). The order of the earlier checks holds:
    - the re-selection return comes first;
    - the `_NO_DIFF` (needs-llm/unreplayable) early return follows;
    - then `row_label_only` → None;
    - then a visible change, `if processed: return None`, frozen and guard (bulk_apply.py:676-699).
  - Start stage is `gather` and digests are the row's (`row.get("digests") or None`, the same value the visible-change and guard reasons carry).
  - Reason string (`_newly_held_reason`, bulk_apply.py:660-670):
    - kinds come from `gather_flags + vet_flags + brief_flags`, in first-seen order, without repeats;
    - a flag where `flag_key` returns None gives `package`;
    - a row with no flags gives the bare prefix with no colon.
  - `_print_mark_plan` (bulk_apply.py:1192-1201) needs no change. It seeds a row per `_REASON_KINDS` entry and assigns kind by `startswith`. No other reason starts with the new prefix, so there is no collision.
  - The plan's Contracts line matches the brief's text exactly. Nothing else in the plan changed.
  - All four fixed test names are present, plus one extra.
  - `mark_apply`, `unmark`, `write_mark`, `emcee_running()`, the record line and the exit rule are all outside the diff, so Review Focus 1 is untouched.
  - Grep of the diff for the "Untouched" items: none appear. No junk constants, `DURATION_TOLERANCE_S`, `audio_reuse`, `purge_package_audio`, `STOP_AFTER_LLM_FAILURES`, `load_list` or `briefing_reusable`.
- I agree with the orchestrator ruling. Putting the trigger last means every more specific reason wins. Listing flag kinds instead of flag texts keeps the station `awaiting_fix.reason`, and emcee's `awaiting fix from llama: <reason>` line, short and stable. The kinds are fixed tokens, so the reason can never contain a newline.
- ⚠️ Cannot verify from the diff: the full-suite result (6342 passed, 1 skipped, 8 deselected) and the RED/mutant evidence come from the implementer's report and were not re-run. Nothing in the code gave me a specific doubt, so I did not re-run them.

### Strengths
- The change is small and exactly where the brief scoped it. The new trigger reuses the existing `NEWLY_HELD` outcome constant and `flag_key`, so it adds no new classification logic.
- The two guard tests (label-only/processed, and earlier triggers win) cannot fail before the change. The implementer still showed they matter, with a mutant in a scratch copy that hoisted the check to the top, and stated which tests should go red before running it. That is the right method for tests that pin precedence.
- `test_newly_held_without_visible_change_is_marked` checks real outcomes end to end:
  - the library record's last mark reason;
  - no station directory for the packaged show;
  - the station manifest's `awaiting_fix.reason` for the delivered one;
  - the batch record lines (`marked` / `not delivered`).
- The dry-run test asserts the exact table line with newlines on both sides and checks that the library and station files are byte-unchanged.
- The extra test, `test_newly_held_reason_kinds_first_seen_and_package_fallback`, pins every clause of the string rule: package fallback, de-duplication across lists, order across gather/vet/brief, and the bare prefix.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **A row held only by a carried package flag gets the bare reason (brief-mandated; zero rows today).** scripts/bulk_apply.py:663-670.
   - The brief says a row "cannot be newly held without" a gather/vet/brief flag. That is not strictly true. `replay.classify` (packages/llama/src/llama/replay.py:654, 693-694) counts `carried_flags` (stored package-family `review_flags`) in `legs.flags`, so a non-held show carrying a stored package flag is `newly-held` with all three lists empty.
   - Such a row would be marked `newly held by today's checks` with no kinds. Reapply never clears a carried package flag (replay.py:651-653), so the mark could not be resolved by re-processing alone.
   - The Checkpoint B addendum measured `stored_flags` empty on all 89 rows, so the population is empty today and this is not a defect in this task. I am noting it so the orchestrator does not rely on the brief's "cannot happen" premise. If it matters, the reason could also read `stored_flags`' package entries.
2. **Stale docstring.** `_could_mark` (bulk_apply.py:717-720) still says a row may be marked when it is "an arm row with a diff". A no-diff `newly-held` row is now markable. The behaviour is already right (any outcome outside `_NO_DIFF`); only the wording lags. The implementer flagged this and left it out of scope.
3. **Forward reference to a constant.** `_plan_one_mark` (bulk_apply.py:700) uses `NEWLY_HELD`, which is defined about 600 lines later in the wave section (bulk_apply.py:1315). It resolves at call time and works, but a reader of the marking section has to search for it. Moving it up beside `_NO_DIFF`, or adding a short comment, would help.
4. **Spec text now trails the code.** Spec "Who gets marked" still lists four triggers. As the brief directs, only the plan's Contracts line was changed. If the spec is meant to stay the binding description, its "Who gets marked" / "Marking skips" sections need the fifth trigger at the next spec touch. This is an orchestrator follow-up, not an implementer defect.

### Assessment
**Task quality:** Approved
**Reasoning:** The trigger is placed exactly as ruled, the reason string follows the contract clause for clause, and the tests pin both the new behaviour and the precedence of every earlier trigger, with a mutant showing the precedence tests matter. The remaining items are a documentation lag and a carried-flag edge case with no rows today.
