# accept-d handback

## Status: DONE_WITH_CONCERNS
I committed the rewritten acceptance.md. The concern: one added hold, the same show in both views, is UNEXPLAINED, and the brief's own explanation for it is contradicted by the arm data.

- **Commit:** cc23df5 `docs(title_hygiene): acceptance at c49cdd1 with the (d) justification table`. It changes one file and is docs-only; the body ends with the two required trailer lines.
- **File:** docs/superpowers/2026-10-22-title-hygiene-evidence/acceptance.md
- **sha256:** 5c03b3b6c9b4e3b2d0489e68717919a8ac786ec0022d9d5bcb611472f2ce431a
- **Tree:** clean after the commit. Nothing outside docs/ was touched, and nothing was written under ~/.llama or ~/.llama-harness. I ran no LLM calls and no llama commands.

## (d) table row counts
The counts match the brief's 14 and 15.
- **As-is: 14 rows.**
  - 10 stop a wrong, shifted or junk title: buttholesurfers, DSO-2015, PLF-2007, railroadearth, signalpath, soulive, stringcheese, umphreys, charliehunter and dumpstaphunk. For soulive and stringcheese, the duplicate stopped is cant-tell.
  - 3 are an accepted cost: DSO-2004 under Q1, lotus under B3/B7, stevekimockband under Q1.
  - 1 is UNEXPLAINED.
- **Fresh-get: 15 rows.**
  - 11 stop a wrong, shifted or junk title: the same list without charliehunter, plus derektrucksband-2007-05-25 and steepcanyonrangers.
  - 3 are an accepted cost: DSO-2004 under Q1, lotus under B3/B7, gratefuldead-1989-07-19 under Q1.
  - 1 is UNEXPLAINED.

## UNEXPLAINED rows
**kinggizzardandthelizardwizard-2022-10-22**, in both views. The arm data:
- **No D fill.** In both cand arms, `cascade.d_fills` is `[]` and `desc_position` is 0.
- **The only change is two C2 replacements:**
  - #6 'Organ Farmer' becomes 'Her and I (part one)';
  - #13 'Altered Beast IV' becomes 'Evil Death Roll (part one)'.
- **Both new titles are taper-backed.** They come from the FLAC tags and the item's own numbered list. The description says "(part one) is added for where I mistracked the songs" (cache `md_kglw2022-10-22.ScheopsMK41.Flac24.json`).
- **The hold is the LLM alignment branch.** The arm has `needs_llm: align_structure` and the flag L. The stored base `show.json` has coverage 0.923 (12/13, setlist.fm). That deterministic coverage now falls under 0.8 is my inference from the `needs_llm` record; I did not compute it.
- **Why I could not justify it.** The hold stops no wrong title, because C2 already replaced the mistracked labels. Spec Goal 3 says C2 "adds no holds", and no ruling accepts a C2-caused hold.
- The brief, the draft, the t21arms2 note and the orch-r2 HANDOFF all say "D fills leave coverage's denominator (slice 2 consequence 1)". That does not match the arm. The operator should see this one.

