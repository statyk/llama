# Task 8 fix round 1: handback

Status: **DONE**. One commit, `392dfde` on `playout-scheduler`. It is green on `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`: **748 passed, 1 skipped**.

As instructed, I left these unchanged: deviations 1, 2 and 4, the search bound, the module layout, `used`, the `start_frame` contract and `show_bends`.

## Changes (`scheduler.py`)
1. **The fill cause is now judged from the block's own start.**
   - `fill_block` works out the cause once per call:
     - `block_start = start_frame - Σ(p.frames + boundary_frames for p in placed)`.
     - It then lays out the `max_shows` longest shows of the whole own pool (placed own shows included) from that start.
     - If they land before `lo` the cause is "structural". Otherwise it is "pool-short", including when the pool holds fewer than `max_shows` shows.
   - The cause is attached only when the plan has fill.
   - Because it is computed from the block start, every re-run and every live continuation reports the same cause.
   - `_Step` no longer carries a cause, and the old per-step `_fill_cause` arguments are gone.
2. **`_has_fill(own_slugs, placed)`** now tests `p.slug not in own_slugs`. This is the same own-pool definition the rest of the code uses.
3. **`_C`** reads `piece.year` and `piece.month_day`. The import of the private `pieces._date_parts` is removed.

## Tests (`test_scheduler_block.py`), each written first
- `test_fill_cause_is_judged_on_the_whole_own_pool_from_the_block_start`
  - Uses the reviewer's example: own a=60, b=150, c=140; fill f=28; max_shows 2; next block at +4 h ±15.
  - The plan is `a, b, f`, tier 1, `fill_from == 2`, cause "pool-short".
  - The continuation with `a`, and the one with `a, b`, return the rest of the plan with the same cause.
- `test_structural_cause_is_judged_from_the_block_start`
  - Four 60-min own shows, next block at 165 ±15.
  - The cause is "structural", and stays "structural" in both continuations.
  - Judged from after the first placed show, it would wrongly read "pool-short".
- `test_structural_cause_holds_through_a_continuation`: a guard on the existing structural case.
- `test_own_membership_is_the_own_pool_not_the_profile_field`
  - A placed show is in `own_pool` but its profile field differs.
  - It is not treated as fill, so an own show still follows it at tier 0.
  - I also updated `test_placed_shows_supply_the_previous_artist` so its placed show is in the own pool, as callers pass it.
- `test_every_offered_option_counts_and_scores_as_rules_does` (item 2)
  - It spies on every `_Tier.offer` from `fill_block`'s first run and checks every option:
    - its violations equal `rules.violations` exactly;
    - its surplus terms equal `rules.score - 1` exactly.
  - It covers five blocks:
    - a dead pair block;
    - a 10 h open block (greedy prefixes);
    - a jam block with max_shows 3;
    - a tier-1 fill block;
    - a tier-2 miss.
  - The inputs exercise the rules: history with same-day artists, year preferences, an on-this-day override, and on-this-day shows placed in partner slots on both sides of local midnight.
  - It asserts that single, pair, three-or-more, fill and on-this-day-partner options all occur.
  - It runs in about 0.12 s.
- `test_candidate_view_matches_the_piece` (item 2 and item 4): a candidate's year, month-day, artist, package and frames equal the piece's, and `_Ctx.score` equals `rules.score`.

## RED / GREEN
- **RED**, logged in `task8-fix1.log`: before the fix, the block-filling tests gave 2 failed, 38 passed.
  - `test_fill_cause_is_judged…` failed with `assert 'structural' == 'pool-short'`.
  - `test_own_membership…` failed with `assert ([] == ['b'])`.
- **The agreement tests are guards**, so they passed against the old code too. To show they detect errors, I ran mutants in scratch copies, with a sentinel confirming the copy was the one imported:

  | mutant | result |
  |---|---|
  | pairs: era same-day clause dropped | caught by the offer-level test |
  | pairs: artist-day same-day clause dropped | caught by the offer-level test |
  | pairs: partner on-this-day boost dropped | caught by the offer-level test, after I added the on-this-day partner shows |
  | candidate month-day wrong | caught by `test_candidate_view…` |
  | old cause from `start_frame` | caught by `test_structural_cause_is_judged_from_the_block_start` |
  | pairs: the prefix-package check | survived |

  The check that survived cannot be reached: no show plays twice in one block, so the prefix's packages are never candidates.
- **GREEN**: the block-filling and rules tests give 53 passed. The full suite gives **748 passed, 1 skipped in 18.78s**.

Command: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`
