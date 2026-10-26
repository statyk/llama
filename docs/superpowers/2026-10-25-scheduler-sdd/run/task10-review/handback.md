### Spec Compliance

**Partly compliant.** The measurement machinery does what the spec's Measurement section asks: one continuous `project` per clock from an empty plan at a block's nominal start, history accumulating, all five reported figures, a like-for-like naive baseline built with the spec's edits, and strictly read-only access to the library. The floor check (clock a: 0.0% vs 2.9%) is correct and holds by a wide margin. The evidence doc's diagnosis of the Dead repeats is wrong, though, and the operator would read it before the go/no-go. The repeats come from a **scheduler defect** (Task 8 ranking) together with a **library defect** (17 Dead packages carry every track twice). They are not the compromise order "squeezing the usable dead shows to a few dozen". With one ranking change, clock (a) airs **384 of 413** Dead shows in 50 weeks instead of 39, with 0 misses and the same own-profile share.

### Strengths

- `measure()` matches the brief: a single `project(..., until_frame=span, ahead=2)` from `rows=()` and `Recency()`. Weekly figures are slices keyed on each row's occurrence `nominal_start`. Misses come from first-show rows (`miss is not None`). Bends are summed per row, which is correct because `PlannedPiece.bends` writes each bend once per block. Fill is split by cause, own-profile share is taken per profile block, and repeat gaps are measured by slug. I re-ran clock (a) for 50 weeks from my own read-only scan and got **every figure identical**: 1151 starts, 0 misses, bends {era 10, gap 347}, 92.4% own-profile, 39/413 Dead shows, the same repeat buckets.
- The naive script is a faithful edit. It takes the root as an argument, reads its anchors and the 15-minute window from clock-a.toml, counts `overran` and `not_fillable` separately with no x1000 weight, reads the fill exclusion from `[open] exclude_profiles`, runs 50 seeds and writes JSON. Its lengths come from the same `scan_delivered` pickle as the scheduler's, so the estimates are identical. The edit also fixes the original's funk anchor time (21:00 in code, 22:30 in the comment and the spec). The like-for-like caveats are stated honestly.
- Nothing was written to the library or to an analysis cache. `scan_delivered` and `station.scan` only read. `LengthCache(None, ...)` never touches the cache. `extra_frames()` encodes synthetic silence through pipes.
- Zero misses is plausible, not a counting artefact. Each occurrence gets at least one show, block starts equal the occurrence count, there are no interstitials (so no occurrence starts with a clip), and the projection runs to `until_frame` plus 2 occurrences. The implementer's 6-show sanity run showed that misses are visible when they happen.
- The implementer raised the Dead-repeat finding instead of burying it, and the bend counter (gap 347) pointed straight at it.
- Both scripts and the test parse under the Python 3.11 grammar (`ast.parse(feature_version=(3,11))`). The smoke test passes.

### Issues

#### Critical
None in Task 10's own code. The scheduler defect diagnosed below is Critical **for Task 11** (go-live), not for this task.

#### Important
1. **`docs/superpowers/2026-10-25-scheduler-measurement/evidence.md`, "Anything surprising" item 1: the explanation is wrong and the numbers are mislabelled.**
   - "Median repeat gap 5 days, p10 1.8, 824 of 1,540 repeats inside 7 days" are station-wide figures (`total.repeat_gap_days` covers every profile), but the doc presents them as Dead figures.
   - On clock (b), "median 46 days" is also station-wide, and "leaving the Dead blocks the same two" is a guess with no support.
   - "Consistent with landing-in-window squeezing the usable dead shows to a few dozen" is refuted. 6,950 never-aired Dead pairs land each dead-am window, and the scheduler passes them over (diagnosis below).
   - Fix: fold in the diagnosis below, and report repeat gaps per profile (at least Dead). Then, once Task 8's ranking is fixed, re-run a/b/c and replace the tables. The present numbers describe a defect, not the design.

