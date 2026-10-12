Status: DONE_WITH_CONCERNS (minor)
Commit: a3daa36 (single commit; all steps wired and green before commit)
Files: src/transmitter/{alerts,service}.py (new), cli.py; tests_transmitter/test_service.py (new), test_cli.py.
Tests added: 17 new (brief's 7 service + 4 cli, plus PlanError/StationRootError continue (2), drift halted, publish_all put-budget (publish, prune), high-water warn, held-horizon warn, error/guard routing, fallback horizon updated/deferred (2)).
Gates: 3.14 repo 2431 passed; 3.11 transmitter 282 passed; debian12 282 passed (ffmpeg 5.1.9-0+deb12u1, Python 3.11.2). transmitter.__file__ resolves inside worktree.
Rulings: a) service._report_stop handles publish and prune: put-budget -> alert; guard -> info; high-water and "horizon held" -> WARNING; other stopped/errors -> alert. b) fallback render prints "horizon updated" or "horizon deferred (next publish batch carries the version)". c) planning-fails test pre-renders segments, removes .station-root, asserts seg/ puts and horizon. d) pinned PlanError/StationRootError alert+continue and FrameCountDrift halted. e) E-based helpers used; unused imports dropped.
Brief vs code: held horizon is signalled only as text in PublishReport.error ("horizon held: ..."), not in stopped, so detected by prefix match on "; "-split parts. Unknown future `stopped` values alert.
Concern: held-horizon detection is string-based; a structured field on PublishReport would be sturdier (not changed, publish.py out of scope). test_cli.py has a mid-file import block (from the brief's append).
