# accept-d-rev: review of acceptance.md at cc23df5 (Opus, read-only)

**Verdict: FIX NEEDED.** There is no Critical finding, and almost every number checks out. Two rows of the (d) table misstate their evidence, and in the direction that hides cost. gratefuldead-1989-07-19 (fresh-get) and stevekimockband-2002-04-20 (as-is) are both described as "not hand-checked, so what the hold stops is unknown". In fact both were hand-checked as all-right shows, so each one is a good show held that stops nothing. As a result, the "good shows held" count that strict surface (d) requires is one short in each view. The status line also undercounts the open items.

File under review: `docs/superpowers/2026-10-22-title-hygiene-evidence/acceptance.md` (cc23df5).

## Findings

### Critical
None.

### Important

**I-1. Two Q1 rows say "not hand-checked, so what the hold stops is unknown". Both shows were hand-checked, and both are good.**

Where it appears:
- line 108: stevekimockband-2002-04-20, as-is;
- line 126: gratefuldead-1989-07-19, fresh-get;
- lines 222-223: both are called "(not hand-checked)" in the bar section.

What contradicts it:
- `docs/superpowers/2026-10-22-title-hygiene-evidence/handcheck/S1/rows.jsonl`: gratefuldead-1989-07-19 is class S, 19/19 right, `all-right`. The note says "the whole-tape rung filled everything correctly. Operator overrides (earlier hand-set) agree".
- `handcheck/S3/rows.jsonl` and `handcheck/U3/rows.jsonl`: stevekimockband-2002-04-20 is 12/12 right and `all-right` in both, confirmed by the 24-bit sibling's durations.
- `~/.llama-harness/piece3/gate-r16/gate_table.md` R2 (and `gate-r16/samples/r2_s_good_lost.txt`): under "good shows losing fills, Q1" it lists `gratefuldead-1989-07-19 (newly held: True)` and `stevekimockband-2002-04-20`.

Why it matters:
- These are hand-checked-good shows held under Q1, and the holds stop no wrong title.
- The "Good shows held" block (lines 140-142) leaves both out. Spec (d) asks for "the count of good shows it would hold", so that count is short by one in each view.
- The pre-screen handback's "gratefuldead-1989-07-19: not hand-checked" meant the Checkpoint B checkers only. acceptance.md carried it over as "never hand-checked".
- The slice-1 bar is unaffected, because Q1 declines are excluded from it.

Fix: in both rows, say "Accepted cost (Q1). Hand-checked all-right (census S1, or S3/U3); stops no wrong title; a good show held". Add both to "Good shows held", and correct lines 222-223.

**I-2. The status line says "One item is still open" (line 5). The file carries a second one.**

- The only open item it names is the C-1 false signature.
- The (d) table also has an **UNEXPLAINED** added hold in both views (kinggizzardandthelizardwizard-2022-10-22, lines 107 and 127). No ruling covers it, so strict surface (d) is not met for that row.
- Line 237 admits that B4's "every added hold is attributed" is unmet for kinggizzard.
- An operator who reads only the status line would think C-1 is the last blocker.

Fix: list both open items. This finding is about the status line only, not about the kinggizzard row's substance.

### Minor

