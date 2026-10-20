# Pre-apply fix: `_SCOPE_AFTER` must not cross the briefing-field boundary (final review I1)

File: packages/llama/src/llama/stages/brief.py (and its test file packages/llama/tests/test_stage_brief.py).

`_SCOPE_AFTER = r"^\s*(?:each|every|a|per)\s+(?:night|day|weekend|tour)\b"` — `\s*` matches the `\n` that `_guard_prose` uses to join briefing fields, so a set-count/ordinal claim that ENDS one field is suppressed as "scoped" when the NEXT field happens to start "A night…", "Each night…", "A tour…" etc. Probe from the final review: `_claim_counts("The band played two sets\nA night to remember")` → no claim; with a period instead of the newline → `{2}`. This is the exact mirror of the Task 14 fix-round-1 negation-window fix (read `git log -S` / the negation window code in brief.py for how that was done and match it).

Fix: make the leading whitespace not cross a newline: `^[^\S\n]*` in place of `^\s*` (keep everything else in the pattern byte-identical). If the scope-before window (if any) has the same defect, fix it the same way and say so; touch nothing else.

Test: add one test in test_stage_brief.py next to the existing 3c scope tests: a claim at the end of one field followed by a newline and a field starting "A night to remember" IS counted (the claim is found), while the same claim followed by " a night" on the same line is still scoped (suppressed). Mutation: in a scratch copy (common.md recipe), revert the regex to `^\s*` — predicted catcher: the new test.

No do-not-retune constant is touched (this regex is a Tier 1 3c addition, not a protected one). Full suite green; one commit `fix(brief): 3c scope window stops at the field boundary (final review I1)`.
