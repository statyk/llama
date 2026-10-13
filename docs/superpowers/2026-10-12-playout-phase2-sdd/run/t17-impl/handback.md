# t17-impl handback
Status: DONE. Commit ea3ca04 "docs(playout): phase-2 runbook (guard, alerts, systemd unit) and verification checklist". Only docs/playout-setup.md changed.

## Changes
- Intro: replaced the "Do not share ... phase 2 ships" sentence (brief edit 1).
- Section 3 step 5: first sentence added (edit 2).
- Section 4 step 3: parenthesis corrected to "JS/CSS and hls.js" (extras A); the "`index.html` is not uploaded" sentence added (edit 3); fresh-bucket note added. The local --dry-run mention is kept.
- Section 4 step 4: opening replaced verbatim (edit 4); the missing-fallback paragraph is kept.
- Sections 6-8 appended verbatim, plus the extras below.

## Extras placement
- A: section 4 step 3 (above).
- B1: section 8, "guard reads and prices usage" item: "confirm the first state/guard.json write succeeded ... onlyIf etagDoesNotMatch".
- B2: section 8, off-air item sub-bullet "kill-switch PATCH kept the rule whole".
- B3: section 7 known limitations "Overlapping cron runs" and a section 8 item.
- B4: section 8, already-playing item: "player buffer (~30 s) plus the 25 s stall watch ... record the measured time".
- B5: new section 8 item "site_url serves the playlist at its root".
- B6: section 8, off-air item sub-bullet "WAF block answers 403 ... alarms after 10 checks".
- B7: section 7 known limitation "A pre-upgrade guard-cache.json", plus a section 8 item.
- C: section 7 bullets for the status/budget reading guide, the corrupt guard.json raise refusal, and the 15-minute all-clear. Known limitations carry the guard-unknown note and the R2-outage/alerts.json note (merged into the "Cloud alerts need R2" bullet). STATION_NAME ASCII is in 6.2 step 5. The watchdog is in 6.1 step 5.
- D: new "7.1 Alert keys", both tables.
- E: 6.1 step 4, a config table (all [alerts] keys, [publish] guard_check_minutes, [antenna] site_url), the env secrets, and the guard_stale_minutes >= guard_check_minutes + 16 constraint. Defaults match DEFAULT_CONFIG_TOML. The config.py diff added AlertsConfig, the model validator, and the site_url comment; guard_check_minutes already existed.

## Deviations
None. Every cloud key, priority, resolvable/once flag and family was checked against alerts.ts, conditions.ts, guard.ts and clock.ts. CLOCK_KEYS and GUARD_KEYS match the tables. hugo LEVEL_CODES match (alerts.py:33). Event codes were found in service.py and deadclock.py. The unit file matches (Type=notify, WatchdogSec=45min, Restart=always, the venv ExecStart path).
I could not find a direct source for a few brief claims ("10 checks", ~30 s buffer); they are taken from the brief and extras text as written.

## Step 2 output
- Name grep count: 21 lines. Each secret/var appears in the doc and in code; KILL_SWITCH_DESCRIPTION and ALERT_REPEAT_HOURS are not mentioned in the doc (brief text does not mention them).
- Email grep: no output.
- config.py diff: reviewed (see E).

## Concerns
- Section numbering: the brief's text has two "6.x" subsections before "6.2 Tokens"; I added step numbers only, no new sections.
- The brief's "5 ." placement in section 3 step 5 puts the sentence inline at the start of the step.
# t17-fix1 handback
Commit: 01186ea docs(playout): runbook fix round 1 (K1-K15 from review) (docs/playout-setup.md only)
- K1: section 8 dashboard-toggle item now quotes "Kill switch corrected" (waf-corrected).
- K2: section 4 step 4: `"triggers": { "crons": [] }` (deleting the key does NOT remove the cron); confirm Trigger events lists no cron BEFORE enabling the rule; "The way back" (offair on first, guard reconciles on redeploy, dead-clock 403 after ~17 checks).
- K3: top of section 7: env-file/set -a and ~/.venvs/transmitter/bin/transmitter; referenced from section 4 step 4 and section 8 intro.
- K4: spend item step 2: unblocked ~1 min, "resolved" ~15 min later.
- K5: step 2 "or any figure above the projected one"; step 3 deletes state/budget.json; extra 50/80% alerts expected.
- K6: section 4 step 3 lists offair.html, JS/CSS, hls.js.
- K7: "section 6.1 step 2"; H1 "Playout setup (phases 1 and 2)".
- K8: B1 reworded as existence check; create-only precondition not observable, Worker falls back to unconditional put.
- K9: the two items removed from the checklist and moved to a "Notes (expected, not pass/fail)" paragraph; section 7 race bullets cross-referenced ("The same race").
- K10: curl -o /dev/null -w '%{http_code}' for the 403 check; / cached 60 s, ~2 min.
- K11: systemctl revert transmitter@<user>.
- K12: have the real token at hand in blind and Rulesets items.
- K13: STATION_NAME note moved to step 6 after the kill-switch step; KILL_SWITCH_DESCRIPTION named.
- K14: notes in section 4 (hard-stop paragraph) and the phase-1 checklist kill-switch step.
- K15: systemd-analyze verify fallback comment on the instance.
Greps: name grep 21 lines; email grep printed nothing.
