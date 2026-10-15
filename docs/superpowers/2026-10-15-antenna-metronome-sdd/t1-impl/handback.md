# t1-impl report
Status: DONE. Created antenna/src/live.ts and antenna/test/live.test.ts verbatim from the brief; edited antenna/src/clock.ts per the four edits (imports + LIVE_KEY re-export, removed local LIVE_KEY and offairWithoutFallback, write closure uses renderLive/putLive).
Tests: `cd antenna && npm test && npm run typecheck` -> Test Files 15 passed, Tests 240 passed (240); tsc silent.
TDD: the RED step (run live.test.ts before live.ts exists) was skipped; files were written together. Not run.
Self-review: clock tests unchanged and green. One behavioural nuance from the brief's code: putLive now floors and clamps max-age to >=1 (previously raw config.liveMaxAge).
Concerns: none.