#### Minor
2. **`packages/transmitter/scripts/measure_scheduler.py:134`: weeks are UTC 7-day spans.** `week_of` subtracts UTC microseconds, so after the March 2027 DST change the Monday 07:00 EDT dead-am falls inside week 49. That gives dead-am 351 starts and 1151 in total instead of 1150, and the doc never explains the extra start. It does not affect the floor check. Fix: either compute weeks from local dates, or add a note to the doc.
3. **`measure_scheduler.py:165-166`: the `--scan-cache` pickle is not keyed by `--library` or `--root`.** Reusing one path with `--library eligible` silently loads the delivered pool. The implementer used separate files (results-c-eligible shows pool = 224), so the results are fine. Fix: store `(root, library)` in the pickle and refuse a mismatch.
4. **`measure_scheduler.py`: no per-profile repeat-gap output.** This is the figure that would have exposed the defect directly. Add `repeat_gap_days_by_profile`.
5. **`tests_transmitter/test_measure.py`: the smoke test checks keys, counts and time only.** That is what the brief asked for. A run where `distinct dead == 2` would still pass, so it is no guard against a repeat regression. Optional.

### Dead-repeat diagnosis

**Root cause: a defect, not the design.** Options within a tier are ranked lexicographically on per-rule **violation counts** (adjacency, gap, artist_day, era), and those counts are **summed over the option's shows**. In a single-artist pool (all 413 `dead` packages are "Grateful Dead"), every additional show adds one unavoidable adjacency violation and one unavoidable artist_day violation. As a result, **a one-show option beats every two-show option on adjacency count before the gap rule is ever consulted.**

dead-am (300 min, window [0, +15]) can be landed by a single Dead package in only about 2 cases (6 with ±15). The scheduler picks one of those singles every day, so it airs again 1–2 days later. The 6,950 fresh pairs that land the same window are never chosen.

- Code: `_blocksearch.py:188-200` (`_Ctx.viol`) and `:357-368` (`_Search.pairs`, the same count inline), compared in `_Tier.offer` at `:122-124` (`head = (pre, viol)`).
- The spec says a rule the pool makes impossible "is not applied within that pool at all". The plan (Task 8, "Bends") turned that into "is not reported as a bend" only, and the code follows the plan. The ranking still applies the impossible rules.

**The concrete block** (clock a, dead-am, Wed 2026-11-04 07:00 EST, prev_artist "Grateful Dead"). I enumerated every in-window option exhaustively:

| | shows (estimated min, last aired, score) | landing | tier | violations (adj, gap, day, era) | value |
|---|---|---|---|---|---|
| **Chosen** | gratefuldead-1966-12-01 (299.3, aired 1.0 d ago, 0.020) | +1.3 min | 0 | **(1, 1, 1, 0)** | −1.024 |
| Best fresh pair | gratefuldead-1986-07-04 (112.3, never aired, 1.0) + gratefuldead-1977-11-04 (186.5, never aired, 4.0 incl. on-this-day) | +0.9 min | 0 | (2, 0, 2, 0) | **+2.971** |

All 12,830 in-window pairs keep the gap rule. The single wins on adjacency count (1 < 2), the first lexicographic key, so the rule that decided is adjacency. The same thing happens on 11-06 (1966-12-01 again) and on 11-07 (1989-07-18, aired 1.2 days earlier).

**Candidates ruled out by probe:**
- (2) Search bound: the exhaustive best pair is not what was passed over by bounding. With the fix, the bounded search finds fresh pairs every day.
- (3) Recency and score: `with_piece` records projected picks (last aired = 1.0 d), the score is 0.02 vs 1.0, and the 24 h `used` window releases the show exactly at 24 h, as designed. The gap rule was the next guard, and the adjacency count outranks it.
- (1) The tight window: not the cause. The defect reproduces with ±15.

