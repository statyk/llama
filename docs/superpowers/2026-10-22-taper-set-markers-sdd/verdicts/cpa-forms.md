### Verdict — NO DEFECT CLASS
No non-marker match in the library or the cached corpus places a boundary or changes ownership. Two latent mechanisms, both built by me and with zero live instances that place, are listed under the table below. Narrowing them is recommended but not required by the drop criterion.

### Drop-criterion hits
**None.**

How I checked:
- **Library line ablation.** 2,101 library shows have taper text (no operator override). For each one, every marker line and veto line was deleted, and separately cut down to its song text. `decide_taper` was then re-run. 1,184 marker lines in 608 owned shows are load-bearing: removing one changes ownership or placement.
  - Every one of the 1,184 is a well-formed marker. Grouped by shape, they are all `Set N`/`Encore:`/`E: …`/`Disc N - Set M`/`(set 2)`/`-SET II-` and the like.
  - I read every marker line, with its neighbours, in all 106 owned shows whose labels differ from what ships today. All of them are the taper's own set or encore markers.
  - The lineage-looking load-bearing lines are all disc/set headers. Examples: `Disc 2/Set 2:`, and `Set 2 - Disc 2` (brokemountainbluegrassband-2004-07-16).
- **Corpus-wide checks** (all 15,607 cached items, not only the sample):
  - all 251 `E`/`E<n>`/`ENC` lines that stand alone, with their neighbours;
  - all 4,658 E-header lines followed by songs, screened for email, URLs, lineage, `none` and digits;
  - every one of the 4,266 inline splits, each re-read with that one split blocked;
  - lineage, personnel and microphone headers;
  - filler or bonus mentions, and other dates, that come before a marker;
  - early/late-show texts.
  
  Every non-marker found is either neutralised at placement (its neighbouring items are not songs, or match no track) or voids the structure.

Latent mechanisms. These are not drop-criterion hits: their only live instances do not assert or do not place. Both cases below were built by editing real texts.

| form | identifier/slug | line | what it does (decide_taper before → after) | recommendation |
|---|---|---|---|---|
| inline split → `Encore/Encores` header | perpetualgroove-2006-12-29 (edited) | `Disc 3 - Set II + Encore:` (with a colon) | Real text `Disc 3 - Set II cont`: OWNED `['6:1>2','12:2>encore']`. With the colon: OWNED `['6:1>2','10:2>encore']`, so Set II's disc-3 songs become the encore. Without the colon: unchanged and correct. Cause: `_INLINE_MARKER` splits before `Encore:`. The spec's "header naming set and encore asserts nothing" (`_AND_ENCORE`) only works when no colon follows. Live instances: `Set II & Encore:` (db2007-12-29.ccm41.RM.flac16), `Set 3 / Encore:` (moe2008-01-24 ×2), `Set 3 & Encore:` (tDB2010-12-31.mk41.RM.flac16). None of them asserts (one set, or `cross-check: 3`). `Set 2 & Encore:` after a real Set 2 header would get past the cross-check. | **Narrow:** apply the set-and-encore test to the raw line before the inline split, or do not split `Encore:` right after `set N` + `+`/`&`/`/`/`and`. |
| E header: rest glued to filler | dso2001-11-09.shnf → darkstarorchestra-2001-11-09 (override-skipped) | `…, Midnight Moonlight, E: None Filler: Evangeline, Stir It Up, …` | Live: NOT OWNED (`unplaced: 2\|encore first song 'None Filler: Evangeline' matches 0 tracks`), saved only by the one-word title. Built case (first filler song `Stir It Up`, the tape without Evangeline): OWNED `['7:1>2','14:2>encore']`. The filler is labelled the encore because `fuzzy_title_eq`'s subphrase rule matches `none filler stir it up`. One live line in the corpus. A plain `Encore: none` (darkstarorchestra-2007-07-04) is neutralised, as designed. | Optional: when an encore rest starts with `none`/`no encore`/`n/a`, the taper owns nothing. Or document it. |

