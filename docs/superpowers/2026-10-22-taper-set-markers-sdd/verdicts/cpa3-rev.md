# cpa3-rev: independent review of 5da667b (set-like veto), Checkpoint A2

**Verdict: NO NEW DEFECT CLASS, NO LOST ENCORE.** Status: DONE. No commits; read-only on repo files.

I found one latent miss of the targeted class and five minor issues. None changes a gate4 row.

## Findings
1. **Minor: the veto misses a set token split across two items** (`taper.py:541-553`, `_set_like`; the split is pre-existing and comes from `setlist._INLINE_MARKER`).
   - **Trigger.** An ordinal header (`First/Second/Third Set`) followed by a line numbered `1-`/`2-`/`3-` (or `N:`). The joined-line lookahead `set\s*[123]\s*(?::|-\s)` cuts the line before `Set`, so the header becomes two items, `'Third'` and `'Set'`. Neither item matches `_SET_LIKE`.
   - **Constructed case on HEAD.** `Set One:\n1- Bertha\n2- Let It Grow\nSet Two:\n1- Scarlet Begonias\n2- Fire On The Mountain\nThird Set\n1- Truckin\n2- Morning Dew` with today `1 1 2 2 3 3` gives asserts=True, set_like=False, OWNED `1 1 2 2 2 2`. Set 3 is silently merged into set 2, which is exactly the class the ruling targets.
   - **Corpus.** A scan of all 26,777 cached description/notes texts finds 3 asserting texts with a bare `Set` item: DSO2012-05-19, jg2010-07-07, jkb2023-04-16. All three are set 1 at the top of the text, so they are harmless. darkstarorchestra-2012-05-19 is owned with labels identical to stored. Cost today: 0 rows.
   - **Possible fix.** Also test `_SET_LIKE` on `prev + " " + item`, or treat a decoration-stripped bare `Set` item as set-like. Either would also flip DSO-2012-05-19, which is harmless collateral. Alternatively, record it as a known gap.
2. **Minor: test gaps (mutants run in a `git archive` scratch copy; import proven to resolve to the copy).**
   - Caught as predicted:
     - drop the same-set check: 1 fail, `[Set 1 con't]`;
     - veto only without an encore: 2 fail;
     - no veto: 18 fail.
   - **Survive (309 pass):**
     - (M1) only the first `_SET_LIKE` match per item is checked, so an exempt `Set 2 con't` followed by another token in the same item goes unchecked;
     - (M2) `_CONT_AFTER.match` changed to `.search`;
     - (M6) set-3 items skipped. No test puts a token in a set-3 item. The only real one is tealeafgreen-2002-11-21's `Entire 3rd set …`, a reason-only gate row.
   - A test for M6 and one for M1 would close these.
3. **Minor: the con't exemption is attributed to the wrong ruling.**
   - Where: spec line 313-315, and `taper.py:69-75` (module docstring).
   - Problem: the whole sentence, exemption included, is attributed "(llama-db ruling, Checkpoint A2)". The exemption is orchestrator ruling R9 (orch-r1/ledger.md), which is still pending llama-db overrule.
   - Fix: attribute the carve-out to R9 / "my call".
4. **Minor: docstring wording** (`taper.py:71` and `taper.py:543`). They say the encore's items "are the notes after the encore songs". In fact the encore's items are the encore songs plus any notes, and the skip skips both. The behaviour is per the ruling; only the description is wrong.
5. **Minor: reporting errors** in the implementer's handback, repeated in the ledger's 11:51:10 entry.
   - The reason-only changes number **9, not 10**: gate 3 and library 6. The handback says "library (7)" but lists 6.
   - umphreysmcgee-2002-12-31 is one of the "7 post-encore-notes rows", but its encore items carry no `_SET_LIKE` token (only "between two of the sets"). So 6 of the 7 actually exercise the encore skip. All 7 are owned.
6. **Minor, theoretical: `_CONT_AFTER` exempts too much** (`taper.py:297`).
   - Any word starting `cont` is exempt (`Set 2 Control…`).
   - Cache scan: all ~50 exempted items are real same-set continuations (`con't`, `cont...`, `continues`, `con't'd`), with 0 false exemptions.

## Q1: defect class
**(a) Sweep of owned rows' numbered-set items.** I re-ran the reader on all 642 owned library rows and 81 owned gate rows (`$S/items.json`).
- Patterns swept: `set`/`sets`/`set\s*[-#:.]N`/`sN`/`disc`/`cd N`/`half`/`part`/`pt`/`break`/`intermission`/ordinals/`acoustic`/`electric`/`show`/`tweener`/`dj set`.
- Every `_SET_LIKE` hit in an owned row is either:
  - a same-set con't item: clubdelf, discobiscuits ×3, railroadearth ×2, stuallenandmarshotel ×2, thegourds; or
  - a post-encore note: davidnelsonband-2009-06-27, gd1993-09-22, philleshandfriends-2006-07-03, tedeschitrucksband-2020-02-21 and 2021-10-08, ymsb-2008-10-11.
