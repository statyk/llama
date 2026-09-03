# QUALITY: CHANGES REQUESTED

Task 3 — `packages/llama/src/llama/siblings.py` + `packages/llama/tests/test_siblings.py`
(review package `0548092..ce80541`, single commit `ce80541`).

Pointer guard printed `OK`. All mutation work ran on a copy at
`…/scratchpad/workc/t3-rev-qual/copy` under
`PYTHONPATH=<copy>/packages/{llama,herder,emcee}/src` with the worktree's
`.venv/bin/python -m pytest`; shadowing proven with a planted `SENTINEL_T3_REV`
(module resolved inside the copy); `__pycache__` purged before and after every
run; worktree `git status` clean, no commits. Baseline in the copy: 19 passed.

---

## Strengths (specific, and verified)

- **The span convention is genuinely pinned, three ways.** `siblings.py:279`
  mutated to inclusive `(j0, j1 - 1)` -> 3 red; mutated to 1-based
  `(j0 + 1, j1 + 1)` -> 3 red. `test_siblings.py:101` pins the 1:1 case, `:123`
  the merged `(0, 2)` case (which is what actually separates half-open from
  inclusive), `:233` the split case. Because `_by_track` keys on `r.track`, a
  0-based `track` reds them too.
- **The convention claim is true, not just asserted.** `structure.anchor_spans`
  (`structure.py:1012-1052`) and `structure.gap_span` (`:1055-1092`) both return
  half-open 0-based spans over canonical items. Task 4 can reuse them unconverted.
- **The DP is correct.** Forward relaxation only writes states strictly ahead in
  lexicographic `(i, j)` order (`i+1,j` / `i,j+1` / `i+a,j+b` with `a,b >= 1`),
  all visited later - no mutate-while-iterating, no stale read. Complexity is
  `O(n*m*MAX_MERGE^2)` as documented, not `O(n^3)`; `MAX_MERGE` genuinely bounds
  both op dimensions (`siblings.py:203-205`).
- **Purity holds, checked empirically.** After `import llama.siblings`, no
  `llama.stages.*`, no `herder`, no `requests`/`httpx` in `sys.modules`. Hygiene
  primitives are imported, not reimplemented (`:40-42`).
