### Finding Verdicts

1. **(Important) Fill cause from the block start: ADDRESSED.**
   - The fix is at `packages/transmitter/src/transmitter/scheduler.py:538-540` (`fill_block`) and `:650-658` (`_fill_cause`).
   - The cause is computed once per call:
     - `block_start = start_frame - Σ(frames + boundary_frames)` over every placed show, fill shows included. That is the right inverse of the documented `start_frame` contract.
     - It lays out the `max_shows` longest shows of the whole own pool with internal `boundary` gaps and one `final`. This is correct when the two boundaries differ.
   - It is identical on every re-run within a call. A live continuation reproduces it as long as the caller keeps `own_pool` and `boundary_frames` the same (see Out-of-Scope).
   - `occ.max_shows` is always an int for a profile block (`clock.py:293-296`). Open and degraded occurrences get `None` and never reach the comparison.
   - The reviewer's example is now a test (`test_scheduler_block.py:258`) and returns `a, b, f`, tier 1, "pool-short", including both continuations.
   - Mutants (scratch copy; imports proven inside each copy):
     - `block_start = start_frame`: predicted RED `test_structural_cause_is_judged_from_the_block_start`. **Caught**, that test only.
     - Laying out the placed own shows as placed plus the longest of the rest (an alternative reading of the brief): **caught** by `test_fill_cause_is_judged_on_the_whole_own_pool_from_the_block_start`.
     - Excluding placed own shows from "longest" (passing `own_all` minus `placed`): predicted SURVIVE. **Survived**. See Minor test gap (a) below.
     - Dropping `boundary_frames` from the `block_start` subtraction: predicted SURVIVE. **Survived**, because every test has a 2 s GAP that is too small to cross `lo`. See (b).

2. **(Minor) Offer-level and score agreement tests: ADDRESSED.**
   - `test_every_offered_option_counts_and_scores_as_rules_does` (`test_scheduler_block.py:369`) spies on every `_Tier.offer` from the first run: singles, pairs, chain prefixes, tier-1 fills and tier-2 options. It asserts `viol == rules.violations` and `terms == rules.score - 1` for each, and asserts that every kind occurs, including an on-this-day partner.
   - `test_candidate_view_matches_the_piece` (`:411`) pins `_C` against `Piece` and `_Ctx.score` against `rules.score`.
   - I accept the implementer's mutation evidence for the pair clauses. I re-checked the reachability claim below.
   - Cosmetic: `assert landing == f - GAP + GAP` at `:402` is just `landing == f`. It only holds because the tests use `boundary == final`.

3. **(Minor) `_has_fill` by own-pool membership: ADDRESSED.**
   - `scheduler.py:497-499`, called at `:547` and `:567`.
   - A faithful revert to `p.profile not in occ.block.profiles` at both call sites was predicted RED `test_own_membership_is_the_own_pool_not_the_profile_field`. **Caught**, that test only.

4. **(Minor) `_C` no longer uses private `_date_parts`: ADDRESSED.**
   - `scheduler.py:51-52` reads `piece.year` and `piece.month_day`. The import is gone (`:27`).
   - Pinned by `test_candidate_view_matches_the_piece`.

**The surviving mutant (the pairs' in-block repeat check).** It is unreachable today, and would become reachable if deviation 4 is rejected.
- In `pairs`, `g.pkg in seq.pkgs` and `g.pkg == fp` (`scheduler.py:383`) can only fire when a partner shares a package with a show already in the sequence.
- A show piece's `package` is its `slug` (`pieces.py:74-75`; interstitials have `None`). Partners are filtered by `taken = excluded ∪ seq slugs`, and `c is f` is skipped. Own and fill pools are disjoint by slug. So no partner can repeat a package in the sequence.
- I ran both clauses as separate mutants: each **survived**, as predicted.
- `_Ctx.viol`'s `c.pkg in seq.pkgs` (`:213`) is a different case: it is **caught** by `test_violation_counts_agree_with_rules` through `_sequence_violations`.
- If the operator rejects deviation 4 (so a block may repeat a show), dropping the slug exclusion makes both pair clauses live. They are then the only thing that counts a within-sequence repeat as a `gap` violation, as `rules.violations` does via `seen` (`rules.py:133`). The required test would be an offer-level agreement case on a scarce pool with repeats allowed, asserting `viol == rules.violations` and `gap == 1` for the repeat:
  - a one-show own pool in a block needing two shows, which offers the pair `(x, x)` and pins `g.pkg == fp`;
  - and a `max_shows >= 3` case whose pair repeats a greedy-chain show, `(x, y, x)`, which pins `g.pkg in seq.pkgs`.
  - Each clause should be confirmed killed by its own mutant.

### New Breakage in the Fix Diff
None at Critical or Important level.

Minor test gaps (the fix is correct; these behaviours are just not pinned):
- **(a) "Whole own pool, placed own shows included" is not pinned.**
  - The mutant that excludes placed own shows from "longest" passes all 53 tests.
  - The existing reviewer-example test never leaves enough unplaced own shows to tell the two apart.
  - Measured fix: add two 30-min own shows (`d0`, `d1`) to `test_fill_cause_is_judged_on_the_whole_own_pool_from_the_block_start`. The plan stays `a, b, f` / "pool-short". Under the mutant, continuation `i=2` reports "structural", so the test kills it (probe log in `task8-rereview1.log`).
- **(b) The boundary term of `block_start` is not pinned.** A test with a large `gap` (for example `gap=fr(10)`) that makes a continuation's cause depend on the placed shows' boundaries would pin it.

### Out-of-Scope Observations
- **Unwritten caller contract.** `own_pool` must contain the placed own shows unfiltered, and `boundary_frames` must be the value the placed shows were laid out with. Two things now depend on it: `_has_fill` (a placed own show missing from `own_pool` now counts as fill, which forces `kmax = 0` and tier 1) and the cause (`own_all` plus `block_start`). `test_placed_shows_supply_the_previous_artist` had to be changed for this reason. The `fill_block` docstring says neither, so Task 9 should state and honour both. A placed own package that drops out of eligibility, or an ID pool that turns non-empty between plans, would change the cause or the tier in a live continuation.
- **No cause on a later step (pre-existing).** A continuation whose `placed` already holds the fill and adds no further show reports `tier == 1` with `fill_from`/`fill_cause = None`, because the cause is attached only to this call's added shows. Task 9's `schedule`/`status` reporting should take the cause from the step that placed the fill, or carry it in the plan.
- The scratch full-suite run's single failure, `test_relay_key_matches_antenna`, is an artifact of the copy: it reads `antenna/src/alerts.ts`, which the prescribed `git archive` paths do not include. The other 747 passed and 1 was skipped.

### Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage. Two Minor test gaps, (a) and (b) above, are worth folding into Task 9 or a polish pass. If deviation 4 is rejected, the repeat-agreement test described above becomes required.
