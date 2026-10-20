# Checkpoint G pre-screen — handback (Opus, read-only)

prescreen.md: /Users/shawn/.llama-harness/cmp-G-held/prescreen.md
sha256: 4e7e7aa465c287cf904e43aaefff123a3ee647fdd813527f2564b00834026ccd

## SUMMARY

**DROP list — every apply row I flag (13).** "B–F approved?" says whether the THING I flag was approved; on the last 7 the show's slice clear was approved, but not this defect, so the operator decides.

| slug | list | reason (one line) | B–F approved? |
|---|---|---|---|
| radiators-1984-09-07 | predicted (fresh) | 3 sets in description, 1 set in show.json | no |
| philleshandfriends-2008-11-18 | predicted (fresh) | set 2 merged into set 1; encore mislabelled; title '(Set 2) Born Cross-Eyed >' | no |
| darkstarorchestra-2004-11-14 | predicted (fresh) | set 1 labelled set 2, Playin reprise as encore; timestamp titles | no |
| smashingpumpkins-2012-05-26 | predicted (fresh) | track 12 '1979' ships as 'The Everlasting Gaze'; '- ' title prefixes | no |
| stringcheeseincident-2005-07-19 | predicted (fresh) | mojibake in 2 titles ('Enc: Bend Down LowÃÂ¹') (cosmetic) | no |
| larrykeel-2007-08-26 | predicted (fresh) | 4 tracks ship titled 'Unknown tune'/'Unknown song' | no |
| ratdog-2007-11-17 | predicted (fresh) | set 1 = 16 tracks, set 2 = 1 (wrong 'Dark Star' occurrence anchored) | C (venue clear only) |
| philleshandfriends-2008-07-04 | predicted (fresh) | set 2 missing (jerrybase CSV row absent) | C (1c venue only) |
| joerussosalmostdead-2018-02-18 | predicted (fresh) | encore labelled set 3 (moe-2002-06-22 precedent) | E (4a only) |
| umphreysmcgee-2006-11-16 | predicted (fresh) | 'E:' encore labelled set 3 (moe-2002-06-22 precedent) | B (2a track 22 only) |
| moe-2006-01-19 | predicted (fresh) | track 19 title carries a leaked checksum line | B (2a track 4 only) |
| northmississippiallstars-2010-03-11 | predicted (fresh) | track 23 ships as 'unknown_title' | B (2a track 12 only) |
| philleshandfriends-2005-07-16 | predicted (fresh) | mojibake in 2 titles ('Uncle JohnÃÂs Band') (cosmetic) | C (1c venue only) |

No hand-check-list row is flagged (all 43 remaining rows routine). The first 6 drops have NO B–F row at all: they are briefing-guard holds that get a fresh brief by the spec's slice-3/6 rule (not a Tier-1 suppression; base arm already listed them needs-brief), and the show the fresh brief would describe is wrong.
**Pilot (10): all routine — none dropped.** furthur-2011-06-03, umphreysmcgee-2004-10-19, railroadearth-2008-09-20, elliottsmith-2000-11-03, ryanadams-2008-11-16, gratefuldead-1979-11-25, joerussosalmostdead-2018-05-04, furthur-2010-02-27, littlefeat-2012-09-03 (reuse), ryanadams-2007-05-16 (reuse). Substitutes if needed (next routine rows in sha1(slug) order): gratefuldead-1982-05-22, umphreysmcgee-2002-10-04, gratefuldead-1972-03-23, railroadearth-2005-04-16 (reuse).
**Counts (G2 mechanical drop; rows on predicted_list minus the 11 rejected-D/E slugs; multi-line row = one row; "approved" = row's stripped text verbatim in approved-[B-F].txt):**
- hand_check_sample: 18 on listed shows / 0 dropped as approved / 18 remaining (2 rows on rejected slugs excluded: gratefuldead-1970-06-24-e2, minutemen-1983-12-16).
- closest_calls: 50 / 25 / 25 (dropped: 23 slice-4a + 2 slice-4b rows, verbatim in approved-E; remaining: 9 slice-1 1c + 16 slice-2a). 7 rows on rejected slugs excluded; 449 rows are on shows not in the apply list.
- title_sources: 24 / 24 / 0 (1 row on rejected minutemen-1983-12-16; 7 rows on structure-changed shows, not in predicted_list).
- structure_changed: 11 listed, 0 on predicted_list, not pre-screened. (The first pass 20/0/20, 65/25/40, 32/31/1 counted rejected and structure-changed slugs; the differences are exactly those.)
- Coverage: 144 apply rows (27 reuse − 5 rejected-D = 22 reuse; 128 needs-brief − 6 rejected-E = 122). Every lost flag on 128 rows is attributed to a slug-specific B–F row (C 54, E 25, B 23, D 22, F 4); the other 16 (briefing family, fresh brief) to the spec's fresh-brief rule (2 of them also carry a D guard row). Every cand note and title change on the 144 is verbatim in approved-[B-F]. 0 rows have a flag left.

**Exposure:** cmp-G-held/packaged_exposure.txt: 0 entries. cmp-G-all: 13 shipped-field changes + 9 newly-held + 5 clean-changed (overlapping), all on packaged/delivered shows, NONE on predicted/pilot/structure_changed lists. Each is a change approved at B–F: B 2b exposure (eotoband-2007-10-09, gratefuldead-1977-03-18, newmastersounds-2018-05-08, blitzentrapper-2013-11-12, motherhips-2013-06-21); C 1d/swap narrowing (beneventorusso-2005-08-27, gratefuldead-1978-09-16, ryanadams-2007-06-06, smashingpumpkins-1997-06-28); E 4c (littlefeat-1970-01-01); F slice5 clean-changed (furthur-2010-02-20, gratefuldead-1982-09-05, gratefuldead-1983-04-09). The other 3 newly-held (aquariumrescueunit-2005-01-08, gratefuldead-1971-04-29, gratefuldead-1977-05-09) are base drift (the base arm raises the same flag): not Tier 1.
Also noted, NOT flagged (minor, pre-existing): encore left in the last numbered set on 6 apply rows (darkstarorchestra-2007-08-06, railroadearth-2007-04-25, thebrew-2008-10-31, railroadearth-2009-11-28, railroadearth-2010-07-01, umphreysmcgee-2005-04-16); filler tracks shipped inside an encore on darkstarorchestra-2005-06-06 and darkstarorchestra-2010-04-23. Say if you want these dropped too (same reasoning as F's rejected encore releases).
Method: per-show read of show.json, the cached description, research.md (4a/fresh-brief rows), briefing.json (fresh-brief rows), setlist.fm cache and sibling md_ caches (2a). Structure was checked on all 144 by script (description set markers vs show sets, short final sets, encore-as-set, odd titles) and by hand on every jerrybase-anchored apply row (56). Nothing was written outside this file and $D/cpG-prescreen/.


Nothing changed in any checkout (worktree git status clean); ~/.llama read only; no subagents; files written: /Users/shawn/.llama-harness/cmp-G-held/prescreen.md and $D/cpG-prescreen/{cpG-prescreen.log,handback.md,done}. Scratch analysis scripts only under the session scratchpad.