- **M-1. PLF cost is understated** (lines 100 and 119: "Cost: #1-#8 were right"). In cpb-k08, today's #9 `Viola Lee Blues` on the medley file is "today title is right here", and today's #18 `Box of Rain` equals the checker's correct title. The cost is #1-#9 plus #18. The 7-wrong list (#10-#14, #16, #17) and #15 partial are correct.
- **M-2. soulive-2004-02-08 "wrong in cpb-k12"** (lines 103 and 122). cpb-k12's verdict field for #10 is `cant-tell`, and `adjusted.jsonl` records `checker_verdict: cant-tell` for cpb-k12. Only the row's `why` text says that today's duplicate is wrong. The census `handcheck/S2/rows.jsonl` does judge it `wrong`/`shifted` but is not cited; that would be the better citation.
- **M-3. charliehunter-2004-05-22, "not hand-checked"** (line 106). Census `handcheck/S0/rows.jsonl` judges all 10 `?` S fills `wrong`. This favours the row; it should be cited rather than called unchecked.
- **M-4. umphreysmcgee-2005-11-12 conflict not disclosed** (lines 105 and 124: "#12 Wife Soup (right)"). Census `handcheck/S3/rows.jsonl` judged #12 `wrong` ("unlisted/continuation… adjacent duplicate"). cpb-k09 and the pre-screen say right, and B3 was ruled on that reading. The census verdict favours the hold, but the conflict should be noted.
- **M-5. Line 194 "#4-#21 are right".** cpb-k13 has 17 right and 1 right-partial for darkstarorchestra-2014-07-31 #4-#21.
- **M-6. Line 227 overstates B6.** It says B6 accepts `SOTM` via D, but ruling 6 names only MRG via C2 and O via slice 4. Line 239 has it right.
- **M-7. Paths for the pre-screen files** (lines 81 and 183). `adjusted.jsonl` and `tally.json` are in `~/.llama-harness/piece3/accept/handcheck/prescreen/`, not directly under `handcheck/`.
- **M-8. Plan Task 21 Step 6 asks for "the gate table's final numbers".** The file gives a pointer, the sha256 and three headline numbers. I verified all three: S 4 wrong at 7.0%, pooled 0.6%, slice-1 at 2 (lotus, steepcanyon). The per-slice table is not reproduced. That is arguably enough.
- **M-9. final-rev Recommendation 3 is not carried out.** It asked acceptance.md to note that the per-path 2% bar is blind to a wrong title the path did not touch, and that the whole-show hand check is the guard. That caveat is missing, although DSO-2014 #3 (line 219) is exactly that case.

## Per-row grades

