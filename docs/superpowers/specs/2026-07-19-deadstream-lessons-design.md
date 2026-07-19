# Deadstream Lessons — Title Hygiene & Selection Signals — Design

**Date:** 2026-07-19
**Status:** Approved design, pending implementation plan
**Extends:** `2026-07-14-llama-design.md` (gather / select-recording),
`2026-07-15-taper-preferences-design.md` (selection scoring)

## Background

An analysis of eichblatt/deadstream (the Grateful Dead Time Machine
software, ~5 years of field corrections against the same LMA corpus)
surfaced four transferable lessons. Its scoring comment — "down-weigh
avg_rating: it's usually about the show, not the tape" — independently
validates llama's winnow/select split; these four items are the deltas
llama lacks. All four ship as one feature: three touch the same
select-recording/titles area and the fourth shares a helper with them.

1. Embedded tag titles often carry the identifier prefix
   ("gd73-06-10d1t04 Here Comes Sunshine"); llama trusts tags verbatim,
   so the prefix pollutes manifests and breaks setlist alignment.
2. Lexicographic filename order is not always play order; the `track`
   metadata field on original files is the authority when present.
3. `downloads` is a crowd-sourced *recording*-preference signal among
   siblings (unlike `avg_rating`, which is about the show); llama
   ignores it.
4. Which sibling you pick determines how hard titling is; a
   title-resolvability signal in selection avoids gambling on the
   fallback cascade when a fully-tagged sibling exists.

## 1. Tag-title cleanup

Two pure helpers in `titles.py`:

```python
def clean_tag_title(raw: str | None) -> str
def is_real_title(cleaned: str) -> bool
```

`clean_tag_title`:

- Strips the identifier prefix, adapting deadstream's regex and
  extending it to 4-digit years:
  `^[a-zA-Z]{2,5}_*\d{2}(?:\d{2})?[-.]\d{2}[-.]\d{2}\s*(?:[td]\d+)*`
- Strips one trailing audio extension (`.mp3|.flac|.ogg|.shn`,
  case-insensitive) and trims leftover separators/whitespace.
- Maps "unknown" (case-insensitive) to `""` — never a real title.

`is_real_title`: cleaned string is non-empty and contains ≥3 ASCII
letters. This deliberately softens deadstream's ≥5-letter test:
"Deal" and "Jam" are staple titles in this catalog, while the test
still rejects date-less filename residue like "d1t02" (2 letters).

Applied at both tag-title consumers:

- `resolve_titles`: use the cleaned tag title, and accept it only when
  `is_real_title` holds; otherwise fall through the cascade
  (setlist → sibling → unresolved) instead of shipping garbage.
- `_sibling_titles` in gather: returns cleaned titles, and its
  "all files have titles" acceptance test becomes "all cleaned titles
  are real."

Structure markers ("E: Baby Blue") are already handled downstream by
`structure.norm_title` — unchanged.

## 2. Track ordering from tags

`junk.filter_files` currently sorts kept files by filename. It becomes
tag-aware:

- Parse each kept file's `track` field. For derivatives the field
  comes from their original (keyed by the `original` filename), since
  derivative entries often lack it. Accept `"5"`, `"05"`, `"5/16"`
  (leading integer wins); non-numeric or absent → unparseable.
- Use track order **only if** every kept file has a parseable number
  and the numbers are unique. Per-disc numbering restarts at 1 and
  makes duplicates ambiguous — deadstream bails on duplicates, so do
  we. Otherwise keep filename order.
- `filter_files` returns, alongside `kept`/`excluded`, a third tuple
  element: an ordering dict
  `{"order_source": "track-tags" | "filename", "reordered": bool}`
  (`reordered` true when tag order and filename order disagree). All
  call sites update together.

