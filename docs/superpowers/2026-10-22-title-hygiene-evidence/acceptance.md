# Title hygiene (piece 3): acceptance

Plan Task 21, re-measured after the Checkpoint B fix wave. Every number below is for candidate code at **c49cdd1** unless a row says otherwise. Read-only on the library: every output is under `~/.llama-harness/piece3/accept/` (the re-measure is in its `r2/` subdirectory; runner report `.superpowers/sdd/title-hygiene/t21arms2/handback.md`).

Status: the operator ruled on Checkpoint B (rulings verbatim in `.superpowers/sdd/title-hygiene/orch-r2/checkpoint-b-rulings.md`). The fix wave landed as 95c6bb2 (C-1), efafc8c (I-1), 8cf89c5 (cosmetic constants, M-1, M-6) and c49cdd1 (Fable's minors). **Two items are still open, both awaiting an operator ruling:** (1) the C-1 false-signature question in the last section; (2) the kinggizzardandthelizardwizard-2022-10-22 added hold, whose cause is now computed (slice 3, C2, via align() coverage) and which contradicts the spec's "C2 adds no holds" (see the (d) table).

The hand check was run on the first measurement, at 415f8d7. 174995e adds tests only (`git diff 415f8d7 174995e -- 'packages/*/src' scripts/replay_holds.py` is empty). A second, smaller hand check (cpb-k13) covers every show whose titles the fix wave changed.

## Arms

| arm | tree | flags | rows | sha256 |
|---|---|---|---|---|
| base-asis | base 74ec267 | none | 3983 | 0bef062a9d355ad127468f0b015050c79f184ceab405373be2c414a0dbeda0b0 |
| base-fresh | base 74ec267 | strip title + structure overrides | 3983 | 759cd2f31743d1008e715a6329c2fee568feb7b6664667e5a3ea82c4106a32e5 |
| cand-asis | cand c49cdd1 | none | 3983 | 3b793503c7c5cc3807670d1a6d8db02c3dbf96746f065a51ed34e82fde3ddfc9 |
| cand-fresh | cand c49cdd1 | strip title + structure overrides | 3983 | 35ddd97016115409247c9dd326942502fb0a785c7159128c6c768d0867c97c1c |
| cand-fresh-no5 | cand c49cdd1 | as cand-fresh, `--disable-slices slice5` | 3983 | 0753f9396711d01fbf4c1eeaaafc2d296a2553539a37cb5a870fea20ce2ea896 |

- **Base arms.** They come from the first measurement (`accept/arms/`); r2 wrote candidate arms only. Every `base_outcome` in r2's `title_rows.json` equals the first measurement's base arm (130 as-is rows and 200 fresh-get rows checked, 0 mismatches).
  - The base tree is 11dbffb plus the cherry-picked Task 12 harness commit. `git diff --stat 11dbffb HEAD -- packages` is empty there.
- **Candidate arms.** They recorded `sha` `c49cdd1…-dirty`. The only uncommitted file at the time was the untracked draft of this file (orch-r2 ledger, HANDOFF), and `git diff c49cdd1 -- packages scripts` is empty.
- **Interpreters.** Each arm ran with its own tree's interpreter, and `llama.__file__` resolved inside that tree.
- **Slices.** All arms use the default `ENABLED_SLICES`, which is all five slices (Checkpoint A ruling 1 kept every slice).
- **Superseded.** The first candidate arms (415f8d7) are superseded: cand-asis 2db77631…3f54, cand-fresh e1abc608…259a, cand-fresh-no5 1335aa28…74f6.

## Parity and slice 5

**Parity.** `title_hygiene_probe.py parity` compared cand-fresh with the post-R16 gate dump (`~/.llama-harness/piece3/gate-r16/dump.jsonl`, sha256 2df10e2cc7fc18470b6801a3b28e8a74ea01bd838ebafb5c28a408c28e4397a6).
- Result: 3983 compared, **3971 matching, 12 mismatching**, 0 skipped. `r2/parity/parity.txt` has sha256 6e5282cda1837d34c25a3a7207d664898721a29bf11cf19d3c1bb1214ec054d0.
- The dump predates the fix wave. The 12 mismatching shows are exactly the 12 shows in `r2/lists/changed_fresh.txt`, the fix wave's old-vs-new candidate diff, which covers 85 tracks.
- Each mismatch is a ruled change, so there is no wiring defect.

| show | tracks | cause (ruling) |
|---|---|---|
| cowboyjunkies-2017-11-05 | 16 (#1-16) | B5: slice 5 strips an artist prefix equal to the show artist (`Cowboy Junkies - 02 - He Will Call You Baby` → `02 - He Will Call You Baby`) |
| darkstarorchestra-2011-04-15 | 1 (#22) | B5: D strips a duration glued after `)` (`Playing In The Band(reprise)6:51`) |
| darkstarorchestra-2014-07-31 | 1 (#3) | B1: C-1 demotes the shifted MP3 tag `Duprees Diamond Blues` → `unresolved`; the show is now held |
| deepbananablackout-2004-04-01 | 9 | B5: D strips a leading `--> ` (8 tracks) and a trailing `^` (#24 `Boot!^`) |
| gratefuldead-1974-10-18 | 1 (#24) | B5: slice 5 strips `Encore- ` |
| greenskybluegrass-2013-05-04 | 21 (#1-21) | B5: artist prefix `Greensky Bluegrass - ` |
| greenskybluegrass-2015-02-27 | 1 (#6) | B5: trailing `^`. C's lossless-title strip shares D's one `_TRAIL_MARKERS`, so C2's `Butcher's Girl ^` loses it |
| guster-2006-07-28 | 19 (#1-19) | B5: artist prefix `Guster - ` |
| joerussosalmostdead-2015-10-29 | 1 (#16) | B5: D strips a trailing `^` (`Jam ^`) |
| lotus-2008-02-07 | 12 (#1-12) | B5: slice 5 strips a trailing ` H2` |
| mymorningjacket-2004-06-18 | 2 (#13-14) | B5: D strips a trailing `$` with its padding (`cobra          $`) |
| zentricksters-2002-12-31 | 1 (#19) | B5/B8, M-6: slice 5 declines a strip that would leave `(actually )`; the title ships `Banks of the Ohio (actually d2t10)` with no `+5` path |

**Slice 5.** cand-fresh-no5 was compared with cand-fresh field by field, over all 3983 shows:
- zero differences in `gather_flags`, `vet_flags`, `brief_flags`, `sets`, `set_changes`, `segue_changes`, `set_breaks` and `needs_llm`;
- **28 shows and 456 tracks carry `+5`** (27 and 422 at 415f8d7). The difference is the new artist-prefix shape: cowboyjunkies-2017-11-05 adds 16 tracks and guster-2006-07-28 adds 19; the M-6 veto removes zentricksters-2002-12-31 #19;
- `cmp-slice5/holds_delta.txt` reports 0 cleared and 0 added (sha256 c4353b0addcc0bf3bf00fd14410ea7fbefd607d47bf0fa6844f08b3bce185fa9);
- the same 7 delivered shows move from `clean` to `clean-changed`, and their briefing goes from reuse to fresh. That means one brief call each on re-processing: gratefuldead-1983-10-12, gratefuldead-1984-10-14, greatamericantaxi-2008-09-17, lotus-2008-02-07, mymorningjacket-2008-06-20, perpetualgroove-2007-09-08, umphreysmcgee-1998-04-15.

## Gate table (Checkpoint A, final pre-wiring form)

The table is `~/.llama-harness/piece3/gate-r16/gate_table.md` (sha256 108cf2b8d38ffebc830080df6a234eb5b4fac8771911839c803e47e8d82562d4). It was measured on 89fd787 plus the R16 clarification diff, in a scratch tree, with gate 0 at 3983/3983 in both views.

- The Checkpoint A artefacts are in `~/.llama-harness/piece3/gate/checkpoint-a/`.
- The operator's rulings are verbatim in the SDD record, `checkpoint-a-rulings.md`.
- After those rulings, the S path's wrong count dropped from 5 to 4 (7.0% on the gate's S hand check), pooled wrong was 0.6%, and the slice-1 bar was met at 2 (lotus, steepcanyon).

## Holds

| view | cleared: held now | cleared: would-hold on a fresh get | cleared: currently shipped | cleared total | added |
|---|---|---|---|---|---|
| as-is | 5 | 0 (by construction) | 2 | 7 | 14 (10 delivered, 3 packaged, 1 voiced) |
| fresh-get | 5 | 33 | 2 | 40 | 15 (10 delivered, 4 packaged, 1 voiced) |

- **Cleared, by slice.** A show is listed under each slice that cleared it. As-is: slice 2: 4, slice 3: 1, slice 4: 2. Fresh-get: slice 2: 19, slice 3: 12, slice 4: 9.
- **The files.** `r2/cmp-asis/holds_delta.txt` has sha256 9b000324e393fe5638af205584f058b109021a7d71b2f50bda24b818bf73e817. `r2/cmp-fresh/holds_delta.txt` has sha256 bd4f853ae5ac281cadd4e631502468b097e7f1d9d617f9c0ba1b0df9fd1c0578.
- **Change since 415f8d7.** darkstarorchestra-2014-07-31 is **no longer a cleared hold** on the fresh-get view; it was one of the 34 would-hold shows. C-1 now holds it on `unresolved track titles` (#3), as the fresh base already did (for #21), so it is neither cleared nor added. On the as-is view the operator's title overrides cover all 21 tracks, C-1 demotes nothing there, and the show stays clean in both arms. The added-hold lists are identical to 415f8d7's in both views.
- **Attribution.** Every added hold is now attributed to a slice (I-1, ruling 4). kinggizzardandthelizardwizard-2022-10-22 comes from no decline, so the replay tags it `unattributed`; its cause is slice 3 (C2) through align() coverage, computed in `.superpowers/sdd/title-hygiene/kg-why/handback.md`. See the (d) table.

## (d) Added holds: justification

Strict surface (d) of the spec says: "any change that adds holds. Each one must be justified by the wrong titles it stops, with the count of good shows it would hold." Checkpoint B ruling 9 asks for one row per added hold in both views.

- The lists, flags and slice attribution are copied from the r2 `holds_delta.txt` files.
- The before and after titles are from r2 `title_rows.json`.
- The mechanism (which rung declined, and why) is from the arms' `cascade` record and gather notes.
- Verdicts are from the hand check. The checker and pre-screen handbacks are under `.superpowers/sdd/title-hygiene/`, and their row files under `~/.llama-harness/piece3/accept/handcheck/` (the pre-screen's `adjusted.jsonl` and `tally.json` are in its `prescreen/` subdirectory).

**Flag key:**
- U: `unresolved track titles`
- L: `low-confidence structure alignment`
- J: `structure has 1 sets but jerrybase shows 2`
- R2: `research asserts 2 sets but structure has 1`
- +N: N `research asserts unknown song` flags, which follow from the unresolved tracks

**Ruling key:** Q1-Q5 are the spec's operator rulings; A-n are Checkpoint A rulings; B-n are Checkpoint B rulings.

### As-is view (14 rows; `r2/cmp-asis/holds_delta.txt`)

| view | show [state] | slice responsible | hold flag(s) | what the hold stops, or the accepted cost | evidence |
|---|---|---|---|---|---|
| as-is | buttholesurfers-1988-11-22 [delivered] | slice1, slice2, slice3 | L, U | **Stops a wrong title.** #19 `Comb` (setlist.fm, via S) is wrong: the taper's description (CD2 #5) and the sibling say `Lou Reed`. D declined the show on tape agreement, and S declined #18-19 with it. The hold also keeps back a tape whose own tags #1-#17 are one early against sibling durations. **Cost:** #18 `Jimi` was probably right (the sibling's 517 s matches 517 s). | cpb-k05 row; pre-screen rejudge #18/#19 (`adjusted.jsonl`); pre-screen handback, slice-1 bar ("bad S copy") and finding 9 |
| as-is | darkstarorchestra-2004-04-24 [delivered] | slice1, slice3 | L, J, U, +23 | **Accepted cost (Q1).** This is a wholly untagged tape, and S may not fill it from a setlist.fm canonical, so all 24 setlist titles are withdrawn. Q1 declines are reported apart from the slice-1 bar (spec Acceptance 4). **Stops no confirmed wrong title:** set 1 (#1-#11) agreed with the taper's 11-entry list, and sets 2-3 are cant-tell (#20 `Dark Star` sits on a 154 s file, judged doubtful). | cpb-k05 rows #1-#24; pre-screen handback, Q1 list |
| as-is | darkstarorchestra-2015-07-11 [delivered] | slice1, slice3 | L, U, +12 | **Stops a shifted show (Q1 decline).** #1-#8 are one off: for example, #1 `Viola Lee Blues` sits on the file the taper's list calls `Feedback`, which setlist.fm omits. **Cost:** #9-#11 were right. | cpb-k05 rows #1-#11; pre-screen handback, Q1 list |
| as-is | lotus-2010-06-10 [delivered] | slice1, slice2, slice3 | U | **Accepted cost: the one good S show held** (B3: slice-1 bar ≤ 2, met at 1). #12 `Sunrain` (right) is withdrawn. Reader (i) reads the bare trailing `13` line as a disc label, so a 13-line list counts as 12, matching the 12 kept files. Entry 12 `Flower Sermon` then duplicates #11's tag, check 2 fires, and S declines with D. That reader gap is accepted as a documented limitation (B7: it costs holds, not accuracy). Stops nothing. | cpb-k07 row #12; pre-screen regression 2; `adjusted.jsonl` |
| as-is | philleshandfriends-2007-10-20 [delivered] | slice1, slice3 | L, J, U, R2, +19 | **Stops a shifted show (Q1 decline).** #9 is one 1878 s medley file (Viola Lee > Cumberland), so the setlist copy runs one late from #10. Seven titles are wrong: #10-#14, #16 and #17. For example, #10 `Cumberland Blues` sits on Plasma's file (sibling Plasma 638 s against 642 s). #15 `Help on the Way` is partial, since the file is Help on the Way > Slipknot!. **Cost:** #1-#9 and #18 were right (cpb-k08: today's #9 `Viola Lee Blues` on the medley file is right, and today's #18 `Box of Rain` equals the checker's correct title). | cpb-k08 rows #1-#18; pre-screen handback, Q1 list and finding 9 |
| as-is | railroadearth-2007-01-28 [delivered] | slice1, slice3 | U | **Stops a wrong title.** Gated S put `My Sisters & Brothers (6:40)` on #9, an adjacent duplicate of #8's tag. The file is `420`: its raw tag, and the description's `2. 420 (4:44)` = 284 s. **Cost:** slice 4 cannot recover `420`, because a disc header carrying a duration (`Disc One (59:44)`) is outside the header grammar. That reader gap is accepted (B7). | cpb-k08 row #9; pre-screen regression 3; `adjusted.jsonl` |
| as-is | signalpath-2005-06-09 [delivered] | slice1, slice2 | L, U | **Stops a junk title:** S shipped a literal `?` on #8, copied from the taper's `?` entry and now declined as a slot placeholder. No right title exists in any source. | cpb-k08 row #8; pre-screen handback ("S shipped a literal `?`"); `adjusted.jsonl` |
| as-is | soulive-2004-02-08 [delivered] | slice2, slice3 | U | **Stops a probable duplicate.** #10 `Do It Again` duplicates #9's tag. D declined on check 2: the description and the tags are one apart around a `?` entry, which is the specified shift signature. Today's #10 is cant-tell in the pre-screen, cpb-k08 and cpb-k12 (k12's verdict field; only its `why` text calls the duplicate wrong), and `wrong`/`shifted` in the census hand check. | cpb-k08 and cpb-k12 rows #10; census `handcheck/S2/rows.jsonl`; pre-screen regression 5; `adjusted.jsonl` |
| as-is | stringcheeseincident-2005-07-23 [delivered] | slice1, slice2 | L, U | **Stops a probable duplicate.** #12 `Quinn the Eskimo (The Mighty Quinn)` duplicates #11's tag `The Mighty Quinn@`, so check 2 declines the fill. Today's #12 is cant-tell: the 486 s tail does not line up with the sibling, and cpb-k08 says "today was likely wrong". | cpb-k08 row #12; pre-screen rejudge (`adjusted.jsonl`) |
| as-is | umphreysmcgee-2005-11-12 [delivered] | slice1, slice3 | U | **Justified hold (B3); stops shifted tape tags.** #12 `Wife Soup` (right) is withdrawn because check 2 fires on tag #13 `Wife Soup,`, which is itself shifted. Tags #13-#17 are one early: #13 ends at 2137 s, which is where Let Me Go Home ends. The hold stops 5 silently shifted tags. Conflict: the census hand check (`handcheck/S3/rows.jsonl`) judged #12 `wrong` (an unlisted continuation, adjacent duplicate of the next file's tag), where cpb-k09 and the pre-screen judge it right; B3 was ruled on the cpb-k09 reading. The census verdict favours the hold. | cpb-k09 row #12; census `handcheck/S3/rows.jsonl`; pre-screen regression 1 and finding 9; `adjusted.jsonl` |
| as-is | charliehunter-2004-05-22 [packaged] | slice2, slice3, slice4 | U | **Stops junk titles:** literal `?` on #12 and #14, which are setlist copies of the taper's `?` entries. D declined the show on its agreement check, and each `?` position as a slot placeholder. No right title exists in the sources. This row appears in the as-is view only, because the fresh base already holds the show. | r2 `cmp-asis/title_rows.json`; `cmp-asis/needs_llm.txt` ("agreement decline"); census `handcheck/S0/rows.jsonl` (all 10 `?` S fills judged `wrong`, `some-wrong-not-shift`); no Checkpoint B packet (no fresh-view row) |
| as-is | kinggizzardandthelizardwizard-2022-10-22 [packaged] | slice3 (C2), via align() coverage; replay tags it `unattributed` | L | **accepted cost — PENDING OPERATOR RULING (orchestrator recommends accepting it as a documented cost and correcting the spec sentence).** Cause, computed (not inferred): the two C2 replacements, #6 `Organ Farmer` → `Her and I (part one)` and #13 `Altered Beast IV` → `Evil Death Roll (part one)`, are both right per the taper's own description ("(part one) is added for where I mistracked the songs") and the FLAC tags. Together they lower deterministic `align()` coverage against the setlist.fm canonical from 12/13 = 0.9231 to 10/13 = 0.7692, under the 0.8 threshold. #6 `Her and I (part one)` no longer fuzzy-matches the canonical `Her and I (Slow Jam 2)`, and #13 `Evil Death Roll (part one)` takes the canonical `Evil Death Roll`, leaving #14, the song's second half, unmatched. Either replacement alone stays at 11/13 = 0.8462 and does not hold. With `--disable-slices slice3` the show replays clean. There is no D fill (`d_fills: []`). The harness outcome is `needs-llm` (one `align_structure` call; the outcome of that call is unmeasured), and the hold stops no wrong title. It is the only show in either view where C2 adds a low-confidence/needs-LLM state; C2 removes it from 6 shows (as-is: explosionsinthesky-2010-09-02, lettuce-2010-11-14, newmastersounds-2009-06-06, newmastersounds-2011-06-04, robertwalters20thcongress-2009-04-29, stuallenandmarshotel-2012-04-18) and 9 shows (fresh-get: those six plus bigheadtoddandthemonsters-1991-01-21, jimlauderdale-2011-07-22, lettuce-2002-07-13). This contradicts the spec's "C2 adds no holds" (spec lines 57 and 290). An earlier explanation, that D fills leave coverage's denominator, does not match the arm. | `.superpowers/sdd/title-hygiene/kg-why/handback.md`; `~/.llama-harness/piece3/kg-why/`; r2 cand arms (`cascade.c_changed` {6, 13}: C2, `needs_llm`: `align_structure`); `~/.llama-harness/piece3/accept/arms/base-asis.json`; stored `show.json` coverage 0.923; `~/.llama/cache/md_kglw2022-10-22.ScheopsMK41.Flac24.json`; not hand-checked |
| as-is | stevekimockband-2002-04-20 [packaged] | slice1, slice3 | U, +12 | **Accepted cost (Q1); a good show held that stops no wrong title.** This is a wholly untagged tape with a setlist.fm canonical, so all 12 setlist titles are withdrawn. Hand-checked all-right: 12/12 right in the census hand check (S3 and U3), the description order and the 12 durations agreeing with the 24-bit sibling. This row appears in the as-is view only, because the fresh base already holds the show (needs-LLM). | census `handcheck/S3/rows.jsonl` and `handcheck/U3/rows.jsonl` (`all-right`); `~/.llama-harness/piece3/gate-r16/gate_table.md` R2 ("good shows losing fills, Q1"); r2 cand-asis `cascade` (`s_mode: untagged`) and note "positional fill declined: setlist wholly untagged tape" |
| as-is | dumpstaphunk-2008-04-25 [voiced] | slice2, slice3, slice4 | U | **Stops junk titles:** S shipped a literal `?` on #2 and #12, copied from the taper's `?` entries and now declined as slot placeholders. No right title exists. **Cost:** a voiced show whose other 13 titles are fine goes back to held. | cpb-k05 rows #2/#12; pre-screen rejudge (`adjusted.jsonl`); pre-screen handback ("S shipped a literal `?`") |

### Fresh-get view (15 rows; `r2/cmp-fresh/holds_delta.txt`)

| view | show [state] | slice responsible | hold flag(s) | what the hold stops, or the accepted cost | evidence |
|---|---|---|---|---|---|
| fresh-get | buttholesurfers-1988-11-22 [delivered] | slice1, slice2, slice3 | L, U | **Stops a wrong title.** #19 `Comb` should be `Lou Reed` (the taper's description and the sibling). D declined on tape agreement, and S declined #18-19 with it. The hold also keeps back a tape whose own tags #1-#17 are one early. **Cost:** #18 `Jimi` was probably right. | cpb-k05; pre-screen rejudge #18/#19; pre-screen handback, slice-1 bar and finding 9 |
| fresh-get | darkstarorchestra-2004-04-24 [delivered] | slice1, slice3 | L, J, U, +23 | **Accepted cost (Q1).** All 24 setlist titles are withdrawn on a wholly untagged tape. Stops no confirmed wrong title: set 1 was right, and sets 2-3 are cant-tell (#20 `Dark Star` on a 154 s file is doubtful). | cpb-k05 rows #1-#24; pre-screen Q1 list |
| fresh-get | darkstarorchestra-2015-07-11 [delivered] | slice1, slice3 | L, U, +12 | **Stops a shifted show (Q1 decline).** #1-#8 are one off; the taper's list starts with `Feedback`, which setlist.fm omits. **Cost:** #9-#11 were right. | cpb-k05 rows #1-#11; pre-screen Q1 list |
| fresh-get | lotus-2010-06-10 [delivered] | slice1, slice2, slice3 | U | **Accepted cost: the one good S show held** (B3; the bar is met at 1). #12 `Sunrain` (right) is withdrawn. The bare `13` line is read as a disc label, a reader gap accepted under B7. Check 2 then fires on `Flower Sermon`, and S declines with D. | cpb-k07 row #12; pre-screen regression 2 |
| fresh-get | philleshandfriends-2007-10-20 [delivered] | slice1, slice3 | L, J, U, R2, +19 | **Stops a shifted show (Q1 decline).** The 1878 s medley file at #9 puts the setlist copy one late from #10: 7 titles are wrong (#10-#14, #16, #17) and #15 is partial. **Cost:** #1-#9 and #18 were right (cpb-k08: today's #9 `Viola Lee Blues` on the medley file is right, and today's #18 `Box of Rain` equals the checker's correct title). | cpb-k08 rows #1-#18; pre-screen Q1 list and finding 9 |
| fresh-get | railroadearth-2007-01-28 [delivered] | slice1, slice3 | U | **Stops a wrong title.** #9 `My Sisters & Brothers (6:40)` is an adjacent duplicate on the file that is `420`. **Cost:** `420` is not recovered, because of the disc-header-with-duration reader gap (B7). | cpb-k08 row #9; pre-screen regression 3 |
| fresh-get | signalpath-2005-06-09 [delivered] | slice1, slice2 | L, U | **Stops a junk title:** a literal `?` on #8, now a slot-placeholder decline. No right title exists. | cpb-k08 row #8; pre-screen handback |
| fresh-get | soulive-2004-02-08 [delivered] | slice2, slice3 | U | **Stops a probable duplicate.** #10 `Do It Again` duplicates #9's tag, and D's check 2 fires on the shift signature. Today's #10 is cant-tell in the pre-screen, cpb-k08 and cpb-k12 (k12's verdict field; only its `why` text calls the duplicate wrong), and `wrong`/`shifted` in the census hand check. | cpb-k08 and cpb-k12 rows #10; census `handcheck/S2/rows.jsonl`; pre-screen regression 5 |
| fresh-get | stringcheeseincident-2005-07-23 [delivered] | slice1, slice2 | L, U | **Stops a probable duplicate.** #12 `Quinn the Eskimo (The Mighty Quinn)` duplicates #11's `The Mighty Quinn@`, and check 2 fires. Today's #12 is cant-tell. | cpb-k08 row #12; `adjusted.jsonl` |
| fresh-get | umphreysmcgee-2005-11-12 [delivered] | slice1, slice3 | U | **Justified hold (B3); stops shifted tape tags.** Tags #13-#17 are one early. #12 `Wife Soup` (right) is withdrawn by check 2 against the shifted tag `Wife Soup,` on #13. Conflict: the census hand check (`handcheck/S3/rows.jsonl`) judged #12 `wrong` (adjacent duplicate), where cpb-k09 and the pre-screen judge it right; it favours the hold. | cpb-k09 row #12; census `handcheck/S3/rows.jsonl`; pre-screen regression 1 |
| fresh-get | derektrucksband-2007-05-25 [packaged] | slice1 | U | **Stops a wrong title.** Gated S put `Well, I Done Got Over It` on #10, an adjacent duplicate of #11's tag `Done Got Over It`. The operator's own override for #10 is `44`. This row appears in the fresh-get view only: on the as-is view the override ships. | pre-screen handback, slice-1 bar ("bad S copy"); r2 cand-fresh `cascade` (`s_declined: [10]`) and `stripped` |
| fresh-get | gratefuldead-1989-07-19 [packaged] | slice1, slice3 | L, J, U, +20 | **Accepted cost (Q1); a good show held that stops no wrong title.** All 19 setlist titles are withdrawn on a wholly untagged tape. Hand-checked all-right: 19/19 right in the census hand check (S1: 19 files = 19 songs, the whole-tape rung filled everything correctly, operator overrides agree). | census `handcheck/S1/rows.jsonl` (`all-right`); `~/.llama-harness/piece3/gate-r16/gate_table.md` R2 ("good shows losing fills, Q1", newly held True); r2 cand-fresh `cascade` (`s_mode: untagged`) |
| fresh-get | kinggizzardandthelizardwizard-2022-10-22 [packaged] | slice3 (C2), via align() coverage; replay tags it `unattributed` | L | **accepted cost — PENDING OPERATOR RULING (orchestrator recommends accepting it as a documented cost and correcting the spec sentence).** The record is identical to the as-is row: the same two taper-backed C2 replacements (`Her and I (part one)` on #6, `Evil Death Roll (part one)` on #13) lower align() coverage from 12/13 = 0.9231 to 10/13 = 0.7692, and the show reaches the LLM branch (`needs-llm`, outcome unmeasured). With `--disable-slices slice3` it replays clean. There is no D fill. The hold stops no wrong title, and it contradicts the spec's "C2 adds no holds" (lines 57, 290). It is the only show in this view where C2 adds the state; C2 removes it from 9 shows (the nine listed in the as-is row). | `.superpowers/sdd/title-hygiene/kg-why/handback.md`; `~/.llama-harness/piece3/kg-why/`; r2 cand-fresh arm; stored `show.json` coverage 0.923; kglw cache metadata; not hand-checked |
| fresh-get | steepcanyonrangers-2004-05-21 [packaged] | slice2, slice3 | U | **Justified hold (B3); stops a silently shifted show.** On a fresh get the tape tags #4-#30 are one early. C declined: "off by one against the taper's list (tracks 4-30)". The operator's overrides re-title #4-#31 one later; for example, tag #30 `Orange Blossom Special` is the override's `Lonesome Moon`. **Cost:** #31 `Orange Blossom Special` (right) is withdrawn by D's adjacent-duplicate decline. This row appears in the fresh-get view only: on the as-is view the overrides ship. | pre-screen handback, slice-1 bar item 3; r2 cand-fresh `cascade` and `stripped` |
| fresh-get | dumpstaphunk-2008-04-25 [voiced] | slice2, slice3, slice4 | U | **Stops junk titles:** literal `?` on #2 and #12, now slot-placeholder declines. No right title exists. **Cost:** a voiced show goes back to held. | cpb-k05 rows #2/#12; `adjusted.jsonl` |

### Summary of the (d) table

| | as-is | fresh-get |
|---|---|---|
| rows | 14 | 15 |
| stops a wrong, shifted or junk title (some with a cost noted) | 10 (buttholesurfers, DSO-2015, PLF-2007, railroadearth, signalpath, soulive, stringcheese, umphreys, charliehunter, dumpstaphunk; soulive and stringcheese stop a cant-tell duplicate) | 11 (the same, minus charliehunter, plus derektrucksband-2007-05-25 and steepcanyonrangers) |
| accepted cost, by ruling (all good shows held) | 3 (DSO-2004 Q1, lotus B3/B7, stevekimockband-2002-04-20 Q1) | 3 (DSO-2004 Q1, lotus B3/B7, gratefuldead-1989-07-19 Q1) |
| accepted cost, pending operator ruling | 1 (kinggizzardandthelizardwizard-2022-10-22, C2 via coverage) | 1 (the same) |
| other / unexplained | 0 | 0 |

**Good shows held.**
- Hand-checked-good S shows held:
  - lotus-2010-06-10 (both views). It is the one counted against the slice-1 bar.
  - stevekimockband-2002-04-20 (as-is, Q1; census S3 and U3 all-right) and gratefuldead-1989-07-19 (fresh-get, Q1; census S1 all-right). Each is a good show held that stops no wrong title. Q1 declines are excluded from the bar.
  - So the hand-checked-good count is 2 in each view (lotus plus the one Q1 show), 1 of which counts against the bar.
- Apart from the bar: DSO-2004's set 1 (Q1); the shows whose wrong title was stopped at the price of right neighbours (buttholesurfers #18, DSO-2015 #9-#11, PLF-2007 #1-#9 and #18); and kinggizzard, which was not hand-checked but whose new titles are taper-backed and whose hold stops nothing (pending ruling).

## Title changes on shows that stay unheld

| view | packaged | voiced | delivered |
|---|---|---|---|
| as-is | 7 shows / 30 positions (9 text, 21 source-only) | 3 / 3 (0 text) | 48 / 181 (147 text, 34 source-only) |
| fresh-get | 37 / 345 (284 text, 61 source-only) | 3 / 3 (0 text) | 49 / 184 (150 text, 34 source-only) |

By path:
- **As-is.**
  - Packaged text changes: D 4, C1 1, slice 4 1, unattributed 3.
  - Delivered text changes: +5 103, C2 30, D 9, C1 2, slice 4 1, unattributed 2.
- **Fresh-get.**
  - Packaged text changes: D 185, C1 68, C2 22, slice 4 8, +5 1.
  - Delivered text changes: +5 103, C2 32, D 9, C1 3, slice 4 1, unattributed 2.
- **Change since 415f8d7.** The fresh-get packaged row was 38 / 363 (308 text, 55 source-only). darkstarorchestra-2014-07-31 is now held, which removes its 18 text positions. Six deepbananablackout-2004-04-01 D titles (#2, #4, #8, #11, #14, #24), once their `--> ` or `^` is stripped, now equal the old setlist text, so they move from text to source-only.

Files: `r2/cmp-asis/title_changes.txt` (94240cd556361a14c347f68473965397a5fc12566a6c73ee7c0dc13fda438e88) and `r2/cmp-fresh/title_changes.txt` (bffcefe54ac572a56dd290a6c468453f1c434e0c3803d06f865de208dfd20efb).

## Needs-LLM

All of these are unchanged from 415f8d7.
- **Held needs-LLM.** As-is: base 188, candidate 186. Fresh-get: base 189, candidate 187.
- **needs_llm.txt, all states.** As-is: base 651, candidate 653. Fresh-get: base 880, candidate 858.
- **D shows that reach the agreement check's decline or the LLM branch.** As-is: 4 agreement declines and 27 in the LLM branch. Fresh-get: 4 and 39.

## Hand check

**Checkpoint B hand check (first measurement, 415f8d7).** Packets come from `title_hygiene_probe.py packets` over the first cmp-fresh (`accept/packets/strata_index.txt` sha256 f1b4490a61c1ca05ff1a5214791a92410adc3a153807fea16904765f44ff843d). There are 157 shows:
- every newly cleared, wholly untagged show with 3 or more D fills: 18;
- a newly cleared sample of 23. That is every other newly cleared show, since fewer than 60 exist; the sample is round-robin over path signature, not proportional;
- every delivered show with a changed title: 74;
- the Checkpoint B carries:
  - every slice-4 show: 16;
  - the 13 R16-admitted lists plus blindmelon-2008-06-24: 14;
  - a seeded, stratified 12 of the 33 shows where reader (ii) admitted a list that reader (i) rejected as non-contiguous: 12. The list `lists/readerii.txt` has sha256 310ab487…83d0, and r16.txt has sha256 fd4ead74…d84a.

The checking:
- **Checkers.** 12 Sonnet checkers (cpb-k01 to k12) worked to the class K brief `orch-r2/cpb-checker-brief.md` (sha256 53625a75…94bb). Their row files are pinned in `handcheck/rows.sha256`.
- **Pre-screen.** An Opus pre-screen re-judged all 87 wrong and cant-tell rows: the checkers had 84 cant-tell and 3 wrong. It also judged 135 calibration rows.
  - `adjusted.jsonl` (222 rows): ecf3844414e6821a17c0360967009b9c4cc46cb6bafe3753fb00e529e439020f
  - `tally.json`: d14284571932c365cd36db8711ed87e0f5c85d5678029f102dc4785bb8aeed00
  - pre-screen handback: 3226550dec5fe2ff277ac317dfecf389f615d6ecf6f25734837c7590a03724b6
- **Calibration.** 134/135 exact agreement and 135/135 agreement on "not wrong", recounted from `adjusted.jsonl`. The one difference is billystrings-2017-07-15 #11, which is right-partial rather than right.

**Fix-wave hand check (cpb-k13, at c49cdd1).**
- **Scope.** The 12 shows the fix wave changed, plus the 4 C-1 signature shows. DSO-2014 appears in both strata, so the file has 16 rows.
- **Pin.** Rows `handcheck/cpb-k13/rows.jsonl` have sha256 7e0cb0a8498489f650037e1c66997371df6c893f5a7879a91961d47de02eebc4. They are pinned separately from `rows.sha256`, which lists k01-k12.
- **Counts over 234 track rows:** right 190, right-partial 40, wrong 2, cant-tell 2.
- **Shows:** 0 shifted.
- **Findings:**
  - **darkstarorchestra-2014-07-31 is now HELD.** #3 is `unresolved`. Its true title, `Greatest Story Ever Told`, is the FLAC tag and the taper's `?`. The 2 cant-tell rows are this one track, counted once in each stratum. #4-#21 are 17 right and 1 right-partial (#10) in cpb-k13. C-1 works as ruled (B1).
  - **The two `wrong` rows are not a piece-3 path:** greenskybluegrass-2013-05-04 #11 `Jam` (should be Broke Mountain Breakdown) and #16 `Take Me Away` (should be Letters to Seymour). Both are **pre-existing delivered MP3 tags**. Piece 3 only stripped their artist prefix, and the pre-screen had already classed them as a pre-existing conflict. C2 cannot reach them: there are 21 files against a 22-entry description.
  - **lettuce-2002-07-13 #10 `Superfred` and #16 `Headin' Home (Josh Redman)` are RIGHT** (M-7). They match the Shorten tags and the taper's list. tedeschitrucksband-2019-02-15 and tedeschitrucksband-2020-01-15 are right.
  - **The new slice-5 strips damage no real title.** Right-partial residue remains: cowboyjunkies-2017-11-05 keeps a `NN - ` track-number leader on all 16 tracks, and guster-2006-07-28 keeps `(m:ss)` on all 19.
  - **One misread.** The checker judged zentricksters #19 right-partial from the packet's pre-fix column `(actually )`. The c49cdd1 arm ships `Banks of the Ohio (actually d2t10)` unchanged (the M-6 veto).

## The bar, as ruled

The bar is the Checkpoint B hand check after the pre-screen, with B2 applied: the two C2 conflicts are RIGHT.

| path | filled or replaced | wrong | cant-tell | wrong % |
|---|---|---|---|---|
| C1 | 86 | 0 | 0 | 0.0 |
| C2 | 91 | 0 | 0 | 0.0 |
| D | 341 | 0 | 0 | 0.0 |
| slice 4 | 22 | 0 | 0 | 0.0 |
| S | 2 | 0 | 0 | 0.0 |
| slice 5 (`+5`) | 355 | 0 | 0 | 0.0 |
| pooled | 900 | 0 | 0 | 0.0 |

The unit is a unique (show, track), and a track judged twice counts once. Pooled is the six path rows plus 3 changed-no-path tracks, all right.

- **C2 is 0/91 (B2).** The C2 conflicts are greenskybluegrass-2012-09-25 #9 and johnkadlecik-2017-10-31 #9; the pre-screen had judged both cant-tell. B2 counts them RIGHT: the operator's standing principle is that the description outranks the tags, and in each case the same taper's description and FLAC tag agree against the MP3 tag.
- **The fix wave adds no wrong title on any path.** cpb-k13 covers every track it changed: 0 wrong on a piece-3 path. Its 35 new `+5` tracks (cowboyjunkies 16, guster 19) are right-partial. The D cosmetic strips (deepbananablackout, darkstarorchestra-2011-04-15, joerussosalmostdead, mymorningjacket-2004-06-18) are right.
- **Shifted shows: zero.** None appears in either hand check. In the gate's untagged hand check, both shifted shows (billystrings-2023-06-10, derektrucksband-2003-11-26) and every some-wrong or cant-tell show are held in the candidate.
- **The pre-screen's one silent wrong title is fixed.** darkstarorchestra-2014-07-31 #3 was an unchanged wrong title on a newly cleared show. After C-1 (B1) the show is held (cpb-k13).
- **Slice 1 (at most 2 hand-checked-good S shows held, Q1 apart): met at 1** (B3). The one is lotus-2010-06-10. umphreysmcgee-2005-11-12 and steepcanyonrangers-2004-05-21 are justified holds, because their shifted tape tags are stopped.
- **Q1 declines, reported apart.**
  - Fresh-get: darkstarorchestra-2004-04-24 (set 1 good, sets 2-3 cant-tell), darkstarorchestra-2015-07-11 (bad, shifted), philleshandfriends-2007-10-20 (bad, shifted), gratefuldead-1989-07-19 (hand-checked all-right, census S1: a good show held).
  - As-is adds stevekimockband-2002-04-20 (hand-checked all-right, census S3 and U3: a good show held).
- **Right-partial: 63 tracks at 415f8d7, all with the right song.**
  - 59 are cosmetic residue. Ruling B5 strips most of the shapes the checkers named: D's `--> `, `^` and `$`, and a glued duration; slice 5's artist prefix, ` H2` and `Encore- `; and the `()` debris.
  - `E: ` stays by spec design.
  - 3 are abbreviations: `SOTM` via D, `O` via slice 4, and `MRG` via C2, which replaced "Mark's Red Guitar". Ruling B6 names only `MRG` via C2 and `O` via slice 4 as accepted documented limitations; it does not name `SOTM` via D.
  - 1 is a segue partial.
- **Caveat: the per-path bar is blind to a wrong title the path did not touch** (final review, Recommendation 3, `.superpowers/sdd/title-hygiene/final-rev/handback.md`: "note that the per-path 2% bar is blind to a wrong title the path did not touch, and that the whole-show hand-check rule is the guard"). darkstarorchestra-2014-07-31 #3 was exactly that case: an unchanged wrong title on a newly cleared show, which no path's rate counts. The whole-show hand check caught it, and that check, not the per-path rate, is the guard.

**The gate's final per-path numbers** (`~/.llama-harness/piece3/gate-r16/gate_table.md`, R1; sha256 in the Arms section; this is the gate's own hand-check join, which predates the fix wave, so it differs from the bar table above):

| path | tracks | judged right | judged wrong | judged cant-tell | wrong / judged |
|---|---|---|---|---|---|
| S | 59 | 53 | 4 | 2 | 7.0% |
| D | 464 | 411 | 0 | 0 | 0.0% |
| C1 | 136 | 22 | 0 | 0 | 0.0% |
| C2 | 118 | 20 | 0 | 0 | 0.0% |
| 4 | 22 | 2 | 0 | 0 | 0.0% |
| 5 | 422 | 97 | 0 | 0 | 0.0% |
| pooled (unique tracks) | 1235 | 617 | 4 | 2 | 0.6% |

- Slice-1 bar in the gate (R2, non-Q1 newly held good S shows): 2 (lotus-2010-06-10, steepcanyonrangers-2004-05-21); the ruled count (B3) is 1, with steepcanyon a justified hold.
- After Q1 and the split: bad shows caught 32, uncaught 5. Good shows losing S fills: Q1 declines 12, other 6.

## Checkpoint B rulings, as applied

| ruling | applied as |
|---|---|
| B1 C-1, preferred fix | 95c6bb2. The verbatim DSO-2014 fixture is pinned. In the r2 arms C-1 demotes on darkstarorchestra-2014-07-31 only (fresh-get, #3; `c_demoted` is empty in every other row of both arms). On the as-is view its #3 is an operator override, which C-1 never demotes, so nothing is demoted there. |
| B2 C2 conflicts count RIGHT | C2 0/91 (bar table) |
| B3 slice-1 good-S = 1 | bar met (bar section); umphreys and steepcanyon are justified holds in the (d) table |
| B4 I-1 | efafc8c. Every added hold is attributed to a decline's slice except kinggizzard, which is `unattributed` because C2 is a change, not a decline; its cause is slice 3 via coverage (see the (d) table; ruling pending) |
| B5 cosmetic constants, M-1 | 8cf89c5. Its changes are the 11 of the 12 parity mismatches that are not C-1; the twelfth is DSO-2014 (B1) |
| B6 abbreviations | documented limitation (MRG via C2, O via slice 4) |
| B7 reader gaps | documented limitation. They cost holds, not accuracy: lotus-2010-06-10 and railroadearth-2007-01-28 in the (d) table |
| B8 Fable's minors | c49cdd1 |
| B9 re-measure and (d) table | this file |

## C-1 false signature (open)

**The finding.** It is fixwave-rr Important #1 (`.superpowers/sdd/title-hygiene/fixwave-rr/handback.md`, sha256 d900b2f93db05a93de6fa24af3454d4bf9f8ef4d20597610a98136df218b11c7).
- The C-1 shift signature (delivered tags that disagree with the reference at their own position but agree at ±1, counted ≥ 2) is symmetric. It cannot tell "the delivered tags are shifted against a right reference" from "the reference is shifted against right delivered tags".
- **Reproduction**, at gather level with all slices:
  - The tape has 8 MP3 tags, all right. The FLAC has titles only on tracks 1 and 8. The description's numbered list is count-matched but shifted: it omits Sugaree and adds `Mama Tried`.
  - C-1 demotes tracks 2-6. setlist-gap then ships 5 wrong titles (`Deal, Loser, Jack Straw, Stella Blue, Mama Tried`) with `needs_review` False and no flag.
  - With slice 3 off, the same tape ships all 8 right titles.
- **Reachability** is unmeasured. The reproduction is synthetic: no library show is known to carry it.

**Measured library impact at c49cdd1** (r2 arms). C-1 demotes on darkstarorchestra-2014-07-31 only, and only on the fresh-get view, where `c_demoted` is [3]. Every other show in both arms has an empty `c_demoted`.

**Proposed narrowing.** Count only the signature positions that C itself confirmed: `sum(1 for i in delivered_shift if i in changed) >= 2`.
- It keeps DSO-2014, since 17 of its 18 signature positions are C2.
- It closes the reproduction.
- It changes no measured number.
- The trade-off: an uncorroborated shifted delivered set ships as it did before the fix.

**Status (replace this paragraph after the ruling):** awaiting the operator's ruling, relayed via llama-db, on the proposed narrowing. Until it is ruled, the code at c49cdd1 implements B1's literal signature, and the false-signature risk above is open.

## Suite

At c49cdd1, from the worktree venv, `./.venv/bin/python -m pytest -q -p no:cacheprovider` gives 4783 passed, 1 skipped, 8 deselected, 26 warnings (the fix-wave implementer's run; `llama.__file__` inside the worktree). At 174995e the orchestrator's re-run gave 4762 passed. The commit that adds this file is docs-only, and the code is unchanged since c49cdd1.
