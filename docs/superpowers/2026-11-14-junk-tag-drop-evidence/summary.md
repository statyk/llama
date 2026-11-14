# Junk-title drop: candidate vs 2026-11-13 baseline

| | baseline | candidate |
|---|---|---|
| drop rows | 960 | 968 |
| shows with a drop | 699 | 709 |
| rule A rows | 508 | 521 |
| rule A shows | 374 | 387 |
| rule B rows | 431 | 426 |
| rule B shows | 359 | 360 |
| rule C rows | 21 | 21 |
| rule C shows | 21 | 21 |
| held rows | 19 | 19 |
| held shows | 19 | 19 |

## Expected-delta reconciliation

Candidate-only drops (in the candidate, not the baseline): 33

- title-differs: 0
- not-in-show.json: 0
- parts-split: 31
- edge-run: 2
- other: 0

Baseline-only drops (in the baseline, not the candidate): 25

- not-in-arm: 0
- operator-include: 2
- arrowed: 0
- needs-llm-row: 23
- title-differs: 0
- not-kept: 0
- other: 0

Kept-track deltas: 3 (kept_track_deltas.tsv)
Override keys naming a dropped file: 13 (override_keys.tsv)
Vocabulary violations: 0 (vocabulary.txt; exit 3 when non-zero)

## Coverage

- base arm shows: 3935 (scope all)
- candidate arm shows: 3935 (scope all)
- in both arms: 3935
- baseline slugs absent from the candidate arm: 0
- baseline slugs absent from the base arm: 0
- rows with empty filenames (skipped by kept-track deltas), base: 2
- rows with empty filenames (skipped by kept-track deltas), candidate: 2
