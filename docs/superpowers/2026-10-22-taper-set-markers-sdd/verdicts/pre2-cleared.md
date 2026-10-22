VERDICT: NO RULE DEFECT. 3 CONCERNs: derektrucksband-2004-04-15 (major), corblund-2004-11-04, yondermountainstringband-2006-07-04 (minor).

pre2-cleared: Opus pre-screen of report 2 (taper_cleared.txt, 8 shows). Branch held-backlog-taper-markers @ 22f565a. Arms: ~/.llama-harness/piece2/accept/{base,cand}.json. Read-only; no code changed, nothing committed. Scratch scripts and dumps: ~/.llama-harness/piece2/accept/work/pre2-cleared/ (dump.py, desc.py, reader.py, out1.txt, desc1.txt).

Summary
- This piece caused 4 of the 8: corblund-2004-11-04, derektrucksband-2004-04-15, derektrucksband-2008-10-23, yondermountainstringband-2006-07-04. All 4 are taper-owned, `structure-changed`, would be needs-brief, and are on `structure_changed_list.json`.
- The other 4 (darkstarorchestra-2004-11-14, johnkadlecik-2021-11-28, northmississippiallstars-2010-03-11, themotet-2013-04-20) are verified identical in both arms. Base and cand records differ only in the harness-only keys (`sets`, `filler`, `taper_owned`, `taper_reason`, `taper_source`, `step1_alignment`). Both arms: outcome `needs-brief`, `set_changes` [], `set_breaks` null, the same flags and notes. Something before this piece clears them (base = main @ a26c4d1). They are on `predicted_list.json`/`pilot_list.json`.
- The list is complete. Of the 338 stored-held shows, exactly 4 are `structure-changed` and 4 are `needs-brief` in cand. Every other stored-held show is still held or needs-llm.
- **No jerrybase flag became a "(taper's markers)" note on any of the 8.** Corb Lund, Derek Trucks Band, Yonder Mountain and John Kadlecik have no jerrybase rows (`is_family_artist` False, `lookup` []). DSO 2004-11-14 is in jerrybase but is not taper-owned. So the date check (item 3) applies to none of them. I still sanity-checked the dates of the 4 caused shows (below).
- The structure on all 4 caused shows is exactly the taper's, on the right tracks:
  - It equals the adjudicator's target on each one that has a verdict (corblund `--set-breaks 12,26`; DTB 2004-04-15 `--set-breaks 8 --set-encore 16`; YMSB `--set-breaks 12 --set-encore 26` in current numbering). DTB 2008-10-23 has no verdict; there the structure matches the description line for line.
  - No encore that ships today is lost. Today's encore stays on the same tracks for both DTB shows; YMSB gains the taper's encore; Corb Lund has none in either arm.
  - Zero title changes and zero segue changes on all 4.
- I re-ran `taper.decide_taper` and the reader read-only on the stored tracks. Placement gives the same boundaries as the cand arm: corblund (12, 26), DTB 2004 (8, 16), DTB 2008 (9, 16), YMSB (12, 25). Reader coverage is 1.0 on all 4, so dropping `low-confidence structure alignment` on the two DTB shows follows section 4.

---

