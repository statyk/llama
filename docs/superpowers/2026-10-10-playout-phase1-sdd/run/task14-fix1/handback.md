Status: DONE. Commit: be38f54 fix(transmitter): structured held-horizon signal with escalation; PublishLocked is a warning; publish exit code
1 PublishReport.held (set in publish.py at the held return; error text kept); _report_stop uses it; dead put-budget clause removed. HeldTracker on Runner (publish_all(p,t,held=None)): WARNING per occurrence, alert "horizon-held" at the 3rd consecutive pass, reset on a clean pass. Test: warn only on 1-2, alert on 3, reset.
   Mutant (scratch copy, PYTHONPATH sentinel-proven, isolated pycache): escalation disabled. Predicted: only the persist test red. Result: exactly that one failed (1 failed, 29 passed).
2 PublishLocked in Runner._step: WARNING, no traceback, no alert; tested.
3 test_status_lines_populated (plan, on air, published segments lines).
4 publish exits 1 with reason on stderr for put-budget/guard/error; 0 clean/empty; tests for all three.
5 blank line fixed.
Gates: 3.14 repo 2437 passed; 3.11 transmitter 288 passed; import resolves in worktree. No Debian gate (no ffmpeg change).
Note: high-water prune stop still exits 0 from publish (not in the listed set).
