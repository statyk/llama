VERDICT: RULE DEFECT (1)

acc-explain: independent Opus review of the newly held shows (Measurement 4), the 5 score misses and the one UNEXPECTED known disagreement (Measurement 1). Branch held-backlog-taper-markers @ 22f565a. Read-only: no code changed, no commits, nothing written under ~/.llama. Scratch scripts and output are in ~/.llama-harness/piece2/accept/work/acc-explain/ (dump.py, probe2.py is an instrumented compute_legs replay under this tree, preset3.py, notesveto.py).

The one defect is B4, stevekimockband-2000-03-31: a real unnumbered set ahead of `Set 1:` gets folded into set 1. Two other items are CONCERNs but not defects: A1 (the low-confidence test on owned shows uses align() coverage) and B5/notes (the veto never reads the unread `notes` field). Everything else is working as designed.

Extraction check. I recomputed the list from the arms (base outcome not held, cand outcome in {newly-held, still-held, still-held-package}) and got the same 10 shows. Across all 3,983 rows, exactly one show gets a gather or vet flag in the candidate that the base arm's own computation does not also raise: mymorningjacket-2018-03-05. For the other 9, every candidate flag is already in base's deterministic flags. They count as "newly held" only because base was needs-LLM, which keeps a show out of the held count. Title changes between the arms: 0.

## A. Newly held (10)

### A1. darkstarorchestra-2009-11-14 (delivered), deadandcompany-2015-10-29 (delivered), stringcheeseincident-2005-03-25 (delivered)
- **Facts.**
  - All three were stored with an `llm` alignment and no flags. In base they are needs-LLM, with gather flags that include `low-confidence structure alignment`.
  - In the candidate the taper owns the structure, so no LLM call is made. Each is now held by `low-confidence structure alignment` alone.
  - The owned structure equals the stored LLM structure at song level in all three:
    - DSO: breaks 9/20, encore at 21.
    - D&C: 7/16, encore at 17.
    - SCI: 11/17, encore at 18-19.
  - For D&C and SCI the taper also agrees with step 1, so the alignment stays `deterministic`. For DSO, step 1 had lost the encore (`was [9] ['1','2']`). The taper restores it, and the base jerrybase closer flag (`One More Saturday Night is not at a set break`) goes away correctly.
  - Measured coverages (step 1 / reader items via align()):
    - DSO: 0.476 / 0.714. The tags carry durations ("Drums > (04:27.01)"), so align() misses single-word titles. Placement still matches them through `title_components`.
    - D&C: 0.588 / 0.588. The tags carry a filename prefix ("Dead&Co2015-10-29i 01_ Playin'").
    - SCI: 0.737 / 0.474. The tags are clean. The taper lists a generic `Jam` in set 2 that setlist.fm omits. align() matches it far ahead, at tape track 8, and the walk cascades.
  - The stored LLM alignments scored 0.905 / 1.0 / 0.842. That is why these shows shipped clean.
- **Caused by this piece?** Partly. The flag itself is today's deterministic flag, and base raises it too. The piece removes the LLM call that used to clear it, then keeps the flag under the §4 rule: no anchoring, step-1 coverage under 0.8, and reader coverage under 0.8.
- **Intended?** Yes. This is spec §4 ("Low-confidence flag on a taper-owned show (my call)") together with the Constraints line "A taper-owned show must not reach the `align_structure` LLM fallback". gather.py:1396-1399 implements exactly that.
- **Verdict: as designed (CONCERN).**
- **For the acceptance record:** These three are correct taper-owned structures. Each equals the structure the LLM alignment shipped. They are held because §4 replaces the LLM's coverage check with align()'s coverage of the taper's own items, and align() undercounts here. DSO and D&C have duration or filename residue in their tags, and those titles are on air today, which arguably deserves a look anyway. SCI is a pure align() cascade on a generic `Jam` item. The hold is the conservative direction and ships nothing wrong. The cost is one overrule per show, and only if the operator chooses to re-gather these non-held shows. If false holds of this kind turn out to be common, the fix belongs in the spec: for example, using placement success instead of align() coverage on owned shows. It is not a branch defect.

### A2. joerussosalmostdead-2017-11-09 (packaged)
- **Facts.**
  - The description is null, so the markers come from `notes` (`Set One:` / `Set Two:` / `Encore:`). The owned breaks are 6/13 with the encore at 14, which equals the stored LLM structure. Step 1 had 7/13, one song off.
  - Reader coverage is 1.0, so the low-confidence flag clears.
  - The show is held only by 8 `research asserts unknown song` flags: Weather Report Part One, Lovelight, Lady With a Fan, Terrapin Refrain, The Eleven, Cast Your Fate, Tennessee Jed, Standing On The Verge. These are the taper's footnoted teases and jams. Base computes the identical 8 vet flags.
