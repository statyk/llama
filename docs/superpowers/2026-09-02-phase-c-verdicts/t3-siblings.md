# Task 3 report — `siblings.py`, the duration DP and row transfer

**Status: DONE_WITH_CONCERNS** (work is complete and green; three findings below
change what Tasks 4/6/7 should expect, none of them blocking).

## Commits

- `ce80541` — siblings: the pure duration DP and per-row title transfer
  (`packages/llama/src/llama/siblings.py` + `packages/llama/tests/test_siblings.py`,
  one commit; the module and its tests are not separately wired-up states).

## Test command and output tail

```
./.venv/bin/pytest -q
1587 passed, 7 deselected, 26 warnings in 5.33s
```

Baseline was 1568 passed / 7 deselected. +19, all new in `test_siblings.py`.
No test removed, none rewritten, none skipped — the delta is exactly the 19
new cases.

## Step 2 — the failing-tests run, verbatim

```
==================================== ERRORS ====================================
____________ ERROR collecting packages/llama/tests/test_siblings.py ____________
ImportError while importing test module '/Users/shawn/projects/llama/.worktrees/sibling-transfer/packages/llama/tests/test_siblings.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/lib/python3.14/importlib/__init__.py:88: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
packages/llama/tests/test_siblings.py:12: in <module>
    from llama.siblings import (
E   ModuleNotFoundError: No module named 'llama.siblings'
=========================== short test summary info ============================
ERROR packages/llama/tests/test_siblings.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.07s
```

## The two named mutations

Both run on COPIES outside the worktree
(`…/scratchpad/workc/t3-siblings/mut`, `…/mut2`), driven by
`$R/.venv/bin/python -m pytest` with `PYTHONPATH` pointed at the copy —
never a `.venv/bin/*` console script from a copy. `__pycache__` purged before
and after each run. The worktree tree and venv are unchanged (`git status`
clean, pointer guard re-checked after: `llama.__file__` still resolves inside
the worktree).

### Mutation 1 — positional transfer (`titles[i] = donor.titles[i]`)

The DP call's row loop replaced by a straight positional walk over
`donor.titles`, keeping hygiene so the mutant is as strong as the old rung was.

Failing test (the named one):
`packages/llama/tests/test_siblings.py::test_a2_deleted_donor_head_track_declines_the_orphan_and_keeps_the_rest`

```
>       assert got[1].verdict == "decline"
E       AssertionError: assert 'adopt' == 'decline'
E
E         - decline
E         + adopt
```
(`tests/test_siblings.py:147`; the run continues on to fail
`got[2].proposed == "Bravo > Charlie"` etc. — the whole tape shifts up by one,
which is exactly the blindness this task exists to remove.)

Seven tests die under it in total: `test_a2_…`, `test_a3_…`,
`test_a_merged_target_file_proposes_the_segue_join`,
`test_near_ambiguous_pairing_declines_on_weak_evidence`,
`test_a_donor_song_split_across_target_files_declines_those_rows`,
`test_a_donor_track_titled_with_show_metadata_fails_hygiene`,
`test_the_exclusion_penalty_is_what_the_best_rival_explanation_costs`
(`7 failed, 12 passed`).

### Mutation 2 — `MIN_EXCLUSION_PENALTY = 0.0`

Failing test:
`packages/llama/tests/test_siblings.py::test_near_ambiguous_pairing_declines_on_weak_evidence`

```
>       assert got[1].verdict == "decline"
E       AssertionError: assert 'adopt' == 'decline'
E
E         - decline
E         + adopt
```
(`tests/test_siblings.py:194`. `1 failed, 18 passed` — precisely the one test,
so the constant is pinned by exactly the case that measures it, and no other
test is silently leaning on it.)

The test is NOT hollow: the near-ambiguous fixture's pairing carries a real
20 s penalty, so it sits strictly between 0 and 60 and the mutation flips it
from decline to adopt. It did not need rewriting.

## The span convention, and why

