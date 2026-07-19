# Jerrybase structure evidence — design

Date: 2026-07-19
Status: approved

## Problem

llama's structural failure modes — misplaced or missing set breaks,
low-confidence alignments, wrong venues, and two-shows-one-tape dates —
currently surface only through weak heuristics (`structure_guard`'s
"long show, zero breaks") or human review. jerrybase.com holds
authoritative per-show structure for the Garcia universe, but offers no
API, no export, and actively blocks scraping (Cloudflare 403 to
non-browser clients; robots.txt disallows AI crawlers).

The deadstream project (github.com/eichblatt/deadstream, GPL-3.0)
commits a jerrybase-derived dataset: `timemachine/metadata/set_breaks.csv`
(~18k rows, ~2 MB). One row per **set** per show: `date, artist,
event_id, venue, city, state, show_set, time, song (the set's closing
song), song_n, isong (global running song index), next_set, Nevents,
ievent, break_length (long|short)`. Coverage: GratefulDead 5,387 sets,
DarkStarOrchestra 4,511, Ratdog 2,231, PhilLeshAndFriends 2,063, Jerry
Garcia Band 1,468, Furthur 738, plus BobWeir, DeadAndCompany, TheDead,
TheOtherOnes.

**What this data is:** ground truth for set count, each set's closing
song, break length, venue/city/state, and multi-event dates.
**What it is not:** a setlist source — it has no per-song rows and can
never build or rank full setlists.

## Decision

Vendor the CSV and use it as a **structure-evidence source**: a tripwire
for bad structure and a narrow deterministic corrector (break
anchoring). Owner intends to license llama GPL, so vendoring GPL-3.0
data is acceptable; vendoring avoids a runtime dependency on a repo we
don't control.

## Data layer

- New subpackage `src/llama/data/` containing `set_breaks.csv` vendored
  **byte-identical** from a pinned deadstream commit, plus `README.md`
  recording provenance: source URL, commit SHA, GPL-3.0, and the
  generation chain (jerrybase → deadstream `setbreaks.q` → this file).
- `scripts/refresh_jerrybase.py`: manual refresh tool (same spirit as
  `capture_fixture.py`). Downloads the CSV from a given/pinned ref,
  prints a row-count and artist-coverage diff against the current copy,
  overwrites the vendored file and reminds the operator to update the
  README commit SHA. No automated tests; never run by the pipeline.
- Packaging: hatchling ships `src/llama/**` data automatically;
  `packaging/llama.spec` adds `collect_data_files("llama.data")`
  alongside the existing prompts line.

## Lookup module — `src/llama/jerrybase.py`

Defensive posture mirrors `setlistfm.py`: nothing raises; absence of
evidence degrades to empty results.

- Pydantic models in `models.py`:
  - `JerrybaseSet(name, closer, break_length, song_count)` — `name` is
    llama's canonical set vocabulary `"1" | "2" | "3" | "encore"`;
    `break_length` is `"long" | "short"`; `song_count: int | None`.
  - `JerrybaseEvent(event_id, venue, city, state, sets)`.
- Lazily-built module-level index, parsed with stdlib `csv`
  (the file contains quoted commas):
  `dict[(artist_key, date)] -> list[JerrybaseEvent]` ordered by
  `ievent`.
- `artist_key` = lowercased alphanumerics only, applied to both the CSV
  artist tokens and llama's artist strings, so `"Grateful Dead"` ↔
  `GratefulDead` and `"Phil Lesh and Friends"` ↔ `PhilLeshAndFriends`
  match without an alias table.
- Set-label normalizer maps jerrybase conventions (`Set 1`, `Set One`,
  `Set I`, `Show`, `Set`, `Encore`, `Encore 1`, `Encore 2`, …) onto
  `"1"/"2"/"3"/"encore"`. Single-set labels (`Show`, `Set`) → `"1"`;
  any `Encore*` → `"encore"`. Unmappable labels drop the row with a
  once-per-load warning.
- `song_count` = `isong` delta between consecutive sets **within one
  event**; the first set of each event gets `None` (its predecessor
  belongs to a different show).
- Closer titles are matched using the existing `norm_title` from
  `structure.py`, so matching behaves identically to track alignment.
