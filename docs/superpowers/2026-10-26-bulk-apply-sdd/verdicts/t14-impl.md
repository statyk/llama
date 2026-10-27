# Task 14 handback: overrule backfill (t14-impl)

Status: DONE_WITH_CONCERNS (concerns are design notes for the checkpoint, not defects)

Commit: da32e253 feat(bulk): overrule backfill from the overnight verdicts

## What was implemented (scripts/bulk_apply.py)
- `BackfillShow(slug, record: list[Overrule], listed: list[tuple[str, str]], show_reason: str | None)`.
- `plan_backfill(root, base, verdicts, delivered) -> list[BackfillShow]`, read-only.
  Considered: base row outcome `newly-held`, base state != `held`, and today's
  `catalog.derive_state(ws, delivered)` != `held` (the same derivation `llama status` uses;
  `delivered` = ledger delivered performance ids, as `iter_shows` builds it).
  Base flags = gather_flags + vet_flags + brief_flags. Verdict `<verdicts>/<slug>.json`.
  Recorded: layout A `flags[].verdict == "spurious"`, layout B `claims[].verdict == "flag-spurious"`
  (each value honoured only in its own layout), or the flag text named in
  `action.overrule_if_reheld_on`. Matching base flag to verdict is exact text.
  Listed reasons (verbatim): `no verdict` (show-level `show_reason`), `verdict never ruled on this flag`,
  `ruled <verdict>`, `only in other_flags (free text)` (exact text of an `other_flags[].flag`),
  `not overrulable (package flag)` (flag_key None), `cannot derive the unresolved files`.
  `titles` subject = show.json filenames at the base row's `title_sources[i] == "unresolved"`
  positions, built explicitly (never via records_for on today's show); listed with
  `cannot derive the unresolved files` when the track counts differ.
  Other kinds use `records_for([flag], show, source="backfill", at=...)`; identifier = show.json's.
- `backfill` subcommand: prints per show `<slug>:` then `  record: <flag>` / `  list: <flag> (<reason>)`
  (a show-level reason prints `<slug>: <reason>` and its `  base flag:` lines), then
  `totals: shows considered N, shows with no verdict N, flags recorded N, flags listed N, shows fully covered N of M`
  (M = shows with a verdict), then `dry run: nothing written (pass --apply)`.
- `--apply` order: require_pinned_code -> require_tools(pin) (both before reading anything) ->
  plan -> targets = shows whose records add something to stored overrules (none: prints
  `nothing to record...`, writes nothing, no snapshot, exit 0) -> batch_snapshot.take into
  `<root>/campaign/backfill/<stamp>/snapshot/` -> retire_rekey_restore(by="bulk-apply overrule backfill <stamp>") ->
  per show under `file_lock(ws.lock)`: re-plan that row, refuse a legacy/mixed overrides.json
  (override_keys.refusal), read_overrides, merge_rules, write_artifact(overrides.json),
  record_after (last write to a tracked file), append `{slug, at, added}` to `record.jsonl`
  (outside the show dir, flushed). Per-show error -> printed, exit 1. Gate refusal -> exit 2.

## Tests (scripts/test_bulk_apply_backfill.py, fixtures of both layouts inline)
All nine from the brief: test_layout_a_spurious_is_recorded_real_is_listed,
test_layout_b_flag_spurious_recorded_research_right_show_wrong_listed, test_overrule_if_reheld_on_records,
test_no_verdict_lists_the_show, test_show_held_today_is_skipped, test_titles_subject_from_base_title_sources,
test_apply_snapshots_retires_and_is_idempotent (order tools -> take(g1 only) with rekey not yet retired;
retired.by carries the stamp; after.jsonl/record.jsonl; restore dry run not refused; second --apply
leaves the whole tree byte-identical), test_apply_refuses_without_gates (no pin, tools refused, dirty
code: exit 2, tree unchanged), test_dry_run_writes_nothing.

### RED
`./.venv/bin/python -m pytest scripts/test_bulk_apply_backfill.py -q` -> 9 failed:
6x `AttributeError: module 'bulk_apply' has no attribute 'plan_backfill'`, 3x argparse
`invalid choice: 'backfill'` (SystemExit 2). Expected: neither the function nor the subcommand existed.

### GREEN
`./.venv/bin/python -m pytest scripts/test_bulk_apply_backfill.py scripts/test_bulk_apply_scaffold.py -q` -> 16 passed.
Full: `./.venv/bin/python -m pytest -q` -> 6260 passed, 1 skipped, 8 deselected (baseline 6251 + 9).
The 26 warnings are the pre-existing fork DeprecationWarnings in test_sessions.py; the new file emits none.

### Mutation (scratch copy under the scratchpad, worktree untouched)
Caught: titles subject from today's show (2 tests), dropping the held-today skip, layout B accepting
`spurious`, ignoring overrule_if_reheld_on, no snapshot before writes, no record_after.
Survived: removing the in-lock `if not added: return "nothing new"` -- masked by the pre-lock target
filter; it only matters in a race (another writer adds the same rule between plan and lock). Kept as
defence in depth; not testable without a race harness.

## Files changed
- /Users/shawn/projects/llama/.claude/worktrees/bulk-apply/scripts/bulk_apply.py
- /Users/shawn/projects/llama/.claude/worktrees/bulk-apply/scripts/test_bulk_apply_backfill.py (new)
No existing test expectation moved.

## Measurement cross-check (read-only, base + verdicts only, no library read)
Same rule, without the today-held filter: 195 considered, 15 no verdict, 316 recorded, 62 listed
(54 never ruled, 2 only in other_flags, 4 ruled research-wrong, 2 ruled research-right-show-wrong),
141 of 180 fully covered -- matches the planning numbers; the plan's "56 never ruled" splits into
54 + 2 `only in other_flags`. All 8 base `unresolved track titles` flags have unresolved base positions.

## Self-review / concerns
1. Small additions beyond the brief (listing-only, never recording): show-level `no show.json` and
   `show.json unreadable: ...` reasons (printed with a separate `shows listed for another reason N`
   total only when non-zero); a `titles` flag whose base row has no unresolved position is listed as
   `cannot derive the unresolved files` (an empty subject would be degenerate; 0 such rows today).
2. A flag ruled several times records only if every ruling is the layout's false-hold value (0 conflicts
   in the real verdicts); `ruled <v>` names the first non-recording verdict.
