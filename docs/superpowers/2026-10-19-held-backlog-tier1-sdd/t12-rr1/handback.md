### Finding Verdicts

- **1. IMPORTANT `_city_parts` spaced region punctuation (D.C. -> d c)**: ADDRESSED. packages/llama/src/llama/structure.py:410-411 now deletes non-[a-z0-9 ] characters from the region field (`re.sub(r"[^a-z0-9 ]", "", ...)`) and collapses whitespace, before the `_COUNTRY_NOISE` strip (:412-414) and the `_REGION_FOLDS` fold (:415). The key keeps punctuation-to-space via `_clean_place` (:407). The three required rows are added to `test_cities_compatible` (packages/llama/tests/test_structure.py:2003-2004), which asserts both directions. I checked this directly with the worktree venv, confirming that `llama.__file__` resolves inside the worktree. `_city_parts` returns `('washington','dc')`, `('utica','ny')` and `('new york','ny')` for the punctuated forms, and `cities_compatible` is True in both directions for all three. `Vancouver, B.C.`/`BC` also works. The implementer reports that a mutant turning punctuation back into spaces makes all three new rows fail, which matches the diff.
- **2. Bare `6` one-edit floor at :312 and :421**: ADDRESSED. `_ONE_EDIT_MIN_LEN = 6` is defined at structure.py:281, with a comment citing spec Slice 1 "New constants" (6-character floor). It replaces both bare literals, at :317 (`_tokens_equal`) and :427 (`cities_compatible`). A grep finds no other `>= 6` in structure.py. The only remaining mention is the prose "(>= 6 chars)" in the `cities_compatible` docstring at :419.

### New Breakage in the Fix Diff

- Minor: structure.py:410. A region that joins its tokens with punctuation now merges them into one token, so the country-noise strip no longer reaches the country part. `Austin, TX-USA` -> region `txusa`, so `cities_compatible("Austin, TX-USA", "Austin, TX")` is False in both directions. Before the fix the region read `tx usa` -> `tx` and the call returned True. I verified this with a direct call. This follows the brief's literal wording at task-12-brief.md:38 ("punctuation dropped"). The error is conservative: a false "incompatible" holds a show for review and never ships one wrongly. It is non-blocking. One possible fix is to keep the dash/slash as a separator and drop only `.`.

No Critical or Important breakage.

### Out-of-Scope Observations

None.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage. One Minor (hyphen-joined `REGION-USA`) goes to the ledger for the final review.
