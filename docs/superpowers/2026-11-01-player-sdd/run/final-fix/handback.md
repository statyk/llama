Status: DONE (one concern below)
Commits: 139d5946 antenna: final review fixes (code); ac454f74 antenna + docs: final review fixes (docs)
Tests: antenna npm test 519 passed (518 + 1 new zoneLabel test); npm run smoke 58 passed (56 + 2 new); typecheck clean; transmitter 951 passed, 1 skipped.

Done, by brief item:
1. CLAUDE.md: module layout, frozen root files (assets/player.js is live), smoke + needs (system Chrome, ffmpeg), sections, Cautions literal with site.CAUTIONS_PREFIX, round-3 note; smoke added to antenna commands; "phase-4 player is built".
2. index.html footer link target=_blank rel=noopener; smoke assertion; npm run pages.
3. playout-setup.md: Safari timing (30 s stall, ~5 s delay, probes 15 s apart, ~170 s); blip check (130 s buffer, outage must outlast it plus ~20 s); kill-switch note now names /assets/app.js and /assets/radio.css. Checked against recovery.js (nativeStallMs 30000, minDelayMs 5000, probeEveryMs 15000, giveUpMs 600000) and player.js (maxBufferLength 130).
4. Plan Step 4.3 and setup-doc deploy order: launch is round 3; --remove-preview 1 and 2 from the worktree first. The spec's Preview section names no round, so unchanged. antenna/.preview-*.json untouched.
5. app.js: interval armed before first tick; renderAt in try/catch (silent, next tick retries) so player.tick always runs. timeline.js zoneLabel catches the throw and falls back to the zone id (no longGeneric). Unit test stubs Intl to throw. Smoke: footer link test, plus a scenario with Intl throwing on longGeneric (page renders, zone line present, Play turns the hubs).
6. Setup-doc known limits clause (past 10 min after lock-screen Play: "Lost the stream." and Try again); notes wait is ~5 hours with max-age=3600 and KeyError meaning the cached file (setup doc and plan Step 2).
7. offair.html link copy "Try again"; npm run pages. No test or doc named the old copy.

Concern: the smoke scenario does not pin the try/catch in app.js itself (zoneLabel no longer throws, so a render throw cannot be provoked without a test-only hook); the loop-survival guard is read-verified, the zoneLabel fallback is tested in both vitest and the browser.
Frozen files untouched. antenna/.env not touched. No deploy, no wrangler.
