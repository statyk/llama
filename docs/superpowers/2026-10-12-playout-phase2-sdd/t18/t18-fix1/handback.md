# t18-fix1 handback
Commit 80e2223 (one commit, on 906222e, branch playout-t18). All F1-F8 done.
- F1 docs/playout-setup.md section 4 step 6 (~l.221): measured freeze result replaces the "~100 s late" claim.
- F2 docs/superpowers/plans/2026-10-11-playout-phase2.md l.70 (A4 amendment): (a) version mix-up fixed, (b) off-air rule failure for on-time invocation, (c) ~2.5 min notice latency supersedes ~45 s, (d) freeze data. Also updated the player-options sentence (no liveSyncDuration).
- F3 antenna/public/player.js ~l.59-69: liveSyncDuration dropped, comment updated. Node check: new Hls({maxBufferLength:130,backBufferLength:30}) constructs (config 130/30, liveSyncDuration undefined) from node_modules/hls.js/dist/hls.mjs.
- F4 config.py dead_clock comment; deadclock.py playlist_age_s docstring (off-air under-read ~loopMs + one segment, ~85 s later alert, more after restart).
- F5 test_deadclock.py: positive-offset case with HOLD-BACK=40.960 (age 40.96); -inf case (ignored, falls to HOLD-BACK; with HOLD-BACK malformed too, dated by newest segment); new test START wins over differing SERVER-CONTROL.
- F6 playout-setup.md step 6 (VLC runway, hold-back=lookahead rationale, lookahead caution) and the dead_clock_seconds row wording.
- F7 antenna/src/clock.ts: local renamed windowSegments (config key still `window`).
- F8 antenna/test/playlist.test.ts: pre-epoch off-air playlist numbers MEDIA-SEQUENCE 3 (lookahead 2); would be -2 unclamped.
Gates: cd antenna && npm test && npx tsc --noEmit: 236 passed, tsc 0. ./.venv/bin/python -m pytest -q: 2613 passed, 1 skipped. ./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q: 457 passed, 1 skipped. test-in-debian12.sh: 458 passed.
Note: my first F5 start-wins test had the wrong "now"; fixed before commit. F8 mutation (removing Math.max) not run by me.
