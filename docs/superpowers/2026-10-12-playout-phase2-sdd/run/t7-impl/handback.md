# Task 7 handback (t7-impl) — Bundled pages and index.html reconciliation

Status: DONE
Commit: a424809 feat(antenna): index.html follows the blocked state from pages bundled into the Worker

## Implemented (verbatim from the brief)
- antenna/scripts/build-pages.mjs — generator; `--check` exits 1 with "src/pages.ts is stale: run `npm run pages`" when stale/missing.
- antenna/src/pages.ts — generated via `npm run pages` (not hand-edited): PLAYER_PAGE, OFFAIR_PAGE.
- antenna/src/indexpage.ts — INDEX_KEY, INDEX_HTTP, sha256Hex, reconcileIndex(bucket, blocked) -> "written" | "unchanged" (one HEAD; PUT with customMetadata {sha256, page} only on sha mismatch).
- antenna/test/indexpage.test.ts — the brief's 4 tests.
- antenna/package.json — scripts set exactly as the brief (test = `node scripts/build-pages.mjs --check && vitest run`, new `pages`).

## Deviations
- Staleness check (Step 4) was run in a scratch copy (rsync of antenna/ minus node_modules, node_modules symlinked) instead of appending to the live public/offair.html, per mandate 5 (deliberate breakage only in a scratch copy). Same command, same result. No code deviations.

## Tests
RED: `cd antenna && npx vitest run test/indexpage.test.ts`
  -> FAIL test/indexpage.test.ts: Error: Cannot find module '../src/indexpage' (Test Files 1 failed, no tests)
GREEN focused: same command -> Test Files 1 passed (1), Tests 4 passed (4)
Full: `cd antenna && npm test && npx tsc --noEmit` -> Test Files 12 passed (12), Tests 150 passed (150); tsc clean (146 -> 150).
Staleness (scratch copy): `node scripts/build-pages.mjs --check` on clean copy -> exit 0; after `echo "<!-- x -->" >> public/offair.html`, `npm test` -> "src/pages.ts is stale: run `npm run pages`", exit 1, vitest not run.

## Self-review
- reconcileIndex does not catch HEAD/PUT errors; they propagate to the caller (Task 8 is expected to wrap it and raise `index-write`). MemoryBucket.failGets fails `head` too, so Task 8 can test that path.
- PUT is unconditional (no onlyIf): two overlapping invocations at worst both write the same correct page; harmless and level-triggered.
- Spend: one Class B HEAD per call; a Class A PUT only on change.
- Off-air page confirmed to contain "The station is off the air." and no player.js.

## Concerns / notes
- scripts/deploy-assets.mjs still uploads index.html (line 32). Per the plan this is Task 10's change ("no longer uploads index.html [T10]"), so left alone. Until T10 lands, a deploy:assets run would overwrite index.html without metadata — which reconcileIndex corrects within a minute once Task 8 wires it into the clock.