Gather records `order_source`/`reordered` on the Show artifact as
information, **not** a review flag: tag order winning *is* the fix,
not an anomaly. Every consumer (`resolve_titles`, `_sibling_titles`,
gather, select-recording's kept-count) receives files already in
canonical order, so titles and files cannot drift positionally.

## 3. Downloads signal (sibling-relative)

- `"downloads"` joins `SEARCH_FIELDS` in `stages/search.py`.
- `RecordingSummary` gains `downloads: int = 0`; the default keeps
  pre-upgrade `candidates.json` artifacts loadable. `grouping.py` maps
  the field (same `_first`/int coercion as `num_reviews`).
- In `select_recording`, compute per sibling
  `downloads_norm = log1p(downloads) / max(log1p(d) for siblings)`
  (0.0 when all siblings have zero downloads), and pass it to
  `score_recording`, which adds `DOWNLOADS_WEIGHT * downloads_norm`
  with `DOWNLOADS_WEIGHT = 0.75`.

Rationale: selection only compares recordings of the same performance,
so era/artist popularity confounds cancel; log1p tames the power-law
spread; the bound (≤0.75) decides same-lineage ties but can never flip
sbd-vs-aud (lineage gap ≥2.0). No age normalization: shnid
supersession (taper-preferences design) already covers
new-transfer recency.

Operational note: the ia_client cache key hashes the field list, so
the first live run after upgrade re-scrapes (correct, just slower
once). Offline fixtures lacking the field default to 0 harmlessly.

## 4. Title-fraction bonus

In `select_recording`'s per-sibling loop (metadata already fetched —
zero extra network calls), compute:

```
title_fraction = |{kept files where is_real_title(clean_tag_title(title))}| / |kept|
```

(0.0 when no files are kept.) `score_recording` adds
`TITLE_WEIGHT * title_fraction` with `TITLE_WEIGHT = 0.5`.

Sharing `clean_tag_title`/`is_real_title` with item 1 gives one
definition of "real title" everywhere: a tag that is just the filename
or id-prefix counts as no title. The weight is format-bonus-sized deliberately: llama's
cascade can still title an untagged tape (unlike deadstream's player,
which has no fallback and punishes tag-less tapes by up to −3), so
tags are a preference, not a requirement.

## Scoring & artifacts

- `score_recording` signature grows `downloads_norm: float = 0.0` and
  `title_fraction: float = 0.0`, both plain additive terms alongside
  the taper bonus (inside the completeness scaling, like every other
  quality term — a fragment with great tags is still a fragment).
- Weights live as constants in `scoring.py` next to `LINEAGE_SCORES`.
  No new config surface: `SelectionConfig` already covers the knobs
  users tune (tapers, era lineage); YAGNI until someone asks.
- The per-recording breakdown written to `selection.json` gains
  `downloads_norm` and `title_fraction` so `llama review` shows why a
  sibling won.

## Testing

All offline, no live calls:

- `clean_tag_title`/`is_real_title` table tests: 2- and 4-digit-year
  prefixes (`gd73-06-10d1t04`, `gd1977-05-08…`), dotted dates, `t`/`d`
  suffix runs, extension stripping, "unknown" → `""`, "d1t02" not
  real, "Deal"/"Jam" real, and plain titles passing through untouched.
- Ordering: unique tags reorder (titles follow), duplicate tags fall
  back to filename order, missing tags fall back, `order_source` /
  `reordered` reported correctly.
- Scoring: downloads_norm and title_fraction terms, including
  all-zero-downloads and no-tags degenerate cases; bound checks
  (max bonus cannot flip sbd-vs-aud).
- Gather-level: a file whose tag title is id-prefixed now aligns
  against the canonical setlist instead of flagging; built on the
  gd73-06-10 fixture.
- Expected ripple: existing `score_recording`/`filter_files` tests
  update for the new signatures/return shape.

## Out of scope

Deliberately not taken from deadstream (recorded for the future in
memory, not here): jerrybase as a canonical-setlist source, multi-event
dates (two shows, one tape), silence-insertion break semantics, cloud
metadata caching.
