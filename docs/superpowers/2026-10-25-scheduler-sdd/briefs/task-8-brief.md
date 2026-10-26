### Task 8: Scores, rules and filling one block (Opus)

**Files:**
- Create: `packages/transmitter/src/transmitter/rules.py`, `packages/transmitter/src/transmitter/scheduler.py` (block filling part)
- Create: `tests_transmitter/fixtures/make_library_durations.py` (generator, deterministic seed) and its output `tests_transmitter/fixtures/library_durations.json`
- Test: `test_rules.py`, `test_scheduler_block.py`

**Interfaces:**
- Consumes: `Piece` (Task 6), `Occurrence`/`ClockConfig` (Task 4), `Recency` (Task 7).
- Produces (`rules.py`):
  - `RULES = ("adjacency", "gap", "artist_day", "era")` — hardest first; bend order is the reverse (era bends first).
  - `score(p: Piece, occ: Occurrence, rec: Recency, clock: ClockConfig, slot_us: int) -> float` = recency term (`1.0` never aired; else `0.9 * min(days_since / concert_gap_days, 1.0)`) + Σ matching `prefer` weights (`years` range contains `p.year`) + on-this-day weight (block override else `rotation.on_this_day_weight`) when `p.month_day` equals the slot's local month-day.
  - `violations(seq: Sequence[Piece], prev_artist: str | None, occ, rec, clock, starts_us: Sequence[int]) -> tuple[int, int, int, int]` — counts per rule for a candidate sequence of shows placed at `starts_us`: adjacency (same artist as the previous show, the first compared to `prev_artist`), gap (aired within `concert_gap_days`, or twice in this sequence), artist_day (artist already on that local date, including earlier in the sequence), era (same artist and year already on that local date).
  - `tie_rank(seed: int, slug: str) -> str` — `planner.shuffle_rank` moved here (planner keeps a re-export until Task 11 removes the shuffle).
