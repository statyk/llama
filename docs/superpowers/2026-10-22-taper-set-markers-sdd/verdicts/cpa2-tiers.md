### Verdict
- Q1: **NEW DEFECT CLASS (1 class, 3 shows).** A line that names a set in a form the reader does not recognise becomes a song item, and the structure it states is silently dropped. The 3 shows: `- end of set one` (thedead-2009-04-25), `Set 1.5:` (gratefuldead-1974-07-19), `Cardinals Set 1 CD 2` (ryanadams-2008-01-21). The other 91 tier rows are correct taper readings, and I found no probe defect in the tiers.
- Q2: **NONE.** No owned row (648 library, 81 gate) loses today's encore without a taper encore marker. 13 library rows have a shorter encore than today, and in every one the taper marks its own encore. Mostly it is a Donor Rap or "callin em back" track that the taper lists before `E:`.
- Q3: the newly owned rows split 74 library (31 by (c), 30 by (b), 13 by R-ITEM) and 17 gate (5 by (c), 3 by (b), 9 by R-ITEM). Every one is genuine taper text placed correctly, except ryanadams-2008-01-21 (the Q1 class). All 41 newly not-owned rows have legitimate reasons: 7 veto gap, 34 ruling (d). But (d) also costs 8 rows where the taper's set break would have changed today's, among them gratefuldead-1966-11-19, a graded gate match now lost.

### Q1 table
Every row in all five tiers was dumped and checked against its text. The dumps are in `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-taper-markers/5c4f03eb-6157-439a-a1f1-688e02807eae/scratchpad/cpa2-tiers/` (`merged.txt`, `split_*.txt`, `enc_*.txt`, `moved_*.txt`, `q2*.txt`). The per-row classification is in `classification.jsonl` in the same directory, with `scope=Q1`.

**The 3 defects:**

| slug | tier | stored → taper | cause | evidence |
|---|---|---|---|---|
| thedead-2009-04-25 | songs moved | Sugaree: set 1 → set 2 | **READER** | The text reads `Disc Two/Set Two: Sugaree` / `- end of set one` / `Drums/Space…`. The taper's own note says Sugaree closed set 1, and the stored structure (jerrybase) agrees. The reader makes `- end of set one` a set-2 song item, so Sugaree ships as set 2's opener. |
| gratefuldead-1974-07-19 | songs moved | Seastones: set 2 → set 1 | **READER** | The text reads `Set 1:` … `Playing In The Band` / `Set 1.5:` / `Seastones` / `Set 2:`. `Set 1.5:` is not a marker and becomes an item. Seastones ships as set 1's closer, but the taper put it in neither set. |
| ryanadams-2008-01-21 | sets merged | 1 / 2 / 3 → 1 / 2 (solo opener plus Cardinals set 1 become set 1) | **READER, then SPEC** | The headers are `Ryan Solo CD 1`, `Cardinals Set 1 CD 2` and `Set 2 CD 3`. Only `Set 2 CD 3` is read, so the leading-block rule makes the whole solo section set 1. Fixing the header would change nothing: placement gives every track before the first boundary set 1's label, so an unnumbered leading section always lands in set 1. The taper treats the solo section as separate ("You can put the acoustic set at the beginning of set 2…"). Compare ryanadams-2008-01-19, a correct merge: there the taper writes `Set 1: Ryan Solo … Cardinals …`. |

**The other tier rows, all correct:**

