# Live Music Archive census — scale, runtime, and what ratings are worth

Measured 2026-08-07 against the live archive.org index. Nothing here is
estimated from memory; every number below came out of a full enumeration of
`collection:etree` plus one 800-item random sample. Counts drift as the archive
grows — treat the *ratios* as durable and the absolute counts as a snapshot.

## Method

Two passes, both reproducible in a few minutes:

1. **Full census.** The scrape API (`/services/search/v1/scrape`, `count=10000`,
   cursor-paged, 31 pages) returns every item's indexed fields. Fields pulled:
   `identifier, avg_rating, num_reviews, downloads, year, creator, item_size`,
   and on a second pass `date`. This is a complete enumeration, not a sample —
   the rating and download figures below carry no sampling error.
2. **Runtime sample.** Runtime is *not* in the search index; it lives per-file in
   item metadata. So 800 identifiers were drawn uniformly at random (seed
   20260807) and `https://archive.org/metadata/<id>` fetched for each.

**Runtime is summed per format, then the largest format total is taken** — never
the sum over all audio files. An item carries the same concert several times over
(VBR MP3 + Flac + original WAVE), so summing everything multiply-counts it. The
known bias: this slightly over-counts where one format carries bonus or junk
files. See "Domain gotchas" in `CLAUDE.md` — that spam file in the canonical
fixture is exactly the shape of thing being counted here.

## Scale

| | |
|---|---|
| Items in `collection:etree` | **302,453** |
| Distinct `(artist, date)` performances | **216,483** |
| Distinct creators | 9,656 |
| Total bytes, all formats | 332.9 TB |
| **Total audio runtime** | **~575,000 h ≈ 65.5 years continuous** |

Runtime from the 800-item sample: 785 usable (98%), mean **1.935 h/item**
(95% CI 1.849–2.021), median 1.91 h, sd 1.23. Quartiles 1.25 / 1.91 / 2.52 h;
16% of items run under an hour, only 7% over three.

Total = mean × items-with-audio = **574,364 h**, 95% CI 548,805–599,922.

**Cross-checked by an independent route**: hours-per-byte on the sample, scaled
by the collection's full 332.9 TB, gives **577,611 h** — 0.6% apart. Two methods
with different failure modes agreeing this closely is the main reason to trust
the figure.

### Do not estimate this from llama's local cache

The `~/.llama/cache` sample (602 items with runtime) reads **2.72 h/item** — 40%
high. That cache is what llama happened to fetch, which is Grateful Dead
two-set shows, which sit near the top of the length distribution. An earlier
pass at this question used the cache and produced a 600k–820k bracket that the
random sample falsifies. Any future "how much content" question must sample the
collection, not the cache.

## Composition

Performances by decade (year present on 293,294 of 302,453 items):

| Decade | Items | |
|---|---:|---|
| 1960s | 630 | 0.2% |
| 1970s | 4,406 | 1.5% |
| 1980s | 13,399 | 4.6% |
| 1990s | 26,390 | 9.0% |
| 2000s | 85,075 | 29.0% |
| 2010s | **112,818** | 38.5% |
| 2020s | 50,573 | 17.2% |

Top creators: Grateful Dead 18,306 (6.1%), moe. 4,615, Widespread Panic 4,353,
Umphrey's McGee 3,378, Max Creek 3,095, Phil Lesh and Friends 2,892. The top 20
artists are only 20% of the collection; 9,636 other artists hold the rest.

### Multiple recordings per performance is a Dead phenomenon, not an archive norm

| Recordings of one performance | Performances | |
|---|---:|---|
| 1 | 176,057 | **81.3%** |
| 2 | 27,395 | 12.7% |
| 3 | 6,438 | 3.0% |
| 4 | 2,790 | 1.3% |
| 5+ | 3,803 | 1.8% |

Archive-wide mean is **1.35 recordings per performance**. Grateful Dead:
**2,073 distinct dates from 18,305 recordings — 8.8 per show.**

This matters for `select_recording`. On llama's actual usage it is doing real
work every time (gd1990-03-29 had 27 candidates). On the archive at large it
would be a no-op for four shows in five. The stage is correctly built for the
Dead case; just don't generalize its importance.

## Ratings

**Coverage is the first problem: only 22.8% of items are rated at all** (68,815
of 302,453). `avg_rating` and `num_reviews` are *absent*, not zero, on the rest —
any filter must treat missing as unknown, never as bad, or it discards 77% of the
archive sight-unseen.

