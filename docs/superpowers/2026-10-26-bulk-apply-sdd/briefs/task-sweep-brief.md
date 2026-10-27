# Task RF (parent-directed RECOMMEND-FIX sweep): two deferred findings fixed before the release

**Implementer: Sonnet.** **Files:** Modify `scripts/bulk_apply.py`; Tests `scripts/test_bulk_apply_reports.py`, `scripts/test_bulk_apply_lists.py`, `scripts/test_bulk_apply_mark.py`.

Earlier task reviews marked these RECOMMEND-FIX; every other RECOMMEND-FIX item in the run's ledgers is already fixed (T9b, T13b, T15b). Each fix is pinned by a test shown RED in the live tree before implementing.

## RF1 — the trial report reads every progress line when it looks for other-kind spend (Task 17 finding)

`_foreign_inside(batch, kind)` (via `_spending_rows`) sees only each slug's LAST progress row (`reapply.read_progress`). An other-kind row that spent inside the block's window, failed, and was re-run outside the window shows only its later row, so its spend hides inside the block's meter delta and the block is measured as contiguous (reviewer probe: 20 shows, delta5 10, no refusal).

Required: the foreign-spend check considers EVERY parseable line of `<batch>/progress.jsonl` (each line with `llm_calls > 0` whose slug's list kind differs from the block's and whose `at` falls inside the block's window, inclusive on both ends, as today). Add a small reader in `bulk_apply.py` (do not change `reapply.read_progress`, which other code relies on for "last row per slug"), skipping unparseable lines as `read_progress` does. The block's own rows, its window, `n` and the measurement stay exactly as today (last row per slug).

Tests: `test_foreign_spend_hidden_by_a_later_retry_is_caught` (an other-kind slug with a spending line inside the window and a later spending line outside it → `not contiguous: 1 spending row(s) of another kind inside it; re-run as one block per kind`, the block excluded from ratio and projection); `test_foreign_window_is_inclusive` (an other-kind spending line whose `at` equals the block's first, and one equal to its last, row's `at` are each counted — pins the inclusive boundary a reviewer's mutant survived).

## RF2 — an empty mount-point directory is not a mounted station (Task 16 finding; `mark` has the same gap)

`lists`, `mark` (its gate in `cmd_mark` and the per-item `station_root.is_dir()` check in `_mark_one`), and `wave-check` accept a station root that `is_dir()`. An unmounted network share can leave its mount point as an EMPTY directory, which passes; `lists` would then read every delivered show as unvoiced (no copy) and `mark` would record `no station copy` for every delivered item.

Required: one shared helper in `bulk_apply.py`, used by all four sites, that refuses a station root unless it is a readable directory (`os.access(R_OK)`, as `wave-check` already checks) holding at least one entry whose name does not start with `.` (stop at the first; never list the whole directory). Messages: keep each site's existing wording for "not mounted or not a (readable) directory"; for the empty case, `station root <path> is empty (is the station mounted?)`. At the three command gates it raises `GateRefused` (exit 2, nothing written). In `_mark_one`'s per-item check it yields the existing refused outcome shape, `refused: station root <path> is empty (is the station mounted?)` (or today's `refused: station root <path> is not readable`), so the item is listed and retried, never recorded as `no station copy`. `no delivery_path in config` stays as is.

Tests: `test_lists_refuse_an_empty_station_root` (exit 2, the exact message, no list written); `test_mark_refuses_an_empty_station_root` (dry run and `--apply` both exit 2 before anything is written); `test_wave_check_refuses_an_empty_station_root`; `test_mark_item_refused_when_the_station_empties_mid_batch` (the root is non-empty at the gate and emptied before an item's check → that item's record line is `refused: station root … is empty (is the station mounted?)`, not `no station copy`, and the batch exits 1 listing it). A station root holding only dot-entries counts as empty.

## Constraints

- Stub `station_mark.emcee_running()` / `ps` in every test that reaches it.
- Never write under `~/.llama`, `~/.llama-harness` or `/Volumes/media/lma-radio/delivered/`; tests use tmp dirs only.
- Existing tests whose station root is an empty tmp dir will now refuse: list each with its reason before editing (Global Constraints dry run), and fix the fixture by giving the station root a real show dir (or a non-dot placeholder dir), not by weakening the check.
- Full suite green after: `./.venv/bin/python -m pytest -q` from the worktree root (baseline: the head you start from; state it).
- One commit per fix is fine: `fix(bulk): trial report sees other-kind spend on every progress line` and `fix(bulk): an empty station root refuses (lists, mark, wave-check)`, each with the trailer `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>` and the test command in the message.
