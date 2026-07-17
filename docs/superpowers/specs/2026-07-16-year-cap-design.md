# Year cap: scores decide the year mix; caps are opt-in knobs

**Date:** 2026-07-16
**Status:** Approved

## Problem

The era-spread change (`b304675`) forces even year representation on every
run. It was built to stop a 1969–1977 profile run from returning 13 shows
all from 1969 — but the true causes of that failure were mechanical and are
fixed independently: search fetched a single 500-row page (`994e8fc`), and
winnow's review-fetch budget truncated a chronologically-ordered candidate
list (`b304675` itself fixed the truncation by sorting on evidence).

With those fixed, strict round-robin across years at the selection points
overrides genuine quality signal. An objective ranking of Grateful Dead
shows is heavily weighted toward the 1970s; a no-range Dead query should
reflect that. Even spread is still *sometimes* wanted ("tour me through
69–77") — so it becomes an opt-in knob, symmetric with `artist_cap`.

## Design

### One mechanism, two knobs

`util.py` gains a single generic picker:

```
capped_pick(items, key_of, n, cap) -> list
```

Best-first selection, but while other buckets still have candidates no
bucket (as keyed by `key_of`) may hold more than `ceil(n * cap)` slots.
`cap = 1.0` is pure best-first (identity prefix); `cap <= 1/n` degenerates
to one-per-bucket round-robin; if every bucket hits the cap before `n`
slots fill, the remainder relaxes to best-first. Items must arrive
best-first; order within the result preserves it.

`cap_across_artists(items, artist_of, date_of, n, artist_cap, year_cap)`
becomes a two-level application of `capped_pick`: each artist's queue is
year-capped (`capped_pick` keyed on `date[:4]` with `year_cap`), then
slots are allocated across artists best-first bounded by `artist_cap`.
With a single artist bucket it reduces to `capped_pick` on years.

`spread_across_years` and `spread_across_artists` (strict round-robin) are
deleted — each is `capped_pick`/`cap_across_artists` with `cap <= 1/n`.
Their call sites and tests migrate to the generalized functions.

### Criteria, CLI

- `Criteria.year_cap: float`, **default 1.0 (off)**, persisted with the
  run like `artist_cap`.
- `--year-cap` (0.0–1.0) on `llama find` and `llama profile add`, mirroring
  `--artist-cap` placement and help style.
- `interpret` never sets it: flag/profile only, same treatment as
  `artist_cap`.

### Application sites — all three use the same caps

1. **Winnow review-fetch sampling** (`stages/winnow.py`): when survivors
   exceed `max_metadata_fetch`, the sample is chosen by
   `cap_across_artists(evidence_sorted, ..., artist_cap, year_cap)`
   instead of `spread_across_artists`. With `year_cap` off, the top-N by
   review evidence get scored, so a 70s-heavy evidence base produces a
   70s-heavy scored pool. (Even-spread sampling would silently cap year
   concentration upstream regardless of the downstream setting.)
2. **Shortlist cut** (`stages/winnow.py`): passes `criteria.year_cap`
   through to the generalized `cap_across_artists`.
3. **Auto-pick** (`choose_entries`, `pipeline.py`): `choose_entries`
   gains a `year_cap` parameter (default 1.0) alongside `artist_cap`;
   `cli._execute` passes `criteria.year_cap`, exactly as it passes
   `criteria.artist_cap` today.

Explicit review approvals are never capped or spread (unchanged).

### Tie-breaking (required, not optional)

LLM quality scores cluster heavily (many 7.5–8.5s), and Python's stable
sort resolves ties in candidate order — which is chronological, so with
caps off every tie band would drain earliest-first: a quiet rerun of the
original bug. Winnow's score sort therefore uses a compound descending
key:

```
(quality_score, total num_reviews, max avg_rating)
```

Equally-scored shows rank by strength of public evidence, not by date.
This is the same evidence signal the sampling pass already sorts on.
`choose_entries` needs no change — it consumes winnow's ranks.

## Resulting behavior

- No-range Dead query: year mix is whatever the scores say — expect
  70s-heavy.
- Era tour (e.g. 69–77 profile): `--year-cap 0.08` ≈ one per year at
  count 13; `0.25` ≈ soft diversity; unset = pure ranking within the
  range.
- Multi-artist style profiles: `artist_cap` default 1/3 unchanged; each
  artist's own slots are year-capped only if `year_cap` is set.
- Old-behavior equivalence: pre-change strict year rotation ==
  `year_cap <= 1/count`.

## Compatibility

- Persisted `criteria.json` without `year_cap` loads with the 1.0 default
  (Pydantic default) — replays of old runs become score-driven; acceptable
  and desired.
- Profile TOMLs: existing profiles gain score-driven behavior on their
  next run unless re-added with `--year-cap`.
- README (`--year-cap` doc line) and `docs/workflow.md` era-spread section
  updated to describe cap semantics.

## Testing

- `test_util.py`: `capped_pick` unit tests — cap off (identity prefix),
  soft cap bounds dominance, `<=1/n` equals old round-robin output,
  cap-relax when all buckets saturate; two-level `cap_across_artists`
  with both knobs; migration of the old spread tests to degenerate-cap
  form.
- `test_stage_winnow.py`: sampling with `year_cap` off takes top-N by
  evidence; shortlist cut honors `year_cap`; tie-break test — equal
  scores, later year with more reviews outranks earlier year with fewer.
- `test_pipeline.py`: `choose_entries` passes `year_cap`; approvals
  bypass caps.
- `test_cli_commands.py` / `test_profiles.py`: `--year-cap` persists to
  criteria/profile round-trip.
