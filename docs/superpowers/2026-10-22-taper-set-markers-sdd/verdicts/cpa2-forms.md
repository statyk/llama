### Verdict — NO DEFECT CLASS
No non-marker match of (b) or (c) places a boundary or changes ownership, in the library or anywhere in the cached corpus. The item-cleaning and pre-split changes never change ownership toward a wrong structure on a library show.

### Drop-criterion hits
**None.**

How I checked (HEAD 5a5343f, read-only, with `./.venv/bin/python -I`; `llama.__file__` resolves inside the worktree):
- **Variant ablation over the library.** Each Checkpoint A change was reverted by monkeypatch on HEAD's `llama.taper`, one change at a time:
  - noB: no `_ANNOT` in any header regex;
  - noC: the pre-2abad1e disc regex (`disc` word, `(` or dash/slash only), and no `_SET_DISC_HEADER`;
  - noItem: the pre-025e713 `_song_titles`;
  - noPre: no `_split_set_and_encore`.
  
  Then `decide_taper` was run on all 3,522 evaluable library shows (458 override shows and 3 with no tracks skipped, as in the probe). Every show whose decision changed was printed with today's breaks, HEAD's breaks, every line the variant classifies differently (with neighbours) and the placed boundary tracks. I read all of them.
  - noB: 30 shows that HEAD owns and the variant does not, from 60 load-bearing lines. All are `1st Set (80:21)`, `Set One (9:30PM - 10:46PM):`, `Set 1 (01:14:40)` or `Set 1\xa0 (58:24)` style headers above the set's own track list. Ownership never runs the other way; there is no "both own, labels differ".
  - noC: 31 shows, from 70 load-bearing lines. All are disc+set headers above their set's track list: `Set 1 Disc 1:`, `Disc 1: Set I`, `Disc/Set1`, `Set1/CD1`, `Disc I 1st Set`, `Disc 01 [Set I]`, `CD 1 - Set 1`, `Disk 1/Set I:`, `DISC ONE, 1ST SET`, `1st set disc one:`. They include continuations such as `Set 1 Disc 2`, `Set 2/Disc 3` and `DISC THREE, 2ND SET (cont.)`. None runs the other way, and none has labels differing.
  - noPre: 0 ownership changes (one reason text changes: `cross-check: 3` becomes `cross-check: 3, encore`, moe-2008-01-24).
- **Corpus-wide (all 15,607 cached items, description and notes).** Every line that HEAD classifies as a set header and a variant does not:
  - (b): 425 lines over 221 fields;
  - (c): 623 lines, of which 291 are set-first (124 fields) and 332 are newly admitted disc-first shapes (171 fields).
  
  Results:
  - **No (b) hit carries any rest text.** Every one is a header alone on its line, the annotation being a duration, a clock range or `...`. So no lineage or prose can ride on the (b) form.
  - The only (c) hits with a rest are a duration (`Set I Disc 1: 74:16`, `Set 2/Disc 2:(51:02)`, `Disc 3: Set 2 cont'd: [40:08]`), dropped by `_TIMESTAMP_ONLY`, and `CD#1: First set: 23 tracks 79:33` (cvb2003-02-28), whose rest can only make placement decline.
  - I screened the line after each header for lineage words, non-song shapes or blank context: 78 lines flagged, all read. Every one is a genuine header of a blank-line-spaced or bracketed track list.
  - I also screened for set/disc disagreement and for texts that name other nights, box sets or volumes.
    - Disagreements: `Set 2 Disc 1`/`Set 3 Disc 2` (rads1987-05-14) and `set 2 disc 1` (pf2006-2-11) are genuine. `Set II/Disc 1` (furthur2011-04-03.…neumann) sits in a second, pasted info file after `Encore`, so it voids the structure (`numbered marker after the encore`).
    - No `Disc N, Set M` naming another night was found.
    - DSO2010-08-12's "boxed" and the multi-date JRAD notes (debut-date footnotes) are not disc/box-set uses.
- **Built lines (`_classify`).**
  - Not matched: `Set 1 (Schoeps MK4 > ...)`, `Set 1 (Disc 1)`, `Set 1 (??:??)`, `Set 2... was hot`, `Set 1 Disc 1 of 3`, `Disc 2 - Set 1 of 2`, `Disc 1, Set 1 (11/02/89)`, `CD1 Set 1 recorded by`.
  - Matched with a lineage or date rest that placement neutralises (no live instance): `Set 1 (9:30): Schoeps MK4 > V3`, `Disc 1, Set 1: 12/31/89`, `Disc 1 Set 1 - Schoeps`.

