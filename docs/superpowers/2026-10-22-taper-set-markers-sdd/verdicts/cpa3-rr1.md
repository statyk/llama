# cpa3-rr1: scoped re-review of fix round 1 (5da667b..6cf03ea)

**Verdict: ALL ADDRESSED, NO NEW BREAKAGE.** Status: DONE. No commits, no repo edits.

## Findings
- **F1: ADDRESSED.** A bare `Set` item in a numbered set now counts as set-like.
  - Code: `taper.py:557-558`, `if item.title.strip(_ITEM_DECOR).lower() == "set": return True`. It runs after the encore skip (`:555-556`), so only items in sets 1, 2 and 3 are affected. This is ruling R10.
  - Tests:
    - `test_split_ordinal_header_is_set_like` (the reviewer's `Third Set` case);
    - `test_bare_set_item_is_set_like` (4 decorations);
    - `test_bare_set_item_real_case_is_not_owned` (DSO-2012-05-19 description, verbatim).
  - `"Set"` was correctly removed from the negatives list.
  - I probed the neighbouring headers. `Third Set:`, `THIRD SET -` and `Set Three` are already recognised as set-3 headers. `3rd Set` splits like `Third Set` and is now caught.
- **F2: ADDRESSED.** All three mutants are now killed (details under Mutants below).
- **F3: ADDRESSED.** Each ruling is now attributed to its source.
  - The veto stays with llama-db: `taper.py:69-70`, `:295`, `:775`, and spec `:314`.
  - The con't carve-out is attributed to "orchestrator ruling R9, 2026-10-22, pending llama-db confirmation": `taper.py:77-78`, `:300-301`, and spec `:317-319`.
  - The bare-`Set` rule is attributed to R10: `taper.py:74-76` and spec `:315-317`.
  - All three match ledger R9 and R10 (`orch-r1/ledger.md:12,16`).
- **F4: ADDRESSED.** The docstrings now say the encore's items, its songs and any notes after them, are skipped: `taper.py:70-71`, `_set_like` docstring `:552-553`, and spec `:312` ("skipping the encore's items"). No "notes after the encore songs" wording remains.

## Gate4 to gate5 delta, recomputed from the jsonl files
- **Gate (339 rows, same slugs):** 0 changed rows, 81 owned in both. `gate_summary.txt` is byte-identical: 77/186 = 0.414, exact 42/54.
- **Library (3983 rows, same slugs):** exactly 1 row changed, darkstarorchestra-2012-05-19. It went from owned to `not-asserted(veto: set-like text)`. Owned is 642 then 641, and "labels identical" is 552 then 551.
  - In gate4 its labels were identical to stored, so the lost ownership loses no correction.
  - Nothing else differs in any field.
  - The claim holds.
- **The other two bare-`Set` texts the original reviewer named:**
  - jackiegreene-2010-07-07 is `veto: track title` in both gates. The earlier veto wins, so there is no flip.
  - jkb2023-04-16 is not in the library.
- **Gate5 provenance:** the files are timestamped 12:03:24-30, one second after the 6cf03ea commit time (12:03:23). So the run was on the tree that was committed, or one matching it. I did not re-run the gate.

## M2 specifically
- **`.match` behaviour is unchanged.**
  - Without `re.M`, `^` matches only at position 0, and `.match` already anchors there, so the `^` was redundant under `.match`.
  - A 300k-string fuzz test confirms the old and new regexes give identical match/no-match and spans under `.match`.
  - Mutant M2c (put `^` back, keep `.match`) passes all 317 taper tests.
  - The gate delta shows no change other than the DSO row, which is caused by F1.
- **The new test genuinely kills `.search`.**
  - M2 (`.match` to `.search` on HEAD) fails exactly `test_continuation_must_follow_the_token_directly`.
  - M2b (old `^` plus `.search`) survives with 317 passed. This confirms the fixer's point that M2 was an equivalent mutant before the `^` was dropped.

## Mutants
- **Setup.**
  - Scratch copy: `git archive 6cf03ea`.
  - Run with `PYTHONPATH=<copy>/packages/llama/src` and a fresh `PYTHONPYCACHEPREFIX` per mutant, using `python -m pytest` from the copy's cwd.
  - Import printed as the copy's `taper.py`.
  - A planted sentinel (`raise` in `_set_like`) gave 292 failed, which proves the copy is the code under test.
- **Results.** Each prediction was written before the run, and every one held:

| mutant | predicted | result |
|---|---|---|
| unmutated | 317 pass | 317 pass |
| M1: inner `continue` changed to `break` (first match only) | `test_set_like_checks_every_token_in_an_item` | that 1 test fails |
| M2: `.match` changed to `.search` | `test_continuation_must_follow_the_token_directly` | that 1 test fails |
| M2b: `^` restored, plus `.search` | survives (equivalent) | 317 pass |
| M2c: `^` restored, `.match` kept | survives | 317 pass |
| M6: set "3" items skipped | `test_set_like_token_in_a_set_three_item` | that 1 test fails |
| F1: bare-`Set` rule removed | split test, 4 bare forms, DSO case | exactly those 6 fail |

The copy was restored and checked with `cmp` against `git show 6cf03ea:…/taper.py`.

## Other checks
- `git diff main -- packages/llama/src/llama/setlist.py`: empty (0 lines).
- Full suite on HEAD in the worktree, run as `./.venv/bin/python -m pytest -q`: **4373 passed, 1 skipped, 8 deselected**. llama is imported from the worktree.
- No new Critical or Important breakage in the fix diff.

## Deferred minors (out of scope, not blocking)
- An item before the first recognised header is labelled `"1"` (`taper.py:576`, `lab or "1"`). So the bare-`Set` rule, like the token rule, also fires above set 1's header. DSO is exactly this case, and it is accepted under R10. This behaviour predates the fix.
- F6 (`_CONT_AFTER` exempts any `cont…` word) is unchanged, as deferred.

Evidence:
- Scratch directory: `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-taper-markers/0443a042-e8ee-4093-a603-2fbd14e62179/scratchpad/cpa3-rr1/`. It holds `mut.py`, `run.sh` and `copy/`.
- Output log: `$D/cpa3-rr1/cpa3-rr1.log`.
