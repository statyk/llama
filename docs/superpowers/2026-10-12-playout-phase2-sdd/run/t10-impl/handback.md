Task 10: DONE. Commit 1556760 "feat(antenna): unrestricted send_email binding, destination in a secret; index.html left to the clock".
Tests: antenna npm test 215 pass (14 files), tsc clean, deploy-assets --dry-run grep -c index.html = 0.
Changes: wrangler.jsonc (send_email binding), tsconfig.json (vite/client), deploy-assets.mjs (no index.html, header updated), test/wrangler-config.test.ts (new), worker-configuration.d.ts regenerated via `npx wrangler types` (ALERT_EMAIL binding type, 2+/1-).
Checks: noSecrets() in clock.test.ts already unsets ALERT_EMAIL, so no email can send; no deviation. wrangler.jsonc has only whole-line // comments and no trailing commas; JSON.parse works. No deploy commands run.

## Fix round 1
Changed antenna/test/wrangler-config.test.ts only: added the 3 assertions (zone_id/account_id regex, 32-hex regex, no routes) and wrapped the JSON.parse with a hint. The test reads only wrangler.jsonc, not worker-configuration.d.ts.
Command: cd antenna && npm test && npx tsc --noEmit -> 215 pass, tsc ok.
Mutant (scratch copy, expected red: "carries no account details"): routes[].zone_id added -> that test failed on the zone_id regex, as predicted.
