# Scheduler measurement against the delivered library (2026-10-25, re-run at 9260dbd)

Evidence for the operator, and for the one floor check the spec's Measurement section makes. This replaces the first
version of this doc, which measured a ranking defect in the scheduler (fixed at 9260dbd) and misread it; see
"What changed since the first run".

## Floor check (clock a, full library): PASS

| | block starts / gaps | outside the window | share |
|---|---|---|---|
| Scheduler (50 consecutive weeks, one projection) | 1150 | 0 | **0.0%** |
| Naive filler, overran | 1100 (22 gaps x 50 seeds) | 15 | 1.4% |
| Naive filler, not fillable | 1100 | 17 | 1.5% |
| Naive overran + not fillable (silences count as misses) | 1100 | 32 | **2.9%** |

0.0% is no higher than 2.9%. Pass. The naive figures are identical to the first run (the script is unchanged apart from
reading the new cache format).

## What changed since the first run

The first run reported only 39 of 413 Dead shows aired in 50 weeks and called it a consequence of landing-in-window
squeezing. That was wrong. The review traced it to a defect in the block ranking: options were ranked on violation counts
summed per show, and in a single-artist pool (all 413 Dead packages are Grateful Dead) every extra show adds an unavoidable
adjacency and artist_day violation, so one long show beat every never-aired pair. Fixed at 9260dbd (a single-artist
own pool is exempt from adjacency and artist_day; gap and era still apply). **Before the fix, clock a, [0,+15]: 39 of 413
Dead shows aired, and the Dead blocks repeated a lone show 1-2 days later** (the doc's old "median 5 days" was
station-wide, not Dead). After the fix: 384 of 413. The old station-wide
repeat statistics and the old tables are gone.

A library defect also matters and is independent of the scheduler: **17 Dead packages list every track twice** (consecutive
identical titles; `doubled-dead.txt`, 1974-09-11 is a voiced one). They are the only single shows that land the
300-minute dead-am block alone (fresh pairs of undoubled shows also land it), and the only own shows and pairs that land a
12-hour two-show block, so they dominate the 12-hour Dead blocks the scheduler can fill from own shows. Every figure below is given with the full library and with these 17 excluded ("excl-17"). The operator
expects the library to shrink before it grows (some delivered shows will be held pending llama fixes), so excl-17 is the
more representative picture.

## What was run

- Code: HEAD 9260dbd for the scheduler; `measure_scheduler.py` as committed with this doc. Library:
  `/Volumes/media/lma-radio/delivered`, 2,786 packages, read strictly read-only (manifests and clip headers; no audio
  decode, no writes there). `--library delivered` = `pieces.scan_delivered`, **estimated lengths only**; 224 packages are
  voiced (the `eligible` library), the other 2,562 get the 4-minute clip allowance. The scan cache is a private scratch
  pickle keyed by root and library.
- Constants: pause 0.75 s, show gap 2.0 s (config defaults), `extra` from `aacenc.extra_frames()` (local ffmpeg on
  synthetic silence).
- One continuous `scheduler.project` per run, 50 weeks, from an empty plan and empty `Recency`, seed 0, no per-week restart.
  Frame 0 is the nominal start of the first occurrence on or after Monday 2026-11-02 local midnight (America/New_York),
  so no block is entered mid-way: a starts at the 07:00 dead-am block, b at the 00:00 overnight block, c at 08:00 dead.
- **Weeks are local-calendar 7-day spans** from the start day (changed from the first run, which used UTC spans and so counted
  1151 starts after a DST change; it is 1150 = 23 x 50 now, 2100 for b, 1050 for c).
- No interstitial library exists on this machine: station IDs and announcements never appear in any run.
- Clocks: (a) the naive script's five anchors, windows [nominal, nominal + 15 min], `[open] exclude_profiles` = dead, funk,
  dead-family; `clock-a-sym.toml` is the same with the default symmetric +-15 window; (b) **illustrative, not the operator's
  clock**: dead-tribute overnight 00:00 (max 3 shows), dead 07:00 and 20:00, bluegrass 12:00, a Mon-Fri 15:00 rotation
  (americana, indie, southern, jam, livetronica), funk weekend afternoons, an open 18:00 stretch, default windows; (c) soft
  launch: dead 08:00 and 20:00 (so a 12-hour evening block), funk 14:00, no open block (other profiles reach air only as
  fill; `exclude_profiles` = dead, funk). Note b's dead blocks are 07:00 to 12:00 and 20:00 to 00:00.