| view | show | grade | why |
|---|---|---|---|
| as-is | buttholesurfers-1988-11-22 | SUPPORTED | Pre-screen rejudge: #19 Comb is wrong (taper CD2 #5 and sibling t19 say Lou Reed); census S0 agrees. #18 Jimi is judged right by the pre-screen and census ("probably" understates). Slices 1, 2, 3 match. |
| as-is | darkstarorchestra-2004-04-24 | SUPPORTED (Q1 cost) | cpb-k05: set 1 agrees with the taper's list; sets 2-3 cant-tell; #20 is the 154 s d3t05. All 24 withdrawn; +23 flags counted. |
| as-is | darkstarorchestra-2015-07-11 | SUPPORTED | cpb-k05: #1-#8 shifted (Feedback omitted), #9-#11 right. |
| as-is | lotus-2010-06-10 | SUPPORTED (B3/B7 cost) | Pre-screen regression 2 and k07: Sunrain right, bare `13` read as a disc label, adjacent-duplicate decline (arm note). |
| as-is | philleshandfriends-2007-10-20 | SUPPORTED (M-1) | cpb-k08: 7 wrong (#10-14, 16, 17), #15 partial, Plasma 638 s against 642 s. The cost omits #9 and #18. |
| as-is | railroadearth-2007-01-28 | SUPPORTED | Pre-screen regression 3: true title 420 (desc `2. 420 (4:44)` = 284 s); `Disc One (59:44)` header gap; census S2 wrong. |
| as-is | signalpath-2005-06-09 | SUPPORTED | Literal `?` on #8 (title_rows); d_track_declines slot placeholder; k08 and pre-screen agree. |
| as-is | soulive-2004-02-08 | WEAK (M-2) | Pre-screen and k08 cant-tell; k12's verdict field is also cant-tell (only its prose says wrong). Census S2 `wrong/shifted` would support it but is not cited. |
| as-is | stringcheeseincident-2005-07-23 | WEAK | Cant-tell in every source; the quote "today was likely wrong" is accurate (k08 note). Honestly labelled "probable". |
| as-is | umphreysmcgee-2005-11-12 | SUPPORTED (B3) | Pre-screen regression 1: #13 ends at 2137 s, the end of Let Me Go Home; arm C note "off by one … tracks 13-17". Census conflict on #12 not disclosed (M-4). |
| as-is | charliehunter-2004-05-22 | SUPPORTED (M-3) | title_rows: `?` on #12 and #14 via setlist; d_failed agreement; slot-placeholder declines; needs_llm.txt agreement decline; fresh base newly-held. Census S0 hand-checked it (wrong). |
| as-is | kinggizzardandthelizardwizard-2022-10-22 | facts ACCURATE; substance not graded | d_fills [], desc_position 0, the C2 #6/#13 changes, needs_llm align_structure, stored coverage 0.9231, the description quote, and spec Goal 3 "It adds no holds" (spec line 57) all verified. The row itself admits the hold is unsupported. |
| as-is | stevekimockband-2002-04-20 | UNSUPPORTED evidence statement (I-1) | The Q1 classification and the facts (untagged, 12 withdrawn, fresh base needs-llm) are correct. "Not hand-checked … unknown" is false: census S3 and U3 found 12/12 right, so this is a good show held. |
| as-is | dumpstaphunk-2008-04-25 | SUPPORTED | cpb-k05 and pre-screen: literal `?` on #2 and #12; 13 other titles fine. Slices 2, 3, 4 match. |
| fresh-get | buttholesurfers-1988-11-22 | SUPPORTED | As as-is. |
| fresh-get | darkstarorchestra-2004-04-24 | SUPPORTED (Q1 cost) | As as-is. |
| fresh-get | darkstarorchestra-2015-07-11 | SUPPORTED | As as-is. |
| fresh-get | lotus-2010-06-10 | SUPPORTED (B3/B7 cost) | As as-is. |
| fresh-get | philleshandfriends-2007-10-20 | SUPPORTED (M-1) | As as-is. |
| fresh-get | railroadearth-2007-01-28 | SUPPORTED | As as-is. |
| fresh-get | signalpath-2005-06-09 | SUPPORTED | As as-is. |
| fresh-get | soulive-2004-02-08 | WEAK (M-2) | As as-is. |
| fresh-get | stringcheeseincident-2005-07-23 | WEAK | As as-is. |
| fresh-get | umphreysmcgee-2005-11-12 | SUPPORTED (B3) | As as-is. |
| fresh-get | derektrucksband-2007-05-25 | SUPPORTED | cmp-fresh title_rows: base #10 `Well, I Done Got Over It` (setlist) beside #11 tag `Done Got Over It`; operator override `44`; arm s_declined [10]; census S0 judged it wrong. Slice 1 matches. |
| fresh-get | gratefuldead-1989-07-19 | UNSUPPORTED evidence statement (I-1) | The Q1 classification and the 19-track withdrawal are correct. "Not hand-checked … unknown" is false: census S1 found 19/19 right, and the gate lists it as a good show losing fills, newly held. |
| fresh-get | kinggizzardandthelizardwizard-2022-10-22 | facts ACCURATE; substance not graded | The record is identical to as-is (verified). |
| fresh-get | steepcanyonrangers-2004-05-21 | SUPPORTED (B3) | Arm: tags #4-#30 match override #5-#31 (e.g. tag #30 OBS = override's Lonesome Moon); C off by one on 4-30; D adjacent duplicate on #31; base #31 OBS; census S3 agrees. |
| fresh-get | dumpstaphunk-2008-04-25 | SUPPORTED | As as-is. |

## Checked and found accurate

- **sha256 values.** All recomputed, all match:
  - 5 arms and 3 superseded arms;
  - gate dump and gate_table;
  - parity.txt;
  - cmp-slice5, cmp-asis and cmp-fresh holds_delta;
  - both title_changes files;
  - strata_index, r16.txt and readerii.txt (prefixes);
  - adjusted.jsonl and tally.json;
  - the pre-screen and fixwave-rr handbacks;
  - the cpb-checker-brief prefix;
  - cpb-k13 rows.
  - `handcheck/rows.sha256` also verifies 12/12 OK.
- **Arms.** Every arm has 3983 rows. The base sha is 74ec267, whose parent is 11dbffb, with an empty `packages` diff. The candidate sha is c49cdd1-dirty, and `git diff c49cdd1 cc23df5 -- packages scripts` is empty. Each arm's `llama_file` sits inside its own tree.
- **Base outcomes.** 130 as-is and 200 fresh-get title rows, with 0 base_outcome mismatches against the first measurement's base arms.
- **Parity.**
  - 3983 compared, 3971 matching, 12 mismatching; the 12 shows equal `changed_fresh.txt`.
  - The per-show mismatch counts sum to 85, and every parity-table cause matches the mismatch text.
- **Slice 5.**
  - 28 shows / 456 `+5` tracks, against 27 / 422 at 415f8d7. The difference is exactly cowboyjunkies +16, guster +19 and zentricksters −1.
  - Zero differences on all 8 fields.
  - The same 7 delivered shows go from clean to clean-changed, with briefings from reuse to fresh.
- **Holds.** The holds table, the cleared counts by slice, the 34 → 33 would-hold count (DSO-2014), and the added lists (names and flags identical to 415f8d7 in both views).
- **(d) row set.** It equals the r2 holds_delta added lists exactly: 14 as-is and 15 fresh-get, with no missing or extra row. Every slice attribution, flag letter and +N count matches (23, 12, 19, 12, 20).
- **Title changes.** Every cell of the title-change table and every by-path count. The 415f8d7 arithmetic holds: 308−18−6 = 284, and 55+6 = 61.
- **Needs-LLM.** 188/186, 189/187, 651/653 and 880/858; agreement declines 4/27 and 4/39.
- **Hand check.**
  - Strata 18/23/74/16/14/12 = 157. The figure "12 of 33" is in the orch-r2 ledger and the t15 handback.
  - 87 rejudged rows (3 wrong, 84 cant-tell) and 222 adjusted rows.
  - Calibration 134/135 exact (billystrings #11) and 135/135 not-wrong.
  - cpb-k13: 16 rows, 234 tracks, 190/40/2/2, 0 shifted. Its findings for greensky, lettuce, tedeschi, cowboyjunkies, guster and zentricksters all match.
- **C-1.** `c_demoted` is non-empty only on DSO-2014 fresh [3], in all three r2 arms. DSO-2014's overrides cover all 21 tracks. The fixwave-rr Important #1 text and the "17 of 18" figure match.
- **Bars (check 3).**
  - The bar table equals tally.json except for C2 cant-tell 2 → 0 and pooled cant-tell 2 → 0, which is B2 applied as ruled.
  - Slice 1 equals 1 per B3.
  - No other cell was re-graded.
  - The "shifted: zero" claim still holds at c49cdd1: billystrings-2023-06-10, derektrucksband-2003-11-26 and every gate some-wrong or cant-tell show are needs-llm in the r2 cand-fresh arm.
- **Task 21 coverage (check 4).** Steps 3 and 6 are covered, except M-8 (gate table detail) and the kinggizzard explanation, which is disclosed as missing.

## Not checked

- I did not re-run the test suite: running it was outside the brief's read-only command list. The c49cdd1 commit message does confirm 4783 passed, 1 skipped, 8 deselected. The 174995e re-run (4762) is unverified.
- That the checkers ran on Sonnet.
- That the draft acceptance.md was the only uncommitted file when the candidate arms ran.
- The pre-ruling S count of 5 (only the post-ruling 4 is in gate_table.md).
- The kinggizzard row's reasoning, beyond its facts (excluded by the brief).
- The "draft/ledger/brief" claim in the kinggizzard row.
