# Task 3 fix round 1 — scoped re-review

Commit under review: `4b07645` only. (`e251feb`, `7e3b7cf` are the orchestrator's
docs-only plan edits — not reviewed.)

PTH-GUARD: **OK**. Worktree `git status` clean at start and end; no commits made.
All mutation work done in a shadowed copy at `.../workc/t3-rerev`, shadowing proven
by a planted `SENTINEL_RRV` (module resolved to the copy; worktree grep count 0).
Baseline in the copy: 215 passed across the three touched test files.

## Verdicts

| # | Finding | Verdict |
|---|---------|---------|
| 1 | `residual_sec` hollow | **ADDRESSED** |
| 2 | donor-side-skip branch unpinned | **ADDRESSED** |
| 3 | REAL BUG: `all(d > 0 …)` TypeError on `None` | **ADDRESSED** |
| 4 | `_hygienic_title` duplicated composition | **ADDRESSED** |
| 5 | `MAX_MERGE` unpinned from below | **ADDRESSED** |
| 6 | `cost == INF` branches undocumented | **ADDRESSED** |

## Finding 3 — the one that mattered

The pin uses a **real `None`**, not a look-alike. Test source:
`propose_rows([300.0, None, 510.0], donor, …)` and a second half with
`_donor([300.0, None, 510.0], …)` — a literal `None` on **each** side, not `0`,
`-1`, `float("nan")` or a stand-in. It asserts the decline, not merely the
absence of a raise: `assert diag["decline"] == "missing per-track durations"`.

Mutation applied (revert `_all_present` to the old guard):

    if not all(d > 0 for d in target_durs) or not all(d > 0 for d in donor.durations):

→ RED, and with the original defect reproduced exactly:

    FAILED test_a_none_duration_declines_instead_of_raising
    E   TypeError: '>' not supported between instances of 'NoneType' and 'int'

The pre-existing `0.0` case is still pinned separately
(`test_a_missing_duration_on_either_side_declines_the_whole_pair`), so the
zero-duration behaviour was preserved, not traded away.

## Finding 4 — one definition, both sides red

Exactly **one** definition survives: `structure.py:1095 def hygienic_title`. Zero
`_hygienic` references anywhere in `packages/`. Two production call sites —
`structure.py:1171` (`adopt_gap_titles`) and `siblings.py:291` (sibling transfer) —
plus the `siblings.py:40` import. No second composition of the four predicates exists.

Mutating the single definition (dropping the `fuzzy_norm_title(t) not in
metadata_norms` clause) turns **both** sides red in one run:

    FAILED test_siblings.py::test_a_donor_track_titled_with_show_metadata_fails_hygiene
    FAILED test_structure.py::test_hygiene_rejects_show_metadata_residue

Two further clause drops (trailing-colon, `is_junk_title`) turn only structure red —
siblings has no fixture isolating those clauses. Not a defect: with one imported
definition, drift is structurally impossible; that is a coverage note, not the
invisible-divergence the finding was about.

**No behaviour change in the collaterally-touched files.** Verified by AST
comparison of `ce80541` vs `4b07645` with docstrings stripped:

    titles.py         AST-identical: True   (comment-text only)
    correspondence.py AST-identical: True   (docstring-text only)
    structure.py      AST-identical modulo the _hygienic -> hygienic_title rename: True

## Findings 1, 2, 5 — mutations applied, red tests named

**Finding 1** — hard-code `residual = 0.0` at `siblings.py:276`:

    FAILED test_residual_seconds_reports_each_pairings_duration_gap
    >   assert [r.residual_sec for r in rows] == [1.0, 1.0, 2.0, 2.0, 1.0]
    E   assert [0.0, 0.0, 0.0, 0.0, 0.0] == [1.0, 1.0, 2.0, 2.0, 1.0]

    FAILED test_a_merged_target_file_proposes_the_segue_join
    >   assert got[1].residual_sec == 3.0   # 703 s of file against 700 s of donor
    E   AssertionError: assert 0.0 == 3.0

Two independent tests, and the per-row fixture uses a *different* non-zero gap per
row (1/1/2/2/1), so reporting whole-tape drift instead of the pairing's also dies.

**Finding 2** — replace the donor-side-skip `continue` with `pass`:

    FAILED test_a1_a_donor_track_the_target_lacks_adds_no_row_to_the_target
    >   assert [r.track for r in rows] == [1, 2, 3, 4, 5]
    E   assert [1, 1, 2, 3, 4, 5] == [1, 2, 3, 4, 5]

The duplicated target-track row surfaces exactly as the finding described. The
assertion is on the track *list*, not a count — a count assertion would have been
satisfiable by a different wrong answer.