### Per-form table
Raw lines are from forms_summary.txt. "Sampled" is the family hits plus up to 30 others. Non-marker counts come from my code passes over all lines, which covers more than the sample.

| form | raw lines | sampled | non-marker hits found | of which can matter | verdict |
|---|---|---|---|---|---|
| set header: Set N/one/I | 17,753 | 13,554 | Lineage, personnel or prose rests: about 36 lines in asserting texts that are read (heuristic, ~104 corpus-wide). Examples: `set 1 : taper : mike inhatt…`/`set 2 : schoeps mk41v >…` (ttb2020-02-29), `Set II : SBD -> Reel Master…` (gd74-10-18 notes), `Set I: Not much was done to the first set…` (gd1970-09-20) | 0. Library: 0 non-markers among the load-bearing set lines. Lineage items never match a track: ttb2020-02-29 is unplaced on `taper : mike inhatt…` | keep |
| set header: Disc N (Set M) | 612 | 276 | 0 | 0 | keep |
| set header: 1st/2nd/3rd Set | 192 | 166 | ~10: lineage (`1st set: SBD>MC>…` gd78-05-06; `1st Set : Nakamichi…` Dc20151031; `1st set - Neumann…` gd84-04-27), microphone (`1st Set - Elevated Approx. 9 feet off` turkuaz2014-07-06), personnel (`2nd set: Trey Anastasio - vocals, guitar` plf2006-07-09/11 notes) | 0. deadandcompany-2015-10-31 is unplaced on `Korg Mr 2` and turkuaz-2014-07-06 on `floor on stack.`; the rest assert nothing or are not read | keep |
| set header: First/Second/Third Set | 69 | 69 | 0 | 0 | keep |
| encore header: E/E\<digit\> | 4,867 | 3,838 | 2: the glued `E: None Filler: …` (above); a signature `e` closing rad1998-08-28's notes. All 251 lone lines and all 4,658 lines with songs reviewed | 0. dso2001-11-09 is latent (above). The signature makes an empty encore, so the structure is void, and those notes are not read | keep |
| encore header: ENC | 42 | 42 | 0 (all 42 read) | 0 | keep |
| encore header: Encore/Encores | 5,301 | 3,276 | ~9: `Encore: none`, `Encore: None +` (3, item `none` matches no track); lineage (`encore: MAC>CD`, `encore:  AUD`, `Encore: FOB Nakamichi…`, ~5; unplaced or not read); `05. 42 (Encore)` (db2006-10-19), a song line read as a header after a double number strip (1) | 0 | keep |
| encore header: ordinal encore | 35 | 35 | 0. But all 14 `1st/2nd Encore:` lines that have a colon never reach this form: the inline split leaves `1st` as a song item (own-less, below) | 0 | keep. The colon case only makes the taper own less |
| inline-split marker | 4,328 | 3,537 | 29 splits after prose or lineage that change the reading (`source: Set 1: SBD>…`, `The sound mix differs from set 1 to set 2:`, `Missing part of Set II:`, `Mic Location: …, 1st Set - Elevated…`); 4 set-and-encore headers with a colon (above) | 0 live: every lineage case is unplaced, not read, or voids; none of the 4 asserts | keep, and **narrow the set-and-encore colon case** |
| rule: continuation header | 345 | 179 | 0 | 0 | keep |
| rule: header naming set and encore | 7 | 7 | 0 (colon-less; fires correctly) | — | keep |

### Own-less collateral
Counted over asserting texts with no recognised encore marker, which is where the veto decides.
- **Veto: encore word** (439 lines / 399 items; most are `encore break`, which is real). 15 items are innocent:
  - 13 say "no encore": `No encore performed` (gd1984-10-14 ×8, including library gratefuldead-1984-10-14), `No encore` (billystrings2026-04-06.ccmmix.kp), `…hence, no encore` (billystrings2026-04-18.aud.flac16);
  - 2 are hypothetical prose: `if they came back and played an encore…` (gd1972-03-23 ×2).