- Runs: `measure_scheduler.py --root $R --clock clock-X.toml --weeks 50 --library delivered|eligible --no-interstitials
  [--exclude-slugs doubled-dead.txt]`, and `naive_filler.py` (50 seeds). Outputs: `results-*.json`.

## Results, 50 weeks

| run | pool | block starts | misses (share) | fill min structural / pool-short = share | own-profile | Dead aired/pool | Dead gap min / median (d) / repeats < 7 d |
|---|---|---|---|---|---|---|---|
| a full | 2786 | 1150 | 0 (0.0%) | 35843 / 72 = 7.1% | 92.9% | 384/413 | 1.0 / 13.0 / 403 |
| a excl-17 | 2769 | 1150 | 0 (0.0%) | 129134 / 110 = 25.7% | 74.3% | 396/396 | 45.0 / 52.4 / 0 |
| a symmetric +-15, full | 2786 | 1150 | 0 (0.0%) | 12121 / 7062 = 3.8% | 96.2% | 396/413 | 1.0 / 18.0 / 320 |
| b full | 2786 | 2100 | 0 (0.0%) | 0 / 0 = 0.0% | 100.0% | 404/413 | 1.99 / 47.0 / 4 |
| b excl-17 | 2769 | 2100 | 0 (0.0%) | 0 / 0 = 0.0% | 100.0% | 395/396 | 4.34 / 46.5 / 4 |
| c delivered full | 2786 | 1050 | 0 (0.0%) | 0 / 0 = 0.0% | 100.0% | 403/413 | 1.0 / 10.0 / 403 |
| c delivered excl-17 | 2769 | 1050 | 0 (0.0%) | 117588 / 0 = 23.3% | 76.7% | 384/396 | 45.0 / 50.5 / 0 |
| c eligible full | 224 | 1050 | 0 (0.0%) | 45891 / 21604 = 13.4% | 86.6% | 113/113 | 1.0 / 32.5 / 290 |
| c eligible excl-17 | 223 | 1050 | 0 (0.0%) | 106221 / 0 = 21.1% | 78.9% | 112/112 | 1.01 / 30.0 / 177 |

Misses were zero in every week of every run. Bends by rule (a bend is counted only when a rule-keeping option was **offered by the bounded search**; see the note below the table):

| run | bends by rule |
|---|---|
| a full | {'era': 3} |
| a excl-17 | none |
| a symmetric +-15, full | {'era': 4} |
| b full | {'artist_day': 15, 'era': 5, 'gap': 41} |
| b excl-17 | {'artist_day': 10, 'era': 8, 'gap': 40} |
| c delivered full | none |
| c delivered excl-17 | {'artist_day': 1, 'era': 1} |
| c eligible full | {'artist_day': 1, 'era': 3, 'gap': 3} |
| c eligible excl-17 | {'artist_day': 3, 'era': 8, 'gap': 6} |

**Bends are undercounted.** The count includes only options the bounded search offered. The review's exhaustive probes
(scratch copies, not committed runs) found gap-keeping options that land but were never offered: **clock a dead-family,
35 of 35 gap-breaking first calls; clock c funk, 30 of 337**. Cause: `_blocksearch.py` first-show selection ignores whether
a rule-keeping partner exists (a Task 8 follow-up). The zero-gap-bend entries above and the dead-family figures (43/225
aired, 7-day minimum) therefore partly reflect that search miss, not the library.

Distinct shows aired / pool by profile, with that profile's repeat gap (min and median, days, over the whole span):

