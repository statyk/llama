Status: DONE
Commit: 8b53cfc8 antenna: off-air page, home-screen app, fixed link preview
Tests: npm test 518 passed (516+2), typecheck clean, npm run smoke 56 passed (55+1).

Implemented
- public/offair.html: inline CSS, system fonts, no script/assets refs, cream/brown/oxblood/teal, refresh 300, link to "/" , viewport-fit=cover.
- public/assets/radio.webmanifest: name/short_name "LMA Radio", standalone, start_url "/", scope "/", palette colours, icon-192 and cassette-512.
- public/index.html: manifest link, apple-touch-icon (icon-180), apple-mobile-web-app-capable/title/status-bar-style, mobile-web-app-capable, theme-color, viewport-fit=cover. No service worker.
- src/pages.ts regenerated via npm run pages.
- Tests: two in indexpage.test.ts (brief's); smoke test at 320 px with long band name (".And You Will Know Us..." as ticket artist and notes artist): documentElement.scrollWidth <= 320 on main and with panel open, panel scrollWidth <= clientWidth.
TDD: RED = vitest indexpage 2 failed (before pages regen/manifest link); GREEN = 6 passed.
deploy-assets --dry-run (ANTENNA_BUCKET=x): lists radio.webmanifest with application/manifest+json; no upload. --preview rewrite not run (needs real upload path); code at deploy-assets.mjs:109 handles it.
Frozen files untouched; antenna/src only via pages.

Concerns / notes
- The 320 px test passed on first run; I did not mutation-check it (no scratch-copy break of CSS), so it is unproven that it fails when overflow exists.
- Added mobile-web-app-capable beyond the brief (Chrome equivalent of the apple tag); trivial to drop.
- Off-air link text: "Check whether we're back".

## Fix round 1
Commit: 4765fcce antenna: the 320 px test puts the long band on the cassette and every ticket; drop mobile-web-app-capable
- smoke 320 px test: timeline = makeTimeline(Date.now(), { onAir: { artist: LONG } }) and every show mapped to LONG (SLUG notes keep it); waits for #label-artist to show LONG before the first assertion.
- Mutant (scratch copy, white-space: nowrap on .hand.h1): expected red = the first scrollWidth <= 320 assertion. Result: RED at smoke.pw.mjs:775 as predicted. Live tree unchanged.
- Removed mobile-web-app-capable from index.html; npm run pages rerun.
- npm test: 518 passed. npm run smoke: 56 passed.
