VERDICT: NEEDS FIXES

Scope: ea3ca04 (4ff1126..ea3ca04), docs/playout-setup.md only. I checked each claim against antenna/src/*.ts, antenna/wrangler.jsonc, antenna/scripts/deploy-assets.mjs, packages/transmitter/src/transmitter/*.py, packages/transmitter/systemd/transmitter@.service, and the installed wrangler 4.149.0 (antenna/node_modules). I deployed nothing, used no network, and ran no systemctl.

### Findings

#### Critical
None.

#### Important

**I1 (plan-mandated: brief edit 4, verbatim). The "broken Worker" fallback can leave the cron running, which then undoes the hand block.** Location: docs/playout-setup.md:200 (section 4 step 4); section 7 (line 378) points here.
- **What the doc says:** "or `npx wrangler triggers deploy` from a config with no crons".
- **What wrangler does:** in wrangler 4.149.0 a config without `triggers.crons` uploads **no** schedule, so the existing `* * * * *` stays in place.
  - The `triggers` default is `{ crons: void 0 }` (node_modules/wrangler/wrangler-dist/cli.js:26739).
  - `resolveCronTriggers` returns `config.triggers?.crons` (cli.js:190886).
  - `triggersDeploy` sends the schedules PUT only `if (crons)` (cli.js:164938-164941).
  - Only an explicit empty array, `"triggers": { "crons": [] }`, PUTs an empty schedule list. An empty array is truthy in JS.
- **What goes wrong:** the obvious way to make "a config with no crons" is to delete the `triggers` line. That leaves the cron running. The operator then enables the kill switch by hand, and a Worker that is still partly running (the guard's reconcile is its first step) disables it again within a minute. The paragraph's own "In that order" sentence exists to prevent exactly this.
- **Why it matters:** this is the last-resort manual block on the spend surface. There is no confirmation step, so the failure is silent apart from `waf-corrected`, which may not arrive if the alert path is the broken part.
- **Fix:**
  1. Say `"triggers": { "crons": [] }` explicitly. Deleting the key does not remove the cron.
  2. Add "confirm Workers & Pages → `antenna` → Settings → Trigger events lists no cron before enabling the rule".

**I2. The operator commands never say they need the R2 keys from the env file.** Locations: sections 4 step 4, 7 and 8 (lines 200, 378-381, 431-449).
- **What the doc says:** every operator lever is written as bare `transmitter offair on|off`, `transmitter budget [--raise-to]` and `transmitter status`.
- **What the code needs:** all of them call `_cloud` → `r2.make_client`, which raises `ConfigError("set R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY (the service's env file)")` (r2.py:17-20). After 6.1, those keys live only in `/etc/transmitter/<user>.env`.
  - The doc says to load the env file only for `fallback render` (line 138).
  - The venv's `bin/` is not on PATH either: the unit uses `/home/<user>/.venvs/transmitter/bin/transmitter`.
- **What goes wrong, followed literally on hugo:**
  - The checkpoint's first spend-path action, `transmitter offair on --reason test`, fails.
  - `transmitter status`'s cloud half degrades to `cloud unavailable: …`, so the expected `offair ON` / `killswitch enabled` lines cannot appear.
  - The failure is loud, not silent. But the off-air command is the main manual block, and its runbook should not depend on the operator working out the precondition during an incident.
- **Fix:** one sentence at the top of section 7, referenced from 4 step 4 and 8. Run the commands as `<user>` with `set -a; . /etc/transmitter/<user>.env; set +a` and with `~/.venvs/transmitter/bin` on PATH (or the full path).

#### Minor

**M1. Wrong alert title (the code wins).** Line 455 expects a "Kill switch toggled by hand" alert. The `waf-corrected` title is "Kill switch corrected" (guard.ts, the `waf-corrected` condition), so the subject is `llama radio: Kill switch corrected`. The other quoted titles match the code: "Station blocked: spend", "Station blocked: guard blind", "Kill switch not reconciled" and "Published lead below floor". The handback's "Deviations: None" missed this one because the title came from the brief.

**M2. "Resolved" timing contradicts itself.**
- Line 449 (spend item, step 2) reads as "within ~1 min … the station is unblocked and a 'resolved' message arrives".
- Section 7 (line 382) and alerts.ts `COOLDOWN_MS = 15 * 60_000` say the resolved notice comes about 15 minutes after the condition clears.
- An operator timing step 2 against ~1 min will record a false failure. Say "unblocked within ~1 min; 'resolved' about 15 min later". The blind item's "unblocks" (line 452) is fine.

**M3. The spend item leaves a test raise in place.**
- After step 3, `state/budget.json` still says $7, expiring at the period end (2026-11-11 here).
- It is harmless at base 15: `effectiveBudget` ignores a raise at or below the base (latch.ts), and `status` shows `ignored: not above the configured budget`.
- But re-running this item in the same period (for example after a fix) silently fails to trip. With the base at 5.5 the $7 raise is honoured, spend sits at about 71%, and nothing trips. Then `--raise-to 7` is refused as "above the raise already in state/budget.json" (cloudstate.py, `raise_budget`).
- Fix: add to step 3 "delete it: `npx wrangler r2 object delete lma-radio/state/budget.json --remote`", or at least note it.
- Also worth saying: expect extra once-only "spend at 50%/80%" alerts at $5.50 and $7, because the key carries the budget.
- Step 2's hard-coded 7 should read "7, or above the projected figure `transmitter budget` shows", matching section 7.

**M4. The section 4 step 3 parenthesis misses `offair.html`.** Line 195 says `deploy:assets` uploads "JS/CSS and hls.js". deploy-assets.mjs:27 also uploads `offair.html`. The extras said JS/CSS/hls.js only, but the code wins.

**M5. Two stale labels.**
- Line 146's "section 6 step 2" should be "section 6.1 step 2".
- The H1 still reads "# Playout setup (phase 1)".

**M6. The B1 check (line 430) cannot fail.**
- If the create-only put throws, `writeGuard` falls back to an unconditional put.
- If it returns false with the key still absent, `persist` retries with `pre = null` (guard.ts, `writeGuard`/`persist`).
- So "no `guard-write` alert and the document exists" passes whether or not `etagDoesNotMatch: "*"` works on production R2. Word it as an existence check, or say that the precondition's behaviour is not observable from outside.

**M7. Notes presented as checklist items.**
- "Overlapping cron runs" and "A pre-upgrade guard-cache.json" (lines 459-460) have no pass criterion, yet sit under "When every item passes". Make them notes.
- Section 7's two race bullets ("Overlapping cron runs" and "ENDLIST may lag a trip") describe facets of the same overlapping-invocation race. Merge them or cross-reference them.

**M8. Two commands in the off-air item don't show what they claim.**
- `curl -s https://<host>/live.m3u8 → 403` prints the body, not the status. Use `curl -s -o /dev/null -w '%{http_code}\n' …`.
- `/` is served with `max-age=60` (indexpage.ts `INDEX_HTTP`), so the off-air page can take about 2 min at the edge or in a browser cache, not ~1.

**M9. The broken-Worker procedure has no way back.**
- On redeploy, the guard reconciles the hand-enabled rule to its own state: it disables the rule and alerts `waf-corrected` unless tripped or off-air.
- Say: write `offair on` (Mac-side) **before** redeploying if the station should stay dark.
- Also say: while the hand block stands, expect hugo's `dead-clock` "403 although the guard says the station is not blocked" after about 17 checks (deadclock.py `forbidden_checks`).

**M10. Watchdog item: removing the override.** "Remove the override" is clearer as `sudo systemctl revert transmitter@<user>`, which deletes the drop-in and reloads. Deleting the drop-in by hand needs a `daemon-reload`.

**M11. The blind and Rulesets items overwrite live tokens.**
- They overwrite `CF_ANALYTICS_TOKEN` and `CF_WAF_TOKEN`. Secrets cannot be read back, and Cloudflare shows a token once.
- Say: have the real value at hand (or be ready to roll the token) before overwriting.
- Losing it fails closed, but the station stays blocked (blind), or the block stays cooperative-only (WAF).

### ⚠️ Cannot verify from diff
- **`sudo systemd-analyze verify /etc/systemd/system/transmitter@.service` on Debian 12 (systemd 252).** Whether verify accepts a bare template path could not be checked offline. If it errors, verify an instance instead: `systemd-analyze verify transmitter@<user>.service`.
- **Dashboard details:** the navigation (Workers & Pages → `antenna` → Settings → Trigger events; Notifications → Workers) and the token permission label "Zone · WAF · Edit".
- **The "~30 s player buffer" figure** in the already-playing item. It is not pinned in player.js. The handback also says it was taken from the brief.

### Strengths
- **No leftover test override weakens the guard.**
  - Each `--var` deploy starts from wrangler.jsonc, so overrides do not accumulate.
  - A forgotten restore is stricter, never looser: the budget stays at 5.5 or 7, blind-after stays at 15 min, the 60 s cadence adds only unbilled GraphQL reads, and the lead floor stays at 30.
  - Restoring the budget var also clears the 5.5 spend latch correctly (`applyAttempt` `raised`: 15 > 5.5, R3).
- **The blind item puts the secret before the `--var` deploy**, so the vars survive. The clamps admit 900 and 60 (guard.ts `clampedSeconds`).
- **The spend item's numbers hold:** 5.5 > the $5 base (`validBaseBudget`), 0.9 × 5.5 = 4.95 < $5, and 7 is above the 5.5 floor `raise_budget` computes.
- **Config table:** every key, default and bound matches `AlertsConfig` / `PublishConfig` / `AntennaConfig` and `DEFAULT_CONFIG_TOML`, including the `guard_check_minutes + 16` validator.
- **Cloud alert table:** keys, families, priorities and resolvable/once flags match `CLOCK_KEYS` / `GUARD_KEYS`, conditions.ts, guard.ts and clock.ts. The hugo `LEVEL_CODES` match alerts.py:33, and the event codes match service.py.
- **Status output:** the `transmitter status` / `budget` strings (`TRIPPED (spend)`, `CORRUPT (…)`, `offair     ON`, `offair     CORRUPT`, `killswitch enabled`, `honoured (period end unknown)`, `<label> unreadable: …`) match service.py `cloud_lines` and cloudstate.py.
- **Unit facts:** `Type=notify`, `WatchdogSec=45min`, `Restart=always`, the `EnvironmentFile` path and the `ExecStart` venv path all match transmitter@.service.
- **Other code facts:**
  - "10 checks" = deadclock.py `TROUBLE_CHECKS`.
  - The 403-after-17 rule = `forbidden_checks`.
  - The kill-switch allowlist (section 2 step 7) admits `/`, so the off-air-page check is right.
- **Public-repo hygiene is clean.** The only address-shaped strings are `alerts@lma-radio.com` (2) and `you@example.com` (2). There are no 32-hex IDs, IPs or token values.

### Checks run (each named risk and what I checked)
1. **Does "config with no crons" really remove the cron?** Read wrangler 4.149.0 cli.js: the triggers default (26739), `resolveCronTriggers` (190886), and `triggersDeploy`'s `if (crons)` PUT (164938). Absent crons means no PUT → I1.
2. **Is the spend item's budget accepted, and does it trip?** guard.ts `guardConfigFromEnv`/`validBaseBudget` (above 5, at most 100); pricing.ts `TRIP_ACTUAL` 0.9 and `baseUsd` 5.
3. **Do the raise floor and clear work?** cloudstate.py `raise_budget` floor logic; latch.ts `applyAttempt` (raised / newPeriod) and `effectiveBudget` (a raise at or below the base is ignored). This gave the leftover-budget.json re-run hazard → M3.
4. **Do blind-item clamps and timing hold?** guard.ts `clampedSeconds`; latch.ts `applyBlindRule`; conditions.ts `READING_WARN_MS`.
5. **Do alert titles, priorities and families match?** guard.ts and conditions.ts (each condition), clock.ts:231-339, alerts.ts `CLOCK_KEYS`/`GUARD_KEYS`/`COOLDOWN_MS` → M1, M2.
6. **Are the hugo alert codes and level semantics right?** alerts.py `LEVEL_CODES`/`_expired`; grep of `alert(`/`resolve(` across transmitter; service.py `_step` names.
7. **Are the dead-clock thresholds right?** deadclock.py `STALE_CHECKS`, `TROUBLE_CHECKS`, `forbidden_checks`, and the pre-upgrade cache branch.
8. **Do status strings match?** service.py `cloud_lines`; cloudstate.py `guard_summary` and `raise_status_line`.
9. **Do the operator commands need credentials?** cli.py `_cloud` → r2.py:17-20 → I2.
10. **Do the config defaults match?** config.py, the models and `DEFAULT_CONFIG_TOML`.
11. **Do the unit claims hold?** transmitter@.service in full.
12. **What does deploy:assets upload?** deploy-assets.mjs:27-31 → M4.
13. **Kill-switch PATCH, rule lookup and refusals:** waf.ts `killSwitch` and `reconcileKillSwitch`.
14. **index.html caching:** indexpage.ts `INDEX_HTTP` → M8.
15. **B1 verifiability:** guard.ts `writeGuard`/`persist` fallbacks → M6.
16. **Hygiene:** grep for email-shaped strings, 32-hex IDs, IPs and `token=`/`key=` in the diff.

No tests run (docs-only change; none needed).