## Numbers in the draft that I changed, and why
- **Candidate arm shas:** replaced with the c49cdd1 arms (3b793503…, 35ddd970…, 0753f939…). The 415f8d7 shas are kept, listed as superseded.
- **Parity:** 3983/3983 became 3971/3983. The 12 mismatches are exactly `r2/lists/changed_fresh.txt`: 85 tracks, all ruled changes, tabled by show and cause. The parity.txt sha is now 6e5282cd….
- **Slice 5:** 27 shows / 422 tracks with `+5` became 28 / 456. The new artist prefixes add cowboyjunkies (+16) and guster (+19); the M-6 veto removes zentricksters #19. The other slice-5 numbers are unchanged: 0 flag, set, segue or needs_llm changes, and the same 7 delivered shows go from clean to clean-changed.
- **Fresh-get holds cleared:** "would-hold on a fresh get" went from 34 to **33**, so the total is 40, not 41. DSO-2014 is now held by C-1. The draft's "slice 2 19, slice 3 and slice 4 the rest" is now exact: slice 2: 19, slice 3: 12, slice 4: 9. The as-is by-slice counts (4/1/2) are added.
- **holds_delta shas:** as-is is 9b000324… (was 7f3e03e2…) and fresh-get is bd4f853a… (was 53531f99…).
- **Fresh-get packaged title changes:** 38 shows / 363 positions (308 text, 55 source-only) became **37 / 345 (284 / 61)**. DSO-2014 drops out (18 text positions), and 6 deepbananablackout D titles move from text to source-only, because the new strips make them equal the old setlist text. I verified this by diffing the old and r2 title_changes. The title_changes shas are updated, and the by-path breakdowns are added.
- **The bar:** C2 cant-tell went from 2 (2.2% if wrong) to 0, and pooled cant-tell from 2 to 0, under B2. Slice-1 good-S went from "3 strict / 1" to 1 under B3. DSO-2014 #3 is now held (cpb-k13).
- **Removed:** the "Open for the operator at Checkpoint B" list. It is replaced by a table of the rulings as applied.
- **Unchanged and re-verified:** as-is cleared 7 and added 14; fresh-get added 15 (the same lists as at 415f8d7); needs-LLM 188/186, 189/187, 651/653 and 880/858; the D agreement and LLM-branch counts 4/27 and 4/39; as-is title changes; delivered and voiced counts; and the shas of the base arms, gate dump, gate table, adjusted.jsonl, tally.json and pre-screen handback. Calibration 134/135 and 135/135 was recounted from adjusted.jsonl.
- **Suite:** 4762 at 174995e became 4783 passed / 1 skipped / 8 deselected at c49cdd1. That is the fixwave run; I did not re-run it, since this was docs only.

## Source disagreements found
1. **kinggizzard:** "D fills leave the denominator" (brief, draft, ledger) against the arm's `d_fills: []` plus two C2 replacements. See above.
2. **"C-1 changed only DSO-2014 in both views"** (brief and ledger). The r2 arms show C-1 demoting on DSO-2014 in the **fresh-get view only** (`c_demoted` [3]). On the as-is view it demotes nothing at all: DSO-2014's #3 is an operator override there, which C-1 never demotes, and the show stays clean. acceptance.md states this precisely.
3. **cpb-k13 handback against its rows file.** The handback says "232 judged … right 189". `rows.jsonl` (7e0cb0a8…) has 234 track rows, of which 190 are right; the right-partial (40), wrong (2) and cant-tell (2) counts agree. I used the file.
4. **cpb-k08, philleshandfriends-2007-10-20 #18.** The row says today's 'Box of Rain' is "wrong (shifted one late)", but the same row gives the correct title as 'Box of Rain', and the r2 base title at #18 is 'Box of Rain'. I wrote 7 wrong titles (#10-#14, #16, #17) with #15 partial, and did not count #18 as wrong.
5. **soulive-2004-02-08 #10.** The pre-screen and cpb-k08 say today's title is cant-tell; cpb-k12 says wrong. Both are reported in the row.
6. **cpb-k13 zentricksters #19.** It is judged right-partial from the packet's pre-fix column `(actually )`; the c49cdd1 arm ships `(actually d2t10)`. The orch-r2 ledger already noted this; I noted it in the file.

## Other notes
- The cand arms record `sha` as `c49cdd1…-dirty`. The file attributes that to the untracked draft (per the orch-r2 HANDOFF), and `git diff c49cdd1 -- packages scripts` is empty.
- I found no t21arms2 brief. I confirmed that the r2 compares used the first measurement's base arms by matching every `base_outcome` in the r2 `title_rows.json`: 130 as-is rows and 200 fresh-get rows, 0 mismatches.
- The C-1 section is written so that its last paragraph ("Status (replace this paragraph after the ruling)") can be replaced on its own.
