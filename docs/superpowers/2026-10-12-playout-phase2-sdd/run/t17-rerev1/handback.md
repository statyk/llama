VERDICT: ALL ADDRESSED

Scoped re-review of t17 fix round 1, 01186ea (ea3ca04..01186ea). Only docs/playout-setup.md changed. I checked each fix against antenna/src/*.ts, antenna/scripts/deploy-assets.mjs, antenna/wrangler.jsonc, packages/transmitter (deadclock.py, cloudstate.py, the systemd unit) and the installed wrangler 4.149.0 (antenna/node_modules/wrangler/wrangler-dist/cli.js). No network, no wrangler runs, no --dry-run, no systemctl, nothing written to the worktree.

### Finding verdicts
- **K1: ADDRESSED.** docs/playout-setup.md:458 now quotes "Kill switch corrected" (`waf-corrected`), which matches guard.ts:295 `title: "Kill switch corrected"`. `grep "toggled by hand"` finds nothing left in the doc.
- **K2: ADDRESSED.** See doc:200.
  - The doc now names `"triggers": { "crons": [] }` and says that deleting the `triggers` key does NOT remove the cron. Both match wrangler 4.149.0:
    - `resolveCronTriggers` returns `config.triggers?.crons` (cli.js:190885-190886).
    - The schedules PUT is sent only `if (crons)` (cli.js:164939). `[]` is truthy, so it PUTs an empty list.
    - Validation accepts an empty array (cli.js:29052 checks only `Array.isArray`).
  - "Confirm … Trigger events lists no cron BEFORE enabling the rule" is present, and the order is right: remove the trigger, confirm, then enable the rule.
  - "The way back" is present and correct against the code:
    - Writing `offair on` first keeps the station dark.
    - On redeploy, reconcile disables a hand-enabled rule and raises `waf-corrected` only when `blocked` is false. guard.ts:289-298: `r.changed && prev.waf.enabled === r.enabled` (prev false, set false). A tripped or off-air station is blocked, so the rule is left alone.
    - "dead-clock 403 alert after about 17 checks" matches deadclock.py `forbidden_checks = 17` and its 403-not-blocked branch.
  - See Minor N4 for one gap in the way back.
- **K3: ADDRESSED.** Top of section 7 (doc:379), referenced from 4 step 4 (doc:200) and from the section 8 intro.
  - `set -a; . /etc/transmitter/<user>.env; set +a` matches phase 1's own form (doc:138).
  - The env path matches the unit's `EnvironmentFile=/etc/transmitter/%i.env`.
  - `~/.venvs/transmitter/bin/transmitter` run as `<user>` resolves to the unit's `ExecStart=/home/%i/.venvs/...`.
  - The ownership and mode statement (`<user>`, 600) matches the 6.1 `install -m 600 -o <user>` line. So the account that owns the file can read it, which works as written.
  - See Minor N3 for one interaction with the App Password.
- **K4: ADDRESSED.** doc:451: "unblocked within ~1 min … 'resolved' … about 15 minutes later". This matches alerts.ts:27 `COOLDOWN_MS = 15 * 60_000`.
- **K5: ADDRESSED.** doc:451-452.
  - The delete command `npx wrangler r2 object delete lma-radio/state/budget.json --remote` is right:
    - wrangler's `r2ObjectDeleteCommand` takes the positional `{bucket}/{key}` (split by `validateAndReturnBucketAndKey`) and a `--remote` boolean (cli.js:353956-354000).
    - The bucket is `lma-radio` (wrangler.jsonc:13), and the key is `state/budget.json` (latch.ts:19, cloudstate.py:26).
  - Deleting the file is benign. An absent budget.json is neither `budget-unreadable` nor a raise (guard.ts:216-226).
  - It runs after the restore deploy, so it cannot re-trip at 5.5.
  - The stated rationale is correct: without the delete, `raise_budget` refuses a figure that is not above "the raise already in state/budget.json" (cloudstate.py:266-269).
  - Two new wording slips are listed below (N1, N2).
- **K6: ADDRESSED.** doc:195 lists the off-air page `offair.html`, JS/CSS and hls.js. This matches deploy-assets.mjs:26-32 (offair.html, player.js, nowplaying.js, style.css, assets/hls.min.js). "`index.html` is not uploaded" still holds.
- **K7: ADDRESSED.** doc:146 says "section 6.1 step 2". The H1 is "# Playout setup (phases 1 and 2)". No other "section 6 step" reference remains.
- **K8: ADDRESSED.** doc:436 is now an existence check: no `guard-write` alert, and the document exists. It says the create-only precondition is not observable from outside and that the Worker falls back to an unconditional put. This matches guard.ts:141-152 `writeGuard`, where a refused `createJson` falls back to `putJson`.
- **K9: ADDRESSED.**
  - Both items were removed from the `- [ ]` list. They now sit under "**Notes (expected, not pass/fail).**" after the checklist.
  - Section 7's two race bullets cross-reference each other ("(See also the next bullet.)" and "The same race: …").
  - The guard-cache claim matches deadclock.py, where a pre-upgrade cache says nothing (`return # a pre-upgrade cache`).
- **K10: ADDRESSED.**
  - doc:439: `curl -s -o /dev/null -w '%{http_code}\n' https://<host>/live.m3u8`. The syntax is correct and prints only the status.
  - doc:441: `/` is cached up to 60 s, `max-age=60`, which matches indexpage.ts:11 `INDEX_HTTP`. The doc gives about 2 min.
- **K11: ADDRESSED.** doc:463 uses `sudo systemctl revert transmitter@<user>`, then restart.
- **K12: ADDRESSED.** The blind item (doc:454) and the Rulesets item (doc:459) both tell the operator to have the real token at hand or be ready to roll it before overwriting.
- **K13: ADDRESSED.** In 6.2 (doc:349-350), Kill switch is step 5 again, as in the brief. Its step now names the Worker var `KILL_SWITCH_DESCRIPTION`. `STATION_NAME` moved to step 6.
- **K14: ADDRESSED.** Two notes were added:
  - after "remains the hard stop" (doc:211);
  - on the phase-1 checklist step that toggles the kill switch by hand (doc:253): do that step before phase 2, or use `transmitter offair on`.
- **K15: ADDRESSED.** doc:305 adds the fallback comment `sudo systemd-analyze verify transmitter@<user>.service`. Whether that fallback itself works is uncertain (see Out-of-scope).

### New breakage in the fix diff
None Critical or Important. Every item below fails safe (the station stays blocked or the alert is loud); none can leave the station unblocked while over budget.

- **Minor N1: doc:451 (K5).** "(or any figure above the projected one that `transmitter budget` shows)" is not enough on its own.
  - The trip test is actual ≥ 90% **or** projected ≥ 100% (pricing.ts:70-71, 113-114). A raise just above the projected figure can still trip on actual.
  - Example: actual ≈ $5.05 here. Any raise in ($5.50 floor, $5.61) is accepted by `--raise-to`, re-trips, and is consumed. Step 2 would then wrongly look like a failure.
  - Fix: "(or any figure above both the projected figure and actual ÷ 0.9)", or keep only "7".
  - The same gap was already in section 7's "Raise above the *projected* figure"; that is out of scope.
- **Minor N2: doc:452 (K5).** "Extra once-only 50% and 80% alerts at $5.50 and $7 are expected" overstates the case.
  - The levels use `max(actual, projected) / budget` (conditions.ts:29-34). At $5.50 both levels fire.
  - At $7, 80% fires only if max(actual, projected) ≥ $5.60, which is not guaranteed with actual ≈ $5.05.
  - Because the Step 3 rule stops the checkpoint on any spend-path failure, a missing "80% at $7" alert could be recorded as a failure.
  - Fix: "the 50% (and, if spend reaches $5.60, the 80%) alert at $7".
- **Minor N3: doc:379 (K3) interacting with doc:315.** Google shows an App Password as four groups of four letters with spaces.
  - Pasted that way, `SMTP_PASSWORD=abcd efgh ijkl mnop` is a valid systemd EnvironmentFile line.
  - The new `. /etc/transmitter/<user>.env` makes bash run `efgh` as a command, print "command not found", and leave `SMTP_PASSWORD` unset in the shell.
  - The R2 keys on other lines still load, so `offair`/`budget`/`status` still work. The operator just sees a confusing error during an incident.
  - Fix: in 6.1 step 3, "paste the App Password without spaces".
- **Minor N4: doc:200 (K2, the way back).** "then redeploy the Worker" does not say the redeploy must carry the real cron.
  - If the operator made the `"crons": []` edit in the committed `antenna/wrangler.jsonc`, a plain `npx wrangler deploy` PUTs an empty schedule again (cli.js:181133 → 164939). The Worker stays cron-less, and the hand-enabled rule is never reconciled.
  - This fails safe (dark, and hugo alerts dead-clock and guard-stale), but the way back silently does not happen.
  - Fix: "redeploy with the committed `wrangler.jsonc` (revert any `crons: []` edit); its output ends with `schedule: * * * * *`", which is section 4 step 2's own check.

### Out-of-scope observations
- **Broken-Worker order (doc:200).** An invocation already in flight when the trigger is removed can still reconcile, and could disable a rule enabled seconds later. Consider "wait a minute after the trigger is gone, enable the rule, and re-check it a minute later". This is not something the fix introduced.
- **K15 fallback.** As I recall systemd's `systemd-analyze verify` source, it handles a bare template path by instantiating it as `test_instance`, so the primary command probably works. A bare unit name, by contrast, is resolved against the cwd, so the fallback may need `cd /etc/systemd/system` or the full path `/etc/systemd/system/transmitter@<user>.service`. I could not verify this offline (no Debian 12 systemd here). It is not on the spend path.
- **Section 7 "Raise above the *projected* figure"** (pre-existing, from the brief's verbatim text) has the same gap as N1.

### Checks run
- **Brief Step 2 name grep:** 21 lines.
- **Brief Step 2 email grep:** **no output** (rc=1). I also scanned the fix diff's added lines for 32-hex strings and token-like strings of 40+ characters: none.
- **wrangler 4.149.0 source:** triggers default and validation (cli.js:26733, 29052), `resolveCronTriggers` (190885), the schedules PUT guard (164939), the main deploy passing `crons` (181133), and the `r2 object delete` definition (353956-354000).
- **Code cross-checks:**
  - guard.ts: `writeGuard` (141-152), budget read handling (210-226), reconcile and `waf-corrected` (283-306);
  - deadclock.py: in full (403 path, `forbidden_checks`, pre-upgrade cache);
  - cloudstate.py: `raise_budget` floors (250-275);
  - pricing.ts: thresholds;
  - conditions.ts: level alerts;
  - alerts.ts: `COOLDOWN_MS`;
  - indexpage.ts: `INDEX_HTTP`;
  - deploy-assets.mjs: the ASSETS list;
  - the systemd unit: EnvironmentFile and ExecStart.
- **Final doc read** at 1-4, 146, 195-211, 240-256, 300-350, 379-392 and 430-468.
- **Takeover flags** checked before writing: none present.
- No tests run (docs-only); no mutants.
