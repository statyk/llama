# Interactive Artist Search — Design

**Date:** 2026-07-15
**Status:** Approved design, pending implementation plan
**Extends:** `2026-07-14-llama-design.md` (pipeline / CLI),
supersedes the matching mechanism of `2026-07-14-artist-discovery-design.md`

## Problem

Users want to explore what's actually on the LMA with a natural-language
query — "jangly 80s college rock", "moody post-rock with long
instrumentals" — and get back a ranked list of matching artists **with
stats** (recordings, years covered, downloads), excluding the backyard
bands with 3 recordings and 20 downloads.

The existing `discover` stage half-covers this internally but has the
architecture backwards: the LLM proposes artist names **blind** (world
knowledge only), then a fuzzy matcher reconciles them against the 9,267
LMA collection titles. Consequences: it can propose artists that aren't
on LMA (wasted slots), it can't rank by what's actually available, it
carries no stats and no junk filter, and the word-set containment
matcher is a permanent source of edge cases. It also isn't user-facing.

Survey facts (verified live, 2026-07-14/15):

- ~292,432 recordings across 9,267 artist collections.
- The scrape API (`/services/search/v1/scrape`) returns all collections
  in one request (10k rows/page, cursor pagination) and all items in
  ~30 requests.
- Search docs for collections carry `downloads` but **no item count**;
  recording counts require aggregating an items scrape.
- Downloads thresholds: ≥10k → 3,055 artists; ≥50k → 1,290; ≥100k → 799.
- Downloads alone is a flawed popularity proxy (Trail of Dead: 11M
  downloads, 138 recordings; Robyn Hitchcock: 1.3M, 985), so the junk
  filter needs recording counts too.

## Design

Approach chosen: **inventory-in-context**. One `complete` call per query
sees the entire *filtered* artist inventory with stats and picks from
it. No fuzzy matcher, no hallucinated artists, stats ride along free.
Per-query cost: ~30–40k input tokens (~1,500–2,000 artists × ~20
tokens/line), ~500 output — pennies on sonnet-class, free on
`claude_cli`. Zero archive.org requests at query time.

### 1. Artist index (`src/llama/artist_index.py`)

One on-disk artifact: `<config.root>/cache/artist_index.json`:

```json
{"built_at": "2026-07-15T12:00:00+00:00",
 "artists": [{"identifier": "GratefulDead", "title": "Grateful Dead",
              "recordings": 18271, "downloads": 226766373,
              "year_min": 1965, "year_max": 1995}, ...]}
```

(~1 MB for 9.3k artists.)

**Build** — two passes over the scrape API, both throttled through the
existing `IAClient` rate limiter:

1. **Collections pass** (1 request):
   `collection:etree AND mediatype:collection`,
   fields `identifier,title,downloads` → the artist universe.
2. **Items pass** (~30 requests):
   `collection:etree AND mediatype:etree`, fields
   `identifier,collection,year`, cursor-paginated at 10k/page.
   Aggregate locally: attribute each item to whichever of its
   `collection` values appear in the artist set from pass 1 (items
   carry extras like `etree`/`stream_only`, which are not in that set
   and fall out naturally); per artist, count recordings and track
   min/max year, skipping missing or unparseable years.

`IAClient` gains a `scrape(query, fields)` method implementing cursor
pagination. Scrape pages are **not** disk-cached — the aggregated index
file is the cache.