Distribution among the rated:

| Stars | Items | Share of rated |
|---|---:|---:|
| 5.0 | 35,678 | **51.8%** |
| 4.5 | 9,524 | 13.8% |
| 4.0 | 14,093 | 20.5% |
| 3.0–3.5 | 4,538 | 6.6% |
| < 3.0 | 1,138 | 1.7% |
| 0.0 | 3,844 | 5.6% |

53% of rated items carry exactly **one** review. The modal rated item in the LMA
is a single five-star review.

### The attendance bias is real and measurable

`CLAUDE.md` asserts LMA reviews are heavily attendance-biased and that winnowing
should demand evidence from people who were *not* there. That premise now has
direct support. Median downloads by rating bucket, whole collection:

| Bucket | n | Median downloads | Per year since upload | Single-review |
|---|---:|---:|---:|---:|
| unrated | 233,638 | 660 | 72 | — |
| < 4.0 | 10,127 | 2,066 | 149 | 60.0% |
| 4.0–4.7 | 23,010 | **3,218** | **200** | **37.7%** |
| 5.0 | 35,678 | 2,095 | 153 | 61.8% |

**A 5.0 rating predicts no more downloads than a sub-4.0 rating** (153/yr vs
149/yr), and fewer than a 4.0–4.7 (200/yr). Rating and popularity are not
monotonically related. The right-hand column is the raw `downloads` field divided
by years since `publicdate` — the ordering is identical either way, so this
headline is not an exposure artifact.

**But the mechanism is composition, not a real penalty on 5.0.** See the
stratified table below: 62% of 5.0 items (22,043 of 35,676) carry a single
review, and single-review items are low-download *regardless of rating*. The
aggregate is dragged down by that mix. Within any fixed review count of 10 or
more, 5.0 is the **best** bucket. This is Simpson's-paradox-shaped, and it is
the whole reason the ceiling needs an escape hatch rather than being applied
flat.

Yield at a genuine bar:

| Filter | Items | % of collection |
|---|---:|---:|
| ≥1 review & ≥4.0 | 58,688 | 19.4% |
| ≥2 reviews & ≥4.0 | 27,958 | 9.2% |
| ≥3 reviews & ≥4.0 | 15,845 | 5.2% |
| ≥3 reviews & ≥4.5 | 11,093 | 3.7% |
| ≥5 reviews & ≥4.5 | 4,919 | 1.6% |
| ≥10 reviews & ≥4.5 | 1,660 | 0.5% |

## TOPIC TO REVISIT: a rating ceiling, with a downloads/reviews escape hatch

**Not implemented. Filed for a later design pass.** What follows is the evidence
that motivates it and the control that keeps it honest.

The finding above suggests winnow could treat a bare 5.0 as *weak* evidence
rather than strong — a **ceiling** as informative as the floor. But that rule
must not throw away the genuine best-of-the-best, which also rates 5.0. The
escape hatch: **a very high review count and/or download count re-admits an
above-ceiling show.**

`downloads` is cumulative, so it measures exposure as much as appeal. Every
table below is therefore **median downloads per year since `publicdate`**, not
raw downloads. (`publicdate` is indexed and free to pull — see the note on the
discarded proxy at the end of this section.)

Median downloads/yr, rating × review count, whole collection (n in parens):

| | 1 review | 2–4 | 5–9 | 10–24 | 25+ |
|---|---:|---:|---:|---:|---:|
| < 4.0 | 108 (6074) | 193 (2730) | **593** (787) | 1,060 (470) | 1,726 (62) |
| 4.0–4.7 | 111 (8686) | **199** (9625) | 592 (2675) | 1,365 (1605) | 3,039 (414) |
| 5.0 | **120** (22043) | 198 (10790) | 497 (2051) | **1,558** (631) | **4,475** (161) |

Unrated baseline on the same metric: **72/yr** (n=233,637).

Three things happen in this table:

1. **Review count dominates rating.** Moving along a row (1 → 25+ reviews) swings
   the rate ~40×. Moving down a column changes it by under 25% except in the
   right-hand cells. If only one of the two signals can be used, it should be
   `num_reviews`, not `avg_rating`.
2. **At 1–4 reviews, rating carries essentially no information.** The three
   buckets sit within ~10% of each other (108 / 111 / 120 at one review). This is
   the regime the ceiling is really about — not "5.0 is bad" but "a rating built
   on one or two reviews tells you nothing at all." Note that *having any review*
   still beats having none: 72/yr unrated vs ~110/yr at one review.
