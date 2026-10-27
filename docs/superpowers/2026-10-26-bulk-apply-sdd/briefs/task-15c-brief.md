# Task 15c (parent-directed follow-up to Task 15): a fifth marking trigger — newly held with no visible change

**Spec:** "The `awaiting_fix` contract" (Who gets marked), "The library side" (Marking skips). Strict surface 1 (station marks on delivered shows). **Implementer: Opus.**
**Files:** Modify `scripts/bulk_apply.py` (marking section: the reason constants, `_REASON_KINDS`, `_plan_one_mark`, and `_print_mark_plan` only as far as the new kind needs), `docs/superpowers/plans/2026-10-26-bulk-apply.md` (Contracts, one line); Test `scripts/test_bulk_apply_mark.py`.

Task 15 (+ 15b) built `bulk_apply.py mark`. Read `scripts/bulk_apply.py` from `# --- marking` through `cmd_mark`, and the existing tests in `scripts/test_bulk_apply_mark.py`, before anything else. `_plan_one_mark` marks, in priority order: a re-selection (start `select`); a `needs-llm`/`unreplayable` row only via the frozen list (not processed); a label-only row never; a visible change (`row_visible_changes`); a processed show is otherwise skipped; the frozen list; a stored briefing that fails today's guard. Everything else is unmarked.

Checkpoint B measured (`.superpowers/sdd/bulk-apply/orch-r2/checkpoint-b-addendum.md`): of 220 arm rows with outcome `newly-held`, 90 were unmarked — 89 with no visible field change whose hold comes only from new gather/vet/brief flags (88 packaged, 1 delivered), and 1 label-only (`stantonmoore-2005-05-14`). The operator confirmed the four-trigger rule as is and ruled one addition:

## The rule

A row whose arm `outcome == "newly-held"` that no existing trigger marks, and that is not label-only, IS marked, with start stage `gather` and the row's `digests` (as the visible-change and guard reasons carry them). Concretely, in `_plan_one_mark` it is the LAST check, after the guard check:
- a processed show with no visible change stays skipped (the existing `if processed: return None` comes first);
- a label-only row stays unmarked (the existing `row_label_only` check comes first);
- a row any earlier trigger marks keeps that trigger's reason (re-selection, frozen, visible change, guard all win);
- `needs-llm`/`unreplayable` rows are untouched (their outcome is not `newly-held`, and they return before this point anyway).

Like every reason, every state gets the library record (`campaign.add_mark`) and only a delivered show with a station copy gets a station mark — `mark_apply`, `unmark`, the record line and the exit rule are unchanged.

## The fixed string

Reason: `newly held by today's checks: <kinds, comma-joined>`, where `<kinds>` is, in first-seen order without repeats, `overrules.flag_key(f, stored).kind` for each `f` in the arm row's `gather_flags + vet_flags + brief_flags` (`stored` = the show's `show.json`, as `_plan_one_mark` already reads it); a flag whose `flag_key` is `None` contributes `package`. If the row has none of those flags (it cannot be newly held without one, but the arm is input), the reason is the bare prefix `newly held by today's checks` with no colon.

Add a constant `REASON_NEWLY_HELD = "newly held by today's checks"` beside the other four and append it to `_REASON_KINDS`, so the dry run's `marking plan` table prints a row for it like the others (the kind is found by prefix, as today).

In the plan's Contracts, the `marking reasons:` bullet gains, after `recording re-selection: <stored> -> <pick>`: `; ` + `` `newly held by today's checks: <flag kinds, comma-joined in first-seen order from gather_flags, vet_flags, brief_flags; package for a non-overrulable flag>` ``. Change nothing else in the plan.

## Tests (names fixed; each RED in the live tree before implementing; reuse the file's fixture library + station + hand-built arm helpers)

- `test_newly_held_without_visible_change_is_marked` — a packaged and a delivered show, each with an arm row `outcome: "newly-held"`, empty diffs, a venue-mismatch `gather_flags` entry and a `research asserts unknown song: X` `vet_flags` entry: both planned with reason exactly `newly held by today's checks: venue, research-song`, start `gather`, the row's digests; after `mark --apply` the packaged show has a library record and no station write, the delivered one has both (record line `marked`).
- `test_newly_held_label_only_and_processed_stay_unmarked` — a `newly-held` label-only row (a title-source-only change, as `stantonmoore-2005-05-14`) and a `newly-held` no-diff row whose campaign record is processed: neither is planned.
- `test_earlier_triggers_win_over_newly_held` — `newly-held` rows that also have (i) a visible change, (ii) a frozen-list slug, (iii) a failing stored-briefing guard, (iv) a re-selection: each keeps its existing reason.
- `test_mark_dry_run_table_has_the_newly_held_row` — the dry run prints a `  newly held by today's checks: …` table row with the right column counts.

Existing tests whose expectation moves (e.g. one asserting a `newly-held` no-diff row is NOT marked, or the dry-run table's exact rows): list each with the reason before editing (Global Constraints dry run).

## Constraints

- Stub `station_mark.emcee_running()` / `ps` in every test (a real emcee process once broke four tests).
- Never write under `~/.llama`, `~/.llama-harness` or `/Volumes/media/lma-radio/delivered/`; tests use tmp dirs only. Do not run the real `mark` (the orchestrator runs the read-only Checkpoint B2 dry run afterwards).
- Review Focus 1 unchanged: `write_mark`'s byte checks and `emcee_running()` before each station write untouched.
- Full suite green after: `./.venv/bin/python -m pytest -q` from the worktree root (baseline: the head you start from; state it).
- Commit `feat(bulk): mark newly held shows with no visible change (Checkpoint B ruling)` with the trailer `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>` and the test command in the message.
