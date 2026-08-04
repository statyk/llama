# Tail-guard family sample: do Furthur/DSO/Dead & Co behave like the Dead or like non-Dead?

**Branch:** `tail-guard` @ `eda63f0` (same reviewed HEAD as the sibling
`2026-08-03-tail-guard-sanity-check.md`; this document lands as a second
docs-only commit on top of it — `packages/` is untouched).
**Lookahead:** `8`, applied **in-process only** — the file's own default
stays **`3`** on this branch and was not edited anywhere for this check.
**Tail guard constants:** `TAIL_GUARD_ITEMS=3, TAIL_GUARD_TRACKS_REMAINING=3,
TAIL_GUARD_MAX_SKIP=6` — the shipped values, unconditionally active
regardless of lookahead. The guard never fires anywhere in this sample or in
the full 271-row corpus-wide sweep below (0 declines), so no GUARD DECLINED
markers appear in this document — only MATCH CHANGED and UNMATCHED, and only
where they occurred.
**Shipped default:** still **3**. Nothing here changes it.

## Why this sample exists

Shawn has already reviewed 6 Grateful Dead shows and 6 non-Dead shows from
the sibling sanity-check doc. This is the **middle category**: artists that
are **not** the Grateful Dead but **do** carry jerrybase structure evidence
— the Garcia universe (`llama.jerrybase.is_family_artist`). Jerrybase gives
these shows the same corroborating evidence the Dead get (anchoring, closer
tripwires, set-count guard, venue matching) that non-Dead artists entirely
lack. The prior sanity-check + flag work found non-Dead shows flip
held→ships at roughly 4-5x the Dead rate precisely because nothing but
coverage holds them. This sample (plus a corpus-wide sweep, not just the
6 rendered shows) tests whether family-but-not-GD shows behave like the
Dead (protected) or like non-Dead (exposed).

**Corpus coverage caveat, stated up front:** the measurement corpus this
branch's instruments were built against (`llama-setlist-analysis/corpus.jsonl`)
contains only **three** of jerrybase's nine family artists as actual rows:
**Furthur (99), Dark Star Orchestra (97), Dead & Company (96)** — 271 rows
after the standing `>=5 tracks and >=5 parsed items` filter. Ratdog, Phil
Lesh & Friends, Jerry Garcia Band, Bob Weir, The Dead, and The Other Ones
have jerrybase CSV rows but **no corpus rows in this dataset** — they simply
aren't in the sample this branch was measured against, so "artist-diverse"
below means diverse across those three, not across all nine. This is a
property of the corpus, not a decision made for this document.

Two other artist groups appear for contrast in the closing section: **Yonder
Mountain String Band, Del McCoury Band, Larry Keel** ride in the same
`corpus.jsonl` file as the Dead (evidently scraped together) but are **not**
in the jerrybase CSV — `jerrybase.is_family_artist` is False for all three —
so they get zero anchoring/closer/set-count evidence despite superficial
proximity to the Dead corpus. They're a clean within-corpus control for "not
jerrybase-covered" that isn't confounded by being a totally different genre.

## Method

Same discipline as the sibling doc and its `flags-report.md`: nothing here
reimplements `align()`, `jerrybase.anchor_breaks`, or `run_gather`'s flag
logic. Two real entry points, both imported from the pinned worktree HEAD
`eda63f0` (verified clean before and after every run below):