- Public surface: `lookup(artist, date) -> list[JerrybaseEvent]`.
  Empty list = no evidence. Length > 1 = multi-event date. Malformed
  rows are skipped, counted, and logged once per load.

## Pipeline integration — `stages/gather.py`

All integration runs after deterministic alignment; no new stage. An
empty lookup makes every step below a no-op — behavior for artists
outside the dataset is byte-identical to today.

1. **Lookup** after `align()` produces the track structure:
   `events = jerrybase.lookup(artist, date)` (skipped when
   `[jerrybase] enabled = false`).
2. **Multi-event tripwire.** `len(events) > 1` → flag
   `multi-event date: N jerrybase events at <venue(s)>` → show is
   `needs-review`. Groundwork only: performance identity, grouping, and
   the ledger key are unchanged in this feature.
3. **Venue enrichment + cross-check** (single-event only).
   - Candidate venue absent → adopt jerrybase venue/city with recorded
     provenance (same pattern as research-date adoption).
   - Both present and disagreeing after normalization
     (lowercase, alphanumerics and spaces only, collapsed whitespace) →
     tripwire flag (venue feeds ledger identity; never overwrite an
     existing venue).
4. **Break anchoring + closer tripwire** (single-event only). Match each
   jerrybase set's closer against aligned tracks via `norm_title`:
   - Deterministic alignment **confident** (coverage ≥ threshold) but a
     break contradicts a matched closer's position → tripwire flag,
     `needs-review`. Confident-but-contradicted is a signal, never an
     auto-fix.
   - Alignment **low-confidence** (below `align_coverage_threshold`):
     before the `align_structure` LLM fallback, attempt **closer
     anchoring** — if every jerrybase closer matches exactly one track
     and the matches are in order, place set breaks after those tracks
     and label sets from the normalized jerrybase set names. Success →
     skip the LLM call entirely; record provenance
     `set breaks anchored from jerrybase`. Failure (any closer missing
     or ambiguous) → LLM fallback as today, then run the closer check
     against the LLM's output as a tripwire.
   - A closer absent from the tracks altogether → soft flag only
     (tapers title tracks differently); it combines with other
     suspicion rather than forcing review alone.
5. **Structure guard extension.** `structure_guard()` gains expected set
   count: aligned set count ≠ jerrybase set count → flag. Both sides
   count **distinct normalized set labels including `encore`**, so a
   2-sets-plus-encore show compares 3 against 3. `song_count`
   deltas are a logged diagnostic only, never a tripwire (taper track
   splitting makes counts noisy).

## Config

- New `[jerrybase]` section with a single knob: `enabled = true`
  (default **on** — vendored, offline, no key, unlike setlist.fm).
  No thresholds: anchoring is all-or-nothing by design.
- `llama config init` template gains the commented section.

## Models and flags

- New suspicion flags ride the existing flag → `needs-review`
  mechanism unchanged.
- Anchoring and venue-adoption provenance reuse the date-adoption
  provenance pattern and surface in `llama show` the same way.
- Exact field shapes are a plan-time detail.

## Testing (offline, `fake` backend)

- **Unit** (`tests/test_jerrybase.py`), against the real vendored CSV
  (in-package, deterministic — no fixture slice): set-label normalizer;
  artist-key matching; `song_count` deltas with first-set `None`;
  malformed-row skipping; multi-event ordering by `ievent`. Known-show
  assertions: gd 1973-06-10 → 3 sets closing PITB / Sugar Magnolia /
  Johnny B. Goode; 1970-02-14 → 2 Fillmore East events; Cornell
  1977-05-08 → short break before encore.
- **Integration** (gather, fake backend): anchoring rescues a
  low-confidence alignment with zero LLM calls; confident-but-
  contradicted break → tripwire; multi-event flag; venue adopt (absent)
  vs flag (mismatch); no-ops when `enabled = false` or artist unknown.

## Docs

- CLAUDE.md: one line noting jerrybase vendored structure evidence and
  the refresh script.

## Out of scope

- Setlist construction or `rank_parses` participation from this data.
- `break_length` in manifest/m3u — waits for the station-format
  conversation.
- Performance-identity / ledger-key changes for multi-event dates
  (flag-only groundwork here).
- Scraping jerrybase.com, or any runtime network fetch of the CSV.
