# Taper's Section allowlist: design

Date: 2026-11-09. Status: draft, awaiting review.

## Review mode and stakes

**Review mode: Opus** (operator, 2026-11-09). The second spec reviewer and the
final branch reviewer are Opus.

**Stakes.** The change is additive: llama gains a second source of artists. No
surface is strict. Nothing deletes, overwrites or migrates user data. The
operator ruled that airing taperssection material from broadly taper-friendly
artists is not a strict surface ("we're pretty under the radar"). Permission
is an operator decision recorded per artist (below), not a hard gate in code. **The guarded surface is no regression for
existing LMA artists**, in two strengths (my call, from the builder check). The
guarantee is behavioural, not byte-level:
- **Empty allowlist: LMA behaviour is identical to today**, and so is every
  LLM prompt's rendered text. Any prompt wording added for this feature renders
  only when the allowlist is non-empty, as does the allowlist's part of
  `replay.config_fingerprint`. Artifacts may gain null-valued new keys, so
  replay digests of re-processed LMA shows can change; that is noise, not a
  regression.
- **Populated allowlist:** each LMA artist's own search query, grouping, winnow
  scoring inputs (including the rendered scorer prompt and payload of an LMA
  batch) and recording selection are unchanged. Discovery's artist mix and a
  mixed profile's shortlist may change **by design**, because allowlisted
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
name = "Phish"                     # display name; the artist everywhere a human or LLM sees one
creators = ["Phish"]               # uploader creator spellings; a doc must match one exactly after normalization
lineages = ["aud"]                 # lineage classes allowed to ship
exclude = ["webcast", "livephish"] # tape-level ban terms (anchored matching, below)
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
- An empty or absent allowlist reproduces today's behaviour (see Stakes).
- **`exclude` matching is anchored**: terms match the identifier, title, the
  `source` field and the description's source lines (defined under Lineage
  classification), never free description text. All three recordings of
  phish1996-11-02 mention "available as a download from LivePhish" in prose.

Left to the builder: exact key names; how creator matching normalizes (case,
leading "The", punctuation; the survey normalized those).

## Identity

Each allowlisted artist gets a **synthetic collection key** that is stable,
derived only from `name`, safe for `slugify` and show directory names, and
guaranteed never to equal a real LMA collection identifier. The key has a
**fixed, recognisable prefix**; the builder picks it, and the index must show
that no LMA identifier carries it. Uniqueness is **slug-level**: the key must
not collide with any LMA collection after `slugify` (which lowercases). The
collision check keys on the prefix and runs where the index is built or loaded,
never at config load. The key flows wherever `Candidate.collection` flows today:
performance ids (`<key>/<date>[/eN]`), show slugs, the ledger's performance
identity, `Criteria.artists`, the artist index and manifests. Show slugs are
user-visible, so prefer a readable prefix.

**Renaming an entry's `name` changes its key**, which orphans existing shows the
same way an LMA collection rename would. Document it. No migration.

**An unknown synthetic key is a hard error.** A pinned roster or stored criteria
naming a key with the synthetic prefix that matches no allowlist entry (for
example after a rename) fails the run with a `LlamaError` naming the key. It
does not fall through to an empty etree search.

**The display name is the artist everywhere a human or LLM sees one.** For an
allowlisted show, `show.artist`, and so the manifest's artist, is the entry's
`name`, not the item's creator. The same name is the artist passed to winnow's
light research, the shortlist display (`cli.py:189`, which today prints
`c.collection` truncated to 18 characters) and the catalog fallbacks
(`catalog.py:309`, `:395`). The builder checks that emcee's `[assign.artists]`
rules (loose artist-name matching) and transmitter's artist separation
(`transmitter/rules.py` compares `piece.artist`) still work with that name, as
do transmitter's rotation by profile and `llama status`/`show` display.
Manifests are the only llama/emcee contract, and emcee must not import llama.

**Gather matches on every spelling.** The setlist.fm lookup uses the entry's
`name`, but gather-internal matching (title cleaning, the artist-item and
banner drops, `cosmetic_strip`, `show_metadata_norms`) uses the item's creator
plus every listed creator and the `name`. Test: a "Jerry Garcia Band - Sugaree"
title is cleaned.

