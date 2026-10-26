# Task 8 review: scores, rules and `fill_block`

### Spec Compliance

**Mostly compliant, with one spec-defined output that is wrong and one unratified deviation from the compromise order.** Both are fixable in a small amount of code or settled by a ruling.

What matches the spec and brief, checked against the diff and by probe:
- **Score:** recency term, `years` ranges, on-this-day by the slot's local month-day (block override, else global), gap 0 disabled.
- **`violations`:** all four rules. Adjacency carries across the block boundary through `prev_artist`, or through `placed[-1]` when there is a prefix. Gap counts "within the gap" or "twice in this sequence". `artist_day` and era use the slot's local date.
- **Tiers 0, 1 and 2:**
  - Tier 1 runs only when tier 0 is empty.
  - The one-own-show floor holds.
  - Open and degraded blocks have no tier 1.
  - Degraded blocks are unbounded.
  - `placed == max_shows` yields a no-show option.
  - There is always an option, unless both pools are empty; that case raises `PlanError`.
- **Bends:** a bend counts only when a kept option existed. Bends follow the `RULES` order.
- **Search bound:** 32 × 64, bisected landing range, ≤ 5 tier-1 prefixes.
- **Determinism:** holds.

Process: I reviewed in three passes (rules/planner, scheduler, tests and fixture). I then ran probes against scratch copies at 5acb9f5 (`git archive`, imports proven to resolve inside the copies):
- a 12,144-call battery over the fixture: 11 profiles × 23 block lengths × wiggle × max_shows × prefs × 3 histories × prev_artist;
- an offer-level violation-agreement probe;
- two alternative-formula copies, for the operator examples.

⚠️ The diff cannot show whether Task 9 will meet `fill_block`'s implicit contracts:
- `start_frame` is after `placed` plus a boundary.
- `rec` must already include `placed`, every persisted-but-unaired row and every earlier projection pick.
- `fill_from` indexes the added shows.
- `show_bends` is per row.

### Strengths
- **The continuation closure (decision 2) is a real result, not a claim.**
  - In the battery, the per-show re-run changed the first run's choice in 306 of 12,144 blocks.
  - None of those changes was a worse tier: 88 tier 0 → tier 0, 206 tier 1 → tier 1, and 12 miss → fill.
  - It is pinned by two parametrised continuation tests on the fixture.
- **The inline pair counting matches `rules.violations`.** The pair search keeps a hand-inlined copy of the rule counting (`scheduler.py:348ff`). I checked 9,254 sampled offered options, singles, pairs, chains and tier-1 fills, including blocks crossing local midnight, against `rules.violations`: 0 mismatches.
- **No false bends:** across 12,144 blocks, no reported bend names a rule the final sequence does not violate.
- **Timing is well inside the budget:**
  - battery mean ≈ 1 ms per call;
  - `test_fill_block_is_fast_on_a_3000_piece_pool` takes 0.35 s against its 2 s bound.
- **Clean test output:** the 49 Task 8 tests pass with no warnings and no noise.
- **The fixture matches the spec's Intent table:**
  - medians are exact for every profile;
  - dead p10/p90 is 132.9/212.4 against the measured 136/213;
  - Dead is a single artist, and country is the real 2-show scarce pool;
  - 300 unique slugs;
  - the generator is stratified and deterministic, and a test pins byte-identity.
- **Infinite weights and huge gaps are handled and tested.** `fsum` makes a pair and its swap tie exactly.
- **The handback is unusually honest:** a mutation pass, survivors named and explained, and the cross-task `used` concern raised unprompted.

### Issues

#### Critical
None.

#### Important