| tier | rows | verdict |
|---|---|---|
| sets merged (other 4) | assemblyofdust-2004-12-31, mymorningjacket-2018-03-05, ryanadams-2008-01-19, tedeschitrucksband-2020-02-21 | CORRECT. The taper writes Encore 1/2, Set 1/2 plus encore, and the sub-heads `Set 1: Ryan Solo … Cardinals`. |
| sets split (22) | 13 rows unchanged since the last run, plus 9 new: corblund-2004-11-04 (`Disc/Set1..3`), darkstarorchestra-2017-02-10, derektrucksband-2003-12-26, derektrucksband-2008-10-23, greenskybluegrass-2013-05-04, lotus-2006-02-18, railroadearth-2005-02-19, soulive-2001-12-15, yondermountainstringband-2006-06-14 | All CORRECT. darkstarorchestra-2017-02-10, furthur-2011-03-11 and derektrucksband-2006-01-22 repair stored structures that were wrong. gratefuldead-1974-09-18 is idiosyncratic but is what the text says (Phil and Ned written as `Set Two`). |
| encore folded (0) | — | Truly empty. No owned row in the library or the gate has stored encore tracks while the taper has none, counting filler tracks too, so nothing is mis-bucketed elsewhere. |
| encore added (31) | 23 unchanged, plus 8 new: davealvin-2008-11-01, JRAD 2017-05-06, JRAD 2018-10-25, JRAD 2019-09-28, radiators-1991-01-18, radiators-2006-04-21, robertwalters20thcongress-2004-01-02, yondermountainstringband-2006-10-21 | All CORRECT. The taper writes `Encore`, `E:`, `-(encore)-`, `[Encore]`, `encores:`, `==Encores==` or `ENCORE 1/2`. Several repair stored rows: a stored `3` that was really the encore (JRAD 2016-02-10, JRAD 2022-04-30, JRAD 2017-05-06), and the stored 4 sets of tedeschitrucksband-2019-11-15. |
| songs moved (35) | 33 correct, plus the 2 defects above | The moves follow the taper's text. Donor Rap, crowd and "callin em back" tracks move ahead of the `E:` marker. Set openers written by the taper: `Space`, `Morfbeats`, `Jam`, `Marco Solo`, `Sound 1`, `Batman tease`, `(acoustic) Think What You've Done`. Set closers written by the taper: `Truckin'`, `Playin' reprise`, `Ritual Jam > Chillout Jam` (to set 3). Godzilla (moe-2006-10-06; the track title itself says "(Encore)") goes into the encore. |
| filler only (1) | aquariumrescueunit-1992-07-07 | CORRECT. Only the `Band Intros > Jam` filler moves. |

**Reader gaps that change nothing.** None of these alters a shipped label today:
- The `con't` continuation spelling is not in `_CONT`: `Set II (con't.)`, `Set 2 con't`, `Set 1(con't)-`. It appears in 9 owned rows, always inside its own set, so the result is identical either way.
- `set one-(1:05:59)` (motherhips-1995-08-06) is not read; the leading-block rule produces the same result.
- `Set 1.`, `Set`, `Set I * […]` and `CD 2` lines are left as items at the start of a set.

**Probe nit.** The delta prints `match=miss` for joerussosalmostdead-2017-03-11 and robertwalters20thcongress-2004-01-02, but both are renum rows that the gate summary does not grade. Both are correct taper readings: the "miss" comes from target indices in the original numbering.

### Q2
I compared encore counts for every owned library row (648) and every owned gate row (81), over all tracks including filler. No owned row has today's encore with no taper encore.

13 owned library rows have fewer encore tracks than today. In all 13, `has_encore` is True and the taper's text puts the moved tracks before its encore marker:

| slug | tracks moved from today's encore into the last set | text |
|---|---|---|
| darkstarorchestra-2001-12-15 | Lovelight | `Set 2 (cont): … Death Don't> / Lovelight / Encore: Baby Blue` |
| darkstarorchestra-2017-02-10 | 11 tracks | Today labels all of set 2 as encore, which is wrong. Taper: `Set 2` … `Encore / 12. Brokedown Palace / 13. White Rabbit` |
| furthur-2009-12-13 | Donor Rap | `11. Phil's Donor Rap` / `12. E: US Blues` |
| furthur-2010-05-29 | Donor Rap | `7. Donor Rap` / `E1: Muli Guli` |
| furthur-2010-06-26 | At A Siding, Terrapin Flyer, Donor Rap | `… At a Siding* > Terrapin Flyer*, Donor Rap, E: Brokedown Palace` |
| furthur-2010-06-27 / -07-05 / -09-23, furthur-2011-02-13 / -03-11 | Donor Rap (or `Doner Rap`) | listed before `E:` / `Encore:` / `ENCORE:` |
| philleshandfriends-2006-07-03 | Viola v3, crowd, Donor Rap | `07. Viola v3 08. crowd 09. Donor Rap… 10. encore: Midnight Hour` |
| radiators-2006-02-10 | callin em back | `10 callin em back` / `encores:` |
| thedead-2009-04-25 | Donor Rap | `Donor Rap` / `E: Brokedown Palace`. This show's separate Sugaree defect is in Q1. |

The only real songs these rows move out of today's encore are Lovelight, At A Siding / Terrapin Flyer, and Viola v3, and the taper's text places each one. Tools: `tools/dump.py`, `tools/dump2.py` and `tools/q2gate.py`; outputs `q2a.txt`, `q2b.txt` and `q2gate.txt`.

### Q3
Method: I exported `taper.py` at each Checkpoint A commit (5010a00, then items 1 to 7) and re-ran `decide_taper` per row, which attributes each flip to the commit that caused it. All 132 delta rows flip at exactly one commit, and the totals agree with `delta_summary.txt`. Outputs: `attrib_lib.jsonl` and `attrib_gate.jsonl`; the header lines each row matched are in `hdr_lib.txt`.

