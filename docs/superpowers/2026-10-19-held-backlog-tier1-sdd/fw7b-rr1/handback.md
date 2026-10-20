VERDICT: APPROVED

fw7b-rr1: re-review of 82fc3a3 (cd9a0b6..82fc3a3), read-only, against fw7b-fix-r1.md and fw7b-rev Minors 1-7. Snapshot via git archive; shadowing proven (llama.__file__ under the snapshot); snapshot and MROOT removed afterwards.

## Per-finding status
| # | item | status | where |
|---|---|---|---|
| 1 | stored `"llm"` alignment moved to the gather clause | ADDRESSED | CLAUDE.md:112-113; true per replay.py:328-329 (show.json `structure.alignment`) |
| 2 | README "its only LLM work: one brief task of up to two attempts" | ADDRESSED, verbatim | README.md:257-258 |
| 3 | `_two_arms` keyword args | ADDRESSED | scripts/test_replay_holds.py:439 `mutate_cand=unknown, mutate_base=unknown` (signature :297) |
| 4 | re-wrap fix-wave lines (CLAUDE 115/134/135/142/154/513/530/535, README 257) | ADDRESSED | no added line exceeds 80 cols; no line >80 left in CLAUDE.md 100-170 or 505-560 |
| 5 | dry-run sentence corrected | ADDRESSED | CLAUDE.md:127-131; matches cli.py:3354-3359 (`would: <slug> -> skipped: structure changed`, no brief/download count) and reapply.py:106-109 (names form `-> dry-run: skipped: structure changed`); summary line is list form only |
| 6 | names-form dry-run skip test | ADDRESSED | test_reapply.py:960, asserts both the skip line and the `--allow-structure-change` line |
| 7 | duplicate `briefing_guard` import | ADDRESSED | test_stage_brief.py:11 (line 3 keeps it) |
Nothing else changed.

## Wording check
Whitespace-normalized word-stream diff (old vs new, both files): the only word changes are the three intended rewrites (Minors 1, 2, 5). Every other rewrapped line is word-for-word identical. Docs still true (checked against code above).

## Findings
Critical: none. Important: none.
Minor (cosmetic, optional):
- CLAUDE.md:546 `  4a: \`right_show_gate\` turns` is left as a short line where the rewrapped paragraph stops (the next lines were not reflowed). Renders identically.
- CLAUDE.md:532 `\`_ENUMERATED_MIN_FILES\`/ \`_ENUMERATED_MIN_COVERAGE\``: the old line break after `/` became a space mid-line. Renders identically to before (a newline in Markdown is a space), so it is not a wording change.

## Mutation spot-check (to confirm the new test is not vacuous; own MROOT, shadowing proven per mutant, private PYTHONPYCACHEPREFIX, prediction logged before flip)
| mutant | predicted test | caught by |
|---|---|---|
| M4 reapply.py:107 dry-run skip -> `if False:` | test_names_form_dry_run_of_a_structure_changed_show_prints_the_skip (+ list-form test) | both predicted (2 failed) |
| M5 reapply.py:107 skip ignores `allow_structure_change` | same, second assertion (+ list-form test) | both predicted (2 failed) |
So the names form now has its own pin.

## Suite (snapshot 82fc3a3, shadowed)
3803 passed, 1 skipped, 8 deselected, 26 warnings in 102.93s (matches the commit message)
