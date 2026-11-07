# Adjudicator pilot review (Checkpoint B, step 3): Opus reviewer

Sources checked, all read-only: the pilot records (`~/.llama-harness/adjudicate-pilot/{opus,sonnet}/*.json`), each show's `show.json`, `overrides.json`, `selection.json`, `research.md` and `briefing.md`, the cached archive.org metadata (`~/.llama/cache/md_<id>.json`: descriptions and original-file tags), the setlist.fm cache (`slfm_*`) and the prototype verdicts. Nothing was written outside `pilot-review/`. The stale scan ran `gather.final_kept` as a pure read, from a scratch cwd with `PYTHONDONTWRITEBYTECODE=1`.

**Headline.** Opus made 48 auto-applicable edits. 43 are correct and 5 are wrong in effect: one show, infamousstringdusters, where five title-bar overrules would air four "Track N" placeholder titles. Sonnet made 50. 33 are correct and 17 are wrong, across two shows: yondermountainstringband would air a 30-minute side-project duo set as the Yonder show, and gratefuldead-1971-12-01 breaks the partial-with-better-sibling hold ruling. **Sonnet fails the acceptance bar and Opus passes it literally.** Two deterministic vetoes (section 3) would block all three wrong shows and leave every correct auto-apply in place.

---

## 1. Auto-apply review (every edit in compare.md's "Auto-apply list")

Identical edits on one show are grouped. The count is the number of edits.

### Opus (48 edits: 43 correct, 5 wrong)

