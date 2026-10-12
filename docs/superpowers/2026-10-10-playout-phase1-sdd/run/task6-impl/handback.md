# Task 6 (trivial planner): handback

Status: DONE_WITH_CONCERNS (the concerns are minor and come from the brief; nothing is broken)
Commit: 6a65436 feat(transmitter): trivial planner with recovery cut and re-plan (on top of 783a934)

## What was implemented
- packages/transmitter/src/transmitter/planner.py: copied verbatim from the brief's Step 3 listing. It has
  shuffle_rank, choose_next, extend, next_start, replan_from, cut_for_recovery, current_run_start,
  publish_next, read_plan and write_plan. write_plan validates the rows first and then writes through
  workspace.atomic_write_text (unique temp file, fsync, rename), so a failed plan leaves plan.jsonl untouched.
- packages/transmitter/tests_transmitter/test_planner.py: the brief's Step 1 listing (13 tests), with one
  change. Per the orchestrator ruling I removed the unused `from transmitter.layout import PlanRow`.
- Unused-import check: an AST scan of both files found nothing unused. All of planner.py's imports are used.

## TDD evidence
- RED: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_planner.py -q`
  failed with `ImportError: cannot import name 'planner' from 'transmitter'` (1 error during collection).
  This was expected because the module did not exist yet. Python reports it as ImportError rather than
  the brief's ModuleNotFoundError because the test does `from transmitter import planner`.
- GREEN: the same command gave 13 passed.

## Test results
- py3.14: `./.venv/bin/python -m pytest -q` (full repo suite): 2289 passed, 7 deselected.
- py3.11: `./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q -p no:cacheprovider`: 140 passed.
- Debian 12 gate (`packages/transmitter/scripts/test-in-debian12.sh`, run in the background and tee'd to the log):
  `ffmpeg version 5.1.9-0+deb12u1`, `Python 3.11.2`, 140 passed.
- transmitter resolves inside this worktree (checked with `transmitter.__file__`).

## Files changed
- packages/transmitter/src/transmitter/planner.py (new)
- packages/transmitter/tests_transmitter/test_planner.py (new)

## Self-review
- I traced each test against the code: the order is the seeded rank when every show has last_seq -1;
  a new show gets -1 and goes first; a show is never repeated back to back unless it is the only one;
  a skipped show is removed from the pool for this call only and reported once; an empty pool raises
  PlanError only when the loop needs another row; the recovery cut boundary is (last+1)*441 and the
  row spanning it gets cut_frame=boundary (cut_frame > start always holds, because rows starting
  at or after the boundary break first).
- Python 3.11 compatible: only `X | None` annotations, no 3.12+ syntax. No network access and no
  imports of llama or emcee.

## Concerns (for Task 9 / the reviewer; none block this task)
1. read_plan on a corrupt plan.jsonl raises a raw json.JSONDecodeError/TypeError, not a TransmitterError.
   Task 9's caller should decide whether a corrupt plan maps to PlanError. Today the CLI would show a traceback.
2. extend validates rows only at the end. If frames_of returned <= 0 the loop would keep running
   until until_frame (frames 0 with gap > 0) and then fail validation with a LayoutError, or never end
   (negative frames with gap < |frames|, or frames 0 with gap 0). A real frame count cannot be negative,
   so the only reachable case is a 0-frame encode, and that ends in a LayoutError.
3. A show skipped by on_skip is retried on the next extend call. That looks intended (the problem may
   be transient), but on every planning pass on_skip fires again for the same persistently bad show.
