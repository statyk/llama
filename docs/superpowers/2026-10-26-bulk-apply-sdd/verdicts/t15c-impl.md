# Task 15c handback: fifth marking trigger (newly held, no visible change)

**Status:** DONE
**Commit:** f1f447db feat(bulk): mark newly held shows with no visible change (Checkpoint B ruling)
**Baseline:** HEAD 4a27c6c6, 6337 passed, 1 skipped, 8 deselected.

## What was implemented (scripts/bulk_apply.py, marking section only)
- `REASON_NEWLY_HELD = "newly held by today's checks"` beside the other four, appended to `_REASON_KINDS`. `_print_mark_plan` needed no change: it builds its table from `_REASON_KINDS` and finds the kind by prefix, so the new row prints like the others.
- `_newly_held_reason(row, stored)`: walks `gather_flags + vet_flags + brief_flags` and takes `flag_key(f, stored).kind`, or `package` when flag_key returns None. Kinds are kept in first-seen order without repeats, giving `newly held by today's checks: <kinds>`. With no flags it returns the bare prefix, no colon.
- `_plan_one_mark`: the LAST check, after the guard check. `if row.get("outcome") == NEWLY_HELD` (it reuses the module's existing `NEWLY_HELD = "newly-held"` constant from the wave section) returns `(reason, "gather", digests)`. All the earlier returns keep their precedence: re-selection, the needs-llm/unreplayable branch, label-only, visible change, `if processed: return None`, frozen, and guard.
- `mark_apply`, `unmark`, the record line, the exit rule, `write_mark` and `emcee_running()` are untouched. `_could_mark` already returns True for any outcome outside `_NO_DIFF`, so a newly-held row with a missing show directory was already listed as unplannable.
- Plan Contracts: `docs/superpowers/plans/2026-10-26-bulk-apply.md`. The `marking reasons:` bullet gains the brief's text verbatim after `recording re-selection: <stored> -> <pick>`. Nothing else in the plan changed.
- Verified: `ShowReplay` (llama/replay.py:709-711) has `gather_flags`/`vet_flags`/`brief_flags` fields, so arm rows carry them.

## Tests (scripts/test_bulk_apply_mark.py; new section "Task 15c")
- `test_newly_held_without_visible_change_is_marked` covers a packaged and a delivered show, each a newly-held no-diff row with a venue-mismatch gather flag and a `research asserts unknown song: X` vet flag.
  - Both are planned with reason exactly `newly held by today's checks: venue, research-song`, start `gather`, and the row's digests.
  - After `mark_apply` (the `--apply` path) both have a library record. Only `dl` has a station mark; pk gets no station write.
  - Record lines: `dl: marked`, `pk: not delivered`.
- `test_newly_held_label_only_and_processed_stay_unmarked`: a title-source-only newly-held row and a processed newly-held no-diff row. Neither is planned.
- `test_earlier_triggers_win_over_newly_held`: newly-held rows with (i) a visible venue change, (ii) a frozen slug, (iii) a failing guard, (iv) a re-selection. Each keeps its existing reason and start.
- `test_mark_dry_run_table_has_the_newly_held_row`: through the CLI dry run with `--campaign-dir` scratch. It asserts the exact line `  newly held by today's checks: delivered unvoiced 1, delivered voiced 0, packaged 2, briefed 0, held 0`, the changed row's counts, `by arm outcome: clean-changed 1, newly-held 3`, and that nothing is written.
- EXTRA, not in the brief: `test_newly_held_reason_kinds_first_seen_and_package_fallback`. It pins the string rule:
  - a `duration mismatch on` flag gives `package`
  - a repeated kind (venue in both gather and brief, two research-song flags) appears once
  - the order is first-seen across gather, vet, brief, giving `package, venue, research-song, briefing-song`
  - a row with no flags gives the bare prefix

## TDD evidence
RED, live tree, before implementing:
`./.venv/bin/python -m pytest scripts/test_bulk_apply_mark.py -q -k "newly_held or earlier_triggers"`
-> 3 failed, 2 passed.
- marked: `assert set() == {'dl', 'pk'}`
- kinds: `assert {} == {...}`
- dry run: `'marking plan: 4 show(s)'` not in `'marking plan: 1 show(s)...'`

These failures are expected because nothing marked newly-held rows yet.
`test_newly_held_label_only_and_processed_stay_unmarked` and `test_earlier_triggers_win_over_newly_held` cannot be RED before the change. They pin existing behaviour that the new trigger must not override. To show they are load-bearing I ran a mutant in a scratch copy (scratchpad/mut15c, run from an empty cwd, import confirmed to resolve to the copy). The mutant moved the newly-held check to the top of `_plan_one_mark`, right after `row is None`. Predicted: both guard tests go red. Result: exactly those 2 failed, 3 passed.

GREEN: `./.venv/bin/python -m pytest scripts/test_bulk_apply_mark.py -q` -> 47 passed.
Full suite: `./.venv/bin/python -m pytest -q` -> 6342 passed, 1 skipped, 8 deselected, 26 warnings in 81.43s (baseline 6337 + 5 new).

## Existing tests whose expectation moved
None. No existing test asserted that a newly-held no-diff row stays unmarked. The existing dry-run test checks table rows with `in out`, so the extra table row does not affect it.

## Self-review
- The diff is minimal and limited to the marking section, as the brief scoped it. Names follow the neighbours (`_llm_reason` -> `_newly_held_reason`).
- The prefix `newly held by today's checks` collides with no other reason kind.
- `_could_mark`'s docstring says "an arm row with a diff". It is slightly loose now that a no-diff newly-held row can be marked, but its behaviour (any outcome outside `_NO_DIFF`) is already correct. I left it unchanged, outside the brief's scope.

## Concerns
- None blocking. The extra test is beyond the brief's four fixed names. It is additive and pins the reason string's rule.
