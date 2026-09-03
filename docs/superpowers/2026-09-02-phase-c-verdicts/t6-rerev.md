# Task 6 fix round 1 — scoped re-review verdict

Scope: `18e618f` only. `2f12052` (docs) not reviewed. Worktree read-only, no commits.
PTH-GUARD: OK. Shadowing proven by planted sentinel (`SENTINEL_MARKER_T6RR` resolved
from the copy tree); `__pycache__` purged before/after every run. All mutation runs via
`$WT/.venv/bin/python -m pytest` with `PYTHONPATH` shadowing the copy at
`scratchpad/workc/t6-rerev/`. Copy verified byte-identical to worktree before and after.

## Per-finding verdicts

| # | Verdict |
|---|---------|
| I1 no-anchors block | **ADDRESSED** |
| I2 per-row decline reasons | **ADDRESSED** |
| I3 residual_sec | **ADDRESSED** |
| I4 declined title leak | **ADDRESSED** |
| I5 duplicated winner selection | **ADDRESSED** |
| I6 empty-picks preemption | **ADDRESSED** |

## Mutant results (all five re-applied independently)

**I1** — deleted the whole `if res.band == "no-anchors":` block.
`test_untagged_fixture_with_tagged_donor_renders_sibling_proposal` RED at:
`assert "embeds in canonical setlist: 2/23 (9%)" in result.output`

**I2** — deleted the `_sibling_run_reasons` render loop. THREE tests RED;
`test_untagged_fixture_with_tagged_donor_renders_sibling_proposal` RED at:
`assert "track 15: sibling track untitled" in result.output`
(also reddens `test_weak_evidence_decline_keeps_the_dp_candidate_out_of_the_write` and
`test_operator_band_donor_untitled_on_the_gaps_falls_through_to_the_dp`)

**I3** — `residual_sec=row.residual_sec` -> `residual_sec=0.0`.
`test_untagged_fixture_with_tagged_donor_renders_sibling_proposal` RED at:
`assert "12s" in row2 and "0s" not in row2`
Mutant output showed row2 as `   2.   7:10     0s  Song 02` vs the truth's `12s`.

**I5** — `candidates.sort(key=lambda c: c[0], reverse=True)` inside the single shared
`gather.best_donor`. RED in BOTH paths:
- CLI: `test_best_donor_picks_the_higher_agreement_donor_not_the_worse_one` at
  `assert f"donor {donor_a_ident}" in result.output`
- gather: `test_the_higher_agreement_donor_wins_not_the_alphabetically_first_one` at
  `assert [got[i].title for i in (2, 3, 4, 5)] == [`

**I6 inverse** — removed `if not picks: return None`.
`test_operator_band_donor_untitled_on_the_gaps_falls_through_to_the_dp` RED at:
`assert "proposal (duration-model)" in result.output or "proposal (sibling-duration)" in result.output`

## Independent checks

**I3 non-degeneracy — PASSES.** The fixture, not the assertion, changed: the
`residual_sec=0.0` mutant reddens, which is only possible if the truth is non-zero.
Asserted value is the specific `"12s"`, paired with `"0s" not in row2` and a
same-table zero-residual control on track 1. Assertion was not loosened to the data.

Swept the other new fixtures for the same degenerate shape — none found:
- I1 coverage figure `2/23 (9%)`: non-zero numerator, and denominator 23 != 24 kept files
  (track 15 declines), so neither half is the input count. Verified independently by
  planting a `return 0, len(adopted)` stub at the top of `_sibling_donor_coverage` — RED
  on the same assertion, so the figure is genuinely computed.
- I4: `assert ov.titles == {3: "Charlie", 4: "Delta"}` — non-empty exact dict.
- I5: `assert ov.titles == {2: "Bravo", 3: "Charlie"}` — non-empty exact dict.
- I6: `assert ov.titles == ANCHORED_GAPS`, a 3-entry non-empty module constant.
The only zero/empty/negative assertions (`assert 15 not in ov.titles`,
`assert 1 not in ov.titles and 2 not in ov.titles`) are each paired with a positive
exact-dict assertion in the same test.

