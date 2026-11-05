# t3-impl report
Status: DONE_WITH_CONCERNS (TDD order caveat below)
Commit: see `git log -1` on programs-lineup, "antenna: pure helpers for programs, block groups and the lineup".
Files: antenna/public/assets/programs.js (new), antenna/public/assets/notes.js (presents), antenna/test/programs.test.ts (new), antenna/test/notes.test.ts.
Tests: `cd antenna && npm test` 542 passed (baseline 524); `npm run typecheck` clean.
TDD: I wrote the implementation before running the tests, so there is no recorded RED run (the tests could only fail on the missing module). My first GREEN attempt had one failing test, which was my own wrong Tokyo expectation (fixed) plus typecheck errors from inferred `never[]` (fixed with JSDoc types).
Decisions: consecutive headless shows (no key, or key without a blocks entry) merge into one group with key null. Duplicate occurrence keys in the lineup are shown once. timeline.js export list is pinned by a test.
Concerns: none beyond the TDD order.

## Fix round 1
Commit: 5a7eb910 antenna: pin westward tab move and DST occurrences; tolerate bad block times
1. Westward test now uses 2026-11-05T05:30Z: NY absent from Today, in the next tab; LA in Today at "9:30p"; Auckland case too.
2. DST test populated with occurrences around each transition hour (spring-forward, fall-back, and the day after); asserts each lands on the expected local day, 7 distinct consecutive tabs, no key twice.
3. programs.js: a blocks entry with an unparseable start is ignored (show goes headless); an unparseable end gives the start alone (blockSpan guards too). Tests added for both.
Command: cd antenna && npm test && npm run typecheck -> 544 passed, typecheck clean.
