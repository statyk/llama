### Task 17: Runbook, deploy, phase-2 verification — HUMAN CHECKPOINT

**Model hint:** sonnet

**Files:**
- Modify: `docs/playout-setup.md`
- Create (by the operator's results, at the checkpoint): `docs/superpowers/2026-10-1X-playout-phase2-verification.md` (X = the day it is run)

**Interfaces:**
- Consumes: every name above, namely:
  - the secrets `CF_ACCOUNT_ID`, `CF_ZONE_ID`, `CF_ANALYTICS_TOKEN`, `CF_WAF_TOKEN`, `NTFY_URL`, `NTFY_TOKEN`, `ALERT_EMAIL_FROM` and `ALERT_EMAIL_TO`;
  - the vars `MONTHLY_BUDGET_USD`, `BILLING_ANNIVERSARY_DAY`, `GUARD_EVAL_SECONDS`, `BLIND_AFTER_SECONDS`, `KILL_SWITCH_DESCRIPTION`, `LEAD_FLOOR_HOURS`, `ALERT_REPEAT_HOURS` and `STATION_NAME`, and the committed `send_email` binding `ALERT_EMAIL`;
  - `npx wrangler deploy`, with `--dry-run` and `--var`;
  - transmitter's `[alerts]` keys and env `SMTP_USERNAME` / `SMTP_PASSWORD` / `NTFY_TOKEN`;
  - the commands `transmitter offair|budget|status`;
  - the unit `transmitter@<user>.service`.
- Produces: the operator runbook for phase 2 and its verification checklist. No code. The implementer writes the doc and commits it. **The deploy and every checklist item are the operator's, at the checkpoint (Step 3).**

- [ ] **Step 1: Edit `docs/playout-setup.md`**

Make these edits, keeping every placeholder literal (`<host>`, `<user>`, `<repo>`, `<your-topic>`, `you@example.com`, `<zone>`). No real address, ID or token may appear; the one exception is the alert sender `alerts@lma-radio.com` (Stakes).

1. In the intro, replace "**Do not share the station publicly until phase 2 (the cost guard) ships.**" with "**Do not share the station publicly until the phase-2 checklist (section 8) passes.**"
2. In section 3, step 5, add as the first sentence: "Phase 2 replaces this transient unit with the system unit in section 6 step 2; follow that instead on an existing install."
3. In section 4, step 3, add: "`index.html` is not uploaded: the clock writes it, the player page normally and the off-air page while the station is blocked."
4. In section 4, step 4, replace the opening ("Off-air by hand …" through "… and back.") with the text below. Keep the paragraph that follows it, about a missing fallback and the ENDLIST-only playlist.

   "Off-air: `transmitter offair on --reason \"…\"` / `transmitter offair off` (section 7). Within about a minute the clock serves the notice and ENDLIST, swaps `index.html` to the off-air page and enables the kill switch, and reverses all three after `off`. **If hugo is down**, write the flag from the Mac instead: from `antenna/`, put `{"offair": true, "reason": "…", "since": "<iso>", "until": null}` in `offair.json` and run `npx wrangler r2 object put lma-radio/state/offair.json --file offair.json --content-type application/json --remote` (`"offair": false` to come back). The guard honours the file within a minute, exactly as if `transmitter offair` had written it. Do **not** toggle the kill-switch rule in the dashboard: the guard reconciles it every minute, undoes the toggle and alerts `waf-corrected`. **If the clock Worker itself is broken** (nothing reconciles, so neither lever acts), first remove the Worker's cron trigger (dashboard: Workers & Pages → `antenna` → Settings → Trigger events; or `npx wrangler triggers deploy` from a config with no crons), then enable the kill-switch rule by hand. In that order: a Worker that is still running would undo the rule within a minute."
5. After section 5, append sections 6–8 exactly as below.

````markdown
## 6. Phase 2: the cost guard, alerts and the service

The guard runs in the clock Worker. It reads the account's usage every 15 minutes and prices it (budget $15 a month, including the $5 Workers Paid base). It **blocks** the station (ENDLIST playlist, off-air `index.html`, the WAF kill switch) when actual spend reaches 90% or projected spend reaches 100%, or when it has had no successful reading for 6 hours. It alerts at 50% and 80%. `transmitter offair on` blocks the station too. Design: `docs/superpowers/specs/2026-10-09-playout-design.md` ("Cost guard", "Alerts and operations").

The billing period starts on day 11 of each month, 00:00 UTC (the committed var `BILLING_ANNIVERSARY_DAY`). Upgrade transmitter and antenna in either order. If transmitter is upgraded first, hugo alerts `guard-stale` until antenna is deployed (no guard has evaluated yet): expected.

### 6.1 transmitter on hugo

1. `cd <repo> && git pull && ~/.venvs/transmitter/bin/pip install -e packages/transmitter`.
2. **System unit.** It replaces the phase-1 `systemd-run --user` unit:
   ```
   systemctl --user stop transmitter                       # the phase-1 transient unit
   sudo install -d -m 755 /etc/transmitter
   sudo install -m 600 -o <user> -g <user> <env file> /etc/transmitter/<user>.env
   sudo cp <repo>/packages/transmitter/systemd/transmitter@.service /etc/systemd/system/
   sudo systemd-analyze verify /etc/systemd/system/transmitter@.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now transmitter@<user>
   systemctl status transmitter@<user>                      # active (running)
   journalctl -u transmitter@<user> -f                      # ALERT lines appear here
   ```
   The unit expects the venv at `/home/<user>/.venvs/transmitter`; edit `ExecStart` in the copied file if yours differs. It is `Type=notify` with `WatchdogSec=45min` and `Restart=always`, and it starts at boot (`sudo loginctl enable-linger` is no longer needed for it).
3. **Alerts.** Add to `<env file>`, which is `/etc/transmitter/<user>.env` from now on (mode 600, owned by `<user>`):
   ```
   SMTP_USERNAME=you@example.com
   SMTP_PASSWORD=<a Google App Password: Google Account -> Security -> 2-Step Verification -> App passwords>
   NTFY_TOKEN=<optional ntfy access token>
   ```
   and to `config.toml`:
   ```
   [alerts]
   email_to = "you@example.com"
   ntfy_url = "https://ntfy.sh/<your-topic>"
   ```
   `[antenna] site_url` must be set: the dead-clock check fetches `<site_url>/live.m3u8` once a minute. Then `sudo systemctl restart transmitter@<user>`.

### 6.2 Tokens and email (dashboard)

1. **WAF token.** My Profile → API Tokens → Create Token → Custom token. Permissions: *Zone · WAF · Edit*. Zone resources: *Include · Specific zone · <zone>*. Keep the token for 6.3.
2. **Analytics token.** The existing *Account Analytics: Read* token (phase 1).
3. **Zone ID.** The zone's overview page → API → *Zone ID*.
4. **Email.** Email Routing must be enabled on the zone, with the destination address verified (phase 1). The sender is `alerts@lma-radio.com`, on the zone's domain. The `send_email` binding `ALERT_EMAIL` in `wrangler.jsonc` is unrestricted: it can only reach the account's verified destinations, and the one the Worker uses is the `ALERT_EMAIL_TO` secret (6.3), so the destination never enters the repo.
5. **Kill switch.** The custom rule *"station: kill switch"* (section 2 step 7) must exist **exactly once**, with action Block. The guard finds it by that description and refuses to touch it if it is missing, duplicated or not a Block rule.

### 6.3 antenna

From `antenna/`, with `.env` holding `CLOUDFLARE_ACCOUNT_ID`:

1. Secrets (each command prompts for the value; nothing is echoed or committed):
   ```
   npx wrangler secret put CF_ACCOUNT_ID
   npx wrangler secret put CF_ZONE_ID
   npx wrangler secret put CF_ANALYTICS_TOKEN
   npx wrangler secret put CF_WAF_TOKEN
   npx wrangler secret put NTFY_URL                    # https://ntfy.sh/<your-topic>
   npx wrangler secret put NTFY_TOKEN                  # optional
   npx wrangler secret put ALERT_EMAIL_FROM            # alerts@lma-radio.com
   npx wrangler secret put ALERT_EMAIL_TO              # the verified destination (its only copy)
   npx wrangler secret list
   ```
2. `npm ci && npm test`, then `npx wrangler deploy --dry-run` and check the output (it bundles and lists the bindings, `ALERT_EMAIL` among them). Then `npx wrangler deploy`.
3. `ANTENNA_BUCKET=lma-radio npm run deploy:assets` (the player's stall watch is in `player.js`/`nowplaying.js`).
4. Within two minutes, `npx wrangler r2 object get lma-radio/state/guard.json --remote --pipe` shows the following. `transmitter status` shows the same picture from hugo.
   - `evaluated_at` recent, `last_error: null`;
   - an `evaluation` with `actual_usd` ≈ 5 plus usage, and `budget_usd: 15`;
   - `waf.enabled: false`, `waf.error: null`;
   - `evaluation.unknown_action_types: []`.
5. Optional second channel for a dead clock: Notifications → Add → Workers → the Worker-error alert for `antenna`.

## 7. Operating

- **Take the station off the air / back on:** `transmitter offair on --reason "…" [--until <iso>]` / `transmitter offair off`. These work while the guard is tripped and whatever the daily PUT budget says. With hugo down, write `state/offair.json` from the Mac; with the clock Worker broken, remove its cron trigger, then enable the kill switch by hand (both in section 4 step 4).
- **The guard tripped for spend:** it clears only in the next billing period, or after `transmitter budget --raise-to <usd>`. Either way it clears only if the guard's next evaluation is under the thresholds. `transmitter budget` shows the guard's state. A raise must exceed the current budget and may not exceed $100. It expires at the period's end. Raise above the *projected* figure `transmitter budget` shows, or the next evaluation re-trips and consumes the raise. A `state/budget.json` that expires after the current billing period is ignored and alerted (`budget-file-invalid`); `transmitter budget --raise-to` always writes the period's end. The station's policy is to shut down on overrun, not to keep raising.
- **Tripped "blind"** (no reading for 6 h): fix the cause (analytics token, `CF_ACCOUNT_ID`, a Cloudflare API outage; see `last_error` in `transmitter budget`). The first successful reading under the thresholds clears it.
- **Alerts.** Cloud alerts come from the clock Worker (ntfy + email). hugo alerts come from transmitter (email + ntfy). Each repeats every 6 h while active and says "resolved" when a latch or outage clears. The 50% and 80% spend alerts come once per billing period (and budget). A dashboard toggle of the kill switch is undone and alerted (`waf-corrected`). `transmitter status` lists both sets; a hugo event alert (a publish error, the PUT budget) drops off once 6 h pass without a new one.
- **Known limitations.**
  - *VLC at a fallback→live switch.* At a fresh run — the first start, an outage longer than the published lead, or a re-epoch — `EXT-X-DISCONTINUITY-SEQUENCE` restarts at 0. hls.js and Safari follow it; VLC goes silent and needs stop/play once.
  - *Cloud alerts need R2.* While R2 itself is unreadable, the cloud cannot send alerts (their state lives in R2); hugo's dead-clock check is the channel for that case. An invocation whose guard could not read its state (`blocked: null`) may still try to read `state/alerts.json`.
  - *ENDLIST may lag a trip.* With two invocations overlapping right after a trip, the ENDLIST playlist can lag by up to about a minute. That matters only while the WAF API is also failing (a cooperative-only block).
  - *`lead-low` on a fresh start.* A fresh run (first start, or a restart after an outage longer than the lead) builds its lead from zero, so `lead-low` fires and later resolves while the lead grows (about 10 minutes of encoding per show on hugo). That alert is expected after a fresh start and needs no action.
  - *A future-dated budget raise.* If `state/budget.json`'s `written_at` is ahead of the Worker's clock (hugo's clock skewed ahead), the guard re-evaluates every minute until that time passes. Those are GraphQL reads, which are not billed; NTP on hugo keeps the window to seconds.

## 8. Phase-2 verification checklist

Run with the station up and **not yet shared**. Record each result (date, observation) in `docs/superpowers/<date>-playout-phase2-verification.md`. Restore the normal deploy (`npx wrangler deploy`, with no `--var`) after each item that changes it.

- [ ] **The guard reads and prices usage.** `guard.json` → `evaluation`: compare `period_to_date` with the dashboard's R2 and Workers metrics for the period (sampled; expect agreement within a few percent). `unknown_action_types` is `[]`; otherwise record the strings.
- [ ] **Off-air blocks fully and comes back.** `transmitter offair on --reason test`. Within ~1 min:
      - `curl -s https://<host>/live.m3u8` → 403 (kill switch);
      - the dashboard shows the kill-switch rule enabled;
      - `curl -s https://<host>/` → the off-air page;
      - `transmitter status` → `offair ON`, `killswitch enabled`.

      Then `transmitter offair off`. Within ~1 min everything reverses and players can tune in again. Repeat once with the Mac-side write of `state/offair.json` (section 4 step 4) in place of `transmitter offair`.
- [ ] **An already-playing page shows the notice** (amendment A2). Play in Chrome and in Safari, then `transmitter offair on`. Each page shows "The station is off the air." with *Try again* within about a minute (the buffer drains, then two probes 10 s apart). VLC stops on ENDLIST. Then `offair off`.
- [ ] **A network blip shows no notice.** While playing in Chrome, toggle the Mac's Wi-Fi off for ~20 s, then on. The page says "Reconnecting…" while stalled, never the off-air notice, and resumes (or needs one *Play*).
- [ ] **A spend trip and a raise.**
      1. `npx wrangler deploy --var MONTHLY_BUDGET_USD:5.5`. Within 15 min (the next evaluation), the actual $5+ is ≥ 90% of $5.50, so you see:
         - an urgent ntfy and email "Station blocked: spend";
         - the station blocked as above;
         - `transmitter budget` → `TRIPPED (spend)`.
      2. `transmitter budget --raise-to 7`. Within ~1 min the raise triggers an evaluation; it is under the thresholds, so the station is unblocked and a "resolved" message arrives.
      3. Restore: `npx wrangler deploy` (the budget is back to 15; the $7 raise is below it and ignored).
- [ ] **A blind trip.**
      1. Set `CF_ANALYTICS_TOKEN` to a wrong value (`npx wrangler secret put CF_ANALYTICS_TOKEN`), then `npx wrangler deploy --var BLIND_AFTER_SECONDS:900 --var GUARD_EVAL_SECONDS:60`. About 15 min after the last success the station blocks with "Station blocked: guard blind", and `guard.json` `last_error` names the failure.
      2. Restore the real token. The next evaluation unblocks the station.
      3. Restore the deploy.
- [ ] **A dashboard toggle is undone and alerted.** Enable the kill-switch rule in the dashboard while the station is on air. Within ~1 min it is disabled again and a "Kill switch toggled by hand" (`waf-corrected`) alert arrives.
- [ ] **A Rulesets failure.** Set `CF_WAF_TOKEN` to a wrong value. Within ~1 min a "Kill switch not reconciled" alert arrives, and `guard.json` `waf.error` is set. With `offair on` at the same time, `live.m3u8` is the ENDLIST playlist and `/` is the off-air page (the block is cooperative). Restore the token: the rule is enabled within a minute, then `offair off`.
- [ ] **Lead floor.** `npx wrangler deploy --var LEAD_FLOOR_HOURS:30`: a "Published lead below floor" alert arrives within a minute. Restore.
- [ ] **A dead clock.** Workers & Pages → `antenna` → Settings → Trigger events → delete the cron trigger. Within ~3 min hugo sends `dead-clock` (email + ntfy). Within about an hour it sends `guard-stale`. Restore with `npx wrangler deploy`; both send "resolved".
- [ ] **The watchdog.** `sudo systemctl edit transmitter@<user>` → `[Service]` `WatchdogSec=2min`. Then `sudo systemctl kill -s STOP transmitter@<user>`. Within ~2 min the journal shows a watchdog timeout and the service restarts. Remove the override, restart the service, and reboot hugo once to see it come back by itself.
- [ ] **Cron lag, 24 h** (carried from phase 1): median, p99, max, and the count over 25 s, from the phase-1 capture.
- [ ] **Cron lag plus guard time, 24 h** (Task 18's input): from a day of phase-2 clock lines, the median, p99 and max of `lagMs` and of `lagMs + guardMs`, and the count with `lagMs + guardMs` over 25 s, together with the Task 18 decision.
- [ ] **A week of op counts** (carried from phase 1, due 2026-10-18), now with the guard's own reads and writes: compare with `guard.json`'s `period_to_date`.

When every item passes, the station may be shared publicly (spec, Phases item 2).
````

- [ ] **Step 2: Check the doc against the code**

Run: `grep -nE "CF_ACCOUNT_ID|CF_ZONE_ID|CF_ANALYTICS_TOKEN|CF_WAF_TOKEN|BILLING_ANNIVERSARY_DAY|NTFY_URL|ALERT_EMAIL_(FROM|TO)|MONTHLY_BUDGET_USD|BLIND_AFTER_SECONDS|GUARD_EVAL_SECONDS|LEAD_FLOOR_HOURS|transmitter@" docs/playout-setup.md | wc -l`
Expected: each name appears, matching `antenna/src/guard.ts`, `antenna/src/alerts.ts`, `antenna/src/clock.ts`, `antenna/wrangler.jsonc`, `packages/transmitter/src/transmitter/config.py` and `packages/transmitter/systemd/transmitter@.service`. Then:

Run: `grep -nE "[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}" docs/playout-setup.md | grep -v "example\.\(com\|org\|net\)\|alerts@lma-radio\.com"`
Expected: no output (only placeholder addresses and the alert sender).

Commit:

```bash
git add docs/playout-setup.md
git commit -m "docs(playout): phase-2 runbook (guard, alerts, systemd unit) and verification checklist"
```

- [ ] **Step 3: HUMAN CHECKPOINT. The operator deploys and verifies (orchestrator: stop and escalate).**

The orchestrator stops here and reports to the parent. The parent explains the material to the operator before asking, following `explain-human-test-procedures`.

What the operator does, in order:
1. Section 6: transmitter, then tokens and email, then antenna.
2. Section 8: every checklist item.
3. A day later, the clock-line summary that Task 18's checkpoint needs.

What each part checks:
- **Spend path:** the guard's metering, pricing and latch, and the blocking reconciliation.
- **Cloud alerts:** ntfy and email delivery.
- **hugo side:** dead-clock, the watchdog and status.
- **Phase-1 findings:** the player stall (VLC at a fresh run is a documented limitation, amendment A1).

How to report: paste the results into the verification file. The template has one row per item: Item | Result (pass / fail / partial) | Observation (times, alert subjects, any deviation).

Failures:
- **On the spend or blocking path** (guard, latch, WAF, `offair`): stop. Do not share the station. Bring the failure back as a fix task.
- **Anywhere else:** record it and continue.

---

