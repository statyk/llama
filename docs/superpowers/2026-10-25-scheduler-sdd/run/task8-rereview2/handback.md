### Finding Verdicts

**Dead-repeat / single-artist exemption (Task 10 review, "Dead-repeat diagnosis"): ADDRESSED.**

- `_BlockRun.__init__` sets `single_artist` when `own_all` has exactly one distinct known artist. Own candidates are built with `exempt=single_artist`, and fill candidates never are.
- The exemption is applied the same way in all three counters:
  - `_Ctx.viol`, which drives singles, the greedy chain and `extend`;
  - the inlined partner count in `_Search.pairs`;
  - `rules.violations(..., exempt=)`.
- In each counter, adjacency and artist_day are skipped for an exempt show. Gap and era are untouched.
- An exempt show's artist is still recorded in `prev`/`day_a`/`day_ay`, so a later non-exempt show is counted against it.
- The regression test `test_single_artist_pool_prefers_a_fresh_pair_over_a_recent_single` covers profile and open blocks, each with prev None and with prev GD. A single aired a day ago now loses to a never-aired pair, with `bends == ()`. The implementer's log shows the RED at 20e78aa.
- I checked the three counters against each other and they agree.
- My own mutant: I made era exempt in `_Search.pairs` only. I predicted `test_every_offered_option_counts_and_scores_as_rules_does` would go red, and that is exactly what went red (1 failed, 62 passed). So the new mono+fill offer case does exercise era on exempt pairs, and "era stays applied" is pinned.

### New Breakage in the Fix Diff

None.

What I checked:

- **Definition of "exactly one artist."**
  - Unknown artists are ignored. They break no rule (`if a and ...`), so they cannot make adjacency avoidable.
  - An all-unknown pool counts as zero artists, so it is not exempt, which makes no difference either way.
  - Placed own shows are in `own_all`: the projection's `extra_own` holds persisted own rows. This is the choice that keeps continuations closed.
    - A package's artist is intrinsic, so a mid-block profile move can only add an artist that the pre-move pool already had.
    - A vanished package rebuilds as a `Piece` with an empty manifest, so it has an unknown artist.
    - So the first projection and a live continuation compute the same flag.
- **Degraded blocks, and open blocks over a single-artist library.** The open pool is the pool those occurrences actually draw from. If it has one artist, the spec's "impossible within that pool" holds literally, so exempting it there is correct (M6 pins this).
- **Multi-artist pools.** `single_artist` is False, every candidate keeps `exempt=False`, and the code paths are byte-for-byte the old ones. `test_multi_artist_pool_still_counts_adjacency_before_the_gap` pins the old ordering (single wins, `bends == ("gap",)`).
- **`rules.violations` default.** It is keyword-only, defaults to `frozenset()`, and gives the old behaviour (asserted in `test_violations_single_artist_exemption`). It has no production caller in src; only tests and `_sequence_violations` call it.
- **`prev_artist` across a block boundary** (e.g. dead-pm after dead-am, or a dead block after an open block that aired GD). The first exempt show is not counted for adjacency or artist_day against the previous block or history. I judge this intended and harmless:
  - Within a tier, every own-only option used to carry the same +1 adjacency on its first show, so dropping it does not reorder options. The artist_day-against-history count was part of the defect itself (it grew with show count).
  - The side that can avoid the collision is still counted. A multi-artist open block after the dead block still counts GD artist_day against the dead block's airing.
  - What nobody counts is an open block's last show being adjacent to the following dead block. That was equally true before the fix, because blocks do not look ahead.
- **Departures from the prototype.** Both are spec-consistent:
  - Fill is judged by own-pool membership, not by artist. Fill comes from the multi-artist open pool, where the rule is avoidable, so a same-artist GD fill is still counted (M4 pins this).
  - Open and degraded blocks are included, since the "pool" is the one the occurrence draws from.
- **Bends.** `_Tier.bends()` is unchanged: a rule is a bend when `viol[i] and kept[i]`. Exempt shows never violate the exempt rules, so those rules are never their bends. A same-artist fill's adjacency is a bend only when another tier-1 option kept the rule.
- **Continuation closure.** I spied on `_BlockRun`:
  - `test_appending_first_pieces_reproduces_one_projection` and `test_continuing_a_block_reproduces_the_first_choice` both run the single-artist path (`('dead', profile_block, not degraded, single_artist=True)`: 165 runs), as well as multi-artist blocks.
  - Both pass at 9260dbd.
- **Unchanged pieces.** The search bound, the surplus value, tier-1 own-count first and no-repeat-within-block are untouched by the diff.
- **Performance is unchanged.**
  - The scheduler test files take 6.96 s at base and 7.06 s at head, but head has 6 more tests.
  - The top-5 durations are identical within noise, including `test_fill_block_is_fast_on_a_3000_piece_pool` and `test_project_over_a_3000_piece_pool_is_fast`.
  - The added cost is one attribute read per candidate evaluation.
- **Suite at 9260dbd** (scratch copy, shadowing proved: `transmitter.__file__` and `tests_transmitter.__file__` resolve inside the copy): 805 passed, 1 skipped.

### Out-of-Scope Observations

1. The plan text still says a pool-impossible rule is "not reported as a bend". The code now follows the spec's stronger "not applied within that pool at all". The plan should get a one-line note (implementer concern 2).
2. Task 10's real-library evidence tables (clocks a/b/c) describe the defect and need re-running at 9260dbd before the measurement docs are trusted.
3. I did not re-run the Python 3.11 gate (`test-in-debian12.sh`). The venv interpreter here is 3.14. The only new import is `collections.abc.Set`, which is valid on 3.11.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.
