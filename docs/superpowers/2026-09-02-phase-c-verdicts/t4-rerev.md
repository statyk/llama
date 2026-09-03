# Task 4 — fix round 1, scoped re-review

**Overall: ACCEPT.** All five findings ADDRESSED. Every mutant reproduced independently
out-of-worktree; no new breakage in the fix diff.

## Method

- `PTH-GUARD: OK` (worktree). Copies under `.../scratchpad/workc/t4-rerev/{base,mut-*}`,
  driven by `$WORKTREE/.venv/bin/python -m pytest` + `PYTHONPATH` (never a `.venv/bin/*`
  console script, never `pip`). Shadowing proven with a planted sentinel:
  `SENTINEL_T4REREV` visible under `PYTHONPATH`, `MISSING` from the worktree import;
  sentinel removed and `diff -q` back to the worktree clean afterwards. Per-run
  `assert '<mut>/packages' in llama.__file__`; `__pycache__` purged before and after
  every run. Worktree read-only, `git status` clean, no commits.
- Reviewed `f149111` only. `453deff`, `0e218e2`, `1170b7d`, `1f60c62` are docs-only and
  were not reviewed. `git diff f149111 HEAD -- packages/llama/{src,tests}` is empty, so
  the copy is the fix commit's code.
- Baseline copy: **1220 passed, 7 deselected** over `packages/llama/tests/`.

## Findings

### 1. Band precedence unpinned — ADDRESSED

Mutant **D** (ladder reordered so `declined` outranks the anchor-count clause):
**1 failed, 1219 passed.**
Red: `test_a_single_disagreeing_anchor_routes_to_the_operator_not_declined`
`assert res.band == "operator"` → `AssertionError: assert 'declined' == 'operator'`.
The fixture is the separating case as claimed: `n_anchors == 1`, `agreement == 0.0`,
one disagreement `(1, "Casey Jones", "Alpha")`. Nothing else in the tree sees the
reorder — the new test is the sole guard.

### 2. `bool(row.proposed)` hollow — ADDRESSED, and the two pins are genuinely separate

Mutant **H** (delete `and bool(row.proposed)`): **2 failed, 1218 passed** —
`test_a_row_with_no_proposal_does_not_crash_the_guard` and
`test_a_track_paired_with_an_untitled_donor_is_not_counted_as_an_anchor`, both by
`AttributeError: 'NoneType' object has no attribute 'replace'`.

**Separateness demonstrated**, not asserted. Mutant **H2** (drop the clause *and* make
the comparison `None`-safe with `row.proposed or ""` — crash gone, denominator widened):
**1 failed, 1219 passed**, and the survivor is the crash test. The only red line is
`assert res.n_anchors == 1                   # track 1 only, not track 2`
(`GuardResult(agreement=0.5, n_anchors=2, disagreements=[Disagreement(track=2,
tape_title='Bravo', proposed=None)], band='operator')`). So a change to the denominator
half does **not** necessarily redden the crash half — which is exactly the rot a single
combined test would have hidden, since the natural "fix" for the crash is the `or ""`
that silently changes the denominator. (The converse direction is vacuous: the crash
guard and the denominator are one clause, so any crash-introducing change also moves the
count. H2 is the direction that matters.)

Fixture fidelity checked, not taken on trust: `_untitled_donor_pairing` hand-writes
`SiblingRow(2, None, (1, 2), 0.0, 900.0, "decline", "sibling track untitled")` and claims
it is what the DP emits. `propose_rows` really does emit
`SiblingRow(i0 + 1, None, span, residual, penalty, "decline", "sibling track untitled")`
(siblings.py ~line 294) — donor_span non-`None`, `proposed=None`. The claim holds.

### 3. `test_cplus_leaves_a_layer_three_decline_reason_alone` hollow — ADDRESSED

Mutant **E** (delete `r.verdict == "adopt"` from `cplus_filter`'s final comprehension):
**1 failed, 1219 passed.**
Red: `test_cplus_leaves_a_layer_three_decline_reason_alone`
`assert by[3].reason == "sibling track untitled"      # layer 3 survives`
→ `AssertionError: assert 'tracks 3-4: ...eeing anchors' == 'sibling track untitled'`.
The re-fixtured run is a tail run (tracks 3-4), which `gap_span` never brackets, so C+
genuinely demotes and the guard is exercised. Assertions went 1 → 3 (adds the C+ reason
on track 4 and its verdict). The old fixture's case (a bracketed count-forced run that C+
passes) is not lost — `test_a_bracketed_count_forced_interior_run_adopts_its_titles`
still covers it.

