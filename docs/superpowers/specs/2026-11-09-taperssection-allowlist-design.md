# Taper's Section allowlist: design

Date: 2026-11-09. Status: draft, awaiting review.

## Review mode and stakes

**Review mode: Opus** (operator, 2026-11-09). The second spec reviewer and the
final branch reviewer are Opus.

**Stakes.** The change is additive: llama gains a second source of artists. No
surface is strict. Nothing deletes, overwrites or migrates user data, and no
existing artifact changes shape. The operator ruled that airing taperssection
material from broadly taper-friendly artists is not a strict surface ("we're
pretty under the radar"). Permission is an operator decision recorded per artist
(below), not a hard gate in code. **The guarded surface is no regression for
existing LMA artists**, in two strengths (my call, from the builder check):
- **Empty allowlist: byte-identical to today**, including every LLM prompt's
  rendered text. Any prompt wording added for this feature renders only when
  the allowlist is non-empty.
- **Populated allowlist:** each LMA artist's own search query, grouping, winnow
  scoring inputs and recording selection are unchanged. Discovery's artist mix
  and a mixed profile's shortlist may change **by design**, because allowlisted
  artists now compete.
A reviewer who finds an LMA-artist change outside those two bullets should
treat it as a defect.

## Intent

archive.org's **Taper's Section** (`collection:taperssection`, Community Audio)
holds about 31,100 lossless live recordings by artists that have no Live Music
Archive collection. llama cannot reach any of it today. Search hard-codes
`mediatype:etree` plus `collection:<artist collection>`
(`stages/search.py:build_query`), and the artist index is built only from
`collection:etree` (`artist_index.py:COLLECTIONS_QUERY`/`ITEMS_QUERY`).
Taperssection items are `mediatype:audio`, and their only collections are
`taperssection` and `audio_music`.

Most of the collection is a long tail of tiny bands: 8,651 distinct `creator`
strings, 6,049 of them with a single item. But about 46% of items belong to
artists the station wants, and none of those artists has an LMA collection
(checked against the cached artist index). Survey, 2026-11-08:

| creator | items | items with any review |
|---|---|---|
| Phish | 11,134 (1,882 show dates) | 96 |
| Jerry Garcia (JGB era, 1973-93 bulk; 1 item after 1995-08) | 1,648 | 41 |
| Gov't Mule | 360 | 9 |
| Dave Matthews Band | 112 | 6 |
| Trey Anastasio / Trey Anastasio Band | 111 / 78 | 2 / 2 |
| Pavement, Medeski Martin & Wood, Allman Brothers Band, Black Crowes, Wilco | 74-107 each | 0-10 |
| Warren Haynes, Neil Young & Crazy Horse, Sonic Youth, Primus, Bruce Hornsby, Pearl Jam, Mike Gordon | 33-51 each | 0-3 |
| Nine Inch Nails | 5 | 1 |

Survey data: the scrape of every item (identifier, creator, date, num_reviews,
downloads, avg_rating, collection), rolled up by normalized creator. The probe
is easy to re-run; the builder should re-run it rather than trust these figures.

**What the operator wants:** a curated **allowlist** of taperssection artists that
become first-class llama artists. The main consumers are profiles. Phish and
Garcia each get a dedicated profile. Others join existing profiles through
ordinary discovery: Warren Haynes in `southern`, Sonic Youth and Pearl Jam in
`indie`, and so on. Opening the whole collection is an anti-goal, because it
would flood discovery with bar bands.

## Goals

1. An operator-maintained allowlist of taperssection artists. Each entry names
   one llama artist, the uploader `creator` spellings it covers, and that
   artist's recording policy.
2. Allowlisted artists appear in the artist index and reach llama by all three
   routes: unpinned profile discovery (the LLM matcher), pinned rosters
   (`Criteria.artists`) and one-off queries (`llama get "Phish 1995-12-31"`
   through `interpret`).
3. Search, grouping, winnow, select, gather and package work on taperssection
   items for those artists, under the adjustments below.
4. A per-tape policy filter that drops, or holds for review, tapes the artist's
   policy forbids or that cannot be classified.
5. A one-time **research round** over the allowlist that records each artist's
   taping and hosting policy with sources, for the operator to rule on.

## Non-goals (phase 1)

- phish.net show ratings as a winnow signal. Wanted later (operator), not now.
- The profile pin-plus-exclude enhancement (the excluded-artists backlog). Not
  a prerequisite: allowlisted artists reach unpinned profiles through ordinary
  discovery.
- Admitting any non-allowlisted taperssection artist.
- An artist that later gains its own LMA collection. Its taperssection
  recordings would key differently from its LMA ones and could duplicate shows.
  This is a known limitation: write it down, don't solve it.
- Audio-quality analysis of tapes.

## Anti-goals

- Any behaviour change for an existing LMA artist (see Stakes).
- Shipping a tape whose lineage the artist's policy forbids, or an unclassified
  tape for an artist with a restricted policy, without a hold.

## The research round

**The research round is separate from the build** (my call): code proceeds
without waiting for it, and the build never writes the operator's
`~/.llama/config.toml`. It commits the research record plus suggested
allowlist entries; the operator pastes the ones they approve. Candidates are the
survey's recognisable artists; the operator trims the list. The sketch's Phish
and Garcia values are illustrative, except Phish audience-only, which is the
operator's ruling.

The research round runs before the allowlist is used in anger. It is subagent
web research: Sonnet workers per artist, with Opus synthesis and verification
per the operator's delegation rules. For each candidate artist it records:

- the taping policy: audience allowed? soundboard, matrix or pre-FM allowed?
- the hosting and streaming policy: may recordings be served publicly on the
  web? Has the band asked archive.org or others to take recordings down?
- explicit exclusions: official releases (LivePhish, nugs and the like),
  webcasts and stream rips, specific tours or eras;
- sources (URLs) and dates for each claim, and what could not be confirmed.

**Taping-friendly and hosting-friendly are different claims.** Findings so far
(Sonnet research, 2026-11-08) show why:

- An LMA collection needs the artist's explicit written permission to host
  (archive.org help page). A taperssection artist by definition has no such
  collection.
- archive.org removed DMB, Dave Matthews solo and Dave & Tim shows on 2003-01-17
  at band management's request, days after DMB's policy began forbidding public
  download or streaming (nancies.org).
- A 2009 Glide piece reports that Phish management does not allow the LMA to
  host Phish or side-band audience tapes. Unconfirmed officially.
- Nothing was found about a JGB LMA collection or a Garcia estate takedown.
- Taper's Section's permission basis is unsourced. The inference is that
  uploaders assert the artist is taper-friendly.

**The operator decides per artist** from the record. The operator has already
said Phish and Garcia stay in scope: Phish "allows (or at least tolerates) the
open serving of their shows on the web". **Phish ships audience tapes only.**
That is the operator's choice, not a ban from the policy, even though some
Phish soundboards circulate openly. The research record is evidence, not an
automatic exclusion.

**Output:** a committed research record (one markdown document with a section
per artist, sources inline) plus the allowlist entries it justifies. The
record's file name must not start with REPORT, SUMMARY, FINDINGS or ANALYSIS
(subagent write guard).

## The allowlist

Lives in `config.toml`, the one hand-edited llama file. Sketch:

```toml
[[taperssection.artists]]
name = "Phish"                     # display name; what the LLM matcher and operator see
creators = ["Phish"]               # exact uploader creator strings this entry covers
lineages = ["aud"]                 # lineage classes allowed to ship
exclude = ["webcast", "livephish"] # tape-level ban terms (builder: decide the matching form)
note = "audience only by operator choice; see research record"

[[taperssection.artists]]
name = "Jerry Garcia"
creators = ["Jerry Garcia", "Jerry Garcia Band"]
lineages = ["aud", "sbd", "matrix"]
jerrybase = "Jerry Garcia Band"    # optional: jerrybase artist key for set-break evidence
active_until = "1995-08-09"        # optional active bounds (active_from too)
```

Decided:

- **One entry can cover several creator spellings** (my call). The `creator`
  field is free text. "Trey Anastasio" vs "Trey Anastasio Band" is the
  operator's call per entry: one entry or two.
- **Garcia is one entry** (my call): every Garcia band the uploaders file under
  "Jerry Garcia" (JGB, Legion of Mary, Garcia/Grisman, acoustic) ships as
  "Jerry Garcia". Only the dates jerrybase has JGB rows for get event evidence.
- **Optional `active_from`/`active_until` dates** (my call, prompted by the
  operator's misattribution example below): a recording dated outside them is
  never a candidate, deterministically.
- **The config shape is strict** like the rest of `config.toml` (an unknown key
  is an error).
- An empty or absent allowlist reproduces today exactly.

Left to the builder: exact key names; how creator matching normalizes (case,
leading "The", punctuation; the survey normalized those); how `exclude` terms
match (identifier, title, `source`, `lineage`, `description`).

## Identity

Each allowlisted artist gets a **synthetic collection key** that is stable,
derived only from `name`, safe for `slugify` and show directory names, and
guaranteed never to equal a real LMA collection identifier. It flows wherever
`Candidate.collection` flows today: performance ids (`<key>/<date>[/eN]`), show
slugs, the ledger's performance identity, `Criteria.artists`, the artist index
and manifests. The exact form is the builder's call (a prefix such as
`taperssection-`, or a suffix). Show slugs are user-visible, so prefer
readable.

**Renaming an entry's `name` changes its key**, which orphans existing shows the
same way an LMA collection rename would. Document it. No migration.

Downstream consumers that key on the artist must keep working: emcee's
`[assign.artists]` rules (loose artist-name matching), transmitter's rotation
by profile, and `llama status`/`show` display. The builder must check each and
decide which field carries the human-readable artist name. Manifests are the
only llama/emcee contract, and emcee must not import llama.

## Artist index and discovery

- `artist_index.build_index` gains a pass producing one entry per allowlisted
  artist: identifier = synthetic key, title = `name`, recordings and year
  coverage aggregated from taperssection items matching its creators, and
  downloads summed over those items. Whether LMA collection `downloads` and
  summed item downloads are comparable is unverified. It doesn't matter for the
  next point.
- **Allowlisted artists bypass the discovery floor** (`filter_artists`'
  recordings-or-downloads test, my call): being on the list is the operator's
  curation. Small entries like NIN (5 items) would otherwise vanish.
- **Cache invalidation:** the index is cached for 30 days. An allowlist edit
  must be visible on the next run without waiting for a TTL or a manual
  `--refresh`. The builder decides how (for example, fold allowlisted entries in
  at load time rather than at build time, or key the cache on the allowlist).
- The `find_artists` prompt currently says "LMA". It must not exclude
  allowlisted artists. Wording change only.

## Query mode (`interpret`)

`interpret`'s prompt has the LLM invent an LMA collection name in CamelCase
(`"Phish"` → `collection: "Phish"`), which would search an empty LMA
collection. A named allowlisted artist must resolve to its synthetic key. The
builder decides how. A deterministic post-interpret mapping from `artist`
against allowlist names and creators is preferred over prompt changes, as more
testable. A named artist that is both an LMA collection and allowlisted cannot
happen while the allowlist holds only artists with no LMA collection. The
builder should still decide which wins and pin it with a test.

## Search and grouping

For a synthetic key, `build_query` produces
`collection:taperssection AND mediatype:audio AND creator:(<the entry's creators>)`
plus the same date clause. Every other key's query is unchanged (the guarded
surface; pin with tests). `group_candidates` then runs as today with the
synthetic key as the collection label.

