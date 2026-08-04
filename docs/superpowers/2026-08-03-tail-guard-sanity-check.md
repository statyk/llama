# Tail-guard sanity check: does la=8 look like real Grateful Dead shows?

> **Update (2026-08-04):** the bump this check evidenced landed in
> `c2740d2`, after this document was written — `align()`'s shipped default
> is now **`8`**, not 3. Everything below was measured one to two commits
> **before** that bump, while `3` was still the shipped default; the
> comparisons here are the evidence that justified moving it. Every "la=3
> (shipped default)" label and the "stays 3" line below describe the
> default **at the time of this review**, not the branch's current
> default — left as measured, since the numbers themselves are unchanged
> and correct. See `2026-08-04-tail-guard-family-sample.md` for the same
> note.

**Branch:** `tail-guard` @ `16eac9b` (this document itself lands as a
docs-only commit on top of that reviewed HEAD — `packages/` is untouched).
**Lookahead:** `8`, applied **in-process only** (`lookahead=8` passed
directly to `align()`/`traced_align()`, exactly as the branch's own
measurement instruments do it) — the file's own default was **`3`** at
the time of this check and was not edited anywhere for it (the branch now
ships `8`, as of `c2740d2` — see the update note above).
**Tail guard constants:** `TAIL_GUARD_ITEMS=3, TAIL_GUARD_TRACKS_REMAINING=3,
TAIL_GUARD_MAX_SKIP=6` — the shipped values, unconditionally active in
`structure.py` regardless of lookahead (only lookahead is varied below; the
guard is not toggled off except in the two explicit "if the guard did NOT
exist" illustrations for the mandatory shows, which say so explicitly).
**Source:** every number below comes from the REAL `llama.structure.align()`
and REAL `llama.jerrybase.anchor_breaks()`, run in-process against a pinned
snapshot of `structure.py` at commit `ca8e603` (`git diff ca8e603..16eac9b --
packages/llama/src/llama/structure.py` touches only comments/docstrings —
verified line-by-line before this check ran; the constants and
`_tail_guard_declines` body are byte-identical, so this snapshot is
behaviorally the same code as the worktree's actual `16eac9b` HEAD). Nothing
here reimplements `align()`'s cascade or the guard predicate — the harness
spies on the real functions (the sibling `llama-setlist-analysis` project's
`tailguard2b/common.py:traced_align`), the same discipline this branch's own
measurement instruments use.

## How to read this

For every show below you get: the identifier and its archive.org page, the
**final setlist as the pipeline would actually ship it at la=8** (real
`align()`, then real `jerrybase.anchor_breaks` where a jerrybase event
exists — anchoring wins whenever it resolves, same as production), grouped
by set with track numbers and titles **exactly as tagged on the tape** (not
normalized). Three kinds of track get an inline marker, and *only* these
three — everything else is unmarked because it didn't change:

- **GUARD DECLINED** — the guard turned down a candidate match for this
  track. Only the two mandatory shows below have any of these.
- **MATCH CHANGED** — the track matched a setlist item at *both* la=3 and
  la=8, but a *different* item.
- **UNMATCHED** — the track has no matched setlist item at la=8, so it
  simply inherits the previous track's set label. These are the ones most
  likely to look wrong on a visual scan, because the label is inherited
  rather than evidenced.

Every show also states its la=3 (the shipped default at the time of this
review) baseline — matched count, break positions, and whether jerrybase
anchoring or plain `align()` produced the structure — so you can judge la=8
as a change from what shipped at the time of this review, not in isolation.
Where la=3 already had real structure (the two mandatory shows and the
control), the full la=3 setlist is included for direct comparison, not
just a summary line.

**The question this document is asking you:** for each show, does the la=8
set structure look like something the band actually played, and — where
something is marked as different from la=3 — is that change an improvement
or a regression? You are the check nothing else in this branch's review can
perform; every prior gate was structural (does the break vector change, does
match identity hold), never "does this read as a real show."

## Selection

**Dead, 7 shows** (jerrybase/GD-family corpus is much broader than the band
itself — Furthur, Dark Star Orchestra, Yonder Mountain String Band, etc. are
in the same corpus file; every discretionary pick below was restricted to
`artist == "Grateful Dead"` specifically, since that's where your expertise
is sharpest):

1. **`gd85-04-06` and `gd91-03-28` (mandatory).** The only two shows
   corpus-wide (1120 Dead rows, 23,275 tracks) where the guard fires at
   la=8 — 2 declined tracks total, one per show. These are the entire
   reason the guard exists.
2. **Four more, ranked by the largest la=3→la=8 change in the final
   post-anchoring set-break vector** (per-track set-label mismatches
   between the two lookaheads), restricted to real Grateful Dead shows.
   **Two higher-ranked candidates were dropped and are disclosed, not
   hidden:** `gd1984-04-24` (10 mismatches) and `gd1991-08-17` (6
   mismatches) both turned out to have a canonical setlist that does not
   correspond to the tape at all (word-overlap between the tape's own
   titles and the parsed canonical setlist under 20%, vs. 80-100% for every
   other selected show) — a pre-existing archive.org/corpus data-quality
   problem unrelated to lookahead or the guard. Rendering either would have
   looked like a glaring bug that isn't actually about this change, so they
   were replaced with the next-ranked, verified-sane candidates
   (`gd1984-03-29`, `gd1971-02-23`). One compilation disc
   (`gd1993-01-01...SongsofOurOwn`, venue "Various") was excluded from
   ranking entirely — it isn't a single performance.
3. **One control** (`gd1973-02-09`, Stanford): la=3 and la=8 produce an
   **identical** result — included so you can see the no-op case, not just
   confirming cases. Chosen for completeness (32/32 tracks matched, full
   jerrybase-anchored two-set-plus-encore structure; 100% tape/canonical
   title overlap) over the first no-op candidate tried
   (`gd1981-12-31`), whose tape and canonical titles include a run of songs
   ("The Boxer", "Tunisian New Year Song", "Do Right Woman", "Bye Bye
   Love"...) that don't read as a standard two-set Dead show and weren't
   worth chasing down further when a cleaner example was available.

**Non-Dead, 6 shows:** the guard fires **zero** times anywhere in the
non-Dead corpus (718 rows, 14,193 tracks) at la=8, so every one of these is
a pure lookahead-gain case with no guard involvement. Ranked the same way
(largest set-break-vector change), one per collection so this isn't six
shows from one artist: Radiators, Against Me!, Guster, Built to Spill, Los
Lobos, Josh Ritter.

---

## Dead — the two mandatory guard-fire shows

### Grateful Dead — 1985-04-06 — The Spectrum

`gd85-04-06.sbd.miller.13467.sbeok.shnf` — <https://archive.org/details/gd85-04-06.sbd.miller.13467.sbeok.shnf>

Collection `GratefulDead` · 19 tracks, 17 canonical setlist items · jerrybase event 4065 (Spectrum, Philadelphia, PA)

**la=3 (the default at the time of this review):** 16/19 matched, breaks=none, structure source = deterministic align()
**la=8 (proposed):** 16/19 matched, breaks=none, structure source = deterministic align(), guard declines = 2

**Guard-fire show (mandatory).** Track 10's own tape tag is “One More Saturday Night” — the same words as this show's real encore (the last canonical item, per the archive.org description's trailing `E: One More Saturday Night`). Without the guard, la=8's wider window lets that title leap 7 items ahead and claim the encore slot, which would exhaust the canonical list and mislabel every one of the 9 tracks after it (China Cat Sunflower through Not Fade Away) as “encore.” **With the guard, that candidate is declined** and the track falls back to unmatched, landing la=8 on the exact same final structure as la=3 (this tape never surfaces set breaks at either lookahead — the source description itself has no `Set 1`/`Set 2` labels, only a flat song list plus an encore marker, so `align()` puts everything in one undifferentiated block regardless). See the 'guard OFF' illustration below for what la=8 does to this show if the guard is removed.

**IDENTICAL final structure at la=3 and la=8**

**la=8 setlist (marked):**

**Set 1**

  1. Feel Like A Stranger
  2. They Love Each Other
  3. Minglewood Blues
  4. Dupree's Diamond Blues
  5. Mama Tried
  6. Big River
  7. Big Railroad Blues
  8. Looks Like Rain
  9. Don't Ease Me In
 10. One More Saturday Night  ← GUARD DECLINED
      _guard declined a match to item 17 “One More Saturday Night” (7 positions ahead of the pointer) — falls back to unmatched, inherits "Set 1" from the previous track_
 11. China Cat Sunflower  ← UNMATCHED
      _unmatched — inherits "Set 1" from the previous track_
 12. I Know You Rider
 13. Playing In The Band
 14. Uncle John's Band
 15. Drums
 16. Space  ← UNMATCHED
      _unmatched — inherits "Set 1" from the previous track_
 17. The Other One
 18. Throwing Stones
 19. Not Fade Away

**If the tail guard did NOT exist, la=8 on this same tape would instead produce this (breaks=[9]):**


**Set 1**

  1. Feel Like A Stranger
  2. They Love Each Other
  3. Minglewood Blues
  4. Dupree's Diamond Blues
  5. Mama Tried
  6. Big River
  7. Big Railroad Blues
  8. Looks Like Rain
  9. Don't Ease Me In

**Encore**

 10. One More Saturday Night  ← now WRONGLY matches item 17 “One More Saturday Night”, exhausting the canonical list
 11. China Cat Sunflower
 12. I Know You Rider
 13. Playing In The Band
 14. Uncle John's Band
 15. Drums
 16. Space
 17. The Other One
 18. Throwing Stones
 19. Not Fade Away

---

### Grateful Dead — 1991-03-28 — Nassau Veterans Memorial Coliseum

`gd91-03-28.fob-schoeps-mahoney-oneill.miller.28391.sbeok.shnf` — <https://archive.org/details/gd91-03-28.fob-schoeps-mahoney-oneill.miller.28391.sbeok.shnf>

Collection `GratefulDead` · 17 tracks, 15 canonical setlist items · jerrybase event 4874 (Nassau Veterans Memorial Coliseum, Uniondale, NY)

**la=3 (the default at the time of this review):** 14/17 matched, breaks=[9], structure source = deterministic align()
**la=8 (proposed):** 14/17 matched, breaks=[9], structure source = deterministic align(), guard declines = 2

**Guard-fire show (mandatory).** Track 8's own tape tag is “Terrapin Station”, positioned right after `Let It Grow` (the true Set 1 closer per the description: `Set 1 Bertha, Greatest Story Ever Told, Loser, Black Throated Wind, Ramble On Rose, Let It Grow`). The description's actual Terrapin Station is the encore, the very last item. la=8 without the guard reaches 8 items ahead, matches this track to the encore's Terrapin instead, and drags the rest of the tape (Victim Or The Crime through Good Lovin', the entire real Set 2) into “encore.” **With the guard, that candidate is declined**, track 8 stays unmatched (as it already was at la=3) and inherits Set 1, and la=8 lands on the exact same final structure as la=3: Set 1 through track 9, Set 2 from Victim Or The Crime on. That is the historically correct shape for this show.

**IDENTICAL final structure at la=3 and la=8**

**la=8 setlist (marked):**

**Set 1**

  1. Tuning  ← UNMATCHED
      _unmatched — inherits "Set 1" from the previous track_
  2. Bertha ->
  3. Greatest Story EverTold
  4. Loser
  5. Black Throated Wind
  6. Ramble On Rose
  7. Let It Grow
  8. Terrapin Station  ← GUARD DECLINED
      _guard declined a match to item 15 “Terrapin Station” (8 positions ahead of the pointer) — falls back to unmatched, inherits "Set 1" from the previous track_
  9. Tuning  ← UNMATCHED
      _unmatched — inherits "Set 1" from the previous track_

**Set 2**

 10. Victim Or The Crime ->
 11. Foolish Heart ->
 12. Man Smart (Woman Smarter) ->
 13. Drums ->
 14. Space ->  ← UNMATCHED
      _unmatched — inherits "Set 2" from the previous track_
 15. China Doll ->
 16. Goin' Down The Road Feeling Bad ->
 17. Good Lovin'

**If the tail guard did NOT exist, la=8 on this same tape would instead produce this (breaks=[7]):**


**Set 1**

  1. Tuning
  2. Bertha ->
  3. Greatest Story EverTold
  4. Loser
  5. Black Throated Wind
  6. Ramble On Rose
  7. Let It Grow

**Encore**

  8. Terrapin Station  ← now WRONGLY matches item 15 “Terrapin Station”, exhausting the canonical list
  9. Tuning
 10. Victim Or The Crime ->
 11. Foolish Heart ->
 12. Man Smart (Woman Smarter) ->
 13. Drums ->
 14. Space ->
 15. China Doll ->
 16. Goin' Down The Road Feeling Bad ->
 17. Good Lovin'

---

## Dead — largest la=3→la=8 set-break-vector change

### Grateful Dead — 1987-07-08 — Roanoke Civic Center

`gd1987-07-08.142149.s2.FOB-schoeps-cmc-mk4-ortf.gastwirt.miller.sirmick.flac1644` — <https://archive.org/details/gd1987-07-08.142149.s2.FOB-schoeps-cmc-mk4-ortf.gastwirt.miller.sirmick.flac1644>

Corpus: Dead · collection `GratefulDead` · 14 tracks, 20 canonical setlist items · jerrybase event 4370 (Roanoke Civic Center, Roanoke, VA)

**la=3 (the default at the time of this review) baseline:** 0/14 tracks matched, breaks=— none (single undifferentiated block), structure source = deterministic align()

**la=8 (proposed) result:** 11/14 tracks matched, breaks=[2, 13], structure source = deterministic align(), guard declines = 0

**Final setlist shipped at la=8:**

**Set 1**

  1. lead in  ← UNMATCHED
      _unmatched — inherits "Set 1" from the previous track_
  2. crowd  ← UNMATCHED
      _unmatched — inherits "Set 1" from the previous track_

**Set 2**

  3. Scarlet Begonias >
  4. Fire On The Mountain
  5. Estimated Prophet >
  6. He's Gone >
  7. Drums >
  8. Space >  ← UNMATCHED
      _unmatched — inherits "Set 2" from the previous track_
  9. Crazy Fingers >
 10. Truckin' >
 11. Comes A Time >
 12. Sugar Magnolia
 13. encore break~~  ← UNMATCHED
      _unmatched — inherits "Set 2" from the previous track_

**Encore**

 14. Black Muddy River

---

### Grateful Dead — 1985-03-09 — Berkeley Community Theater

`gd1985-03-09.165109.sbd.miller.flac1644` — <https://archive.org/details/gd1985-03-09.165109.sbd.miller.flac1644>

Corpus: Dead · collection `GratefulDead` · 13 tracks, 18 canonical setlist items · jerrybase event 4050 (Berkeley Community Theater, Berkeley, CA)

**la=3 (the default at the time of this review) baseline:** 0/13 tracks matched, breaks=— none (single undifferentiated block), structure source = deterministic align()

**la=8 (proposed) result:** 10/13 tracks matched, breaks=[3], structure source = deterministic align(), guard declines = 0

**Final setlist shipped at la=8:**

**Set 1**

  1. Tuning  ← UNMATCHED
      _unmatched — inherits "Set 1" from the previous track_
  2. Let It Grow
  3. Tuning  ← UNMATCHED
      _unmatched — inherits "Set 1" from the previous track_

**Set 2**

  4. China Cat Sunflower >
  5. Cumberland Blues
  6. I Need A Miracle >
  7. Eyes Of The World >
  8. Drums >
  9. Space >
 10. The Other One >
 11. The Wheel >
 12. Sugar Magnolia
 13. Encore Break  ← UNMATCHED
      _unmatched — inherits "Set 2" from the previous track_

---

### Grateful Dead — 1984-03-29 — Marin County Veterans Auditorium

`gd1984-03-29.148306.2nd.set.fob.akg.d330bt.senn421.hecht.miller.clugston.flac1648` — <https://archive.org/details/gd1984-03-29.148306.2nd.set.fob.akg.d330bt.senn421.hecht.miller.clugston.flac1648>

Corpus: Dead · collection `GratefulDead` · 10 tracks, 19 canonical setlist items · jerrybase event 3921 (Marin Veterans Memorial Auditorium, San Rafael, CA)

**la=3 (the default at the time of this review) baseline:** 0/10 tracks matched, breaks=— none (single undifferentiated block), structure source = deterministic align()

**la=8 (proposed) result:** 9/10 tracks matched, breaks=[1], structure source = deterministic align(), guard declines = 0

**Final setlist shipped at la=8:**

**Set 1**

  1. Crowd  ← UNMATCHED
      _unmatched — inherits "Set 1" from the previous track_

**Set 2**

  2. Shakedown Street
  3. Estimated Prophet >
  4. Eyes Of The World >
  5. Drums >
  6. Space >
  7. Spanish Jam >
  8. The Other One >
  9. Wharf Rat >
 10. Sugar Magnolia

---

### Grateful Dead — 1971-02-23 — Capitol Theater

`gd1971-02-23.151503.aud.partial.lamarre.vernon.sirmick.flac24` — <https://archive.org/details/gd1971-02-23.151503.aud.partial.lamarre.vernon.sirmick.flac24>

Corpus: Dead · collection `GratefulDead` · 13 tracks, 29 canonical setlist items · jerrybase event 1168 (Capitol Theater, Port Chester, NY)

**la=3 (the default at the time of this review) baseline:** 0/13 tracks matched, breaks=— none (single undifferentiated block), structure source = deterministic align()

**la=8 (proposed) result:** 12/13 tracks matched, breaks=[7], structure source = deterministic align(), guard declines = 0

**Final setlist shipped at la=8:**

**Set 1**

  1. Me And Bobby McGee
  2. Bertha
  3. Next Time You See Me
  4. Morning Dew
  5. Sugar Magnolia
  6. crowd/tuning  ← UNMATCHED
      _unmatched — inherits "Set 1" from the previous track_
  7. Casey Jones// (snippet)

**Set 2**

  8. Me And My Uncle
  9. Bird Song
 10. Truckin' >
 11. Drums >
 12. The Other One >
 13. Wharfrat//

---

## Dead — control (no-op case)

### Grateful Dead — 1973-02-09 — Roscoe Maples Pavilion - Stanford University

`gd1973-02-09.sbd.finney.10361.shnf` — <https://archive.org/details/gd1973-02-09.sbd.finney.10361.shnf>

Collection `GratefulDead` · 32 tracks, 34 canonical setlist items · jerrybase event 1668 (Roscoe Maples Pavilion, Stanford University, Palo Alto, CA)

**la=3 (the default at the time of this review):** 32/32 matched, breaks=[15, 31], structure source = jerrybase anchoring
**la=8 (proposed):** 32/32 matched, breaks=[15, 31], structure source = jerrybase anchoring, guard declines = 0

**IDENTICAL final structure at la=3 and la=8**

**la=8 setlist (marked):**

**Set 1**

  1. The Promised Land
  2. Row Jimmy
  3. Black Throated Wind
  4. Deal
  5. Me And My Uncle
  6. Stage Chatter
  7. Sugaree
  8. Looks Like Rain
  9. Loose Lucy
 10. Beer Barrel Polka
 11. Mexicali Blues
 12. Brown Eyed Women
 13. El Paso
 14. Here Comes Sunshine
 15. Playing In The Band

**Set 2**

 16. Wavy Gravy chatter
 17. China Cat Sunflower >
 18. I Know You Rider
 19. Jack Straw
 20. Dead battery
 21. They Love Each Other
 22. Truckin' >
 23. Eyes Of The World >
 24. China Doll
 25. Big River
 26. Ramble On Rose
 27. Box Of Rain
 28. Wave That Flag
 29. Sugar Magnolia
 30. Uncle John's Band
 31. Around And Around

**Encore**

 32. Casey Jones

---

## Non-Dead — largest la=3→la=8 set-break-vector change

### Radiators — 2008-06-22 — Varsity Theater

`rad2008-06-22.flac16` — <https://archive.org/details/rad2008-06-22.flac16>

Corpus: non-Dead · collection `Radiators` · 23 tracks, 38 canonical setlist items · no jerrybase event resolved for this artist/date

**la=3 (the default at the time of this review) baseline:** 5/23 tracks matched, breaks=— none (single undifferentiated block), structure source = deterministic align()

**la=8 (proposed) result:** 23/23 tracks matched, breaks=[11], structure source = deterministic align(), guard declines = 0

**Final setlist shipped at la=8:**

**Set 1**

  1. Todd Baker Intro,
  2. Boomerang
  3. This Wheel's On Fire
  4. I Walked With A Zombie
  5. You Can't Take It With You [medley]> Crazy Mixed Up World> Thrill On The Hill (Let's Go, Let's Go, Let's Go)> Land Of 1000 Dances> You Can't Take It With You
  6. Fools Go First
  7. No Face, No Name, No Number [tease]> Waiting For The Rain
  8. Rain
  9. Make Fire
 10. House Of Blue Lights>
 11. Nail Your Heart To Mine

**Set 2**

 12. Todd Baker Intro II
 13. Ooh La La
 14. Run Red Run
 15. Don't Pray For Me
 16. Memories Of Venus
 17. Lost Highway
 18. Spanish Moon
 19. Little Red Rooster
 20. Lucinda> The Magnificent Seven> American Woman [excerpt]> Cissy Strut
 21. Thank You (For letting Me Be My Self Again) [tease]> Jambalaya (On The Bayou)
 22. Jesus On The Mainline>
 23. Lost What They Had

---

### Against Me! — 2017-10-14 — Brooklyn Steel

`againstme2017-10-14.BrooklynSteel.Nitcomb.flac16-44.1` — <https://archive.org/details/againstme2017-10-14.BrooklynSteel.Nitcomb.flac16-44.1>

Corpus: non-Dead · collection `AgainstMe` · 30 tracks, 38 canonical setlist items · no jerrybase event resolved for this artist/date

**la=3 (the default at the time of this review) baseline:** 10/30 tracks matched, breaks=— none (single undifferentiated block), structure source = deterministic align()

**la=8 (proposed) result:** 28/30 tracks matched, breaks=[24], structure source = deterministic align(), guard declines = 0

**Final setlist shipped at la=8:**

**Set 1**

  1. True Trans Soul Rebel
  2. I Was A Teenage Anarchist
  3. ProVision L-3
  4. From Her Lips To God’s Ears (The Energizer)
  5. Miami
  6. New Wave
  7. Up The Cuts
  8. Laura Jane Talk
  9. Jordan’s First Choice
 10. Walking Is Still Honest
 11. Haunting, Haunted, Haunts  ← UNMATCHED
      _unmatched — inherits "Set 1" from the previous track_
 12. Delicate, Petite & Other Things I’ll Never Be
 13. Runnin’ Down A Dream *
 14. Unconditional Love
 15. Those Anarcho Punks Are Mysterious…
 16. 333
 17. Dead Friend
 18. Transgender Dysphoria Blues
 19. The Ocean
 20. Bamboo Bones
 21. Reinventing Axl Rose
 22. Black Me Out
 23. Thrash Unreal
 24. Crowd Ambience

**Encore**

 25. The Best Ever Death Metal Band In Denton **
 26. Two Coffins
 27. Pints Of Guiness Make You Strong
 28. Baby, I’m An Anarchist
 29. Sink, Florida, Sink  ← UNMATCHED
      _unmatched — inherits "Encore" from the previous track_
 30. We Laugh At Danger (And Break All The Rules)

---

### Guster — 2018-01-13 — House of Blues

`gus2018-01-13` — <https://archive.org/details/gus2018-01-13>

Corpus: non-Dead · collection `Guster` · 26 tracks, 32 canonical setlist items · no jerrybase event resolved for this artist/date

**la=3 (the default at the time of this review) baseline:** 0/26 tracks matched, breaks=— none (single undifferentiated block), structure source = deterministic align()

**la=8 (proposed) result:** 25/26 tracks matched, breaks=[21], structure source = deterministic align(), guard declines = 0

**Final setlist shipped at la=8:**

**Set 1**

  1. 01 Intro - Ramona
  2. 02 Two Points For Honesty
  3. 03 Banter - Sports Talk
  4. 04 G Major
  5. 05 Demons
  6. 06 Doing It By Myself
  7. 07 Zeno
  8. 08 Barrel Of A Gun
  9. 09 Lightning Rod
 10. 10 Satellite
 11. 11 Great Escape
 12. 12 Ruby Falls
 13. 13 I Spy
 14. 14 Endlessly
 15. 15 Never Coming Down
 16. 16 Manifest Destiny
 17. 17 Amsterdam
 18. 18 Summertime
 19. 19 Come Downstairs and Say Hello
 20. 20 Do You Love Me
 21. 21 Airport Song

**Encore**

 22. 22 Long Night
 23. 23 Architects and Engineers
 24. 24 Adlib - Trisha on Stage  ← UNMATCHED
      _unmatched — inherits "Encore" from the previous track_
 25. 25 Happier
 26. 26 Jesus On The Radio

---

### Built to Spill — 2015-06-06 — Neurolux

`BTS2015-06-06` — <https://archive.org/details/BTS2015-06-06>

Corpus: non-Dead · collection `BuiltToSpill` · 18 tracks, 25 canonical setlist items · no jerrybase event resolved for this artist/date

**la=3 (the default at the time of this review) baseline:** 0/18 tracks matched, breaks=— none (single undifferentiated block), structure source = deterministic align()

**la=8 (proposed) result:** 18/18 tracks matched, breaks=[15], structure source = deterministic align(), guard declines = 0

**Final setlist shipped at la=8:**

**Set 1**

  1. intro
  2. All Our Songs
  3. The Plan
  4. Distopian Dream Girl
  5. Living Zoo
  6. Kicked It In The Sun
  7. Else
  8. On The Way
  9. I Would Hurt A Fly
 10. Virginia Reel Around The Fountain (Halo Benders cover)
 11. Never Be The Same
 12. Conventional Wisdom
 13. Life's A Dream
 14. So
 15. Carry The Zero

**Encore**

 16. Joyride
 17. Stab
 18. Car

---

### Los Lobos — 2007-05-06 — The Sage Gateshead

`LosLobos2007-05-06.aud.flac16` — <https://archive.org/details/LosLobos2007-05-06.aud.flac16>

Corpus: non-Dead · collection `LosLobosMusic` · 19 tracks, 28 canonical setlist items · no jerrybase event resolved for this artist/date

**la=3 (the default at the time of this review) baseline:** 0/19 tracks matched, breaks=— none (single undifferentiated block), structure source = deterministic align()

**la=8 (proposed) result:** 19/19 tracks matched, breaks=[17], structure source = deterministic align(), guard declines = 0

**Final setlist shipped at la=8:**

**Set 1**

  1. Chuco's Cumbia
  2. One Time One Night
  3. Luz De Mi Vida
  4. Short Side Of Nothing
  5. The Town
  6. Maricela
  7. Hold On
  8. Sabor A Mi
  9. Chains Of Love
 10. Maria Christina
 11. Kiko And The Lavender Moon
 12. Let's Say Goodnight
 13. Ay Te Dejo En San Antonio
 14. Mexico American
 15. Will The Wolf Survive?
 16. Evangeline
 17. La Bamba ->Good Lovin' -> La Bamba

**Encore**

 18. E: Don't Worry Baby
 19. My Generation

---

### Josh Ritter — 2010-10-10 — Devil's Backbone Brewery-Festy

`jritter2010-10-10.flac16` — <https://archive.org/details/jritter2010-10-10.flac16>

Corpus: non-Dead · collection `JoshRitter` · 19 tracks, 27 canonical setlist items · no jerrybase event resolved for this artist/date

**la=3 (the default at the time of this review) baseline:** 0/19 tracks matched, breaks=— none (single undifferentiated block), structure source = deterministic align()

**la=8 (proposed) result:** 18/19 tracks matched, breaks=[18], structure source = deterministic align(), guard declines = 0

**Final setlist shipped at la=8:**

**Set 1**

  1. Good Man
  2. Snow is Gone
  3. Change of Time
  4. Rumors
  5. Wolves
  6. Southern Pacifica
  7. Me & Jiggs
  8. Folk Bloodbath
  9. Girl in the War
 10. To the Dogs or Whoever
 11. Long Shadows
 12. Idaho
 13. Pretty Saro-Moon River
 14. unknown
 15. Everybody Wants to Rule the World>Harrisburg
 16. Right Moves
 17. Dont stop believing
 18. Lillian,Egypt  ← UNMATCHED
      _unmatched — inherits "Set 1" from the previous track_

**Encore**

 19. Money for nothing

---

## Summary of what changed corpus-wide at la=8

Across the full corpus (not just the 13 shows above): Dead matched-track
count moves 20,267 → 20,731 of 23,275 tracks (+464, +2.0%); non-Dead moves
12,355 → 13,051 of 14,193 tracks (+696, +4.9%). Most of that recovery
happens *without* crossing a set-break line — the **final post-anchoring
set-break vector** (the thing that actually ships as `set_breaks`) changes
in only 12/1120 Dead rows (1.1%) and 10/718 non-Dead rows (1.4%). The tail
guard fires in exactly 2 of those 1120+718 = 1838 rows, both Dead, both
shown above in full, both with a same-titled far-ahead candidate that would
otherwise have exhausted the canonical list and mislabeled the rest of the
tape — and both land la=8 on the *identical* final structure la=3 already
shipped at the time of this review, not a new one.

None of the 13 rendered shows come out looking worse at la=8 than la=3 by
this reader's own pass — the two guard shows are unchanged from what
shipped at the time of this review (the guard's job, working as designed),
the four other Dead picks and all six non-Dead picks go from "no set
breaks recovered at all" (or, for Radiators/Against Me!, partial) to a
structured, plausible setlist with the expected shape (segue chains,
Drums>Space placement, standard encore slots). The `UNMATCHED`-marked
tracks that remain are consistently
explainable as filler (crowd noise, tuning, stage banter, "encore break")
or tracks whose canonical setlist item was itself dropped by an upstream
parser artifact (e.g. `gd85-04-06`'s "China Cat Sunflower" got glued into
the same canonical item as "Don't Ease Me In" by a missing separator in the
source description) — not evidence of a new lookahead-caused failure mode.
That said: this is one reader's pass over 13 out of 1838 corpus-wide (Dead +
non-Dead) rows, weighted toward the largest movers, not an exhaustive
review — treat it as a sanity check on the mechanism, not a certification
of every la=8 output.

