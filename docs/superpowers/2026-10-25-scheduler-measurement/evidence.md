# Scheduler measurement against the delivered library (2026-10-25)

Evidence for the operator, and for the one floor check the spec's Measurement section makes.

## Floor check (clock a): PASS

| | block starts / gaps | outside the window | share |
|---|---|---|---|
| Scheduler (50 consecutive weeks, one projection) | 1151 | 0 | **0.0%** |
| Naive filler, overran | 1100 (22 gaps x 50 seeds) | 15 | 1.4% |
| Naive filler, not fillable | 1100 | 17 | 1.5% |
| Naive filler, overran + not fillable (silences count as misses) | 1100 | 32 | **2.9%** |

0.0% is no higher than 2.9%. Pass. Caveats on the comparison are under "Reading the floor check".

## What was run

- Library: `/Volumes/media/lma-radio/delivered`, 2,786 packages, read strictly read-only (manifests and clip headers; no
  audio decode, no writes there). `--library delivered` is `pieces.scan_delivered`: **estimated lengths only**. 224 of the
  packages are voiced (eligible); the other 2,562 get the 4-minute clip allowance. The scan took about 160 s and was cached in
  a private scratch pickle outside the repo and the library.
- Render constants: `pause_samples` = 0.75 s (config default `clip_pause_seconds`), show gap 2.0 s (`show_gap_seconds`),
  `extra` = `aacenc.extra_frames()` measured once with the local ffmpeg (on synthetic silence, not library audio).
- One continuous `scheduler.project` per run, 50 weeks, from an empty plan and an empty `Recency`, seed 0, history
  accumulating through the projection's own recency; weekly figures are slices of it (`results-*.json`, `weeks`).
- Start: frame 0 is the nominal start of the first occurrence on or after Monday 2026-11-02 local midnight (America/New_York),
  so no block is entered mid-way: clock a starts at the 07:00 dead-am block, b at the 00:00 overnight tribute block,
  c at the 08:00 dead block (`clock_start` in each JSON gives the instant, 2026-11-02 EST). Block starts counted are occurrences whose nominal start falls in the 50 weeks.
- No interstitial library exists on this machine, so station IDs and announcements never appear in any run; for clock (a)
  `--no-interstitials` is the same thing the brief asked for. The default announcement settings were not exercised.
- Commands (from the worktree root; `S` is a scratch pickle path):
  ```
  measure_scheduler.py --root $R --clock clock-a.toml --weeks 50 --library delivered --no-interstitials --scan-cache $S --out results-a.json
  naive_filler.py      --root $R --clock clock-a.toml --scan-cache $S --out results-naive.json      # 50 seeds
  measure_scheduler.py ... clock-b.toml --library delivered ...  --out results-b.json
  measure_scheduler.py ... clock-c.toml --library delivered ...  --out results-c-delivered.json
  measure_scheduler.py ... clock-c.toml --library eligible  ...  --out results-c-eligible.json
  ```