**jerrybase:** `jerrybase.lookup(collection, date)` and `is_family_artist` key
on the collection. An entry's optional `jerrybase` field maps its synthetic key
to the jerrybase artist key, so Garcia shows get event evidence (multi-event
dates, set-break anchoring) and Dead vocabulary. Without the field the entry
gets neither. (My call: JGB is in the vendored dataset and is the reason Garcia
is worth doing well.)

Taperssection metadata is thinner than LMA. The sampled item had no venue,
coverage, source or lineage. Expect more venue/city holds and weaker grouping.
That is acceptable: the hold machinery exists for it. Do not loosen any hold
for these artists.

## Winnow: downloads instead of reviews

Today every candidate must clear `min_reviews` (default 3) and
`min_avg_rating` (3.5) before scoring. Almost no taperssection show would pass.
**For allowlisted artists only** (operator: "downloads is probably as good a
signal as we've got"):

- The review and rating floor is not applied.
- Show merit comes from **downloads ranked within the same artist**. A
  downloader is mostly someone who was not at the show, which is the evidence
  the quality philosophy asks for. Existing reviews, where present, still
  count.
- **Downloads enter as evidence to the existing scorer** (operator, 2026-11-09):
  `score_reviews` receives, for an allowlisted show, its download percentile
  alongside whatever reviews exist, and produces the same `quality_score` every
  other show gets, gated by `min_quality_score`. So taperssection and LMA shows
  compete on one scale in mixed profiles under the same
  `artist_cap`/`year_cap`/`count`. The percentile is taken over the artist's
  **whole taperssection catalogue** (from the index aggregation), not the run's
  date-filtered pool. That is stable, and it means something even for a small
  run. An LMA show's scorer input is unchanged (guarded surface). The prompt
  wording that explains the percentile renders only when an allowlisted show is
  in the batch.
- **A query naming one specific date skips the merit gate** (operator,
  2026-11-09): `llama get "Phish 1997-11-22"` has already chosen the show.
- **Misattribution check** (operator, 2026-11-09). Uploader details can't be
  trusted: `gd2015-05-14` is filed as "Grateful Dead" but is a 2015 Garcia
  tribute. Besides the `active_*` dates, the same scorer call answers, for each
  allowlisted show, whether the recording is the named artist or a
  tribute/cover/mislabel, reading the description and title it is already
  given. A suspect answer does not drop the show. It holds it with a review
  flag naming the reason, with an overrule kind, so the adjudicator and triage
  can clear it. The builder decides the output-schema field.
- Research and vet run as today. Phish and Garcia have plenty of online writing
  for research to draw on.

## Select-recording and the per-tape policy filter

Recording scoring is unchanged: lineage, completeness, format, title coverage,
ratings, downloads. Among siblings, downloads becomes the main tiebreaker by
default, because reviews are absent.

Policy filter, per recording of an allowlisted artist:

- **Lineage forbidden by the entry** (e.g. `sbd` for Phish): not a candidate.
- **Matches an `exclude` term:** not a candidate.
- **Lineage `unknown` for an entry whose `lineages` is restricted** (doesn't
  include every class): stays a candidate. **If it is the recording selected,
  the show is held for review** with a review flag naming the reason. A show
  with a classified, allowed sibling simply selects among those normally (my
  call on the detail; operator: "for now let's say held"). The hold flag needs
  an overrule kind so `fix --overrule` and the adjudicator can clear it the
  usual way.
- Entry allows every lineage: no filtering beyond `exclude`.
- A show whose every recording is filtered out yields no show, recorded the way
  winnow and select record other rejections.

`lineage_class` reads identifier, `lineage`, `source` and `title`.
Taperssection identifiers are free-form, so expect many `unknown`s. **Hold-rate
gate** (operator, 2026-11-09): an early task measures, on a sample of real
Phish items (at least 100 show dates, stratified by era), how many shows would
hold for `unknown` lineage. If more than 25% would, extending what
`lineage_class` reads (for example `description`) becomes a required task,
**for allowlisted artists only**, with tests showing LMA selection does not
move. Below 25%, the adjudicator and `fix --overrule` clear the holds and the
extension is optional.

## Delivery formats

The sampled items carry `24bit Flac` and `VBR MP3` derivatives, as LMA items
do. The builder should confirm the junk filter's dominant-format logic and
`FORMAT_BY_AUDIO` handle a sample of real taperssection items, including the
uploader conventions (PNG and spectrogram files appeared beside the audio).
Capture at least one Phish and one Garcia item as test fixtures
(`scripts/capture_fixture.py`).

## Profiles

New `phish` and `garcia` profiles are operator work after the build. Per the
operator's prior concern ("we'll see how it looks in practice"), expect their
first runs with `human_gate = true`. Existing profiles need no change: they
reach allowlisted artists through discovery.

## Success

- A Phish profile run and a Garcia profile run each produce at least one
  correct, airable, delivered show from taperssection. For Phish it is an
  audience tape.
- An unpinned `southern` or `indie` discovery run can match an allowlisted
  artist (Warren Haynes, Sonic Youth, Pearl Jam).
- `llama get "Phish 1997-11-22"` resolves and finds candidates.
- With the allowlist empty, the whole suite and a replay of today's library are
  unchanged.

## Left to the builder

Key names and shapes; the synthetic-key form; creator normalization; exclude
matching; the downloads-in-winnow mechanism; index cache invalidation; the hold
flag's wording and overrule kind; which manifest field carries the display
name. Each needs its rationale recorded in the plan.
