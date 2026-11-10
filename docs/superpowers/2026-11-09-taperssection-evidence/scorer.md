# Checkpoint B: scorer measurement

20 Phish shows (seeded era-stratified sample, seed 20261109), scored through the real `score_reviews` provider twice in two batch orders (A = chronological, B = seeded shuffle mixing batches). Run date 2026-11-09. Baseline = percentile/10, or 4 with no percentile. Floor (min_quality_score) = 6.0.

| date | identifier | percentile | baseline | score A | score B | |diff| | attribution A/B | notes |
|---|---|---|---|---|---|---|---|---|
| 1987-08-10 | phish1987-08-10.029630.burlington.aud.flac16 | 60.0 | 6.0 | 6.0 | 5.8 | 0.2 | ok/ok |  |
| 1990-06-02 | phish1990-06-02.093885.columbia.unk.partial.flac.16 | 4.9 | 0.5 | 2.0 | 0.5 | 1.5 | ok/ok |  |
| 1992-04-18 | phish1992-04-18.085404.paloalto.km140.flac1644 | 88.4 | 8.8 | 8.5 | 8.8 | 0.3 | ok/ok |  |
| 1992-12-07 | phish1992-12-07.020381.minneapolis.unk.flac1644 | 60.7 | 6.1 | 6.0 | 6.1 | 0.1 | ok/ok |  |
| 1993-04-16 | phish1993-04-16.001407.louisville.akg460.flac1644 | 86.7 | 8.7 | 8.2 | 8.7 | 0.5 | ok/ok |  |
| 1994-06-23 | phish1994-06-23.012008.pontiac.akg460.flac1644 | 55.5 | 5.6 | 5.6 | 5.6 | 0.0 | ok/ok |  |
| 1995-06-13 | ph1995-06-13d2t01_raw | 80.2 | 8.0 | 8.0 | 8.0 | 0.0 | ok/ok |  |
| 1995-11-24 | phish1995-11-24.012609.pittsburgh.at4031.flac1644 | 42.4 | 4.2 | 4.2 | 4.2 | 0.0 | ok/ok |  |
| 1996-10-19 | phish1996-10-19.008846.buffalo.cmc64.flac1644 | 37.3 | 3.7 | 3.7 | 3.7 | 0.0 | ok/ok |  |
| 1998-07-25 | phish1998-07-25.007907.austin.cmc64.flac1644 | 91.9 | 9.2 | 9.2 | 9.2 | 0.0 | ok/ok |  |
| 1998-11-13 | phish1998-11-13.004504.cleveland.cmc6.mk41.flac1644 | 57.7 | 5.8 | 5.8 | 5.8 | 0.0 | ok/ok |  |
| 2000-06-24 | phish2000-06-24.001042.atlanta.mk41.cmc6.flac1644 | - | 4.0 | 4.0 | 4.0 | 0.0 | ok/ok | no percentile |
| 2009-08-02 | ph2009-08-02dpa4027-24bitRMd2t03 | 17.4 | 1.7 | 1.7 | 1.7 | 0.0 | ok/ok |  |
| 2010-06-29 | phish2010-06-29.108549.canandaguia.senn441.kutik.flac1644 | - | 4.0 | 4.0 | 4.0 | 0.0 | ok/ok | no percentile |
| 2014-07-25 | phish2014-07-25.peluso.ck4.flac16 | 38.8 | 3.9 | 3.9 | 3.9 | 0.0 | ok/ok |  |
| 2016-10-19 | phish2016-10-19.137095.nashville.m934c.m221.taylorc.flac1644 | 26.9 | 2.7 | 2.7 | 2.7 | 0.0 | ok/ok |  |
| 2019-07-06 | phish2019-07-06.147109.boston.ccm4v.zman.flac1644 | 17.5 | 1.7 | 1.7 | 1.7 | 0.0 | ok/ok |  |
| 2022-07-15 | phish2022-07-15.157468.mansfield.ccm4v.obanion.flac2496 | 78.2 | 7.8 | 7.8 | 7.8 | 0.0 | ok/ok |  |
| 2023-09-01 | ph2023-09-01.dpa4022.flac24 | 65.3 | 6.5 | 6.5 | 6.5 | 0.0 | ok/ok |  |
| 2026-04-30 | ph2026-04-30.mk41v.cmc1k.788T.2448 | 99.4 | 9.9 | 9.9 | 9.9 | 0.0 | ok/ok |  |

- Order A: 9/20 at or above 6.0 (45%)
- Order B: 8/20 at or above 6.0 (40%)
- Overall: 17/40 at or above 6.0 (42%)
- Largest per-show difference between orders: 1.5 at ts-phish/1990-06-02 (A 2.0, B 0.5)
- Shows with both scores within +/-0.5 of their baseline: 19/20 (high = the scorer follows the baseline; low = it ignores it)
- Shows whose percentile came from tied zero rates (tie-percentile caveat): none

## Batches

- A1: 1987-08-10, 1990-06-02, 1992-04-18, 1992-12-07, 1993-04-16
- A2: 1994-06-23, 1995-06-13, 1995-11-24, 1996-10-19, 1998-07-25
- A3: 1998-11-13, 2000-06-24, 2009-08-02, 2010-06-29, 2014-07-25
- A4: 2016-10-19, 2019-07-06, 2022-07-15, 2023-09-01, 2026-04-30
- B1: 1987-08-10, 2022-07-15, 1995-11-24, 2019-07-06, 2014-07-25
- B2: 1990-06-02, 1993-04-16, 1995-06-13, 2026-04-30, 2010-06-29
- B3: 2009-08-02, 1992-12-07, 2023-09-01, 1996-10-19, 1992-04-18
- B4: 1998-11-13, 2000-06-24, 2016-10-19, 1994-06-23, 1998-07-25