Documented on the `SiblingRow` docstring and pinned by
`test_donor_span_is_half_open_and_zero_based_while_track_is_one_based`:

- `track` — **1-based** target track number. It matches `models.Track.track`
  and everything an operator ever reads; a row model that renumbered would
  need a conversion at every call site in Tasks 4–6.
- `donor_span` — **half-open over 0-based donor track indices**, `[j0, j1)`.
  Chosen because the spec has Task 4's guard treat the donor's track sequence
  as the canonical's stand-in, reusing `structure.gap_span` and the shape
  `structure.anchor_spans` returns — both of which are half-open and 0-based
  over items. Any other convention would need a translation layer inside the
  guard whose whole purpose is preventing silent adoption.
- The asymmetry (1-based track, 0-based span) is deliberate and is stated in
  the docstring rather than smoothed over: each side matches the convention of
  the code that consumes it.
- A **merged** pairing (one target file holding donor tracks 3 and 4, 0-based
  2 and 3) has span `(2, 4)` and `proposed == "A > B"`.
- A **split** pairing (one donor song across several target files) gives every
  affected row the SAME span and the same `residual_sec`. Spans therefore do
  **not** partition the donor whenever a split is present — the docstring says
  "do not sum them", because a count-forcing check in Task 4 that sums spans
  would be wrong exactly where the split rows already declined.
- `donor_span is None` only for a target track paired with nothing
  (`no sibling track`).

## Spec / prototype disagreements and findings

1. **The prototype's whole-donor gates are gone, as the spec requires.**
   `MIN_SIB_TAGGED = 0.90` and `MIN_SIB_DUR = 0.95` are not in the shipped
   module. Complete durations survive as a *structural* precondition on both
   sides (a missing duration corrupts the DP), which is the spec's own
   framing. `test_an_untitled_donor_track_declines_only_its_own_row` uses a
   67%-tagged donor precisely so the per-item rule is pinned by a case the
   prototype would have refused wholesale.

2. **FINDING, and the one worth carrying into Tasks 4/6/7: a target-side skip
   (`no sibling track`) is *structurally rare*, not merely uncommon.** Under
   an L1 timeline cost, skipping a track and absorbing it into the pairing
   beside it cost the same: skip is `dur(t)`; absorbing is
   `|dur(t) + dur(neighbour) − dur(donor)|`, which equals `dur(t)` plus the
   same jitter when the neighbour is the longer side, and is strictly
   **cheaper** when it is the shorter one. So absorption is never worse than
   skipping, and a `no sibling track` row appears only where absorption is
   *illegal* — `min(a, b) == 1` bars a 2:2 op (the neighbour is already a 1:2
   merge), or `MAX_MERGE` bars a 4:1 one. Everywhere else the DP reports a
   merge, whose rows all decline with `sibling song split across target
   files`. Consequences:
   - The brief's A2/A3 sketch ("the orphaned target row declines with
     `no sibling track`") is reachable but needs the orphan's neighbour to be
     a genuine 1:2 pairing — which is what both deletion fixtures do, and the
     test docstrings say why. A naive A2 fixture (delete donor track 1, 1:1
     everywhere else) produces an exact algebraic **tie** and the DP reports
     the absorption, declining two rows instead of one.
   - This is the *safe* direction (more declines, no shifted titles), and the
     tie-break is exploration order, not a rule — so I did **not** add a
     tie-break preferring skips over merges, even though it would be more
     legible. That would change the reported op set on real tapes and
     invalidate every measurement the spec's tables rest on. Filed here for
     Task 7 rather than acted on.
   - It also explains the spec's A2 line "20 adopted, 20 correct, **3
     declined**" on a 23-track tape: a single deleted donor track can cost two
     rows, not one.
   `test_align_durations_skips_a_target_track_no_merge_can_absorb` pins the
   mechanism directly.

