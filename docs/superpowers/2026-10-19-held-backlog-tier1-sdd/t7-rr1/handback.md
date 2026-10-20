# t7-rr1 handback: re-review of Task 7, fix round 1 (050c84b..0038589)

### Finding Verdicts

- **Important 1: the narration_candidates.html sort used parseFloat's leading-prefix parse (dates sorted by year only, and digit-led slugs made the comparator non-transitive)**: ADDRESSED.
  - scripts/replay_holds.py:553-557. `parseFloat` is gone. A cell counts as a number only when the whole trimmed string matches `/^-?\d+(\.\d+)?$/`. I checked the rendered string: the Python `\\d` in a non-raw triple-quoted string comes out as `\d` in the emitted JS. Two numbers compare by value (`+x - +y`), a number always sorts before text, and two text cells use `localeCompare`. That is a total order, so the comparator is transitive. ISO dates and digit-led slugs are now text, so they sort lexically: `1973-01-02` < `1973-06-10` < `311-1995-01-01`. `?` placeholders are text and land after all numbers.
  - The fix is pinned in two places:
    - scripts/test_replay_holds.py:615-617 checks the JS has no `parseFloat(` and does contain the regex.
    - scripts/test_replay_holds.py:620-636 extracts the comparator body, runs it in node over a mixed list, and asserts the order. It accepts two outcomes, which differ only in where `?` falls under the locale's `localeCompare`. The old parseFloat comparator would have put `311-1995-01-01` before both 1973 dates, so it fails this test.
  - Check I ran: `./.venv/bin/python -m pytest scripts/test_replay_holds.py -k narration_sort -q -rs` at HEAD 0038589 gave 2 passed with nothing skipped (node is at /opt/homebrew/bin/node), so the node test really executed. The fix report names both tests and shows a full-suite run (3294 passed, 1 skipped). The skip count matches the pre-fix run, so the skip is not the new node test.

### New Breakage in the Fix Diff

None.
- Minor, non-blocking: the node test finds the comparator body by slicing between the `var x = a.cells` and `return asc` markers and string-replacing `a.cells[i]`. A rewrite of the JS will make that test error loudly, not pass silently, which is acceptable.

### Out-of-Scope Observations

None.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.
