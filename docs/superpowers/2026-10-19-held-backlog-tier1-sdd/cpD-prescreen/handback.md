## SUMMARY

Arms: base 0038589 / prev b6f353a (cp-C2) / cand b9ae699 (cp-D), same sitting. Slice 3 alone moves 34 stored_brief_guard rows (3a 11, 3b 15, 3c 8); 32 clear fully, 2 partly. 27 held shows now `clears` with the stored briefing shipped by **reuse** (the only reuse outcome among held shows; 2,037 non-held `clean` reuses are not held and not listed). The other 5 cleared rows stay needs-llm.

| # | Check | Result | Rows | Flagged | Routine | Sample |
|---|---|---|---|---|---|---|
| 1 | Reused briefings vs show.json | PASS with 5 flags for the operator | 27 | 5 | 22 | 20 |
| 2 | Zero newly firing on clean briefings | **PASS** (base 0, cand 0; 2,400 clean stay clean, no flag added anywhere) | - | - | - | - |
| 3 | Suppressed set-count/ordinal matches | PASS (no detection lost on this library) | 21 | 1 | 20 | 20 |
| 4 | Remaining holds | 23 rows: 5 TRUE, 18 FALSE (17 misfires slice 3 does not cover + moe, a show.json defect) | 23 | 6 | 17 | 17 |
| 5 | stored_brief_guard differences | PASS: every removal is mechanically right; 3 flags on prose | 34 | 3 | 31 | 20 |

**Flagged rows.**
- L1 `smashingpumpkins-1996-04-27`: unhedged "A second encore of 'Bodies', 'Silverfuck' and 'Farewell and Goodnight'..." (show.json has one encore set).
- L1+L5 `wacobrothers-2005-12-22`: "The first encore opens ..." / "The second encore follows ..." (all 29 tracks are set 1; support is only the track titles "encore", "encore #2").
- L1+L5 `warrenzevon-1988-11-30`: two encores, attributed to "the complete 2020 transfer" (all set 1).
- L1+L5 `thewaybacks-2006-04-29`: "Research describes "Like A Rolling Stone" as an encore." (all set 1).
- L1 `deadandcompany-2015-11-20`: attributed segue Eyes > Let It Grow > Terrapin (show.json marks no segues).
- L3 `furthur-2011-02-12`: classed negation ("expected"), but "had expected a spacier second set" is not a negation. Benign: the structure has 2 sets.
- L4 TRUE: `darkstarorchestra-2004-11-14` (empty per_set), `derektrucksband-1999-02-13` ("44 Blues"), `larrykeel-2007-08-26` (listener IDs of "Unknown tune"), `radiators-1984-09-07` (an attendee's "three sets" vs 1), `strangefolk-2002-09-01` ("Lucy Down" is not on the tape). And `moe-2002-06-22`: the briefing's "two sets and an encore" is right; show.json labels the "E:" tracks as set 3.

**Evidence and recommendation: approve slice 3.** Every flag the slice removes is one the spec intends to remove, and each removal checks out against show.json. Nothing newly fires. Every suppressed phrase that is about this show is consistent with its structure, so 3c costs no detection here. The 5 list-1 flags are prose claims the guard never checked: encore and segue wording outside per_set keys and mentioned_songs. They predate slice 3 and slice 3 did not create them, but 3 of them (waco, waybacks, warren) become reusable only because 3a dropped the empty encore key while the prose still talks about encores. The operator should decide whether those 5 ship by reuse (all but smashingpumpkins-1996 are hedged or have a caution) or get a fresh brief. Note for slice 6: 9 of the 27 stored briefing.md files still carry the empty "## Encore" heading. Spec reuse step 3 re-renders briefing.md, so that re-render is load-bearing.

**Product file:** /Users/shawn/.llama-harness/cmp-D-all/prescreen.md
**shasum -a 256:** `b8965457825e94b5c5e5b5107fa3b97193ee76de797a7f14f33675936db3b242  /Users/shawn/.llama-harness/cmp-D-all/prescreen.md`

Read-only run: no code, git or ~/.llama changes. Code was imported only from a git-archive snapshot of tier1-cp-D (`/var/folders/yn/jlwxryrj1ds7jpvw931jk1jm0000gn/T/cpD-snap-Ia7ISi`, now deleted). Log: /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1/cpD-prescreen/cpD-prescreen.log
