VERDICT: APPROVED

fw4-rev (Opus) — review of 4cd1ebc..b7147e0 (one commit, b7147e0). Read-only; no worktree changes, no commits.
Snapshot: git archive b7147e0 -> /var/folders/yn/jlwxryrj1ds7jpvw931jk1jm0000gn/T//fw4-rev-snap-NH8tSD (shadowing proven: llama.__file__ resolved inside the snapshot). Removed at the end.

## Spec compliance (fw4-brief.md)
| Item | Status | Where |
|---|---|---|
| `_SET_COUNT_CLAIM` lookahead `(?!\s+of\b)` -> `(?![^\S\n]+of\b)`, nothing else changed | OK | brief.py:34 |
| `_SET_COUNT_CLAIM_3C` same replacement, nothing else changed (leading `\s+`, `(\w+)` untouched) | OK | brief.py:48 |
| Comment above `_SET_COUNT_CLAIM` says the lookahead stops at the field boundary, like `_SCOPE_AFTER` (I1 follow-up) | OK (two added lines rather than one; harmless) | brief.py:29-32 |
| "stays as it is" sentence above `_SET_COUNT_CLAIM_3C` updated | OK | brief.py:45-46 |
| Test 1: full `_claim_counts("...two sets\nOf note...") == ({2}, {})`; same-field "sets of" no claim | OK (same-field case was already pinned in test_3c_set_count_claims; re-asserted) | test_stage_brief.py:379-382 |
| Test 2: vague, cross-field -> "asserts set structure under vague narration"; same-field -> [] | OK | test_stage_brief.py:385-391 |
| Test 3: end-to-end full narration, 3-set show -> "briefing claims 2 sets but structure has 3" | OK | test_stage_brief.py:394-398 |
| One commit, exact subject, test command/result + operator ruling in body | OK | b7147e0 |
| Nothing extra changed | OK (diff = 2 files, 29+/5-) |

Do-not-retune grep over the diff (all Global Constraints names + RIGHT_SHOW*): no +/- line touches any. Direction: strictly tighter (only adds claims where a newline precedes `of`); correct for the strict surface.

## Findings
Critical: none. Important: none.

Minor
- m1. brief.py `_guard_prose` docstring (lines ~180-183) still says the newline join leaves "their matches and spans, and with them the vague branch, ... unchanged" vs the old single-space join. That is no longer true by design: "two sets" + "Of note" now matches under the newline join and did not under the space join. Likewise the comment in test_guard_prose_field_marker_leaves_todays_matches_unchanged (test_stage_brief.py:402-403) — the test still passes only because its fixture's "sets of" is within one field. Fix: append to the docstring "except the `of` lookahead, which stops at the newline (fw4), so a field ending in a count claim is no longer excused by the next field opening "Of ..."". Optional, doc-only.
- m2. briefing_guard's vague-branch comment "Unchanged by slice 3: today's regexes" (brief.py ~205-206) is literally still true but now hides that fw4 changed the vague regex under operator ruling; optional "(fw4 changed only its `of` lookahead)".
- m3 (informational, no fix asked). Other `\s+` that can still span the field newline: `_SCOPE_AFTER`'s inner `\s+` ("two sets a\nNight ...") and the count-to-intervening-word `\s+` ("...two\nElectric sets"). Both need a field to end on a bare "a"/count word; negligible, and the brief explicitly kept the leading `\s+`.

Commit trailer says Claude Sonnet 5.5 — consistent with common.md (implementer uses its own model name).

## Mutation spot-check (recipe: fresh copy per mutant under MROOT=/var/folders/yn/jlwxryrj1ds7jpvw931jk1jm0000gn/T//mut-fw4-rev-WpiFYa, PYTHONPATH shadowing proven per mutant, private PYTHONPYCACHEPREFIX, predictions logged before flips; ran test_stage_brief.py + scripts)
| mutant | predicted test | caught by |
|---|---|---|
| M1 3C lookahead -> `(?!\s+of\b)` | ..._field_boundary_full + ..._end_to_end_full_narration | both (2 failed, 168 passed) |
| M2 vague lookahead -> `(?!\s+of\b)` | ..._field_boundary_vague | ..._field_boundary_vague (1 failed) |
| M3 drop 3C lookahead | test_3c_set_count_claims[two sets of fiddle tunes-...] + ..._field_boundary_full | both (2 failed) |
| M4 (unlisted) drop vague lookahead | ..._field_boundary_vague (b2 assert) | ..._field_boundary_vague (1 failed) |
All four match predictions; implementer's M1-M3 claims confirmed. M4 was the one mutant the brief should have listed; it is caught.

## Suite (snapshot)
3765 passed, 1 skipped, 8 deselected, 26 warnings in 83.60s
