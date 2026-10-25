### Spec Compliance

- ✅ Spec compliant (spec 5.3, plan Task 11), with one deviation from the brief's wording that changes no reuse decision:
  - Filtering: `short` comes from the new show only (replay.py:247). It is removed from both shows (replay.py:248-249). An old show.json without `short_kept` reads False (plan Task 2 default), so only the new side's flags count. Correct.
  - Matched by filename: the `tracks differ` check (replay.py:250-251) makes the later positional title/set/segue comparisons (replay.py:262-264) a per-filename comparison. Correct.
  - Set-break key: the filename of the last remaining track with `index <= i` in that show's own index space, `None` when none, compared sorted with a None-safe key (replay.py:253-259). Probed in scratch:
    - a break after a removed short-kept track, or one sliding across it, keys to the real track before it;
    - a break preceded only by short-kept tracks keys `None`;
    - a break whose only following tracks are short-kept still counts and forces a brief. That is the literal spec rule, and the error is the conservative kind (it costs a brief, never a false reuse).
  - Narration and `briefing_guard(normalize_briefing(...), new_show)` still run unchanged after the field checks (replay.py:272-276).
  - Deviation: the brief asks for first-failure reasons (`titles/sets/segues`, then `set_breaks`, then `date/venue/city`). The code keeps today's single joined `broadcast fields changed: a, b, ...` message (replay.py:261-271). **It changes no decision.** Every one of those reasons is non-None either way. The only caller is replay.py:371, which branches on `reason is None` and stores the text in `Legs.brief_reason`. A grep finds no reader that parses `brief_reason` (replay.py:300 and 378 only; scripts included). Keeping the joined form also keeps test_replay.py:292 and :411 valid. Acceptable.
- ⚠️ Cannot verify from diff (cross-task, for the controller):
  - **Reapply's structure gate.** test_reapply.py:1169 needs `allow_structure_change=True`. `shipped_diff` (replay.py:201-212) records every position as a set change whenever the track count differs, so `_structure_changed` is True for every show that gained a short-kept file. In production, `reapply` will therefore skip each such show as `skipped: structure changed` unless `--allow-structure-change` is passed, and `compare` will put them in `structure_changed_list.json` for hand-checking. That holds even when their briefing is reusable. Neither the spec nor the plan mentions `shipped_diff`/structure-changed for piece 4 (grepped both). Confirm that the bulk-apply route expects this, or that another task owns it.
  - **Filename format in old show.json files.** Old dirs must store `Track.filename` exactly as the current gather does. Otherwise `tracks differ` fires on every old show. Task 15's measurement (at least 1,017 reuses) will show this. It cannot be seen from the diff.

### Strengths

- Small, contained change: one function, signature unchanged. The filtered lists are computed once and every field comparison uses them.
- The break key works in each show's own index space, so a moved break is judged by real tracks only, as spec 5.3 asks. The None-safe sort key avoids a `TypeError` on mixed None and str.
- The tests pin each mechanism, confirmed by mutation in a scratch copy (`git archive 5c78650`). Shadowing was proven by a sentinel `raise` in the scratch `replay.py`, which broke collection. A prediction was written before each mutant:
  - no filtering: CAUGHT (inserted, title-change pin, banter-sliding, guard, reapply);
  - old side left unfiltered: CAUGHT (already-included test only);
  - raw `set_breaks` compare: CAUGHT (banter-sliding, reapply);
  - `<` in place of `<=` in the key: CAUGHT (banter-sliding, reapply);
  - break keys over unfiltered lists: CAUGHT (banter-sliding, reapply);
  - set_breaks check removed: CAUGHT (moved-real-break);
  - titles check removed: CAUGHT (title-change pin plus the existing joined-message test);
  - sets or segues over unfiltered lists: CAUGHT (5 tests each);
  - guard removed: CAUGHT (`test_guard_still_runs_on_reuse`, `test_briefing_reusable_reasons`);
  - `tracks differ` return removed: SURVIVED, as predicted (Minor 1).
- The reapply test drives a real fixture item through `reapply_show` to `briefing == "reuse"`. It is red without the filter, so it covers the integration and not only the pure function.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **`tracks differ` has no test.** No test asserts `tracks differ` (replay.py:251), so the mutant that drops the return survives. Its only independent effect is equal-length remaining lists whose filenames differ while titles, sets, segues and break keys agree. My scratch probe of a renamed file returned `tracks differ`. Add a one-line assertion, for example to `test_briefing_reusable_reasons` (test_replay.py:394).
2. **The 173-case test passes without the change.** test_replay.py:906 passes on today's code: the banter file has identical fields on both sides, so filtering is not needed for it to pass. It does catch the "old side unfiltered" mutant, so the mechanism is pinned. It would model the real 173 case better, and fail on today's code as the brief's "failing tests" framing implies, if the new side's short-kept file differed in title or set. `test_a_moved_real_break_forces_a_brief` (test_replay.py:935) also passes on today's code and is unmarked. It works as a pin, so label it `(pin)`.
3. **No test for the `None` break key.** No test exercises a break preceded only by short-kept tracks (replay.py:258). The behaviour is conservative, and I checked it by a scratch probe only.
4. **Stale docstring.** The docstring (replay.py:242-245) still says "the first failing reason" and does not mention the short-kept exclusion or the filename match. Add a line naming spec 5.3.
5. Grepped the diff for every global "untouched" name (junk/titles/structure constants, `DURATION_TOLERANCE_S`, `purge_package_audio`): none appear. The implementer's reported test output (5019 passed, 1 skipped, 8 deselected) shows no warnings.

### Assessment

**Task quality:** Approved

**Reasoning:** `briefing_reusable` follows spec 5.3 exactly: the new show's short-kept files are dropped on both sides, tracks are matched by filename, and breaks are keyed by the last remaining track. Mutation confirms every decision branch except the untested `tracks differ` return. The joined reason message changes no reuse decision, since nothing parses `brief_reason`. One cross-task item needs the controller's confirmation: reapply's structure-changed gate will still refuse every show that gained a short file unless the operator passes `--allow-structure-change`.