**Library defect (candidate 4 is real, but it is upstream).** The packages that land dead-am alone (about 300 min) and the only own-only pairs that land clock (a)'s 12-hour dead-pm block are **17 Dead packages that list every track twice**: consecutive identical titles, e.g. `01 - New Minglewood Blues.mp3`, `02 - New Minglewood Blues.mp3`. The 17 are:
1966-12-01, 1968-10-13, 1969-04-21, 1974-05-25, **1974-09-11 (voiced)**, 1978-12-30, 1987-06-30, 1987-07-06, 1988-03-27, 1988-06-23, 1989-07-18, 1989-08-19, 1990-03-16, 1990-07-14, 1991-04-05, 1991-10-31, 1995-03-18 (272–424 min).

They would air every song twice. This is a llama packaging defect for the operator, independent of the scheduler.

**Residual, as designed.** Clock (a)'s dead-pm and clock (c)'s dead-evening are 12-hour blocks with `max_shows` 2. Only about 5 own-only pairs land a 12-hour window (14 with ±15), all built from doubled packages, and the compromise order correctly puts own-in-window ahead of the gap rule. With the fix, these still repeat every few days, and no gap bend is counted because no option keeps the rule. Once the doubled packages are fixed, those blocks will fall to structural fill instead.

**Smallest fix (prototyped in a scratch copy, about 10 lines).** When a profile block's own pool has exactly one artist, do not count adjacency or artist_day for that artist. That means adding a flag on `_Ctx`, set in `_BlockRun.__init__`/`_advance` (`scheduler.py:76-127`), and checking it in `_Ctx.viol` and `_Search.pairs`. `rules.violations` needs the same exemption, because the parity test `test_every_offered_option_counts_and_scores_as_rules_does` fails without it (it was the only real failure: 796 passed). A regression test should cover a single-artist pool where a recently aired single and a fresh pair both land: the pair must win.

A more general form would rank on violations beyond the unavoidable minimum for the option's show count; the mono-pool rule is the spec's own wording. This is a ranking change in Task 8's code, so it goes to the controller or operator as a scheduler fix before Task 11.

**Measured effect, 50 weeks, estimates, read-only** (original → fix; misses 0 in every run):

| run | Dead aired /413 | gap bends | own-profile share | station repeat-gap median |
|---|---|---|---|---|
| a, [0, +15] | 39 → **384** | 347 → 0 | 92.4% → 92.9% | 5 d → 46 d |
| a, ±15 | 50 → **396** | 342 → 0 | 95.9% → 96.2% | 4 d → 15 d |
| b | 38 → **404** (8 wk: 31 → 163; repeat gap min 1.0 → 8.85 d) | 663 → 41 | 100% | 46 d → 50 d |
| c (delivered) | 66 → **403** | 323 → 0 | 100% | 4 d → 11 d (funk 87 → 91: the funk block's own-only pairs, as designed) |

**The ±15 comparison.** The default symmetric window barely changes the picture under the current code: 50 vs 39 Dead shows, still about 342 gap bends a year. It only widens the set of lone landers from 2 to 6. The defect is independent of the window. After the fix, both windows give about 390 of 413. ±15 lowers fill (structural 18.5k vs 38.2k min) and raises own-profile share to 96%.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The scripts are sound, read-only, reproducible (I matched every clock-a figure independently), and the floor check is valid and passes. The evidence doc, however, presents station-wide repeat statistics as Dead figures and attributes the repeats to the compromise order, when they come from a Task 8 ranking defect (violation counts summed per show in a single-artist pool) plus 17 doubled-track Dead packages. The doc needs the corrected diagnosis and per-profile repeat gaps now. After the scheduler fix, it needs a re-run, because the current tables measure the defect. The go/no-go for Task 11 should wait for that fix: today the scheduler would air about 39 Dead shows a year, some of them doubled.

Probe scripts and outputs (scratch only): `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-scheduler/6a271170-52a3-49a3-b4db-a9d5cd08acfc/scratchpad/p3_block.py` (exhaustive block probe), `.../scratchpad/p2_run.py`, `.../scratchpad/p4_seq.py`, `.../scratchpad/r10/*.out`, and the fix copy at `.../scratchpad/fix/packages/transmitter/src/transmitter/{_blocksearch,scheduler}.py`. Log: `$D/task10-review/task10-review.log`.
