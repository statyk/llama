# Checkpoint B addendum (orch-r2)

Source: b90-analysis child (Sonnet), read-only from a git-archive snapshot of d1bb0127; full handback at $D/b90-analysis/handback.md; scripts ~/.llama-harness/bulk/b90/.

## B-90: why 90 newly-held rows are not marked (at d1bb0127)

**Reproduction check: passes.** Snapshot of d1bb0127 (`git archive`) imported (`llama` and `bulk_apply` resolved under `~/.llama-harness/bulk/b90/src`); `mark_plan` against `~/.llama`, the arm, the frozen list and `reselections.json` gives total 2551 marked (= dry run), newly-held 220 = 130 marked + 90 unmarked. Scripts: `~/.llama-harness/bulk/b90/{cls.py,sub.py,sub2.py,classes.json}`. The 130 marked are: 126 `changed by the held-backlog fixes`, 3 `recording re-selection`, 1 `stored briefing fails today's guard`; states packaged 104, delivered 24, briefed 2.

| Class | n | Rule branch (`_plan_one_mark`) | Spec intends unmarked? |
|---|---|---|---|
| A. No visible change, not processed, not frozen, `_guard_holds` false | 89 | falls through to the final `return None` (`row_label_only` false, `row_visible_changes` empty, `processed` false, not in `frozen`, guard false) | Unclear: spec is silent on newly-held. "Who gets marked" lists only four triggers (visible-field change, frozen needs-LLM, stored briefing fails today's guard, re-selection); a new hold on unchanged fields matches none. |
| B. Label-only change | 1 | `row_label_only(row, stored)` true | Yes: "Not a label-only change (`title_source` or `structure.alignment` alone...)". |
| C. needs-LLM / unreplayable / processed / show dir missing / arm row missing / re-selection | 0 | other branches | n/a (none of these occur among the 90) |

None of the 90 is in the frozen list, in `reselections.json`, or has outcome in `_NO_DIFF`. Processed is false for all 89 of class A.

Examples A: `aquariumrescueunit-1989-12-01`, `aquariumrescueunit-2005-01-08` (the only delivered one), `badlivers-1991-05-04`, `belafleckandtheflecktones-2004-12-11`, `billystrings-2018-05-26`.
Example B: `stantonmoore-2005-05-14` (title_changes only: #18 `new song?`, source `setlist` -> `desc-position`; it also carries the long-show hold flag).

### Sub-classification of class A (89)
Common to all 89: arm row has empty `title_changes`, `set_changes`, `segue_changes`, and null `venue`/`city`/`date`/`set_breaks`/`alignment`; `needs_llm` empty; `briefing` = none; `would_be` null; `reproduces` false. Stored side: `stored_flags` empty, `stored_brief_guard` empty, stored `needs_review` false, no recorded overrules in `overrides.json`. The arm row carries 1+ new `gather_flags`/`vet_flags`/`brief_flags` (all gather or vet; the hold is the only difference). `_guard_holds` reads only `stored_brief_guard` (empty), so it never sees the arm's new flags. State: packaged 88, delivered 1 (`aquariumrescueunit-2005-01-08`). Flag count: 1 flag family in 80 rows, 2 in 9.

By flag family (a row can count in two; none is covered by an existing overrule, since no row has any overrule):
- venue mismatch 21 (`darkstarorchestra-2008-07-23`, `darkstarorchestra-2013-05-24`, `furthur-2010-05-28`)
- structure has N sets but jerrybase shows N 19 (`bobweir-2013-03-01`, `darkstarorchestra-2002-04-13`, `darkstarorchestra-2004-08-31`)
- research asserts unknown song 12 (`badlivers-1991-05-04`, `godspeedyoublackemperor-1999-01-19`, `-1999-09-04`)
- research asserts wrong date 10 (`billystrings-2018-05-26`, `derektrucksband-2005-06-17`, `dumpstaphunk-2010-05-01`)
- research asserts N sets but structure has N 9 (`gratefuldead-1970-05-01`, `-1970-08-18`, `mogwai-1997-10-15`)
- single-set structure for a long show 8 (`aquariumrescueunit-2005-01-08`, `belafleckandtheflecktones-2004-12-11`, `donnathebuffalo-2011-01-22`)
- jerrybase set closer ... not at a set break 14 total (`darkstarorchestra-2004-04-20`, `-2007-05-08`, `-2009-02-27`, `furthur-2010-07-08`, `-07-30`)
- low-confidence setlist 3 (`aquariumrescueunit-1989-12-01`, `melvinsparksband-2004-05-28`, `stantonmoore-2002-05-02`)
- setlist evidence shows multiple sets but alignment found none 2 (`delmccouryband-2008-05-24`, `firehose-1991-04-19`)
- recordings of this date disagree on city 2 (`moe-2004-09-04`, `philleshandfriends-2008-06-15`)

Reading: these are shows the stored package ships unflagged whose replay under today's guards would be held, with no manifest-visible change. The rule leaves them unmarked, so they stay airable/deliverable as they are (the one delivered show, `aquariumrescueunit-2005-01-08`, stays on air). Marking them would be a new trigger the spec does not list.

## Summary
- Reproduced exactly: 2551 total; newly-held 220 = 130 marked + 90 unmarked.
- 89 of 90: no visible field change, not processed, not frozen, `_guard_holds` false (it reads only `stored_brief_guard`, which is empty); the hold comes only from new gather/vet flags. The spec does not list this as a mark trigger (silent, so unclear).
- 1 of 90 (`stantonmoore-2005-05-14`): label-only (title_source setlist -> desc-position); spec says intended.
- None of the 90 is frozen, re-selected, processed, missing a dir or an arm row.
- Among the 89: 88 packaged, 1 delivered (`aquariumrescueunit-2005-01-08`); no overrules and no stored flags on any, so no existing overrule covers the flags.
- Top flags: venue mismatch 21, jerrybase set-count 19, research unknown song 12, wrong date 10, research set-count 9, single-set long show 8, jerrybase closer 14.
- Decision for the operator: whether newly-held-with-no-visible-change should be a mark trigger (it is not one today).
