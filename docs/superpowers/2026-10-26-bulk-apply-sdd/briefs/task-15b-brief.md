# Task 15b (parent-directed follow-up to Task 15): three marking fixes before any `mark --apply`

**Spec:** "The marking batch", "A batch is reversible by its record", "Who gets marked", "Marking skips". **Implementer: Opus** (M1 touches the irreversible station-write surface). **Files:** Modify `scripts/bulk_apply.py` (`_mark_station`, `_mark_one`, `mark_apply`, `_unmark_one`/`unmark`, `mark_plan`/`_plan_one_mark`, `_print_mark_plan`, `cmd_mark`); Test `scripts/test_bulk_apply_mark.py`.

Task 15 (commits 5fb225b6, d1bb0127) built `bulk_apply.py mark|unmark`. Its reviewer marked three minors RECOMMEND-FIX; the parent ruled they are fixed before any `mark --apply`. Each is pinned by a test shown RED in the live tree before implementing.

## M1 — a station mark written without its record line must be reversible by `unmark`

Today two windows leave the station copy marked by this batch with no `marked` record line (and no shas):
- a crash (or Ctrl-C) between `station_mark.write_mark`'s rename and `_append_jsonl` in `_mark_one`;
- `_write_durable(saved, before)` in `_mark_station` raising AFTER a successful `write_mark` (the `before != raw` branch), which records `refused: …` although the station IS marked.

Consequence: a re-run reads the station copy, sees a mark, and records `already marked`; `unmark` then removes the library mark, prints `batch mark removed`, exits 0, and the station keeps this batch's `awaiting_fix` — on a voiced show, a stray station mark with the library no longer awaiting.

Required outcome (either design is acceptable; choose and justify in your report):
- **(a) Recognise the batch's own mark on re-run.** When the station copy already carries a mark whose `marked_at` equals this batch's library mark `at` for that show (they are the same value — `_mark_one` passes `at` to both) AND `before/<slug>.json` exists, record `marked` with `before_sha256 = sha256(before/<slug>.json bytes)` and `after_sha256 = sha256(current station bytes)`, so `unmark` can put it back by its normal path. The `_write_durable` failure after a successful `write_mark` must not record `refused` (the station is marked): record `marked` from the evidence that exists, or a distinct non-refused outcome `unmark` reverses.
- **(b) Or make the state impossible by write order** (e.g. a `pending` record line with the before-sha written durably before the station write, completed after), with `unmark` reversing a pending line whose station still holds a mark with this batch's `marked_at`.

Either way, `unmark` must never report success (exit 0) while the station copy holds a mark it attributes to this batch: any `already marked` (or other non-`marked`) line with `mark_added: true` whose station copy carries a mark with this batch's `marked_at` must be put back (when the evidence suffices) or listed as a problem (exit 1) — never silently skipped.

Tests (names fixed): `test_crash_after_station_write_is_reversible` (simulate the crash: monkeypatch `_append_jsonl` to raise on the first call after `write_mark` succeeded, then re-run the batch and `unmark --apply`; assert the station manifest bytes equal the original and exit 0, or, if you choose listing, exit 1 with the slug listed and the station untouched); `test_before_save_failure_after_write_is_not_recorded_refused` (make the second `_write_durable` raise after `write_mark`; assert the record line is not `refused: …` and that `unmark` reverses or lists it); `test_unmark_never_reports_success_over_this_batchs_station_mark` (an `already marked` line, `mark_added: true`, station carrying this batch's `marked_at`, no usable evidence → listed, exit 1).

Hold Review Focus 1 (concurrent emcee rewrite) unchanged: `emcee_running()` before each station write, `write_mark`'s byte checks untouched, `put_back` only while the file holds the bytes marking wrote.

## M2 — a missing show dir or unreadable `show.json` must not silently drop a row

Today `mark_plan` does `if not ws.dir.is_dir(): continue`, and `_plan_one_mark` with `_stored_show(ws) is None` (unreadable/missing `show.json`) skips the label-only and visible-change checks, so a visibly changed row can fall through unmarked and unlisted.

Required: such rows are counted and reported like unreadable station manifests are. `mark_plan` returns them alongside the items (shape your choice, e.g. a second list of `(slug, problem)`), `_print_mark_plan` prints one count line `unplannable shows: N` followed by `  <slug>: <problem>` per show (`no show directory` / `show.json unreadable (<detail>)`), and `cmd_mark --apply` refuses (exit 2, nothing written) while any exist, naming them; the dry run lists them and exits 1. A row that `_plan_one_mark` would mark WITHOUT reading `show.json` (a re-selection; a no-diff frozen row) is still planned when its directory exists; only a missing directory makes it unplannable. Keep the existing `unreplayable, not marked:` and `unreadable station manifests:` lines as they are.

Tests: `test_missing_show_dir_is_reported_not_dropped` (a re-selection row whose show dir is gone); `test_unreadable_show_json_is_reported_not_dropped` (a visibly changed arm row whose `show.json` is not JSON); `test_apply_refuses_while_shows_are_unplannable` (exit 2, no `marking/` batch dir created, nothing under the station written).

## M3 — refuse `--campaign-dir` together with `--apply`

`campaign.frozen_slugs(root)` (used by deliver's hint) always reads `<root>/campaign/needs-llm-frozen.json`, so a real `--apply` pointed elsewhere splits campaign state. `cmd_mark` (and `cmd_unmark`, if it accepts `--campaign-dir`) refuses the combination before reading anything: exit 2, one line `refusing --campaign-dir with --apply: campaign state must live in <root>/campaign (the dry run may use a scratch dir)`. The dry run keeps accepting `--campaign-dir` (Checkpoint B's dry run uses it).

Test: `test_campaign_dir_refused_with_apply`.

## Constraints

- Stub `station_mark.emcee_running()` / `ps` in every test (a real emcee process once broke four tests).
- Never write under `~/.llama` or `/Volumes/media/lma-radio/delivered/`; tests use tmp dirs only.
- Existing tests' expectations change only if a fix requires it; list each one with its reason in the report before editing.
- Full suite green after: `./.venv/bin/python -m pytest -q` from the worktree root (baseline at d1bb0127: 6291 passed, 1 skipped, 8 deselected).
- Commit `fix(bulk): a station mark without its record line is reversible; unplannable shows are listed; --campaign-dir refuses --apply` with the trailer `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>` and the test command in the message.