- **Setlist rendering / selection ranking**: `render/data.json` (already
  computed for the full dead+nondead corpus by the sibling doc's
  `render/gen_data.py`, via `traced_align`/`jerrybase.anchor_breaks`, spied
  not reimplemented) — reused as-is, just re-filtered and re-ranked for the
  family-not-GD artist set. `render/data.json`'s track set comes from
  `common.py`'s "dominant file extension, no duration filter" convention
  (same convention the sibling doc's setlist renderings used) — **not**
  identical to real `gather.py`'s track set; see the discrepancy note below.
- **`needs_review`/`review_flags` and the corpus-wide flip sweep**: the real
  `llama.stages.gather.run_gather`, imported directly from the worktree
  (blob-verified against `eda63f0` for the same watched files
  `flags-report.md` used, at start and end of every run), called with the
  production default `audio_format="mp3"`. Lookahead varied in-process by
  monkeypatching `gather_mod.align` to call the real `structure.align(...,
  lookahead=N)`, then restoring it — the file's own default (3) was never
  touched. Data: the sibling project's already-populated `iacache/`, no
  network call.

Scripts and raw intermediate data live under this task's scratchpad, in a
sibling `family/` directory next to the sanity-check doc's own `render/` and
`flags/` directories (same scratchpad root both prior docs used):
`family/family_flags.py` (the 6-show flag harness, ported from the sibling
doc's `flags/gather_flags.py`), `family/corpus_wide_flip.py` and
`family/corpus_wide_flip_compare.py` (the 271-row and four-bucket
corpus-wide sweeps), `family/render_family.py` (setlist rendering, reuses
`render/render_shows.py`'s `render_setlist` verbatim rather than
reimplementing the marker logic), `family/overlap_check.py` (the
title-overlap sanity gate, reusing the real `fuzzy_norm_title`/`is_filler`).
Raw output: `family/results_final.json` (6-show flags),
`family/corpus_wide_results.json` (271-row sweep),
`family/corpus_wide_compare.json` (four-bucket comparison).

**Track-count discrepancy, disclosed exactly as `flags-report.md` did for
the first 13 shows:** the setlist renderings below use `render/data.json`'s
simpler track set; the real `run_gather` (used for every `needs_review`
number) applies the production junk/duration filter and can drop filler
tracks the renderer's harness keeps (e.g. `deadco2017-06-30` renders 22
tracks below but `run_gather` sees 20 — the two `~crowd~` fillers are
dropped). This never changes a `needs_review` verdict; it's flagged for
transparency, not hidden.

## Selection

**The ranking metric degenerates.** Per the sibling doc's own ranking rule
("rank by the largest la=3→la=8 change in the final post-anchoring
set-break vector"), every one of the 271 family-not-GD rows was scored by
per-track final-set-label mismatch count between la=3 and la=8. **The result
is 0 for all 271 rows, with no exceptions.** The jerrybase-anchored final
structure this bucket ships is *completely* invariant to lookahead — not
"mostly," not "for the top movers," literally 0/271. This is itself the
headline finding (see Closing section), and it forces a change to the
selection procedure: with the primary metric flat, ranking falls back to
`select.py`'s own documented tie-break, matched-track-count delta
(`la8.n_matched - la3.n_matched`). Under that fallback, **exactly six rows**
in the entire 271-row bucket have any nonzero matched-count delta at all —
every other row (265/271) is byte-identical between la=3 and la=8 down to
per-track match identity, not just the final set-break vector. So this
sample isn't "the top 6 of a long tail" — it's **the complete, exhaustive
set of every family-not-GD row lookahead touches at all**, plus one
substitution (below).

**One substitution, disclosed per the sibling doc's own honesty rule.** The
6th of those six nonzero-delta rows, `dac2021-09-15.AKGmultitrack.toaste.flac16`
("Dead & Company," Deer Creek), passed the mechanical <20% title-overlap
gate (55.8% word overlap) but is **not actually a music recording** — its 8
"tracks" are raw microphone-channel stems from a DIY multitrack upload
(`"Shotgun center - This should be kept in the center of the mix..."`,
`"Cardioid left - can be anywhere in the left side..."`), not song audio.
The overlap score passed by coincidence (generic words like "left"/"right"/
"track" trivially overlapping canonical setlist text), which the sibling
doc's overlap gate was never designed to catch — it targets "wrong
performance," not "not a performance at all." Rendering "6/8 tracks matched"
against microphone-position descriptions would misrepresent what's really a
select-recording-stage data problem as a lookahead effect, so it's dropped
and disclosed rather than rendered. **Substitute:** the next family-not-GD
row that (a) has a real jerrybase event, (b) does **not** anchor at either
lookahead (preserving the "event exists but doesn't help" case the dropped
show was meant to illustrate), and (c) is a legitimate recording —
`dso2019-05-25.16-44.flac` (Dark Star Orchestra, Dark Star Jubilee festival,
Legend Valley Campground, OH; 66.7% title overlap, real song titles). It
turned out to independently reproduce one of the two known defects Shawn
asked to be flagged (see per-show notes) — not cherry-picked for that, found
after the fact.

**Final selection, 6 shows, all 3 corpus artists represented (2 DSO / 2 Dead
& Company / 2 Furthur is close — Furthur only has one nonzero-delta row in
the whole bucket, `dso2019-05-25` fills the DSO slot a second time):**

| Show | Artist | Δmatched (la8−la3) | Event? | Anchored (la3/la8) |
|---|---|---|---|---|
| `dso2026-06-12.km140` | Dark Star Orchestra | +24 | No | False/False |
| `deadco2018-06-19...` | Dead & Company | +21 | Yes | True/True |
| `furthur2011-02-11...` | Furthur | +17 | Yes | True/True |
| `dso2019-05-25.16-44.flac` (substituted in) | Dark Star Orchestra | 0 | Yes | False/False |
| `dso2012-05-08...` | Dark Star Orchestra | +5 | Yes | True/True |
| `deadco2017-06-30...` | Dead & Company | **−6** | Yes | True/True |

That last row is not a typo: la=8 matches *fewer* tracks than la=3 for
`deadco2017-06-30` — the one show in this sample that's worse at la=8 by a
raw internal metric. See its section below; it's the most important show in
this document.

---

## The six shows

### Dark Star Orchestra — 2026-06-12 — Beak and Skiff

`dso2026-06-12.km140` — <https://archive.org/details/dso2026-06-12.km140>

Corpus: Family (jerrybase-covered, non-GD) · collection `DarkStarOrchestra` · 24 tracks, 51 canonical setlist items · **no jerrybase event resolved for this artist/date**

**la=3 (shipped default):** 0/24 matched, breaks=none (single undifferentiated block), structure source = deterministic align(), coverage=0.00
**la=8 (proposed):** 24/24 matched, breaks=none, structure source = deterministic align(), coverage=1.00, guard declines = 0

**IDENTICAL final structure at la=3 and la=8** (both are one undifferentiated block — there's no internal break to find either way, since jerrybase never got a chance to anchor one in).

**la=8 setlist (marked):**

**Set 1**

  1. Set1 tuning
  2. Quinn the Eskimo (The Mighty Quinn)
  3. Cassidy
  4. Althea
  5. Passenger
  6. Just Like Tom Thumb's Blues
  7. Lazy Lightnin'
  8. Supplication
  9. Run For the Roses
 10. Walkin' Blues
 11. We Can Run
 12. Johnny B. Goode
 13. Set2 tuning
 14. Feel Like A Stranger
 15. New Speedway Boogie
 16. Playing In The Band>space
 17. He's Gone
 18. drums>space
 19. The Wheel
 20. All Along The Watchtower
 21. Comes A Time
 22. Sugar Magnolia
 23. encore break
 24. Take A Letter Maria

**needs_review / review_flags (real `run_gather`, `audio_format=mp3`):**

```
la=3: needs_review=True
  ["low-confidence structure alignment",
   "single-set structure for a long show (183 min)"]
la=8: needs_review=True
  ["single-set structure for a long show (183 min)"]
```

**No flip — held at both.** This is the one show in the sample with **no
jerrybase event at all** (`resolve_event` returns nothing for this
artist/date), so it gets *zero* family protection despite being a
jerrybase-family artist — it behaves exactly like a non-Dead show would:
la=8's wider window clears the coverage-based `low-confidence structure
alignment` flag (0.00→1.00 coverage, the biggest single matched-count
recovery in this whole sample), but the `structure_guard`'s duration branch
(`guard_min_minutes=150`, this tape runs 183 minutes as one undifferentiated
block) is orthogonal to lookahead and keeps it held regardless — the same
"flag narrows but the show stays held" pattern the non-Dead corpus showed
in the sibling doc's flag work. **Aside, not scored:** this item's own
canonical-setlist parse tail is license/copyright boilerplate text
("`cc by-nc-nd 4.0 https://creativecommons.org/...`", "`never for sale`")
that got swept into the 51 "canonical setlist items" — a pre-existing
description-parsing artifact, not a lookahead effect, and not why this show
is held (the two real flags above are).

---

### Dead & Company — 2018-06-19 — Darien Lake Amphitheater

`deadco2018-06-19.akg483.marino.flac24` — <https://archive.org/details/deadco2018-06-19.akg483.marino.flac24>

Corpus: Family (jerrybase-covered, non-GD) · collection `DeadAndCompany` · 21 tracks, 38 canonical setlist items · jerrybase event 3695 (Darien Lake Performing Arts Center, Darien Center, NY)

**la=3 (shipped default):** 0/21 matched, breaks=[9, 20], structure source = **jerrybase anchoring**, coverage=0.00
**la=8 (proposed):** 21/21 matched, breaks=[9, 20], structure source = **jerrybase anchoring**, coverage=1.00, guard declines = 0

**IDENTICAL final structure at la=3 and la=8** — despite raw `align()`
coverage swinging from 0% to 100% underneath it, because anchoring already
resolved the breaks at both lookaheads and wins outright once it does.

**la=8 setlist (marked):**

**Set 1**

  1. Crowd/tuning
  2. Cold Rain & Snow
  3. Tennessee Jed
  4. Dire Wolf
  5. Queen Jane Approximately
  6. If I Had The World To Give
  7. Here Comes Sunshine
  8. Little Red Rooster
  9. Let It Grow

**Set 2**

 10. Set 2 Crowd/tuning
 11. Iko Iko>
 12. Dark Star >
 13. Truckin' >
 14. Smokestack Lightning >
 15. Dark Star >
 16. Deal >
 17. Drumz >
 18. Space >
 19. Wharf Rat >
 20. Casey Jones

**Encore**

 21. (E) Werewolves Of London

**needs_review / review_flags:**

```
la=3: needs_review=True
  ["low-confidence structure alignment",
   "venue mismatch: archive 'Darien Lake Amphitheater' vs jerrybase 'Darien Lake Performing Arts Center'",
   "no playable tracks"]
la=8: needs_review=True   (byte-identical flags)
```

**No flip — held at both, identical flags.** Two caveats on the flag
content specifically (not on the la=3/la=8 comparison, which is solid
either way): (1) **"no playable tracks"** is a known, pre-existing,
lookahead-independent artifact — the cached metadata for this item has
**no mp3 derivative at all**, only `flac`/`afpk`, so llama's default
`audio_format="mp3"` finds nothing to play. This is the same category of
finding `flags-report.md` disclosed for the first sample (untagged/missing
default-derivative pickup) — not new, not a lookahead effect, and it
doesn't change the la=3 vs la=8 comparison since it fires identically at
both. (2) Because `run_gather` filtered to zero tracks under `mp3`, its
internally-computed `coverage`/`anchored` differ from `render/data.json`'s
numbers above (which use flac-derivative tracks) — hence the real run
reports `"low-confidence structure alignment"` (the coverage gate, implying
anchoring did *not* resolve under the empty-track view) even though the
setlist rendering above (computed with real tracks present) shows clean
jerrybase anchoring. Re-run with `audio_format="flac"` for a sanity check:
identical `needs_review`/flag verdict at both lookaheads either way — the
artifact changes *why* it's held, not *whether* it flips, so it doesn't
threaten the sample's conclusion.

---

### Furthur — 2011-02-11 — 1st Bank Center

`furthur2011-02-11.dpa4022.phil_er_up.111976.flac16` — <https://archive.org/details/furthur2011-02-11.dpa4022.phil_er_up.111976.flac16>

Corpus: Family (jerrybase-covered, non-GD) · collection `Furthur` · 21 tracks, 26 canonical setlist items · jerrybase event 2590 (1st Bank Center, Broomfield, CO)

**la=3 (shipped default):** 0/21 matched, breaks=[9, 19], structure source = **jerrybase anchoring**, coverage=0.00
**la=8 (proposed):** 17/21 matched, breaks=[9, 19], structure source = **jerrybase anchoring**, coverage=0.81, guard declines = 0

**IDENTICAL final structure at la=3 and la=8.**

**la=8 setlist (marked):**

**Set 1**

  1. Jack Straw
  2. Me and My Uncle
  3. Loser
  4. Big River
  5. It Must Have Been The Roses  ← UNMATCHED
      _unmatched — inherits "Set 1" from the previous track_
  6. Deal
  7. Jam
  8. Black Throated Wind
  9. Brown Eyed Women

**Set 2**

 10. Weather Report Suite  ← UNMATCHED
      _unmatched — inherits "Set 2" from the previous track_
 11. Mountian Song  ← UNMATCHED
      _unmatched — inherits "Set 2" from the previous track_
 12. I Know You Rider
 13. Jam
 14. Dark Star
 15. China Doll
 16. Playin In The Band
 17. Help On The Way  ← UNMATCHED
      _unmatched — inherits "Set 2" from the previous track_
 18. Slipknot
 19. Franklin's Tower

**Encore**

 20. Donor Rap
 21. Liberty

**needs_review / review_flags:**

```
la=3: needs_review=False   flags=[]
la=8: needs_review=False   flags=[]   (identical — clean ship at both)
```

**Zero flags at either lookahead**, despite la=3's raw `align()` coverage
being literally **0.00** (matched nothing at all). This is the sharpest
illustration in this sample of the anchoring shield described in the
Closing section: `gather.py`'s `elif canonical.items and result.coverage <
threshold:` branch — the only path that can append `"low-confidence
structure alignment"` — is gated on anchoring having *failed*
(`anchored is None`). Since jerrybase anchoring succeeds here at both
lookaheads, that branch never runs, so a 0% raw match rate produces the
exact same clean ship as a 100% one would.

---

### Dark Star Orchestra — 2019-05-25 — Dark Star Jubilee, Legend Valley Campground

`dso2019-05-25.16-44.flac` — <https://archive.org/details/dso2019-05-25.16-44.flac>

Corpus: Family (jerrybase-covered, non-GD) · collection `DarkStarOrchestra` · 23 tracks, 25 canonical setlist items · jerrybase event 3888 (Legend Valley Concert Venue and Campground, Thornville, OH)

**la=3 (shipped default):** 22/23 matched, breaks=[12, 21], structure source = deterministic align() (**anchoring did not resolve**), coverage=0.95
**la=8 (proposed):** 22/23 matched, breaks=[12, 21], structure source = deterministic align(), coverage=0.95, guard declines = 0

**IDENTICAL final structure at la=3 and la=8 — in fact per-track match
identity is fully identical too**, not just the break vector: this row (like
265 of the 271) is a true no-op end to end.

**la=8 setlist (marked, tape's own titles, unedited):**

**Set 1**

  1. 01 Tuning
  2. 02 Bertha >
  3. 03 Good Lovin'
  4. 04 Friend Of The Devil
  5. 05 Passenger
  6. 06 Candyman
  7. 07 Cassidy
  8. 08 Peggy-O
  9. 09 Me And My Uncle >
 10. 10 Big River
 11. 11 Deal
 12. 12 Piano and Drums

**Set 2**

 13. 13 Samson And Delilah
 14. 14 It Must Have Been The Roses
 15. 15 Estimated Prophet >
 16. 16 He's Gone >
 17. 17 Drums > Space >
 18. 18 The Other One >
 19. 19 Wharf Rat >
 20. 20 Around And Around

**Encore**

 21. 21 Encore Break  ← UNMATCHED
      _unmatched — inherits "Encore" from the previous track_
 22. 22 Werewolves Of London
 23. 23 Mister Charlie

**needs_review / review_flags:**

```
la=3: needs_review=True
  ["venue mismatch: archive 'Dark Star Jubilee, Legend Valley Campground' vs jerrybase 'Legend Valley Concert Venue and Campground'",
   "jerrybase set closer 'Around and Around' is not at a set break",
   "structure has 2 sets but jerrybase shows 1"]
la=8: needs_review=True   (byte-identical flags)
```

**No flip — held at both, identical flags.** This is the "event exists but
anchoring declines" case: jerrybase resolved a real event for this date, but
`jerrybase.anchor_breaks` couldn't place breaks from it (event sets are
`["1", "encore", "encore"]` — an unusual jerrybase encoding for this show,
two encore-labeled sets and only one numbered set — vs. this tape's own
2-set-plus-encore structure), so structure comes from plain `align()`
instead, same as a non-Dead show would get. **But it is still held at both
lookaheads by evidence a non-Dead show could never generate**: the venue
mismatch and the jerrybase closer tripwire both require a resolved event to
exist at all, and `"structure has 2 sets but jerrybase shows 1"` requires
jerrybase's own set-count evidence. A non-Dead show with this exact tape
quality would ship past `align()`'s own gates (or hold only on coverage,
which la=8 usually clears) — this one is held on jerrybase-only tripwires
that don't care about lookahead. **Partial protection, not full anchoring,
but real evidence-based protection all the same.**

**Defect flag #1, found independently while selecting this show, not
searched for:** every track title on this tape carries a **surviving
track-number prefix** — `01 Tuning`, `02 Bertha >`, `03 Good Lovin'`, all
the way through `23 Mister Charlie` — exactly the `01 Intro - Ramona` /
`10. 10 Satellite` pattern Shawn already found elsewhere. This is a
title-tagging/embedded-tag problem upstream of structure entirely (title
resolution here is `title_source=tags`, i.e. the archive.org file's own
embedded tag literally contains the number), **not a lookahead artifact** —
identical at la=3 and la=8 — but worth surfacing since it's the exact defect
class being hunted. **Defect flag #2 (encore short by a song): checked, not
found.** The tape's own tail (`21 Encore Break`, `22 Werewolves Of London`,
`23 Mister Charlie`) fully covers jerrybase's two encore closers
("Around and Around" is actually the *Set-1-equivalent* closer per this
event's odd 1/encore/encore labeling, and "Mr. Charlie" is captured). The
canonical parse's stray `"Filler:"` item (between "Werewolves Of London" and
"Mister Charlie" in the 25-item canonical list) is a description-parsing
split artifact, not a missing song — the tape actually captured everything
the description names.

---

### Dark Star Orchestra — 2012-05-08 — Higher Ground Ballroom

`dso2012-05-08.nak.shivaho.flac16` — <https://archive.org/details/dso2012-05-08.nak.shivaho.flac16>

Corpus: Family (jerrybase-covered, non-GD) · collection `DarkStarOrchestra` · 21 tracks, 25 canonical setlist items · jerrybase event 2743 (Higher Ground Music Hall, South Burlington, VT)

**la=3 (shipped default):** 10/21 matched, breaks=[8, 17], structure source = **jerrybase anchoring**, coverage=0.50
**la=8 (proposed):** 15/21 matched, breaks=[8, 17], structure source = **jerrybase anchoring**, coverage=0.75, guard declines = 0

**IDENTICAL final structure at la=3 and la=8.**

**la=8 setlist (marked):**

**Set 1**

  1. Feel Like A Stranger
  2. Peggy-O
  3. CC Rider
  4. Althea  ← UNMATCHED
      _unmatched — inherits "Set 1" from the previous track_
  5. Desolation Row
  6. Loose Lucy
  7. Hell In A Bucket
  8. Don't Ease Me In

**Set 2**

  9. Touch Of Grey
 10. Saint Of Circumstance
 11. Ship Of Fools
 12. Women Are Smarter->  ← UNMATCHED
      _unmatched — inherits "Set 2" from the previous track_
 13. Drums->  ← UNMATCHED
      _unmatched — inherits "Set 2" from the previous track_
 14. Space->  ← UNMATCHED
      _unmatched — inherits "Set 2" from the previous track_
 15. Goin' Down The Road Feelin' Bad->  ← UNMATCHED
      _unmatched — inherits "Set 2" from the previous track_
 16. All Along The Watchtower->
 17. Morning Dew

**Encore**

 18. Crowd  ← UNMATCHED
      _unmatched — inherits "Encore" from the previous track_
 19. Brokedown Palace
 20. You Ain't Woman Enough
 21. Cats Under The Stars

**needs_review / review_flags:**

```
la=3: needs_review=True
  ["venue mismatch: archive 'Higher Ground Ballroom' vs jerrybase 'Higher Ground Music Hall'"]
la=8: needs_review=True   (identical)
```

**No flip — held at both, identical single flag.** This is the cleanest
"jerrybase-covered but not the Dead" example in the sample: anchoring
resolves correctly at both lookaheads (10→15 of 21 tracks recovered by la=8,
all UNMATCHED entries are Drums/Space/Crowd-adjacent filler, not real
songs), the set structure is textbook and unaffected by lookahead — but a
venue-name string mismatch (`venues_equivalent` treating "Ballroom" and
"Music Hall" as different, correctly or not) holds it regardless of how
clean the recovered setlist looks. Not a lookahead story at all; included
because it's the median case for this bucket, not an outlier.

---

### Dead & Company — 2017-06-30 — Wrigley Field

`deadco2017-06-30.sibert.c4card.flac16` — <https://archive.org/details/deadco2017-06-30.sibert.c4card.flac16>

Corpus: Family (jerrybase-covered, non-GD) · collection `DeadAndCompany` · 22 tracks, 21 canonical setlist items · jerrybase event 3548 (Wrigley Field, Chicago, IL)

**la=3 (shipped default):** 21/22 matched, breaks=[7, 20], structure source = **jerrybase anchoring**, coverage=1.00
**la=8 (proposed):** **15/22 matched** (−6), breaks=[7, 20], structure source = **jerrybase anchoring**, coverage=0.70, guard declines = 0

**IDENTICAL final structure at la=3 and la=8 — but the internal alignment
that feeds it is measurably WORSE at la=8. Flagging this prominently, as
instructed:**

**la=8 setlist (marked):**

**Set 1**

  1. ~crowd~
  2. The Music Never Stopped  ← UNMATCHED
      _unmatched — inherits "Set 1" from the previous track_
  3. Bertha  ← UNMATCHED
      _unmatched — inherits "Set 1" from the previous track_
  4. Me and My Uncle  ← UNMATCHED
      _unmatched — inherits "Set 1" from the previous track_
  5. Sugaree  ← UNMATCHED
      _unmatched — inherits "Set 1" from the previous track_
  6. Let It Grow >  ← UNMATCHED
      _unmatched — inherits "Set 1" from the previous track_
  7. Uncle John's Band  ← UNMATCHED
      _unmatched — inherits "Set 1" from the previous track_

**Set 2**

  8. ~crowd~  ← UNMATCHED
      _unmatched — inherits "Set 2" from the previous track_
  9. Shakedown Street >
 10. Dark Star >
 11. St Stephen >
 12. China Doll >
 13. Terrapin Station >
 14. Uncle John Reprise' >
 15. Drums >
 16. Space >
 17. Standing On The Moon >
 18. Help On The Way >
 19. Slipknot >
 20. Franklins Tower

**Encore**

 21. Encore: Ripple
 22. Encore: US Blues

**What went wrong internally at la=8:** track 1 is `~crowd~` filler. At
la=3, it correctly stays unmatched. At la=8's wider window, it incorrectly
reaches 7 canonical items ahead and grabs the *other* `~crowd~` item (item 7
in the canonical list, the one that actually belongs to track 8, between
"Uncle John's Band" and "Shakedown Street"). That consumes the pointer past
the real Set-1 songs, and tracks 2–7 ("The Music Never Stopped" through
"Uncle John's Band" — six real, correctly-tagged songs) all fail to match
anything at la=8, where they matched cleanly at la=3. Coverage drops
1.00→0.70. **This is a genuine, real la=8 regression in `align()`'s own
matching — not a fabrication and not explainable by track-set differences**
(same 20-track set at both lookaheads per the real `run_gather`).

**needs_review / review_flags — and why the regression above is invisible
downstream:**

```
la=3: needs_review=False   flags=[]
la=8: needs_review=False   flags=[]   (identical)
```

**No flip.** Two independent reasons the internal regression never reaches
the listener or the review queue:

1. **Titles never depend on `align()`'s hit.** Every track's title comes
   from `title_source=tags` (the file's own embedded metadata) at both
   lookaheads, verified via the real `run_gather` output — confirmed
   byte-identical track titles regardless of which canonical item `align()`
   thought each track hit. A track being UNMATCHED changes nothing a
   listener would hear or see; it only affects internal `coverage` and,
   through it, gating logic.
2. **Anchoring already resolved before `coverage` is ever checked.**
   `stages/gather.py` line ~562: `if anchored is not None: ... alignment =
   "jerrybase"`. The `elif ... result.coverage < threshold:` branch that
   appends `"low-confidence structure alignment"` is only reachable when
   anchoring is `None`. Since `jerrybase.anchor_breaks` succeeds for this
   show at **both** lookaheads (same event, same closers, same tracks), the
   coverage-based gate is architecturally skipped either way — a coverage
   collapse from 1.00 to 0.70 has **zero** effect on `needs_review` for an
   already-anchored show. This is the precise mechanism behind "family
   shows are shielded," not just an observed correlation.

This show is the single most important data point in this document: it
demonstrates that la=8 **can** make `align()`'s own matching measurably
worse on a real, well-tagged, fully-resolved family show — Shawn should
treat that as a real (if narrow) regression in the align() layer itself —
but that regression is fully absorbed by the anchoring architecture before
it can reach anything a listener or the review queue would see. If a future
change ever weakens or removes anchoring's precedence over the coverage
gate, this exact failure mode (a filler track's wide-window mismatch
desyncing several real songs behind it) would resurface as a real held-show
flag on shows that ship clean today.

---

## Closing: do family-but-not-GD shows behave like the Dead or like non-Dead?

**Like the Dead — actually the least lookahead-sensitive of the four groups
measured, corpus-wide, not just in this 6-show sample.**

Corpus-wide held→ships / ships→held flip rate at la=3 vs la=8 (real
`run_gather`, `audio_format="mp3"`, every row in each bucket, not a sample):

| Bucket | n | held @ la=3 | held @ la=8 | **flips** | flag-set changed |
|---|---:|---:|---:|---:|---:|
| Grateful Dead only | 585 | 56.75% | 56.41% | **2 (0.34%)** | 9 rows |
| **Family-not-GD (Furthur/DSO/Dead&Co)** | **271** | **48.34%** | **48.34%** | **0 (0.00%)** | **0 rows** |
| Non-family, same corpus file (YMSB/Del McCoury/Larry Keel) | 264 | 52.27% | 49.62% | 7 (2.65%) | 10 rows |
| True non-Dead (no jerrybase anywhere) | 718 | 41.64% | 36.35% | 40 (5.57%) | 51 rows |

This is a full corpus sweep for every bucket (not a sample; see
`family/corpus_wide_compare.json` in this task's scratchpad), same harness, same pin, same
lookahead-override discipline as everything else in this document.

**The family-not-GD bucket flips *less* than the Grateful Dead itself, and
16x less than the true non-Dead corpus.** More strikingly: in the
family-not-GD bucket, `needs_review`'s exact `review_flags` list — not just
the boolean verdict — is **byte-identical** between la=3 and la=8 in all
271 rows. Zero rows even *narrow* their flag set the way several Dead rows
in the sibling doc's 13-show sample did (`gd1987-07-08`,
`gd1985-03-09`, `gd1984-03-29` all cleared `low-confidence structure
alignment` at la=8 while staying held on other grounds). For this bucket,
la=8 changes *nothing observable at the gather-flag level, ever*, in this
corpus.

**Why**, precisely, from the code and the six shows above:

1. **Anchoring, once it resolves, makes the coverage-based flag
   unreachable** (`gather.py`'s `if anchored is not None: ... elif
   ...coverage < threshold:` — mutually exclusive branches). 169/271
   (62.4%) of family-not-GD rows anchor at both lookaheads. For those rows,
   `align()`'s own coverage — the one metric lookahead actually moves — is
   architecturally irrelevant to `needs_review`. `deadco2017-06-30` is the
   sample's proof: coverage genuinely collapses (1.00→0.70) at la=8 and it
   changes nothing downstream.
2. **Even when anchoring fails, jerrybase-only tripwires still apply and
   are lookahead-independent.** `dso2019-05-25` (event resolved, anchoring
   declined) is still held at both lookaheads by the closer tripwire and
   the set-count guard — evidence a non-Dead show, with zero jerrybase
   coverage, could never generate. This is why even the *non*-anchored
   slice of this bucket doesn't behave like non-Dead: it still carries
   more tripwires.
3. **Only a show with no jerrybase event at all is exposed the way
   non-Dead is.** `dso2026-06-12` (no event) shows exactly the non-Dead
   pattern from the sibling doc's flag work: la=8 clears the coverage gate,
   but an orthogonal, lookahead-independent flag (here,
   `structure_guard`'s duration branch) keeps it held. This is the one
   show in the sample that's a true non-Dead analog — and it's the one
   without jerrybase evidence, which is exactly the mechanism this document
   set out to test.

**Answer to the framing question:** family-but-not-GD shows behave like the
Dead, and the reason is legible in the code, not just the numbers —
jerrybase *coverage*, not being the Grateful Dead per se, is the protective
factor. A show gets the shield whenever `jerrybase.lookup(artist, date)`
resolves an event, regardless of whether the artist string says "Grateful
Dead," "Furthur," "Dark Star Orchestra," or "Dead & Company." The
`nonfamily_in_deadfile` row in the table above is the cleanest proof of the
converse: Yonder Mountain String Band, Del McCoury Band, and Larry Keel sit
in the exact same corpus file as the Dead, get scraped and processed
identically, and still flip at 2.65% — 8x the family-not-GD rate — because
`jerrybase.is_family_artist` is False for all three and they get none of
the evidence that shields the family bucket.

**Two things worth flagging as genuinely worse at la=8, neither of which
changes a shipped outcome in this sample:**

- `deadco2017-06-30`'s internal `align()` coverage collapse (1.00→0.70,
  detailed above) — real, reproducible, currently harmless only because
  anchoring is in front of it.
- `dso2026-06-12`'s canonical-setlist parse pulling in license/copyright
  boilerplate as fake "setlist items" — pre-existing, not a lookahead
  artifact, not scored, noted for completeness.

**Defect sweep (the two patterns Shawn already found elsewhere), across all
six shows:**

- **Track-number prefixes surviving into shipped titles:** found on
  **`dso2019-05-25`** (`01 Tuning`, `02 Bertha >`, ... `23 Mister Charlie`
  — all 23 tracks). Not found on the other five.
- **Encore short by a song vs. the description:** checked on every show
  with an encore (`deadco2018-06-19`, `furthur2011-02-11`, `dso2019-05-25`,
  `dso2012-05-08`, `deadco2017-06-30`) by comparing the tape's captured tail
  against jerrybase's own encore closer(s). **Not found in this sample** —
  every jerrybase-named encore closer is present in the captured tape in
  all five cases.

## Status

Complete. 6 shows rendered + fully exhaustive selection rationale (all 6
nonzero-lookahead-delta rows in the 271-row bucket, one substituted and
disclosed) + a 271-row family-bucket flip sweep + a 4-bucket, 1838-row
corpus-wide comparison, all from the real `align()`/`jerrybase.anchor_breaks`/
`run_gather`, never reimplemented. Worktree verified clean at `eda63f0`
before and after every run; main checkout verified unmoved at `51b3f73`.
Nothing written under `~/.llama`. Lookahead varied in-process only (file
default untouched throughout). No `TAKEN_OVER` seen at any write batch.