| show | edits | verdict | evidence checked |
|---|---|---|---|
| buttholesurfers-1987-11-07 | 9 research-song overrules (Something, Rocky, Sweat Loaf, Ricky, Graveyard, Paranoid, 100 Million People Dead, Backass, Julio Iglesias), quote "1. Cherub" | CORRECT | Description: `"1. Cherub 2. Gary Floyd 3. Psych 4. Pittsburg to Lebanon 5. John E. Smoke 6. JIMI (cuts)"`. research.md: setlist.fm lists these 9 before Cherub, so "your six-song recording is songs 10–15". |
| buttholesurfers | Psychedelic Jam overrule ("3. Psych") and Pittsburgh to Lebanon overrule ("4. Pittsburg to Lebanon") | CORRECT | research.md: "setlist.fm calls this 'Psychedelic Jam'". The second is a spelling variant. |
| buttholesurfers | 22 Going on 23 and X-Ray overrules ("6. JIMI (cuts)") | CORRECT | setlist.fm has both after Jimi, and the taper marks JIMI as cut. |
| littlefeat-1977-08-08 | structure-bar overrule "multiple sets but alignment found none" | CORRECT | setlist.fm cache: set 1 ends `...Dixie Chicken, Tripe Face Boogie`, then encore 1 is `Willin', Don't Bogart Me, Willin', Feats Don't Fail Me Now, Rocket in My Pocket, Spanish Moon` and encore 2 is `Teenage Nervous Breakdown`. The tape ends at "9. Tripe Face Boogie (cuts)", so it holds one set. |
| littlefeat | 6 overrules quoting taper lines (All That You Dream, Skin It Back, Walkin' All Night, Fat Man, Red Streamliner, Oh Atlanta) | CORRECT | Description: `"Walkin' All Night Fat Man In The Bathtub Red Streamliner Oh Atlanta 1. A Day At The Dog Races All That You Dream Skin It Back 2. ..."`. These are unnumbered (missing) or inside track 1. |
| littlefeat | Spanish Moon, Willin', Don't Bogart overrules (quote "Unnumbered tracks are missing") | CORRECT (weak quote) | All three are setlist.fm encores, which are not on the tape. The quote does not name the songs. |
| littlefeat | Rock and Roll Doctor overrule ("Rock & Roll Doctor") | CORRECT | Alias of track 6. |
| **infamousstringdusters-2010-10-15** | 5 research-song overrules (Count Me In "3. Track 3", Get On With It "9. Track 9", Dream You Back "11. Track 11", Sunny Side "12. Track 12", Well, Well "8. Fork In The Road") | **WRONG (title surface)** | show.json ships titles `Track 3`, `Track 9`, `Track 11`, `Track 12`, and `is_placeholder_title("Track 3")` is True. Track 8 repeats "Fork In The Road" (402 s against 234 s for track 2). These five flags were the only thing holding the show. The trial apply recorded `status: applied, held: False`, so four placeholder titles would air. Opus's reasoning ("'Track N' counts as a real title") misreads the prompt's line about the "Track 9" false-demotion. Sonnet held it, and so did the prototype ("research-right-show-wrong"). |
| soundtribesector9-2000-09-26 | 10 set_title edits from original tags | CORRECT | Cached original tags: `01…flac Squares & Cubes`, `02 Itzamana`, `03 Kamuy > Hubble >` (1800 s), `04 TWELVE >`, `05 TWELVE >`, `06 Water Song >`, `07 Evasive Maneuvers >`, `08 EB >`, `09 EB`, `10 Bossa Profundo`. The shipped titles were setlist.fm titles laid one per file (Hubble on 04, Space on 09), which were wrong. Every quote matches the tags. |
| joerussosalmostdead-2019-06-15 | briefing-set overrule (medium bar) | CORRECT | Description: "One Set (1:10AM - 3:27AM)". briefing.md also says "one late-night set", so the flag misreads the briefing. |
| moe-2004-10-31 | briefing-set overrule (medium bar) | CORRECT | Description has Set 1, Set 2, Set 3 and an Encore. briefing.md: "two Nashville-style sets followed by a third set" and "three full sets and an encore". |
| themotet-2013-04-20 | 6 briefing-song overrules (medley parts) | CORRECT | Description: "Weed Medley-Pass The Dutchie-Legalize It - Mary Jane", "PFunk Medley-Handcuffs-Mothership-Tear the roof off". |
| themotet | briefing-set overrule | CORRECT | briefing.md: "one long set of about two and a half hours, plus an encore", and "Do not describe the show as two sets". |

### Sonnet (50 edits: 33 correct, 17 wrong)

| show | edits | verdict | evidence checked |
|---|---|---|---|
| buttholesurfers | 13 research-song overrules | CORRECT (11 with an irrelevant quote) | The conclusion matches Opus. But 11 of the 13 quote "JIMI (cuts)" as evidence for songs played *before* Cherub. The gate accepted a quote that does not support the claim. |
| littlefeat | structure overrule plus 10 title-bar overrules | CORRECT | Same as Opus. Four of them rest only on "Unnumbered tracks are missing". |
| **gratefuldead-1971-12-01** | structure-bar overrule "structure has 1 sets but jerrybase shows 2" (quote "Set 2:") | **WRONG (breaks a ruling; not a factual air error)** | The selected item is a set-2-only SBD: 11 tracks, Ramble On Rose through Not Fade Away. The AUD sibling `gd71-12-01.aud.minches-vernon` keeps 23 tracks (the full show, Truckin' through One More Saturday Night plus set 2). Operator ruling: "Partial tape whose better sibling fails the auto-switch bar: hold". Sonnet declared `better_sibling: null` ("not clearly better") and overruled. The trial apply cleared the hold. Set 2 as aired would be correct, but the ruling says hold and propose. The prototype also held it. |
| **yondermountainstringband-2009-07-11** | structure-bar overrule "low-confidence structure alignment" (quote "Duration:  29min") plus 15 research-song overrules (all quoting "30db (Jeff Austin and Brenden Bayliss)") | **WRONG (strict: wrong performance)** | The selected item `ymsb2009-07-11.u89i_211` is described as "30db (Jeff Austin and Brenden Bayliss) … Duration: 29min, 01. Lick #6 … 06. Always Up". That is a side-project duo set. Its sibling `ymsb2009-07-11.u89i_16bit`, from the same rig, is "Yonder Mountain String Band … Duration: 1hr, 29min, 01. Casualty … 18. Peace Of Mind" (18 kept tracks against 6). Sonnet's rationale: "the show ships as is". It would air a 29-minute duo set as Yonder's All Good show. Opus proposed the switch, and the prototype held it as wrong content. |
| joerussosalmostdead, moe, themotet | 9 medium-bar briefing overrules | CORRECT | Same evidence as Opus. One themotet set-count overrule quotes the PFunk medley line, which is irrelevant, but it passes at the medium bar. |

**Wrong auto-applied edits on the strict surface:**
- **Opus:** infamousstringdusters, 5 title-bar overrules. These are not title fills, so the literal bar does not count them. Their effect is to air placeholder titles.
- **Sonnet:** yondermountainstringband (1 structure-bar overrule plus 15 title-bar overrules: the wrong act airs) and gratefuldead-1971-12-01 (1 structure-bar overrule against the ruling).

**Gate weakness behind several of these.** A title-bar or structure-bar overrule passes on any substring-valid quote of the right *kind*, even when the quote has nothing to do with the flagged song. Sonnet used one quote 15 times on Yonder and "JIMI (cuts)" 11 times on buttholesurfers.

---

## 2. Disagreements

1. **darkstarorchestra-2010-07-02.** Both hold, so both are safe. **Opus is more useful.** Its proposal (break after GDTRFB d1t10, encore Johnny B Goode after Evan's Rap) follows the disc split and the recreated 9/28/76 running order. The gate correctly kept it at medium confidence because disc numbers are the only taper-side marker. Sonnet raised a real point Opus missed: `d1t01-Tuning` (232 s) and `EvansRap` (220 s) are kept non-music, nearly 4 minutes of tuning on air.
2. **waynehancock-2004-04-08.** Both malformed with the same edits, so neither arm is at fault (see section 5). Opus's structure (no set break, encore Everytime) follows the "discs are not sets" ruling better than Sonnet's break after disc 1.
3. **discobiscuits-2002-10-02.** **Opus is right.** Its switch proposal to the full-show `db2002-10-02.shnf` (13 against 6 kept tracks) is correct, and the gate blocked it only because the show is station-marked. Sonnet's verdict carries the same switch but went malformed (section 5).
4. **gratefuldead-1971-12-01.** **Opus is right.** It held with a switch proposal to the full AUD and the decision written out ("choose between the soundboard's partial Set 2 and the lower-quality full show"). Sonnet's auto-overrule breaks the ruling (section 1).
5. **gratefuldead-1982-04-14.** Both diagnose correctly that the SBD files the encore U.S. Blues as d1t11 after Bertha (description: "…Johnny B. Goode, E: U.S. Blues"), and both hold. **Opus is more useful** because it stores a one-key switch proposal to the Griesman matrix. Sonnet gives the same options in prose only.
6. **thenewdeal-2004-11-26.** Both are right to propose switching to the titled sibling `tND2004-11-26`; the tubes copy is untitled, with French numerals only. **Opus is slightly better** because its date overrule is also correct (research.md: "the day after Thanksgiving 2004 (Thursday, Nov 25)" is a calendar aside).
7. **yondermountainstringband-2009-07-11.** **Opus is right** (switch to u89i_16bit, Yonder's full set). Sonnet is wrong and would auto-apply (section 1).
8. **hollybowling-2019-09-12.** Both are right on structure: the s1/s2 filenames plus the "Encore Break" track. Opus adds three titles taken only from reviews, so they are proposals, and the gate correctly kept them propose-only. One of them is imprecise: s1t03 gets "Fast Enough for You", but the review says that song starts about 3 minutes in. Sonnet's caution is the more accurate reading. Both are safe.
9. **infamousstringdusters-2010-10-15.** **Sonnet is right** (hold: the review-only IDs need a listen). Opus is wrong (section 1).
10. **philleshandfriends-2007-10-20.** Both held. **Opus is better.** Its 18-file mapping of the taper's list onto the blank-tag md421 files is right on count (7 + 11) and checks out against sibling durations: Bird Song 786.58 against 786.29, Bertha 543.26 against 544.01, the Viola suite as one 1878 s file. It keeps the delivered recording. Sonnet's switch to spyder9 forces a re-download and re-voice of a delivered show. It is not wrong, but it costs more; its point that this copy's Franklin's Tower is short (665 s against 873 s) deserves a listen.
11. **southerncultureontheskids-2006-11-18.** Same diagnosis from both: D2T07 is "?" in every taper source, and "Primitive" comes from one review. **Opus is more useful** because it stores a set_title proposal. Both are safe. Neither flagged the kept 124 s "feedback/crowd" track, which is minor.
12. **soundtribesector9-2000-09-26.** **Opus is right**: all 10 titles from original tags, verified. Sonnet proposed 4 of the same titles but held on the alignment flag, which was over-cautious.
13. **deepbananablackout-2010-07-31.** Both hold. **Opus is more useful.** It has taper titles for t02 and t05, an encore after t10 from "11. encore intro", and review titles as proposals. Weak spot: it titles t10 "crowd" (130 s) where it should propose an exclude.
14. **explosionsinthesky-2004-10-13.** Both hold with the same reasoning. Opus adds a review-only proposal for t05 ("The Only Moment We Were Alone"), which is fine.

**Tally:** Opus is better or right on 11, Sonnet on 1 (stringdusters), and 2 are a wash (waynehancock, explosionsinthesky).

---

## 3. Acceptance bar per arm

The bar is zero wrong auto-applied edits in four classes: >60 s track-list edits, title fills or replacements, structure edits, and switches.

| class | Opus (auto / wrong) | Sonnet (auto / wrong) |
|---|---|---|
| >60 s include/exclude | 0 / 0 | 0 / 0 |
| title fill/replacement (set_title) | 10 / 0 (STS9) | 0 / 0 |
| structure edits | 0 / 0 | 0 / 0 |
| structure-bar overrules (counted as structure surface) | 1 / 0 | 3 / 2 (Yonder, GD 71-12-01) |
| switches | 0 / 0 | 0 / 0 (but Yonder is a missed mandatory switch: the wrong act airs) |
| title-bar overrules (research-song) | 28 / 5 (stringdusters) | 38 / 15 (Yonder) |

- **Sonnet: FAIL.** Yonder is the clearest case of what the bar exists to stop (a wrong performance on air), and GD 71 breaks an operator ruling.
- **Opus: PASS on the literal bar** (0 wrong in the listed classes). It **fails in substance on one show**: title-bar overrules shipped placeholder titles. Shawn should decide whether a title-bar overrule counts as "title" surface. I think it should.

**Demotions and gate fixes I recommend before any sweep.** These are deterministic and model-independent. Checked against all 30 records:
1. **Sibling-coverage veto.** Make any verdict without a `switch_recording` edit propose-only when a considered recording keeps more tracks (or more kept duration) than the current one. This blocks Yonder (18 against 6) and GD 71 (23 against 11). It spares every correct auto-apply: buttholesurfers, littlefeat, moe and themotet have no siblings; the JRAD siblings are equal at 13; the STS9 sibling keeps 8 against the current 10. It also enforces the "partial with better sibling: hold" ruling in code instead of in the prompt.
2. **Placeholder veto.** Make research-song overrules propose-only while any shipped title satisfies `is_placeholder_title`. This blocks stringdusters. Better still, have the vet or titles stage flag `Track N` placeholders sourced from `tags` (today they ship unflagged).
3. **Quote relevance for title-bar overrules.** Require the quote to contain the flagged song (after normalisation), or else require `partial_tape` plus a taper-side partiality quote. Without that, propose. This item is optional: fixes 1 and 2 already catch every wrong case in the sample. Fix 3 tightens the class that produced the irrelevant quotes.

With fixes 1 and 2, neither arm has a wrong auto-apply in the sample. Sonnet still needs more of Shawn's attention, because it judges more shows "ships as is" and leaves fewer usable proposals (section 8).

---

## 4. The six stale shows

**Cause.** In every one of the six, `staleness.stale_message` compares `gather.final_kept(files, overrides, mp3)` against `show.json`'s track list. **The current gather keeps short files that the old `show.json` excluded as "implausibly short"** (the piece-4 short-keep rule). Nothing was dropped or reordered; files were only added.

| show | file(s) gather keeps now (length) | campaign mark (unprocessed) |
|---|---|---|
| mymorningjacket-2004-05-28 | mmj2004-05-28d1t06 (1:16) | replay needs an LLM call: align_structure, stored alignment llm |
| robertwalters20thcongress-2004-01-02 | RW2C04-01-02d1t08 (1:05) | changed by the held-backlog fixes: files, titles, sets… |
| leftoversalmon-1996-03-16 | los1996-03-16d2t08 (1:03) | replay needs an LLM call: align_structure |
| greatamericantaxi-2009-11-03 | d01t08 (0:59), d01t14 (0:10), d02t01 (0:26) | replay needs an LLM call: align_structure, stored alignment llm |
| soulive-2003-08-07 | d1t01 (0:32), d1t05 (1:48) | replay needs an LLM call: align_structure, stored alignment llm |
| elliottsmith-1997-05-06 | esmith1997-05-06t09 (0:24) | replay needs an LLM call: align_structure |

**Is it correct?** Yes. Each show was marked by the 2026-10-27 bulk-apply batch (`d2089b95…`) with `processed: null`. Five are in the campaign's needs-LLM class, which the spec makes a non-goal ("reprocessed by `redo` / `reapply --with-gather-llm`; whichever end up held are adjudicated"). Judging them now would have the model edit a track list that the next gather will change. The pre-flight did what the spec asks.

**Population share.** I ran the same check over every held show (345, matching population.json) as a pure read. **109 of 345 (31.6%) are stale**, and all 109 carry an unprocessed campaign mark:
- 68 are needs-LLM replays: align_structure 64, stored alignment 3, extract_setlist 1.
- 39 are "changed by the held-backlog fixes".
- 2 are recording re-selections.

By class:

| class | stale | share |
|---|---|---|
| untitled | 30 / 85 | 35% |
| needs a listen | 25 / 71 | 35% |
| partial tape | 11 / 31 | 35% |
| partial tape with a better sibling | 8 / 28 | 29% |
| other | 24 / 82 | 29% |
| better sibling | 6 / 23 | 26% |
| scrambled | 5 / 25 | 20% |

Staleness is spread fairly evenly across classes rather than concentrated in one. **The pilot, at 6 of 30 (20%), slightly under-samples stale shows compared with the population (32%)**, so the judged sample (24) is not biased toward easy shows by this. The practical effects are:
- A sweep today can judge only about 236 shows.
- The 109 stale shows have to be reprocessed first, and since that changes their track lists, their verdicts will differ from what a judgment now would give.
- The 39 "held-backlog fixes" marks are not in the needs-LLM class. Whether they were reapplied and came back held without `processed` being set, or were never run, is worth a check before the sweep. I did not establish which.

---

## 5. Malformed verdicts

**waynehancock-2004-04-08 (both arms, identical edits).**

The errors recorded:
- `edit 11 set_title: WayneHancock2004-08-04d2-08.mp3 is not a current track`
- the same for edit 12 (set_title) and edit 13 (structure)
- `edits 7, 11: conflict on …d2-08.mp3`
- `edits 9, 12: conflict on …d2-10.mp3`

The date-swapped filenames are real: the item's original files are named `WayneHancock2004-08-04d2-01.shn` … `-11.shn`, which is the taper's typo on archive.org. They appear in `show.json` as excluded rows with `reasons: ['filename convention mismatch']`, durations 170 to 467 s. Both models named them exactly as the bundle does. Their includes are valid.

The verdict went malformed because `gate.validate_targets` checks set_title and structure targets against the **pre-apply** track list, and treats an include and a set_title on the same file as a "conflict". A verdict that re-admits a file and then titles it, or places the encore on it, therefore cannot be valid. The spec text ("title and structure targets must be current tracks") does not foresee this case, and the prompt does not warn the model about it.

This is a **validator or spec defect, not a model error and not a library-data error**. The library side is a real taper-typo filename that gather's filename-convention filter dropped.

"Malformed → held, nothing fuzzy-matched" behaved as designed: no near-miss matching happened, and the show stayed held with the verdict stored. The cost is that a correct verdict that restores 11 songs (about 50 minutes) is lost as a proposal. It would not have auto-applied anyway: the includes total more than 120 s, and only the first quote names a position outside the file's own tag row, so it would have ended as held with a proposal. **Fix:** let set_title and structure target files that the same verdict includes, and drop the include+set_title "conflict" (two set_titles on one file, or include+exclude, still conflict).

**discobiscuits-2002-10-02 (Sonnet).** The errors recorded:
- `flag judgement 'research asserts unknown song: Crystal Ball': judged twice`
- the same for "Sister Judy's Soul Shack"

The cause is library data: the show's `review_flags` contains both strings **twice**, because the research names the song and its reprise. Sonnet judged each listed flag, duplicates included, with identical verdicts. Opus de-duplicated them. The validator rejects any repeated judgment.

This is a library-data defect (vet emits duplicate flag strings) combined with a strict validator. It is not a real model error; Sonnet mirrored the list it was given. The verdict was otherwise identical to Opus's correct switch proposal, which the gate would have blocked anyway as station-marked. "Malformed → held" behaved as designed. **Fix:** de-duplicate `review_flags` in the bundle (better, in vet), or accept repeated judgments that agree.

---

## 6. CO5: does "partial tape airs" have a real auto path?

**Yes, but a narrow one.** In the plain partial-tape class, 2 of 4 shows auto-apply in both arms (buttholesurfers and littlefeat). In both, the only flags are research songs that the tape does not contain, plus a structure flag that the partiality explains. Both trial-applied and cleared the hold, and both are correct. That projects to roughly 15 of the 31 in the class. The other two are blocked for good reasons:
- DSO's `low-confidence setlist` is a never-overrule kind.
- waynehancock is malformed (the validator defect), and even when fixed it would end as a proposal.

Two weaknesses remain:
- The path depends on title-bar overrules whose quotes often do not name the song, for example "Unnumbered tracks are missing" or "JIMI (cuts)". It is right here because the facts are right, not because the gate checked them.
- The path leaks into the **partial-with-better-sibling** class whenever the model declares `better_sibling: null`. Sonnet did this on GD 1971-12-01. The gate trusts the model's flag there, and nothing checks the siblings.

The sibling-coverage veto in section 3 closes the leak without removing the real path.

---

## 7. Strict-surface spot-check list for Shawn

| arm | slug | op | target(s) | bar | my verdict |
|---|---|---|---|---|---|
| opus | buttholesurfers-1987-11-07 | overrule ×13 | research-song (pre-Cherub songs, Psych/Pittsburg aliases, post-JIMI songs) | title | CORRECT |
| opus | littlefeat-1977-08-08 | overrule | multiple sets / alignment found none | structure | CORRECT (the tape ends before the encores) |
| opus | littlefeat-1977-08-08 | overrule ×10 | research-song (unnumbered songs, track-1 medley songs, encores, R&R Doctor alias) | title | CORRECT (3 with weak quotes) |
| opus | infamousstringdusters-2010-10-15 | overrule ×5 | Count Me In, Well Well, Get On With It, Dream You Back, Sunny Side | title | **WRONG**: airs "Track 3/9/11/12" placeholders |
| opus | soundtribesector9-2000-09-26 | set_title ×10 | 01–10 STS92000.09.26.mp3 | title | CORRECT (matches the FLAC tags) |
| sonnet | buttholesurfers-1987-11-07 | overrule ×13 | same as Opus | title | CORRECT (11 with an irrelevant quote) |
| sonnet | littlefeat-1977-08-08 | overrule ×11 | same as Opus | structure + title | CORRECT |
| sonnet | gratefuldead-1971-12-01 | overrule | structure has 1 sets but jerrybase shows 2 | structure | **WRONG** (ruling: a partial tape with a fuller sibling holds) |
| sonnet | yondermountainstringband-2009-07-11 | overrule | low-confidence structure alignment | structure | **WRONG**: tape is the 30db duo set |
| sonnet | yondermountainstringband-2009-07-11 | overrule ×15 | research-song (Yonder's real setlist) | title | **WRONG**: same cause; the switch to u89i_16bit was needed |

Worth Shawn's ear if he spot-checks anything: Yonder (the u89i_211 item really is 30db), and stringdusters tracks 3, 8, 9, 11 and 12.

---

## 8. Recommendation on the model (advice; the decision is Shawn's)

**Use Opus.**

**Accuracy.** Opus's wrong auto-apply is one show, five placeholder-title overrules. Sonnet's are two shows and 17 edits, one of which puts the wrong performance on air. In the 14 disagreements Opus is right or more useful in 11 and Sonnet in 1. Opus also leaves Shawn more one-keystroke proposals: 129 projected held-with-proposal against 67. That is the better outcome under the spec's intent, because Sonnet's lower number is mostly "held, no proposal" (prose only) and "ships as is" auto-applies, not fewer problems.

**Cost** (compare.md, judge-only rows):
- Opus: 0.22 five-hour-meter points a show, 19.5 s wall. Full 345-show sweep: about 77 points, 1.9 h.
- Sonnet: 0.11 points a show, 11.3 s wall. Full sweep: about 38 points, 1.1 h.
- The meter deltas are whole numbers (0 or 1 a row: 6 of 27 Opus rows read 1, against 3 of 27 Sonnet), so "about 2x" is coarse.
- With 109 shows stale today, the sweep that can actually run is about 236 shows: roughly 53 points for Opus and 26 for Sonnet. The rest come later, after reprocessing.

The roughly 39-point difference buys avoiding a wrong-act airing and about twice the usable proposals. That is worth it against Shawn's attention.

**Before the sweep, whichever model is chosen:**
- Add the sibling-coverage veto and the placeholder veto (section 3).
- Fix the include-then-title or include-then-structure validation (section 5).
- De-duplicate `review_flags` (section 5).
- Until the vetoes land, demote **title-bar research-song overrules** and **structure-bar overrules** to propose-only. These are the only classes that produced wrong auto-applies. Demoting them costs the correct buttholesurfers and littlefeat auto-applies, 2 of Opus's 7 auto-applied shows in the sample.
- **Keep auto** for set_title from original tags or the taper description (STS9: all correct) and for medium-bar briefing overrules (all 9 correct in both arms).
