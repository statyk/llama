# Blind-the-tags: how often is the `setlist-gap` rung wrong?

**This is the M1 evidence for Phase A of the title-correspondence plan.** It
answers one question: when `structure.adopt_gap_titles` fills a count-forced
run of unresolved tracks from the canonical setlist, how often is the title it
adopts *not* the title the tape itself carries?

**Branch:** `title-correspondence` @ `a37bb83` — the reviewed Phase A HEAD.
Every number below was produced against that tree. The harness itself lands as
`8ac7d77` and this document on top of it; neither commit touches `packages/`,
so the code measured is byte-identical to the code that would ship.

**Source:** every number comes from the REAL
`llama.structure.adopt_gap_titles`, run in-process. The harness
(`scripts/blind_tag_gapfill.py`) is a driver and a scorer; it reimplements
nothing it measures. `adopt_gap_titles`, `titles.resolve_titles`,
`junk.filter_files`, `setlist.parse_setlist`, `structure.rank_parses`,
`structure.blend_segues`, `gather._collect_parses`,
`gather._strip_head_banner`, `gather._drop_artist_items`,
`gather._show_metadata_norms`, `gather._sibling_titles` and
`gather._recover_format_titles` are all imported and called. The canonical
setlist is therefore **the real gather canonical**
(`_collect_parses` → `rank_parses` → `blend_segues` → `_strip_head_banner` →
`_drop_artist_items`), not raw `parse_setlist` output — which is the specific
thing that made the design spec's 45–52% pilot figure a bound rather than a
truth.

**Anchor kinds are spied, not inferred.** `adopt_gap_titles` does not expose
which anchors it bound or how. The harness wraps `structure._merge_run` for the
duration of each call and records which of its calls returned a hit; a track
carrying more than one title component whose `_merge_run` call succeeded was
bound as a **merged** anchor, and every other anchor by exact normalized
equality. The breakout below is therefore a reading taken from the function
under test, not a guess about it.

**Standing caveat (offline).** These runs have `setlistfm=None`. Several of
these shows' real canonicals are setlist.fm-won, and setlist.fm parses are
cleaner than LMA description parses. **Every figure here is a bound, not a
truth**, and it is a bound in the pessimistic direction for correctness: the
LMA-only canonical is the noisier input.

---

## The harness can return non-empty — checked before anything below was believed

A harness that silently adopts nothing and a harness that correctly finds no
errors produce identical output. This exact failure has already happened twice
on this branch in miniature (a verification that produced nothing because a
plugin was not on `PYTHONPATH`, which looked precisely like a clean run), so it
was checked first and is checked on every run.

**1. The summary block prints an adoption count and a firing count
unconditionally**, on stdout and stderr, whether or not anything was wrong. On
the corpus run those read `trials in which gap-fill FIRED: 15118` and `scored
adoptions: 28605`. Neither number can be nonzero unless the real
`adopt_gap_titles` ran and really adopted.

**2. The scorer was shown to be able to emit `wrong` at all**, against cases
built to produce one:

```console
$ ./.venv/bin/python scripts/blind_tag_gapfill.py --selftest
# selftest: real adopt_gap_titles, real spy, real scorer
  A single-anchor gap that is right: track 3 anchor=single verdict=ok adopted='Deal' hidden='Deal'
  B single-anchor gap that is WRONG (canonical disagrees with the tape): track 3 anchor=single verdict=wrong adopted='Sugaree' hidden='Deal'
  C merged-anchor gap (left anchor consumes two items): track 2 anchor=merged verdict=ok adopted='Estimated Prophet' hidden='Estimated Prophet'
# selftest adoptions=3 saw_wrong=True
# SELFTEST PASSED: the harness adopts, and it can score an adoption wrong
```

Case B is a four-track tape tagged `Bertha / Jack Straw / Deal / Loser` against
a canonical reading `Bertha / Jack Straw / Sugaree / Loser`; track 3 is blinded,
the gap is count-forced 1-for-1 between two exact anchors, and a correct
implementation *must* adopt `Sugaree`. Case C additionally proves the
`_merge_run` spy fires and is attributed to the right track: the left anchor is
one tagged file `Scarlet Begonias > Fire On The Mountain` consuming two
canonical items, and the row comes back `anchor=merged`. The selftest exits
non-zero if it ever adopts nothing or never scores a `wrong`.

---

## Method

For every cached archive.org item under `~/.llama/cache/md_*.json`
(read-only; nothing under `~/.llama` is written):

1. Group the cache into performances with the real
   `grouping.group_candidates` — so early/late splits, `/spans` and
   `/unassigned` come out exactly as production produces them — and measure
   every recording in turn as the *chosen* one, since the chosen recording is
   the one whose tags are on trial.
2. Reproduce `run_gather`'s prefix (gather.py:508–635) minus the workspace I/O
   and the setlist.fm lookup, ending in the `tracks` list and the
   `metadata_norms`/`aliases` that `adopt_gap_titles` is called with.
3. Enumerate every window of 1–3 consecutive **tag-titled** tracks whose
   flanking tracks are themselves titled (or which touch a tape edge). Windows
   whose neighbour is *already* unresolved are skipped: blinding one would
   merge with a pre-existing run and only part of the resulting gap would have
   ground truth behind it.