**1. `fill_cause` reports "structural" for a block that is actually pool-short whenever fill follows two or more own shows** (`scheduler.py:571`, `scheduler.py:648-660`).
- **What:** `_fill_cause` is evaluated at the re-run step whose first show is fill. By then the own shows chosen earlier are in `placed`, so `need = max_shows - len(placed)` is 0. The "landing" it tests is then just the end of the placed prefix, which is before `lo` by construction (fill was needed). So whenever a block reaches `max_shows` own shows before its fill, the cause is "structural", whatever the pool could do.
- **Brief's definition:** "structural when the `max_shows` longest own candidates together still land before lo, else pool-short".
- **Reproduced:**
  - Setup: own shows a = 60, b = 150, c = 140 min; fill f = 28 min; profile block, `max_shows` 2, next block at +4 h ±15.
  - The plan is `a, b, f`, tier 1, `fill_cause="structural"`.
  - But the two longest own shows (150 + 140 = 290 min) overrun the window, so per the brief it is **pool-short**.
  - Across the battery, 24 of the 1,032 tier-1 blocks are misreported this way. None goes the other direction.
- **Why it matters:** the spec says "Only 'pool short' is a compromise". This bug hides real compromises in `schedule`/`status` reporting. No test covers fill after two or more own shows with a pool-short cause:
  - `test_fill_with_long_own_shows_that_cannot_combine_is_pool_short` has `fill_from == 1`;
  - the other pool-short test has fewer own shows than `max_shows`.
- **Fix:** compute the cause once per call from the block's own start, so it is the same on every re-run and in a live continuation:
  - `block_start = start_frame - Σ(p.frames + boundary for p in placed)`;
  - test whether the `max_shows` longest shows of `own_all`, including placed own shows, land before `LO`.
  - Add the example above as a test.

**2. A block never plays the same piece twice (handback decision 6). This departs from the brief and from the operator-confirmed compromise order, and nobody has ruled on it** (`scheduler.py:488-492`, and `_taken` in `_Search`).
- **The brief** expects within-block repeats to be possible: "drop pieces in `used` only when the pool has other candidates (else allow, the gap rule then counts it)", and gap includes "twice in this sequence".
- **The spec's order:** "a block filled from its own profile always beats one that keeps a rotation rule by using fill". That makes `(a, a)` in tier 0 beat `(a, fill)` in tier 1.
- **The implementation** gives `(a, fill)` in tier 1, or an early miss when there is no fill pool. `test_a_block_never_plays_one_piece_twice` asserts that tier-2 early landing.
- **This is live today:** the spec's Intent table has americana at 1 voiced show and bluegrass at 2. A one-show own pool in a two-show block is the normal case for such a block.
- **My view:** the implementation's behaviour is what a listener wants. Hearing the same concert twice back to back is worse than one fill show. But it reorders an operator-confirmed order, so it needs a ruling.
- **Fix:** add it to the operator's ruling list. If accepted, no code change is needed, and the spec's compromise-order paragraph should record the exception. If rejected, allow a repeat as a last resort inside tier 0.

#### Minor

1. **`bends` and `show_bends` are unions of per-step bends** (`scheduler.py:565-569`). Each step's bends describe that step's projected option, so a rule bent only in a projection that a later step abandoned could be reported. Measured 0 instances in 12,144 blocks, but nothing in the code prevents it. Also, `show_bends[i]` includes every later show's bends: if Task 9 writes `show_bends[i]` on row i and `status` sums rows, one bend counts once per earlier row. Task 9 needs to define per-row attribution, e.g. the rules the show itself violates that its step's tier kept.
2. **The rule logic exists three times** and the score logic twice:
   - rules: `rules.violations`, `_Ctx.viol`, and the inlined copy in `_Search.pairs`;
   - score: `rules.score`, plus `_Ctx.score` and its inline copy in `pairs`.
   - `test_violation_counts_agree_with_rules` only exercises `_Ctx.extend`/`viol`, not the `pairs` copy (my probe did, and it agreed).
   - Fix: add an offer-level agreement test (hook `_Tier.offer` the way the probe did) and a score-agreement test, so a later edit to one copy cannot drift silently.