**Freshness** — `load_or_build(ia, cache_dir, ttl_days=30)`: missing or
older than the TTL → rebuild with a progress line ("building artist
index: ~30 requests, about a minute"). If a rebuild fails mid-scrape
and a stale index exists on disk, keep the stale index and warn with
its age instead of failing.

**Filter** — `filter_artists(artists, min_recordings, min_downloads)`:
keep an artist when `recordings >= min_recordings OR downloads >=
min_downloads`. Defaults **25 / 50,000** (≈1,500–2,000 survivors),
declared in config section `[artists]` (`min_recordings`,
`min_downloads`), overridable per invocation via CLI flags.

### 2. LLM touchpoint: `find_artists`

Replaces `propose_artists`, keeping the named-touchpoint count at nine.
Prompt `prompts/find_artists.md`, placeholders:
`query`, `max_results`, `artist_table`. The table renders one artist
per line: `identifier | title | N recordings | year_min–year_max |
downloads`. The prompt asks for up to `max_results` identifiers ranked
best-fit-first, each with a one-line reason, chosen **only** from the
table.

Output schema (in `models.py`):

```python
class ArtistMatch(BaseModel):
    identifier: str
    reason: str

class ArtistMatches(BaseModel):
    matches: list[ArtistMatch]
```

Task key `find_artists`, default tier `medium`, overridable via the
existing `[llm.<task>]` mechanics. Schema-validation retries and
final-retry tier escalation come free from `run_json_task`.

Post-call, identifiers are joined back against the filtered index
deterministically; any identifier not present is dropped with a logged
warning (hallucination guard).

**Retired:** `prompts/propose_artists.md`, the `ProposedArtists` model,
and `match_artists` (the word-set containment matcher) are deleted,
along with their tests.

### 3. CLI: `llama artists`

```
llama artists "moody post-rock with long instrumentals"
  [--limit 20] [--min-recordings N] [--min-downloads N] [--all]
  [--refresh] [--config PATH]
```

- **With a query:** load/build index → filter → one `find_artists`
  call (`max_results` = `--limit`) → print ranked table: rank, title, recordings, years, downloads
  (humanized: `1.5M`), reason. Display-only; exits after printing.
  Composability is the workflow: copy a name into `llama find` or a
  profile.
- **No query:** no LLM call — print the filtered index sorted by
  recordings descending, capped at `--limit`. Free browsing of what's
  deep on LMA.
- `--all` bypasses the filter; `--refresh` forces an index rebuild.
- Zero matches (including the all-dropped case): friendly message
  suggesting a broader query, lower thresholds, or `--all`; exit 0.
- Empty filtered list (thresholds set absurdly high): explicit message;
  no LLM call.

### 4. Discover-stage rewiring (`src/llama/stages/discover.py`)

`run_discover` keeps its exact contract — trigger condition
(`collection is None and artist is None and soft_preferences`),
`artists.json` artifact of `[{"identifier", "title"}]`, skip-if-exists
unless force, cap `max_artists=10` — but swaps its internals:

- Artist index via the same `load_or_build` (config-default filter
  thresholds).
- One `find_artists` call with a query composed from `criteria.query`,
  soft preferences, and the date range, `max_results=10`. The date
  range doubles as a relevance hint the blind proposer never had: the
  LLM sees each artist's `year_min–year_max` and can avoid artists
  whose recordings miss the requested era.

Downstream is untouched: the interactive prune prompt in `_execute`,
the search fan-out, ledger dedup, winnow onward — no changes.

Behavioral note: discover now auto-builds the index on the first
fuzzy-query run — a one-time ~1-minute pause inside a pipeline that
already takes minutes, logged clearly.

### 5. Error handling

- **Scrape failure mid-build:** stale index on disk → keep it + warn.
  No index at all → clean error naming the failing request;
  `llama artists` exits 1, discover raises like any stage failure.
- **Unknown identifiers from the LLM:** dropped + logged; if all are
  dropped, treated as zero matches (message, exit 0), not an error.
- **Validation retries / tier escalation:** inherited from
  `run_json_task`; nothing new.

### Out of scope (documented futures)

- Select-from-results interactivity (pick artists → launch `find` or
  seed a profile). Display-only for now; profiles have no artist-list
  field yet.
- Genre metadata from collections (LMA doesn't expose reliable tags).
- Embedding-based retrieval to shrink the prompt below the filtered
  list; unnecessary at ~30–40k tokens.
- Guarding `--all` combined with a query: the full 9.3k-artist table is
  ~150–200k input tokens and can exceed a medium-tier context window,
  failing with a provider error rather than a friendly message. Noted at
  final review; add a size warning if it bites in practice.

## Testing

- `tests/test_artist_index.py`: aggregation over a small fake scrape
  (multi-collection items attributed correctly; missing/garbage years
  skipped; downloads joined from the collections pass); filter gate
  table test (OR semantics; `--all` equivalent); TTL logic with a
  monkeypatched clock; mid-build failure keeps the stale index.
- `tests/test_artists_cmd.py` (CLI, FakeProvider): ranked table
  rendering; hallucinated identifier dropped; no-query stats listing
  asserts **no** LLM call; zero-match message and exit 0; empty
  filtered list message.
- `tests/test_stage_discover.py`: rewritten — same trigger and
  artifact-contract assertions; FakeProvider returns identifiers; cap
  at 10; empty-result path writes the empty list and the CLI reports
  and exits cleanly. Matcher table tests deleted with the matcher.
- Prompts test table: `find_artists` with its three placeholders;
  `propose_artists` row removed.
- One opt-in `-m live` test: scrape API shape (single 100-row page;
  asserts cursor and requested fields present).

## Docs

README gains a `llama artists` section with a query example, the
no-query browsing mode, and a note on the one-time index build and the
`[artists]` thresholds.
