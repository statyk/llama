# task8-fix2 handback: single-artist exemption for the rotation rules

**Status: DONE.** One commit, `9260dbd` (on `20e78aa`), green: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q` gives 805 passed, 1 skipped. The tree is clean. Log: `$D/task8-fix2/task8-fix2.log`.

## The change, and where

The spec ("What counts as a bend") says a rule the pool makes impossible "is not applied within that pool at all". The ranking now follows that, not the plan's narrower "not reported as a bend".

- **`_blocksearch.py`**
  - `_C` gains an `exempt` slot (default False). `_Ctx.cand(piece, exempt=False)` passes it through.
  - `_Ctx.viol` (`free = c.exempt`) and the inlined partner count in `_Search.pairs` (`free = g.exempt`) skip adjacency and artist_day for an exempt candidate.
  - Gap and era are unchanged.
  - An exempt show's artist is still recorded in `prev`, `day_a` and `day_ay`, so a later show that is not exempt is counted against it.
  - `_sequence_violations` gains `exempt: frozenset[str]` (slugs).
  - The module docstring has a new paragraph stating the rule.
- **`scheduler.py` (`_BlockRun.__init__`)**
  - `self.single_artist = len({p.artist for p in own_all if p.artist}) == 1`.
  - Own-pool candidates are built with `ctx.cand(p, self.single_artist)`. Fill candidates are never exempt.
  - The flag lives on the candidates, which `_BlockRun` builds once, so every run of a block and every rebuilt `_Ctx` in `_advance` sees the same exemption with no extra plumbing.
- **`rules.py`**
  - `violations(..., *, exempt: Set[str] = frozenset())` takes the slugs of exempt shows. The default (empty) is the old behaviour, and no other caller changes.
  - The docstring now reads: "Era implies artist_day, by definition, except on an exempt show."

**Projection (Task 9):** no change was needed. `_Projection._new_run` already passes the own pool, with persisted own rows added back (`extra_own`). The first projection and a live continuation therefore build the same `own_all` and the same flag. `test_appending_first_pieces_reproduces_one_projection` is green.

**Unchanged:** Task 8's accepted deviations (surplus value, tier-1 own-count first, no repeat within a block), the search bound (`PAIR_FIRSTS`/`PAIR_PARTNERS`/chain) and the continuation closure.

## Precise definition, and the era decision

- **"The pool has exactly one artist"** means that `own_all`, the occurrence's own pool as `_BlockRun` sees it, has exactly one distinct known (non-empty) artist.
  - For a profile block, `own_all` is the profile pool deduplicated. In the projection it also contains the block's persisted own shows, so placed own shows count.
  - For an open or degraded occurrence, it is the open pool.
  - A placed show outside `own_all` is fill by the existing rule (`_has_fill`), so it is not part of the pool.
  - Pieces with an unknown artist are ignored. They never break adjacency or artist_day anyway (`if a and ...`), so they cannot make the rule avoidable.
  - Every own candidate of such a pool is exempt. All of them are by that one artist, or have no artist.
- **Fill shows are counted normally, even by the same artist.** Fill comes from the open pool, which has many artists, so the rule is avoidable there. This differs from the reviewer's prototype, which exempted by artist on the `_Ctx`: a "Grateful Dead" fill show from another profile would also have gone uncounted. Mutant M4 pins this.
- **Open and degraded occurrences are covered too**, as the brief asks. The prototype covered profile blocks only. Mutant M6 pins this.
- **Era stays applied.** "Same artist and year on the same day" is avoidable inside a single-artist pool by choosing a different year, and the spec's example of an impossible rule names only "the same artist twice a day or in a pair". I found no spec reason to exempt it.
- **Bends:** within the pool the exempt rules are never violated by own shows, so they are never bends of the pool's choices.
  - A same-artist fill show that breaks adjacency in tier 1 is a bend when another tier-1 option kept the rule. That is the correct reading, because the fill pool can avoid it.

## Tests (written first; RED captured at HEAD 20e78aa)

| test | file | RED before the fix | GREEN |
|---|---|---|---|
| `test_single_artist_pool_prefers_a_fresh_pair_over_a_recent_single` [profile/open x prev None/GD] | test_scheduler_block.py | all 4 chose `['single']` (the single aired 1 day ago beat the never-aired pair on adjacency) | pair p1+p2, tier 0, no bends |
| `test_multi_artist_pool_still_counts_adjacency_before_the_gap` | same | passed (pins the old ordering: a two-artist pool still prefers the single, `bends == ("gap",)`) | passes |
| `test_fill_after_a_single_artist_pool_counts_its_rules` | same | passed (pins the own-membership choice: the "Funk" fill beats a higher-scoring Dead fill) | passes |
| `test_violations_single_artist_exemption` | test_rules.py | TypeError (no `exempt`) | `(4,1,4,2)` without the exemption, `(0,1,0,2)` with it; a non-exempt same-artist show counts as before; default unchanged |
| `test_violation_counts_agree_with_rules` (+200 trials with random exempt subsets; asserts gap and era are unchanged) | test_scheduler_block.py | TypeError | passes |
| `test_every_offered_option_counts_and_scores_as_rules_does` (passes the exempt set, computed independently; new mono+fill case; asserts the `exempt` and `exempt fill` kinds occur) | same | TypeError | passes |

The regression test's RED is in the log: `assert (['single'] == ['p1', 'p2']`.

## Mutants

Each mutant ran in its own fresh `git archive` copy of `9260dbd`, under `PYTHONPATH` shadowing, with the import path checked inside the copy, no bytecode written and no cache provider. Predictions were written to the log before the runs. The control (M0) was 805 passed.

| mutant | predicted red | actual red |
|---|---|---|
| M1 `_Ctx.viol` exemption removed | violation_counts_agree, every_offered_option | **exactly those 2** |
| M2 `_Search.pairs` exemption removed | regression x4, every_offered_option | regression **[profile-*] x2** + every_offered_option. **Prediction miss on [open-*]:** an open block has no `max_shows`, so the greedy chain's two-show prefix (`ctx.extend` uses the still-exempt `viol`) offers the same pair with correct counts. Still caught 3 ways. |
| M3 `rules.violations` exemption removed | rules exemption test, violation_counts_agree, every_offered_option | **exactly those 3** |
| M4 artist-only exemption (same-artist fill exempt too) | fill_after_a_single_artist_pool | **exactly that 1** (the offer test did not also catch it, because its restated exempt set is slug-based and the mismatch shows only on fill) |
| M5 unknown artists count in the definition | regression x4 | **exactly those 4** |
| M6 exemption for profile blocks only | regression [open-*] x2 | **exactly those 2** |

The scripts are at `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-scheduler/6a271170-52a3-49a3-b4db-a9d5cd08acfc/scratchpad/t8f2/mutate.sh` and `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-scheduler/6a271170-52a3-49a3-b4db-a9d5cd08acfc/scratchpad/t8f2/mutants/`.

## Sanity re-run (fixture library, estimates)

The probe is `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-scheduler/6a271170-52a3-49a3-b4db-a9d5cd08acfc/scratchpad/t8f2/probe.py`. It runs one continuous `project` over 4 weeks, starting 2026-11-02. The clock has a `dead-am` block at 07:00 (profile `dead`, 44 shows, all Grateful Dead, window [0, +15]) and an open block for the rest of the day with `dead` excluded. The probe ran 30 dead-am occurrences per run, with 0 misses and 0 fill in every run.

| dead-am length | distinct Dead aired, before → after | shortest repeat gap (median) | gap bends |
|---|---|---|---|
| **240 min** | **2 → 10** | 1.0 d (2.0) → 1.0 d (2.0) | **28 → 0** |
| 300 min | 37 → 37 | 2.0 d (10.1) → same | 0 → 0 |
| 180 min | 17 → 17 | 6.0 d (15.0) → same | 0 → 0 |

How to read it:
- At 240 min the fixture reproduces the defect: one single lands the window alone and was aired every other day. After the fix the block rotates the pairs instead.
- The fixture caps this case. Only 1 single and 7 pairs (7 distinct shows) land [240, 255]. That is far fewer than the 45-day gap needs, so a repeat gap of 1.0 d remains, with no gap bend, because no option keeps the rule.
- At 300 and 180 min no single lands alone, so the defect never applied and the result is identical.
- On the real library, the reviewer's prototype measured 39 → 384 Dead shows over 50 weeks (clock a).

## Files changed

- `/Users/shawn/projects/llama/.claude/worktrees/scheduler/packages/transmitter/src/transmitter/_blocksearch.py`
- `/Users/shawn/projects/llama/.claude/worktrees/scheduler/packages/transmitter/src/transmitter/scheduler.py`
- `/Users/shawn/projects/llama/.claude/worktrees/scheduler/packages/transmitter/src/transmitter/rules.py`
- `/Users/shawn/projects/llama/.claude/worktrees/scheduler/packages/transmitter/tests_transmitter/test_scheduler_block.py`
- `/Users/shawn/projects/llama/.claude/worktrees/scheduler/packages/transmitter/tests_transmitter/test_rules.py`

## Concerns

1. **This is a deliberate departure from the prototype in two places:** fill shows are keyed on own-pool membership rather than on artist, and open and degraded occurrences are included. Both are pinned (M4, M6). If the controller wanted the prototype's narrower scope, M6 shows exactly which test would change.
2. **The plan text still says "not reported as a bend".** The code now follows the spec. The plan and any plan-level docs may want a one-line note; I did not edit docs.
3. **Task 10's evidence tables describe the defect.** a/b/c need re-running on the real library (the controller's step). The 17 doubled-track Dead packages are a separate llama defect, untouched here. They still make the 12-hour own-only pairs repeat, which the reviewer's "Residual, as designed" covers.
4. **What this does not change:** a single-artist pool with too few landing combinations still repeats inside the gap (the 240-min fixture case). That is the gap rule's compromise working as designed, not this defect.
5. **Python 3.11:** all five files parse under `ast.parse(feature_version=(3,11))`. `collections.abc.Set` is the only new import. The Debian-12 docker script was not run.