### Per-form table
| form | raw lines (probe) | load-bearing in library | non-marker hits | of which can matter | verdict |
|---|---|---|---|---|---|
| (b) header + `(duration)` / `(time range)` / `...` | 425 / 215 items (my scan: 425 / 221 fields) | 30 shows, 60 lines; 23 identical to today, the rest follow the taper's own text | 0 (no (b) hit has a rest) | 0 | keep |
| (c) set first (`Set 1 Disc 1`, `Set 1/Disc 1:`, `Set I Disc 1: 74:16`) | 291 / 123 (mine 291 / 124) | 31 shows across both (c) halves, 70 lines | 0 | 0 | keep |
| (c) disc first, newly admitted (`Disc 1: Set I`, `Disc I 1st Set`, `Disc 01 [Set I]`, `CD 1 - Set 1`, `Disc/Set1`, `Disk 1/Set I:`, `Disc I, Set I`, `DISC ONE, 1ST SET`) | 332 lines / 171 fields newly read, within the probe's 970 disc-first | (in the 31) | 0. Lineage-like rests: only `23 tracks 79:33` (cvb2003-02-28, makes placement decline) | 0 | keep |
| pre-split set-and-encore hold (now also over (c) shapes: `~Disc 1: Set 1+Encore~`, `Set II + Encore Disc IV`) | 18 | 0 ownership changes | 0 | 0 | keep |

### Item-cleaning check
- **Library:** reverting R-ITEM loses ownership on exactly 14 shows. It gains none, and no owned show changes labels.
  - The cleaning is load-bearing only where junk sat at a boundary: `------`, `-----`, `%`, `-`, `==============`, `Disc 1:`, `Disc 2:`, `-Disk 2`, `(total 1h 57 min)`, `01: Truckin'`, `s1t11 - Deal`, the `44 Blues` double strip, and the comma holds `Farewll, solong, Goodby` and `Oh My God Whatever, Etc`.
  - In all 14, the placed boundary tracks are the taper's set-end songs. 10 are identical to today. darkstarorchestra-2017-02-10, railroadearth-2005-02-19, derektrucksband-2003-12-26 and robertwalters20thcongress-2004-01-02 follow real `Set 2`/`Encore` headers that today missed (robertwalters' gate "miss" carries `renum: true`).
- **Corpus:** item lists change in 2,873 texts (mostly the prefix strip). Assertion changes in exactly one text (kw2007-02-23, own-less; below).
- **Why the class is safe:**
  - Dropping an item can only make the next item the boundary song. If the dropped item was a real song on the tape, its non-filler track then sits between *a* and *b*, so placement declines.
  - A comma-held two-song line (`Like The Christian Life, Roll On Blues`, `Kick To The Head, Burrito On The Floor`) `fuzzy_title_eq`-matches both tracks (checked). So it gives 2 hits and declines, matches a merged track exactly, or, matching one, leaves the other as a non-filler track between.
  - There are 84 comma items at boundaries corpus-wide. In the library, yondermountainstringband-2006-01-28 is not owned and greyboyallstars-1996-03-09 is unchanged and correct (its tape has the merged track).

### Own-less collateral
Strictly own-less (the variant asserts, HEAD does not): 1 text each. None of the three would have placed.
- **(b):** ttb2020-02-29.mk41v.edtyre. Lineage `set 1 : taper…`/`set 2 : schoeps…`, then the real `Set 1  (65:02)`, gives `void: decreasing set number`. Before, the text asserted on the lineage and was unplaced (`taper : mike inhatt`).
  - Also: 2 one-set texts became `void: numbered marker after the encore`. Neither asserted before.
- **(c):** dso2003-02-28.shnf (library darkstarorchestra-2003-02-28). `Disc 2 Set 1 (cont):` after a bare `1:` gives `void: continuation without its set's header`. Before: unplaced on `Music`.
  - Also, with no assertion before: lotus-2005-10-15 (`void: numbered marker after the encore`, the pinned case), philleshandfriends-2006-10-28 and furthur-2010-03-08 / umphreysmcgee-2005-07-06 (continuation voids).
  - Placement-level: campervanbeethoven-2003-02-28, where `CD#1: First set: 23 tracks 79:33` puts `25 tracks 68:48` as set 2's first song. It is vetoed first on a track title anyway.
- **Item cleaning:** kw2007-02-23 (library kellerwilliams-2007-02-23). The `(Disc Two /` + `Set Two:)` layout left only `)` items, and dropping them empties the sets, so the structure is `void: empty set`. Before: unplaced on `)`.

### Notes for the operator
- ryanadams-2008-01-21 (newly owned via (c), one line `Set 2 CD 3`): the marker is real, but the earlier `Cardinals Set 1 CD 2` is not read (a word comes first). The leading-block rule therefore folds Ryan's 3-song solo opener into set 1. Today: 3 sets; taper-owned: 2 (1–14, 15–21). Worth a look in the report-3 pre-screen. Not a form defect.
- furthur-2011-04-03 (via (b)) puts `Phil Donor Rap` in the encore, because the taper's `-Encore-` sits above it. joerussosalmostdead-2017-05-06 and -2019-09-28 relabel today's set 3 as `encore`, and 2019-09-28 also moves 4 tracks into set 1. All follow the text: songs moved, so report-3 rows.
- Placement, not form shape, is again what neutralises every lineage or count rest. The (b) form never carries a rest in the live corpus.
- Scratch is in /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-taper-markers/5c4f03eb-6157-439a-a1f1-688e02807eae/scratchpad/cpa2-forms/: variants.py, libvar.py/libvar.jsonl, corpus2.py/corpus2.jsonl, inspect_show.py, noB_owned.txt, noC_owned.txt, noItem_owned.txt, ctx_odd.txt. Repo, ~/.llama and ~/.llama-harness untouched.