- **a full**: ? 1/1; americana 106/329 (gap min 48.96, median 167.0); bluegrass 301/307 (gap min 2.0, median 54.5); dead 384/413 (gap min 1.0, median 13.0); dead-family 43/225 (gap min 7.0, median 28.0); dead-tribute 14/208; funk 61/221 (gap min 48.97, median 56.0); indie 156/329 (gap min 45.04, median 105.0); jam 19/244 (gap min 199.94, median 199.9); livetronica 25/232 (gap min 81.04, median 160.9); southern 67/275 (gap min 47.0, median 75.5)
- **a excl-17**: americana 238/329 (gap min 51.5, median 124.5); bluegrass 307/307 (gap min 2.0, median 55.0); dead 396/396 (gap min 45.0, median 52.4); dead-family 43/225 (gap min 7.0, median 28.0); dead-tribute 75/208 (gap min 63.5, median 95.7); funk 62/221 (gap min 48.94, median 63.0); indie 274/329 (gap min 46.5, median 130.0); jam 94/244 (gap min 66.97, median 124.2); livetronica 104/232 (gap min 49.51, median 131.2); southern 182/275 (gap min 61.52, median 141.4)
- **a symmetric +-15, full**: americana 63/329 (gap min 124.99, median 125.0); bluegrass 238/307 (gap min 1.0, median 3.0); dead 396/413 (gap min 1.0, median 18.0); dead-family 26/225 (gap min 48.96, median 49.0); dead-tribute 8/208; funk 62/221 (gap min 48.94, median 63.0); indie 87/329 (gap min 58.47, median 98.0); jam 9/244 (gap min 153.96, median 154.0); livetronica 10/232; southern 41/275 (gap min 62.0, median 93.0)
- **b full**: americana 181/329 (gap min 47.04, median 127.0); bluegrass 233/307 (gap min 45.0, median 65.5); country 1/2; dead 404/413 (gap min 1.99, median 47.0); dead-family 5/225; dead-tribute 208/208 (gap min 2.86, median 47.0); funk 148/221 (gap min 47.04, median 92.0); indie 217/329 (gap min 45.0, median 77.0); jam 70/244 (gap min 46.08, median 70.0); livetronica 75/232 (gap min 59.0, median 132.0); southern 141/275 (gap min 46.0, median 70.0)
- **b excl-17**: americana 180/329 (gap min 47.08, median 108.0); bluegrass 238/307 (gap min 45.0, median 76.0); country 1/2; dead 395/396 (gap min 4.34, median 46.5); dead-family 4/225; dead-tribute 208/208 (gap min 6.0, median 47.0); funk 153/221 (gap min 47.04, median 94.4); indie 213/329 (gap min 45.0, median 79.0); jam 68/244 (gap min 46.08, median 86.0); livetronica 73/232 (gap min 52.06, median 135.4); southern 137/275 (gap min 45.0, median 95.4)
- **c delivered full**: dead 403/413 (gap min 1.0, median 10.0); funk 91/221 (gap min 1.01, median 21.0)
- **c delivered excl-17**: americana 192/329 (gap min 63.0, median 174.0); bluegrass 150/307 (gap min 50.0, median 99.0); dead 384/396 (gap min 45.0, median 50.5); dead-family 55/225; dead-tribute 60/208 (gap min 56.93, median 56.9); funk 94/221 (gap min 1.0, median 21.0); indie 224/329 (gap min 45.06, median 165.9); jam 88/244; livetronica 76/232 (gap min 51.92, median 145.9); southern 145/275 (gap min 51.0, median 129.9)
- **c eligible full**: americana 2/2 (gap min 6.0, median 16.0); bluegrass 2/2 (gap min 1.99, median 12.5); dead 113/113 (gap min 1.0, median 32.5); funk 45/89 (gap min 1.0, median 12.0); indie 18/18 (gap min 1.0, median 13.0)
- **c eligible excl-17**: americana 2/2 (gap min 1.19, median 12.0); bluegrass 2/2 (gap min 1.03, median 3.5); dead 112/112 (gap min 1.01, median 30.0); funk 46/89 (gap min 1.0, median 11.9); indie 18/18 (gap min 1.0, median 7.0)

### The Dead blocks, with and without the 17

Fill share and own-profile share of the block named (fill = shows from the open pool because own shows could not land the
next window):

| run | block | fill share | own-profile share |
|---|---|---|---|
| a full | dead-am | 0.0% | 100.0% |
| a full | dead-pm | 0.0% | 100.0% |
| a excl-17 | dead-am | 0.0% | 100.0% |
| a excl-17 | dead-pm | 40.9% | 59.1% |
| a +-15 full | dead-am | 0.0% | 100.0% |
| a +-15 full | dead-pm | 0.0% | 100.0% |
| b full | dead-morning | 0.0% | 100.0% |
| b full | dead-evening | 0.0% | 100.0% |
| b excl-17 | dead-morning | 0.0% | 100.0% |
| b excl-17 | dead-evening | 0.0% | 100.0% |
| c delivered full | dead-morning | 0.0% | 100.0% |
| c delivered full | dead-evening | 0.0% | 100.0% |
| c delivered excl-17 | dead-morning | 0.0% | 100.0% |
| c delivered excl-17 | dead-evening | 46.5% | 53.5% |
| c eligible full | dead-morning | 0.0% | 100.0% |
| c eligible full | dead-evening | 26.8% | 73.2% |
| c eligible excl-17 | dead-morning | 0.0% | 100.0% |
| c eligible excl-17 | dead-evening | 42.0% | 58.0% |