3. **`penalty_sec = inf` ("forced") is unreachable.** The interface comment
   names it, and the branch is kept, but the DP can always fall back to
   "skip both sides", so the exclusion re-solve is never infeasible. Rather
   than ship an untestable branch silently I replaced the would-be inf test
   with `test_the_exclusion_penalty_is_what_the_best_rival_explanation_costs`,
   which pins the penalty's *meaning* (a lone pairing's penalty is exactly the
   two skipped durations, 600 s), and both the module and the test say inf is
   structurally unreachable.

4. **The brief's near-ambiguous sketch does not produce a low penalty.** "Two
   adjacent 300 s songs both sides" gives a penalty of ~600 s, not <60: barring
   a 1:1 op forces a skip on both sides, so the rival explanation always costs
   about a whole track. The mechanism that *does* produce a sub-60 penalty is
   a **short adjacent fragment** — the fixture uses a 25 s donor track between
   two songs and a 10 s boundary drift, giving penalty `2 × min(10, 25) = 20`.
   That is also the mechanism the constant's own comment describes ("boundary
   drift ~4 s … a one-song shift should cost about a song"), so the fixture is
   closer to the spec's reasoning than the brief's sketch was. Two rows decline
   there, not one — the ambiguity spans the pair of rows the shift would move,
   which the test asserts explicitly while rows 3–4 still adopt `"Charlie"` and
   `"Delta"` by exact string.

5. **Hygiene: composed, not copied, and pinned equal.** Per the brief,
   `is_real_title` / `is_junk_title` / `MAX_TITLE_LEN` are imported from
   `titles` / `setlist` and `fuzzy_norm_title` from `structure`, and
   `siblings._hygienic_title` composes them. Because that composition is
   itself a second copy of `structure._hygienic`'s *shape*,
   `test_hygiene_matches_structures_own_predicate_exactly` asserts the two
   agree title-for-title over a 14-case table (including `1922`, `d1t02`,
   `01`, `Encore:`, `3:45`, `Disc 2`, an 81-char string, and a metadata norm).
   The alternative — importing `structure._hygienic` directly — would have
   been zero-drift but falsifies that function's docstring claim to be "the
   only silent adopter in the pipeline". Flagging the trade rather than
   deciding it unilaterally.

## Concerns

- **The DP is O(n·m·MAX_MERGE²) per solve and `propose_rows` re-solves once
  per matched op**, so a pair is O(n²·m·9). At 30×30 that is microseconds
  (the whole 19-test file runs in 0.07 s), but Task 5 will call this for
  *every* donor in `candidate.recordings`. A 40-track tape against six donors
  is still fine; a pathological item with 200 "tracks" would not be. Not
  guarded here — flagging it as Task 5's call, since only gather knows how
  many donors it is about to try.
- **`align_durations` ties are broken by exploration order.** Documented in
  the docstring, exercised by the fixtures, and deliberately left alone (see
  finding 2). If Task 7's acceptance run shows the reported op set drifting
  between Python versions, this is where to look — dict/loop order here is
  deterministic, but the *equality* of the two explanations is the real
  fragility, not the language.
- **`MIN_MATCH_FRACTION` is computed over matched TARGET tracks only.** A
  donor twice the target's length matching the target's first half scores
  1.00. That is the spec's definition and matches the prototype, and the
  anchor-agreement guard above is what catches a wrong donor — but it is the
  same shape as the known coverage gap already recorded in CLAUDE.md
  (coverage never inspects unmatched *items*), so it should not be mistaken
  for a completeness check by Task 4.
- The evidence doc the constants cite,
  `docs/superpowers/2026-09-02-sibling-transfer-evidence.md`, does not exist
  yet — it is Task 7's deliverable, as the brief specifies. The citations are
  forward references by design.

---

# Fix round 1 — all six findings closed

**Status: DONE.** Commit `4b07645` — "siblings: fix round 1 — one hygiene
definition, a None-safe guard, real pins".

```
./.venv/bin/pytest -q
1590 passed, 7 deselected, 26 warnings in 4.96s
```

Suite delta from 1587, itemised (one case removed, so the plan constraint
applies):