corblund-2004-11-04
- Caused by this piece: YES. Base `still-held` with gather `single-set structure for a long show (160 min)` and vet `research asserts 3 sets but structure has 1`. Cand `structure-changed`, gather [] and vet []. alignment deterministic -> taper; note `set breaks from the taper's markers (was [] ['1'])`.
- Completeness: OK. The description says "Three Sets" and lists `Disc/Set1` 01-12, `Disc/Set2` 01-14, `Disc/Set3` 01-11 = 37. The tape has 37 tracks (d1t01-12, d2t01-14, d3t01-11), 160.1 min, nothing excluded. Not tagged partial-tape.
- Date: n.a. for jerrybase (no rows). But the item date is 2004-11-04 while the description says "November 5, 2004". The adjudicator marked the date flag `undecidable` and left the call to the operator ("if he picks 11-05 add --set-date 2004-11-05, if 11-04 then --overrule"). That flag (`research asserts wrong date: November 5, 2004`) is already gone in the BASE arm (adjacent-day context, Tier 1 4b), not removed by this piece. Once this piece removes the last structure holds, the show clears with that question never put to the operator.
- Structure: OK. Set 1 = 1-12 (… Okie From Muskogee), set 2 = 13-26 (Roughest Neck Around … Always keep An Edge on Your Knife), set 3 = 27-37 (Workin' Man Blues … On The Road Again). No encore: the taper marks none, and nothing in the text triggers the veto ("encode" is not "encore").
- Removed flags: both are structure flags that the taper structure resolves. Nothing that should keep it held.
- Verdict: CONCERN. The rule is right. The operator should decide 11-04 vs 11-05 before apply, because clearing pre-empts the date call the adjudicator reserved for him. The titles of tracks 1 and 34 ship as "Gonna) Shine up My Boots" (the tag dropped the paren). That is pre-existing, not this piece.

darkstarorchestra-2004-11-14
- Caused by this piece: NO. Identical in both arms apart from harness keys: `needs-brief`, gather/vet [], notes []. Cand is not owned: `unplaced: 2|encore last song 'Playin' matches 2 tracks`. That is section 3's repeated-title decline, working as specified (Playin > track 18 and the Playin reprise track 20).
- Completeness: OK. 21 tracks, 147 min, matches the 21-item description (adjudicator: "21 = 21").
- Date: n.a. (not owned, so its jerrybase flags are computed as today).
- Structure: unchanged from stored, and stored is WRONG, but not because of this piece. Tracks 1-19 are labelled set "2" and 20-21 encore (jerrybase's partial row: set 2 closer So Many Roads plus the encore). The taper's and the adjudicator's target is set 1 = 1-10, set 2 = 11-20, encore = 21.
- Verdict: OK for this piece. Hand-check item: it is on predicted_list.json.

derektrucksband-2004-04-15
- Caused by this piece: YES. Base `needs-llm` (`align_structure`, `stored alignment llm`) with gather `low-confidence structure alignment` and vet `research asserts 2 sets but structure has 1`. Cand `structure-changed`, would be needs-brief, needs_llm [], flags []. alignment llm -> taper (the section 7 relaxation); note `set breaks from the taper's markers (was [16] ['1', 'encore'])`.
- Completeness: PARTIAL. It is one of the 10 named partial-tape shows, and the adjudicator's action kind is **"hold"**. The selected item's notes say: "** - missing nearly 2 mins of this one due to turning my Edirol UA-5 off accidently with my knee, trying to supply a patch. Reboot was needed." The ** is on "1. Hey Driver **" in Set II. Hey Driver runs 637 s on this tape against 746 s (12:26) on Huffy's sibling dtb2004-04-15.pvm480s.flac16, so about 110 s is missing. Everything else is present (17 of 17 songs, 131 min). The adjudicator's rationale reads: "Operator decides: air this tape with the step above (correct titles and sets, one song with a ~110 s hole), or re-select Huffy's complete sibling (same Set 1/Set 2/E: structure; its d1t09 is a 17:42 WZKR radio interview that would need excluding)."
- Date: n.a. for jerrybase. Both tapers agree on 2004-04-15, Hal and Mal's, Jackson MS.
- Structure: OK. Set 1 = 1-8 ("Set I:" Jackson Soul Stew … Vol. Slavery), set 2 = 9-16 ("Set II:" Hey Driver … Afro Blue), encore = 17 (the bare `encore` line, "9. Gonna Move"). This is exactly the adjudicator's `--set-breaks 8 --set-encore 16`, and the encore stays where it is today.
- Removed flags: both are structure flags, rightly removed. But they were the only thing holding a tape the adjudicator wanted held for a selection decision, and llama has no flag for the dropout.
- Verdict: CONCERN (major). This is not a rule defect: the dropout is not structure, and the taper rule did exactly what the spec says. But applying `structure_changed_list.json` with `--allow-structure-change` would ship a tape with a known ~110 s hole, with no human look. Exclude it from the apply list or decide the selection first.

derektrucksband-2008-10-23
- Caused by this piece: YES. Base `needs-llm` with gather `low-confidence structure alignment`, `setlist evidence shows multiple sets but alignment found none`, and vet `research asserts 2 sets but structure has 1`. Cand `structure-changed`, would be needs-brief, all flags cleared. alignment llm -> taper; note `(was [] ['1'])` (step 1 had no encore; the stored LLM had [16] 1/encore).
- Completeness: OK. The description and notes list `Disk 1 Set 1` 1-10 and `Disk 2 Set 2` 1-8 plus "Encore: 9 Leavin' Trunk" = 19 items. On the tape, d1t04 "Band intros" (69 s, excluded as implausibly short) is gone and the other 18 are present, 129 min. Not tagged partial-tape, and there is no adjudicator verdict for this show.
- Date: n.a. for jerrybase. The notes header reads "Music Center at Strathmore, N. Bethesda, MD / 10/23/2008", matching the item.
- Structure: OK. Set 1 = 1-9 (Volunteered Slavery … Drums > My Favorite Things), set 2 = 10-16 (Chicken Robber … Anyday), track 17 "crowd" (filler) and track 18 Leavin' Trunk = encore. The filler goes with B, as specified; today it is also encore. Today's encore is kept, and segues are unchanged (Drums > stays).
- Verdict: OK.

johnkadlecik-2021-11-28
- Caused by this piece: NO. Owned (`taper_owned` true) but its labels agree with step 1, so alignment stays deterministic and no note is written. Otherwise identical in both arms: needs-brief, flags [], notes []. The stored `research asserts unknown song: …` flags are curly-apostrophe cases that base already clears.
- Completeness: OK. 15 songs, 140 min. The excluded walk-on, set break, encore break, intros and thank-you files are non-music.
- Date: n.a. (no jerrybase rows; no notes).
- Structure: OK. 1-7 / 8-14 / encore 15, the same as stored [7, 14].
- Verdict: OK. The reader reads the personnel and URL lines after the encore as encore items. Placement never uses them and they cannot place a boundary, so this is harmless.

northmississippiallstars-2010-03-11
- Caused by this piece: NO. Not owned (`one set`: the description marks only an encore). Identical in both arms; the `accepted short tag title: track 12 'ML'` note (2a) is in both.
- Completeness: OK. 23 tracks, 140.6 min, matches the adjudicator's "identical track list" with the sibling.
- Date: n.a.
- Structure: unchanged from stored: set 1 = 1-20, encore = 21-23 (it follows the sibling's "E: Keep The Devil Down"). The adjudicator called that defensible.
- Verdict: OK for this piece. Track 23 still ships as the title "unknown_title" (adjudicator: "Capricorn Briarpatch" from the sibling). That is pre-existing.

themotet-2013-04-20
- Caused by this piece: NO. The structure is an operator override (stored `source: override`), so the taper step never runs (`taper_source` null). Identical in both arms.
- Completeness: OK. 14 songs, 137 min; the intro, banter, announcement and encore-break files are excluded correctly (adjudicator).
- Date: n.a.
- Structure: the stored override, unchanged (one set 1-13, encore 14).
- Verdict: OK for this piece. The hold was a brief-guard flag (`briefing claims 2 sets but structure has 1`). `needs-brief` only means the replay cannot judge a fresh briefing, which may raise it again.

yondermountainstringband-2006-07-04
- Caused by this piece: YES. Base `still-held` with vet `research asserts 2 sets but structure has 1`. Cand `structure-changed`, would be needs-brief, flags []. alignment deterministic -> taper; note `(was [] ['1'])`.
- Completeness: OK, with one small gap. The description lists "Disc 3: Freebird Tease" (d03t01, 68 s), which the junk filter excludes as implausibly short. The adjudicator's fix re-admits it with `--include`. The sibling (Mayfield, SampsonC02s) folds it into Too Late Now. Runtimes otherwise agree: Matrix 144.9 min including the tease vs sibling 143.9 min, set 2 at 5315 s vs 5130 s. Not tagged partial-tape.
- Date: n.a. for jerrybase. Both tapers say 2006-07-04, Moonlight Garden(s), Cincinnati.
- Structure: OK. Set 1 = 1-12 ("Set 1: Disc 1:" Intro … Sidewalk Stars; Intro is filler), set 2 = 13-25 ("Set 2: Disc 2:" Chit-Chat … Traffic Jam; Chit-Chat and Crowd Surfin Comments are filler and stay in set 2), encore = 26 ("Encore:Two Hits and the Joint Turns Brown"). This equals the adjudicator's `--set-breaks 12 --set-encore 26` (his numbering adds the re-included tease, so his encore is track 27). The sibling has the same break and encore.
- Verdict: CONCERN (minor). The structure is right. The show clears without the taper-listed 68 s Freebird Tease that the adjudicator's own fix restored. Pre-existing and independent of this piece: the adjudicator rated it `show_correct_after_action: unsure` because the two tapers split the d02t05-t07 titles differently ("only a listen would settle").

---

Things the operator's hand check should look at

1. **derektrucksband-2004-04-15: decide before apply.** The adjudicator's action was "hold" over a known ~110 s dropout in Hey Driver (selected item notes: "missing nearly 2 mins of this one … Reboot was needed"). The choice is to air it as is, or to re-select dtb2004-04-15.pvm480s.flac16 and exclude its d1t09 WZKR interview. As things stand, `reapply --from-list structure_changed_list.json --allow-structure-change` ships it with no look. The title also ships with the footnote marker, "Hey Driver **".
2. **corblund-2004-11-04: the date.** The item says 2004-11-04 and the description says "November 5, 2004". The adjudicator reserved this call ("undecidable", needs a gig listing). The date flag was already dropped in base, so this piece's clear is the last gate. Separately, tracks 1 and 34 ship as "Gonna) Shine up My Boots".
3. **yondermountainstringband-2006-07-04:** consider `llama fix … --include ymsb2006-07-04d03t01.Matrix.mp3` (the Freebird Tease) before or after apply. The structure needs no change.
4. **darkstarorchestra-2004-11-14** is on predicted_list.json (not caused by this piece). It would re-brief with tracks 1-19 labelled set "2" (a wrong jerrybase anchoring onto a partial row) and with duration-laden titles ("LTGTR, (04:32.18)", "Encore: Sing Me Back Home (09:06.33)"). The adjudicator's fix is `--set-breaks 10 --set-encore 20` plus the clean titles. The taper rule rightly declines it, because Playin' repeats across the set 2/encore boundary (a documented limitation).
5. **northmississippiallstars-2010-03-11** (not caused by this piece): track 23 ships titled "unknown_title".
6. **The two stored-`llm` DTB shows** were made replayable by the section 7 relaxation. Both have zero segue changes, and both keep today's encore tracks.
7. A reader observation, not a defect: trailing prose after the last set becomes items of that set. Examples are corblund's "Please share but NEVER EVER encode to mp3 or other lossy formats." (set 3) and JK's personnel and URLs (encore). Such items can only make placement decline (no track matches them, or the other-side check fires); they never place a boundary, and coverage is per track, so they do not lower it. No wrong outcome came from this in these 8.
