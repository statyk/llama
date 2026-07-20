# Multi-event dates: per-event performance identity — design

Date: 2026-07-19
Status: approved

## Problem

Some dates carry two performances (early/late show) on one date —
e.g. GD 1970-02-14 at Fillmore East. Today `group_candidates` keys
performances as `collection/date` (plus an `/early`//`late` suffix only
when the archive identifier happens to contain those words), so distinct
events collapse into one candidate, and the jerrybase-evidence feature
can only flag `multi-event date` → needs-review. Multi-event shows never
auto-ship, and a merged package would misrepresent two shows as one.

jerrybase evidence (vendored `set_breaks.csv`) now provides ground
truth: `Nevents`/`ievent` per date, with per-event venue and set-closer
songs.

## Decision

**One show per event.** Each event becomes its own performance —
own candidate, own workspace/library slug, own ledger entry. Splitting
happens at **grouping time** (search stage), so identity is fixed
before any later stage runs; no mid-pipeline id rewrites.

**No reverse compatibility.** Ledger entries written before this
feature (`collection/date`) simply don't match new per-event ids; no
migration code, no legacy matching (owner will purge and re-run; this
matches the project's removed-migration precedent). Document in the
spec/CLAUDE.md only.

## Design

### Identity

- Multi-event dates: `collection/date/eN`, N = jerrybase `ievent`
  order (e1 = first/early). Single-event dates keep `collection/date`.
- The existing `/early`//`late` identifier sniffing folds into this:
  when jerrybase confirms 2 events, early→`e1`, late→`e2`. When
  jerrybase has no data for the date, today's behavior is preserved
  verbatim (including the old early/late suffix path).

### Grouping (`grouping.py`)

`group_candidates` gains access to the jerrybase module (offline,
free). Collection strings (`GratefulDead`) already normalize to
jerrybase artist keys via `artist_key`. For each date with
`Nevents > 1`, partition that date's recordings into per-event
candidates:

1. **Early/late text** in identifier, title, or description →
   e1/e2 (2-event dates only).
2. **Closer matching in description text:** an event's set-closer
   songs (via `norm_title` containment) appearing in the recording's
   description assigns it to that event.
3. A recording matching closers from **multiple events** (one tape
   spans the evening) → its own candidate flagged
   `tape spans N events` → needs-review; never split, never
   auto-assigned.
4. **Unassignable** recordings (no signal either way) → grouped into
   their own candidate flagged `unassigned multi-event recordings` →
   needs-review.

Each per-event candidate carries its event's jerrybase venue/city as
grouping venue when archive fields are absent.

### Gather (`stages/gather.py`)

- A candidate with an `/eN` pid selects `events[N-1]` from
  `jerrybase.lookup` for all existing evidence checks (venue
  enrichment/mismatch, break anchoring, closer tripwires, set-count
  guard) — replacing today's blanket multi-event flag for partitioned
  candidates.
- The blanket `multi-event date` flag remains only for the
  spans/unassigned candidates and for multi-event dates encountered
  without partitioning (defensive).
- Spans-both detection at gather too: if aligned tracks contain
  closers from more than one event, flag `tape spans N events`
  (a tape mislabeled at grouping can still be caught).

### Ledger / workspace / packaging

No structural changes: `performance_id` strings are the key
everywhere; slugs and show-dir names inherit the `/eN` suffix through
the existing slugging. `llama show`/`status` display the pid as-is.

## Testing (offline)

- **New fixture:** capture real archive.org responses for GD
  1970-02-14 (early + late Fillmore East items) via
  `scripts/capture_fixture.py` — one-time live capture, committed like
  gd73-06-10.
- Unit (grouping): early/late-hint partition; description-closer
  partition; spans-both → held candidate; unassignable → held
  candidate; no-jerrybase-data date → byte-identical current behavior;
  single-event date unchanged.
- Unit (gather): `/eN` candidate uses the right JerrybaseEvent for
  venue/closer/set-count checks; spans-both gather flag.
- End-to-end (fake backend): a 1970-02-14 run produces independent
  per-event candidates with distinct pids, slugs, and ledger entries.
  Data reality (verified against archive.org): no early-show-only
  recording of 1970-02-14 exists — the early set survives only inside
  complete-evening tapes — so the integration proof is a clean `/e2`
  package plus a held `/spans` candidate, which exercises the same
  identity mechanism.

## Out of scope

- Splitting a single tape's audio between events.
- Break-length/location-break semantics in the package (blocked on the
  station-format conversation).
- Ledger migration or any legacy-id compatibility.
- Multi-event detection without jerrybase data (identifier-sniff path
  keeps its current limited behavior).
