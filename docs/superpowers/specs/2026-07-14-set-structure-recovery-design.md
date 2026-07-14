# Set-Structure Recovery — Consensus Setlists, setlist.fm, and the Long-Flat-Show Guard

Design spec approved 2026-07-14. Extends the base design
(`2026-07-14-llama-design.md`); where they conflict, this spec wins for
set/segue structure handling.

## Purpose

The first full `find` run (gratefuldead-1974-02-24) shipped a 27-track,
two-set-plus-encore show with every track marked set 1 and `set_breaks: []`.
Root cause: set structure was derived solely from the chosen recording's own
description, which for that item is a single unbroken line with no set
markers; 11 of the 12 sibling recordings of the same performance parse at high
confidence with full 1/2/encore structure, but the pipeline never looked at
them. Nothing downstream questioned a three-hour single-set show.

Set structure, song order, and segues are properties of the **performance**,
not of any one recording. This design makes gather build a canonical
performance-level setlist from all available sources, aligns it onto the
chosen recording's audio tracks, and flags implausibly flat results.

## Decisions made during brainstorming

- **Always build consensus** — every gather constructs the canonical setlist
  from all sources, not only as a repair path when the chosen parse fails.
- **setlist.fm is optional** — the pipeline must operate best-effort with no
  API key; when a key is configured, setlist.fm is always queried and
  participates in the consensus.
- **Ranked pick-best, not voting** — LMA descriptions of the same show are
  often copies of one another, so majority voting rewards the most-copied
  text. Sources are ranked and the best single parse wins.
- **Ordered alignment with LLM fallback** — deterministic position-aware
  alignment first; a new LLM touchpoint recovers messy cases.
- **Guard on duration OR track count** — zero set breaks plus a long show is
  suspicious regardless of which arm detects "long".
- **Segues blended from LMA** — taper descriptions carry segue notation that
  setlist.fm generally lacks; the boundary winner does not overwrite it.
- **Approach A** — consensus and alignment live inside the gather stage as
  new pure-logic modules (`structure.py`) plus a `setlistfm.py` client; no
  new pipeline stage. A provenance block in `show.json` records which source
  won and how alignment went, recovering the inspectability a dedicated
  stage would have offered.

## Gather data flow

```
run_gather(show_ws, ia, provider, candidate, identifier, setlistfm=None, ...)
  1. metadata(identifier) → kept files                       (unchanged)
  2. build canonical setlist:
       a. parse_setlist() over EVERY recording description in
          candidate.recordings (ia.metadata is disk-cached; anything
          winnow/select-recording touched is already local)
       b. if setlistfm client present: fetch (artist, date) setlist,
          venue-checked, converted to ParsedSetlist
       c. ranked pick-best:
            setlist.fm > best LMA parse > chosen recording's parse
          LMA parses ranked by: confidence (high>medium>low), then
          multi-set over single-set, then item count closest to the
          kept-file count
       d. segue blend: winner supplies sets/order; segue flags overlaid
          from the best LMA parse by position-matched normalized title
       e. LLM extract_setlist fallback only if NO source yields a usable
          parse — run against the longest non-empty description across
          the performance's recordings, not just the chosen recording's
  3. resolve_titles(kept, canonical)                          (cascade unchanged:
       tags → setlist → sibling → filename/unresolved)
  4. align structure onto tracks:
       a. ordered, position-aware alignment on normalized titles
       b. coverage = aligned / total; if coverage < threshold, LLM
          touchpoint align_structure maps files → setlist items
       c. unaligned tracks inherit the previous track's set
  5. guard: zero set breaks AND (duration ≥ guard_min_minutes OR
     track count ≥ guard_min_tracks) → needs-review flag
  6. Show written with structure provenance block
```

Everything is deterministic except steps 2e and 4b, which are existing-style
LLM touchpoints at the stage boundary. setlist.fm errors can never fail
gather; they degrade to LMA-only operation.

## Components