| case | change |
| --- | --- |
| `test_residual_seconds_reports_each_pairings_duration_gap` | ADDED (finding 1) |
| `test_a1_a_donor_track_the_target_lacks_adds_no_row_to_the_target` | ADDED (finding 2) |
| `test_a_none_duration_declines_instead_of_raising` | ADDED (finding 3) |
| `test_one_file_may_hold_three_donor_songs` | ADDED (finding 5) |
| `test_hygiene_matches_structures_own_predicate_exactly` | REMOVED (finding 4) |

The removal is the finding, not collateral: that test existed only to pin two
copies of one composition equal, and the fix deletes the second copy. It could
not detect the drift it was written for (the spec reviewer added an arm to
`structure._hygienic` and it stayed green), so nothing that was actually being
verified is now unverified. What replaces it is stronger: mutating the single
definition turns `test_a_donor_track_titled_with_show_metadata_fails_hygiene`
**and** `test_hygiene_rejects_show_metadata_residue` red together — a
structure-side change is now visible from the siblings side, which is precisely
what the deleted table failed to do.

No other case was removed, renamed or weakened. `test_a2_…` / `test_a3_…` each
gained a sixth pair and two assertions; the merged-pairing fixture's
`residual_sec == 0.0` became `== 3.0`.

## The four required pins, verbatim under their own mutations

All run on copies outside the worktree via `$R/.venv/bin/python -m pytest` with
`PYTHONPATH` at the copy, `__pycache__` purged before and after each run. A
no-mutation baseline copy was verified green first (`1153 passed, 1 skipped`)
so that a red line means the mutation and not the copy.

**Finding 1 — `residual = 0.0` hard-coded**
`tests/test_siblings.py::test_residual_seconds_reports_each_pairings_duration_gap`
and `::test_a_merged_target_file_proposes_the_segue_join` (2 failed, 1151 passed):
```
>       assert got[1].residual_sec == 3.0   # 703 s of file against 700 s of donor
E       AssertionError: assert 0.0 == 3.0
E        +  where 0.0 = SiblingRow(track=1, proposed='Alpha > Bravo', donor_span=(0, 2), residual_sec=0.0, penalty_sec=600.0, verdict='adopt', reason='').residual_sec
```

**Finding 2 — donor-side-skip `continue` removed**
`tests/test_siblings.py::test_a1_a_donor_track_the_target_lacks_adds_no_row_to_the_target`
(1 failed, 1152 passed):
```
>       assert [r.track for r in rows] == [1, 2, 3, 4, 5]
E       assert [1, 1, 2, 3, 4, 5] == [1, 2, 3, 4, 5]
E
E         At index 1 diff: 1 != 2
E         Left contains one more item: 5
```
The duplicate `1` is the whole point: the mutant emits a row for the unmatched
donor track and breaks the one-row-per-target-track invariant Tasks 4–6 index
by. An assertion on `len(rows)` alone would have caught it here too, but an
assertion on the track *list* is what catches it when a duplicate replaces a
missing row rather than adding one.

**Finding 3 — `isinstance` arm removed (the pre-fix code)**
`tests/test_siblings.py::test_a_none_duration_declines_instead_of_raising`
(1 failed, 1152 passed):
```
>       rows, diag = propose_rows([300.0, None, 510.0], donor, metadata_norms=set())
>   return all(d > 0 for d in durations)   # MUTATION F3
E   TypeError: '>' not supported between instances of 'NoneType' and 'int'
```
The fixture uses a literal `None`, per the standing instruction — not `0`,
`-1`, `nan` or a stand-in. `nan` is separately handled (it fails `> 0`) but is
not what production produces.

**Finding 5 — `MAX_MERGE = 3 -> 2`**
`tests/test_siblings.py::test_one_file_may_hold_three_donor_songs`
(1 failed, 1152 passed):
```
>       assert got[1].proposed == "Alpha > Bravo > Charlie"
E       AssertionError: assert 'Alpha > Bravo' == 'Alpha > Bravo > Charlie'
E
E         - Alpha > Bravo > Charlie
E         + Alpha > Bravo
```