## Artist index and discovery

- `artist_index.build_index` gains a pass producing one entry per allowlisted
  artist: identifier = synthetic key, title = `name`, recordings and year
  coverage aggregated from taperssection items whose normalized creator is
  exactly one of the entry's `creators`, and downloads summed over those items.
  It also stores **raw `downloads` and `addeddate` per item, keyed by show
  date**, for winnow's download measure; rates and percentiles are computed at
  run time. Whether LMA collection `downloads` and summed item downloads are
  comparable is unverified. It doesn't matter for the next point.
- **Allowlisted artists bypass the discovery floor** (`filter_artists`'
  recordings-or-downloads test, my call): being on the list is the operator's
  curation. Small entries like NIN (5 items) would otherwise vanish.
- **Cache:** the allowlisted aggregation is cached separately from the LMA
  index, keyed on the allowlist's content. An edit rebuilds only that part, on
  the next run that needs the index, without waiting for the LMA index's TTL or
  a manual `--refresh`.
- The `find_artists` prompt currently says "LMA". It must not exclude
  allowlisted artists. Wording change only.
- **Discovery reaches dedicated-profile artists, by design.** The `jam`
  profile's query will match Phish, and `dead-family`'s (which names JGB) will
  match Garcia. Until the excluded-artists backlog lands, the workaround is a
  "not Phish" clause in the profile query.

## Query mode (`interpret`)

`interpret`'s prompt has the LLM invent an LMA collection name in CamelCase
(`"Phish"` → `collection: "Phish"`), which would search an empty LMA
collection. A named allowlisted artist must resolve to its synthetic key.
**The mapping is deterministic and exact**: interpret's `artist`/`collection`
maps to a synthetic key only on an exact normalized match with an entry's `name`
or one of its `creators`, never a substring (unlike `resolve_artists`). It is
applied inside `run_interpret`, so all three call sites get it: `_get_query`,
`run resume`'s re-interpret and `profile add`. Test: an LMA tribute-band query
("Jazz Is Phish 2005") is untouched. A named artist that is both an LMA
collection and allowlisted cannot happen while the allowlist holds only artists
with no LMA collection. The builder should still decide which wins and pin it
with a test.

## Search and grouping

For a synthetic key, `build_query` produces
`collection:taperssection AND mediatype:audio AND creator:(<the entry's creators>)`
plus the same date clause. Every other key's query is unchanged (the guarded
surface; pin with tests). **The `creator:(...)` clause is only a prefilter.**
archive.org's `creator:"X"` is a phrase/token match and returns tribute acts
such as "Vitalogy: Pearl Jam Tribute", "Jerry Garcia Band Cover Band" and
"Tribute - A Celebration Of The Allman Brothers Band". For synthetic keys,
search adds `creator`, `addeddate`, `source` and `lineage` to the scrape fields
(`description` is already there), and keeps a doc only when its normalized
creator is exactly one of the entry's `creators`; the index aggregation applies
the same test. Test: search and the index fed tribute-band docs keep none of
them. `group_candidates` then runs as today with the synthetic key as the
collection label.

**Date cross-check.** For allowlisted items only, when a date parsed from the
identifier or title disagrees with `date`, the recording is dropped from that
date (not reassigned) and logged. Uploader typos (`Phish2027-07-27`) simply
drop. Measured on Phish: 168 items on 137 of 1,882 dates; 73 are the only tape
on their filed date. The drop count is reported at the lineage checkpoint.

**jerrybase:** lookups do not all key on the same field. Grouping
(`grouping.py:131`) and winnow (`winnow.py:41`) use the collection. Gather
(`stages/gather.py:1866`, and the Dead vocabulary at `:1399`), the title
proposal (`cli.py:3637`) and the adjudicator bundle (`adjudicator/bundle.py:228`)
use `show.artist` or the creator. **Every jerrybase `lookup` and
`is_family_artist` call resolves through one helper** that maps an allowlisted
key or display name to the entry's optional `jerrybase` value, so Garcia shows
get event evidence (multi-event dates, set-break anchoring) and Dead vocabulary.
Without the field the entry gets neither. Test: a Garcia `/e1` candidate gets
its event in gather. (My call: JGB is in the vendored dataset and is the reason
Garcia is worth doing well.)