- **Caused by this piece?** No. The flags are vet-code drift since the stored vet; they are not structure. The piece only made the show replayable.
- **Verdict: as designed.**
- **For the acceptance record:** The taper's notes-sourced structure is right, and it corrects step 1's off-by-one set break. The hold comes from vet's unknown-song flags on teases. Base raises them identically. They have nothing to do with set markers.

### A3. joerussosalmostdead-2023-01-26 (packaged)
- **Facts.** `Set One (8:15PM - 9:38PM):` / `Set Two (10:15PM - 12:20AM):` / `Encore:` gives 6/13 with the encore at 14. That equals both the stored structure and step 1, so the alignment stays `deterministic`. Reader coverage is 1.0. The show is held only by `research asserts wrong date: January 26, 2022`, which base raises identically.
- **Caused by this piece?** No.
- **Verdict: as designed.**
- **For the acceptance record:** The structure is unchanged. The only hold is a pre-existing vet date flag that base also raises. The piece only made the show replayable.

### A4. mymorningjacket-2018-03-05 (delivered; the only show held by a flag the piece causes)
- **Facts.**
  - The taper writes `Set 1` (01-14), `Set 2` (01-21, numbered straight through from Victory Dance to Only Memories Remain) and `encore`. The filenames also put everything after set 1 under "set 2".
  - Step 1 (setlist.fm) had three sets, 14/24/34. The taper owns the show and ships 14/34 (`was [14, 24, 34] ['1','2','3','encore']`): tracks 25-34 move from set 3 to set 2.
  - Vet then raises `research asserts 3 sets but structure has 2`. The research cites Jambands: Set 1 *Evil Urges*, Set 2 *Circuital*, Set 3 *The Waterfall*, each album played in full. Tracks 15-24 are exactly *Circuital*'s 10 songs and tracks 25-34 exactly *The Waterfall*'s.
  - The tape has no intro or tuning track between Movin Away and Believe.
- **Caused by this piece?** Yes. The structure change produced the flag.
- **Is the 2-set structure right?** Probably not. setlist.fm and the Jambands writeup both say three sets. The taper tracked sets 2 and 3 as one continuous set. This is genuine contrary evidence against the tape.
- **Verdict: as designed.**
- **For the acceptance record:** The taper's own text, and its filenames, label *Circuital* and *The Waterfall* as one "Set 2". The rule faithfully ships that. setlist.fm and Jambands say three sets. The vet research flag is exactly the backstop the spec relies on (Non-goals: research flags clear when the structure is right, and "the harness shows the rest"). It holds the show, so the 2-set structure cannot ship on a re-gather without a human look. The operator picks between the taper (overrule) and three sets (`--set-breaks 14,24 --set-encore 34`). The show must also appear in report 3 as songs moved on a delivered show.

### A5. derektrucksband-2003-12-26, jackiegreene-2011-02-12, radiators-1991-01-18, soulive-2001-12-15 (all stored HELD; outcome still-held)
These were held before the piece and are still held. They appear on the list only because base was needs-LLM. In every case the candidate's flags are a subset of the stored flags.
- **derektrucksband-2003-12-26.**
  - Markers: `Set I` / `Set II` / `Set II (Cont.)` / `Encore:`. The owned breaks are 8/16 with the encore at 17. The stored structure was one set, 16. `Set II (Cont.)` is read as a continuation, as designed.
  - Two flags are cleared: `research asserts 2 sets but structure has 1` and `low-confidence`.
  - Still held by `unresolved track titles` (track 13, the 7/4).
  - Verdict: as designed, and an improvement.
