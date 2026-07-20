# Venue-name normalization — design

Date: 2026-07-19
Status: approved

## Problem

The jerrybase venue-mismatch tripwire (gather) compares venue strings
with `_norm_place` (lowercase, alphanumerics+spaces, collapsed
whitespace), which cannot equate abbreviation variants: archive
"RFK Stadium" vs jerrybase "Robert F. Kennedy Stadium" flags a venue
mismatch and holds an otherwise-fine show for review. Under default-on
jerrybase evidence this false-holds common venues (RFK, MSG,
Winterland-style variants) on the primary `--auto` GD path.

Scope note: venue is NOT part of performance identity
(`performance_id` is `collection/date[/eN]`), so this feature touches
only the gather tripwire comparison — not grouping, ledger, or dedup.

## Decision

Conservative, deterministic, offline matching — no LLM, no curated
alias file. Only high-confidence equivalence patterns auto-pass;
everything else still trips the flag. When uncertain, hold for review.

## Design

New pure predicate `venues_equivalent(a: str, b: str) -> bool`
(location: alongside `norm_title` in `structure.py`, or a small new
`places.py` if the plan prefers isolation — plan decides). `_norm_place`
becomes its shared tokenizer. Venues are equivalent iff ANY of:

1. **Normalized equality** — today's rule, unchanged.
2. **Initialism match** — the leading letters of one side's tokens
   (in order, skipping stopwords) spell a token of the other side:
   RFK ↔ Robert F. Kennedy (Stadium), MSG ↔ Madison Square Garden.
3. **Token-subset match** — after dropping stopwords (the, at, of,
   and), one side's token set is a subset of the other's:
   Winterland ↔ Winterland Arena, Fillmore East ↔ Fillmore East (New
   York) [city tail dropped by tokenization].
4. **Abbreviation expansion** — small built-in dict applied
   token-wise before rules 1–3: aud↔auditorium, theatre↔theater,
   univ↔university, coll↔college, mem↔memorial, ctr/cntr↔center,
   gym↔gymnasium, st↔street/state (ambiguous — st expands to a set;
   any expansion matching counts).

Call site: `stages/gather.py` venue check swaps
`_norm_place(venue) != _norm_place(event.venue)` for
`not venues_equivalent(venue, event.venue)`. Flag text unchanged.

## Error handling

Pure string predicate; None/empty handling stays at the call site
(absent venue already takes the adoption path, never the comparison).

## Testing

- Table-driven unit tests: equivalent pairs (RFK Stadium ↔ Robert F.
  Kennedy Stadium, MSG ↔ Madison Square Garden, Winterland ↔
  Winterland Arena, Barton Hall ↔ Barton Hall, Cornell University,
  Fillmore Aud ↔ Fillmore Auditorium) and non-equivalent pairs that
  MUST still trip (Fillmore East vs Fillmore West, Boston Garden vs
  Boston Music Hall, Winterland vs Warfield).
- One gather integration test: with jerrybase enabled, the real
  gd73-06-10 fixture ("RFK Stadium") passes the venue check against
  jerrybase's "Robert F. Kennedy Stadium" (no mismatch flag). Existing
  `[jerrybase] enabled = false` isolation in pipeline/cli e2e tests
  stays untouched.

## Out of scope

- Fuzzy scoring (edit distance, token-overlap thresholds) — rejected
  as too aggressive for a tripwire.
- Curated per-venue alias data files.
- LLM adjudication of mismatches.
- Any change to grouping, ledger, or performance identity.