4. Blind that window — one window per trial — by applying
   `resolve_titles`' own fallback ladder (titles.py:150–160) to those tracks
   only: the whole-tape `setlist` rung if it is live for this recording, else
   the `sibling` rung, else `unresolved`. Nothing else on the tape moves.
   (Blanking the file dicts and re-running `resolve_titles` outright was
   rejected: removing three titles perturbs `clean_tag_titles`' enumerated-tape
   gate and can change the *other* tracks' titles — i.e. the anchors.)
5. Call the real `adopt_gap_titles`, with the `_merge_run` spy armed.
6. Score every adopted track inside the blinded window against the tag it could
   not see, by `fuzzy_norm_title` equality. Adoptions *outside* the window have
   no ground truth and are counted separately as unverifiable (135 of 28,740,
   0.5%).

### Two populations are reported, and they are different

Trials overlap by construction: blinding `[3,3]`, `[3,4]` and `[3,5]` all put
track 3 in a gap. **Per-trial** counts therefore weight a track by how many
windows contain it. **Distinct** counts collapse every row making the same
claim about the same track (same identifier, track, adopted title, hidden tag,
anchor kind). The triage below operates on the distinct population, and so does
the ship gate; the per-trial numbers are reported because the spec's pilot
counted that way ("1,652 firings, 3,144 adoptions") and the comparison is
otherwise not like-for-like.

---

## Corpus and headline numbers

```console
$ ./.venv/bin/python scripts/blind_tag_gapfill.py --progress 100 > gapfill-mp3.tsv
format=mp3
cached items scanned          : 968
items with usable audio       : 960
items offering >=1 blind run  : 949
blinding trials run           : 57098
  trials pre-empted by a higher rung: setlist=25416, sibling=1138
trials in which gap-fill FIRED: 15118
scored adoptions              : 28605
unverifiable adoptions        : 135
  pooled  ok=26497 wrong=2108 rate=7.37%
  single  ok=26010 wrong=2086 rate=7.42%
  merged  ok=487 wrong=22 rate=4.32%
distinct adoptions            : 6864
  pooled  ok=6237 wrong=627 rate=9.13%
  single  ok=5990 wrong=617 rate=9.34%
  merged  ok=247 wrong=10 rate=3.89%
```

**The 25,416 pre-empted trials are not a harness defect and are worth reading.**
On a recording where the parsed canonical's item count happens to equal the kept
file count, `titles.resolve_titles`' whole-tape `setlist` rung answers first and
the gap never forms — so `adopt_gap_titles` is unreachable on that recording, in
this experiment and in production alike. That is 44% of trials. It is the same
mechanism as the fixture caveat below, at corpus scale.

**Raw wrong-rate is not the answer.** 627 distinct wrong adoptions is the number
before triage, and the pilot's headline contained all three classes. The great
majority of these are the scorer disagreeing with itself, not the adoption being
wrong.

### Robustness: the same sweep on `flac`

```console
$ ./.venv/bin/python scripts/blind_tag_gapfill.py --format flac --progress 400 > gapfill-flac.tsv
format=flac
cached items scanned          : 968
items with usable audio       : 683
...
distinct adoptions            : 4892
  pooled  ok=4491 wrong=401 rate=8.20%
  single  ok=4316 wrong=393 rate=8.35%
  merged  ok=175 wrong=8 rate=4.37%
```

Different delivery format, largely overlapping but differently-filtered tapes,
same raw rate to within a point and the same ordering between anchor kinds. The
flac sweep was **not** hand-triaged; it is reported as a consistency check on
the pre-triage rate only, and no gate is taken from it.

---

## The three-way triage

Every one of the 627 distinct wrong adoptions was classified by hand into
exactly one class. 627 rows collapse to **382 distinct (adopted, hidden)
pairs**; the classification is per pair, applied to every row carrying it.

**The rule, stated before the exceptions:**

- **`scorer-artifact`** — adopted and hidden name the same song or the same
  segment, differing only by spelling variant, punctuation, diacritics, a
  leading article, a subtitle kept or dropped, a segue/encore/duration/taper
  annotation, an abbreviation or nickname, or because the adoption names one
  component of a merged tape track. The adoption is acceptable; the strict
  `fuzzy_norm_title` equality the scorer uses is what failed. **This class
  includes cases where the adopted title is the *worse* rendering of the right
  song** (`Sugar Magnoli` for `Sugar Magnolia`, `Miles From Denver` for
  `40 Miles From Denver` — the canonical's own text, warts included). Those are
  cosmetic, not correspondence errors.
- **`tag-typo-adoption-superior`** — the hidden tag is a misspelling or mangling
  and the adopted title is the correct rendering. Split out from
  `scorer-artifact` on this test: is the *tag* a plausible rendering of the
  song's name at all? `Lazy Lightnin'` is; `Loset` is not.
- **`genuinely-wrong`** — the adopted title names a different song, a different
  segment, or a different movement (main vs reprise) than the tape carries at
  that position.

**Auditing this classification from this document alone:** every pair in the
`genuinely-wrong` and `tag-typo-adoption-superior` tables below is enumerated in
full. Everything else — the residue — is `scorer-artifact`.

Three judgement calls made deliberately and recorded so they can be overturned:

1. **Main vs reprise counts as genuinely wrong.** `Playin' In The Band` and
   `Playin' In The Band Reprise` are different tracks in different halves of a
   Dead second set, and the pairing appears in both directions in the data
   (`Reprise` adopted over a `Band` tag *and* `Band` adopted over a `Reprise`
   tag), which is the signature of a shift rather than of loose tagging. Same
   for `Dark Star Reprise`/`Dark Star` and `Hey Jude Reprise`/`Hey Jude`.
   **Fifteen** distinct adoptions ride on this call. Calling them cosmetic
   instead would move the pooled genuinely-wrong rate from 1.57% to **1.35%**
   (93/6,864) — so the headline is not sensitive to it in any direction that
   changes a decision.
2. **Interchangeable jam/segment labels are broken out as a subclass rather
   than excused.** `Jam` adopted where the tape says `Space`, `Drums` where the
   tape says `Jam`, and so on: 56 distinct adoptions where both sides are
   improvisation-segment names that tapers genuinely use interchangeably. They
   are *not* counted in the headline `genuinely-wrong` figure, because the
   adopted string does not misattribute a song; they are reported separately and
   the "including filler-segment" total is given everywhere the headline is.
   Anyone who thinks that is too generous should read the second number.
3. `Phil & Ned`/`Seastones` and `Sunshine Daydream`/`Sugar Magnolia` are the
   same music under two names and are `scorer-artifact`;
   `One More Saturday Night`/`One More Halloween Night` is a taper's Halloween
   joke on the same song and is likewise `scorer-artifact`.

### Results

```console
$ python triage.py            # roll-up over the classification below
distinct adoptions: 6864  ok=6237  wrong=627
  scorer-artifact: 422  (6.15% of all distinct adoptions)
  genuinely-wrong: 108  (1.57% of all distinct adoptions)
  genuinely-wrong/filler-segment: 56  (0.82% of all distinct adoptions)
  tag-typo-adoption-superior: 41  (0.60% of all distinct adoptions)
  genuinely-wrong incl. filler-segment: 164 (2.39%)
  single: n=6607 genuinely-wrong=107 (1.62%) +filler=163 (2.47%) artifact=415 typo=39
  merged: n=257 genuinely-wrong=1   (0.39%) +filler=1   (0.39%) artifact=7   typo=2
  interior: n=5708 genuinely-wrong=85 (1.49%)
  edge:     n=1156 genuinely-wrong=23 (1.99%)
```

| | distinct adoptions | genuinely-wrong | rate | incl. filler-segment |
|---|---|---|---|---|
| **pooled** | 6,864 | 108 | **1.57%** | 164 (2.39%) |
| single anchors only | 6,607 | 107 | **1.62%** | 163 (2.47%) |
| **≥1 merged anchor** | 257 | 1 | **0.39%** | 1 (0.39%) |
| interior gaps | 5,708 | 85 | 1.49% | — |
| edge gaps (one anchor + a tape end) | 1,156 | 23 | 1.99% | — |

The "incl. filler-segment" column is very close to the spec pilot's **2.4%
interior / 1.5% edge**, from a different instrument on a differently-built
canonical. That is corroboration, not a coincidence to lean on.

### The merged-anchor path is not the weak point the docstring feared

This was the gate the plan added on top of the brief (Rulings 7 and 9): a
merged anchor binds via `_merge_run`, which compares components with
`fuzzy_title_eq` and falls through to `_is_subphrase`, so it can land one item
off and count-forcing cannot catch a same-size shift.

Measured: **1 genuinely-wrong adoption out of 257 distinct merged-anchor
adoptions, 0.39%** — four times *better* than the single-anchor path, not
worse. And the one case is not a merged-anchor failure. It is
`billystrings2021-08-14.Neumann` track 3, where the canonical carries an extra
item (`There Is a Time`) the tape does not:

```
billystrings2021-08-14.Neumann  ... run 2-3  track 3  merged  wrong  There Is a Time | Red Daisy
billystrings2021-08-14.Neumann  ... run 3-3  track 3  single  wrong  There Is a Time | Red Daisy
```

The identical error occurs at the same track with a *single* anchor when the
blinded window starts one track later. The merged bind is incidental.

**Consequence for the ship decision:** the conservative tightening the plan held
in reserve — making `_merge_run`'s call site in `adopt_gap_titles` require
exact per-component equality — **is not indicated by this evidence and should
not be applied.** It would decline 257 adoptions to prevent one error that a
single anchor produces anyway. Recorded as measured, not as an argument that
the docstring's stated weakness is impossible; it is reachable, it is just not
where the errors are.

### What the genuinely-wrong adoptions actually are

Reading the 88 distinct pairs below, they fall into four recognisable shapes,
and the first one accounts for most of them:

**1. The tape carries filler the canonical does not list.** `Estimated` adopted
over a `Tuning` tag; `Bertha` over `Tuning`; `Blues For Allah` over `Tuning`;
`Saint Stephen` over `Tuning/Dead Air`; `Sugaree` over `Crowd/Tuning`;
`Crazy Fingers` over `Tuning/ Bill Graham intro`. The tape has a tuning track
between two songs, the canonical setlist does not, so the one-file gap is
count-forced against the *next song's* item and every adoption in that
neighbourhood slides by one. **Count-forcing is satisfied exactly because the
shift is size-preserving** — this is the same "consistency is not correctness"
failure the spec records for the LLM aligner and the unanchored DP, in its
third costume. It is the dominant failure mode of this rung and it is not
detectable from inside the mechanism.

**2. The canonical carries a truncated or split item.** `Prophet` adopted over
a `Bertha` tag (the parser emitted a bare `Prophet` item, splitting
`Estimated Prophet`), `Weather Report Suite Part 1` over `Let It Grow`, and
`Let It Grow` over `Spanish Jam` on five different tapes of gd1974-07-19 — one
upstream parse defect reproduced across every recording of the same
performance. Note the corollary: **wrong adoptions are correlated across
sibling recordings**, so 108 distinct adoptions are fewer than 108 independent
failures.

**3. Main vs reprise.** Fifteen adoptions, per judgement call 1 above.

**4. Tail junk adopted as a title — the most serious shape, and the smallest.**
`gd1991-09-10` (two recordings): the last track's tag is
`It's All Over Now Baby Blue` and the adopted title is
**`Branford Marsalis on saxophone throughout`** — a taper's credit line sitting
at the *end* of the parsed setlist. `_strip_head_banner` cleans the head only;
there is no tail equivalent, and `_hygienic` passes the string (it has three
letters, is under 80 characters, is not `is_junk_title`, and is not in
`metadata_norms`). Both instances are **edge gaps**: a trailing run anchored on
one side only, whose span runs to the end of the canonical — which is precisely
where the junk lives. Same shape: `= no lyrics` adopted on two
recordings of gd1975-06-17, both at track 18, both edge gaps (one classed
`genuinely-wrong`, one `filler-segment` because the tag it displaced was
`Crowd Out`). This is four distinct adoptions out of 6,864 in the blind test,
but see the exposure section: it is **one of the two** adoptions the rung makes
on the cache as it actually stands.


### The classification, in full

Every `genuinely-wrong` and `tag-typo-adoption-superior` pair is listed. The
`scorer-artifact` table is a sample; that class is the residue, so anything not
appearing in the two complete tables belongs to it. `n` is distinct adoptions
(not trials); `anchor` and `edge` show how those adoptions split.

#### genuinely-wrong — 108 distinct adoptions, 88 distinct pairs

| n | adopted (canonical item) | hidden (tape tag) | anchor | edge | first example |
|---|---|---|---|---|---|
| 4 | `Estimated` | `Tuning` | single:4 | int:4 | `gd1977-04-23.143220.weidner.akg-d200e.miller.flac1644 t12` |
| 3 | `Playing In The Band` | `Playin' (Reprise)` | single:3 | int:3 | `gd1991-06-17.dts.dan.33670.sbeok.flac16 t18` |
| 3 | `Prophet` | `Bertha` | single:3 | int:3 | `gd1977-04-23.139535.fob.ecm.99a.hopkins.miller.clugston.flac1648 t21` |
| 2 | `Bertha` | `Tuning` | single:2 | int:2 | `gd1977-04-23.139535.fob.ecm.99a.hopkins.miller.clugston.flac1648 t22` |
| 2 | `Blues For Allah` | `Tuning` | single:2 | int:2 | `gd1975-06-17.fob.menke.motb.97078.flac24 t10` |
| 2 | `Estimated` | `Take A Step Back` | single:2 | int:2 | `gd1977-04-23.139535.fob.ecm.99a.hopkins.miller.clugston.flac1648 t19` |
| 2 | `Hey Jude Reprise` | `Hey Jude ->` | single:2 | int:2 | `gd1989-10-09.sbd.miller.32902.sbeok.flac16 t20` |
| 2 | `Let It Grow` | `Spanish Jam >` | single:2 | int:2 | `gd1974-07-19.mtx.sirmick.103132.sbeok.flac16 t20` |
| 2 | `Mama Tried` | `Sugaree` | single:2 | edge:2 | `gd1979-12-28.167365.nak700.biggar.smith.miller.clugston.flac1648 t2` |
| 2 | `Playin' In The Band` | `Playing In The Band (reprise)` | single:2 | int:2 | `gd1977-11-04.141004.aud.boswell.smith.sirmick.flac2496 t21` |
| 2 | `Playin' In The Band Reprise` | `Playin in the Band>` | single:2 | int:2 | `gd1989-10-09.125737.mk4.48khz.flac16 t14` |
| 2 | `Saint Stephen` | `Tuning/Dead Air` | single:2 | int:2 | `gd1977-05-08.sbd.cantor.sacks.266.shnf t17` |
| 2 | `Stronger Than Dirt Or Milkin' The Turkey` | `Blues For Allah >` | single:2 | int:2 | `gd1975-06-17.fob.menke.motb.97078.flac24 t11` |
| 2 | `Sugaree` | `Crowd/Tuning` | single:2 | edge:2 | `gd1979-12-28.167365.nak700.biggar.smith.miller.clugston.flac1648 t1` |
| 2 | `There Is a Time` | `Red Daisy` | merged:1/single:1 | int:2 | `billystrings2021-08-14.Neumann t3` |
| 2 | `Weather Report Suite Part 1` | `Let It Grow >` | single:2 | int:2 | `gd1974-07-19.mtx.sirmick.103132.sbeok.flac16 t19` |
| 1 | `(Encores) It's All Over Now` | `Sugar Magnolia` | single:1 | int:1 | `gd1982-08-10.sbd.kempa.334.shnf t46` |
| 1 | `= no lyrics` | `U.S. Blues` | single:1 | edge:1 | `gd1975-06-17.mtx.menke.gems.97079.flac16 t18` |
| 1 | `Alligator` | `Jam` | single:1 | int:1 | `gd71-04-29.sbd.frisco.16782.sbeok.shnf t22` |
| 1 | `Angeline` | `Instrumental` | single:1 | int:1 | `bluegrassgenerals2017-01-06.matrix t8` |
| 1 | `Back In The Goodle Days` | `Good Ole Days` | single:1 | int:1 | `tmc2015-05-23 t7` |
| 1 | `Beat It On Down The Line` | `Crazy Fingers` | single:1 | edge:1 | `gd1975-06-17.fob.menke.motb.97078.flac24 t2` |
| 1 | `Bertha` | `The Music Never Stopped` | single:1 | int:1 | `gd1977-04-23.sonyECM99a.hopkins.minches.83685.flac16 t15` |
| 1 | `Blue Collar Blues` | `I Love My Job` | single:1 | int:1 | `ymsb2010-07-16.aud.flac16 t2` |
| 1 | `Boo Boo` | `Rise Up` | single:1 | int:1 | `los1996-08-09.shnf t2` |
| 1 | `Branford Marsalis on saxophone throughout` | `It's All Over Now Baby Blue` | single:1 | edge:1 | `gd1991-09-10.fob.brennecke-young.GEMS.96422.flac16 t22` |
| 1 | `Branford Marsalis on saxophone throughout` | `It’s All Over Now, Baby Blue` | single:1 | edge:1 | `gd1991-09-10.153418.mtx.photoleon.flac1644 t22` |
| 1 | `Crazy` | `Used To Call Me Baby` | single:1 | int:1 | `ymsb2010-07-16.aud.flac16 t8` |
| 1 | `Crazy Fingers` | `Tuning/ Bill Graham intro` | single:1 | edge:1 | `gd1975-06-17.fob.menke.motb.97078.flac24 t1` |
| 1 | `Crowd/Tuning` | `I Know You Rider` | single:1 | int:1 | `gd1982-08-10.sbd.kempa.334.shnf t28` |
| 1 | `Crowd/Tuning` | `Stagger Lee` | single:1 | int:1 | `gd1982-08-10.sbd.kempa.334.shnf t20` |
| 1 | `Cryptical Envelopment` | `Drums` | single:1 | int:1 | `gd85-06-30.aud.oade-sacks.set2.7833.sbefail.shnf t5` |
| 1 | `Cryptical Envelopment` | `Drums >` | single:1 | int:1 | `gd1985-06-30.165131.s2.sbd.pcm.latvala.miller.flac1644 t6` |
| 1 | `Cryptical Envelopment` | `Midnight Hour` | single:1 | int:1 | `gd1968-02-14.sbd.douglas-cleef.2267.shnf t7` |
| 1 | `Dark Star Reprise` | `Dark Star >` | single:1 | int:1 | `gd1991-09-10.sbd.sacks.tetzeli.fix-511.34678.reflac.flac16 t13` |
| 1 | `Depot Bay` | `Too Tired` | single:1 | int:1 | `gsbg2014-02-28.BusmanLD.24bit t13` |
| 1 | `Drums` | `Dark Star` | single:1 | int:1 | `gd91-06-17.sbd.gardner.3591.sbeok.shnf t14` |
| 1 | `E. And We Bid You Good Night` | `Not Fade Away` | single:1 | edge:1 | `gd1989-10-26.sbd.cribbs.1829.shnf t34` |
| 1 | `Estimated Prophet` | `Crowd` | single:1 | edge:1 | `gd1977-02-26.sbd.wizard.32009.sbefail.shnf t31` |
| 1 | `Ewie with the Crooked Horn` | `Instrumental (forgot)` | single:1 | int:1 | `ymsb2010-07-16.aud.flac16 t13` |
| 1 | `Feel Like A Stranger` | `Tuning` | single:1 | edge:1 | `gd1980-11-30.128440.naks.mason.flac16 t2` |
| 1 | `First Terrapin Station` | `E: U.S. Blues` | single:1 | edge:1 | `gd1977-02-26.sbd.wizard.32009.sbefail.shnf t30` |
| 1 | `Fixin' To Ruin` | `Old Dangerfield*` | single:1 | int:1 | `bluegrassgenerals2017-01-06.matrix t5` |
| 1 | `Good Morning Little Schoolgirl` | `Morning Dew` | single:1 | edge:1 | `gd68-02-14.sbd.kaplan.15640.sbeok.shnf t1` |
| 1 | `Good Times` | `Never Trust A Woman >` | single:1 | int:1 | `gd84-04-26.sbd.pj.4770.sbeok.shnf t13` |
| 1 | `Hey Jude Reprise` | `Hey Jude >` | single:1 | int:1 | `gd1989-10-09.mtx.v2.haugh.92495.flac16 t19` |
| 1 | `Hillbillies` | `Getting Down The Road**` | single:1 | int:1 | `bluegrassgenerals2017-01-06.matrix t14` |
| 1 | `Introduction` | `Morning Dew` | single:1 | edge:1 | `gd1968-10-12.139745.sbd.miller.Glassberg.flac1644 t1` |
| 1 | `It Must Have Been The Roses` | `Run For The Roses` | single:1 | edge:1 | `gd1974-06-18.sbd.bertha-ashley.18150.sbeok.shnf t2` |
| 1 | `It's All Over Now Baby Blue` | `Crowd` | single:1 | edge:1 | `gd1991-09-10.fob.brennecke-young.GEMS.96422.flac16 t21` |
| 1 | `It's All Over Now Baby Blue` | `encore break` | single:1 | edge:1 | `gd1991-09-10.153418.mtx.photoleon.flac1644 t21` |
| 1 | `La Bamba` | `Good Lovin\'` | single:1 | int:1 | `gd1987-09-18.sbd.bobh.10536.sbeok.shnf t30` |
| 1 | `Let It Grow` | `Spanish Jam` | single:1 | int:1 | `gd1974-07-19.sbd.gans-finney.217.sbeok.shnf t5` |
| 1 | `Let It Grow` | `Spanish Jam ->` | single:1 | int:1 | `gd1974-07-19.shure.unknown.102766.flac16 t20` |
| 1 | `Let It Grow` | `Spanish Jam>` | single:1 | int:1 | `gd1974-07-19.sbd.pre-dankfix.4596.sbeok.shnf t20` |
| 1 | `Man Smart` | `Shakedown Street>` | single:1 | int:1 | `gd1987-09-18.nak300.pasternak.mallick.105497.flac16 t8` |
| 1 | `Momma` | `outtro and taper signout` | single:1 | edge:1 | `HackensawBoys2007-06-13 t31` |
| 1 | `Morning Dew` | `Good Morning Little Schoolgirl` | single:1 | edge:1 | `gd68-02-14.sbd.kaplan.15640.sbeok.shnf t2` |
| 1 | `Natural to Be Gone` | `What's the Difference >` | single:1 | int:1 | `tmc2015-05-23 t6` |
| 1 | `Not Fade Away` | `Saint Stephen` | single:1 | int:1 | `gd77-05-08.sbd.hicks.4982.sbeok.shnf t15` |
| 1 | `Not Fade Away` | `Saint Stephen->` | single:1 | int:1 | `gd1977-05-08.sbd.cantor.sacks.266.shnf t18` |
| 1 | `On the Run` | `Encore break` | single:1 | int:1 | `ymsb2009-08-28.dpa4027.flac16 t27` |
| 1 | `Playin' In The Band` | `Playin' In The Band Reprise` | single:1 | int:1 | `gd1977-11-04.141833.sony.ecm33p.moore.dalton.miller.clugston.flac1644 t20` |
| 1 | `Playin' In The Band Reprise` | `Playin` | single:1 | int:1 | `gd89-10-09.schoeps.howland.443.sbeok.shnf t12` |
| 1 | `Playin' In The Band Reprise` | `Playin' In The Band` | single:1 | int:1 | `gd1989-10-09.nak300.juteau.116646.flac t14` |
| 1 | `Playin' In The Band Reprise` | `Playin' in the Band` | single:1 | int:1 | `gd83-06-18.senn421.nawrocki.14411.sbeok.shnf t16` |
| 1 | `Saint Stephen` | `Not Fade Away` | single:1 | int:1 | `gd77-05-08.sbd.hicks.4982.sbeok.shnf t16` |
| 1 | `Saint Stephen` | `Not Fade Away->` | single:1 | int:1 | `gd1977-05-08.sbd.cantor.sacks.266.shnf t19` |
| 1 | `Scarlet Begonias` | `Minglewood Blues` | single:1 | int:1 | `gd1978-04-16.sbd.unknown.20085.shnf t14` |
| 1 | `Shakedown Street` | `E: Knockin' On Heaven's Door` | single:1 | int:1 | `gd1987-09-18.nak300.pasternak.mallick.105497.flac16 t7` |
| 1 | `Supplication` | `Don't Ease Me In` | single:1 | int:1 | `gd84-10-31.senn.14947.sbeok.shnf t8` |
| 1 | `Take a Step Back` | `Fire On The Mountain` | single:1 | int:1 | `gd1977-04-23.sbd.aj.gardner.4334.shnf t34` |
| 1 | `The Music Never Stopped` | `tuning` | single:1 | int:1 | `gd1977-04-23.sonyECM99a.hopkins.minches.83685.flac16 t16` |
| 1 | `The Other One` | `Spanish Jam` | single:1 | int:1 | `gd84-04-07.sbd.dodd.13816.sbeok.shnf t15` |
| 1 | `The Wheel` | `Space >` | single:1 | int:1 | `gd84-07-13.sbd.ferguson.353.sbeok.shnf t15` |
| 1 | `Throwing Stones` | `The Other One` | single:1 | int:1 | `gd84-04-07.sbd.dodd.13816.sbeok.shnf t16` |
| 1 | `Throwing Stones` | `Wharf Rat` | single:1 | int:1 | `gd84-04-07.sbd.dodd.13816.sbeok.shnf t17` |
| 1 | `Tied Down` | `[banter/crowd]` | single:1 | int:1 | `gsbg2007-03-03.matrix.flac16 t28` |
| 1 | `Tuning` | `Feel Like A Stranger` | single:1 | edge:1 | `gd1980-11-30.128440.naks.mason.flac16 t1` |
| 1 | `U.S. Blues` | `Crowd` | single:1 | edge:1 | `gd1975-06-17.mtx.menke.gems.97079.flac16 t17` |
| 1 | `U.S. Blues` | `Crowd + Tune Up` | single:1 | edge:1 | `gd1977-02-26.sbd.wizard.32009.sbefail.shnf t29` |
| 1 | `Weather Report Suite Part 1` | `Let It Grow` | single:1 | int:1 | `gd1974-07-19.sbd.gans-finney.217.sbeok.shnf t4` |
| 1 | `Weather Report Suite Part 1` | `Let It Grow ->` | single:1 | int:1 | `gd1974-07-19.shure.unknown.102766.flac16 t19` |
| 1 | `Weather Report Suite Part 1` | `Let It Grow>` | single:1 | int:1 | `gd1974-07-19.sbd.pre-dankfix.4596.sbeok.shnf t19` |
| 1 | `Weather Report Suite Prelude` | `WRS Part I>` | single:1 | int:1 | `gd1974-07-19.sbd.pre-dankfix.4596.sbeok.shnf t18` |
| 1 | `Wharf Rat` | `Throwing Stones` | single:1 | int:1 | `gd84-04-07.sbd.dodd.13816.sbeok.shnf t18` |
| 1 | `What You're Selling` | `Things You're Selling` | single:1 | int:1 | `ymsb2007-02-01.SBD-KM184.flac16 t21` |
| 1 | `Wheel Hoss` | `Tied Down` | single:1 | int:1 | `gsbg2007-03-03.matrix.flac16 t27` |

#### genuinely-wrong / filler-segment subclass — 56 distinct adoptions, 25 distinct pairs

| n | adopted (canonical item) | hidden (tape tag) | anchor | edge | first example |
|---|---|---|---|---|---|
| 10 | `Jam` | `Space ->` | single:10 | int:10 | `gd1989-10-09.aud.robr.31211.sbeok.shnf t18` |
| 10 | `Jam` | `Space >` | single:10 | int:10 | `gd1989-10-09.dts.dan.26235.sbeok.shnf t16` |
| 5 | `Jam` | `Space>` | single:5 | int:5 | `gd1989-10-09.125737.mk4.48khz.flac16 t17` |
| 3 | `Drums` | `Dark Star Jam >` | single:3 | int:3 | `gd1991-06-17.dts.dan.33670.sbeok.flac16 t14` |
| 3 | `Space` | `Drums ->` | single:3 | int:3 | `gd1991-06-17.128692.mtx.dusborne.flac16 t15` |
| 3 | `Space` | `Drums >` | single:3 | int:3 | `gd1991-06-17.dts.dan.33670.sbeok.flac16 t15` |
| 2 | `Drums` | `Dark Star Jam ->` | single:2 | int:2 | `gd1991-06-17.128692.mtx.dusborne.flac16 t14` |
| 2 | `Drums` | `Space ->` | single:2 | int:2 | `gd1984-06-27.getto.aud.122873.flac16 t7` |
| 2 | `Drums` | `Space >` | single:2 | int:2 | `gd84-03-28.fob-faintych.miller.27303.sbeok.shnf t15` |
| 1 | `= no lyrics` | `Crowd Out` | single:1 | edge:1 | `gd1975-06-17.fob.menke.motb.97078.flac24 t18` |
| 1 | `Drums` | `Dark Star jam ->` | single:1 | int:1 | `gd1991-06-17.150371.FOB.Schoeps.Brotman.Metchick.Miller.Noel.t-flac1648 t13` |
| 1 | `Drums` | `Jam` | single:1 | int:1 | `gd68-10-12.sbd.eD.10909.sbeok.shnf t8` |
| 1 | `Drums` | `Jam \>` | single:1 | int:1 | `gd1968-10-12.sbd.gans.miller.owen.9385.shnf t16` |
| 1 | `Drums` | `Space` | single:1 | int:1 | `gd85-06-30.aud.oade-sacks.set2.7833.sbefail.shnf t6` |
| 1 | `Intro` | `Blah, Blah, Blah` | single:1 | edge:1 | `ymsb2006-08-25.neumann140.flac16 t1` |
| 1 | `Jam` | `Primal Jam >` | single:1 | int:1 | `gd1971-04-29.sbd.murphy.1858.shnf t39` |
| 1 | `Jam` | `Space` | single:1 | int:1 | `gd91-06-17.sbd.gardner.3591.sbeok.shnf t16` |
| 1 | `Jam` | `Space/Jam` | single:1 | int:1 | `gd90-03-22.sbd.bertha-ashley.21433.sbeok.shnf t15` |
| 1 | `Jam` | `The Eleven Jam % >` | single:1 | int:1 | `gd1975-09-28.aud.gofob.86250.flac16 t9` |
| 1 | `Jam` | `eleven jam>` | single:1 | int:1 | `gd1975-09-28.sbd.unknown.2562.sbefail.shnf t9` |
| 1 | `Space` | `Drums` | single:1 | int:1 | `gd91-06-17.sbd.gardner.3591.sbeok.shnf t15` |
| 1 | `Spanish Jam` | `Space` | single:1 | int:1 | `gd84-04-07.sbd.dodd.13816.sbeok.shnf t14` |
| 1 | `Spanish Jam` | `Space ->` | single:1 | int:1 | `gd84-04-23.set2-sbd.miller.14949.sbeok.shnf t7` |
| 1 | `[ instrumental ]` | `Unknown Title #1` | single:1 | int:1 | `delmccouryband2005-07-29.flac16 t5` |
| 1 | `[ instrumental ]` | `[ banjo tune ]` | single:1 | int:1 | `del2005-07-29.mk21.flac16 t5` |

#### tag-typo-adoption-superior — 41 distinct adoptions, 34 distinct pairs

| n | adopted (canonical item) | hidden (tape tag) | anchor | edge | first example |
|---|---|---|---|---|---|
| 3 | `Loser` | `Loset` | single:3 | int:3 | `gd1974-02-24.136140.mtx.tobin.flac16 t10` |
| 2 | `Around & Around` | `Arouond & Around` | single:2 | int:2 | `gd1977-05-25.147785.fob.shure.sm57.sublette.miller.clugston.flac1648 t22` |
| 2 | `Gimme Some Lovin'` | `Gimmie Some Lovin` | single:2 | int:2 | `gd1985-06-30.126176.chasingwilma.flac24 t12` |
| 2 | `Mexicali Blues` | `Mexical Blues` | single:2 | int:2 | `gd1980-11-29.132456.aud.flac16 t8` |
| 2 | `Mexicali Blues` | `Mexicalli Blues` | single:2 | int:2 | `gd85-06-30.aud.set1.mckeown.7893.sbefail.shnf t5` |
| 2 | `Watermelon Man` | `is Watermelon Man` | merged:1/single:1 | int:2 | `lkeel2009-03-07.dpa4022_portico t6` |
| 1 | `- All Four Wheels` | `All Four` | single:1 | int:1 | `gsbg2015-01-22.c4.flac16 t19` |
| 1 | `Box Of Rain` | `Box OfRain` | single:1 | int:1 | `gd1973-02-09.sbd.ashley.12571.shnf t24` |
| 1 | `Brown Eyed Women` | `Bown Eyed Women` | single:1 | int:1 | `gd79-10-27.sbd.clugston.13980.sbeok.shnf t6` |
| 1 | `Damned If The Right One Didn't Go Wrong` | `Damed if the right one didnt go wrong` | single:1 | int:1 | `ymsb2006-08-25.neumann140.flac16 t10` |
| 1 | `First Girl I Ever Loved` | `is First Girl I Ever Loved` | merged:1 | edge:1 | `lkeel2009-03-07.dpa4022_portico t3` |
| 1 | `Franklin's Tower` | `Franklins's Tower` | single:1 | int:1 | `gd1975-09-28.unknown.beggs.236.shnf t5` |
| 1 | `GDTRFB` | `Goin' Down The Raod Feeling Bad` | single:1 | int:1 | `gd1977-04-23.143220.weidner.akg-d200e.miller.flac1644 t20` |
| 1 | `Gimme Some Lovin'` | `Gimmie Some Lovin'` | single:1 | int:1 | `gd85-06-30.aud.oade-sacks.set2.7833.sbefail.shnf t3` |
| 1 | `Goldbricking` | `Goldbreaken` | single:1 | int:1 | `del2002-05-24.shnf t3` |
| 1 | `Greatest Story Ever Told` | `Greates Story Ever Told ->` | single:1 | int:1 | `gd1971-04-29.sbd.unknown.4333.shnf t42` |
| 1 | `I Ain't Superstitous` | `I Ain' Superstitious` | single:1 | int:1 | `gd85-04-08.sbd.wiley.8755.sbeok.shnf t7` |
| 1 | `It Hurts Me Too` | `It Hurts Me To` | single:1 | edge:1 | `gd1971-04-29.sbd.haugh.33565.flac16 t3` |
| 1 | `It's All Over Now Baby Blue` | `It's All Ove Now Baby Blue` | single:1 | edge:1 | `gd84-12-31.sbd.gorinsky.6395.sbeok.shnf t21` |
| 1 | `Jack Straw` | `Jack Staw` | single:1 | edge:1 | `gd1978-04-16.139240.sbd.ForTheFaithful_KTS528-529.flac1644 t1` |
| 1 | `Looks Like Rain` | `Look Like Rain` | single:1 | int:1 | `gd1973-05-26.147312.aud.taback.flac16 t8` |
| 1 | `Loser` | `Lose/r` | single:1 | edge:1 | `gd1980-11-30.128440.naks.mason.flac16 t3` |
| 1 | `Me And Bobby McGee` | `Me & My Bobby McGee` | single:1 | int:1 | `gd1971-04-29.sbd.haugh.33565.flac16 t12` |
| 1 | `Me And Bobby McGee` | `Me and My Bobby McGee` | single:1 | int:1 | `gd1971-04-29.mtx.hansokolow.97660.flac16 t12` |
| 1 | `Morning Dew` | `Moring Dew` | single:1 | int:1 | `gd1977-05-08.148737.SBD.Betty.Anon.Noel.t-flac2448 t22` |
| 1 | `New Minglewood Blues` | `New Minlewood Blues` | single:1 | edge:1 | `gd1982-08-10.152133.mouth.akg-ce1.mac.uherarchive.rogers.wise.flac2444 t3` |
| 1 | `New Speedway Boogie` | `New Speedway Boogies` | single:1 | int:1 | `ymsb2010-07-17.aud.flac16 t9` |
| 1 | `Peggy-O` | `Peggio` | single:1 | int:1 | `gd1975-06-17.aud.unknown.87560.flac16 t5` |
| 1 | `Playin' In The Band` | `Playing In The Bnad` | single:1 | int:1 | `gd1974-07-19.shure.unknown.fix-102766.102866.flac16 t10` |
| 1 | `Stronger Than Dirt Or Milkin' The Turkey` | `tronger Than Dirt Or Milkin' The Turkey >` | single:1 | int:1 | `gd1975-06-17.fob.menke.motb.97078.flac24 t13` |
| 1 | `Tennessee Jed` | `Tennesee Jed` | single:1 | int:1 | `gd1973-11-17.sbd.patched.bec.22799.flac16 t6` |
| 1 | `Tennessee Jed` | `Tennesse Jed` | single:1 | int:1 | `gd1974-06-18.sbd.bertha-ashley.18150.sbeok.shnf t21` |
| 1 | `They Love Each Other` | `The Love Each Other` | single:1 | edge:1 | `gd77-09-03.sbd.unk.276.sbefixed.shnf t2` |
| 1 | `Wharf Rat` | `Whar Rat` | single:1 | int:1 | `gd84-04-19.aud.willy.14013.sbeok.shnf t17` |

#### scorer-artifact — 422 distinct adoptions, 235 distinct pairs (sample of the 20 most frequent)

| n | adopted | hidden |
|---|---|---|
| 31 | `Minglewood Blues` | `New Minglewood Blues` |
| 16 | `Promised Land` | `The Promised Land` |
| 11 | `We Can Run But We Can't Hide` | `We Can Run` |
| 8 | `Mississippi Half-Step Uptown Toodleloo` | `Mississippi Half-Step Uptown Toodeloo` |
| 8 | `Touch Of Gray` | `Touch of Grey` |
| 8 | `Drums` | `Drumz>` |
| 7 | `New Minglewood Blues` | `Minglewood Blues` |
| 7 | `Day Job` | `Keep Your Day Job` |
| 6 | `Prophet` | `Estimated Prophet` |
| 5 | `She Makes My Love` | `She Makes My Love Come Rolling Down` |
| 5 | `My Brother Esau` | `Brother Esau` |
| 5 | `CC Rider` | `C.C. Rider` |
| 4 | `We Bid You Good Night` | `And We Bid You Good Night` |
| 4 | `Mississippi Half-Step Uptown Toodleloo` | `Mississippi Half Step` |
| 4 | `The Promised Land` | `Promised Land` |
| 4 | `Stronger Than Dirt Or Milking The Turkey` | `Stronger Than Dirt Or Milkin' The Turkey >` |
| 4 | `Mississippi Half Step` | `Mississippi Half-Step Uptown Toodeloo` |
| 4 | `C.C. Rider` | `CC Rider` |
| 4 | `Women Are Smarter` | `Man Smart, Woman Smarter` |
| 4 | `Mississippi Half-Step Uptown Toodleloo` | `Mississippi Half-Step Uptown Toodeloo >` |

---

## Exposure: what the rung does to the cache as it actually stands

The blind test manufactures gaps. This measures the real ones — blinding
nothing, running `adopt_gap_titles` over every cached item exactly as gathered:

```console
$ ./.venv/bin/python scripts/blind_tag_gapfill.py --natural --progress 400 > natural-mp3.tsv
items measured                : 960
naturally unresolved tracks   : 210
items the rung changes at all : 2
tracks the rung fills         : 2

is2008-12-06.flac16.aud   34  for being so nice and quiet which allowed me to pull a nice recording.  is2008-12-06d2t22.mp3
ymsb2010-07-17.aud.flac16 19  Robot Jam                                                               ymsb2010-07-17d2t10.mp3
```

**Two adoptions across 960 items and 210 genuinely-unresolved tracks. One is
exactly right and one is a taper's thank-you sentence.**

- `ymsb2010-07-17` track 19 is the mechanism working as designed. The tape's
  own tags run `... Another Day / <untagged> / Ramblin In The Rambler pt.1 ...`;
  the canonical has `Another Day / Robot Jam / Ramblin In The Rambler pt.1`; the
  gap is one file against one item between two exact anchors. `Robot Jam` is a
  title nothing else in llama could have recovered, and today it ships as
  `ymsb2010-07-17d2t10.mp3`.
- `is2008-12-06` track 34 is failure shape 4. It is the last file on the tape;
  the parsed canonical's 39th and final item is the tail of the taper's notes,
  `for being so nice and quiet which allowed me to pull a nice recording.`; the
  gap is an **edge** gap anchored on the left only, so its span runs to the end
  of the canonical. One item, one file, count-forced, hygienic — adopted.

The other 208 unresolved tracks are not touched, overwhelmingly because they sit
on wholly-untagged tapes where there are no anchors at all, or in runs whose
item count does not match. That is count-forcing declining, which is what it is
for.

**Read this number honestly in both directions.** It bounds the damage Phase A
can do on today's cache to one bad title. It also bounds the *good* it does to
one good title, and the 1.57% blind-test rate is measured on 6,864 synthetic
adoptions that the production population does not currently supply. The
mechanism's value is prospective — it fires when a tape is well tagged *except*
for a short run — and the exposure measurement says that situation is rare in
this library today.

---

## The ship gate

The plan's gate: *"ship unflagged only if `genuinely-wrong` is at or below the
tag rung's own typo baseline."* Ruling 9 made the by-anchor-kind breakout a
second, independent gate.

**Gate on the merged-anchor path: passes, decisively.** 0.39% (1/257) against
1.62% (107/6,607) for single anchors. The merged path is the better one.

**Gate on the pooled rate: cannot be settled as written, because the reference
quantity does not exist.** "The tag rung's own typo baseline" has never been
measured in this repo, and this instrument cannot measure it without
circularity: the tags are the ground truth here, so an experiment that scores
them needs a *third* source. What this instrument does yield are two bounds:

- **≥ 0.60%** of adoptions (41 of 6,864) sit at a position where the tape's tag
  is demonstrably defective and the adopted canonical title is better — a
  *floor* on the tag rung's error rate, since it only counts tag defects large
  enough to be scored wrong and small enough for me to adjudicate.
- **6.5%** of scored disagreements (41 of 627) are the tag's fault rather than
  the adoption's.

Against the floor, 1.57% is about 2.6× the tag rung's demonstrated error rate,
so on a literal reading the pooled gate **does not pass**. Against any honest
estimate of the true tag-typo rate the comparison is unresolved — the floor is
certainly a large undercount, because every tag defect the canonical happens to
reproduce is invisible to this experiment.

**I am recording that the gate is unresolvable as specified rather than
adjusting the measurement until it resolves.** No threshold was moved and no
class boundary was drawn after seeing a number; the three judgement calls above
were all made before the roll-up was run, and judgement call 1 — the only one
that moves the headline — was made in the *conservative* direction.

### Recommendation

**Ship Piece 1, with the edge/trailing-gap path tightened first — not
unflagged, and not abandoned.** Reasoning, in the order it should be weighed:

1. **The merged-anchor gate passes and the reserved tightening should not be
   applied.** That is a clean result and it retires Ruling 7's open question.
2. **The strict genuinely-wrong rate of 1.57% is the good half of the number.**
   Roughly two thirds of it is one upstream defect class — the canonical parse
   listing songs the tape splits differently, or the tape carrying filler the
   canonical omits — and it is correlated across sibling recordings, so it is
   fewer than 108 independent failures. Against the alternative (the track
   ships as `gd77-05-08d2t04.mp3`), a 98.4%-correct title is a large
   improvement in what a listener sees and what a scriptwriter reads.
3. **The one shape I would not ship as-is is the trailing edge gap.** It is
   where `_hygienic` demonstrably fails — a taper's sentence and a lineage
   credit adopted as track titles — because `_strip_head_banner` has no tail
   counterpart and the trailing span of a parsed LMA setlist is where the notes
   live. It is 1 of the 2 real adoptions on today's cache. Two options, in
   preference order:
   - **decline edge gaps whose span reaches the last canonical item** (a
     three-line change in `adopt_gap_titles`; strictly conservative, costs the
     1.99% edge population and prevents both observed junk adoptions), or
   - **add a tail counterpart to `_strip_head_banner`**, which is the real fix
     and is Phase-B-sized.
   Either is above this task; both are cheaper than shipping the taper sentence.
4. **A review flag on adoption is defensible but I do not recommend it as the
   primary control.** At today's exposure it would fire on 2 shows out of 89 and
   would have flagged the good adoption as loudly as the bad one; the shape that
   needs catching is specific enough to decline outright.

**This is a recommendation, not a decision.** Whether Phase A ships unflagged,
ships flagged, ships with the edge tightening, or is held is the plan owner's
call.

---

## Fixture caveat: `gd73_metadata.json` pre-empts the code under test

**Read this before writing any test against the canonical fixture.** It cost the
Phase A plan author three separate debugging cycles, and Phase B has more
fixture-dependent tests than Phase A did.

`packages/llama/tests/fixtures/gd73_metadata.json` filters to **6 kept `VBR MP3`
files**, and its description parses to **6 setlist items at
`confidence="high"`**:

```console
$ ./.venv/bin/python -c "..."   # filter_files + parse_setlist on the fixture
kept mp3 files: 6
parsed items: 6 confidence: high
names: ['gd73-06-10d1t01.mp3', ..., 'gd73-06-10d3t01.mp3']
items: ['Morning Dew', 'China Cat Sunflower', 'I Know You Rider', 'Dark Star', 'Eyes of the World', 'Johnny B. Goode']
```

`titles.resolve_titles`' whole-tape rung is gated on
`setlist.confidence != "low" and len(setlist.items) == n` (titles.py:129–147).
On this fixture that is `6 == 6`, so **the rung fires**. Consequences:

- **A test that blanks a tag on gd73 to create an unresolved run does not create
  one.** The blanked positions resolve as `title_source == "setlist"` and
  `adopt_gap_titles` never sees a gap. The test then passes or fails for reasons
  that have nothing to do with the code it names.
- **This is a fixture property, not a production one.** The same rung fires
  **zero** times across 2,015 production tracks:

  ```console
  $ ./.venv/bin/python scripts/title_source_census.py     # 2026-08-31
  shows=89 tracks=2015
    tags 1917
    unresolved 75
    sibling 21
    override 2
  ```

  The census prints only the sources it observes, and **neither `setlist` nor
  `setlist-gap` appears at all** — 1917 + 75 + 21 + 2 = 2015, so both are
  exactly 0. Exact count equality between a parsed
  description and a tape's file list is close to a measure-zero event on real
  tapes. The corpus sweep above says the same thing from the other side: 25,416
  of 57,098 blinding trials were pre-empted by this rung, because blinding
  manufactures the untagged condition that lets it be reached.

**The workaround, used by the Phase A tests that need a real gap:** add an
`overrides.exclude` entry for a file that is already untagged, breaking the
count coincidence without touching either anchor or the gap under test —

```python
write_artifact(sws.overrides, Overrides(exclude=["gd73-06-10d3t01.mp3"]))
# kept=5, items=6 -> the whole-tape rung declines, adopt_gap_titles is reachable
```

See `test_gap_fill_resolves_a_mixed_show` and
`test_adopted_titles_make_the_closer_tripwire_reachable` in
`packages/llama/tests/test_stage_gather.py`, both of which carry this reasoning
in their docstrings.

**Do not re-cut the fixture.** It is the canonical fixture for the whole repo;
changing its file or item count would invalidate measurements and pinned
expectations across `test_stage_gather.py`, `test_structure.py`, `test_junk.py`
and `test_setlist.py`. The count coincidence is a known trap to route around,
not a defect to fix.

---

## User-visible behaviour change shipped by Phase A

**A show whose every songish title came from the setlist now sets
`needs_review = True` where it previously set `False`**, with the review flag
`"low-confidence structure alignment"`.

The mechanism: `structure.TAUTOLOGICAL_TITLE_SOURCES` is
`{"setlist-gap", "setlist"}`, and `_songish_coverage` excludes both from its
denominator, because a track whose title *is* the canonical item's own text
cannot furnish independent evidence that `align()` matched it. On a show where
every songish track is `setlist`-sourced the independent-evidence set is empty,
coverage is the safe-direction `0.0`, and the low-confidence flag fires.
`gather.py`'s final track assembly tests the same constant, so those tracks also
report `matched = None` ("not measured") rather than `True`.

**This is the safe direction and it is honest** — such a show has literally zero
independent evidence its alignment is right, which is exactly what the flag
exists to say. It is nonetheless user-visible, so it is recorded here rather
than only in a test docstring.

**Scoping: 0 of 2,015 production tracks are affected.** Per the census quoted
under the fixture caveat above (`shows=89 tracks=2015`, 2026-08-31), the
`setlist` rung produces **0** tracks in the live library, so no existing show
flips. The change is reachable in tests (`test_gather_artist_item_does_not_block_title_resolution` in
`test_stage_gather.py` asserts it directly, with the reasoning in its
docstring) and on any future tape where that rung fires.

---

## What this does not measure

- **`setlistfm=None`.** Stated at the top and restated here because it is the
  single largest caveat: every canonical here is LMA-only, and the real
  canonicals for several of these shows are setlist.fm-won. **Every number in
  this document is a bound.**
- **Correlated failures are counted as independent.** 108 distinct
  genuinely-wrong adoptions include the same upstream parse defect reproduced
  across five recordings of gd1974-07-19 and two of gd1991-09-10. The count of
  distinct *causes* is materially smaller.
- **The blinded population is not the production population.** Blinding a
  well-tagged tape's tuning track manufactures a one-file gap that production
  reaches only when the tape is untagged at that spot. The `--natural` run is
  the honest exposure measure; the blind test is the honest *rate* measure, on a
  population chosen to be measurable rather than to be representative.
- **Adoptions outside the blinded window are unscored** (135 per-trial, 0.5%);
  they have no ground truth by construction.
- **Coverage is not evaluated here.** The known gap recorded in `CLAUDE.md` —
  coverage never inspects unmatched *items* — is untouched by this work.
- **The `flac` sweep is untriaged.** Its rate is a raw rate and no gate is drawn
  from it.

---

## Reproduction

From the worktree root, with its own venv (never a bare `pytest`/`python`):

```bash
./.venv/bin/python scripts/blind_tag_gapfill.py --selftest
./.venv/bin/python scripts/blind_tag_gapfill.py --progress 100        > gapfill-mp3.tsv
./.venv/bin/python scripts/blind_tag_gapfill.py --format flac         > gapfill-flac.tsv
./.venv/bin/python scripts/blind_tag_gapfill.py --natural             > natural-mp3.tsv
./.venv/bin/python scripts/title_source_census.py                     # the 2,015-track census
```

The harness reads `~/.llama/cache/md_*.json` and writes nothing anywhere. The
triage roll-up is the classification tables in this document applied to
`gapfill-mp3.tsv`; the tables enumerate the `genuinely-wrong` and
`tag-typo-adoption-superior` classes in full, and everything else is
`scorer-artifact`.

Suite at the time of writing: `./.venv/bin/pytest -q` → **1499 passed, 7
deselected**.