### `src/llama/setlistfm.py` — new client

Mirrors `IAClient`: httpx, 1 req/sec throttle, retry with exponential
backoff, JSON responses cached to `cache/slfm_<sha1(artist|date)>.json` so
repeat runs are offline.

- `SetlistFMClient(cache_dir, api_key, client=None, max_retries=3, ...)`
- `setlist(artist: str, date: str) -> dict | None` — calls
  `GET /rest/1.0/search/setlists?artistName=…&date=DD-MM-YYYY` with the
  `x-api-key` header. Picks the result whose venue/city best matches the
  candidate (normalized substring match). Returns raw setlist JSON, or
  `None` on: no match, ambiguous match, empty/stub setlist, or any error
  (logged as a warning, never raised past the client).
- Constructed in `cli.py` alongside `IAClient` only when a key is
  configured; otherwise `None` flows through the pipeline.

### `src/llama/structure.py` — new module (pure logic, no I/O)

- `from_setlistfm(raw: dict) -> ParsedSetlist` — converts setlist.fm
  `sets.set[]` (with `encore` markers) to `ParsedSetlist`,
  `confidence="high"`, `segue=False` throughout. Fewer than 5 songs is
  treated as no-result so a stub entry cannot out-rank a rich LMA parse.
- `rank_parses(parses: list[SourcedParse]) -> SourcedParse | None` — the
  ranked pick-best.
- `blend_segues(winner: ParsedSetlist, best_lma: ParsedSetlist) -> ParsedSetlist`
  — overlays segue flags by in-order normalized-title occurrence matching
  (the same matching rule `align` uses, so repeated songs pair with the
  right occurrence); unmatched titles keep `segue=False`.
- `align(tracks: list[Track], canonical: ParsedSetlist) -> AlignResult` —
  ordered position-aware aligner (two-pointer with lookahead, LCS-flavored):
  repeated songs map to their in-order occurrences; skips tolerated on both
  sides (missing encore on tape; tuning/soundcheck extras on the recording).
  Alignment is driven by the recording's track order; the canonical setlist
  supplies boundaries only. Returns per-track set/segue assignments,
  coverage, unaligned indices, and conflicts.
- `structure_guard(tracks, set_breaks, min_minutes, min_tracks) -> str | None`
  — returns the review-flag string or `None`. Runs on the final structure.
  Duration is the sum of kept tracks' `duration_sec`; missing per-file
  durations blind only the duration arm; the track-count arm still works.

### Config (`config.py`)

```toml
[setlistfm]
api_key = "..."        # optional; SETLISTFM_API_KEY env var overrides

[structure]
guard_min_minutes = 100
guard_min_tracks = 16
align_coverage_threshold = 0.8
```

`Config` gains `setlistfm: SetlistFMConfig` and `structure: StructureConfig`
sub-models with those defaults.

### New LLM touchpoint: `align_structure` (7th named task)

- Prompt template `prompts/align_structure.md`: given the ordered track list
  (filenames, tag titles, durations) and the canonical setlist, return
  per-track `{set, segue, matched_title}`.
- Output schema `AlignedStructure`; invoked via `run_json_task`; default
  tier medium, overridable via `[llm.align_structure]`; `fake` backend
  serves a canned response for tests.

### Model changes (`models.py`)

- `Show.structure: StructureInfo | None` — provenance:
  `{source: "setlist.fm" | "lma:<identifier>" | "chosen" | "llm",
    alignment: "deterministic" | "llm", coverage: float,
    conflicts: list[str]}`
- New models: `SourcedParse`, `AlignResult`, `StructureInfo`,
  `AlignedStructure`.

### Changed modules

- `titles.py` — `resolve_titles` keeps the title cascade but stops
  assigning sets/segues (returns placeholder `set="1"`, `segue=False`;
  `structure.align` stamps the real values). This also removes the
  `by_norm` dict that silently collapsed duplicate song names.
  `set_breaks()` unchanged.
