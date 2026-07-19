# Research-Date Adoption for Placeholder Item Dates — Design

**Date:** 2026-07-19
**Status:** Approved design, pending implementation plan
**Extends:** `2026-07-14-llama-design.md` (vet stage, quality philosophy)

## Background

Real-world case: `cjm1976-01-01.koln.flac16` (Country Joe McDonald, WDR
Köln). The archive item's `date` is `1976-01-01` with `year: 1976` — the
archive.org **year-only placeholder pattern** (uploader knew only the
year; Jan 1 is baked into the identifier). Deep research found the true
date, February 8 1976, and all 13 asserted songs grounded against the
tracklist — yet vet emitted four `research asserts wrong date` flags
(one per surface spelling of the same date; all normalize to
`1976-02-08`) and held the show. Two defects and one gap:

1. Blame inversion: the flag wording says the research is wrong when the
   evidence says the *item date* is wrong.
2. Flag spam: each spelling of one date gets its own flag.
3. No mechanism to adopt a well-evidenced research date, so the package
   would announce the wrong date on air unless a human intervenes.

## Core principle: identity vs presentation

**Performance identity stays item-derived and immutable.**
`performance_id`, the show-dir slug, and the ledger dedup key are minted
from the item's date at search/grouping time and never change — a future
run of the same item regroups identically, so dedup holds. Only the
**presented** date is correctable: `Show.date`, which flows to the
manifest, m3u naming, DJ script, and displays. A corrected show may
therefore live in a dir slugged with the placeholder date; provenance
explains.

## Model changes

`Show` gains two defaulted fields (old artifacts load unchanged):

```python
    item_date: str | None = None  # original archive date, set only when corrected
    date_source: str = "item"  # "item" | "research"
```

`VettingResult` gains:

```python
    adopted_date: str | None = None  # research date adopted over a placeholder
```

## Adoption (vet stage)

In `run_vet_research` / `grounding_flags` (`stages/vet_research.py`),
after extraction. All four conditions required:

1. `show.date` ends `-01-01` (year-only placeholder pattern), and
   `show.date_source == "item"`.
2. The parseable full asserted dates normalize to exactly **one**
   distinct value, and every parseable year-less (`--MM-DD`) assertion
   agrees with that value's month/day — a year-less contradiction means
   the research dates conflict, which blocks adoption.
3. That value shares `show.date`'s year and differs from `show.date`.
4. The unknown-songs gate did not fire (research provably describes
   this show).

On adoption:

- `show.date` ← research date; `item_date` ← old date;
  `date_source` ← `"research"`.
- **No wrong-date flag, no hold** (owner decision 2026-07-19): the
  wrong-show risk the gate exists for is covered by condition 4;
  `--auto` runs proceed.
- `VettingResult.adopted_date` records the correction.

Idempotence: a corrected show's date no longer ends `-01-01`
(condition 1 fails on same-year adoption by construction — the adopted
date differs from Jan 1) and matches the research dates, so re-vet
neither re-adopts nor flags. A `redo --from gather` resets the date from
the candidate and re-vet re-adopts — converges to the same state.

Jan 1 shows can be real (New Year's runs), so adoption never triggers on
date agreement alone — it requires an actual research contradiction plus
the full condition bundle; a real Jan-1 show whose research also says
Jan 1 has no mismatch and is untouched.

## Diagnosis fixes (non-adopted mismatch paths)

In `grounding_flags`:

- **Dedup by normalized date:** one `wrong date` flag per distinct
  normalized value; the first-seen surface text is quoted. Unparseable
  and year-less handling unchanged (year-less still matches on MM-DD,
  each distinct year-less mismatch flags once).
- **Placeholder-aware wording:** when `show.date` ends `-01-01` and
  `date_source == "item"` but adoption conditions fail (different year,
  conflicting research dates, or songs did not ground), the flag reads:
  `research asserts <normalized>; item date <show.date> looks like a
  year-only placeholder` — still a hold, honest blame. Non-placeholder
  mismatches keep the current wording, deduped:
  `research asserts wrong date: <first surface text>`.
- Both wordings keep the `research asserts ` prefix so re-vet flag
  scrubbing (`_VET_FLAG_PREFIX`) continues to work.

## Surfacing

- `llama show` (cli.py header line): when `date_source == "research"`,
  the header shows `1976-02-08 (item date 1976-01-01, corrected via
  research)`.
- Downstream (manifest, DJ script, status listings) needs no changes —
  everything reads `Show.date`.

## Out of scope

- Renaming show dirs / re-slugging to the corrected date (identity is
  immutable; collision-prone; provenance explains).
- Adopting dates across years, from conflicting research, or on
  non-placeholder dates — those remain holds for a human.
- Placeholder detection at search/winnow time.

## Testing

All offline, `tests/test_stage_vet.py` (+ one models default test, one
cli display test if cheap):

- Countryjoe-shaped adoption: placeholder show + four spellings of one
  same-year date + grounded songs → date adopted, fields set, no flags,
  `needs_review` false, `adopted_date` recorded.
- Each adoption condition broken singly → no adoption:
  non-placeholder date (plain wrong-date flag, deduped to one);
  two distinct research dates (placeholder wording, one flag each);
  different year (placeholder wording); unknown-songs gate fired
  (placeholder wording + song flags, no adoption).
- Dedup: multiple spellings of one wrong date on a NON-placeholder show
  → exactly one flag.
- Idempotent re-vet on an adopted show → still clean, date unchanged.
- Year-less mismatch behavior unchanged.
- `Show` defaults: pre-upgrade show.json (no new fields) loads with
  `date_source == "item"`, `item_date is None`.
