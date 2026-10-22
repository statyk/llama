# t9-fix2 handback

**Status: DONE_WITH_CONCERNS** (all rulings built, suite green; the concerns are judgment calls and one yield cost, listed below).

## Commits (on held-backlog-taper-markers, BASE 22f565a)
- ec90395 fix(taper): B4 step-1 break before set 1, G1 no encore on today's LLM path
- 6727429 fix(harness): report 3 gets a segues-changed tier (R1)
- 2bc84b1 docs(spec): B4 and G1 vetoes, D1 and two more documented limitations, R9 confirmed
- 26b4f4e test(taper): pin B4's hit as the earliest match of set 1's first song
- 9388d09 docs: taper-markers mutation record, fix round 2 (B4 and G1)

## What was built
- **B4 → (b).** New `taper._step1_break_before_set_1`, called in `decide_taper` right after a successful placement and before ruling (d)'s check. Decline reason: `veto: step-1 break before set 1`. A "numbered break" is a step-1 label change between two numbered labels (an encore boundary does not count). "Before the hit" means a change between tracks k and k+1 with k < h, where h is the 0-based hit. A change between h and h+1 is "at the hit" and stays owned. `_place_boundary`'s local `hit` became module-level `_hit` (same logic) so both can use it.
- **G → G1.** `decide_taper(..., today_reaches_llm: bool = False)`. When the taper has no recognised encore marker and that argument is true, it declines with `veto: no encore on today's LLM path`. This check runs after ruling (d)'s. `compute_gather` computes the predicate once as `today_llm = bool(canonical.items) and anchored is None and result.coverage < threshold`. Three places use it: `decide_taper`, the owned low-confidence flag, and the not-owned LLM branch's `elif`. The `elif` rewrite is equivalent to the old condition, because `anchor_note` is set exactly when anchoring succeeds. Replay is untouched, so these shows go back to needs-LLM because they are no longer owned.
- **Attribution.** Code comments and spec text say "(llama-db reading of operator ruling (d), 2026-10-22)". For R9, "pending llama-db confirmation" is now "confirmed by llama-db, 2026-10-22" at spec §2, taper.py :78 and taper.py :303.
- **Spec.**
  - §2 has two new veto bullets (G1 and B4), with the measured cases and the note on §7.
  - §4's ownership sentence now lists every veto.
  - Report 3's tier list now includes `segues changed`.
  - Documented limitations gains three entries: D1, verbatim, followed by a parenthetical (the figure is the pre-G1 measurement, G1 shrinks the population, and report 3's new tier lists these rows); the furthur-2012-07-08 closer-note fold; and the owned low-confidence hold (darkstarorchestra-2009-11-14, deadandcompany-2015-10-29, stringcheeseincident-2005-03-25, all delivered).
- **R1.**
  - `_tier` now has a `segues changed` tier, between `filler labels only` and `provenance only`. A row lands there when its labels are unchanged, the candidate is newly owned, and its segue changes differ from "before". "Before" is the base arm's `segue_changes`, or `[]` when the base is needs-LLM, matching how labels are compared.
  - Each row in the tier prints `segue changes: before … after …`.
  - It is counted in `TAPER_TIERS`, so it appears on the summary line.
- **Probe.** `taper_probe` passes a stored proxy for G1's predicate (details below).

## Tests added
- packages/llama/tests/test_taper.py:
  - test_step1_break_before_set_1_real_case_declines (stevekimockband-2000-03-31, verbatim description; tracks are the stored titles; step 1 is [6,13]; the flat step-1 counterpart is owned at (13,))
  - test_no_step1_break_before_set_1_stays_owned[names0..3]: leading filler, a pre-show song, and two cases of a break AT the hit
  - test_step1_break_just_before_the_hit_declines
  - test_an_encore_boundary_before_set_1_is_not_a_numbered_break
  - test_set_1_first_item_with_no_hit_uses_the_next_set_1_item
  - test_a_set_1_song_heard_only_after_set_1_does_not_widen_the_window
  - test_the_hit_is_the_earliest_match_of_set_1s_first_song
  - test_no_taper_encore_on_todays_llm_path_real_cases_decline[johnkadlecik-2013-06-22, newridersofthepurplesage-2006-04-08, radiators-2010-06-05, jackiegreene-2011-02-12]: verbatim excerpts; with the predicate on, the reason is G1; with it off, the show is owned
  - test_taper_encore_marked_stays_owned_on_todays_llm_path (the inverse)
- packages/llama/tests/test_stage_gather.py:
  - test_no_taper_encore_on_todays_llm_path_is_exactly_today (equal to the oracle, needs align_structure)
  - test_taper_encore_marked_stays_owned_on_todays_llm_path
  - test_g1_needs_canonical_items, test_g1_needs_no_anchoring, test_g1_needs_weak_step_one: each removes one conjunct
- scripts/test_replay_holds.py::test_taper_changes_segues_changed_tier
- scripts/test_taper_probe.py: test_stored_llm_path_proxy[4 params], test_library_passes_the_stored_proxy_for_g1
- Changed existing tests:
  - Gather stubs `_not_owned`, `spy` and `filler_only` accept the new keyword.
  - In `test_owned_low_confidence_uses_reader_coverage`, the "weak" case is on the LLM path, so under G1 it needs an encore marker. Its text gained `Encore:\nGolf`, and its coverage assertion went from 2/7 to 4/7.

## Suite
`./.venv/bin/python -m pytest -q` → **4469 passed, 1 skipped, 8 deselected** (BASE: 4443 passed). `llama.__file__` resolves inside the worktree.

`git diff main -- packages/llama/src/llama/setlist.py` is empty: **yes**. No Global Constraints protected name was edited.

## Gate / library deltas (`taper_probe.py gate --out ~/.llama-harness/piece2/gate6`; `delta --old gate5 --new gate6 --out ~/.llama-harness/piece2/delta5-6`)
- **Gate, in scope:** 77/186 → **76/186** owned (0.414 → 0.409). One flip: soulive-2001-12-15 (G1).
- **Gate, all yes/partial rows:** 2 newly not owned, soulive-2001-12-15 and thenewdeal-2005-04-29, both G1. 0 newly owned, 0 owned with changed labels.
- **Library:** 641 → **628** owned. 13 newly not owned, all `veto: no encore on today's LLM path`:
  - belafleckandtheflecktones-1996-11-09, bobbyleerodgers-2010-01-13, greatamericantaxi-2010-08-07, greenskybluegrass-2013-05-04, leftoversalmon-1997-10-31
  - melvinseals-2003-01-25, ryanadams-2006-12-04, soulive-2001-12-15, stevekimockband-2002-07-03, stevekimockband-2005-10-01
  - stevekimockband-2005-10-07, yondermountainstringband-2010-07-17, zero-2008-08-08
- **Library:** 0 newly owned, 0 owned with changed labels.
- **B4: 0 flips in the probe, and the probe cannot see it.** In the library, stevekimockband-2000-03-31 is skipped (operator structure override). In the gate, its bundle titles are the tautological `setlist` rung, so it is unplaced before B4 runs. B4 is visible only in the replay arms, where titles come from the kept title overrides.
- **G1's predicate cannot be computed offline by the probe**, which runs no gather and has no canonical, coverage or anchoring. It passes a stored proxy instead, `stored_llm_path(sj)`: the stored `structure.alignment == "llm"`, or a stored `low-confidence structure alignment` flag. The proxy is true on **647 library rows** and **76 gate rows**. G1 declined 13 of the library rows and 2 of the gate rows.
- **The 4 named shows do not appear as flips.** The probe's `today_sets` are the stored labels, which still carry the stored LLM encore. So ruling (d) already declined them at gate5, and it still does: their reason remains `veto: today's encore`, because (d) runs before G1.
- The orchestrator's replay re-run measures the real predicate.

## Mutation rows added (docs/superpowers/2026-10-22-taper-set-markers-sdd/mutation.md, "Fix round 2")
- **Method:** each mutant was a one-line diff in its own `git archive 26b4f4e` copy, run from an empty cwd with PYTHONPATH shadowing and a fresh PYTHONPYCACHEPREFIX. Imports were asserted to come from the copy, and predictions were logged in t9-fix2.log before the run. 795 tests.
- **Sentinels:** S0 had 0 red. S1 had 91 red. S2 turned exactly the 6 tests predicted for G1a red.
- **B4a–B4f:** rule off, break-at-hit counted, encore-boundary conjunct dropped, window unrestricted, no fallback, latest hit. All caught. B4b has 3 undeclared extra reds; each is a "break right after the hit" case, read.
- **G1a–G1g:** rule off, has_encore conjunct dropped, predicate conjunct dropped, gather passes False, and G1's argument minus canonical / anchoring / coverage. All caught. G1g has 3 undeclared extras in replay/reapply (the `_PLACING` no-encore owned text), read.
- **Total: 13/13 caught**, 0 survived, 0 hangs.

## Concerns / judgment calls
- **G1 has a yield cost the pre-screens had counted as wins** (flagged; the ruling decides it). Among the 13 library flips:
  - soulive-2001-12-15 and greenskybluegrass-2013-05-04 are pre3-llm C4 "better than stored" rows, where the LLM shipped one set and the taper marks Set 1 / Set 2. They go back to needs-LLM, and that improvement is lost.
  - stevekimockband-2005-10-07 was one of the 4 real gained segues.
  - leftoversalmon-1997-10-31 (12 lost segues, D1) also returns to the LLM.
- My call: `today_reaches_llm` defaults to False, so the probe and the many existing unit-test callers keep working. Only gather passes the real predicate, and G1d pins that wiring. A caller that forgets the argument gets the off-path behaviour.
- My call: B4's hit is the earliest track at or before set 1's placed boundary that matches set 1's first song item. When that item has no such hit, the next set-1 item's earliest hit stands in. When nothing hits, the veto does not fire, although placement guarantees set 1's last song has a hit. The hit is the earliest match and is restricted to the set-1 window; tests and B4d/B4f pin both.
- My call: veto order is placement → B4 → (d) → G1. A placed show therefore reports the most specific step-1 reason, and unplaced rows keep their placement reasons. G1 does not depend on placement.
- My call: the not-owned LLM branch now reads the same `today_llm` variable (an equivalent refactor; "one predicate"). Mutants y1–y3 of the earlier round targeted the owned flag's former inline expression. They were not re-run against the shared form, and the mutation record says so.
- My call: the R1 tier applies only where the candidate is newly owned (the same ownership gate as `provenance only`). A not-owned row with segue drift stays unlisted, as before.
- My call: the G1 real-case unit tests use a stand-in step 1, the stored labels with the stored (LLM) encore relabelled into set 2. pre3-moved measured that step 1 has no encore on these shows; I did not re-measure step 1 for them.
- The D1 limitation is copied verbatim, then followed by the parenthetical that says the figure predates G1.
