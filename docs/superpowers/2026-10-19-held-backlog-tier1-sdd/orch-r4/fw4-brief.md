# fw4 — set-count guard: the `(?!\s+of\b)` lookahead crosses the briefing-field boundary

File: `packages/llama/src/llama/stages/brief.py`. Tests: `packages/llama/tests/test_brief.py` (or wherever the existing `_claim_counts` / `briefing_guard` set-count tests live — find them with grep and add beside them).

## The defect
`_guard_prose` joins briefing fields with `\n`; that newline is the field boundary (see its docstring and the comments above `_SCOPE_AFTER` / `_CLAUSE_BREAK`). Final-review I1 fixed `_SCOPE_AFTER` (`^\s*` → `^[^\S\n]*`) at commit 4cd1ebc. The same hole remains in the negative lookahead `(?!\s+of\b)` of BOTH count regexes:

- `_SET_COUNT_CLAIM` (the vague-narration branch's regex), and
- `_SET_COUNT_CLAIM_3C` (the full-narration 3c regex).

`\s+` matches the `\n`, so a count claim that ENDS one field is suppressed when the NEXT field starts with `Of …` ("The band played two sets\nOf note, the encore…" → no claim). Direction: fewer holds (a loosening on the strict surface). The operator has approved fixing BOTH copies (this changes the vague branch, which slice 3 had promised to leave alone; the operator ruled on it — record that in the commit message).

## Required change (verbatim)
In both regexes replace `(?!\s+of\b)` with `(?![^\S\n]+of\b)`. Nothing else in either pattern changes: the leading `\s+` between the count word and `sets` stays as it is (it crossing a newline can only ADD claims — the strict direction — and `_guard_prose`'s docstring relies on spans being unchanged). Update the comment above `_SET_COUNT_CLAIM` (and the "stays as it is" sentence above `_SET_COUNT_CLAIM_3C`) in one line each to say the lookahead stops at the field boundary, like `_SCOPE_AFTER` (final review I1 follow-up).

## Tests (add; do not weaken existing ones)
1. Full narration, `_claim_counts("The band played two sets\nOf note, the encore was long")` → claimed counts `{2}`. And the same-field form `"two sets of fiddle tunes"` still → no claim (existing behaviour pinned; add it if no test pins it).
2. Vague narration: a `briefing_guard` call on a vague briefing whose prose has `"…two sets\nOf note…"` across two fields yields "briefing asserts set structure under vague narration"; with `"two sets of fiddle tunes"` in one field it does not (if an existing test already pins the `of` case for vague, reuse it).
3. A `briefing_guard` end-to-end row (full narration, a 3-set show, a field ending "…two sets" followed by a field starting "Of note…") → contains `briefing claims 2 sets but structure has 3`.

## Mutants (mutation recipe in the plan's Global Constraints; write the predicted test BEFORE each flip)
- M1: revert `_SET_COUNT_CLAIM_3C`'s lookahead to `(?!\s+of\b)` → predicted: test 1 (and test 3).
- M2: revert `_SET_COUNT_CLAIM`'s lookahead to `(?!\s+of\b)` → predicted: test 2.
- M3: drop the lookahead from `_SET_COUNT_CLAIM_3C` entirely → predicted: the same-field `sets of` test.

## Done when
Full suite green (`./.venv/bin/python -m pytest -q`), one commit `fix(brief): set-count 'of' lookahead stops at the field boundary` with the test command/result and the operator ruling in the body, mutation table in the handback.