- `stages/gather.py` — orchestration per the data flow; signature gains
  optional `setlistfm` param.
- `manifest.py` — unchanged; it already reads sets/breaks from `Show`.

## Error handling

setlist.fm (all degrade to LMA-only, never fail gather):

- No key → client is `None`; normal operation, no warning noise.
- HTTP error / rate limit / timeout after retries → warn, `None`.
- No result for (artist, date); or results but none venue-matches when the
  candidate has a venue → `None`. If the candidate lacks a venue, accept a
  sole result for the date and reject multiple (a wrong-venue match is
  worse than no match).
- Stub setlists (< 5 songs) → treated as no-result.
- Artist-name mismatch → one retry with a cleaned
  (`normalize_song`-style) name, then `None`.

LMA siblings:

- Sibling metadata unfetchable (offline, error) → skip that sibling,
  record in `structure.conflicts`.
- All siblings weak/single-set → pick-best falls through to the chosen
  recording's parse; the guard is the safety net.
- Duplicate copy-paste descriptions are harmless under pick-best.

Alignment:

- Coverage ≥ threshold → deterministic result stands; unaligned tracks
  inherit the previous track's set (first track defaults to set 1),
  `segue=False`.
- Coverage < threshold → run `align_structure`. If the LLM output fails
  schema validation or still leaves coverage below threshold → keep the
  deterministic result AND flag `"low-confidence structure alignment"`
  (needs-review). LLM errors never hard-fail the stage.
- Canonical songs missing from the recording → skipped on the canonical
  side. Recording-only tracks (tuning, soundcheck) inherit neighboring
  sets; heavy cases surface via the coverage metric.
- Order disagreement between winner and recording → recording order wins;
  unplaceable songs recorded in `structure.conflicts`.

Guard: runs on final structure. Short single-set shows pass silently; a
long show that survived all recovery as single-set is flagged
`"single-set structure for a long show"` → `needs_review=True`, skipped by
`--auto` runs, surfaced by `llama review`.

## Testing strategy

All offline and deterministic (project convention).

Fixtures:

- Capture gd74-02-24 windsor item (the structureless regression case) plus
  one high-confidence sibling (`gd1974-02-24.sbd.miller.116902.flac16`) via
  `scripts/capture_fixture.py` — second canonical fixture set alongside
  gd73-06-10.
- One captured real setlist.fm response for 1974-02-24 plus a no-match
  response, checked in as JSON; `scripts/capture_fixture.py` gains a
  `--setlistfm` flag.

Unit tests (`tests/test_structure.py`): `from_setlistfm` conversion and
stub rejection; `rank_parses` ordering rules; `blend_segues` position
matching; `align` on exact match, duplicate songs, split/merged tracks,
extras, coverage math, first-track default; `structure_guard` long+flat,
short single-set, multi-set, missing durations, config thresholds.

Client tests (`tests/test_setlistfm.py`): mocked httpx transport — venue
disambiguation, no-key construction path, HTTP 500 → warn + `None`, cache
hit avoids a second request.

Pipeline tests: the regression test (windsor + sibling fixtures, no
setlist.fm → sets 1/2/encore from sibling, non-empty `set_breaks`,
`structure.source == "lma:…"`); with setlist.fm fixture →
`structure.source == "setlist.fm"` with LMA segues; all-sources-weak long
show → guard flag; low coverage → fake `align_structure` used
(`structure.alignment == "llm"`); fake returning garbage → deterministic
fallback + review flag; existing gd73-06-10 tests unchanged (healthy items
behave as before).

Live (`-m live`, opt-in): one real setlist.fm call for 1974-02-24, skipped
unless `SETLISTFM_API_KEY` is set.

## Out of scope

- Re-gathering existing runs (operators re-run with `--force` as needed).
- setlist.fm MBID-based artist resolution (name search suffices for now).
- Voting/merging structure across multiple sources beyond pick-best.
- Using setlist.fm data anywhere outside gather (e.g., research stage).
