Task 19: DONE. Commit: see git log (docs(CLAUDE.md): transmitter and antenna commands and architecture).
Tests: pytest 2438 passed, 7 deselected; antenna npm test 37 passed (3 files). transmitter imports from the worktree.
Corrections vs brief: added `--once` to `transmitter run`; noted test-in-debian12.sh needs docker. Other brief facts matched code (dist llama-transmitter, import test name, spike build|serve, scripts, wrangler, d=10.24).
Additions folded in: high-water (publish.json high_water; fallback render defers horizon), antenna bounds, HeldTracker (3 consecutive held publish_all passes -> horizon-held), PublishLocked, py3.11 gate.
Concern: extra files pytest.out/pytest.rc left in this dir.
