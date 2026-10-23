# Checkpoint A — title hygiene (piece 3), peer 24bca8e3

Branch held-backlog-title-hygiene HEAD 981be7d (clean; suite 4713 passed, 1 skipped, 8 deselected). Base worktree .claude/worktrees/title-hygiene-base HEAD 74ec267.

## Artifacts (pins)
- Gate table: ~/.llama-harness/piece3/gate/gate_table.md  sha256 b91464419885f225a599457c07dcfbbe1dd599efd8dc409ba9555871ab067a14 (U4b folded; hand-check dir ~/.llama-harness/piece3/gate/handcheck = evidence classes + U4b)
- Dump: ~/.llama-harness/piece3/gate/dump.jsonl  sha256 434ca3ba49109c1d1d9458c774cbd5785649677a86e7239b889fac29c0ac7633 (_meta sha f750d7d, 3983 shows)
- Pre-screen (Opus): .superpowers/sdd/title-hygiene/prescreen/handback.md  sha256 0792eea1c90e8720c805a1e2dd460d26b9e3c590dba37094877ff5e6335d8c8b
- Superseded table (U4 judged the census reader's candidate, not the arm): gate_table.u4-census-candidate.md

## Gate 0
3983/3983 fresh-get and 3983/3983 as-is (None counts as failing). Task 13's reviewer also widened it to whole-Track equality + the whole prelude: clean (cb.notes differs only by in-place aliasing, exact prefix).

## Headlines (R1, R2, R5, R13)
- R1 path view, judged wrong / judged: S residual 5/57 = 8.8% (fills identical to today: what S still ships, not slice-1 damage); D 0/411; C1 0/22; C2 0/20; slice4 0/2; slice5 0/97; pooled 5/621 = 0.8%. Inferred kept separate (59 right, 1 wrong).
- R1 ablation (all vs all-<slice>): slice1 171 tracks, 1 judged wrong (0.9%); slice2 483, 0; slice3 254, 0 (42 judged); slice4 22, 0 (2 judged); slice5 422, 0 (97 judged).
- S fills removed: 503 = 336 judged right (cost), 118 judged wrong (benefit), 26 cant-tell, 8 inferred wrong, 15 unjudged.
- R2: bad S shows caught 31, uncaught 6. Slice-1 bar "holds no more than 2 hand-checked-good S shows (excl. Q1)": 3 = gomez-2008-07-05, lotus-2010-06-10, steepcanyonrangers-2004-05-21 — MISSES by 1 (pre-screen: gomez is a check-3 defect, see P1; steepcanyon's hold is a benefit, tags shifted; only lotus is a clean cost).
- R5 Q1: 32 shows, 510 declined tracks; verdicts good 16, bad 13, cant-tell 3; newly held 4 (good 1, bad 1, cant-tell 2); the 1 silent bad show is now held. Ships silently (changed and unheld today): slice1 48/15, slice2 34/5, slice3 63/27, slice4 16/5, slice5 27/8.
- R13: 40 wholly untagged count-matched shows, all checked (U4b folded): good 27, bad 10, cant-tell 3.

## R14-R19 (verbatim from the table)
- R14: Bare-number S candidates: 52 track(s) on 11 show(s); the own-tag-core exemption decides 5. Over the hand-checked S rows (128 shows): 11 show(s), declines by verdict {good 7, bad 4}.
- R15: Extra show-level hygiene declines if every entry were judged (plan reading): 24 show(s) beyond the candidates; by check {trailing colon 5, header 1, timestamp 2, banner 2, over length 17, filename residue 9, no alnum 2}; verdicts (D/U) all 24 unchecked.
- R16: Lists inadmissible only because a numbering restart follows an `Encore` header: 13 show(s), 7 count-matched; all 7 unchecked.
- R17: C1 show-level declines: 12 show(s), 138 target(s), 0 would pass on their own (per-stem alternative); all 'C1 unconfirmed'. C1 adoptions via (c) where (a)/(b) disagreed: 0.
- R18: `agreement` 7 firings library-wide, 0 on hand-checked-right D/U shows; `written durations` 0 firings.
- R19: trailing `m:ss` strips: 12 candidates, all filled by D, all judged right (darkstarorchestra-2011-04-15 'Jack Straw \t\t 7:08' -> 'Jack Straw' etc.). No `1 Samuel 15:23`-type truncation fired.

## Pre-screen (Opus) — what changes the reading
- B (9 wrong tracks): 4 sound real S residual errors (deadandcompany-2016-07-15 t10, ericmcfadden-2005-10-06 t12 'II: ?', smashingpumpkins-2012-05-26 t12, karldenson-2001-03-08 t7); 2 sound-with-caveat (godspeed-2011-03-15 t4 '12-28-99' right-partial by the segue rule; rosehilldrive-2008-12-31 t7 right song shipped as '07-8th Wonder'); 3 unsound (belafleck-2003-04-12 t9 cant-tell, slice-5 and slice-4 inferred-wrong are right songs). Net: D, slice 4, slice 5: 0 wrong songs.
- R8 adjacent duplicate (13): 10 right declines, 1 false hold (DSO-2004-08-31 Jam/Jam across disc change, spec-accepted), 2 warranted holds.
- R9 agreement (7): 0 stopped a wrong fill; 5 inert; 2 FALSE HOLDS on A_rev-right fills (godspeed 2000-10-30/31: '12.28.99' vs setlist.fm aliases). R18's "0 on right shows" counts D/U classes only.
- R10 block size (3): 2 right, 1 false hold (railroadearth-2004-04-08, caused only by the encore fold). Encore fold "changes 52 shows" but 48 are tagged tapes where the check never runs; in practice 3 shows change: fold right on DSO-2005-06-04 and RRE-2004-04-09, no-fold right on RRE-2004-04-08.
- U4b: railroadearth-2019-04-08 all-right (21 D fills = filename songs; 'ISINMID' is the taper's shorthand for Farewell to Isinglass); elliottsmith-1997-05-15 stays held (D declined on tape agreement because t1's junk header tag counts as a real tag).
- Not touched by any slice: tag layers shifted against the description/FLAC (deadandcompany-2016-07-15 delivered with every MP3 tag one late).

## Decisions for the operator
1. Keep or DROP each slice (operator: an LLM adjudicator at ~1-2% of LLM spend is the alternative for a small-yield slice):
   - slice1 (S gate, Q1, split): removes 503 S fills (118 judged wrong, 336 judged right); catches 31 of 37 bad S shows; bar misses by 1 (3 vs 2).
   - slice2 (D): 483 tracks, 0 wrong of 411 judged.
   - slice3 (C1/C2): 254 tracks, 0 wrong of 42 judged (212 unjudged).
   - slice4 (short tags): 22 tracks, 0 wrong of 2 judged — small yield.
   - slice5 (cosmetic strip): 422 tracks, 0 wrong of 97 judged.
2. Plan readings: R15 (judge candidates only vs every entry: +24 shows held, unchecked); R16 (Encore-header restart inadmissible: 13 lists, 7 count-matched); R17 (C1 show-level all-or-nothing vs per-stem: 0 targets would pass alone, so no difference here); R10's encore fold (fold into the preceding block: right on 2 of the 3 shows it actually changes, wrong on 1).
3. Gate the trailing `m:ss` strip? (R19: 12 strips, all right, no truncation case fired.)
4. Constants: none shown misfiring on measured right shows except via the defects below; AGREEMENT_FLOOR's 2 false holds are alias-driven (P3).
5. Earlier plan readings carried for your ruling (predecessor's and mine):
   a. Task 3: reader (ii) bypasses reader (i)'s contiguity guard — 36 shows use a (ii) list while (i) says non-contiguous (Notes 2).
   b. Task 5: check 2 compares the cleaned candidate with the neighbour's RAW title; cleaning neighbours too would add 0 declines (alt_check2_cleaned).
   c. Task 8: C's "agrees" = loosely_same_title incl. its containment arm; containment-only C2 replacements: 0.
   d. Task 9: slice-4 entry matches the tag core OR its shipped short-tag form; `Filler:` entries confirming slice-4 tags: 0.
   e. Task 11: wholly-untagged count / 2b demotions include override positions (as today).
   f. Task 13: R4 stricter non-chosen S alternative — gap_span-literal (3 shows/13 tracks dropped, 2 good held, 0 bad stopped) vs both-sides (5/15, 3 good held, 0 bad stopped). Neither stops a bad show.
   g. Task 4/6: rosehilldrive `07-8th Wonder` keeps its `07-` because the entry leader `_ENTRY_LEADER` (a Global-Constraints constant) needs a non-digit after it; 4 D fills start with a number (3 are real date titles '12.28.99').
   h. Notes 3a: 40 lone-`?` texts pass check 1 (they are per-track slot-placeholder declines, as specified); Notes 7b: 22 C1 fills on 7 shows end in a taper marker ('Dark Star->', 'Funky Miracle >').
6. Proposed rule-defect fixes from the pre-screen (each changes declines; I have NOT applied them — say go/no per item):
   P1. check 3: a slot-placeholder entry (`???`) counts as disagreeing with an independent title; make it neutral (gomez-2008-07-05; fixing it meets the slice-1 bar at 2).
   P2. check 1 / S: `II: ?` passes because a leading set prefix is not stripped before the `?`-only test (ericmcfadden-2005-10-06 t12, an uncaught bad S show).
   P3. agreement check: 2 false holds from setlist.fm aliases (godspeed 2000-10-30/31); rule on whether to accept.
   P4. D tape-agreement fired on a junk header-fragment tag (elliottsmith-1997-05-15 t1 '15.97 - ej�s - portland, or') that passes is_real_title; accept as a limitation or rule a fix.

On your rulings: Task 15 applies drops/reading changes/approved fixes (fixes go back to the owning task with tests), then Steps 4-6 re-run.
