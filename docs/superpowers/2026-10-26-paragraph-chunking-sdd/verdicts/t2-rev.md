### Spec Compliance

- ✅ Spec compliant. `plan_chunks` (audio.py:117-151 in the diff) implements spec section 2 steps 1-5 and the brief's algorithm in order: paragraph split `re.split(r"\n\s*\n", text)` + `" ".join(p.split())` + empty parts dropped (step 1); paragraph <= C is one unit, longer goes through `_greedy(_split_sentences(para), ceiling)` (step 2); `_greedy(units, ceiling)` (step 3); the <20-char merge loop, backward else forward, single chunk left alone (step 4); whitespace-only returns `[""]` as the brief specifies.
- ✅ Review Focus 1 (CRLF): `test_plan_chunks_crlf_breaks_and_no_carriage_returns` asserts exact `[P1, P2]` equality, which excludes any `\r`. Probe I ran: `P1 + "\r\n \t\r\n\r\n" + P2` -> `[P1, P2]`; `P1 + " " + P2` -> no separator survives (`str.split()` covers U+2028/U+0085 too).
- ✅ Review Focus 2: `test_plan_chunks_blank_trailing_paragraphs_make_no_empty_chunk` (`f"{P1}\n\n   \n\n"` -> `[P1]`); the `if not para: continue` at audio.py:131-132 is what drops them.
- ✅ Review Focus 3: `test_plan_chunks_whole_short_segment_is_one_chunk`; the loop guard `len(chunks) > 1` (audio.py:140) leaves a lone short chunk untouched.
- ✅ Brief test literals verified: len(P1)=75, len(P2)=73 (probe); handback says no literal was changed, and the diff's tests match the brief verbatim.
- ✅ Mutation evidence (binding rubric item): t2-impl.log lines 11-20 record PREDICT lines before each run; A -> predicted test + `tiny_first` (the log's prediction already anticipated it), B and C -> exactly the predicted test. Each observed result follows from the stated edit. The live-worktree mutations were sanctioned by implementer-common.md:15 for this task; `git status --porcelain` is clean now.
- ✅ Commit message states its test command (`./.venv/bin/python -m pytest packages/emcee -q`, 966 passed).
- ⚠️ Cannot verify from diff: whitespace-only input returns `[""]` (brief-mandated, mirrors `_split_sentences`). Whether the Task 4/5 caller avoids an empty provider call for it (Review Focus 2's "no empty provider call") lives in `_chunked_pcm`/`render_speech_mp3`, not this diff; check it in that task's review.

### Strengths

- Small, pure, and readable: one private `_greedy` reused for both packing levels instead of two hand-rolled loops (audio.py:105-113).
- The step-4 loop is correct on the cases that are easy to get wrong: backward merge does not advance `i` (so a following tiny chunk is also checked), forward merge re-checks the new head (so two leading tiny chunks cascade), and termination is guaranteed because every `continue` shrinks the list. Probes: `"Hi.\n\nOk."` -> `["Hi. Ok."]`; `"Hi.\n\nOk.\n\n"+P1` @80 -> one chunk; `P1+"\n\nHi."` @80 -> `[P1+" Hi."]`.
- The docstring states the why (tiny clips make the backend hallucinate; newline-free because mlx splits on `\n`), not just the what.
- Tests pin exact outputs for the ordering-sensitive rules (steps 3 and 4) and each of the three Review Focus items.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)

1. test_audio.py `test_plan_chunks_no_paragraphs_packs_plain_sentences` (plan-mandated literal): compares `plan_chunks` against itself on two inputs, so it pins only "single newline == space", never the packed result; a regression that changed both sides identically passes. Consider also asserting the concrete expectation (e.g. every chunk <= 250 and `" ".join(chunks) == LONG`). Coverage polish, not a gap: `..._long_paragraph_packs_sentences_never_splits_one` already pins the packing.
2. audio.py:136 step 2's inner `_greedy` is behaviourally redundant: greedy over a paragraph's maximal sentence packs followed by step 3's greedy gives the same result as feeding the sentences straight into step 3 (each pack plus the next one's first sentence already exceeded C). It is spec-mandated and harmless; noted only so nobody spends a mutation on it expecting a red test (it is an equivalent mutant).
3. A lone CR (classic-Mac `"\r\r"`) is not treated as a paragraph break (probe: `"a\r\rb ..."` -> one chunk, collapsed to a space). No `\r` reaches the provider, and the spec only defines newline breaks, so this is out of scope; recorded for completeness.
4. Handback line "baseline 943 + 8 Task1 tests? + 15 new" carries a stray question mark; the arithmetic (966) and the log (t2-impl.log:10) agree, so the evidence stands.

Checks run: read-only probe of `plan_chunks` with the worktree's interpreter (`emcee.__file__` resolved inside the worktree) on CRLF-with-whitespace, U+2028, lone-CR, leading/trailing tiny chunks, and an over-ceiling single sentence (`[300]`, sent whole). No suite or test re-run.

### Assessment

**Task quality:** Approved

**Reasoning:** The packer matches spec section 2 step for step, all three Review Focus edge cases are tested with exact expected values, and the mutation evidence has stated predictions that each observed failure follows from; only coverage polish remains.
