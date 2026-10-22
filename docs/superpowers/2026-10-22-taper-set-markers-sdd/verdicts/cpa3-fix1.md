# cpa3-fix1 handback: fix round 1 on the set-like veto

**Status: DONE.**

## Commit
- `6cf03ea` fix(taper): a bare `Set` item is set-like; every token checked (fix round 1, cpa3). Parent 5da667b. Trailer per the mandates.
- Suite: `./.venv/bin/python -m pytest -q` gives **4373 passed, 1 skipped**, 8 deselected. The taper tests give 317 passed.
- `git diff main -- packages/llama/src/llama/setlist.py` is empty.

## Findings
- **F1, fixed as ruled.** In `_set_like`, an item of a numbered set that is exactly `Set` after `.strip(_ITEM_DECOR)`, case-insensitive, is now set-like. I did not use prev+item. The bare-`Set` rule is what R10 states, and it also catches `1st Set` and `First Set` splits. prev+item would miss DSO's top-of-set `First`/`Set` only by accident, and it would invent cross-item matches.
  - Tests:
    - `test_split_ordinal_header_is_set_like` uses the reviewer's constructed `Third Set` case. It is not owned and gives `veto: set-like text`.
    - `test_bare_set_item_is_set_like` covers `Set`, `- Set -`, `[Set]` and `*set*`.
    - `test_bare_set_item_real_case_is_not_owned` covers darkstarorchestra-2012-05-19, with the verbatim description from md_DSO2012-05-19.json.
  - `"Set"` is removed from the negatives list.
- **F2, mutants.**
  - The code already checked every match: the `for` loop skips an exempt token with `continue` and vetoes on the next one. M1 only survived because no test covered it, so I added a test.
  - M2 was an equivalent mutant. `_CONT_AFTER` began with `^`, so `.match` and `.search` were the same. I dropped the redundant `^`, which means no behaviour change under `.match`, and added a test, which now kills M2.
  - New tests:
    - `test_set_like_checks_every_token_in_an_item` (`Set 2 con't from set one` in set 2);
    - `test_continuation_must_follow_the_token_directly` (`Set 2 starts here (cont. after Drums)`);
    - `test_set_like_token_in_a_set_three_item` (`end of set two` in set 3, decide_taper declines).
- **F3, doc.** The spec §2 sentence and the module docstring now attribute the veto to llama-db (Checkpoint A2) and the bare-`Set` rule to orchestrator ruling R10. The con't carve-out is attributed to "orchestrator ruling R9, 2026-10-22, pending llama-db confirmation", in the docstring, the `_CONT_AFTER` comment and the spec.
- **F4, doc.** The docstring and the `_set_like` docstring now say that the encore's items, which are its songs and any notes after them, are skipped.
- **F6** is left as it is, as instructed.

## Mutants (scratch `git archive` copy of 5da667b plus the new test file and taper.py, import shown to resolve to the copy)

| mutant | result |
|---|---|
| unmutated | 317 pass |
| M1 (`continue` to `break`, first match only) | KILLED: `test_set_like_checks_every_token_in_an_item` |
| M2 (`_CONT_AFTER.match` to `.search`) | equivalent with the old `^`, survived (317 pass); after dropping `^`, KILLED: `test_continuation_must_follow_the_token_directly` |
| M6 (skip set-3 items) | KILLED: `test_set_like_token_in_a_set_three_item` |
| F1 (bare-`Set` rule removed) | KILLED by 6 tests: the split case, 4 bare forms, the DSO real case |

## Gate5 (`taper_probe.py gate --out ~/.llama-harness/piece2/gate5`, then `delta --old gate4 --new gate5 --out gate5`)
- **Gate, unchanged:**
  - in-scope 186, owned 77, ratio 77/186 = 0.414;
  - target match exact 42/54 = 0.778, incl. filler-only 53/54 = 0.981, misses 1;
  - renum 8, no target 15.
- **Library:** taper-owned **641** (was 642). Labels identical to stored: 551. Labels differ: 90. Tiers are unchanged: songs moved 33, encore added 31, sets merged 4, sets split 21, filler only 1, labels renamed 0, encore folded 0.

### Flip list, gate4 to gate5
- **Gate:** no flips. My own row diff over status, reason, labels and match found 0 changes.
- **Library:** **darkstarorchestra-2012-05-19 is newly not owned, `veto: set-like text`, and it is the only change.** No row is newly owned, no owned row's labels changed, and there are no reason-only changes. The reviewer also listed jg2010-07-07 and jkb2023-04-16 as having bare `Set` items; neither shows up as a changed row.

## Correction to my previous handback (reviewer F5)
- The gate3 to gate4 reason-only changes number **9**, not 10: 3 gate rows and 6 library rows. I wrote "library (7)" and listed 6.
- umphreysmcgee-2002-12-31 has no `_SET_LIKE` token in its encore items, so only 6 of the "7 post-encore-notes rows" actually exercise the encore skip. All 7 stay owned.
