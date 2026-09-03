# Task 2, fix round 2 -- scoped re-review verdict

Commit under review: `e1c0be9` only (`06d526e`/`48d6d61` are orchestrator
docs commits, not reviewed). Worktree clean at `e1c0be9`, no commits made.
Pointer guard: `PTH-GUARD: OK`.

## Finding 1 -- restore `"3"` to the negative parametrize: **ADDRESSED (verified by mutation)**

`test_titles.py:130` now reads
`@pytest.mark.parametrize("cleaned", ["3", "01", "174", "19770101", "12345"])`.

Independently verified on a shadowed copy (shadowing proven first with a
planted `T2_REREV2_SENTINEL`, read back from
`.../workc/t2-rerev2/packages/llama/src/llama/titles.py`; worktree confirmed
unpolluted; `__pycache__` purged before and after).

Mutation applied: `_YEAR_LIKE_NUMERIC = re.compile(r"\d{4}")` ->
`re.compile(r"\d{4}|\d")` (confirmed live: `is_real_title('3')` -> `True`).

Result -- `./.venv/bin/python -m pytest .../test_titles.py -q`:

```
FAILED test_is_real_title_still_rejects_non_year_numeric_residue[3]
>       assert is_real_title(cleaned) is False
E       AssertionError: assert True is False
E        +  where True = is_real_title('3')
1 failed, 56 passed in 0.10s
```

The restored case lands in a parametrize that DOES exercise the predicate --
it is the sole failure among 57, which also independently confirms the
report's claim that no other single-digit `is_real_title` case exists in the
file. Mutation reverted; copy byte-identical to the worktree afterward.

## Finding 2 -- drop the unsupported `_show_metadata_norms` attribution: **ADDRESSED**

The "1-item difference from approximating `_show_metadata_norms`" claim is
gone. Replacement text is accurate and the stated arithmetic checks out as
written: 181 entries - 19 newly-passing entries = 162; 181 - 18 distinct
newly-passing items = 163 (explicitly labelled "the mismatched 163", so the
deliberate unit mismatch is the point, not an error). The list itself is
consistent with both: 18 item lines, 19 titles, `minutemen1984-07-14`
carrying two (`2008, 2021`) -- so it is correctly named as the boundary case.
"162 confirmed under two independently built date-source approximations" is
a restatement of the re-reviewer's own derivations, not a new unbacked claim.

## Finding 3 -- self-contradiction ("not real songs"): **ADDRESSED**

The block now opens "This list is NOT uniformly junk" and names `1977`
(`MWatt2013-01-12`) and `1662` (`turkuaz2018-01-18`) as the two real songs,
scoping the junk claim to the REST of the list. Verified those two ARE
established as real songs earlier in the same comment (`titles.py:33` "Clash
cover", `:35` "Turkuaz original"), so the block no longer asserts something it
disproves. Internally consistent: 19 entries = 2 real songs + 17 junk, which
matches the finding's framing.

## Suite-count delta itemisation: **PRESENT and correctly framed**

Report section "Suite-count delta, itemised" states round 1 -> round 2 as
1567 -> 1568, net +1, attributed case-by-case to the restored `"3"` and
nothing else, with a note that it was not subsumed (unlike the round-1
trims). It also pays back a retroactive case-by-case itemisation of round 0
-> round 1's -1 (`d1t02` and `12` removed as subsumed, `3` removed in error,
`19770101` and `12345` added). Not a bare number.

## Deferred (out of scope, one line each)

- `\d` matches Unicode digits: `is_real_title("١٩٧٧")` is
  True. Pre-existing under `^\d{4}$`, already recorded in-code as DEFERRED --
  no action wanted here.

## Verdict

**APPROVED.** All three Minor findings ADDRESSED; finding 1's pinning proven
by mutation rather than by reading. No Critical or Important issues. Full
suite not re-run (per instruction); the 57-test `test_titles.py` run under
mutation was the only suite execution.
