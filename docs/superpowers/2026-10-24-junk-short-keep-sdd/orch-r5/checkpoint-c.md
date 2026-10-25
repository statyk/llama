CHECKPOINT C (piece 4, junk short-keep): branch held-backlog-junk-filter at b8fe321 (code 65be006). STOPPED for your go; Task 23 not started.

## Where it stands
- Tasks 0-21 are complete and reviewed. The final whole-branch review is done. Its fix wave ran as FW1 (I-1 + I-2 per Shawn's rulings, 1 fix round, re-review clean) then FW2 (items 3-15 + N-1/N-2/m-1; Opus review Approved, 0 Critical/Important, 4 Minors deferred).
- Verdict pins (sha256 prefix):
  - final review `.superpowers/sdd/junk-short-keep/tfin-rev/handback.md` 9a8689679aada19b
  - FW1 re-review `tfw1-rr1/handback.md` 1b21d352396f8723
  - FW2 review `tfw2-rev2/handback.md` 2c138ad4a6fcc574
  - segue investigation `t22-seg/handback.md` 6f75a7004e789a13
- Evidence: docs/superpowers/2026-10-23-junk-short-keep-evidence/acceptance.md, section "Checkpoint C" (commits 0f2e7d8, b8fe321).

## Task 22 results (at 65be006)
- **Suite:** `./.venv/bin/python -m pytest -q -p no:cacheprovider` gives 5442 passed, 1 skipped, 8 deselected, rc 0. The 26 warnings are the pre-existing py3.14 fork() DeprecationWarnings, the same count since the baseline.
- **Arms:** cand-c2 (sha256 f502c0c5…) against the Checkpoint A base. Same config fingerprint, 0 rekey errors.
  - compare `--no-repro-gate` (your 2026-10-24 ruling) is rc 0, 127/148 as before.
  - arms: **BLOCKS MERGE 0**; changed 1545, files added 2624, added 34, cleared 21.
  - Tallies: clean 1653, clean-changed 1308, needs-llm 654, newly-held 220, still-held 135.
- **Fix-wave delta:** cand-c2 differs from the pre-fix-wave arm on exactly the 23 de-doubled shows, and nothing else.
  - On the kept files: 0 title changes, 0 title-source changes, 0 set-label changes. Every break is on the same song, and play order is kept on 23/23.
  - Cost: 13 fresh briefs at apply (12 GD shows lose briefing reuse, 1989-07-18 goes none to fresh; sci gains reuse).
- **Migration dry run** (read-only, real library): 606 to rekey, 0 refused, 0 already migrated, 3377 without positional keys.
  - Totals 3,203 / 427 / 365, equal to spec 4.3.
  - The process check printed "none". Nothing was written (no lock file, nothing newer under ~/.llama).
- **Mutation record:** docs/superpowers/2026-10-24-junk-short-keep-sdd/mutation.md (Task 21): 21 mutants, 20 caught, (j) a ruled plan-prediction error. The fix waves added 18 scratch mutants, all red as predicted.

## New finding: segue marks move on 9 de-doubled GD shows (read-only Opus investigation, t22-seg)
- **Cause.** `gather.build_canonical` picks the description that supplies segue marks (the `blend_segues` donor) by closeness to `len(kept)`. The doubled track count steered that pick.
  - This is a pre-existing selection rule. FW1's rule is not at fault.
  - Proven: no-op'ing only the dedupe reproduces the old segues exactly, 18/18.
- **Net effect: the de-doubled result is better.** Of 33 song-level marks that change, 18 are right, 9 wrong, 6 unclear. Agreement with the description majority: 153 → 156 of 179.
  - The doubled arm's "right" marks sat on the wrong transition (Bird Song > its own _vbr twin).
- **Worst case: gratefuldead-1988-06-23 (delivered).** It loses 5 real marks (He's Gone > Drums > Space > Miracle >, Watchtower >). The new donor is the chosen tape's description, which has no `>` at all.
- **Fix (A), one line in gather, not built.** It ranks the donor only among descriptions that carry a segue.
  - Tested in memory: it restores 4 of the 5 and changes nothing on the other 8 shows (agreement 160/179).
  - Library-wide effect unmeasured.

## Questions for Shawn (each with my recommendation)
1. **Flip the copy preference to _vbr?** If flipped, truncated songs air: in all 13 library / 48 cache duration-mismatched pairs the truncated copy is the _vbr (e.g. Sugaree 16 s vs 725 s).
   - RECOMMEND: keep plain X.mp3, no flip. If a flip is ever wanted, add a duration tie-break or refusal first.
2. **Copy pick in the 23 non-_vbr duplicate groups.** Today the rule is "the copy named after its original". It is also the newest file in 23/23, so a newest-date rule picks the same files today.
   - RECOMMEND: keep the current rule.
3. **2 of the 20 recording re-selections orphan operator overrides:** gratefuldead-1970-05-06 and gratefuldead-1985-11-10. On 1985-11-10, set_breaks/encore_after will hit the dangling refusal loudly with its `llama fix --clear-…` route; excludes only warn.
   - RECOMMEND: let the bulk apply surface them, then clear and re-set by hand on the new recording (2 shows).
4. **The 20 GD dates whose selected recording changes** (`~/.llama-harness/piece4/fw1/m3_changed-r1.json`) re-gather and re-research in the bulk apply. That is LLM spend for 20 shows.
   - RECOMMEND: accept. They move off recordings that were scored on doubled track counts.
5. **Stale _vbr excludes** on the 5 hand-repaired shows (sci 1999-12-31, jrad, ttb2022, gd1970-05-06, gd1985-11-10). They now coincide with the automatic drop and apply as operator-excluded.
   - RECOMMEND: leave them (harmless). Clearing them is optional tidying.
6. **Titles/structure on the 23 de-doubled shows** (open since r4): now MEASURED, unchanged (above). The open part is the segue donor.
   - RECOMMEND: build fix (A) in this branch as one small task before merge: Opus implementer, Opus review, a whole-library replay arm diffed against cand-c2, and a stop if it moves shows I can't explain. Reason: the bulk apply right after this branch would re-ship 1988-06-23 with no segues.
   - Leave classes B (run-on descriptions, parse_setlist's documented merge) and C (`Space` vs `Jam` in blend_segues) for separate changes.
   - Alternative: merge as is, since net segues are better, and take (A) before the bulk apply.
7. **Task 20 Minor 3.** `--restore` lists station manifests that emcee re-voiced in place since the snapshot as "re-delivered" (an mtime test, spec-conformant). That advice could prompt an unneeded `--replace-voiced`.
   - RECOMMEND: no code change; one runbook line in Task 23 ("a re-voiced show listed here needs no --replace-voiced").
8. **FW2 concerns, all in the refuse-more direction** (costs a fresh brief, never a wrong reuse):
   - "lists no" fires on 49 rows vs 15b's 96;
   - "lacks" / "not recorded" over-refuse;
   - `--restore` warns twice, exit 0.
   - RECOMMEND: accept as is.
9. **(new) FW2 review Minors.**
   - M1: two apostrophe look-alikes (U+02BB, U+02B9) are not folded by the briefing gate. A free, refuse-only fix.
     RECOMMEND: add both to `_APOSTROPHES`, folded into the fix (A) task if you approve 6.
   - M2: a pair whose copies are BOTH excluded counts twice in its format's running time. Latent: multi-format only, 0 library shows.
     RECOMMEND: leave, note in the record.

## What I need from you
- A go or no-go on fix (A), with M1 riding along (Q6, Q9).
- Any overrule of Q1-Q5, Q7-Q8.
- Then the go for Task 23 (CLAUDE.md + the SDD record; its batch (a)-(j) is ready).
- Merge, push and tag stay yours.