### 4. The donor-span-slide fixture — ADDRESSED on the rename; the new fixture is a *disclosed partial*, and I want the residual stated plainly

**The rename half is fully addressed.** `_localised_shift` → `_tape_tag_shift` with a
docstring that now says what it actually is (ops 1:1, alignment correct end to end, the
tape's own tags shifted, two of the three blocked titles correct). I confirmed the ops
are 1:1 by dumping the rows: spans `(0,1)…(9,10)` then `(10,12)`, `(12,13)`, `(13,14)`.
The prior overclaim is gone.

**The new `_donor_span_slide` fixture: I dumped it rather than reading its docstring.**
What I verified as TRUE:
- Built through the real DP (`propose_rows`) from real durations, not hand-assembled.
- Ops genuinely non-1:1: track 7 is a merge, span `(6, 8)`; the run 5-7 covers donor
  span `(4, 8)` — 4 donor tracks for 3 files.
- Tape tags all correct/self-consistent: `agreement == 1.0`, `n_anchors == 6`,
  `disagreements == []`, band `auto`.
- All three interior rows are `verdict="adopt"` at layer 3 — penalties **406.0, 406.0,
  240.0** against `MIN_EXCLUSION_PENALTY = 60.0`, exactly as the docstring states.
- The decline is attributable to **count-forcing alone**: `gap_span` returns `(4, 8)`
  (bracketing succeeds and contributes nothing), the ratio says `auto`, and mutant **B**
  (count-forcing clause deleted) gives **3 failed, 1217 passed** including
  `test_a_donor_span_slide_adopts_zero_interior_titles_under_cplus`. Reason string on all
  three tracks: `"tracks 5-7: donor span holds 4 tracks for a 3-file run"`.

What I judge **NOT** established — the one thing the acceptance wording asked me to
attack hardest: **the three interior titles are not demonstrably wrong.** Their
wrongness exists only in the docstring's declaration. Donor `[…, Echo 205, Foxtrot 395,
Golf 305, Hotel 120, …]` against target `[…, 207, 393, 425, …]`: the DP's reading
(Echo / Foxtrot / Golf > Hotel) has residuals **2.0, 2.0, 0.0**, while the fixture's
declared truth (Foxtrot / Golf / Hotel) would require duration errors of ~188 s, ~88 s
and ~305 s. By the fixture's own numbers the DP is right and the declared truth is the
implausible reading. So this test pins C+'s **yield cost** — a correct proposal declined
because the donor has one more track than the target has files — not C+ preventing an
error.

That is a materially weaker overclaim than last round's (there the fixture reproduced a
*different* mechanism; here it reproduces the right *arithmetic* signature with a
stipulated rather than exhibited error), and, decisively, **the implementer disclosed it
himself**: the docstring's "HONESTY NOTE ON THE DURATIONS" states the compromise and its
structural cause (a credible slide is either duration-implausible or penalty-ambiguous
and declined by layer 3 first — measured penalties 2-18 s), and the report escalates it
as an open question for Task 7's blind arm. The mislabelling that made this a finding is
cured. I therefore verdict **ADDRESSED**, with two residuals for the record:

- **Wording still one notch hot.** The docstring headline "THE DONOR-SPAN SLIDE — the
  class the spec names" and the report's "it does reproduce the spec's class" are not
  supported by the fixture's own durations. Suggest: "the *arithmetic signature* of a
  donor-span slide". Docstring change only, no test change.
- **Concern 6 in the report is the right escalation and should not be lost.** If Task 7's
  blind arm finds no real donor-span slide, this test is pinning a yield cost with no
  demonstrated error prevented, and C+'s count-forcing justification rests on the
  tag-shift class plus the merge case.

The test is nonetheless load-bearing and better than what it replaced: it is the only
count-forcing test built through the real DP *and* at agreement 1.0, and it asserts the
span (`by[5].donor_span == (4, 5)`), not just the title, so a fixture that stopped
reproducing the shape fails rather than passes vacuously.

### 5. `_anchor_agrees` — ADDRESSED

Both call sites route through it: `rate_alignment` line 451, `cplus_filter` line 521. No
inline composition of the predicate remains (`loosely_same_title` appears exactly once in
executable code, inside `_anchor_agrees`). `rate_alignment`'s denominator still uses
`_anchor_row`, which is correct — the denominator is anchors, not agreeing anchors.

Mutant **F** (drop the `loosely_same_title` conjunct from `_anchor_agrees`):
**7 failed, 1213 passed**, red in **both** layers —
layer 1: `test_agreement_below_auto_but_above_floor_routes_to_the_operator`,
`test_agreement_below_floor_is_declined_outright`,
`test_a_single_disagreeing_anchor_routes_to_the_operator_not_declined`,
`test_a_tape_tag_shift_passes_the_ratio_band_the_ratio_is_blind`;
layer 2: `test_runs_decline_individually_one_unbracketed_run_does_not_sink_the_pair`,
`test_a_disagreeing_anchor_does_not_bracket_even_though_it_is_titled`,
`test_a_tape_tag_shift_adopts_zero_interior_titles_under_cplus`.

## Suite delta — itemised, CONFIRMED

`f149111` touches exactly two files (`siblings.py`, `test_siblings.py`), so the whole
1617 → 1622 delta is in `test_siblings.py`. Test-function name sets: **41 → 46 (+5)**.
No `parametrize`, `skip` or `xfail` anywhere in the file, so 1 function = 1 case and +5
functions is exactly +5 cases.

- **Added (5):** `test_a_single_disagreeing_anchor_routes_to_the_operator_not_declined`,
  `test_a_row_with_no_proposal_does_not_crash_the_guard`,
  `test_a_track_paired_with_an_untitled_donor_is_not_counted_as_an_anchor`,
  `test_a_donor_span_slide_passes_the_ratio_band_with_perfect_agreement`,
  `test_a_donor_span_slide_adopts_zero_interior_titles_under_cplus`.
- **Renamed (3) — verified renames, not rewrites, by AST body comparison** (docstrings
  stripped, helper rename normalised):
  - `test_an_unpaired_tagged_track_is_not_an_anchor` →
    `test_a_track_the_dp_paired_with_nothing_is_not_an_anchor` — **byte-identical body**,
    2 asserts → 2.
  - `test_the_localised_shift_passes_the_ratio_band_the_ratio_is_blind` →
    `test_a_tape_tag_shift_passes_the_ratio_band_the_ratio_is_blind` — only diff is
    dropping the unused third return value (`rows, tracks, _` → `rows, tracks`);
    4 asserts → 4.
  - `test_the_localised_shift_adopts_zero_interior_titles_under_cplus` →
    `test_a_tape_tag_shift_adopts_zero_interior_titles_under_cplus` — same single diff;
    10 asserts → 10.
  - Helper `_localised_shift` → `_tape_tag_shift`: body identical but for the return
    arity; **all 14 donor and 13 target durations unchanged**, so the fixture is the same
    fixture under an honest name.
- **Removed: 0.** `comm` over the name sets shows the only names leaving are the three
  renamed-away ones, each with a renamed-to counterpart.
- **Re-fixtured (1), name unchanged:** `test_cplus_leaves_a_layer_three_decline_reason_alone`,
  strengthened 1 assert → 3.
- **Nothing weakened:** file-wide assert count 167 → 190; every renamed test kept its
  exact assertion set.

## New breakage in the fix diff

None. Base copy green at 1220. The only source change is additive (`_anchor_agrees`) plus
the two call sites now delegating to it; behaviour is identical by construction and mutant
F confirms the delegation is live in both layers.

## Deferred (out of scope, one line each)

- `test_a_row_with_no_proposal_does_not_crash_the_guard`'s assertion
  (`res.band in {all four bands}`) is tautological — it is purely a no-raise test, which
  is honest but worth naming as such.
- `_donor_span_slide`'s docstring/report headline overclaims by one notch (see finding 4);
  wording only.
- Report's own carry-overs still open: `tracks: list` untyped in the public signatures;
  the unstated positional contract between `rows` and `tracks`; the vacuous second
  assertion in `test_cplus_says_nothing_about_a_track_that_already_has_a_title`;
  concerns 1-6 from the two reports.