**Finding 5** — I did not spot-check two; I re-ran **all four constants in both
directions independently**. Every one of the ten mutations turns at least one named
test red, reproducing the implementer's claim in full:

    MAX_MERGE 3->1 (down)              9 failed
    MAX_MERGE 3->2 (down)              1 failed  test_one_file_may_hold_three_donor_songs
    MAX_MERGE 3->4 (up)                1 failed  test_too_few_matched_tracks_declines_the_whole_pair
    MAX_MERGE 3->5 (up)                1 failed  test_too_few_matched_tracks_declines_the_whole_pair
    MIN_EXCLUSION_PENALTY 60->0 (down) 1 failed  test_near_ambiguous_pairing_declines_on_weak_evidence
    MIN_EXCLUSION_PENALTY 60->600 (up) 3 failed
    MIN_MATCH_FRACTION .8->0.0 (down)  1 failed  test_too_few_matched_tracks_declines_the_whole_pair
    MIN_MATCH_FRACTION .8->1.0 (up)    2 failed
    SKIP_COST_MULT 1.0->0.5 (down)     2 failed
    SKIP_COST_MULT 1.0->2.0 (up)       5 failed

Two downward spot-checks, verbatim:

    MAX_MERGE 3 -> 2:
      FAILED test_one_file_may_hold_three_donor_songs
      >   assert got[1].proposed == "Alpha > Bravo > Charlie"
      E   AssertionError: assert 'Alpha > Bravo' == 'Alpha > Bravo > Charlie'

    MIN_MATCH_FRACTION 0.80 -> 0.0:
      FAILED test_too_few_matched_tracks_declines_the_whole_pair
      >   assert rows is None
      E   AssertionError: assert [SiblingRow(track=1, …)] is None

`MAX_MERGE 3 -> 2` fails **only** the new fixture — which is the finding: that test
is now the sole pin from below, and before it existed the mutation was silent.

## Finding 6 — and its claim independently checked

Both `cost == INF` sites are documented, in the same voice as the row model's
already-documented `inf` penalty ("structurally unreachable, because skipping both
sides always leaves a feasible alignment" / "UNREACHABLE from any input … skips are
always legal"). I did not take the unreachability claim on trust — a false comment is
new breakage. Fuzzed 4,000 random tapes (n,m in 0..7) plus **every legal pairing
`forbid`** on each: **0 INF results**. The claim holds, and the reasoning does too —
`forbid` is only ever a non-degenerate pairing op, so the all-skip path is never
barred.

## Suite delta — itemised case by case

Static test-function census across the whole test tree, `ce80541` -> `4b07645`:
1509 -> 1512 defs, net **+3**, matching the reported 1587 -> 1590.

ADDED (4), each traceable to a finding:
- `test_residual_seconds_reports_each_pairings_duration_gap`  — finding 1
- `test_a1_a_donor_track_the_target_lacks_adds_no_row_to_the_target` — finding 2
- `test_a_none_duration_declines_instead_of_raising` — finding 3
- `test_one_file_may_hold_three_donor_songs` — finding 5

REMOVED (1):
- `test_hygiene_matches_structures_own_predicate_exactly` — confirmed: this **is**
  the equality table, and it is the only removal in the entire test tree.

**Nothing else was weakened.** Assert-count per surviving test in `test_siblings.py`
moved only upward: A2 10 -> 12, A3 9 -> 11; every other surviving test unchanged.
The three replaced assertions are each equal-or-stronger (`residual_sec == 0.0` ->
`== 3.0`; `["adopt"]*4` over 4 tracks -> `*5` over 5).

## A2/A3 off the 0.80 boundary

Confirmed by measurement, not by reading:

    MIN_MATCH_FRACTION      = 0.8
    A2 (new, 6 pairs)       = 0.8333333333333334
    A3 (new, 7 pairs)       = 0.8333333333333334
    A2 (old, 5 pairs)       = 0.8            <-- exactly on the threshold

The reason is stated inline in both tests, and both now assert
`diag["match_fraction"] > MIN_MATCH_FRACTION` rather than leaving it implicit.

## New breakage in the fix diff

**None found.**

## Deferred (out of scope, not for this loop)

- `_all_present`'s `isinstance(d, (int, float))` also admits `bool` (`True > 0`);
  unreachable from `Track.duration_sec`, cosmetic only.
- `hygienic_title`'s `is_junk_title` and trailing-colon clauses have no
  siblings-side discriminating fixture (structure-side only).

## Overall verdict

**APPROVED** — all six findings ADDRESSED, verified by mutation rather than by
reading; no new breakage in `4b07645`.