Overnight-tribute on b is 100% own, 0% fill in both runs. Every row above is from the committed JSON.

- **Full library, clock a**: dead-am and dead-pm have no fill, but the repeat gap shows the cost: Dead min 1.0 day, median 13,
  403 of 982 repeats inside a week. These come from the 12-hour dead-pm block (19:00 to 07:00), which only the doubled
  packages can land from own shows.
- **excl-17**: Dead repeats drop to min 45 days (the 45-day concert gap holds, no gap bend needed), 396 of 396 Dead shows
  aired, median 52 days. The price is fill: **dead-pm fill share 40.9%, own-profile share 59%** on clock a, and
  **dead-evening 46.5% / 54%** on clock c delivered (42% / 58% eligible). dead-am is unaffected (0% fill, still lands from
  own shows once the lone doubled lander is gone, because fresh pairs land it).
- The 12-hour blocks (a's dead-pm 19:00 to the next 07:00 on a week night, c's dead-evening 20:00 to 08:00) are where the
  shrinking library will show first: own shows rarely land a 12 h window in two shows, so the block falls to structural fill
  from indie, americana and southern (a: 129k fill minutes over 50 weeks excl-17, versus 36k full).

## Naive baseline (clock a)

`naive_filler.py`: the parent's feasibility-sim edited as the spec lists (root argument; anchors and the 15-minute window
read from `clock-a.toml`; `exclude_profiles` from `[open]`; separate overran / not-fillable counts; the scheduler's length
estimates via the same scan; 50 seeds; JSON). 2,786 shows, 23 anchors per week, 22 gaps per seed, 1,100 gaps: overran
15, not fillable 17. It keeps the original's simplifications (one random show per anchor,
4,000-try random fill, no join gaps, one week and no history per seed).

## Caveats

- The comparison is not fully like-for-like in the scheduler's favour: `max_shows` 2 (up to two own shows per block), real
  2 s gaps, 50 weeks of history, versus the naive one-show anchors with no gaps or history.
- Estimates only: lengths come from manifests and clip headers, not decoded audio. Zero misses is a statement about
  estimated lengths; the live planner's exact-count re-run will move landings.
- No interstitials, so IDs and announcements (and their effect on landing) are unmeasured.
- Misses are visible to the instrument (a 6-show pool against clock a gave 44 misses in 46 starts).

## Anything surprising

1. **Funk concentrates on clock c, for a structural reason.** Clock c delivered: funk aired 91/221, median repeat gap 21.0 d,
   230 repeats inside a week. The funk block runs 14:00 to 20:00 (360 min) at the default `max_shows` 2, and only the 8 funk
   shows of 183 min or longer can complete a landing pair; the top three by sub-week repeats are newmastersounds-2008-01-18,
   robertrandolph...-2004-07-25 and bluestraveler-1991-01-05. In 307 of 351 blocks no in-window option keeps the gap, so the
   compromise order correctly prefers landing over rotation: a library/clock limitation, not a defect. **Reviewer probe
   figures (scratch copy, not a committed run):** `max_shows = 3` on that block alone gives funk 221/221 aired, gap min 45 d,
   median 60 d, none within 7 d, no misses and no fill. Clock a's funk block (22:30 Saturday only) is fine at 61/221, 49-day minimum.
2. With the 17 excluded on clock b the Dead gap minimum is 4.3 days and there are 4 repeats inside a week (b full: min 2.0,
   4); b's overnight tribute and open blocks keep the pool moving.
3. Country is 2 packages and never dominates a figure.
4. Clock c eligible (224 voiced): 13.4% fill, of which 21.6k minutes `pool-short`; indie (18 voiced shows) is almost all of
   the fill. Dead aired 113 of 113 with a 32-day median gap.
5. Excl-17 raises clock a fill from 7.1% to 25.7% and clock c delivered from 0% to 23.3%: the exclusion is the cheapest
   large lever on how much of the schedule is non-Dead fill.
6. **Clock a at symmetric +-15 concentrates bluegrass** (the Mon-Sat 12:00 to 19:00 block): only one pair lands it,
   leftoversalmon-2000-01-28 + yondermountainstringband-2014-02-16, and those two shows account for 295 of the 301 bluegrass
   repeats under 7 days (summary: 238/307 aired, median gap 3.0 d). Under [0, +15] no pair lands, so the block goes to fill
   (20%) and bluegrass keeps a 54.5-day median. In short, +-15 fixes landing but hurts rotation. Operator design question:
   whether repeated gap breaks should eventually yield to fill rather than keep airing the one landing pair.