- Clocks: (a) the naive script's five anchors, windows `[nominal, nominal + 15 min]`, `[open] exclude_profiles = dead, funk,
  dead-family`; (b) **illustrative only, not the operator's clock**: dead-tribute overnight 00:00 (max 3 shows), dead 07:00
  and 20:00, bluegrass 12:00, a Mon-Fri 15:00 rotation (americana, indie, southern, jam, livetronica), funk weekend
  afternoons, an open 18:00 stretch, default 15-minute windows; (c) soft launch: dead 08:00 and 20:00, funk 14:00, the
  no open block at all: every other profile reaches air only as fill (`exclude_profiles` = dead, funk).

## Results, 50 weeks per clock

| clock | pool | block starts | outside window | share | degraded | show min | fill min (structural / pool-short) | fill share |
|---|---|---|---|---|---|---|---|---|
| a (delivered) | 2786 | 1151 | 0 | 0.0% | 0 | 504161 | 38162 / 0 | 7.6% |
| b (delivered) | 2786 | 2101 | 0 | 0.0% | 0 | 504250 | 0 / 0 | 0.0% |
| c (delivered) | 2786 | 1051 | 0 | 0.0% | 0 | 504238 | 0 / 0 | 0.0% |
| c (eligible) | 224 | 1051 | 0 | 0.0% | 0 | 504214 | 42806 / 21963 | 12.8% |

| clock | bends by rule | own-profile share | shows per block start |
|---|---|---|---|
| a (delivered) | {'era': 10, 'gap': 347} | 92.4% | 2.07 |
| b (delivered) | {'artist_day': 15, 'era': 2, 'gap': 663} | 100.0% | 1.56 |
| c (delivered) | {'gap': 323} | 100.0% | 1.69 |
| c (eligible) | {'adjacency': 4, 'artist_day': 4, 'era': 9, 'gap': 4} | 87.2% | 2.43 |

| clock | shows aired | repeats | min / p10 / median / p90 (days) | <1d | 1-7d | 7-30d | 30-45d | 45-90d | >=90d |
|---|---|---|---|---|---|---|---|---|---|
| a (delivered) | 847 | 1540 | 1.0 / 1.8 / 5.0 / 99.9 | 0 | 824 | 126 | 19 | 399 | 172 |
| b (delivered) | 1325 | 1950 | 1.0 / 7.0 / 46.0 / 132.0 | 0 | 191 | 404 | 107 | 903 | 345 |
| c (delivered) | 153 | 1622 | 1.0 / 1.8 / 4.0 / 48.0 | 0 | 1014 | 306 | 31 | 249 | 22 |
| c (eligible) | 183 | 2371 | 1.0 / 2.0 / 26.0 / 45.3 | 0 | 754 | 603 | 584 | 427 | 3 |

Per-block, per-profile detail (own-profile share by block, distinct shows aired against the pool, fill minutes by profile)
is in `results-*.json` under `total`. Misses were zero in every week of every run.

## Naive baseline (clock a)

`naive_filler.py`: the parent's feasibility-sim, edited as the spec lists (root argument; anchors and the 15-minute window
read from `clock-a.toml`; `exclude_profiles` from `[open]`; separate counts; the scheduler's length estimates via the same
scan; 50 seeds; JSON). 2,786 shows, 23 anchors per week, 22 gaps per seed, 1,100 gaps in all: overran 15, not fillable 17.
It keeps the original's simplifications (one random show per anchor, a 4,000-try random fill, no join gaps, one week and no
history per seed), so it is a baseline of the parent's method, not a model of everything the scheduler does.

## Reading the floor check

- It is not fully like-for-like in the scheduler's favour: the scheduler counts 1,151 block starts over 50 weeks including
  the 07:00-to-07:00 wrap and its `max_shows = 2` default plays up to two own-profile shows per block, where the naive script
  plays exactly one anchor show then fills; the naive run restarts each week with no history; the scheduler's gaps between
  shows are real (2 s) and the naive run's are zero.
- Both are on estimates. The scheduler's zero is a statement about the estimated lengths it planned with; it says nothing
  about how exact lengths will move landings (that is the live planner's exact-count re-run).
- A zero-miss result is only informative if misses can be seen. They can: a sanity run on a 6-show pool (dead and funk)
  against clock (a) produced 44 misses in 46 block starts, and 16 degraded blocks.

## Anything surprising

1. **Dead shows repeat heavily.** On clock (a) the scheduler aired only 39 of the 413 dead-profile shows in 50 weeks (roughly
   1,400 plays), median repeat gap 5 days, p10 1.8 days, 824 of 1,540 repeats inside 7 days. On clock (b) it is 38 of 413,
   but median 46 days (the overnight and weekday blocks take their own profiles, leaving the Dead blocks the same two). On (c)/delivered 66 of 413 dead and 87 of 221 funk, median
   4 days. Other profiles spread much further (bluegrass 302/307, dead-tribute 208/208 on b, indie 148/329 on a). The
   compromise order puts "land the next block in its window" ahead of every rotation rule, and the `gap` rule (the
   45-day concert gap) is the rule bent most often (347 bends on a, 663 on b, 323 on c) - consistent with landing-in-window
   squeezing the usable dead shows to a few dozen. I did not dig into the cause (the dead pool's lengths, the tight
   15-minute window, the pair search); this is a finding, not a diagnosis. Within the spec's terms there are no misses but
   a listener hears the same Dead tapes every few days. Worth the operator's eye before Task 11.
2. **No fill clusters / MAX_FILL stalls**: zero misses anywhere, so no run of early-landing blocks. On (a) fill is 7.6% of show
   minutes, all `structural` (the fill cause), never `pool-short`, drawn from indie (13,039 min), americana (10,252),
   southern (7,768), livetronica, jam, dead-tribute and bluegrass. Nothing from `dead`, `funk`, `dead-family` (the exclusion
   held), and no country.
3. **Country** never dominates: 2 packages in the library, one aired (b, 120 minutes of open time). Folding it into
   americana would change nothing here.
4. **Clock (c) on the eligible library (224 voiced packages)**: 87% own-profile (dead-evening only 74%: 113 voiced dead cannot
   fill two daily blocks without repeats), fill 12.8% of show minutes, 22,000 of them `pool-short`, and it is dominated by
   indie (52,253 of 64,769 fill minutes) because indie is the only voiced non-Dead/funk profile with 18 shows. Repeat
   gaps: 82% of repeats inside 45 days, median 26 days, 183 distinct shows over 50
   weeks. Zero misses even so.
5. On (b) and (c)/delivered own-profile share is 100% and fill is zero: every block reached the next window from its own
   shows. Open stretch time on (b) is 42,000 minutes across nine profiles (indie, americana, southern lead); dead-family
   is open-pool eligible on (b) because (b) excludes nothing.
6. `shows_per_block_start` is 2.07 / 1.56 / 1.69 / 2.43 for a / b / c-delivered / c-eligible.

## Files

`clock-a.toml`, `clock-b.toml`, `clock-c.toml`, `naive_filler.py`, `results-a.json`, `results-b.json`,
`results-c-delivered.json`, `results-c-eligible.json`, `results-naive.json`; the script is
`packages/transmitter/scripts/measure_scheduler.py`.
