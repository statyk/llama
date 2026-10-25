# t9-pre: Opus pre-screen of the short-keep hand-check (rows 25, 36, 46) and spec premise 3 (sibvocab)

Read-only. I edited no repository file and committed nothing. Nothing under ~/.llama or ~/.llama-harness was written. I ran the worktree's own `llama.junk` through `/Users/shawn/projects/llama/.claude/worktrees/junk-filter/.venv/bin/python -I`; `llama.__file__` resolves inside the worktree. Scratch scripts and outputs are in `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-junk-filter/68216777-fbbf-4e29-a05f-d8f145d56c7f/scratchpad/t9-pre/` (`classified.json`, `hand.json`, `hand.txt`, `dlist.txt`, `scripts/*.py`). One process slip: I briefly created a stray `handback-head.md` in `$D/t9-pre/` and deleted it at once (mandate 2).

## Summary for the operator

| row | file | rule did | checker said | class |
|---|---|---|---|---|
| 25 | `skb2004-09-24d1t01.mp3` (80 s, untagged, first track) | drop (edge) | keep | **A, checker error** |
| 46 | `01 Intro.mp3` (19 s, untagged, first track) | drop (edge) | keep | **A, checker error** |
| 36 | `gd73-10-29d2t01_vbr.mp3` (length `00:00`, 1,017 bytes) | keep | drop | **C, a small defect: fix before merge** (by the letter it sits inside section 7's "very short files" limitation, but that limitation does not cover a file with no audio in it) |

Corrected score: 59 of 60 rows right, plus one real defect. The 6(c) bar still holds on the sample. Two things outside the sample need Checkpoint A rulings:

1. **Premise 3 only partly holds.** The crowd and tuning vocabulary misses about 200 sibling rows (typos, plurals, set labels, taper prefixes). Those are short junk inclusions, the error the operator ranks cheaper, so I recommend no change. The non-performance vocabulary is a different matter: it misses broadcast and PA items. That includes **6 rule-kept non-performance files in the library itself**, 5 of them on 3 delivered shows. Strict surface (c) and the 6(c) bar ("zero kept spam or non-performance") are therefore not met across the whole population, though they are met in the sample. A narrow addition to NONPERF, measured below, newly drops exactly those 6 library files and no music.
2. **A severe pre-existing defect, not piece 4's.** 20 Grateful Dead shows ship every song twice: two VBR MP3 derivatives (`X.mp3` and `X_vbr.mp3`) of each original. 17 of them are delivered, unvoiced and on the station now. Row 36 surfaced it.

## Part 1: the three wrong rows

### Row 25: `stevekimockband-2004-09-24`, `skb2004-09-24d1t01.mp3` (packaged)
- **What it is.** 80 s at the very start of the tape (floor 160 s). The cached metadata gives no `title` on the mp3 or on its FLAC original (`skb2004-09-24d1t01.flac`, 80.6 s, `track` 1). The description lists `d1t01 - Tuning/Introduction`. So it is tuning plus a band or stage introduction before `High & Lonesome`. The same show's `d2t04 - Band Intros` (120 s) is the other untagged edge file, also dropped.
- **Under the spec.** 2.2 defines the tag as the file's own `title`, else its original's. The description is not the tag, so this file is untagged. 2.4 (ruling 4): an untagged short file is kept only when it is interior. This one is first in play order, so it is an edge file and drops. The checker brief says the same ("An untagged file is kept only between two kept tracks; at the edge it drops"). The checker substituted the description's label for a tag.
- **Class A, checker error.** The rule did what ruling 4 says. Little is lost: 80 s of tuning and an intro at the head of the tape. (Had it been tagged `Tuning/Introduction`, 2.3 would keep it as a mixed tag. Ruling 4 deliberately does not reach that far for untagged files: 37 edge files measured.)

### Row 46: `loslobosmusic-2024-06-14`, `01 Intro.mp3` (packaged)
- **What it is.** 19 s, the first file (floor 64.8 s). No `title` on the mp3 or on its 24-bit FLAC original (`track` `01`). The description's setlist starts `Intro`, then `Manny's Bones~>`. It is almost certainly a stage welcome or announcement before the first song.
- **Under the spec.** Untagged (2.2), at the edge (2.4), so it drops. The filename can only ever drop a file (2.4 "Filename junk... It only ever drops"); `Intro` is not wholly junk, so it falls through to the edge test. The checker kept it on the evidence of the filename, which the spec does not allow.
- **Class A, checker error.** 19 s of announcement at the start of the tape.

### Row 36: `gratefuldead-1973-10-29`, `gd73-10-29d2t01_vbr.mp3` (packaged)
- **What the file is: a real, audio-less stub, not a missing length.** In the cached metadata (`~/.llama/cache/md_gd1973-10-29.sbd.kaplan.1070.shnf.json`):
  - this file: `format: VBR MP3`, `length: "00:00"`, `size: "1017"`, tagged `Promised Land \>`, derived from `gd73-10-29d2t01.shn` (174.1 s, 16.7 MB) in 2009.
  - the same original's other VBR MP3, `gd73-10-29d2t01.mp3`: `02:54`, 3.98 MB, from 2014. That one is fine and already ships.

  1,017 bytes holds no audio: about an ID3 header's worth. archive.org's own length reads `00:00`.
- **How the filter treats it.** `util.length_seconds("00:00")` returns `0.0`, not `None`. So the `missing duration` arm (`secs is None`) does not fire, and the file lands in the short arm as `0.0 < 87.5`, reasons `["implausibly short"]`. Today that drops it. Under piece 4, `_apply_short_rule` re-decides it: not spam, and the tag `Promised Land \>` is not junk, so it is **kept** (a tagged file needs no interior test). The spec's literal rule did exactly this.
- **What shipping it does.**
  - **llama.** `build_package` downloads it (the md5 matches its 1,017 bytes) and `tag_audio` writes an ID3 tag. `read_duration` (mutagen) returns `None` on a file with no MPEG frames: I simulated an ID3-only mp3 in scratch and got `read_duration None`. The duration check is `real is not None and ...`, so it is skipped, **no flag is raised**, and the manifest records `duration_sec 0.0`. llama sees nothing wrong.
  - **emcee.** It never decodes track audio, so it voices the package. Its DJ gap falls between "Promised Land" and a second "Promised Land".
  - **transmitter.** `analysis.analyze_show` decodes every file. On an audio-less mp3, ffmpeg fails ("Failed to find two consecutive MPEG audio frames", exit 183 in my simulation). That raises `DecodeError`; a zero-sample decode would raise `AnalysisError: decoded to no audio` instead. Both are `TransmitterError`, which `planner` turns into `on_skip`, logged `skipping <slug>`. **The whole show silently drops out of rotation.** If the show is mid-air when the re-delivered package is re-planned, `pipeline` raises `LayoutError` ("refusing to re-plan into a mid-show cut"); spec 5's timing rule (re-deliver outside the playout horizon first) mitigates that.
- **Class C: a defect to fix before merge.** By the letter, section 7 accepts "Very short files. About 6 kept files have a metadata length under 5 s". The six are exactly bgug trk04 (0.0), gd73 (0.0), gd74 (0.0), JK `Outro` (4), NRPS `2 more seconds...` (2) and PAF `...intro>` (4). So this file is inside an accepted class as written. That limitation reads as "a few seconds of real audio", though, and 2 of the 6 contain no audio and take their show off the air. The operator was not told that.
  - **Smallest fix.** `packages/llama/src/llama/junk.py`, `_apply_short_rule`, first loop: do not re-decide a zero-length file. It keeps `implausibly short` and stays dropped:
    ```python
    if e["reasons"] != ["implausibly short"] or not e["duration_sec"]:
        continue
    ```
  - This is an exact test with no threshold, and it only ever drops. It needs the spec 2.3 and 6(f) corpus-test expectations changed for 3 rows, and section 7's "about 6" becomes 3.
  - The candidate's changed-show list loses 2 shows. In each, this stub is the only `short_kept` file: `gratefuldead-1973-10-29` (packaged) and `gratefuldead-1974-09-11` (delivered). `bluegroundundergrass-2008-04-04` (held) keeps its other short-kept file, `trk02`.
  - The section 5 table moves by 1 in the delivered and packaged rows, and in their "music restored" counts if those counted these files.
  - The rest of the "very short" limitation (3 real files of 2-4 s) stands.
- **Does the 0.0 case occur on other shows?** In `~/.llama-harness/piece45/spec/r1/r1_files.jsonl` (3,547 rows), **5 rows have dur 0.0** (7 more are 2-4 s; none is `None`). Their treatment in the candidate arm (`~/.llama-harness/piece4/cand.json`, `filenames` and `short_kept`):

  | slug | state | file | tag | what the file is | candidate |
  |---|---|---|---|---|---|
  | gratefuldead-1973-10-29 | packaged | `gd73-10-29d2t01_vbr.mp3` | `Promised Land \>` | 1,017-byte stub; a full copy of the same original also ships | **kept, short_kept** |
  | gratefuldead-1974-09-11 | **delivered** | `gd74-09-11v3d2t03_vbr.mp3` | `Phil \& Ned-\>` | 1,745-byte stub; `gd74-09-11v3d2t03.mp3` (11:39) also ships | **kept, short_kept** |
  | bluegroundundergrass-2008-04-04 | held | `bgug2008-04-04-16bit-d2.trk04.mp3` | `The Times They Are A Changin` | real but 0.17 s (FLAC original 0.17 s, 18 KB); the mp3 reads `00:00` | kept, short_kept (harmless; show held) |
  | gratefuldead-1991-04-05 | delivered | `gd1991-04-05d1t01_vbr.mp3` | `Tuning` | 1,004-byte stub | dropped (junk tag) |
  | giantsand-1996-02-03 | packaged | `gsand1996-02-03d1t04.mp3` | `./---blank---` | 6,656 bytes | dropped (junk tag) |

  The two harmful cases are both stub `_vbr.mp3` files in items carrying two VBR MP3 derivatives per original.

### Found through row 36: shows shipping every song twice (pre-existing; outside piece 4)
- **What I found.** `gd1973-10-29.sbd.kaplan.1070.shnf` carries two `VBR MP3` derivatives of every `.shn` original: `X.mp3` (2014) and `X_vbr.mp3` (2009). Both pass every arm. `_stem` is the name up to the first digit (`gd`), so the convention arm accepts both. `_dedupe_duplicate_listings` keys on (basename, duration), and the basenames differ. The library `show.json` for this show has **47 tracks, each song twice in a row**.
- **Why such items get picked.** `select_recording` scored the doubled item 9.906 against 7.702 for the best single copy, on `kept_tracks` 47 against 25. So doubled items tend to win selection.
- **How many.** A library-wide scan of `show.json` files containing both `X.mp3` and `X_vbr.mp3` finds **20 shows**:
  - delivered (17): gratefuldead-1966-12-01, 1968-10-13, 1969-04-21, 1974-05-25, 1974-09-11, 1978-12-30, 1987-06-30, 1987-07-06, 1988-03-27, 1988-06-23, 1989-07-18, 1989-08-19, 1990-03-16, 1990-07-14, 1991-04-05, 1991-10-31, 1995-03-18;
  - packaged (1): 1973-10-29;
  - held (2): 1972-11-18, 1991-06-25.
- **On the station.** I read all 17 station manifests under `/Volumes/media/lma-radio/delivered/`. Every one has adjacent same-title pairs (e.g. 1974-09-11: 45 tracks, 22 pairs, `Scarlet Begonias` x2, `Mexicali Blues` x2...). None is voiced. They air with every song twice.
- **Not known before.** Nothing in `shipped-broken.md` or the piece-4 evidence mentions it. The only trace is a taper-markers note on `gratefuldead-1989-07-19` that "duplicate _vbr files also broke alignment".
- **Smallest fix (a separate decision, not part of piece 4).** Keep one derivative per `original` within the winning format: prefer the one whose length agrees with the original, then the newer one. This would go in `_keep_and_exclude` or a sibling of `_dedupe_duplicate_listings`. It also removes the stubs above.
- **Interaction with the bulk apply.** The apply would re-deliver gratefuldead-1974-09-11 with the stub added. Without the zero-length fix, that takes the show off the air.

## Part 2: premise 3 (sibvocab)

**What the 630 are.** `short_keep_probe.py sibvocab` takes sibling drops with `tagged and jc is None`, that is, files the reference rule KEEPS (5,024), and greps them for `tun|crowd|applau|radio|dj|silen|noise|fade|commercial|promo|interview|station|static|hiss`. "Already dropped-shaped" is therefore empty by construction.

**Cross-check.** I re-ran the worktree's `junk.short_tag_is_junk` and `short_is_spam` on all 630: 0 junk, 0 spam. Over all 9,487 tagged sibling short drops, the worktree port agrees with the reference `jc` on every row (9,487 agree, 0 disagree). The port matches what was measured.

| group | rows | notes |
|---|---|---|
| 1. already dropped-shaped by the regexes | **0** | by construction (these are the rule's keeps); confirmed by the port |
| 2. mixed or spoken tags the rulings keep | **354** | `banter`/`intro`/`outro`/`thanks`/`donor rap`/`announcements` combined with crowd or tuning (`crowd/banter` x31, `intro/crowd` x36, `outro/crowd` x29, `Intro/Tuning`...); the Dead's tuning ditties the spec names as kept (`Mexican Hat Dance Tuning`, `Beer Barrel Polka tuning`, `Twilight Zone Tuning`, `Nickelodeon tuning`...); `Tuning Jam`, `Crowd> Jam>`, `tunin' & teasin'`, `crowd/false start`; band and crew talk (`Bob & Phil yell at crowd`, `Lost Kid Announcement/Tuning/Crowd`, `Stage announcements by Chip Monck/tuning/Intro`, `Weir's football score`). Borderline but kept: `crowd/1812 Overture` (UM, 58 s after `Divisons`; band or PA unknown), `tuning/announcer` (an SBD of a broadcast date), `Say Hi To Your Radio`, `Happy New Year to radio stations from Dan Heally.` (crew), `Tuning / Balk` |
| 3. real music or song titles matching by accident | **54** | `Not Fade Away` (and its reprises and jams, with `E:`/`E1:` prefixes), `Terrapin Station` (and its jams), `West L.A. Fadeaway`, `Courage (fade`, `Tripe Face Boogie (fades out)` |
| 4. junk or non-performance the rule KEEPS | **222** | listed in full below; subclasses: non-performance 9, possible non-performance 3, crowd chants 20, crowd shout 1, vocabulary gaps 22, typos 8, plurals 6, `etc` 5, hyphen-joined 2, set labels 11, annotations 11, taper or filename residue 124 |

**The grep also misses broadcast tags.** It has no call-sign term, so broadcast intros fall outside the 630. A call-sign probe (below) finds **15 more sibling keeps**: `KUSF show intro`, `KDHX ID` x3, `KBFH introduction` x2, `KBFH intro >` x2, `KBFH/GD Intro` x2, `KBFH Outro` x2, `WMMS Intro` x2, `WXRT Intro`, plus `WMMR Tuning Intro` (already in group 4).

**The library itself keeps non-performance (found while testing the premise).** I scanned the library's 2,668 rule-kept tagged files with a broad broadcast and PA vocabulary and read each hit against the item description. **6 rule-kept non-performance files**, none in the 60-row sample:

| slug | state | file | tag | what it is |
|---|---|---|---|---|
| joerussosalmostdead-2020-02-21 | **delivered** | `...-s1t01.mp3`, 20 s, edge but tagged | `Rock and Roll (Played over PA - fades in)` | the description says "Pre Show Music: ... 'Rock And Roll' Led Zeppelin"; census kind `music-fragment` |
| railroadearth-2006-02-18 | packaged | `rre2006-02-18d2t01.oktava.mp3`, 76 s | `Mardi Gras Celebration (Hey Pocky Way on PA)` | PA music during a celebration |
| guster-2006-07-28 | **delivered** | `Guster2006-07-28D1T01.mp3`, 56 s, edge but tagged | `WXRT Intro` | a radio-station DJ intro, the same class as the ruled `Q104.3 DJ intro` |
| theotherones-2002-08-03 | **delivered** | `d2t03`, `d2t14`, `d4t08` (21, 33, 37 s) | `Host #03 "General Banter"`, `HOST #12 "Intermission..."`, `HOST #16 "Post-Show Banter"` | WXRT-FM DJ Bobby Skafish ("a.k.a. Host") on an FM broadcast. Context: this show already ships 14 long HOST tracks, pre-existing and out of scope as long spoken tracks |

Borderline: `umphreysmcgee-2006-05-05` `Marching band music (Notre Dame fight song?)` (53 s, delivered).

**Measured candidate fix** (scratch probes `scripts/nonperf_probe.py` and `scripts/callsign_probe.py`). Three additive NONPERF alternatives:

- `\b(?:over|on)\s+(?:the\s+)?p\.?a\.?(?=\W|$)`: PA playback;
- `\b(?:closing|exit|outro)\s+music\b`: the existing `(house|pa|intro|...)\s+music` alternation, extended;
- `(?=.*\b[KW][A-Z]{2,3}(?:-?FM)?\b)(?=.*\b(?i:<the existing qualifier list>|wrap\w*)\b)` (call letters are case-sensitive) and `\bhost\s*#\s*\d`, case-insensitive: broadcast call signs and hosts.

| over | newly drops | music lost |
|---|---|---|
| library, 3,547 rows | **exactly the 6 files above** | 0 (the 2 other library hits, `KSAN DJ Talk` and `WXRT-FM Station ID...`, were already dropped) |
| siblings, 5,024 kept | 2 PA, 2 closing/outro music, 16 call-sign or host (and `Tuning and Station Announcer` x2 if `station\s+announc\w*` is added) | 0 |

Risks:
- A bare `PA` part test would also catch a tag like `Ardmore, PA`, so I left it out. `Sgt. Pepper's PA/crowd` and `Star Spangled Banner (PA/Crowd)` therefore stay kept (siblings only).
- A capitalised band name such as `WAR` followed by `intro` would match the call-sign term. That is measured 0 here, but it is why the corpus re-measure matters.
- A whole-tag `DJ` term would catch one sibling (gd1972-12-31 FM).

### Verdict on premise 3
- **Crowd and tuning vocabulary (JUNK_PART): no rule change. Record it as an accepted limitation in section 7:** "beyond the library the junk test keeps typo'd, pluralised, set-labelled, annotated and taper-prefixed crowd and tuning tags (about 200 of 5,024 sibling short keeps; e.g. `crown/tuning`, `Tunings`, `Set I: Tuning`, `Tune Up (AUD)`, `gd81-09-12 s1t01 Crowd`, `JKB110506_03 Noise`)". These are seconds of tuning or crowd, the error the operator ranks cheaper. Each fix would be a new regex in a normative, corpus-gated block, and the clugston-family `gdYY-MM-DD sNtNN` prefix alone is 100+ rows. The 20 crowd-chant rows (`Not Fade Away Chant`, `We want Phil`) are crowd-only by the direction, but they are a Deadhead tradition: an optional one-line operator ruling, and I lean keep.
- **Non-performance vocabulary (NONPERF): a Checkpoint A ruling item, because (c) is a strict surface.** The rule keeps 6 non-performance files in the library (5 on 3 delivered shows) and at least 24 in siblings (9 in the 630 plus 15 call-sign intros outside it; 3 more borderline). My recommendation is to take the measured three-alternative NONPERF addition above. It is additive, newly drops exactly the 6 library files with 0 music lost, and costs one corpus-test update (the 6 rows), a spec 2.3 edit and a candidate re-run. The alternative is to accept it as a section 7 limitation, listing the 6 files so the operator can `fix --exclude` them.

### Group 4, every tag (with item ids; `xN` = rows)
#### nonperf (9 rows, 9 distinct)
- `13. Tuning and Station Announcer` x1: gd1978-11-24.151616.prefm.WBUF.blackwood.gems.t.flac1648
- `Crowd/Closing Music` x1: gd1990-07-14.Nak100sSenn421.Hill.Keo.130834.Flac1644
- `DJ` x1: gd1972-12-31.137465.fm.GEMS.flac16
- `Rock and Roll (Played over PA - fades in)` x1: jrad2020-02-21.cmc621.cmc641v.sbd.matrix.flac24
- `Rock and Roll (played over PA fades in)` x1: jrad2020-02-21.Microtech_Gefell_M300_flac24
- `Sgt. Pepper's PA/crowd` x1: gd1985-06-14.senn441.mccue.ford.32867.sbeok.flac16
- `Star Spangled Banner (PA/Crowd)` x1: furthur2011-11-11.vp88.digigal.flac16
- `Tuning and Station Announcer` x1: gd1978-11-24.150970.prefm.WBUF.larussa-blackwwod-chastain-waddell.flac2496
- `WMMR Tuning Intro ->` x1: gd1987-03-31.172773.ultramatrix.remaster.miksis.miller.flac16
#### nonperf? (3 rows, 3 distinct)
- `02 GD Preface German MC & Tuning` x1: gd1981-03-28.136977.FM-UK.flac24
- `Pre Show/Tuning` x1: rre2009-03-20.AKG461-BUSMAN670
- `Radio Broadcast>` x1: deadco2025-05-11.Bootsy
#### chant (20 rows, 12 distinct)
- `Crowd Doing Not Fade Away` x1: dead2016-06-20.flac16
- `Crowd Doing Not Fade Away*` x2: ftw2015-07-05.schoeps-sonosax.flac24
- `encore break/crowd Fade Away` x1: dac2017-06-18.sennmke4010.mbhoka200n.tascamdr680.busmanmod.flac16
- `encore break~crowd Fade Away` x1: deadco2017-06-18.mbhoka200.flac24
- `gd83-04-12 s2 t12 Not Fade Away Chant` x1: gd1983-04-12.140047.set2.sbd.pcm.gans.miller.clugston.flac1644
- `gd83-04-23 s2t12 Not Fade Away Chant` x2: gd1983-04-23.143126.fob.senn421.wise.clugston.miller.flac1648, gd1983-04-23.143127.fob.senn421.wise.clugston.miller.flac2496
- `gd83-10-12 s2t12 Not Fade Away Chant` x2: gd1983-10-12.143608.fob.nak700.cohen.miller.clugston.flac1648, gd1983-10-12.143609.fob.nak700.cohen.miller.clugston.flac2496
- `Not Fade Away Chant` x1: dac2015-11-17.ccm41v.flac16
- `Not Fade Away Chant >` x4: gd1983-04-12.162699.senn421.blend.vita.miller.clugston.flac1648, gd1983-04-12.162700.senn421.blend.vita.miller.clugston.flac2496, gd1983-04-23.163833.senn441.eaton.miller.clugston.flac1648, gd1983-04-23.163834.senn441.eaton.miller.clugston.flac2496
- `Not Fade Away crowd chant` x2: gd1983-04-12.141632.senn421.executive-crew.holbrook.flac1644, gd1983-04-12.141633.senn421.executive-crew.holbrook.flac2448
- `Not Fade..Away Chant (End Added From set 1 Tape)` x1: gd1989-07-09.Nak300CP4.Fitzy.Keo.125228.Flac2496
- `We want Phil"/crowd` x2: gd1988-03-27.144487.sennme-80.porter.carbonetta.sirmick.flac1644, gd1988-03-27.144488.sennme-80.porter.carbonetta.sirmick.flac2496
#### crowd-shout (1 rows, 1 distinct)
- `Crowd/Steve!` x1: gd1990-07-18.Nak100sSenn421.Hill.Keo.131337.Flac1644
#### vocab (22 rows, 13 distinct)
- `./-pre encore crowd-` x1: UM2006-11-17.adkTL
- `band tuning / warmup` x1: robertrandolph2001-11-16.4021.flac16
- `crowd in` x1: gd1985-06-25.senn441.kutik.106739.flac16
- `Crowd Set II` x2: rd2014-03-07.aud.shurem81.24bit.flac, rd2014-03-07.aud.shurem81.flac16
- `encore #2 crowd` x1: mofro2007-03-09.NeumannMix
- `fade` x2: gd1982-09-21.sbd.perkins.tetzeli.fix-13306.34723.flac16
- `Fade In Track` x4: gd1974-06-23.sbd.OBV.30846.shnf, gd74-06-22.aud.obv.30999.shnf
- `Fade Out Track` x4: gd1974-06-23.sbd.OBV.30846.shnf, gd74-06-22.aud.obv.30999.shnf
- `more crowd` x1: gd85-09-07.oade.georges.17078.sbeok.shnf
- `Piano/Bass Tuning` x1: gd1973-12-18.126123.mtx.dusborne.droncit.flac16
- `pre-encore crowd` x2: ratdog2007-07-13.mk4v.flac16, ratdog2007-07-13.mk4v.flac24
- `The crowd are ecstatic` x1: dead2009-05-01.nak300.bleich.99036.sbeok.flac16
- `Tuning Too` x1: furthur2010-03-03.neumann-skm140.hopely.111160.flac16
#### typo (8 rows, 6 distinct)
- `Crowd/tunng` x1: gd1990-03-16.senn-hubbard.cpb.83791.flac16
- `crowed/tuning` x1: gd1980-09-02.mtx.sirmick.110785.sbeok.flac16
- `crown/tuning` x2: gd1978-12-30.137674.neumankm88.troy.smith.sirmick.sbeok.flac16, gd1978-12-30.137675.neumankm88.troy.smith.sirmick.sbeok.flac24
- `Crown/tuning` x1: gd1984-06-26.senn.hubbard.bandrofcheck.81495.sbefail.flac16
- `Crown/tuning >` x1: gd1984-10-06.aud.unknown.fix-32898.33955.sbeok.shnf
- `tuniung` x2: gd1978-02-05.151837.s2.aud.lamarre.vernon.sirmick.flac16, gd1978-02-05.151838.s2.aud.lamarre.vernon.sirmick.flac24
#### plural (6 rows, 2 distinct)
- `Crowd/Tunings` x1: gd1990-07-18.118892.aud.dak5245-pzm.flac
- `Tunings` x5: gd1989-04-08.111975.aud.dak5245-pzm.cincinnati-oh.flac16, gd1990-07-18.118892.aud.dak5245-pzm.flac, gd1990-07-19.118893.aud.dak5245-pzm.flac
#### etc (5 rows, 3 distinct)
- `crowd, dead air etc.` x1: zero1997-04-26a
- `tuning etc.` x3: gd1970-05-06.156178.msr.zootype.flac16, zero1997-04-26a
- `Tuning/Etc.` x1: skb2005-12-09_24bit
#### hyphen (2 rows, 2 distinct)
- `01 - crowd-tuning` x1: gd1995-06-02.153192.sony.bregman.miller.vernon.f1648
- `01 tuning-crowd` x1: DeadCompany2016-06-20.DC2016-06-20
#### set-label (11 rows, 9 distinct)
- `(Set 2) Tuning` x2: dead2009-05-02.98799.zman.ccm4v.flac16, dead2009-05-05.98863.zman.ccm4v.flac16
- `(set 2) Tuning` x1: dead2009-04-22.98663.muletaper.mc930.flac16
- `Encore Tuning *` x1: gd1989-10-09.120404.Nak300sSenn441.AlabamaBob.Currier.Keo.Flac1644
- `moe. set tuning` x1: moe2005-09-02.atFOB-SchoepsCMC64v.AD1000.flac16
- `Set I: Tuning` x1: skb2005-10-26.dsm6p.flac16
- `Set II: Tuning` x1: skb2005-10-26.dsm6p.flac16
- `set1: tuning` x1: furthur2010-06-25.neumann-skm140.sunboy.108579.flac16
- `Set2: crowd/tuning` x1: furthur2011-07-26.neumann-skm140.sunboy.115427.flac16
- `Tuning (start set 1)` x2: gd1990-06-10.168425.3xnakcm300.ont.flac1644, gd1991-10-27.168818.cm300.cp4.ont.flac1644
#### annotation (11 rows, 5 distinct)
- `Crowd/Tuning (Added From Tape 1)` x2: gd1995-06-25.Nak300CP4.Baker.Keo.113092.Flac1644, gd1995-06-25.Nak300CP4.Baker.Keo.113093.Flac2496
- `Tune Up (Aud patch)` x4: gd1977-05-26.sbd.wizard.32302.shnf
- `Tune Up (AUD)` x2: gd1974-06-23.sbd.OBV.30846.shnf
- `Tuning (1)` x2: gd1974-05-19.sbd.fix.miller.107165.flac16, gd1974-05-19.sbd.miller.106716.flac16
- `Tuning/Crowd (to end of reel) [:38]` x1: gd1970-05-06.sbd.gans-hall.95.shnf
#### residue (124 rows, 69 distinct)
- `01.03] Tuning` x1: gd1990-03-28.mtx.dts.haugh.95825.flac16
- `01.16] Tuning` x1: gd1989-10-09.mtx.dts.haugh.92005.flac16
- `0213 crowd` x1: Deadnco2016-07-10
- `crowd\` x4: jrad2019-08-29.schoeps.mk22.flac24, jrad2019-08-29.schoeps.mk4v.flac24
- `Crowd\tuning` x1: gd1978-09-16.aud.tobin.patched.95292.flac16
- `Disc01,Track01 Tuning` x2: gd1989-07-17.144302.Dak.boedicker.flac1644, gd1995-04-02.143095.nak300-cp4.Boedicker.flac1644
- `Disc02,Track01 Tuning` x1: gd1989-07-17.144302.Dak.boedicker.flac1644
- `fade in<` x2: skb2002-07-03.mk4v.shnf
- `Fur2010-11-21AkgARMS1 01 Tuneup` x4: Furthur2010-11-21.ARM.AKG480BCK69GraceV3SD744T192-24.TapSecFlac16-44, Furthur2010-11-21.ARM.AKG480BCK69GraceV3SD744T192-24.TapSecFlac24-48, Furthur2010-11-21.ARM.AKG480BCK69GraceV3SD744T192-24.TapSecFlac24-96, Furthur2010-11-21.ARM.AKG480BCK69SD744T192-24.TapSecFlac24-192
- `Fur2010-11-21AkgS1 01 Tuneup` x4: Furthur2010-11-21.AKG480BCK69GraceV3SD744T192-24.TapeSecAudFlac24-48, Furthur2010-11-21.AKG480BCK69GraceV3SD744T192-24.TapeSecAudFlac24-96, Furthur2010-11-21.AKG480BCK69SD744T192-24.TapeSecAudFlac16-44, Furthur2010-11-21.AKG480BCK69SD744T192-24.TapeSecAudFlac24-192
- `Fur2010-11-21NeuARMS1 01 Tuneup` x4: Furthur2010-11-21.ARM.NeumanKM140GraceV3SD744T192-24.TapSecFlac16-44, Furthur2010-11-21.ARM.NeumanKM140GraceV3SD744T192-24.TapSecFlac24-48, Furthur2010-11-21.ARM.NeumanKM140SD744T192-24.TapSecFlac24-192, Furthur2010-11-21.ARM.NeumanKM140SD744T192-24.TapSecFlac24-96
- `Fur2010-11-21NeuS1 01 Tuneup` x4: Furthur2010-11-21.NeumanKM140SD744T192-24.TapeSecAudFlac16-44, Furthur2010-11-21.NeumanKM140SD744T192-24.TapeSecAudFlac24-192, Furthur2010-11-21.NeumanKM140SD744T192-24.TapeSecAudFlac24-48, Furthur2010-11-21.NeumanKM140SD744T192-24.TapeSecAudFlac24-96
- `gd1985-07-01s1t01 Crowd Tuning.flac` x1: gd1985-07-01.176684.senn.nd41.strizak.flac2448
- `gd1985-07-01s2t01 Crowd Tuning.flac` x1: gd1985-07-01.176684.senn.nd41.strizak.flac2448
- `gd1990-07-19s1t02 - Tuning` x2: gd1990-07-19.154264.mac.billtmcdee.t.flac2496, gd1990-07-19.154265.mac.billtmcdee.t.flac1648
- `gd1990-07-19s1t04 - Tuning` x2: gd1990-07-19.154264.mac.billtmcdee.t.flac2496, gd1990-07-19.154265.mac.billtmcdee.t.flac1648
- `gd1990-07-19s1t06 - Tuning` x2: gd1990-07-19.154264.mac.billtmcdee.t.flac2496, gd1990-07-19.154265.mac.billtmcdee.t.flac1648
- `gd1990-07-19s1t08 - Tuning` x2: gd1990-07-19.154264.mac.billtmcdee.t.flac2496, gd1990-07-19.154265.mac.billtmcdee.t.flac1648
- `gd1990-07-19s1t10 - Tuning` x2: gd1990-07-19.154264.mac.billtmcdee.t.flac2496, gd1990-07-19.154265.mac.billtmcdee.t.flac1648
- `gd73-07-28 s1 t10 Tuning` x2: gd1973-07-28.141306.sbd.eaton.miller.clugston.flac1644, gd1973-07-28.141307.sbd.eaton.miller.clugston.flac2496
- `gd73-11-20 s1t01 Tuning` x3: gd1973-11-20.144245.sbd.hollister.remaster-01234.clugston.flac1644, gd1973-11-20.144265.sbd.boswell.smith.miller.clugston.flac1648, gd1973-11-20.144266.sbd.boswell.smith.miller.clugston.flac2496
- `gd73-11-20 s2t01 Tuning` x3: gd1973-11-20.144245.sbd.hollister.remaster-01234.clugston.flac1644, gd1973-11-20.144265.sbd.boswell.smith.miller.clugston.flac1648, gd1973-11-20.144266.sbd.boswell.smith.miller.clugston.flac2496
- `gd76-06-12 s1t01 Crowd` x2: gd1976-06-12.143166.fob.akg.d1000e.warburton.smith.miller.clugston.flac1648, gd1976-06-12.143167.fob.akg.d1000e.warburton.smith.miller.clugston.flac2496
- `gd76-06-15 s1t01 Tuning` x1: gd1976-06-15.143119.sbd.betty.dalton.clugston.miller.flac1644
- `gd76-06-15 s2t01 Crowd` x1: gd1976-06-15.143119.sbd.betty.dalton.clugston.miller.flac1644
- `gd77-10-02 s1t01 Crowd` x1: gd1977-10-02.142121.akg.d224e.troy.smith.miller.clugston.flac1648
- `gd80-09-06 s2t01 Crowd` x2: gd1980-09-06.142971.fob.nak700.wise.miller.clugston.flac2496, gd1980-09-06.142972.fob.nak700.wise.miller.clugston.flac1648
- `gd80-10-10 s3t01 Crowd` x2: gd1980-10-10.144765.nak700.severson.miller.clugston.flac1648, gd1980-10-10.144766.nak700.severson.miller.clugston.flac2496
- `gd81-03-28 12 Crowd_Tuning` x1: gd1981-03-28.140323.fm.eaton.miller.clugston.flac1648
- `gd81-05-01 s1 t01 Crowd` x2: gd1981-05-01.139774.fob.beyer.m160.streeter.miller.clugston.flac1644, gd1981-05-01.139775.fob.beyer.m160.streeter.miller.clugston.flac2496
- `gd81-05-01 s1t01 Crowd` x2: gd1981-05-01.142845.fob.senn421.wise.miller.clugston.flac2496, gd1981-05-01.142846.fob.senn421.wise.miller.clugston.flac1648
- `gd81-05-16 s1 t01 Crowd_Tuning` x2: gd1981-05-16.139958.fob.senn421.streeter.miller.clugston.flac1644, gd1981-05-16.139959.fob.senn421.streeter.miller.clugston.flac2496
- `gd81-05-16 s2 t01 Crowd_Tuning` x2: gd1981-05-16.139958.fob.senn421.streeter.miller.clugston.flac1644, gd1981-05-16.139959.fob.senn421.streeter.miller.clugston.flac2496
- `gd81-05-16 s2t01 Crowd` x2: gd1981-05-16.142973.set2.aud.beckwith.sterry.miller.clugston.flac2496, gd1981-05-16.142974.set2.aud.beckwith.sterry.miller.clugston.flac1648
- `gd81-07-04 11 Crowd_Tuning` x1: gd1981-07-04.140286.fob.nak300.vita.wise.miller.clugston.flac1648
- `gd81-09-12 s1t01 Crowd` x2: gd1981-09-12.142835.fob.senn421.wise.miller.clugston.flac2496, gd1981-09-12.142836.fob.senn421.wise.miller.clugston.flac1648
- `gd81-09-12 s2t01 Crowd` x2: gd1981-09-12.142835.fob.senn421.wise.miller.clugston.flac2496, gd1981-09-12.142836.fob.senn421.wise.miller.clugston.flac1648
- `gd81-09-26 s2 t01 Tuning` x2: gd1981-09-26.140027.set2.sbd.healy.miller.clugston.fixed.flac1644, gd1981-09-26.140028.set2.sbd.healy.miller.clugston.fixed.flac2496
- `gd81-12-31 s1t01 Tuning` x2: gd1981-12-31.143570.sbd.healy.walker.scotton.miller.clugston.flac1648, gd1981-12-31.143571.sbd.healy.walker.scotton.miller.clugston.flac2496
- `gd81-12-31 s3t01 Tuning` x2: gd1981-12-31.143570.sbd.healy.walker.scotton.miller.clugston.flac1648, gd1981-12-31.143571.sbd.healy.walker.scotton.miller.clugston.flac2496
- `gd82-04-06 s2t01 Crowd` x2: gd1982-04-06.143050.fob.nak700.wise.miller.clugston.flac1648, gd1982-04-06.143051.fob.nak700.wise.miller.clugston.flac2496
- `gd82-04-19 s1t01 Tuning` x2: gd1982-04-19.144567.sbd.healy.streeter.smith.miller.clugston.flac1648, gd1982-04-19.144568.sbd.healy.streeter.smith.miller.clugston.flac2496
- `gd82-04-19 s2t01 Tuning` x2: gd1982-04-19.144567.sbd.healy.streeter.smith.miller.clugston.flac1648, gd1982-04-19.144568.sbd.healy.streeter.smith.miller.clugston.flac2496
- `gd82-09-17 s1t01 Crowd` x2: gd1982-09-17.142823.fob.senn421.wise.miller.clugston.flac1648, gd1982-09-17.142824.fob.senn421.wise.miller.clugston.flac2496
- `gd82-09-17 s2t01 Crowd` x2: gd1982-09-17.142823.fob.senn421.wise.miller.clugston.flac1648, gd1982-09-17.142824.fob.senn421.wise.miller.clugston.flac2496
- `gd83-04-15 s2 t01 Tuning` x1: gd1983-04-15.140059.set2.sbd.pcm.gans.miller.clugston.flac1644
- `gd83-04-23 s1t01 Crowd` x2: gd1983-04-23.143126.fob.senn421.wise.clugston.miller.flac1648, gd1983-04-23.143127.fob.senn421.wise.clugston.miller.flac2496
- `gd83-04-23 s2t01 Crowd` x2: gd1983-04-23.143126.fob.senn421.wise.clugston.miller.flac1648, gd1983-04-23.143127.fob.senn421.wise.clugston.miller.flac2496
- `gd83-10-11 s1t01 Crowd` x2: gd1983-10-11.143610.fob.nak700.cohen.miller.clugston.flac1648, gd1983-10-11.143611.fob.nak700.cohen.miller.clugston.flac2496
- `gd83-10-12 s1t01 Crowd` x2: gd1983-10-12.143608.fob.nak700.cohen.miller.clugston.flac1648, gd1983-10-12.143609.fob.nak700.cohen.miller.clugston.flac2496
- `gd83-10-12 s2t01 Crowd` x2: gd1983-10-12.143608.fob.nak700.cohen.miller.clugston.flac1648, gd1983-10-12.143609.fob.nak700.cohen.miller.clugston.flac2496
- `gd83-10-15 s2t01 Crowd` x2: gd1983-10-15.143606.fob.nak700.cohen.miller.clugston.flac2496, gd1983-10-15.143607.fob.nak700.cohen.miller.clugston.flac1648
- `gd85-03-25 s1 t01 Crowd_Tuning` x2: gd1985-03-25.140841.unknown.bryant.miller.clugston.flac1644, gd1985-03-25.140842.unknown.bryant.miller.clugston.flac2496
- `gd85-03-25 s2 t01 Crowd_Tuning` x2: gd1985-03-25.140841.unknown.bryant.miller.clugston.flac1644, gd1985-03-25.140842.unknown.bryant.miller.clugston.flac2496
- `gd85-06-30 s2t01 Crowd` x2: gd1985-06-30.144154.set2.nak304.guy.pailes.miller.clugston.flac1648, gd1985-06-30.144155.set2.nak304.guy.pailes.miller.clugston.flac2496
- `gd85-07-01 s1t01 Crowd` x2: gd1985-07-01.144156.nak304.guy.pailes.miller.clugston.flac1648, gd1985-07-01.144157.nak304.guy.pailes.miller.clugston.flac2496
- `gd87-04-03 s2 t01 Crowd` x1: gd1987-04-03.141970.set2.fob.oade.cmc4.mk41.jacobs.miller.clugston.flac1644
- `gd89-07-07 s2t01 Crowd` x1: gd1989-07-07.142464.fob.schoeps.cmc4.mk41.mattes.miller.clugston.flac1648
- `gd89-10-16 s2t01 Crowd` x1: gd1989-10-16.142543.fob.schoeps.cmc4.mk4.mattes.miller.clugston.flac1648
- `JKB110506_03 Noise` x1: JohnKBand5611AtTheStateTheater
- `JKB110506_09 Noise` x1: JohnKBand5611AtTheStateTheater
- `JKB110506_12 Noise` x1: JohnKBand5611AtTheStateTheater
- `JKB110506_14 Noise` x1: JohnKBand5611AtTheStateTheater
- `JKB110506_16 Noise` x1: JohnKBand5611AtTheStateTheater
- `JKB110506_18 Noise` x1: JohnKBand5611AtTheStateTheater
- `JKB110506_20 Noise` x1: JohnKBand5611AtTheStateTheater
- `JKB110506_26 Noise` x1: JohnKBand5611AtTheStateTheater
- `tuning $$++[][]` x1: cd2008-03-13.onstage.murray.vgrm04.flac16
- `tuning @` x1: rd2007-07-21.schoeps-mk5.swanson.118843.flac1644
