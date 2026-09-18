# Live Music Archive genre survey — what the archive actually covers

Measured 2026-09-12 against the live archive.org index. Companion to
`2026-08-07-lma-census.md`, which measured scale, runtime and ratings but not
genre. Counts drift as the archive grows; the *shape* is the durable part.

**Headline:** the LMA is one scene covered deeply, a ring of adjacent genres
covered adequately, and everything else thin — and even the adjacent genres
arrive through a jam-scene lens (jam-jazz, jam-funk, reggae-jam). The etree
collection only admits trade-friendly artists, so most major-label acts are
simply absent.

## Method

1. **Full scrape.** `/services/search/v1/scrape` over
   `collection:etree AND mediatype:etree` (cursor-paged, `count=10000`), fields
   `identifier, creator, year, date, downloads, num_reviews, avg_rating,
   subject, publicdate, collection`: **294,701 items**. (The census's 302,453
   omitted the `mediatype` filter.) A second scrape of
   `collection:etree AND mediatype:collection` returned the 9,308 artist
   collections with `subject` and `description`.
2. **Artist = artist collection.** Each item maps to the etree sub-collection it
   belongs to (46 items map to none). **7,781 collections hold at least one
   item.** A "show" below is a distinct `(artist, date)` pair — **217,375** —
   so an early/late double bill counts once.
3. **Genre by classification, not by metadata.** archive.org's `subject` field
   cannot answer the question: 76% of items carry one, but the tokens are
   dominated by `live concert`, `audience`, `soundboard`, taper and microphone
   names; only ~2% of artist collections carry a genre word at all. So the
   **top 2,000 artists by item count** (90.2% of items, 87.7% of shows) were
   classified by four Sonnet agents into the fixed 21-code taxonomy below, one
   `primary` per artist, from an evidence pack of genre-word `subject` tokens,
   the first 220 characters of the collection description, and the model's own
   knowledge — with an explicit instruction to answer `unknown` rather than
   infer from a band name. The 5,781 tail artists were not classified; they are
   described from tags alone.
4. **MusicBrainz grounding was attempted and abandoned.** Anonymous lookups
   were throttled (503s and timeouts) to ~3/min, i.e. ~10 h for 2,000 artists.

### Taxonomy