3. **`scheduler.py` is 671 dense lines** of `__slots__` micro-structures, nested closures and the inlined rule copies. It is already hard to hold in one's head, and Task 9 appends "part 2" to the same file. Fix: move the block search (`_C`, `_Seq`, `_Tier`, `_Ctx`, `_Pool`, `_Search`, `fill_block`) into its own module before Task 9 adds to it. `rules.py` (147 lines) is fine.
4. **Two definitions of "own" that can disagree.** `_has_fill` (`scheduler.py:495`) tests `p.profile not in occ.block.profiles`, while own membership elsewhere is `own_slugs`. They agree only if Task 9 builds `own_pool` by `Piece.profile`, which falls back to `source.profile` (pieces.py:191). Fix: test `p.slug not in own_slugs`.
5. **`_C` imports the private `pieces._date_parts`** instead of using `Piece.year` and `Piece.month_day`. This was done for speed, but it couples the scheduler to a private helper.
6. **The 3,000-piece speed test is wall-clock bound at 2 s.** It takes 0.35 s here; hugo's Python 3.11 will be slower. There is margin, but it is a flakiness risk to keep an eye on.
7. **Handback concern 5 (open blocks and on-this-day):** under the surplus, each on-this-day show adds +3, so an open block keeps adding on-this-day shows toward its late edge. This is legal; the operator should know when ruling on deviation 1.

### Deviations
- **(1) value = `fsum(score − 1)` − distance, not `mean(score)` − distance:** accept as spec-consistent; operator ruling pending.
  - The spec says "prefer higher summed score". The plan's mean was a builder call to honour Goal 2.
  - Goal 2's "at most two" is still enforced by `max_shows` (default 2) on profile blocks.
  - The implementer's rationale holds: a placed show's score cannot be recomputed after it enters `rec`, so a mean has no stable value for a continued block.
  - Cost: positive `prefer` and on-this-day weights now favour more shows (example below).
- **(2) tier 1 ranks own-show count first:** accept as spec-consistent. Goal 3 says fill is "a compromise to minimise", and the operator ruling says own profile first. Operator ruling pending (example below).
- **(3) rule-aware greedy:** accept. The spec says rules bend only when needed, and a score-only greedy commits every longer option to a break.
- **(4) a block never plays a piece twice:** reject until ruled (Important 2).
- **(5) one search run per added show:** accept. It is what makes live and projection agree, and it is measured never to worsen the tier.
- **(6) tie-break on every show's tie rank:** accept. It is harmless and deterministic.
- **The `start_frame` contract** (after `placed` plus a boundary) and the extra `show_bends` field: accept. Task 9 must honour them (see Minor 1).

**(g) The `used` contract (my view).** The implementer is right that the current shape breaks live/projection symmetry. The right contract is that **`rec` and `used` are built from the same set**:
- every show placed before this occurrence that is not yet in `aired.jsonl`, i.e. persisted-but-unaired plan rows plus earlier projection picks;
- each one goes into `rec` via `with_piece` at its start and local date, so recency, gap, `artist_day` and era see it, and into `used`.

A live step and the projection then see identical candidate sets and rule counts. Dropping `used` and relying on the gap rule alone is not enough: with `concert_gap_days = 0` the gap rule is off, and the same show could then air in consecutive blocks. This is also a precondition for the rules to work at all. A `Recency` built from `aired.jsonl` alone cannot see the hours of persisted lead, so without this the gap and same-day rules would ignore everything already planned. This belongs in Task 9's brief.

### Concrete examples for the operator

All examples are from the 300-show fixture library, starting at 18:00 local on 2026-11-02, with a 2 s inter-show gap and no IDs. Scores include recency (1.0 never aired, 0.9 aired long ago) and any `prefer` weights. The alternative formulas were run only in scratch copies of 5acb9f5.