- **jackiegreene-2011-02-12.**
  - `Set 1` holds items 1-7 and `Set 2` holds 8-17, ending "17.Sugaree.". There is no encore marker and no encore-like text, and step 1 (deterministic, `[8]`) had no encore, so ruling (d) does not apply.
  - Breaks are 7 (correcting step 1's 8), with track 17 in set 2. The stored LLM structure had track 17 as the encore.
  - Still held by 7 unknown-song vet flags; base raises the identical set.
  - Verdict: as designed under the operator ruling (no taper encore marker means the last set runs to the end).
  - Note for the record: ruling (d) is defined against step 1, not the stored LLM structure. So on a stored-LLM show, an encore that only the LLM (from setlist.fm) supplied is folded into the last set. That is the spec as written.
- **radiators-1991-01-18.**
  - Markers: `Set 1 Disc 1`, `Set 2 Disc 2`, `[Encore]`. Owned: set 1 is tracks 1-15, set 2 is 16-22, the encore is 23-25. That is exactly the taper's list. The stored structure had a single break at 19, aligned from a sibling description full of junk.
  - `low-confidence` is cleared.
  - Still held by 4 unknown-song vet flags. Base raises the same four, and they are stored flags. Two of those songs (Drinkin' Wine, Brown Eyed Girl) are in the taper's list but missing from the tape.
  - Verdict: as designed, and an improvement.
- **soulive-2001-12-15.**
  - Markers: `Set 1 disc 1` / `Set 2 disc 2`. Owned break at 5. The stored structure was one set.
  - Still held by the stored `unresolved track titles`. Unresolved track 10 falls in set 2, as the last set runs to the end.
  - Verdict: as designed.
- **For the acceptance record:** None of the four is newly held. They were already held, they stay held on a subset of their stored flags, and in three of them the taper replaced a wrong stored structure with the taper's own.

## B. Score misses (5)

All five are misses in the override-stripped arm only. In the real candidate arm, each carries an operator `set_breaks`/`encore_after` override, which wins, and outcome and structure are unchanged from base.

### B1. furthur-2012-07-08
- **Taper text:** `1st Set:` (Tuning, Hell in a Bucket … 8. Cosmic Charlie) / `2nd Set:` (9. Tuning … 19. Throwin Stones / 20. Donor Rap / 21 Sampson and Delilah). The word encore appears nowhere, in the description or the notes, and there is no `E` line.
- **Veto should have fired?** No. There is no encore-like text.
- **Today's step 1:** `[7]`, with no encore. The stripped arm's alignment is `deterministic`, so the taper's labels equal step 1's and ruling (d) does not apply.
- **Owned:** `[7]`, with Donor Rap and Samson in set 2.
- **Caused by this piece?**
  - The labels: no. Today folds the encore the same way.
  - The hold: yes. jerrybase's `set closer 'Throwing Stones' is not at a set break` becomes an operator note (§5: the taper's last song of set 2, Samson, differs from jerrybase's closer). So a fresh gather would ship this show clean where today it is held.
- **Who is right?** The adjudicator is right about the event: Samson was the encore (jerrybase, the sibling's `E:`, setlist.fm). The taper simply did not mark it.
- **Verdict: as designed.** This is the same class as the known disagreements derektrucksband-2005-01-09 and thedead-2009-04-29: "an encore the taper did not label … last set runs to the end". The evidence classification marked it `target_matches_marker: yes` because it judged only the set break.
- **For the acceptance record:** Under the operator ruling, the taper's unmarked encore folds into set 2, and the §5 closer demotion is exactly what lets that ship unheld. This is the accepted class. It should be scored as a known disagreement, not a miss.
- **CONCERN to record:** the documented limitations cover a misdated tape losing its jerrybase holds. They do not say that jerrybase's closer flag was the only thing catching an unmarked encore, and that the encore now folds silently on a taper-owned show.

### B2. greenskybluegrass-2014-02-28
- **Taper text:** `Set 1:` … `Road To Nowhere` / `Set 2:` … `Bringing In The Georgia Mail`, then a blank line, then `Drink Up and Go Home`. No encore word in the description or the notes.
- **Veto should have fired?** No.
- **Today's step 1:** `[11]`, with no encore. Same labels as the taper, so ruling (d) does not apply.
- **Caused by this piece?** No. The owned labels equal today's.
- **Who is right?** The target's encore rests on a blank line and a reviewer's `E:`. Blank lines are explicitly not markers (Non-goals), and reviews are not taper text. The target is probably right about the event, but nothing in the taper's text says so.
- **Verdict: as designed.**
- **For the acceptance record:** The taper wrote no encore marker, and today's structure has none either. The shipped labels are identical to today's. Score it as the unmarked-encore class.

### B3. darkstarorchestra-2007-05-17
- **Taper text:** `Set I` … `The Music Never Stopped` / `Set II` … `Good Lovin` / `E: I Fought The Law` / `E2: Don't Let Go**`. The encore is recognised: `E:` starts it and `E2:` continues it.
- **Owned:** `[8]`, encore at 16. Identical to the stored jerrybase-anchored 8/16, so the alignment is unchanged.
- **Cause of the miss:** shifted tags. Per the adjudicator, the disc-3 tags are one file late (each embedded duration matches the next file), d3t03 is Attics (which the taper's list omits), and d3t06 is untagged. Placement trusts the tag `E: I Fought The Law` on track 17, which is really Good Lovin. The jerrybase closer flags become notes as §5 says.
- **Caused by this piece?** No. The structure is identical to today's, and the show stays held by `unresolved track titles`.
- **Who is right?** Both. The taper's text is right about the songs, and the target is right about the audio. Once the adjudicator's retitles are applied, placement lands the encore after 17, which is the target.
- **Verdict: as designed** (out of scope: the shifted-tag defect, piece 5).
- **For the acceptance record:** The taper did mark the encore. The miss is the tape's tags being shifted by one file, which places every structure source one track early. The structure equals today's and the show stays held on titles.

### B4. stevekimockband-2000-03-31: RULE DEFECT
- **Taper text:** `Happy Hour Set:` (d1t01-06: Cissy Strut … Rainbow's Cadillac, then d1t07 Band Intros) / `Set 1:` (d2t01 Severe Tire Damage … d3t01 Berm) / `Set 2:` (d3t02 Tongue 'n' Groove … Golden Road, d4t05 Band Intros). No encore.
- **What the reader does:** `Happy Hour Set:` is not a recognised marker, and spec §2 says that when the first explicit marker is set 1, earlier lines are "header text and are ignored". So the reader's items start at Severe Tire Damage, and the six Happy Hour songs are dropped from its view. I confirmed this with `read_taper_structure`.
- **What placement does:** it checks only the 1|2 boundary (Berm 13 / Tongue 'n' Groove 14) and labels every track before it as set 1. The owned structure is `[13]`: tracks 1-13 in set 1, 14-19 in set 2.
- **Today's step 1:** `[6, 13]` with labels 1/2/3 (stripped note: `was [6, 13] ['1','2','3']`). That equals the adjudicator's target `[[6, 13], None]` and the taper's own three headers.
- **Caused by this piece?** Yes. The rule replaced a correct three-set structure with a two-set one. It silently erases a boundary the taper wrote (between the Happy Hour set and Set 1) and labels the Happy Hour songs as the taper's Set 1, which the taper's text contradicts. The stripped outcome is `clean-changed`, so on a fresh gather it would ship with no look.
- **Why this is a defect:** it hits the "taper break silently moved" anti-goal, and it breaks "exactly the taper's structure ships" / "the shipped labels are always the taper's". The implementation matches the letter of §2. The gap is in the rule: §2 assumed the ignored lines are banner text. Nothing checks the region before set 1's first song item. The set-like veto (ruling A2) is limited to numbered tokens inside an item of a numbered set, so an unnumbered `… Set:` header before `Set 1` passes.
- **Prevalence:**
  - Real candidate arm: 0 of 645 owned shows have a step-1 break before the taper's first set-1 song.
  - Stripped arm: 1 (this show).
  - The method was preset3.py, using stored tracks. 8 owned library shows do have non-filler tracks before the first set-1 song, but each agrees with today: gd1974-02-22's leading filler songs, zero-2008-08-08's pre-show `Fool on the Hill`, intros, and similar.
- **Suggested narrow fix** (needs a spec ruling; for the branch to choose):
  - (a) Treat a line carrying the word `Set` before the first recognised marker (`Happy Hour Set:`, `Acoustic Set:`, `Early Set`) as set-like text, giving `veto: set-like text`. Or:
  - (b) Decline (unplaced) when non-filler tracks precede the hit of set 1's first song item while today's step 1 has a break there.
  - (a) is the narrowest and matches what the spec already does for unrecognised encore and set text. Either way this show then computes as today, which here is correct.
- **For the acceptance record:** The taper wrote three set headers, but the reader recognises only `Set 1:`/`Set 2:` and discards the leading `Happy Hour Set:` block as header text. Placement then folds those six songs into set 1 and overrides today's correct three-set structure. That is a taper break silently erased, which the whole-or-nothing rule exists to prevent. It is a defect in the rule (§2's leading-lines clause), not in its transcription. It occurs once in the evidence and zero times in the live library.

### B5. thenewdeal-2005-04-29
- **Taper text (description):** `Set 1` (1-10) / `Set 2` (1. Navidrome … 11. Deep Sun / 12. Gone Gone Gone). No encore word in the description.
- **The item's notes:** "**About 45 seconds of crowd noise during the encore break was removed to allow all of set 2 to fit on one disc." The notes are not read because the description has markers, and the veto checks "the description and the notes, whichever was read". So this encore-like text is never seen.
- **Today's step 1:** `[10]`, no encore, with the same labels as the taper. Owned `[10]`, with Gone Gone Gone in set 2.
- **Caused by this piece?** No. The shipped labels are identical to today's, so the gap costs nothing here.
- **Who is right?** The target, which uses the sibling's `E: Gone Gone Gone` and these notes, is right about the event. The description, which the taper owns, does not mark it.
- **Verdict: as designed (CONCERN).** The spec is followed literally. But Plan Review Focus 1 ("never 'last set runs to the end' silently when encore-like text is present") is not honoured when the encore-like text sits in the unread notes field.
- **Measured over owned rows whose markers came from the description and that have no taper encore** (notesveto.py):
  - Real arm: 1. jackiegreene-2010-02-12, whose notes carry a bare `E` line before Sugaree. Its labels also equal today's: `clean`, no change.
  - Stripped arm: 1 (this show).
  - So the shipped impact is zero today.
- **Possible tightening for the branch, optional:** run the encore-like veto over the notes as well as the description that was read. It only makes the taper own less.
- **For the acceptance record:** The taper's description marks no encore, so the rule repeats the tape. Today's structure has no encore either, and the labels are identical to today's. The item's notes do mention an "encore break", and the veto does not read notes when the description supplied the markers. This is a recorded concern with zero measured shipped impact.

## C. gratefuldead-1970-05-15-spans (UNEXPECTED known disagreement)
- **Facts.**
  - The rows are identical in base, the candidate and the stripped arm: outcome needs-LLM (`align_structure`), gather flags `low-confidence structure alignment` and `tape spans 2 events`, vet flag `research asserts 3 sets but structure has 2`.
  - The taper does not own it (`one set`). Its markers are `(late show, acoustic Dead set)` and the like, which are deliberately non-markers (§1).
  - The stored show is held with the same three flags.
- **Held in substance?** Yes. `tape spans N events` is appended in compute_gather's multi-event block (`if kind == "spans"`), after and independent of the structure step. No LLM alignment result can remove it. The needs-LLM outcome only means the low-confidence branch would make an LLM call. Whatever that call returned, the show stays held by `tape spans`.
- **Caused by this piece?** No. The candidate equals base.
- **Verdict: scorer strictness artifact, not a departure.**
- **For the acceptance record:** The expectation is met. The show is held by `tape spans 2 events`, a deterministic hold no LLM can clear, and the taper does not own it. The scorer counts needs-LLM as not held. It should treat needs-LLM with a deterministic hold flag such as `tape spans` as held.

## Summary for the acceptance record
- **Measurement 4.**
  - Of the 10 shows the arms call newly held, 4 were already held and stay held on a subset of their stored flags.
  - 5 are held by flags base computes identically:
    - 3 by the §4 low-confidence rule on correct taper-owned structures (by design);
    - 2 by pre-existing vet flags.
  - 1 (mymorningjacket-2018-03-05) is newly held by a flag this piece causes. It is the vet research backstop catching a genuine taper-versus-setlist.fm/Jambands disagreement, by design.
  - Zero title changes.
- **Measurement 1 misses.**
  - furthur-2012-07-08, greenskybluegrass-2014-02-28 and thenewdeal-2005-04-29 are the accepted unmarked-encore class. The labels are identical to today's, though for furthur the §5 closer demotion means a fresh gather would ship it unheld.
  - darkstarorchestra-2007-05-17 is shifted tags (piece 5). The structure equals today's.
  - stevekimockband-2000-03-31 is a RULE DEFECT: an unnumbered `Happy Hour Set:` ahead of `Set 1:` is discarded as header text, and its songs are folded into set 1, overriding today's correct three sets.
- **Known disagreement gratefuldead-1970-05-15-spans:** held in substance; scorer artifact.
- **Concerns, not defects:**
  1. §4's low-confidence test on owned shows uses align() coverage, which tag residue and generic-item cascades depress. It produces false holds on correct structures; safe, but each costs an overrule.
  2. The encore-like veto never reads the unread `notes` field. Measured shipped impact is 0.
  3. Add to the documented limitations: on a taper-owned show with no encore marker, the jerrybase closer flag becomes a note, so an unmarked encore folds silently (furthur-2012-07-08).