3. A corrupt verdict file refuses the whole plan (LlamaError, exit 2) rather than listing the show.
4. If a per-show unit failed after write_artifact but before record_after, restore treats that show
   as written-without-record (left alone) -- reported as `error:` and exit 1.
5. Open for the checkpoint (not decided here): rehold-verdicts/ is not read.

## Fix round 1 (review Important 1)

Commit: 884dd4ad `fix(bulk): the backfill's per-show unit rolls back a write it cannot record`

Change: `_backfill_one` now runs inside `show_unit(ws, None)` (it takes the show lock; the bare
`file_lock` and its import are gone, so there is no nesting). Any exception, including Ctrl-C, inside
the unit restores every file outside `package/audio/` from `.txn/`. `record_after` is still the last
write to a tracked file; the `record.jsonl` append (outside the show dir) follows it inside the unit.
If the append fails, the unit rolls back and the after-record's show then reads `already restored`
on a batch restore (current == snapshot), which is harmless. Added `_stamp()` as a seam for the batch
directory name (the test's re-run lands within the same second).

Covering test: `test_a_failed_after_record_rolls_the_show_back`. With `record_after` raising OSError:
exit 1, overrides.json byte-identical to before, no after.jsonl, no record.jsonl, no `.txn/` left,
and the batch restore reports `untouched`. A re-run with `record_after` working exits 0, writes both
rules, and records g1 in the new batch's after.jsonl and record.jsonl.

RED (live tree, before the fix): `./.venv/bin/python -m pytest scripts/test_bulk_apply_backfill.py -q`
-> the new test failed on `assert ov.read_bytes() == before` (overrides.json was left rewritten:
`b'{\n  "exclu...` vs `b'{"narration": "vague"}'`), which is the defect the reviewer reproduced.
GREEN: `./.venv/bin/python -m pytest scripts/test_bulk_apply_backfill.py scripts/test_bulk_apply_scaffold.py -q`
-> 17 passed. Full: `./.venv/bin/python -m pytest -q` -> 6261 passed, 1 skipped, 8 deselected.
The reviewer's Minor items were left alone, as instructed.