## Two-directional sweep of every ordered constant

Per the standing rule. Each row is a separate mutation run against the whole
affected suite; "red" names the first-listed failing test.

| constant | mutation | result |
| --- | --- | --- |
| `MAX_MERGE` 3 | → 1 | **9 red** — `…pairs_one_merged_file…`, `…skips_a_target_track…`, `…segue_join`, `…three_donor_songs`, A1, A2, A3, near-ambiguous, split |
| | → 2 (down) | **1 red** — `test_one_file_may_hold_three_donor_songs` (the new pin; this direction was free before) |
| | → 4 (up) | **1 red** — `test_too_few_matched_tracks_declines_the_whole_pair` (a wider merge lets one donor track absorb 4 target tracks and clear `MIN_MATCH_FRACTION`) |
| | → 5 (up) | **1 red** — same |
| `MIN_EXCLUSION_PENALTY` 60.0 | → 0.0 (down) | **1 red** — `test_near_ambiguous_pairing_declines_on_weak_evidence` |
| | → 600.0 (up) | **3 red** — `…one_to_one_alignment…`, A2, A3 |
| `MIN_MATCH_FRACTION` 0.80 | → 0.0 (down) | **1 red** — `test_too_few_matched_tracks_declines_the_whole_pair` |
| | → 1.0 (up) | **2 red** — A2, A3 (each matches 5 of 6) |
| `SKIP_COST_MULT` 1.0 | → 0.5 (down) | **2 red** — `…skips_a_target_track…`, `…exclusion_penalty…` |
| | → 2.0 (up) | **5 red** — `…skips_a_target_track…`, A2, A3, A1, `…exclusion_penalty…` |
| `structure.hygienic_title` | metadata_norms clause dropped | **2 red**, one on each side of the promotion — `test_a_donor_track_titled_with_show_metadata_fails_hygiene` (siblings) and `test_hygiene_rejects_show_metadata_residue` (structure) |

No direction of any constant is free. Nothing to report against the tests.

Note on `MIN_MATCH_FRACTION → 1.0`: the two tests that catch it are A2 and A3,
which now sit at 5/6 = 0.833 rather than exactly 0.80. Moving them off the
boundary did not cost the up-direction pin — it improved it, because at exactly
0.80 the up-mutation was being caught by a float comparison landing on the
threshold rather than by the fixture's shape.

## What changed, file by file

- `packages/llama/src/llama/structure.py` — `_hygienic` → public
  `hygienic_title`, docstring rewritten to say why it is single-sourced and to
  record the failed-pin history; `adopt_gap_titles`' call updated. No behaviour
  change; `adopt_gap_titles` untouched otherwise.
- `packages/llama/src/llama/siblings.py` — duplicated composition deleted and
  `hygienic_title` imported; `_all_present` added; the two `INF` branches
  documented as unreachable.
- `packages/llama/src/llama/titles.py`, `correspondence.py`,
  `tests/test_structure.py`, `tests/test_titles.py` — prose and import
  references follow the rename. No logic touched. (I renamed rather than
  keeping a `_hygienic` alias: the house pattern beside it
  (`_is_junk_title = is_junk_title`) exists for a genuinely external name,
  whereas this one had three call sites, all in-tree.)

## Concerns after the fix round

- **Unchanged from the first report:** the skip/absorb cost degeneracy
  (finding 2 there), the per-op DP re-solve fan-out (deferred to Task 5 by
  ruling — the orchestrator's 0.064 s at 40×40 / 1.77 s at 120×120 per donor
  is the number to plan against), and `MIN_MATCH_FRACTION` being measured over
  matched *target* tracks only.
- **New, minor:** `structure.py` now has a public name that `siblings.py`
  imports, so `structure` → `siblings` must never become a dependency in the
  other direction. Nothing today does that, and `siblings.py` importing
  `structure` (not the reverse) keeps the layering the spec asks for, but Task
  4 puts the guard on top of both and is where that could be gotten wrong.
- The evidence doc the constants cite is still Task 7's deliverable.
