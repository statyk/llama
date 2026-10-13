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
