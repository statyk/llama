**Task quality (Tasks 1+2, 9f3aadec..c110c025): Needs fixes.** Two missing tests, no code change needed. Line refs are to c110c025: `packages/emcee/src/emcee/audio.py` (A) and `packages/emcee/tests/test_audio.py` (T).

### Strengths
- A:75-87: the dotted-abbreviation pre-pass is small and runs before the merge loop, so the loop's abbreviation, initial, decimal and short-fragment rules see the same boundaries as before. The loop body (A:89-102) is untouched. `carry` handles chaining and a trailing token in one pass, with no index juggling.
- A:105-113: `_greedy` is one 8-line helper reused for both packing passes (A:136, A:139) instead of two copies.
- A:140-150, step 4 terminates: each iteration either increments `i` or shrinks `chunks`. The `len(chunks) > 1` guard covers a lone tiny chunk (T:216). The comment at A:146 is correct: `chunks[i-1]` is always at least `_MIN_FRAGMENT_LEN`, because front merges re-check index 0 through `continue` (probe: `plan_chunks("Hi.\n\nYo.\n\nOk.", 5)` gives `['Hi. Yo. Ok.']`).
- A:129: splitting on `\n\s*\n` and collapsing with `" ".join(p.split())` handles CRLF, `\n \n\n`, wraps and stray `\r` in one expression. Review Focus 1-3 each have a direct test (T:181, T:186, T:216).
- Tests assert exact outputs on real behaviour, with no mocks. The verbatim 1974-05-19 outro fixture (T:110-125) is reused across both tasks.
- Both handbacks state a prediction for every mutation, and each observed result follows from its edit.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **A:85-86: the trailing-carry append is unpinned, and removing it silently drops spoken text.** Scratch mutant M1 deleted `if carry: joined.append(carry)`. Prediction: nothing fails. Observed: test_audio.py + test_scriptwrite.py, 125 passed. These are the only test files that exercise the splitter. With the mutant, `"The first sentence is long enough here. We played in Washington D.C."` loses its last sentence. That is a closing line missing on air. The `sentences or [text.strip()]` fallback hides the mutant only for single-part text. The implementer noted the behaviour ("a trailing part ending in a dotted abbreviation ... is kept as-is") but did not test it. The global constraints say "A mutation that fails nothing means the test is missing: add one." Fix: add `assert _split_sentences(t) == ["The first sentence is long enough here.", "We played in Washington D.C."]`.
2. **A:136: step 2's inner `_greedy` is unpinned, and it is what keeps a paragraph break a chunk boundary.** Scratch mutant M3 replaced it with `units.extend(_split_sentences(para))`. Prediction: nothing fails. Observed: `-k plan_chunks`, 15 passed. The output changes, though. For `"Short opening paragraph here.\n\n" + six ~50-char sentences` at ceiling 120:
   - the original gives `['Short opening paragraph here.', 'Sentence 0 … Sentence 1 …', …]`;
   - the mutant gives `['Short opening paragraph here. Sentence 0 …', …]`: the author's paragraph break disappears inside a chunk.

   Preferring the author's paragraph breaks is the point of this feature. The brief also claims "the order matters and the tests pin it", which is not true for this step. Fix: add that case (a short paragraph followed by a paragraph over the ceiling, where the long paragraph's first sentence would fit after the short one) and assert the exact list.

#### Minor (Nice to Have)
3. **A:79-84: chaining (`U.S. B.B.`) is required by the brief but untested.** Scratch mutant M2 stopped the carry after one join (`was_carried` guard). Prediction: nothing fails. Observed: 125 passed. The behaviour is correct today (probe: `"Tonight the band played U.S. B.B. King songs for the whole crowd."` stays one piece). Add it as a parametrize case.
4. **T:202, `test_plan_chunks_no_paragraphs_packs_plain_sentences`, is close to tautological.** It compares `plan_chunks(LONG)` with the same text with `". "` turned into `".\n"`. That proves only that a single newline equals a space, which T:165 already covers. It asserts nothing about packing, despite its name. Either assert the expected list or rename it.
5. **A:140-150: no test for two or more consecutive tiny chunks in the middle**, the repeated merge into the previous chunk with no `i` increment. It is correct by reading. A test would pin it.
6. **A:138: whitespace-only text returns `[""]`.** That matches `_split_sentences` and the brief. Review Focus 2 forbids an empty provider call, so the Task 4/5 caller must skip an empty chunk. This is a carry-forward check, not a defect here.
7. **A:81: the regex is rebuilt per part.** `re.sub` with a string pattern goes through re's cache, so the cost is negligible. Precompiling it beside `_DOTTED_ABBREV_RE` (A:56) would match the module's style. Cosmetic.
8. **t2-impl handback: the mutation run command is not stated.** The global constraints prescribe `PYTHONDONTWRITEBYTECODE=1 ... -p no:cacheprovider`, and a stale `.pyc` is a known false-CAUGHT source in this repo. The observed results are plausible: A failed 2 tests, B and C failed exactly the predicted test. Its test count line also reads "8 Task1 tests?", but 943+8+15=966 adds up.

### Checks run (all in a scratch `git archive c110c025` copy; `emcee.__file__` resolved inside it; worktree untouched)
- Probes: trailing `D.C.`; chain `U.S. B.B.`; quoted `"U.S."` is not split, because the split regex needs `[.!?]` right before the whitespace; `p.m.` joins, as harmless as `D.C.`; front merge of all-tiny chunks; old-Mac `\r\r` collapses to a space, not a break.
- Mutants M1, M2 and M3 as described above. The file was restored with `cmp` after each.
- Not run: the package-wide suite (rubric).

### Assessment
**Task quality:** Needs fixes

**Reasoning:** Both functions are correct, small and readable, and Review Focus 1-3 each have a direct test. But two behaviours have no test: the trailing-token append, whose loss silently drops spoken text, and the paragraph-first packing order, which is the feature's purpose. In each case a mutant passes the whole relevant test set, so each needs one added test.
