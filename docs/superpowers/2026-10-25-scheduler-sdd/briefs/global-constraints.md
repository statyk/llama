## Global Constraints

- Python **3.11** compatible: no 3.12+ syntax (no `type X = …`, no PEP 695 generics, no nested same-quote f-strings). The gate is `packages/transmitter/scripts/test-in-debian12.sh`.
- transmitter never imports llama or emcee (`tests_transmitter/test_no_llama_or_emcee_imports.py`).
- Run tests in the worktree with its own venv: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q` (create it once per the repo CLAUDE.md setup line if missing; check `./.venv/bin/python -c "import transmitter; print(transmitter.__file__)"` resolves inside the worktree).
- Config models stay strict (`_StrictModel`, `extra="forbid"`); persisted state (`plan.jsonl` rows, `aired.jsonl`) is permissive.
- **The plan is append-only:** no new code changes or removes a persisted `plan.jsonl` row. Only `planner.replan_from` (render's skip path) and `planner.cut_for_recovery` (recovery) drop rows, unchanged.
- **Gap layout:** every appended non-`run_start` row starts at `previous.end_frame + gap_frames` (interstitials included); asserted on appended rows only.
- Written rows always carry exact frame counts (`Station.planned_frames` of a real analysis), never estimates.
- The scheduler adds no R2 writes; rows whose `kind` is not `"show"` (interstitials) never reach `timeline.json`, `notes/` or `show/`.
- `[planner] seed` and `[planner] start_delay_minutes` stay as config keys.
- Clock file: `<TRANSMITTER_ROOT>/clock.toml`; last-good copy `<TRANSMITTER_ROOT>/clock.last-good.toml`.
- Interstitials folder default `<station root>/interstitials/`; station IDs `id-*.mp3`, announcements `ann-<id>.mp3`; transmitter only reads it (`announcements --export DIR` is the one explicit operator write).
- Announcement defaults (part of the clock contract; changing one later retires voiced clips):
  `next = "Coming up next, {title}. Then at {next_time}, {next_title}."`,
  `next_one = "Coming up next, {title}."`,
  `later = "Stay tuned for {title} at {time}, followed by {next_title} at {next_time}."`,
  `later_one = "Stay tuned for {title} at {time}."`,
  `time_format = "short12"`, `zones = [{tz="America/New_York", label="Eastern"}, {tz="America/Los_Angeles", label="Pacific"}]`.
- Rotation defaults: `concert_gap_days = 45`, `on_this_day_weight = 3.0`; open blocks `max_shows` unbounded by default, profile blocks 2; `wiggle_minutes` 15.
- New alert codes, neither gated (each sends at once, deduped by `repeat_hours`): `clock` (Task 11) and `history` (Task 7).
- Implementer model: Sonnet unless the task header says Opus.