- **`MIN_EXCLUSION_PENALTY` is bracketed both directions** - `0.0` -> 1 red
  (implementer's run, reproduced), `1000.0` -> 8 red. Strongest constant pin here.
- **The `matched` definition is well pinned** - restricting it to 1:1 ops -> 5 red.
- **Nothing removed or weakened.** `git diff --stat 0548092..ce80541` is two
  files, 626 insertions(+), zero deletions; the diff restricted to everything
  except the two new files is empty. The +19 claim holds.
- **The commit message states the test command** (`./.venv/bin/pytest -q ->
  1587 passed, 7 deselected`, baseline 1568), the span convention, and the
  do-not-retune citation. No scope creep: the module is unwired, correct for Task 3.

---

## Issues

### Important (Should Fix)

**I1. `residual_sec` is hollow - a constant `0.0` passes all 19 tests.**
`siblings.py:278`. Mutation `residual = 0.0` -> **19 passed**. The only assertion
on the field anywhere is `test_siblings.py:125`, `assert got[1].residual_sec ==
0.0` - i.e. asserted exclusively at the value the mutation hard-codes.
`residual_sec` is part of the row interface Tasks 4/5/6 consume, so this is
precisely the "pin that reads as binding and is not" class this phase exists to
prevent.
*Fix:* assert a non-zero residual. The existing 1:1 fixture already produces one
- `test_siblings.py:85`, target `300.0` vs donor `301.0`, so
`got[1].residual_sec == 1.0`; the near-ambiguous fixture's merged row has
`residual_sec == 15.0`. One added line each.

**I2. The donor-side-skip branch has zero coverage - deleting it leaves the
suite green.** `siblings.py:273-274` (`if i1 == i0: continue`). Mutation: delete
both lines -> **19 passed**. This is the A1-shaped case - the *target* tape is
missing a song the donor has - the exact inverse of the A2/A3 controls and just
as common in the wild, and it is the one branch protecting the
one-row-per-target-track invariant: without it a donor-side skip appends a
**second row for the same `track` number**, into a list Tasks 4-6 index by `track`.
*Fix:* add a test forcing a donor-side skip that asserts `len(rows) ==
len(target_durs)` plus surrounding titles by exact string. Note it is hard to
force (see concern 1); if no fixture produces `i0 == i1`, that is itself the
finding and the branch should be documented as unreachable alongside the other
two (M4), not left silently untested.

**I3. The documented missing-duration re-check raises `TypeError` on the
codebase's actual "missing" value.** `siblings.py:252`. The docstring at `:81-84`
says "the caller guarantees none missing, and `propose_rows` re-checks rather
than trusting it", and the decline string is literally `"missing per-track
durations"` - but `d > 0` against `None` raises. Verified:
`propose_rows([300.0, None, 510.0], …)` -> `TypeError: '>' not supported between
instances of 'NoneType' and 'int'`, same on the donor side.
`models.Track.duration_sec` is declared `float | None` in three places
(`models.py:155`, `:250`, `:330`), so `None` is exactly how this codebase
represents a missing duration, and Task 4's caller will assemble these lists from
`Track`s. A defensive guard that crashes on the one input it names is worse than
no guard.
*Fix:* `if not all(isinstance(d, (int, float)) and d > 0 for d in target_durs)`
(same for the donor), and add the `None` case to
`test_a_missing_duration_on_either_side_declines_the_whole_pair`
(`test_siblings.py:271`), which today covers only `0.0`.

**I4. `_hygienic_title` is a verbatim copy of `structure._hygienic`'s body -
comment included.** `siblings.py:135-151` vs `structure.py:1095-1107`: the same
six-line boolean and the same "No `aliases` here, deliberately" comment. Labeled
*plan-adjacent* - the brief said "import from `setlist`/`titles`, do not copy",
which the implementer reasonably read as the primitives - but the composition is
still a second definition, in a codebase whose own docs say a drifting second
definition is invisible. The mitigation is real and it bites: dropping
`not t.endswith(":")` from the siblings copy reds
`test_hygiene_matches_structures_own_predicate_exactly`. It can only catch drift
the 14-case table happens to distinguish.
*Fix:* promote to `structure.hygienic_title` (keep `_hygienic` as an alias) and
import it in `siblings`. The equality test then becomes tautological and its
14-case table should move onto the shared function. The implementer's objection -
that this falsifies `_hygienic`'s "only silent adopter in the pipeline" docstring
- is a comment to update, not a design constraint.

### Minor (Nice to Have)

**M1. `MAX_MERGE = 3` is unpinned from below.** `siblings.py:57`. Mutation
`MAX_MERGE = 2` -> **19 passed**; `MAX_MERGE = 5` -> 1 red, and only by accident
(`test_too_few_matched_tracks…`, where a 5-wide split lifts `match_fraction` to
1.0). A do-not-retune constant with no test showing why its shipped value is
needed. *Fix:* one test - `align_durations([1000.0], [300.0, 300.0, 400.0])`
returns `(0.0, [(0, 1, 0, 3)])` at 3 and cannot at 2; verified.

**M2. The `is_real_title` clause in the untitled branch is unpinned and
redundant.** `siblings.py:290`. Mutation to plain `if not all(t.strip() …)` ->
**19 passed** - a `"01"`-titled donor falls through one line to
`_hygienic_title`, which rejects it anyway. Only the *reason string* differs
(`sibling track untitled` vs `sibling title fails hygiene`). Either drop the
clause or pin the distinction. Named because it is the same shape as Task 2's
escape (a title predicate nothing was measuring).

**M3. `siblings.py:220` is the only bare `assert` in the entire `llama` src
tree** (grep over `packages/llama/src/llama/` returns exactly this one). It
vanishes under `python -O`, leaving the backtrack loop to spin on `None`.
*Fix:* `if step is None: raise AssertionError(...)`, or make the `(0, 0)`
terminal explicit.

**M4. A second dead branch, unlike the first, is undocumented.**
`siblings.py:214-215` (`if dp[n][m] == INF: return INF, []`) and `:256-257`
(`"no legal alignment"`) are unreachable for exactly the reason the report gives
for `penalty = inf`: skips always leave a feasible path. Verified:
`align_durations([], [])` -> `(0.0, [])`. The `inf` penalty branch is documented
as structurally unreachable at `:117-118`; these two are not. Document both or
drop both.

**M5. `rows.sort(key=...)` at `:303` is a no-op.** Ops tile in increasing `i`, so
rows are already ordered; removing the line -> **19 passed**. Delete it or
comment it as deliberate belt-and-braces.

**M6. `rstrip(">")` at `:289` is unpinned and unexplained.** No test has a donor
title ending in `>`; removing it -> **19 passed**. If it strips a taper's
trailing segue marker, say so and pin it; otherwise drop it.

**M7. The A2/A3 fixtures sit exactly ON the `MIN_MATCH_FRACTION` boundary.**
`test_siblings.py:141` yields `matched == 4` of 5 -> `match_fraction == 0.80`
exactly, and the gate is `< MIN_MATCH_FRACTION`. That is why
`MIN_MATCH_FRACTION = 0.81` reds A2 *and* A3 - a genuine upper bracket, welcome -
but it means the phase's two headline tests are one float away from
`propose_rows` returning `None`. Worth a one-line comment saying the margin is
deliberate and exact.

**M8. The penalty re-solve runs for rows that never use it.**
`siblings.py:275-277` executes before the split / untitled / hygiene branches,
all of which discard the value for their decision. Hoisting it below those
branches removes most re-solves at no behavioural cost. See concern 3.

---

## Test hygiene - what edit reds each of the 19

`[run]` = verified by mutation; the rest are read-and-reasoned against a named edit.

| # | Test (`test_siblings.py`) | Source edit that reds it |
|---|---|---|
| 1 | `…pairs_one_merged_file…` :38 | `MAX_MERGE = 1` / remove the a:b op loop `:203` |
| 2 | `…forbidding_the_best_pairing…` :44 | delete the `op != forbid` guards `:194,:200,:208` |
| 3 | `…skips_a_target_track…` :53 | `SKIP_COST_MULT = 2.0` **[run]** |
| 4 | `…ops_partition_both_sequences` :70 | drop `list(reversed(ops))` `:223` / mis-tile the backtrack |
| 5 | `…one_to_one…string_by_string` :85 | `MIN_EXCLUSION_PENALTY = 1000` **[run]** |
| 6 | `…donor_span_is_half_open…` :101 | span -> inclusive, or -> 1-based **[run, both]** |
| 7 | `…merged_target_file…segue_join` :116 | join `", "`; span mutations; `MIN_EXCL=1000` **[run, all three]** |
| 8 | `test_a2_…` :135 | positional transfer (implementer, :147); `MIN_MATCH_FRACTION=0.81`; `SKIP_COST_MULT=2.0`; join sep; `matched` def **[run, four]** |
| 9 | `test_a3_…` :158 | same set **[run, four]** |
| 10 | `…near_ambiguous…weak_evidence` :180 | `MIN_EXCLUSION_PENALTY = 0` (implementer) and `= 1000`; constant penalty **[run]** |
| 11 | `…untitled_donor_track…` :205 | remove the `t.strip()` empty-title test `:290`; `MIN_EXCL=1000` **[run]**. Does **not** pin `is_real_title` - see M2 **[run: green]** |
| 12 | `…split_across_target_files…` :223 | split rows verdict -> `"adopt"` **[run]**; span mutations **[run]**; `matched` def **[run]** |
| 13 | `…titled_with_show_metadata…` :238 | drop the `fuzzy_norm_title(t) not in metadata_norms` clause `:151` |
| 14 | `…hygiene_matches_structures_own…` :253 | drop `not t.endswith(":")` from either definition **[run]** |
| 15 | `…missing_duration…` :271 | delete the `d > 0` precondition `:252`. Covers `0.0` only - **not** `None` (I3) |
| 16 | `…too_few_matched_tracks…` :283 | `MIN_MATCH_FRACTION = 0.5` **[run]**; `MAX_MERGE = 5` **[run]**. Loose from below: any value > 0.2 passes |
| 17 | `…fields_disagree_in_length…` :292 | delete the length check `:250` -> `IndexError` |
| 18 | `…empty_tape…dividing_by_zero` :300 | delete the empty check `:248` -> `ZeroDivisionError` |
| 19 | `…exclusion_penalty_is_what…costs` :307 | `SKIP_COST_MULT = 2.0`; constant penalty **[run, both]** |

**No test is fully hollow.** Three things the 19 do not pin, all named above:
`residual_sec` (I1), the donor-side-skip branch (I2), the `is_real_title` clause
(M2). `MAX_MERGE`'s shipped value is unpinned from below (M1).

**Span convention: PINNED - yes, unambiguously.** Both wrong conventions go red
on three tests each (inclusive `(j0, j1-1)`: `test_donor_span…`,
`test_a_merged…`, `test_a_donor_song_split…`; 1-based `(j0+1, j1+1)`: the same
three). A 0-based `track` also reds them via `_by_track`. Best-pinned thing in
the change.

---

## The three implementer concerns

**1. No skip-preferring tie-break - right call, incompletely reported.**
The L1 argument checks out and the failure direction is more declines, never a
shifted title - the correct bias for a rung feeding an automatic band. Refusing
to perturb the op set the spec's tables were measured on is the right instinct.
Two corrections: (a) the same argument makes the **donor**-side skip rare too,
and that branch shipped with zero coverage (I2) - the report reasons only about
the target side; (b) the A1-shaped case degrades further than "one deletion costs
two rows". Measured: target `[300, 420, 510, 360]` against donor
`[300, 420, 455, 510, 360]` (one *extra* donor track) yields ops
`[(0,1,0,1), (1,2,1,2), (2,3,2,4), (3,4,4,5)]` and rows
`Alpha/decline(penalty 0s)`, `Bravo/decline(penalty 0s)`,
`"Xray > Charlie"/decline`, `Delta/adopt` - three correct pairings thrown away at
penalty 0 and only the tail adopted. Safe, but the yield cost of one inserted
donor track is near-total, not two rows. Belongs in Task 7's measurement.
I also probed whether a trailing donor track can force `i0 == i1`: with target
`[300,420,510,360,480]` vs donor `[…,4000.0]` the DP produced `(2, 5, 5, 6)` - a
3:1 split of the 4000 s track across three target files - rather than skipping
it. Every row declined, so the outcome is safe, but it confirms how hard the
donor-side skip is to reach.

**2. `penalty_sec = inf` kept - defensible, but be consistent.** Keeping an
eight-character branch that documents an interface the row model names is fine,
and the replacement test (`:307`) pins something better than a magnitude. The
defect is not that branch; it is that the *same* dead-branch class at `:214-215`
/ `:256-257` is neither flagged nor documented (M4). Document all three as
structurally unreachable, or drop all three.

**3. Per-op re-solve - correctly deferred, one cheap win worth taking now.**
Measured in the worktree: `propose_rows` costs **0.064 s at 40x40** and
**1.77 s at 120x120** per donor pair. A real tape against six donors is well
under half a second, so Task 3 is not the place to optimize, and the guard Task 5
needs is a cap on donor track count, which only `gather` can set. The one thing
worth doing here is M8 - hoisting the re-solve below the split/untitled/hygiene
branches, which discard the value anyway.

---

## Assessment

**Task quality: Needs fixes.**

**Reasoning:** The DP is correct, pure, well-documented and its central interface
(the span convention) is the best-pinned thing in the change - but three concrete
gaps that mutation caught and reading did not: `residual_sec` is asserted only at
the value a constant-zero mutation produces, the donor-side-skip branch can be
deleted with the suite still green, and the documented missing-duration guard
raises `TypeError` on `None`, the value `models.Track.duration_sec` actually
uses. All three are small edits; I4 is a judgement call for the human.