- The other hits are song titles: `Half Step`, `WRS Part I`, `The Sun Also Sets`, `Part Of Me`, `Shoot First`. Or they are disc labels (`CD 2`, `CD 1 [75:06]`) or notes.
- Unnumbered set names that stay owned:
  - themotet-2011-10-29 `DJ Set:`: labels identical to stored.
  - nrps-2007-12-31 (gate) `Tweener Set - Skarecrow`: the gate's known miss, unchanged from gate3. The taper equals today's alignment (a_breaks [15]). The operator fixed it by override and exclusion.
  - Neither is a numbered-set token, so out of the ruling's scope.
- Only shape the veto misses: finding 1. It is latent, with 0 structure-changing instances.

**(b) Declines beyond the accepted collateral.** None.
- Exactly the 6 named rows flip.
- The 9 reason-only rows were already not owned (unplaced). Each triggering item is genuine set-naming text:
  - `Set 1 Acoustic Cindy Poris Opened` (in set 2);
  - `Set2 patches: MSC`;
  - `set 1 pt. 1`/`Set2 Pt.3`;
  - `Set One @ (8:16PM - 9:18PM):`;
  - `Set One (Acoustic)`;
  - `Entire 3rd set…`;
  - `Set two featured Trey…`;
  - `I did not cut the second set…`;
  - `Set I (Sticky Fingers): Brown Sugar`.
- No false positive among them.

**(c) The con't exemption is sound.** An item labelled N can only carry that label after a recognised set-N header, so a same-set continuation item states no new structure.
- The wrong-set form (`Set 1 con't` in set 2) still vetoes, and a test pins it.
- A cache-wide scan finds no exempted item that is not a true continuation.
- It narrows the literal ruling: own-more by 9 rows, all measured harmless. That is in line with the ruling's intent ("unrecognised set-naming that drops structure"), but it is R9's call, not llama-db's (finding 3).

**(d) The `_SET_LIKE` regex.**
- `\b` on the left plus `(?!\w)` on the right inside `_SET_TOKEN`. `Sunset 1`, `Reset 2`, `Set In Stone` and `Sets 1 and 2` are correctly negative.
- False positives in the corpus: none (all 15 vetoed rows checked by hand above).
- False negatives:
  - `Set-2`, `set #2` and `set: 2` are not matched, with 0 instances in owned items or asserting cache texts;
  - the split shape in finding 1.
- Non-numbered `Set Break`/`Setbreak` items (≈20 cache texts, all at a set's end) are not matched, which is correct: they state no new structure.

## Q2: lost encore
- **Library gate4, 642 owned:**
  - 0 rows have an encore in stored but none in the taper's labels;
  - 0 rows have labels that changed against gate3;
  - 0 rows whose encore was lost against gate3.
- **Gate4, 81 owned** (recomputed from bundles): 0 lost encores against pre-adjudication today, and 0 with fewer encore tracks. Rows are identical to gate3.
- **Pre-existing, not this delta:** 12 library rows have fewer encore tracks than stored, but still have an encore (e.g. philleshandfriends-2006-07-03 has 4→1, darkstarorchestra-2017-02-10 has 13→2). They are the "songs moved" tier and are byte-identical in gate3.

## Q3: delta, verified from the jsonl files
- **Library** (3983 rows, same slug set):
  - 6 flip owned→not-owned, all `veto: set-like text`. They are exactly gratefuldead-1974-07-19, localh-2004-12-31, motherhips-1995-08-06, neworleanssuspects-2012-08-02, ryanadams-2008-01-21, thedead-2009-04-25.
  - 0 newly owned; 0 other field changes; owned count 648→642.
- **Gate** (339 rows): 0 flips; owned 81 both times (in-scope 77/186).
- **Reason-only:** 9, not 10. Gate: joerussosalmostdead-2019-03-03, strangefolk-2002-09-01, tealeafgreen-2002-11-21 (all three are skipped by operator override in the library pass). Library: furthur-2010-07-02, gratefuldead-1978-11-20, gratefuldead-1981-10-16, karldensonstinyuniverse-2011-10-28, soundtribesector9-2003-06-13, tedeschitrucksband-2019-08-24.
- **All 7 post-encore-notes rows are still owned.** The 9 con't rows (8 library + railroadearth-2005-03-17 gate), thedead-2009-05-07 and the JRAD rows are also still owned.

## Q4: code and test quality
- **Correctness.**
  - `_set_like` is correct.
  - Placement after the encore vetoes keeps the old reasons stable. Placement before `place_taper_structure` means the veto applies with a marked encore (thedead-2009-04-25 has `E:`).
  - `TaperText.set_like` defaults to False.
  - The only consumers of reasons are in `scripts/taper_probe.py`, which is unaffected.
- **Tests.** Real-case excerpts are embedded verbatim. The 309 taper tests pass on HEAD. See finding 2 for the gaps.
- **Protected names.** None appears on a +/- line of the diff (grep rc=1).
- **setlist.py.** `git diff main -- packages/llama/src/llama/setlist.py` is empty (0 lines).
- **Spec.** The added spec sentence matches the code, apart from the attribution (finding 3).

## Evidence files
Scratch dir: `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-taper-markers/0443a042-e8ee-4093-a603-2fbd14e62179/scratchpad/cpa3-rev/`
- `items.json` and `sweep_hits.txt`/`sweep2.txt` (item sweeps);
- `cachescan.py`/`cachescan2.py` (cache-wide scans);
- `gateenc.py` (gate encore check);
- `mut.py` and `copy/` (mutants).

The mutant and scan output is also in `$D/cpa3-rev/cpa3-rev.log`.