Taperssection metadata is thinner than LMA. The sampled item had no venue,
coverage, source or lineage, and grouping will be weaker. Do not loosen any hold
for these artists.

**Venue from the title.** Taperssection items rarely fill `venue` (1 of 300
sampled Phish items) but put it in the title ("Phish - 1999-07-12 - Tweeter
Center - Mansfield, MA", "Phish Live at The Centrum on …", "… @ Old Waldorf,
SF"). For allowlisted items only, venue and city parsed from title patterns are
the candidate-level fallback when the recording vote is empty. They are never
written into per-recording `venue`/`coverage`, so they cannot feed
`two_venue_signature`, the city-conflict hold or the jerrybase venue check. The
fixture task checks the patterns' precision. A venue still null raises no hold:
the show ships "venue unknown", as today.

**Per-set and partial items are a known limitation.** 336 of 11,134 Phish
identifiers carry set, disc or partial tokens. Grouping makes them siblings, and
select's completeness is relative. The fixture task checks whether an existing
hold catches a set-only date. If none does, it is recorded as a known
limitation, with no new mechanism.

## Winnow: age-adjusted downloads instead of reviews

Today every candidate must clear `min_reviews` (default 3) and
`min_avg_rating` (3.5) before scoring. Almost no taperssection show would pass.
**For allowlisted artists only** (operator: "downloads is probably as good a
signal as we've got"):

- The review and rating floor is not applied.
- **Show merit comes from downloads per day since `addeddate`** (operator,
  2026-11-09). Raw downloads mostly measure upload age. Measured on Phish
  (median downloads by upload year): 2024, 336 (541 items); 2025, 166 (3,723
  items); 2026, 40 (6,870 items). Among same-year uploads, show era barely moves
  the median. A "show" here is a date. Per show, the measure is its best
  recording's rate, and the show is ranked against the artist's **whole
  taperssection catalogue** on that per-show measure (from the index store), not
  the run's date-filtered pool. That is stable, and it means something even for
  a small run. A downloader is mostly someone who was not at the show, which is
  the evidence the quality philosophy asks for. Existing reviews, where present,
  still count. The operator will judge the signal in practice ("we'll see how
  helpful a signal it is").
- **The download-counter lag.** archive.org reports `downloads = 0` for about
  the first 45-60 days (Phish, at zero: 1,077 of 1,077 items aged 0-44 days;
  271 of 635 at 45-59; none at 60+). So an item younger than 75 days carries
  **no download evidence** and is left out of the catalogue distribution. A show
  with no evidence-bearing recording goes to the scorer without a percentile,
  and the prompt's baseline for it is below `min_quality_score`: it waits until
  its counters catch up. This defers the newest tour.
- **The pre-fetch sample and tie-break use the same measure.** The
  `max_metadata_fetch` sample is split between LMA and allowlisted survivors in
  proportion to their survivor counts, each sorted by its own key, then
  `cap_across_artists` runs as today. Allowlisted candidates sort by reviews
  where present, then by the download measure, within their own share. LMA
  ordering is unchanged (test). Test: a mixed pool larger than
  `max_metadata_fetch` samples both sources.
- **Downloads enter as evidence to the existing scorer** (operator, 2026-11-09):
  `score_reviews` receives, for an allowlisted show, its download percentile
  alongside whatever reviews exist, and produces the same `quality_score` every
  other show gets, gated by `min_quality_score`. So taperssection and LMA shows
  compete on one scale in mixed profiles under the same
  `artist_cap`/`year_cap`/`count`.
- **Allowlisted shows are scored in batches of their own**, so an LMA batch
  renders exactly today's prompt and payload. Test: rendered-prompt equality
  for an LMA batch with a populated allowlist.
- **Scorer payload and calibration.** An allowlisted show's payload entry adds
  every recording's `creator`, `title` and a short `description`. The prompt
  gives an explicit baseline mapping from download percentile to a 0-10 score
  when a show has no reviews; reviews, where present, adjust it. The plan includes an early measurement:
  score about 20 Phish shows and check the spread against `min_quality_score`
  before relying on it.
- **A query naming one specific date skips the merit gate** (operator,
  2026-11-09): `llama get "Phish 1997-11-22"` has already chosen the show. This
  applies to allowlisted artists only, when `date_from == date_to`. It skips the
  review and rating floors and `min_quality_score` only (so a show inside the
  download lag is reachable this way). The scorer still runs, so the
  misattribution check still applies.
- **Misattribution check** (operator, 2026-11-09). Uploader details can't be
  trusted: `gd2015-05-14` is filed as "Grateful Dead" but is a 2015 Garcia
  tribute. Besides the `active_*` dates, the same scorer call answers, for each
  allowlisted show, whether it is the named artist or a tribute/cover/mislabel,
  reading every recording in its payload. The verdict is show-level: any
  suspect recording holds the show (never drops it) with a review flag naming
  the reason (see Holds). The builder decides the output-schema field.
- **Policy pre-filter.** Before winnow, recordings whose lineage class (the
  shared rule under Lineage classification) is forbidden by the entry, or which
  match an `exclude` term, are dropped, judged from search-time fields. A show
  with no remaining recording is dropped there, so it never spends a shortlist
  slot or research. Select keeps the same filter as the final check.
- Research and vet run as today. Phish and Garcia have plenty of online writing
  for research to draw on.

## Select-recording and the per-tape policy filter

Recording scoring is unchanged: lineage, completeness, format, title coverage,
ratings, downloads. Among siblings, downloads becomes the main tiebreaker by
default, because reviews are absent. For allowlisted siblings, `downloads_norm`
uses the per-day rate (with the same 75-day rule), not raw downloads.

Policy filter, per recording of an allowlisted artist:

- **Lineage forbidden by the entry** (e.g. `sbd` for Phish): not a candidate.
- **Matches an `exclude` term:** not a candidate.
- **Lineage `unknown` for an entry whose `lineages` is restricted** (doesn't
  include every class): excluded from select whenever a classified, allowed
  sibling remains. It competes only when none does, and then **a selected
  unknown holds the show for review** with a review flag naming the reason. A
  pin (operator or adjudicator) to an unknown recording also holds (my call on
  the detail; operator: "for now let's say held").
- Entry allows every lineage: no filtering beyond `exclude`.
- **Filtered recordings never appear in selection `scores`.** A recording pin
  (`overrides.recording`, including an adjudicator `switch_recording`) naming a
  forbidden or excluded recording raises `LlamaError` for that show (a per-show
  failure), never ships. Test through the adjudicator's switch path.
- **No silent rejection.** The winnow pre-filter means select normally never
  sees an empty set. If it does, select raises `LlamaError` (a per-show
  failure), never `ValueError` from `max()` on an empty set.

**Lineage classification for allowlisted artists** (operator, 2026-11-09).
`lineage_class` reads identifier, `lineage`, `source` and `title`. Measured
under it, 1,502 of 1,882 Phish dates (80%) would hold unknown under aud-only,
190 ship aud and 190 have no allowed tape. Phish items describe sources as mic
chains ("Schoeps CMC6/MK4 > 744T", "B&K 4011 (FOB)"). So, for allowlisted
entries only, one shared function, used by both the winnow pre-filter and
select, classifies by a short stated rule. LMA classification is unchanged
(test).

- It reads the identifier, the title, the `source` and `lineage` fields, and
  the description's **source lines** only (lines beginning `Source`, `Src`,
  `Lineage` or `Transfer`), never free description prose.
- **A source marker wins over gear:** sbd/soundboard/board/patch, matrix/mtx,
  FM/pre-FM, webcast/stream in those fields gives that class. Exception: "aud
  matrix" or "audience matrix" with no other source marker reads as aud.
- Otherwise a microphone model or a position word (FOB, OTS, DFC, taper
  section, "aud", "audience") gives aud.
- **Deck, recorder and transfer gear** (DAT, Tascam, Sony, 744T, Nakamichi deck
  models) **never counts as aud evidence.**
- Anything else is unknown. Known limitation: a source line that names no
  source class and no microphone stays unknown.

Acceptance cases (expected class in brackets):

- `Source: Schoeps CMC6/MK4 > 744T` [aud]; `Source: SBD > DAT` [sbd]
- `Source: FM->DAT->CD` [fm, so non-aud]
- `Location: OTS (right of SBD)` + `Source: DPA 4061 > R-09` [aud; not a source line]
- `Source: AKG 480 AUD Matrix` [aud]
- `Source: SBD/AUD matrix (Schoeps)` [matrix; the marker beats gear]
- prose `This show was webcast live` + `Source: Neumann AK43 > LC3` [aud; prose ignored]
- `Transfer: DAT (patch master)` and nothing else [sbd; patch on a source line]
- `Source: DAT master` only [unknown; a deck is not evidence]

**Checkpoint: the operator rules**, with the rule measured on the Phish
catalogue for **coverage** (share of unknown dates newly classified) and
**precision** (a hand-labelled sample of about 50 dates: false-aud and
false-non-aud counts), plus the date cross-check's drop count:

- (a) if the vast majority of unknown dates gain positive evidence,
  still-unknown tapes hold;
- (b) if only a minority do (the likely case), for an allowlisted artist the
  absence of any sbd, matrix, FM, pre-FM or webcast marker in the same fields
  (never free description text) reads as aud.

## Holds

- **Carriers.** `compute_gather` reads only `overrides.json` from the show
  workspace, and replay passes it only `prov.candidate` and the stored
  identifier (`replay.py:619-630`). So both verdicts live in `provenance.json`
  (misattribution on the winnow assessment; select writes unknown-lineage there
  and in `selection.json`), are passed to `compute_gather` as explicit
  arguments, and replay's `compute_legs` sources them from provenance, already
  in `input_digests`. Each flag gets a `replay.py` `_FAMILIES` entry. Test: a
  replayed held unknown-lineage show, and a held misattribution show, each keeps
  its flag.
- **Overrule kinds.** Each flag gets an `overrules.py` `_PATTERNS` kind, so
  `fix --overrule`, triage and the adjudicator clear it the usual way.
- **Adjudicator bars** (added to `OVERRULE_BAR`): unknown-lineage is `never`
  (operator-only clear, because no adjudicator evidence kind can establish
  lineage); misattribution is `medium`.

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
first runs with `human_gate = true`. Existing profiles need no change to reach
allowlisted artists through discovery; `jam` and `dead-family` may take the
"not Phish"-style clause (see Artist index and discovery).

## Unverified premises

- Taper's Section's permission basis and each artist's hosting stance: the
  research round.
- The scorer's spread with zero reviews, and its consistency for the same
  shows in different batch mixes: the early ~20-show Phish measurement
  (Winnow).
- The scrape API returns `creator`, `addeddate`, `source`, `lineage` for
  `mediatype:audio`: one scrape call.
- setlist.fm's name for JGB ("Jerry Garcia" or "Jerry Garcia Band"): test one
  date; if needed, add an optional per-entry `setlistfm` name.
- JGB jerrybase rows misfiring on non-JGB "Jerry Garcia" acts (Legion of Mary,
  acoustic): count on the Garcia fixture.
- emcee `[assign.artists]` with "Phish" and "Jerry Garcia": run emcee's matcher
  over the operator config.
- Date reliability for other allowlisted artists: re-run the date cross-check
  per artist.
- The junk filter and `FORMAT_BY_AUDIO` on taperssection file sets: the fixture
  task.
- `setlist.py` on `<div>`/`<p>` HTML descriptions: parse one captured Phish
  description.
- `year` present on taperssection items: verified (11,132 of 11,134 Phish
  items).

## Success

- A Phish profile run and a Garcia profile run each produce at least one
  correct, airable, delivered show from taperssection. For Phish it is an
  audience tape.
- An unpinned `southern` or `indie` discovery run can match an allowlisted
  artist (Warren Haynes, Sonic Youth, Pearl Jam).
- `llama get "Phish 1997-11-22"` resolves and finds candidates.
- With the allowlist empty, the whole suite passes unchanged and a replay of
  today's library shows no behavioural change (digest churn from null-valued
  new keys aside; see Stakes).

## Left to the builder

Key names and shapes; the synthetic-key prefix; creator normalization; the
title venue patterns; where the download store lives; the microphone-model and
position-word lexicon; the hold flags' wording and overrule kind names; the
misattribution output-schema field. Each needs its rationale recorded in the
plan.