`gd-family` (the Dead and members' own bands) · `dead-tribute` · `tribute-other`
· `jam-rock` · `livetronica` · `bluegrass` (incl. newgrass, jamgrass, string
band) · `americana` (alt-country, roots rock) · `country` · `folk` (incl.
singer-songwriter, Celtic) · `blues-southern` · `funk-soul` (incl. New Orleans) ·
`jazz` · `indie-alt` · `rock-classic` · `punk-metal` · `reggae-world` ·
`electronic` (non-jam) · `hip-hop` · `pop` · `other` · `unknown`.

## Concentration

| Top N artists | Share of items |
|---:|---:|
| 10 | 15.4% |
| 100 | 41.4% |
| 250 | 57.2% |
| 500 | 68.9% |
| 1,000 | 80.4% |
| 2,000 | 90.2% |
| 5,000 | 98.5% |

| Shows per artist | Artists | Items |
|---|---:|---:|
| 1 | 1,674 | 1,815 |
| 2–4 | 1,959 | 5,852 |
| 5–24 | 2,636 | 32,518 |
| 25–99 | 1,085 | 60,373 |
| 100–999 | 412 | 142,551 |
| 1,000+ | 15 | 51,592 |

## Coverage by genre

`show%` is share of all 217,375 shows. `no-low%` is the same share with every
low-confidence classification moved to `unknown` — the robustness check.
`100+` / `25–99` count artists with that many shows: **100+ is the depth that
can sustain a recurring profile.** `rated%` is the share of the genre's items
with any review — the evidence winnow runs on. `med yr` is the item-weighted
median recording year; `2020s` counts artists with a recording in 2020 or later.

| Genre | Artists | Shows | show% | no-low% | item% | 100+ | 25–99 | rated% | dl/item | med yr | 2020s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| jam-rock | 384 | 53,029 | 24.4% | 22.6% | 24.8% | 112 | 199 | 23.2% | 1,751 | 2009 | 245 |
| bluegrass | 176 | 20,022 | 9.2% | 9.0% | 9.3% | 46 | 91 | 23.7% | 1,671 | 2013 | 124 |
| *unknown* | 415 | 19,280 | 8.9% | 13.2% | 7.3% | 39 | 222 | 8.5% | 943 | 2014 | 225 |
| indie-alt | 140 | 15,155 | 7.0% | 6.9% | 6.6% | 34 | 78 | 20.8% | 3,228 | 2006 | 86 |
| americana | 127 | 13,281 | 6.1% | 6.0% | 5.4% | 30 | 70 | 21.6% | 2,145 | 2010 | 83 |
| funk-soul | 161 | 11,590 | 5.3% | 5.0% | 5.1% | 29 | 91 | 18.3% | 1,227 | 2013 | 104 |
| dead-tribute | 78 | 10,429 | 4.8% | 4.7% | 4.4% | 28 | 41 | 14.3% | 1,313 | 2017 | 73 |
| folk | 96 | 7,633 | 3.5% | 3.3% | 3.0% | 19 | 62 | 20.1% | 2,549 | 2010 | 61 |
| blues-southern | 77 | 7,477 | 3.4% | 3.3% | 3.4% | 16 | 43 | 23.7% | 2,001 | 2011 | 52 |
| gd-family | 21 | 5,717 | 2.6% | 2.6% | **9.3%** | 10 | 10 | **51.7%** | 9,727 | 1985 | 10 |
| jazz | 72 | 5,538 | 2.5% | 2.3% | 2.5% | 14 | 44 | 21.9% | 1,148 | 2011 | 47 |
| rock-classic | 72 | 5,475 | 2.5% | 2.0% | 2.2% | 14 | 35 | 20.9% | 2,301 | 2007 | 38 |
| livetronica | 38 | 5,342 | 2.5% | 2.4% | 2.5% | 11 | 21 | **46.3%** | 3,517 | 2006 | 23 |
| reggae-world | 45 | 4,184 | 1.9% | 1.6% | 1.7% | 10 | 24 | 20.2% | 1,774 | 2010 | 26 |
| punk-metal | 27 | 1,758 | 0.8% | 0.8% | 0.7% | 4 | 15 | 23.4% | 2,474 | 2006 | 14 |
| pop | 17 | 1,627 | 0.7% | 0.7% | 0.7% | 3 | 9 | 33.5% | 5,765 | 2005 | 8 |
| tribute-other | 20 | 1,342 | 0.6% | 0.6% | 0.6% | 3 | 15 | 13.7% | 1,000 | 2019 | 17 |
| country | 16 | 837 | 0.4% | 0.4% | 0.3% | 2 | 8 | 14.4% | 2,790 | 2015 | 12 |
| electronic | 10 | 522 | 0.2% | 0.2% | 0.2% | 1 | 6 | 6.4% | 856 | 2009 | 6 |
| other | 6 | 298 | 0.1% | 0.1% | 0.1% | 1 | 1 | 23.3% | 4,397 | 2017 | 4 |
| hip-hop | 2 | 143 | 0.1% | 0.1% | 0.1% | 1 | 0 | 18.3% | 1,679 | 2013 | 1 |
| *tail (not classified)* | 5,781 | 26,696 | 12.3% | — | 9.8% | — | — | — | — | — | — |

### Tiers

- **Core — deep enough for many independent recurring segments.** jam-rock
  (112 deep artists), bluegrass/jamgrass (46), and the Dead universe:
  `gd-family` + `dead-tribute` together are ~7.4% of shows, and **~10,300 shows
  across the top 2,000 are by bands whose `tribute_of` names only the Dead or
  Garcia** (another ~300 cover the Dead alongside Phish, Pink Floyd or Steely
  Dan), against 370 for Phish.
- **Solid — dozens of deep artists, but scene-flavoured.** indie-alt (34, skewed
  to 1990s–2000s college rock), americana (30), funk-soul (29, jam-funk and New
  Orleans), folk/singer-songwriter (19), blues-southern (16, the Trucks family),
  jazz (14 — jam-jazz, not straight-ahead), classic rock (14), livetronica (11).
- **Thin — a segment would be a handful of artists on rotation.** reggae-world
  (10 deep), punk-metal (4), pop (3: Mayer/Mraz/Nathanson adult pop), country
  (2), electronic (1), hip-hop (1).
- **Effectively absent.** Mainstream country, straight-ahead jazz, hip-hop,
  non-jam electronic, metal, classical (two community orchestras), and
  non-anglophone music beyond reggae/afrobeat-jam.

### Single-artist concentration

Share of a genre's items held by its largest artist: hip-hop **87%** (DJ Logic),
gd-family **67%** (Grateful Dead), `other` 54% (Holly Bowling), country **39%**
(Daniel Donato), livetronica 27% (Disco Biscuits), tribute-other 27% (Pink
Talking Fish). Every core and solid genre is at 18% or under. A "country" or
"hip-hop" profile would in practice be one artist.

### Largest artists by genre (shows)

- **jam-rock:** Widespread Panic 2,551; Max Creek 2,093; moe. 2,006; Umphrey's
  McGee 1,781; Radiators 1,473; String Cheese Incident 1,294; Mr. Blotto 1,250;
  Blues Traveler 1,226
- **bluegrass:** Yonder Mountain String Band 1,406; Railroad Earth 1,243;
  Leftover Salmon 976; Greensky Bluegrass 884; Hot Buttered Rum 676; Infamous
  Stringdusters 632; Cabinet 620; Billy Strings 556
- **indie-alt:** Smashing Pumpkins 923; Robyn Hitchcock 836; Guster 766; Ween
  626; Cracker 552; Godspeed You! Black Emperor 537; Steve Wynn 508; Local H 505
- **americana:** Donna the Buffalo 1,015; Drive-By Truckers 811; Los Lobos 806;
  Bob Walkenhorst 702; Yarn 659; Ryan Adams 581; New Riders of the Purple Sage
  411; Dave Alvin 366
- **funk-soul:** Karl Denson's Tiny Universe 541; JJ Grey & MOFRO 492; Lettuce
  465; Galactic 406; Dumpstaphunk 396; Soulive 394; Robert Randolph 314; Kung Fu
  311
- **dead-tribute:** Stu Allen & Mars Hotel 920; Dark Star Orchestra 805;
  Cubensis 805; Splintered Sunlight 548; John Kadlecik 396; Joe Russo's Almost
  Dead 381; The Reckoning 373; Deadstein 367
- **folk:** Ryan Montbleau 471; Glen Phillips 441; Stephen Kellogg 400; Howie
  Day 336; Gandalf Murphy & the Slambovian Circus of Dreams 291; Robert Hunter
  273; Carbon Leaf 268; Charlie Parr 245
- **blues-southern:** North Mississippi Allstars 980; Tedeschi Trucks Band 732;
  Derek Trucks Band 730; Grace Potter & the Nocturnals 363; Marcus King Band
  273; Chris Duarte Group 240; Blackberry Smoke 215; G. Love & Special Sauce 207
- **gd-family:** Grateful Dead 2,073; Phil Lesh & Friends 788; Ratdog 689; JGB
  366; Bob Weir 309; Dead & Company 265; Furthur 246; Melvin Seals 192
- **jazz:** Club d'Elf 497; Charlie Hunter 375; Garaj Mahal 312; Hairy Larry
  301; Jacob Fred Jazz Odyssey 228; Jazz Mandolin Project 226; Marco Benevento
  214; Schleigho 208
- **rock-classic:** Little Feat 854; Mother Hips 440; Jefferson Starship 270;
  Bloodkin 247; Drivin' N' Cryin' 194; John Grizzly Band 176; Warren Zevon 161;
  Mermen 161
- **livetronica:** Disco Biscuits 1,186; Perpetual Groove 689; Sound Tribe
  Sector 9 561; Brothers Past 449; Lotus 437; The New Deal 247; Particle 228;
  Papadosio 131
- **reggae-world:** The Mighty Manatees 650; Michael Franti & Spearhead 424;
  Dub Apocalypse 376; Conehead Buddha 373; Matisyahu 350; Toubab Krewe 197;
  John Brown's Body 128; State Radio 116
- **punk-metal:** Meat Puppets 241; Mudhoney 197; Mekons 194; Mike Watt 173;
  Candlebox 87; Buckethead 87; Karma To Burn 71; Supersuckers 65
- **pop:** John Mayer 384; Jason Mraz 367; Matt Nathanson 360; Miles Nielsen 69;
  Gavin DeGraw 65; Vertical Horizon 65
- **tribute-other:** Pink Talking Fish 298; The Electric Waste Band 117; Dead
  Floyd 104; Runaway Gin 97; Steely Dead 96; The Machine 79
- **country:** Daniel Donato 250; Hank Williams III 113; Girls, Guns and Glory
  62; Corb Lund 52; Josie Sanken 50; Wayne Hancock 49
- **electronic:** Jeff Bujak 129; Frank Moore 81; Instagon 79; Autechre 66
- **other:** Holly Bowling 187; Tenacious D 52; Brave Combo 20; two community
  symphony orchestras
- **hip-hop:** DJ Logic 129; optimus rhyme 14

## Era

Item mix by recording decade (top genres only):

| Decade | Items | Mix |
|---|---:|---|
| 1960s | 634 | gd-family 94%, rock-classic 3% |
| 1970s | 4,422 | gd-family 89%, rock-classic 4%, jam-rock 2%, americana 2% |
| 1980s | 13,440 | gd-family 73%, jam-rock 12%, indie-alt 4% |
| 1990s | 26,445 | jam-rock 36%, gd-family 20%, indie-alt 13%, unknown 5% |
| 2000s | 85,197 | jam-rock 26%, tail 11%, indie-alt 8%, bluegrass 8%, americana 6% |
| 2010s | 112,928 | jam-rock 24%, bluegrass 12%, tail 12%, unknown 8%, funk-soul 7% |
| 2020s | 51,560 | jam-rock 23%, unknown 12%, bluegrass 12%, tail 11%, dead-tribute 10% |

**Before 1990 the archive is the Dead.** Anything wanting pre-1990 material
outside that universe has very little to draw on. The 1990s are jam-rock plus
college rock; since 2010 bluegrass has doubled its share, and in the 2020s
Dead tribute bands reach 10% of new recordings.

## Implications for llama

- **Winnow's reception evidence thins sharply outside two genres.** Only
  gd-family (52%) and livetronica (46%) have more than a third of items reviewed;
  most genres sit at 18–24%, and dead-tribute (14%), tribute-other (14%),
  country (14%) and electronic (6%) are thinner still. Per the census, a single
  review carries almost no information, so the effective evidence is thinner
  than these percentages.
- **Offline structure evidence covers ~2.6% of shows.** jerrybase
  (`data/set_breaks.csv`) covers the Garcia universe only; every other genre
  depends on descriptions and setlist.fm.
- **The Dead's multi-recording is visible here too.** gd-family is 2.6% of shows
  but 9.3% of items (the census's 8.8 recordings per show);
  `select_recording` does real work there and little elsewhere.
- **Profile viability tracks the `100+` column.** A recurring segment in a
  genre with fewer than ~5 deep artists is effectively an artist profile.

## Confidence and limits

- **Robust to the low-confidence labels.** Moving every `conf: low`
  classification to `unknown` moves jam-rock 24.4% → 22.6% and no other genre
  by more than 0.5 points.
- **`unknown` grows with rank** — 0 in ranks 1–100, 41 in 101–500, 92 in
  501–1000, 122 in 1001–1500, 160 in 1501–2000. Only 26 of the 415 `unknown`
  artists carry any genre tag, and those lean acoustic / jam / bluegrass, so
  jam and bluegrass shares are if anything understated.
- **Knowledge-only labels can be confabulated.** In ranks 1501–2000, 46 artists
  with no archive evidence were classified from model knowledge alone.
  Spot-checked examples were correct (Alice Donut, The Antlers, Thinking
  Fellers Union Local 282), but some are unverifiable. Top-rank labels
  (1–45 inspected by hand) were all sound.
- **Boundary calls exist.** e.g. the Radiators went to jam-rock rather than
  funk-soul; String Cheese Incident to jam-rock with livetronica secondary.
  One `primary` per artist hides real hybrids.
- **The tail is unclassified.** 5,781 artists, 12.3% of shows, median 3 shows
  each. 1,680 carry any genre tag; weighted by shows those read rock, funk,
  jam, jazz, jam band, acoustic, bluegrass, blues, folk, americana — the same
  scene profile as the head.
- **Genre is per artist, not per recording.** Artists who changed style over a
  career are counted under their dominant LMA style.

## Reproducing

Scripts and intermediate data were written to the session scratchpad, not the
repo. To redo: page the scrape API for items (the fields above) and for
`mediatype:collection`; map each item to its artist collection; aggregate items,
distinct dates, downloads, reviewed items and year span per artist; build a
one-line evidence pack per artist for the top 2,000; classify in batches of 500
against the taxonomy with an explicit `unknown` instruction; join. The scrape
takes ~5 minutes; classification took four parallel Sonnet agents ~11 minutes
each.

---

# Addendum, 2026-09-18 — the Dead universe, split two ways

Measured while deciding whether the Dead material supports one recurring
profile or two. This is a **targeted** re-scrape, not a repeat of the survey
above: two hand-curated collection sets rather than the top-2,000
classification. The archive had grown to **9,313** artist collections (from
9,308 on 2026-09-12).

## Question

The survey's `gd-family` (21 artists, 5,717 shows) and `dead-tribute` (78
artists, 10,429 shows) rows are adjacent but were never compared on the axis
that decides profile viability: **how many shows survive winnow's floors.**
Genre share does not answer that, because review density varies by a factor of
four across these two groups.

## Method

Two collection sets, both hand-curated, both listed in the reproduction notes:

- **Member-led** — bands fronted by actual Grateful Dead members (Phil Lesh and
  Friends, Ratdog, Furthur, The Dead, The Other Ones, Dead & Company, Bob Weir,
  Billy and the Kids, Mickey Hart Band, Rhythm Devils, 7 Walkers, JGB, Melvin
  Seals, Donna Jean, Tom Constanten, Vince Welnick, Robert Hunter, plus the
  Lesh-family bands). 22 collections hold items. The Grateful Dead's own
  collection is excluded throughout — it is `dead.toml`'s.
- **Tribute** — Dead/Garcia repertoire bands with no original members. 130
  collections curated from a name sweep, 123 hold items.

A "show" is a distinct `(collection, date)` pair. A show counts as passing a
floor when **any** of its recordings passes, since `select_recording` picks per
performance.

## Result

| | Collections | Items | Shows | 100+ | 25–99 | any review | pass `≥3 & 3.5` |
|---|---:|---:|---:|---:|---:|---:|---:|
| Member-led | 22 | 9,519 | 3,895 | 10 | 10 | **59.4%** | **28.6%** (1,115) |
| Tribute | 123 | 10,835 | 8,488 | 19 | 29 | 17.2% | **2.7%** (226) |

**The two halves are not the same population under winnow.** Tribute bands hold
more than twice the shows and less than a quarter of the eligible ones. A single
combined profile at `min_reviews = 3` would draw 1,115 against 226 — 83/17 — so
the tribute half would be a rounding error in every run, silently, with nothing
in the output saying why. That asymmetry, not the editorial distinction, is the
argument for two profiles.

## Two findings that changed the build

**Jerry-era Garcia side projects are absent from the LMA entirely.** There is no
Jerry Garcia Band, Legion of Mary, Old & In the Way or Garcia/Grisman collection
in etree. The `JGB` collection is **Melvin Seals'** post-Jerry band; every other
"Garcia" collection is a tribute act or an unrelated band (Boris Garcia, Garcia
Peoples). 3,571 of the 3,895 member-led shows postdate 1995-08-09, and the
remaining 324 are mostly Weir's pre-hiatus side projects. **So "post-Jerry
projects by Dead members" is the entire member-led population** — a further
era split would separate 324 shows from 3,571, and no `date_from` is needed.

**The review floor is what decides whether a tribute profile is a genre or two
bands.** Of the 226 tribute shows clearing `min_reviews = 3`, Dark Star
Orchestra holds 119 and Joe Russo's Almost Dead 62 — 80% in two acts, with only
16 of 123 collections contributing a single show.

| `min_reviews` (at `avg ≥ 3.5`) | Eligible shows | Contributing artists | Can fill a 9-show run alone | Top-2 share |
|---:|---:|---:|---:|---:|
| 3 | 226 | 16 | 2 | **80%** |
| 2 | 496 | 27 | 7 | 67% |
| 1 | 1,336 | 56 | 17 | 46% |

Member-led is far less floor-sensitive — 1,115 / 1,543 / 2,164 eligible at the
same three thresholds, with 21 artists contributing at every one.

## Offline structure evidence covers these two profiles, unlike the rest

The survey's "jerrybase covers ~2.6% of shows" implication does **not** carry
here. `data/set_breaks.csv` holds ten artist keys — Grateful Dead, Dark Star
Orchestra, Ratdog, Phil Lesh & Friends, Jerry Garcia Band, Furthur, Bob Weir,
Dead & Company, The Dead, The Other Ones — plus JRAD via
`jerrybase._EXTRA_FAMILY`. That is the whole top tier of the member-led set and
the top two of the tribute set, so both get set-break anchoring and the
`songs.GD_SHORTHAND` vocabulary. The tribute long tail (Cubensis, Stu Allen,
Splintered Sunlight) falls off-family and depends on descriptions and
setlist.fm like every other genre.

Note a quirk rather than a defect: a tribute recreating a specific historical
setlist is dated to its **own** performance date, so jerrybase matches that
band's row, not the show being recreated.

## What was built

`dead-family` (member-led, `min_reviews = 3`) and `dead-tribute`
(`min_reviews = 2` — double the eligibility and triple the artists that can
carry a run, without dropping to a lone uncorroborated review). Both at
`artist_cap = 0.25`: member-led's top two are 49% of its eligible pool, so the
default 1/3 would let two artists take 6 of 9 slots.

## Limits

- **The tribute set is a floor, not a census.** It was curated from a name sweep,
  so tributes whose names carry no Dead vocabulary (Crazy Fingers, Zen
  Tricksters, Cosmic Charlie and their kind) are missing — which is why 8,488
  shows here sits below the survey's classified 10,429. The misses are small,
  obscure and lightly reviewed, so they would if anything push the pass rate
  *down*; the concentration finding is conservative.
- **A handful of items are dual-listed** in both a member-led and a tribute
  collection — about 5 shows, depending on attribution order. Immaterial to
  every conclusion above, but the two sets are not perfectly disjoint.
- **Membership is by collection, not by lineup-at-the-time.** A band whose
  lineup gained or lost a Dead member mid-history sits wholly on one side.

## Reproducing

Scrape `collection:etree AND mediatype:collection` for `identifier,title`; sweep
titles for Dead vocabulary and hand-curate the two sets (the name sweep
over-collects badly — Billy Strings, Billy Corgan, Dead Confederate, …And You
Will Know Us By the Trail of Dead all match); scrape
`mediatype:etree AND (collection:A OR collection:B OR …)` for
`identifier,collection,date,avg_rating,num_reviews,downloads`; reduce to
`(collection, date)` keeping the best `(num_reviews, avg_rating)` per show; count
against the floors. Under a minute end to end.