- Produces (`scheduler.py`, part 1):
  - `BlockPlan` (frozen): `shows: tuple[Piece, ...]`, `fill_from: int | None` (index of the first fill show), `fill_cause: str | None` (`"pool-short" | "structural"`), `tier: int` (0 own profile in window, 1 with fill in window, 2 miss), `landing_frame: int` (where the next block's first show would start), `bends: tuple[str, ...]`, `degraded: bool`.
  - `fill_block(occ: Occurrence, next_occ: Occurrence, *, start_frame: int, placed: Sequence[Piece], own_pool: Sequence[Piece], open_pool: Sequence[Piece], boundary_frames: int, final_boundary_frames: int, prev_artist: str | None, rec: Recency, clock: ClockConfig, epoch_us: int, seed: int, used: frozenset[str]) -> BlockPlan`.

**Algorithm (`fill_block`), the decisions this task owns:**
- Positions: shows follow `start_frame` back to back with `boundary_frames` between consecutive shows and `final_boundary_frames` after the last (into the next block); the caller passes `gap_frames` for both when the ID pool is empty, else `2 * gap_frames + typical_id_frames` (Task 9). `landing_frame` = end of the last show + `final_boundary_frames`. In window ⇔ `next_occ.lo_us <= landing_us <= next_occ.hi_us`.
- Continuation: `placed` = shows of this occurrence already in the persisted plan, a fixed prefix. They count toward `max_shows`, count as own shows, and supply `prev_artist`. `fill_block` may add `0 .. max_shows - len(placed)` more own shows (0 allowed only when `placed` is non-empty), then fill after the prefix (tier 1), then a miss. With no show added, the block lands where the prefix ends (+ `final_boundary_frames`).
- Pools: for an open occurrence (`occ.is_open`) the caller passes the open pool as `own_pool`. `degraded=True` only for a profile block whose own pool is empty: it is then filled from `open_pool` as open time (unbounded `max_shows`, as an open block) and not announced.
- Candidates: drop pieces in `used` (slugs chosen earlier in this projection) only when the pool has other candidates (else allow, the gap rule then counts it). Rank candidates by `score` (tie: `tie_rank`).
- Tier 0 — own shows only: the prefix plus `k` more, `k = 0 .. max_shows - len(placed)` (`k = 0` only when `placed` is non-empty; with `max_shows` None, `k` grows until the greedy extension can add no show). `k = 1`: singles over every candidate. `k = 2`: pairs, the first from the top 32 by score, the partner from the candidates whose length lands the window (sort the pool by frames once; bisect the landing range), capped at the top 64 by score. `k > 2`: extend greedily (highest score whose addition keeps the landing at or before `hi`) until two shows remain, then the pair search. Keep options landing in window.
- Tier 1 — only when tier 0 is empty: for the best 5 own prefixes whose landing is before `hi`, each holding at least one own show (`placed` counts) when the own pool is non-empty, fill the remainder from `open_pool` minus own-pool pieces with up to 3 fill shows by the same single/pair/greedy search and the same bound. With `placed` already at `max_shows`, the only prefix is `placed` itself (no more own shows, then fill). Cause `"structural"` when the `max_shows` longest own candidates together still land before `lo`, else `"pool-short"`. An open or degraded occurrence has no fill pool (its own pool is the open pool), so tier 1 never applies to it. The one-own-show floor is an operator ruling (2026-10-25): if it happens, the following block starting late is preferable to not playing the scheduled profile at all.
- Tier 2 — miss: among own-only options (the prefix plus own shows, at least one own show in the block; with `placed` already at `max_shows`, "no more shows", landing where the prefix ends), the one whose landing is closest to the window; ties prefer late over early. There is always at least one option in some tier, so the choice is never an empty `min()`.
- Search bound: per occurrence at most 32 × 64 pair evaluations per prefix; tier 0 has one prefix per `k` (the greedy one), tier 1 at most 5.
- Order within a tier: `violations` lexicographically (fewest adjacency first, then gap, artist_day, era), then the larger of `mean(score) - 0.5 * |landing - nominal| / max(early, late)` (for tier 2 only the distance outside the window, then violations, then value), then `tie_rank` of the first show. The mean, not a sum, is a builder call (see Builder calls).
- Bends: for the chosen option, each rule it violates for which some option in the same tier had a zero count for that rule. Rules no option keeps are therefore never bends (single-artist pools, concert gap longer than the pool's airtime).
- Overlapping windows resolve as a late start plus a miss: an occurrence always plays at least one show of its own pool (the open pool for an open or degraded occurrence), late, and the projection sets `miss=True` on its first show (Task 9). No occurrence is ever skipped.

- [ ] **Step 1: Build the fixture** — commit the generator `tests_transmitter/fixtures/make_library_durations.py` (deterministic seed) and its output `fixtures/library_durations.json`: a list of `{slug, artist, date, profile, frames}` for ~300 shows drawn from the measured profile distribution (medians, p10/p90 in the spec's Intent section; Dead all one artist "Grateful Dead"). Re-running the script reproduces the file byte for byte.

- [ ] **Step 2: Failing tests** (`test_rules.py`, `test_scheduler_block.py`)

```python
def test_never_aired_outranks_recently_aired(): ...
def test_on_this_day_boost_uses_the_slot_local_date(): ...
def test_years_preference_adds_its_weight(): ...
def test_violations_count_each_rule(): ...

def test_single_show_landing_in_window_is_tier0(): ...
def test_pair_fills_a_long_block_from_its_own_profile():
    # 4 h jam block, own pool only 2 h and 1.9 h shows -> both chosen, tier 0
def test_own_profile_pair_beats_fill_even_when_pairing_breaks_adjacency():
    # single-artist Dead pool, block needs two shows: tier 0 pair chosen; "adjacency" not in bends
def test_fill_when_the_own_pool_cannot_reach_the_window():
    # own shows all short; tier 1 with fill_cause "pool-short"
def test_structural_fill_when_block_is_longer_than_max_shows_can_cover(): ...
def test_miss_keeps_the_blocks_own_profile():
    # every own show overruns: tier 2, one own show, landing late, no fill
def test_empty_pool_block_degrades_to_open_time(): ...
def test_scarce_pool_repeats_rather_than_degrading():
    # own pool of 2 shows both aired yesterday: still own profile, "gap" not a bend (no option kept it)
def test_bend_counted_only_when_a_keeping_option_existed(): ...
def test_softest_rule_bends_first():
    # an option breaking only era beats one breaking only artist_day, which beats gap, which beats adjacency
def test_overlapping_window_plays_late_with_a_miss():
    # the next block's window has already passed at start_frame: one own show still chosen, tier 2, landing late
def test_placed_prefix_at_max_shows_has_an_option(): ...   # placed == max_shows: a BlockPlan with no added own show, no exception
def test_early_landing_block_gets_no_extra_show(): ...     # placed prefix already lands in window: k = 0 chosen
def test_deterministic_with_seed_tiebreak(): ...
```

- [ ] **Step 3: Run to verify failure.** Expected: FAIL.
- [ ] **Step 4: Implement** per the algorithm above.
- [ ] **Step 5: Run the transmitter suite.** Expected: all PASS.
- [ ] **Step 6: Commit**

```bash
git add packages/transmitter/src/transmitter/{rules,scheduler,planner}.py packages/transmitter/tests_transmitter/test_{rules,scheduler_block}.py packages/transmitter/tests_transmitter/fixtures/
git commit -m "transmitter: scheduler block filling with tiers, rotation rules and bend accounting"
```

---

