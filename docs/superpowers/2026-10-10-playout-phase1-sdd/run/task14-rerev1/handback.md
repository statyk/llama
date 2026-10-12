Re-review of task14-fix1 (a3daa36..be38f54)

#1 held flag + escalation: ADDRESSED.
  - publish.py:297 sets `report.held = True` on the only held return in publish_batch. The fix touches nothing else in publish.py: a new field defaulting to False, plus that one line.
  - service.py: `_report_stop` routes on `held` (no prefix match decides any more; the marker only splits the error text). The dead put-budget clause is gone.
  - HeldTracker: WARNING on every held pass; alert "horizon-held" exactly once when the streak reaches 3; any pass without a hold resets the streak. Wired through Runner.tick into publish_all.
#2 PublishLocked: ADDRESSED. `Runner._step` catches it before `except Exception`, logs a WARNING with no exc_info and raises no alert. Tested.
#3 status_lines populated-path test: ADDRESSED. test_service `test_status_lines_populated` covers the plan, on-air and published lines.
#4 publish exit code: ADDRESSED. cli.py publish_cmd prints problems to stderr and exits 1 on put-budget, guard or any error (a held hold carries an error, so it also exits 1). It exits 0 when clean or empty. Tests cover clean/empty, budget and guard.
  - Prune "high-water" exiting 0 is acceptable. The service also treats it as a deferral (WARNING), and main_cli's basicConfig still prints that WARNING.
  - It only happens without a publish-side problem when publish found nothing to send; when publish itself failed or held, its own report already exits 1.
#5 blank line before the parametrize decorator: ADDRESSED. But the new tests are preceded by 3 blank lines in both files (test_service.py ~213, test_cli.py ~124; E303). Trivial.

New in the fix diff:
- Minor (test gap): no test drives the real publish_batch into the held path and checks `report.held`; the service tests monkeypatch the report.
  - Mutant run in a scratch copy (sentinel-proven PYTHONPATH, isolated pycache): replacing `report.held = True` with `pass`. Predicted to survive; it survived, with all 288 transmitter tests passing.
  - Risk is low because the failure is loud: an unset flag makes every held pass alert, rather than going quiet. Still, add a test_publish case (high_water above the batch's last, a missing local segment) that asserts `held` and that no horizon PUT happens.
- Note: the escalation alerts once per streak and does not repeat while the hold persists. That matches the ruling; repeating it is phase 2 dedupe's job.

Out of scope (still deferred to the final review): #6 row_analysis clock and lock hold; plan/render taking no lock against `run`.

Verdict: Approved