3. **Above ~10 reviews the ordering separates and 5.0 wins decisively.** At 25+
   reviews a 5.0 item runs 4,475/yr against 3,039 (4.0–4.7) and 1,726 (<4.0) —
   1.5× and 2.6×. **A 5.0 backed by many reviewers is exactly the best-of-the-best
   the escape hatch is meant to protect.** The crossover sits around **10
   reviews**, and the 5–9 column is where 5.0 is genuinely *worst* (497 vs ~592).

### Controlling for exposure directly

Review count is itself strongly correlated with how long an item has been up:

| Reviews | n | Median **upload** year |
|---|---:|---:|
| 0 | 233,637 | 2016 |
| 1 | 36,803 | 2011 |
| 2–9 | 28,658 | 2008 |
| 10–24 | 2,706 | 2005 |
| 25+ | 637 | **2004** |

So the ≥25-review population has had roughly 22 years of exposure against 10 for
the unreviewed one. Holding reviews at ≥25 and stratifying by **upload** year
(median downloads/yr, so exposure is controlled twice over):

| Uploaded | < 4.0 | 4.0–4.7 | 5.0 |
|---|---:|---:|---:|
| 2001–2004 | 1,829 (52) | 3,088 (336) | **4,846** (98) |
| 2005–2008 | 1,569 (9) | 3,681 (43) | **4,335** (47) |
| 2009–2013 | 468 (1) | 924 (34) | **3,112** (16) |
| 2014–2026 | — | 3,310 (1) | — |

**The ordering holds in every populated stratum**, and the 2009–2013 gap (3.4×)
is the widest of the three. Exposure does not explain the effect.

### A discarded proxy, recorded so it isn't repeated

The first version of this analysis stratified by **performance** year, on the
assumption it proxied upload date. It does not, in the population that matters.
Median lag from performance to upload is 0 years overall (Q3 = 5) — the archive
is mostly contemporary taping uploaded promptly — but for the old performances
that dominate the high-review cells the lag is decades. The proxy made the
confound look far worse than it is: performance year read 1981 vs 2012 across the
review-count range (31 years), where the true upload figures are 2004 vs 2016
(12 years).

It also inverted one cell. On raw cumulative downloads, 5.0 at one review looked
*lower* than 4.0–4.7 (1,533 vs 1,597), which read as "a bare 5.0 is actively
worse." Exposure-normalized it is marginally higher (120 vs 111). Both gaps are
noise; the correct statement is that the buckets are indistinguishable there. Use
`publicdate`. It costs one extra field on the scrape call.

### Open questions for the design pass

- Where exactly does the ceiling apply — is `num_reviews < 10` the right gate, or
  should it scale with the artist's own review density? A 1970s Dead show and a
  2015 club gig do not draw reviewers at comparable rates.
- Should the escape hatch key on downloads, review count, or both? Downloads have
  99.1% coverage but an unfixed age confound; reviews have 22.8% coverage but no
  exposure problem.
- Downloads must be normalized by `publicdate` before use as a threshold — the
  raw field is cumulative and an old mediocre tape outscores a new great one.
  Ranking *within* an upload-era stratum needs no normalization and may be
  simpler than carrying a rate.
- The population is small: only 162 items archive-wide are 5.0 with 25+ reviews.
  Confirm the hatch is worth its complexity before building it.

## Filterable fields, by cost

**Indexed — free, server-side, usable in the initial wide-net search:**
`creator`, `year` / `date`, `downloads` (**99.1% coverage** — the only broad
popularity signal in the archive), `avg_rating` / `num_reviews` (22.8%),
`item_size`, `format` (lossless availability), `publicdate` / `addeddate`
(**required to make `downloads` meaningful**), subcollection membership.

**Not indexed — requires per-item metadata, which `gather` already pays for:**
runtime, track count, SBD vs AUD lineage, taper/transfer notes, setlist.

## Reproducing

The two scripts are ~40 lines each and were written to the session scratchpad,
not the repo. To redo: page the scrape API with a cursor for the census, then
fetch `archive.org/metadata/<id>` over a random sample for runtime, summing per
format and taking the max. Expect ~3 min for the census and ~25 min for an
800-item runtime sample (the metadata endpoint is slow on large items).
