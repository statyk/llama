# c1n handback
Status: DONE. Commit 3751735 `fix(lossless_titles): C-1 fires only on C-confirmed signature positions (operator ruling)`.

## Implemented
- lossless_titles.py apply_lossless: demotion condition is now `sum(1 for i in delivered_shift if i in changed) >= 2`; block comment states the rule and the symmetry rationale.
- stages/gather.py: `c_demoted = set(lossless.demoted)`; the 2c/2d note loop skips `i in c_changed or i in c_demoted` (fixwave-rr Minor 2).
- Tests: test_title_cascade.py `test_shifted_reference_with_right_tags_demotes_nothing_c1_narrowing` (demo_gather synthetic show; pins that the 8 right MP3 tags ship as tagged, no setlist-gap, no demotion/note) and `test_c1_demotion_note_loop_skips_demoted_glued_prefix_notes`; test_lossless_titles.py `test_c1_one_confirmed_signature_position_demotes_nothing` / `test_c1_two_confirmed_signature_positions_demote`.
- DSO-2014-07-31 pins (unit + gather, existing) pass unchanged; they already pin 17 C2 + 1 C1 changed positions, i.e. >=2 confirmed, so no assertion added.

## TDD
RED on b653592 code (tests only): `./.venv/bin/python -m pytest -q -p no:cacheprovider packages/llama/tests/test_lossless_titles.py packages/llama/tests/test_title_cascade.py` -> 3 failed, 77 passed (one-confirmed unit; demo gather; note-loop, failing at the note assertion). GREEN after: 80 passed.
Mutants (scratch copy in session scratchpad, llama.__file__ proven under scratch): `>= 1` -> 2 failed (test_one_shifted_delivered_tag_changes_nothing, new one-confirmed); `>= 3` -> 4 failed (the three existing exactly-2 tests + new two-confirmed). Both killed.

## Signature-show check (read-only replay, outputs in ~/.llama-harness/piece3/c1n/, flags as r2: asis = plain, fresh = --strip-title-overrides --strip-structure-overrides)
Whole row compared against r2 cand-asis.json / cand-fresh.json: zero differing keys for all 8.
- asis: darkstarorchestra-2014-07-31 clean; lettuce-2002-07-13 clean; tedeschitrucksband-2019-02-15 clean-changed; tedeschitrucksband-2020-01-15 clean-changed; all c_demoted [] , unchanged.
- fresh: darkstarorchestra-2014-07-31 newly-held (unresolved track titles), c_demoted [3], unchanged; lettuce, tedeschi 2019, tedeschi 2020 clean-changed, c_demoted [], unchanged.

## Full suite
`./.venv/bin/python -m pytest -q -p no:cacheprovider` -> 4787 passed, 1 skipped, 8 deselected, 26 warnings in 71.00s.

## Judgement calls / concerns
None. Trade-off as fixwave-rr stated: an uncorroborated shifted delivered set (fewer than 2 C-confirmed signature positions) now ships as tagged, as before the fix wave. CLAUDE.md/spec/acceptance.md untouched.
