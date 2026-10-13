# Task 17 fix round 1 — all findings to fix (orchestrator ruling: fold everything; docs only, the code wins)

Full reviews: $D/t17-rev-spec/handback.md and $D/t17-rev-qual/handback.md (read both; they carry the code references).

K1 (spec Important / quality M1). Section 8 "A dashboard toggle is undone and alerted": the alert title is "Kill switch corrected" (guard.ts, waf-corrected), not "Kill switch toggled by hand". Fix the quoted title (and anywhere else it appears).

K2 (quality I1, plan-mandated brief edit 4 — RULED: fix, the code wins over the brief's text). Section 4 step 4 "broken Worker" procedure: "`npx wrangler triggers deploy` from a config with no crons" leaves the cron running when `triggers` is merely deleted (wrangler sends the schedule PUT only when `crons` is set). Say explicitly `"triggers": { "crons": [] }` (deleting the key does NOT remove the cron), and add "confirm Workers & Pages → antenna → Settings → Trigger events lists no cron BEFORE enabling the rule". Add the way back (quality M9): before redeploying the Worker, write `offair on` (Mac-side state/offair.json) if the station should stay dark — on redeploy the guard reconciles the hand-enabled rule (disables it and alerts waf-corrected unless tripped/off-air); and while the hand block stands, expect hugo's dead-clock 403 alert after ~17 checks.

K3 (quality I2 — RULED: fix). The operator commands (`transmitter offair|budget|status`) need R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY, which after 6.1 live only in /etc/transmitter/<user>.env, and the venv bin is not on PATH. Add one sentence at the top of section 7 (referenced from section 4 step 4 and section 8): run them as `<user>` with `set -a; . /etc/transmitter/<user>.env; set +a` and `~/.venvs/transmitter/bin/transmitter` (or that bin on PATH). (Reading the env file needs root or the file's owner: say so if relevant — it is owned by <user>, mode 600.)

K4 (quality M2). Spend item step 2: "unblocked within ~1 min; the 'resolved' message about 15 min later" (section 7's cooldown).

K5 (quality M3). Spend item: step 2 "`--raise-to 7` (or above the projected figure `transmitter budget` shows)"; step 3 also deletes the test raise: `npx wrangler r2 object delete lma-radio/state/budget.json --remote` (otherwise a re-run of this item in the same period never trips and `--raise-to 7` is refused); note that extra once-only 50%/80% alerts at $5.50 and $7 are expected (the key carries the budget).

K6 (spec M1 / quality M4). Section 4 step 3: deploy:assets uploads offair.html, JS/CSS and hls.js (deploy-assets.mjs:27) — not index.html.

K7 (quality M5). "section 6 step 2" → "section 6.1 step 2" (line ~146); H1 "# Playout setup (phase 1)" → reflect phases 1–2.

K8 (quality M6). B1 check: word it as an existence check of the first state/guard.json (no guard-write alert, document present); say the create-only precondition itself is not observable from outside (the Worker falls back to an unconditional put).

K9 (quality M7). "Overlapping cron runs" and "pre-upgrade guard-cache.json" are notes, not pass/fail items: move them out of the checklist items (a "Notes" list under section 8, or section 7 only). Merge or cross-reference section 7's two race bullets ("Overlapping cron runs", "ENDLIST may lag a trip").

K10 (quality M8). Use `curl -s -o /dev/null -w '%{http_code}\n' https://<host>/live.m3u8` for the 403 check; say `/` is cached up to 60 s (max-age=60), so the off-air page can take ~2 min at the edge/browser.

K11 (quality M10). Watchdog item: remove the override with `sudo systemctl revert transmitter@<user>`.

K12 (quality M11). Blind and Rulesets items: have the real token value at hand (or be ready to roll the token in the dashboard) before overwriting the secret — secrets cannot be read back.

K13 (spec M3). 6.2: restore the brief's numbering — put the STATION_NAME ASCII note after the kill-switch step (step 6) instead of before it; optionally name the Worker var `KILL_SWITCH_DESCRIPTION` in the kill-switch step.

K14 (spec M4). Section 4's kept paragraph ("the WAF kill switch … remains the hard stop") and the phase-1 checklist step that toggles the kill switch by hand: add a short note that after phase 2 is deployed the guard reconciles the rule every minute, so a hand toggle is undone and alerted (use offair / section 4 step 4's broken-Worker order instead).

K15 (quality ⚠️). 6.1 step 2: after `systemd-analyze verify` of the template, add "if it rejects the bare template path, verify the instance: `sudo systemd-analyze verify transmitter@<user>.service`".

Rules: docs/playout-setup.md only; run nothing against the account or network; no --dry-run of anything; re-run the brief's Step 2 greps (email grep must print nothing); commit by explicit path.