**Newly owned, library (74):**
- **(c) disc-and-set shapes, 31 rows.** Forms seen: `Set 1 Disc 1`, `Disc 1: Set I`, `Disc/Set1`, `Set1/CD1`, `set 1/Disc 1`, `Disc I, Set I`, `Disk 1 Set 1`, `Disc I 1st Set`, `Set 1/Disk 1:`, `Disc 01 [Set I]`, `~Disc 1: Set 1~`, `CD 1 - Set 1`, `1st set disc one:`, `DISC ONE, 1ST SET`, `Disk 1/Set I:`. 20 rows have labels identical to today; the 11 that differ are correct (reviewed in Q1), apart from **ryanadams-2008-01-21**, which is wrong (Q1). radiators-1980-01-14, previously voided as "skipped set number", is now owned and identical to today.
- **(b) annotation, 30 rows.** 25 are JRAD headers of the form `Set One (9:30PM - 10:46PM):` / `Set 1 (8:21pm):`. The rest: `1st Set (80:21)` (deadandcompany ×2), `Set I (68:48)`, `Set I (66:47:02)`, `Set 1 (01:14:40)`, `Set 1  (58:24)`, `Set One (46:20)`, `Set 1 (9:45pm - 11:20pm)`. 23 are identical to today and 7 differ correctly. No prose was admitted.
- **R-ITEM, 13 rows.** Junk items such as `-----`, `(total 1h 57 min)`, `01: Truckin'`, `s1t11 - Deal`, `Disc 1:`, `Disc 2:`, `-Disk 2`, `Blues` (now `44 Blues`), `%`, `-`, `Etc` and `Goodby` are now stripped or kept whole. 9 are identical to today and 4 differ correctly.
- All 52 identical rows have real headers (`hdr_lib.txt`), and placement agrees with today's at song level.

**Newly owned, gate (17):**
- 13 match the target and 2 are filler-only (philleshandfriends-2007-10-07, railroadearth-2014-11-28).
- The 2 "misses" are ungraded renum rows, both correct (see the probe nit above).
- 3 have no target: derektrucksband-2003-12-26, soundtribesector9-2007-07-08 (`Set 1/Disc 1:`), thecodetalkers-2003-10-31 (`DISC 1 SET ONE`). All three are correct.
- By mechanism: (c) 5, (b) 3 (cowboyjunkies `SET ONE (50:28)`, JRAD ×2), R-ITEM 9. No wrong row.

**Newly not owned (35 library, 6 gate). Every reason is legitimate:**
- **Veto gap, 7 library rows:** darkstarorchestra-2013-12-29 `Encor:`, railroadearth-2011-10-30 `9E.`, ratdog-2014-02-14 `E Ripple`, shakedownband-2013-08-24 `24. E Ripple`, and soundtribesector9 2003-11-01 / 2004-06-25 / 2004-10-31 `-e-`/`E~`. Each is a taper-written encore that would have been folded.
- **Ruling (d), 28 library and 6 gate rows.** Each has no taper encore marker while today has one, which is the operator's rule applied exactly.
  - **Cost of (d)** (`dcost.txt`): in 8 of the 34 rows, the taper's numbered break differs from today's, so a set-break repair is lost as well.
    - Library (4): ryanadams-2007-10-14 and ryanadams-2008-01-25 (today has no set 2; ryanadams-2007-10-14 keeps a 7-song encore), ryanadams-2008-09-29, smashingpumpkins-1998-05-19.
    - Gate (4): darkstarorchestra-2011-07-31, mymorningjacket-2008-12-31 and philleshandfriends-2008-07-04 (today has no set 2 in any of them), and **gratefuldead-1966-11-19**, where the taper's reading exactly matched the adjudicator target, which has no encore.
  - Also: thedead-2009-04-21 is now computed as today, with a stored 10-track encore that the last reviewer judged wrong.

### Notes for the operator
- The one new hazard: unrecognised set-naming text, 3 of 648 owned rows. A "set-token in a numbered-set item" veto would catch all 3. It would also hit 3 harmless rows (localh-2004-12-31, neworleanssuspects-2012-08-02, motherhips-1995-08-06), where an unread `Set 1.`/`set one-(…)` header is item 0. It must skip trailing notes after the encore songs: 7 more rows such as "Trey… plays entire 2nd set".
- ryanadams-2008-01-21 is partly a spec matter. An unnumbered leading section (`Ryan Solo`) always takes set 1's label at placement, so fixing the header alone will not change it.
- Ruling (d) protects every encore, as intended. Its price is 8 rows where today's set break also stays wrong, one of them a graded gate match. The ruling's no-merge clause is what makes it cost this.
- Optional, no-risk: add `con't` to `_CONT` (9 owned rows, no label change).
- Q2 is clean. All 13 shortened encores follow the taper's own encore marker.
