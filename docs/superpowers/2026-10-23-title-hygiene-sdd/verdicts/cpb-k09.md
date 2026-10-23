# cpb-k09 handback (class K, stratum delivered_changes, 15 shows)

Rows: ~/.llama-harness/piece3/accept/handcheck/cpb-k09/rows.jsonl

Track verdicts (49 tracks): right 47, right-partial 1, wrong 1, cant-tell 0.
By path: C1 1 right; C2 17 right (incl. #10-17 of ttb-2020, 2019 swap pair); unattributed 2 (motet #1 right; umg-2005 #12 wrong);
tags/4 1 right (u-melt #2); S 1 right (um-1998 #10); +5 18 tracks: 17 right, 1 right-partial.
(All C2 sibling-format tracks were right; the FLAC tag matched the taper's description every time.)

Show verdicts: all-right 14, some-wrong-not-shift 1, shifted 0, cant-tell 0.

Wrong / partial tracks:
- umphreysmcgee-2005-11-12 #12 WRONG: candidate is the bare filename `umg2005-11-12d2t03.mp3` (unresolved); correct "Wife Soup" (871s ~ sibling 840s). Today shipped "Wife Soup" correctly, so this is a regression, but base clean -> cand newly-held, so it is held, not shipped silently. The tape's neighbour tags also look off (d2t04 522s tagged "Wife Soup," probably Let Me Go Home); not judged further.
- zentricksters-2002-12-31 #19 RIGHT-PARTIAL: +5 turned "Banks of the Ohio (actually d2t10)" into "Banks of the Ohio (actually )". Song right, dangling empty parenthetical. Show is needs-llm both arms.

Shifted shows: none in the candidate. Notably, today's title set was shifted/damaged in several and the change repairs it.

Instructive examples:
1. tedeschitrucksband-2020-01-15 #10-17: mp3 tags were shifted one early from track 10 (mp3 lacked Made Up Mind, junk tag "(Willie Nelson cover)"), so today shipped eight wrong titles. FLAC tags (cache md) + description order give the correct set, incl. the encore/Bound for Glory order (Earhole 390s, Bound for Glory 934s).
2. tedeschitrucksband-2019-02-15 #14/#15: mp3 tags swapped The Storm / Part of Me; FLAC + description + durations (267s vs 599s) fix it.
3. themotet-2013-01-07 #1: today's cleaner damaged the real title "1 + 1 + 1=3" to "+ 1 + 1=3"; the new path keeps it.
4. u-melt-2008-08-29 #2: "415" restored (today a duplicate "Question Matters"); sibling "415 >" 878s decisive.
5. umphreysmcgee-1998-04-15: +5 stripped 17 mm:ss prefixes safely (each equals the file duration); only damage seen in +5 is zentricksters #19.

Pattern: C1/C2 recovery was right in every case here; the one regression (umg-2005 #12) is a hold, and the only +5 defect is a strip inside a parenthetical.
