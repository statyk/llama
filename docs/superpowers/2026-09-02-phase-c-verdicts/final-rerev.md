# Final fix-wave re-review — 6859fe5..9971435

Pointer guard: `PTH-GUARD: OK`. Worktree unmodified (`git status --porcelain` clean
after every mutation). No commits.

## Verdicts

| # | Item | Verdict |
|---|---|---|
| 1 | MAJ-1 FLOOR near-boundary fixture | **ADDRESSED** |
| 2 | Task 2 Unicode gap (`\d{4}` -> `[0-9]{4}`) | **ADDRESSED** |
| 3 | spec:390-391 "6.7x enrichment" | **ADDRESSED** |
| 4 | spec:192 790 denominator | **ADDRESSED** |
| 5 | `_donor_key` docstring / evidence Step 9 | **ADDRESSED** |
| 6 | evidence doc flags library non-frozen | **ADDRESSED** |
| 7 | plan Global Constraints near-boundary amendment | **ADDRESSED** |

## Item 1 — the one with teeth

Both mutations run by me, `__pycache__` purged between runs, `siblings.py:333` restored
and verified after each.

- **`FLOOR = 0.30` (loosen, near-boundary) — NOW FAILS.**
  `packages/llama/tests/test_siblings.py::test_agreement_inside_the_030_to_050_band_still_declines`
  Verbatim red line: `assert res.band == "declined"` ->
  `E AssertionError: assert 'operator' == 'declined'`.
  Result: `1 failed, 1643 passed`. It is the ONLY failure — the new fixture is the sole
  thing pinning that direction, exactly as claimed.
- **`FLOOR = 0.75` (tighten) — STILL FAILS.**
  `test_siblings.py::test_agreement_below_auto_but_above_floor_routes_to_the_operator`
  Verbatim red line: `assert res.band == "operator"` ->
  `E AssertionError: assert 'declined' == 'operator'`; plus
  `test_cli.py::test_delmccoury_shaped_operator_band_confirms_only_unresolved_rows`.
  Result: `2 failed, 1642 passed`.

**The thing the original rule missed — computed independently**, by re-running the
fixture body outside pytest against the shipped constants:

```
n_anchors= 5 agreement= 0.4 band= declined FLOOR= 0.5 AUTO= 0.8
inside [0.30,0.50)? True
```

Agreement is **0.40**, strictly inside `[0.30, 0.50)` — 5 anchors, 2 agreeing. It is
not far on the other side; it flips precisely because the boundary moved past it.
The fixture pins the boundary, not the constant's existence.

## Item 2 — Unicode gap and the standing ruling

- `is_real_title("1922")` -> `True`; `is_real_title("2001")` -> `True`;
  `is_real_title("١٩٧٧")` (Arabic-Indic 1977) -> `False`.
- `git diff 6859fe5..9971435 -- packages/llama/src/llama/titles.py` is **2 changed
  lines** (one `-`, one `+`): `_YEAR_LIKE_NUMERIC = re.compile(r"\d{4}")` ->
  `re.compile(r"[0-9]{4}")`. Nothing else. Test side is one new test
  (`test_is_real_title_rejects_unicode_digits`, +12 lines, docstring included).
  The standing ruling ("character class plus a test, else deferred") is satisfied —
  no finding.

## Items 3-6 — read-level, each checked against the artifact it cites

- **3.** spec now gives all three quantities and labels 20-vs-3 a **raw count (6.7:1)**,
  not a rate; 6.5x as a share of wrong rows (13.1% vs 2.0%); 19.1x as a rate over rows
  (0.431% vs 0.023%). Matches evidence doc lines 645-650 verbatim in substance,
  including the doc's own "an earlier draft called it '6.7x enrichment', which named
  the wrong quantity" retraction. The `Tuning`/tape-wrong breakdown of the 3 admitted
  is preserved.
- **4.** spec now discloses the dispute: two reconstructions + a third recount all got
  **782**, the third against a cache grown **968 -> 981**, so no recount confirms 790
  against its own population; numerator 14 stable; conclusion independent of the
  denominator. Matches evidence doc lines 555-576.
- **5.** `gather._donor_key`'s docstring cites evidence Step 9 and claims
  135 of 136 slide-shaped pairs are kept out of the automatic band by donor selection.
  Evidence doc line 678: "donor selection removes 135/136". It also claims "two tests
  pin the ordering (a reversed sort fails in both gather and cli)" — **I mutated
  `return (-rank, ...)` to `return (rank, ...)` and got exactly two failures**:
  `test_cli.py::test_best_donor_picks_the_higher_agreement_donor_not_the_worse_one`
  and `test_stage_gather.py::test_the_higher_agreement_donor_wins_not_the_alphabetically_first_one`
  (`2 failed, 1642 passed`). The docstring's claim is literally true, one per module.
- **6.** Evidence doc's new header block flags **both** populations as non-frozen:
  cache 968 -> 981 and library "89 shows" -> **98**. Independently verified:
  `ls -d ~/.llama/shows/*/ | wc -l` = **98**.

## Item 7 — the amendment reads as one idea

Plan `## Global Constraints`, consecutive lines:

- **21** — degenerate-fixture constraint (unchanged).
- **22** — NEW unifying statement: "The test data must be positioned where the thing
  being tested actually decides — the same failure as the bullet above, at different
  coordinates", explicitly forward-referencing the next bullet.
- **23** — both-directions rule, now carrying "**AND AT LEAST ONE MUTATION IN EACH
  DIRECTION MUST LAND NEAR THE BOUNDARY**" plus "A fixture set that only flips under a
  distant mutation does not pin the bound; it pins the fact that the constant exists."
- **24** — the FLOOR worked example, naming the "passed the rule and was still
  half-loose" case: 0.75/0.10 passed, 0.10 flips fixtures at 0.20/0.15 "for a reason
  unrelated to where the real boundary sits", 0.30 left all 1642 green.

Adjacency and the unifying statement both hold. The 0.75/0.10 attribution is accurate:
`task-4-report.md:109-110` records exactly those two mutations for FLOOR. The bullet
was MOVED here from its old position (after the count/unit bullet), not duplicated —
the diff shows one deletion at the old site.

## Scope

`git diff 6859fe5..9971435 -- packages/llama/src/` touches exactly two files:
`titles.py` (+1/-1, the character class) and `stages/gather.py` (+11/-1, docstring
only — the `rank`/`return` lines are untouched context). Nothing else. Independently
confirmed; the caller's own check holds.

## Suite

`1642 -> 1644`, delta itemised as exactly two added tests:

1. `test_siblings.py::test_agreement_inside_the_030_to_050_band_still_declines`
2. `test_titles.py::test_is_real_title_rejects_unicode_digits`

`git diff 6859fe5..9971435 -- packages/llama/tests packages/emcee packages/herder scripts`
is **32 insertions, 0 deletions** — grep for `^-[^-]` returns nothing, so no test was
removed, and no assertion was weakened. Full suite at HEAD:
`1644 passed, 7 deselected` (6.88 s).

## New breakage in the fix diff

None found.

## Overall verdict

**All seven items ADDRESSED. No new breakage. Fix wave accepted.**
