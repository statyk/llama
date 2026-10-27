Spec compliance: not judged here (separate reviewer). Task 7 code-quality review of 2cb14e34..675d16e5.

### Strengths
- `_unescape_breaks` (scriptwrite.py:199-202) is a single-purpose pure helper with a docstring that states why it exists; both call sites reuse it, no duplication.
- In `write_script` the unescape sits inside the retry loop, before `script_guard` (scriptwrite.py:257-261), so a retried reply is unescaped too, and the returned `notes` is the unescaped copy; the raise path is unchanged.
- `rephrase_segment` unescapes before `.strip()` (scriptwrite.py:284), so a trailing escaped break is trimmed rather than surviving as real newlines.
- Tests exercise real behaviour through `FakeProvider` and the real `write_script`/`rephrase_segment` (test_scriptwrite.py:615-645): the double-escape test asserts exact equality on `set_intros["1"]` and absence of a literal backslash-n on both `outro` and an intro; the round-trip test also asserts the wire form really is a JSON escape (`"\\n\\n" in reply`), so it cannot silently degrade into a raw-newline test.
- Mutation evidence meets the rubric: A (drop in write_script), A2 (drop in rephrase_segment), B (move after guard) each have a prediction stated before running, and the observed results follow from the edits.
- Prompt edits are guidance, placed where the brief says (scriptwrite.md:40-43, rephrase.md:19), not a new hard rule.

### Checks run (named risk -> what I checked)
- Unescape-before-guard ordering matters? -> read `script_guard` (scriptwrite.py:130-176): it checks `mentioned_songs`, set keys, and set-count/ordinal regexes over `" ".join(...)` prose; nothing inspects backslashes or newlines, so mutation B's "no failure" is correct and before-guard is merely the safer placement.
- Unescaped field coverage -> `context` is not unescaped; grep shows it is only rendered in dj-notes.md (scriptwrite.py:186-187) and joined into guard prose (:154), never spoken, so leaving it alone does not leak `\n` to TTS.
- Raw newlines would break parsing -> herder parses with `schema.model_validate_json(extract_json(raw))` (herder/tasks.py:96), strict JSON, confirming the prompt's "never a raw line break" wording guards a real retry cost.
- `model_copy(update=...)` skips validation -> values stay `str`/`dict[str, str]`, so no type drift.
- rephrase call site (process.py:234) consumes the returned text; `_fold` collapses whitespace (test_scriptwrite.py:597-598 pins `\n` -> space), so `rephrase_problems` comparison is unaffected by real breaks.
- No tests or mutants run by me; the implementer's run (1017 passed) and mutation log answer every doubt I had.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. test_scriptwrite.py:607 — `assert "never a raw line break" in prompt` depends on the prompt's line wrapping (scriptwrite.md:42-43 wraps right before "never" specifically so the phrase stays on one line; the handback calls this out as a caveat). A future re-wrap of that paragraph breaks the test for no behavioural reason. Fix: compare against a whitespace-normalised copy, e.g. `" ".join(prompt.split())`.
2. scriptwrite.py:284 — unescape-before-strip is not pinned: swapping to `_unescape_breaks(result.text.strip())` leaves trailing real newlines and no test fails (test_scriptwrite.py:642-645 has no trailing escape). Low impact because the packer drops trailing blank paragraphs (Task 2), so a test is optional.
3. scriptwrite.py:199-202 — only `\n` is unescaped; a model that double-escapes `\r\n` or `\t` would still leave literal `\r`/`\t` in spoken text. Speculative (no observed instance) and the spec scopes the fix to `\n`; mention only.

### Assessment

**Task quality:** Approved

**Reasoning:** A small, pure helper applied at the two points where model text enters the pipeline, in the right order relative to the guard and `.strip()`, with behaviour-level tests and properly predicted mutations; the remaining items are test-brittleness and coverage polish.
