# Artist Discovery — Design

**Date:** 2026-07-14
**Status:** Approved design, pending implementation plan
**Extends:** `2026-07-14-llama-design.md` (pipeline stages / search)

## Problem

Queries that name no artist ("a highly rated concert by a well-known
performer in a folk/acoustic style from the 1960s or 70s") interpret to
`collection=null, artist=null`, so search degrades to an unsteered
`mediatype:etree` sweep truncated at 500 arbitrary rows. The style guidance
only influences winnow's review scoring. The LMA has 9,267 artist
collections (verified live), each enumerable with identifier + display title
in one cheap, cacheable API call.

## Design

### New stage: `discover` (`src/llama/stages/discover.py`)

Runs between interpret and search, ONLY when
`criteria.collection is None and criteria.artist is None and criteria.soft_preferences`.
Otherwise the orchestrator skips it entirely (no artifact — absence means
"not applicable").

```python
def run_discover(ws, provider, ia, criteria, *, max_artists: int = 10,
                 force: bool = False) -> list[dict]
```

1. **Enumerate:** `ia.search("collection:etree AND mediatype:collection",
   ["identifier", "title"], rows=10000)` — disk-cached by the existing
   IAClient cache like every other call.
2. **Propose (LLM, one call):** new prompt `propose_artists.md`
   (placeholders: `query`, `soft_preferences`, `date_from`, `date_to`) asks
   for up to 25 artist names matching the style/era brief, ranked
   best-fit-first, drawing on world knowledge — NOT shown the collection
   list. Output schema: new model `ProposedArtists(artists: list[str])`.
   New LLM task key `propose_artists`, default tier `medium`.
3. **Match (deterministic):** normalize proposed names and collection titles
   (lowercase, strip punctuation — same normalization style as `songs.py`);
   a proposed name matches a collection when normalized-equal, or by
   word-set containment — every word of the shorter name appears in the
   longer one (handles "Doc Watson" vs "Doc and Merle Watson", where plain
   substring matching fails) — guarded so containment requires the shorter
   side to have ≥2 words (single-word names like "War" match by equality
   only, to avoid grabbing unrelated titles). A proposed name keeps at most
   its single best match (equality beats containment; first-listed wins
   ties). Order is the LLM's ranking; cap at `max_artists`.
   *(Amended during execution: the original substring rule failed its own
   Doc Watson example; word-set containment with the single-word guard is
   what shipped.)*
4. Write `artists.json` to the run workspace: `[{"identifier", "title"}]`.
   Standard stage discipline: skip-if-exists unless force, atomic write.
   Zero matches: write the empty list, and the CLI reports "none of the
   proposed artists were found on the LMA — try naming an artist or
   broadening the style" and exits cleanly without searching.

Artifact editability is a feature: `artists.json` can be hand-edited and the
run replayed (`llama run <dir>`), the same as every other artifact.

### Search fan-out (`src/llama/stages/search.py`)

`run_search` gains an optional parameter:

```python
def run_search(ws, ia, criteria, artists: list[dict] | None = None,
               rows: int = 500, force: bool = False) -> list[Candidate]
```

When `artists` is provided and non-empty: one query per artist with the same
hard filters but `collection:{identifier}`, `rows` applying per query;
`group_candidates(identifier, docs)` per artist; results concatenated then
sorted by `(date, performance_id)` as today. Progress: one
`log.info("search: %s (%d/%d)", title, i, n)` per artist. When `artists` is
`None` (all current callers), behavior is unchanged. Performance ids become
`{artist-collection}/{date}`, so ledger dedup works per real artist.

### CLI integration (`_execute` in `src/llama/cli.py`)

After criteria are in hand and before `run_search`:

- If the trigger condition holds, call `run_discover`.
- Interactive (not `--auto`): print the numbered artist list
  (`1. Doc Watson`, ...) and prompt
  `Search which artists? (comma-separated, empty = all)` using the existing
  `_parse_ranks` digit-tolerant parsing; prune, rewrite `artists.json` with
  the pruned list.
- `--auto` (cron/profiles): use the list as-is.
- Pass the list to `run_search(..., artists=...)`. Both `find` and
  `profile run` get this automatically since both go through `_execute`.

### Unchanged

Winnow, select-recording, gather, research, synthesize, package: no changes.
Winnow's light-research artist label already falls back to `c.collection`,
which now carries the real per-artist collection identifier.

### Out of scope (documented futures)

- Chunk-scanning all 9,267 titles through the LLM (comprehensive fallback if
  propose-then-match proves too narrow).
- Configurable `max_artists` (constant 10 for now).
- Genre metadata from the collections themselves (LMA doesn't expose
  reliable genre tags).

## Testing

- `tests/test_stage_discover.py`: trigger produces matched, capped,
  LLM-order-preserving `artists.json` (FakeProvider + stub ia returning a
  small collection list); equality-beats-containment and best-single-match
  tie rules (table test on the matcher); zero-match writes empty list;
  skip-if-exists honored (empty FakeProvider on second call).
- `tests/test_stage_search.py`: fan-out test — two artists, per-artist
  queries issued (assert on stub's recorded queries), merged candidates
  carry each artist's collection in their performance ids; `artists=None`
  path asserted unchanged.
- CLI test: interactive prune via stdin (pick artist 2 of 3) rewrites
  `artists.json` and search receives only the pruned artist; `--auto` skips
  the prompt. Zero-match message and clean exit.
- Prompts test table gains `propose_artists` with its four placeholders.

## Docs

README usage section gains the fuzzy-query example with a note about the
interactive artist-confirmation step.