- **Veto: line starts E./E)/E\<digit\>/(E)** (97 lines / 88 items). About 3 items are innocent, and lettuce-2008-05-02 is ambiguous:
  - md5 checksum lines `e9294d0d… *Smashing Pumpkins …flac` (tsp2000-11-29.aud3; tsp2007-06-27.aud5 ×4);
  - `E.S.P. show` (gd1971-02-18.157425);
  - ambiguous: `d2t10  E. Vill^` (lettuce-2008-05-02, library).
- **Veto R4(b): line ends ` E`** (9 lines). 4 items are innocent: `Open E` (sts9-2006-04-14, sts92007-06-15, sts92007-09-08) and `1. D to E` (mogwai2001-06-16). mogwai-2001-06-16 is the probe's only library show lost to R4 alone.
- **Veto R4(a,c): item is exactly E/E\<digit\>/ENC** (14 lines): 0 innocent seen. `E)` lines and `…, E` both mean an encore.
- **Void: set 4 or higher** (28 lines). 8 are innocent: `One Set 96:57` (JRAD2014-08-01 notes), `-- This file set 16 bit` (gd1988-03-31 notes), `This File Set 2022-12-04` (ttb2022-12-03). The cause is the `[1-9]\d+` branch. `(Set 23 of 24 over 4 days)` (zachdeputy-2009-06-14, library) is debatable.
- **Void: empty encore** from a bare `e` signature: 1 (rad1998-08-28 notes).
- **Ordinal `1st/2nd Encore:` with a colon**: 14 lines over 9 items. The inline split leaves `1st` as the last song of the set, so the encore boundary cannot place. Today all are one-set texts (ryanadams, robynhitchcock, ra2007-06-29) or harmless second encores (SCI2006-06-29, db2009-01-30).
- **Library, real markers whose encore boundary did not place**: about 100 owned→not rows. These are by design, not collateral.

### Required negatives spot-check
From the real cached texts and the library tracks:
- `giantsand-1991-01-30` and `calexico-2000-07-01`: no markers.
- `darkstarorchestra-2005-11-16`: asserts, then unplaced (`'NFA' matches 2 tracks`).
- `darkstarorchestra-2004-04-20`: one set.
- `railroadearth-2008-08-17` (`(E) With Allie Kral`): no markers.
- `stringcheeseincident-2004-06-19`: void, set 4 or higher.
- `davidnelsonband-2007-09-07`: void, numbered marker after the encore.
- `paf2007-10-12…flac24`: `cross-check: 3`.
- `antibalasmusic-2003-04-28`: no markers.
- `Set IV` voids.
- None of these lines is classified as a marker: `E.Ville`, `B. E. Women`, `E. Rutherford, NJ`, `I Know You Rider`, `J`, `Untitled #12`, `1:08:07`, `Set I is Bobby and Jerry playing acoustic`, `Set Intro`, `[1]`, `1:`, `II:`, `S1`, `E.`, `(E)`.

All hold as the spec states.

### Notes for the operator
- Placement is what makes lineage text harmless. Every lineage, personnel or prose set header I found fails at "matches 0 tracks", as section 1 predicts.
- greenskybluegrass-2006-05-16 ships 3 sets from `disc1/set1 … disc3/set3`, where today has no breaks. The marker is real, but it may be disc labels: worth a look in the report-3 pre-screen.
- A `Set N & Encore:` header with a colon breaks the spec's section-2 rule (shown on perpetualgroove-2006-12-29). It is a small fix, best made before merge, even though no live text triggers it.
- The scratch scripts and outputs are in /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-taper-markers/5c4f03eb-6157-439a-a1f1-688e02807eae/scratchpad/cpa-forms/ (ablate.jsonl, corpus.jsonl, inline_ablate.json, veto.json, dec.py). The repo and ~/.llama were not touched.