**I4 property-vs-mechanism — PASSES, and it is the property.** Decisive run: reverted
`picks` to a non-verdict gate (`if row.proposed and ...`) while leaving the RENDERING
untouched, so declined rows still print blank — the mechanism still looked correct.
`test_weak_evidence_decline_keeps_the_dp_candidate_out_of_the_write` still went RED, at
the write assertion (test_cli.py:1267), `Left contains 2 more items: {1: 'Alpha > Crowd
Noise', 2: 'Bravo'}`. So the test catches a leak that the blank-row rendering hides —
it is asserting absence from the written `overrides.titles`, not a blank row.
Confirmed in source: `if is_adopt and show.tracks[...].title_source == "unresolved"`
gates on the raw `SiblingRow.verdict`, never on `ProposalRow.title` truthiness.
The reverse route (rendering `title=row.proposed` for declines while keeping the verdict
gate) leaves the write dict correct — the two are properly decoupled.

**I5 single definition — CONFIRMED.** `cli.py` contains no `candidates.sort`,
`_donor_key`, `propose_rows`, `rate_alignment` or `load_donor_tapes` call — the only
occurrences of those names are inside the `_sibling_proposal` docstring. `best_donor` is
the sole definition (`gather.py:170`) and both `_sibling_transfer` and
`cli._sibling_proposal` call it; the single reverse-sort mutant reddens both paths.

**Private imports — CONFIRMED.** `cli.py` has exactly three `gather` imports:
`best_donor`, `show_metadata_norms` (line 1405) and `build_canonical` (line 1537). Zero
underscore-prefixed names. (Line 1368's `gather._sibling_transfer` is docstring prose.)

**Suite delta — CONFIRMED exactly.** `--collect-only` on both trees:
3f68c86 = `1639/1646 tests collected`; 18e618f = `1642/1649`. Deselected count unchanged
at 7. Test-function name diff over `test_cli.py`: exactly 3 added
(`test_best_donor_picks_the_higher_agreement_donor_not_the_worse_one`,
`test_operator_band_donor_untitled_on_the_gaps_falls_through_to_the_dp`,
`test_weak_evidence_decline_keeps_the_dp_candidate_out_of_the_write`), zero removed.
`test_cli.py` is the only test file the diff touches, so
`test_untagged_fixture_with_tagged_donor_renders_sibling_proposal` is the one
strengthened in place. Scoped green: 182 passed across
test_cli.py + test_stage_gather.py + test_siblings.py on the restored copy.

## New breakage in the fix diff

**None.** Reviewed `_sibling_run_reasons` by hand: traced adopt/decline interleavings,
adjacent declines with differing notes, and trailing runs — the run boundaries are
correct, and an adopted row can never carry a reason on this path
(`siblings.py:305` constructs adopts with the default empty reason; the only adopt+reason
producer is `cplus_filter`, which this renderer never calls, spec invariant 1).

## Deferred (out of scope — pre-existing, NOT introduced here)

- `scripts/blind_tag_gapfill.py` is un-importable. It imports `_show_metadata_norms`,
  which `18e618f` renamed to `show_metadata_norms` — but it was ALREADY dead at
  `3f68c86` on `_sibling_titles` (verified: pre-fix import fails first on
  `_sibling_titles`), so this diff deepens an existing break rather than causing one.
  No test imports the script, which is why the suite stayed green through both. Worth an
  owner ticket given this project's "instruments are code" rule.

## Overall verdict

**ACCEPT.** All six findings ADDRESSED. Every one of the five hollow-coverage mutants
kills its named test, I3's non-degeneracy and I4's property-level assertion both hold up
under independent adversarial mutation, `best_donor` is a genuine single definition,
`cli.py` imports no private gather symbol, and the suite delta is exactly +3 with
nothing removed or weakened.