**(1) Surplus versus mean.** Across 12,144 battery blocks, 1,064 pick a different set of shows. The surplus picks more shows than the mean in 374 and fewer in 60; the other 630 have the same count but different shows. Most of the differences (782 of 1,064) come from runs with `prefer` weights. Two cases from default-shaped profile blocks (`max_shows` 2):

- **(1a) Surplus picks more shows.**
  - Block: americana, next block at 20:30 ±30 min, `prefer` 1972–1977 (+0.6) and 2010–2019 (+0.3), nothing aired yet.
  - Candidates: Gillian Welch 2012-09-20 (85.5 min, score 1.3), Drive-By Truckers 2012-04-10 (79.8 min, 1.3), Old Crow Medicine Show 2013-04-29 (146.0 min, 1.3).
  - **Surplus** picks Gillian Welch + Drive-By Truckers: 2 shows, 165.3 min, landing **+15.4 min** (value 0.6 − 0.257 = 0.343, against 0.235 for the single).
  - **Mean** picks Old Crow alone: 1 show, 146.0 min, landing **−3.9 min** (value 1.3 − 0.065 = 1.235, against 1.043 for the pair).
  - In general, each preferred show adds its weight under the surplus, so a +0.3 weight per show outweighs about 18 min of landing drift on a ±30 window.
- **(1b) Surplus picks fewer shows.**
  - Block: americana, next block at 20:45 ±30 min, no `prefer`, about 60% of the library aired in the last 120 days.
  - Candidates: Son Volt 1998-02-09 (169.0 min, 1.0), Gillian Welch 2012-09-20 (85.5 min, 0.9, aired), Drive-By Truckers 2012-04-10 (79.8 min, 1.0).
  - **Surplus** picks Son Volt alone: 1 show, 169.0 min, landing **+4.1 min**. Each aired show costs −0.1, so the single scores −0.068 against −0.107 for the pair.
  - **Mean** picks Gillian Welch + Drive-By Truckers: 2 shows, 165.3 min, landing **+0.4 min** (0.943 against 0.932).

**(2) Own shows first in tier 1 versus the brief's order** (violations, then value, then tie rank). Across the battery, 480 blocks differ. **All of them are country**, the 2-show pool, in blocks of 4 h 45 or longer. Every other profile's tier-1 choices are identical under both orders. In every case the difference is 2 own shows plus fill against 1 own show plus fill. Example:
- Block: country, `max_shows` 2, next block at 22:45 ±15 min, nothing aired, all options clean of rule breaks.
- Candidates: Wayne Hancock 2012-10-17 (109.2 min, 1.0), Hank Williams III 2006-02-19 (143.1 min, 1.0), and open-pool fill including Godspeed You! Black Emperor 2000-01-17 (indie, 46.1 min, 1.0), Godspeed You! Black Emperor 2005-05-28 (indie, 104.2 min, 1.0) and Lettuce 2017-05-31 (funk, 71.5 min, 1.0).
- **Own shows first** picks Hancock + Williams + the 46-min Godspeed: 3 shows (2 country, 1 fill), 298.4 min, landing **+13.5 min** (window +15).
- **Brief's order** picks Hancock + the 104-min Godspeed + Lettuce: 3 shows (1 country, 2 fill), 284.9 min, landing **0.0 min**, which wins on the distance term.

### Assessment
**Task quality:** Needs fixes

**Reasoning:** The core is sound. The tier logic, rule counting and bend accounting are correct by probe across about 12k blocks, the search is fast, and the continuation-closure design is a genuine improvement that is measured never to worsen a choice. Two things stop approval:
- `fill_cause` misreports pool-short blocks as structural, a spec-defined compromise signal (24 of 1,032 tier-1 fixture blocks). The fix is small and needs a test.
- The no-repeat rule reorders the operator-confirmed compromise order and needs a ruling (probably accept).

Deviations (1) and (2) are spec-consistent and are with the operator, with the examples above. The Minor items, especially per-row bend attribution and the `rec`/`used` contract, should be carried into Task 9's brief.
