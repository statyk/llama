# t12-fix1: DONE. Tests only, no production change.
Commit 8fa473df test(emcee): pin abbreviation carry, paragraph-first packing, chains, tiny runs
Added to packages/emcee/tests/test_audio.py: I1 test_split_trailing_dotted_abbreviation_keeps_its_sentence; I2 test_plan_chunks_short_paragraph_stays_apart_from_a_packed_long_one (exact list); M3 parametrize case "U.S. B.B."; M5 test_plan_chunks_consecutive_tiny_paragraphs_all_join_the_chunk_before (ceiling 15, exact list).
Suite: ./.venv/bin/python -m pytest packages/emcee -q -> 982 passed, 1 deselected.
Mutations (command each: PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -m pytest -p no:cacheprovider packages/emcee -q; predictions logged first; restored by git checkout, status clean):
- I1 deleted `if carry: joined.append(carry)` -> predicted/observed: only the I1 test failed.
- I2 `units.extend(_greedy(_split_sentences(para), ceiling))` -> `units.extend(_split_sentences(para))` -> only the I2 test failed.
- M3 `carry = part if (not carry and fullmatch) else ""` (no carry after a join) -> only the [U.S. B.B.] case failed.
- M5 `continue` after backward merge preceded by `i += 1` -> only the M5 test failed.
No process of mine is left running (the one pgrep hit was the pgrep-carrying shell itself).
