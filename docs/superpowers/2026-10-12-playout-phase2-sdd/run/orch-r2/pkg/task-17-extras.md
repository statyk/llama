# Task 17 — required additions beyond the brief's verbatim text (orchestrator ruling, binding)

The brief's text goes in verbatim (edits 1–4 and sections 6–8). In addition, the runbook MUST carry everything
below. Put each item where an operator will meet it: a checklist item goes in section 8 (as its own `- [ ]`
item or as a sub-bullet of the matching item), an operating fact goes in section 6 or 7. Keep placeholders
literal; no account ID, zone ID, token, key or email address except `alerts@lma-radio.com`.

## A. Fix section 4 step 3 (docs/playout-setup.md ~line 195)
It still says deploy:assets uploads the "player page, off-air page". Since R8 `index.html` belongs to the clock
(both pages are bundled into the Worker); deploy:assets uploads JS/CSS/hls.js only. Correct the parenthesis
(the brief's edit 3 adds the "`index.html` is not uploaded" sentence — make the two agree). Also add: on a
FRESH bucket run deploy:assets before or alongside the Worker deploy (the clock's index.html references
player.js, style.css and hls). Do not change or remove the existing mention of the local
`deploy-assets.mjs --dry-run` print; do not RUN any --dry-run yourself.

## B. Section 8 checklist — operator-checkpoint items (add each)
1. Confirm the FIRST `state/guard.json` write succeeds on production R2 (its create-only conditional put,
   `onlyIf: { etagDoesNotMatch: "*" }`, was verified only in miniflare).
2. Confirm the kill-switch PATCH keeps the rule whole (after an off-air on/off, the rule's expression, action
   and description in the dashboard are unchanged; only `enabled` toggled).
3. Known window (ruling 14): when overlapping cron runs race, a one-minute unblocked window is possible; the
   trip is never lost, the next run re-blocks, and it is alerted. (Section 7 known limitations.)
4. On the "already-playing page shows the notice" item: end-to-end latency on an already-playing page is
   about the player buffer (~30 s) plus the 25 s stall watch, so it can exceed RF5's "~45 s"; record the
   measured time.
5. Confirm `[antenna] site_url` serves `live.m3u8` at its root (the dead-clock check fetches
   `<site_url>/live.m3u8`).
6. Confirm the WAF block answers **403** on the R2 custom domain; any other status counts as "unreachable"
   and alarms after 10 checks.
7. After the upgrade, a pre-upgrade `guard-cache.json` without the `guard_evaluated_at` key is treated as
   unknown (no false `guard-stale`): note it as expected.

## C. Section 7 — operating facts (add each)
- Every all-clear ("resolved"), including `tripped-spend` after `--raise-to`, arrives about 15 minutes after the
  condition clears (it must stay clear for the 15-minute cooldown first).
- `guard-unknown` can also appear when the guard did return a known outcome (a race); never describe it as
  "unknown outcome only".
- An R2 outage reading `state/alerts.json` silences cloud alerts that minute; hugo's dead-clock check is the
  cover (the brief's known-limitations bullet covers part of this — make it say so).
- `STATION_NAME` (Worker var) must be ASCII (it goes into the raw ntfy Title header).
- While `guard.json` is corrupt and readings fail, `transmitter budget --raise-to` refuses (no period known)
  even though the `guard-state-corrupt` alert recommends a raise: wait for the next successful evaluation.
- `transmitter status` / `budget` reading guide: a `CORRUPT (…)` guard line means the clock treats the document
  as a spend trip; `offair CORRUPT` means the clock treats the station as off the air; `<doc> unreadable: …`
  lines state the clock's reading; a raise shows whether the Worker honours it (`honoured`, `expired`,
  `ignored: …`, or `honoured (period end unknown)` when the period end cannot be read).
- The watchdog (section 6.1): transmitter pings systemd after every step, every publish batch, every batch of
  prune deletes and every show encode. After restoring `~/.transmitter` WITHOUT `cache/`, the first publish
  recomputes analyses for ~48 h of shows and may meet `WatchdogSec`; the service restarts and continues (each
  analysis is cached as it completes; at most one batch, ≤360 segments, is re-PUT per kill, within the daily
  PUT budget).

## D. Alert keys — add a subsection (e.g. "7.1 Alert keys") with BOTH tables, complete:

Cloud (antenna, state/alerts.json; "guard" family resolves whenever the guard returned a known outcome,
"clock" family only on a complete invocation; a key in neither family is treated as clock):

| key | family | priority | kind |
|---|---|---|---|
| tripped-spend | guard | urgent | resolvable |
| tripped-blind | guard | urgent | resolvable |
| budget-50:<period>:<budget> | guard | default | once per period and budget |
| budget-80:<period>:<budget> | guard | high | once per period and budget |
| guard-reading-failing | guard | high | resolvable |
| guard-unknown | guard | high | resolvable |
| budget-unreadable | guard | high | resolvable |
| offair-corrupt | guard | high | resolvable |
| budget-file-invalid | guard | high | once |
| guard-state-corrupt | guard | urgent | resolvable; its "resolved" text says the spend trip stays |
| waf-api | guard | high | resolvable (ids redacted in alert text) |
| waf-corrected | guard | high | sent on appearance, never "resolved" |
| guard-write | guard | high | resolvable |
| guard-crashed | clock | urgent | resolvable |
| index-write | clock | high | resolvable |
| clock-inputs | clock | urgent | resolvable |
| horizon-missing | clock | default | resolvable |
| horizon-refused | clock | urgent | resolvable |
| lead-low | clock | high | resolvable |
| offair-without-fallback | clock | high | resolvable |
| clock-failed | clock | urgent | resolvable |

hugo (transmitter, ~/.transmitter/alerts.json, R16):
- Level codes (active until resolved): `dead-clock` and `guard-stale` (resolved by the monitor),
  `station-root` and `plan` (by a successful plan step), `render` (by a successful render step).
- Event codes (re-sent at most every `repeat_hours`; drop off once `repeat_hours` pass without a new fire):
  `publish`, `prune`, `publish-state`, `put-budget`, `horizon-held`, `frame-count-drift`.
VERIFY every key and its priority/kind against the code before committing (antenna/src/alerts.ts,
guard.ts, conditions.ts, clock.ts; packages/transmitter/src/transmitter/alerts.py, service.py, deadclock.py):
the doc must match the code; if a key or attribute differs, the CODE wins — report each difference under
"Deviations".

## E. Config keys — document every transmitter config key added on this branch
Run `git diff ccf0f16..HEAD -- packages/transmitter/src/transmitter/config.py` and document every new key
(at least `[alerts]` email_to, email_from, smtp_host, smtp_port, ntfy_url, repeat_hours, dead_clock_seconds,
guard_stale_minutes, and any new `[publish]`/`[antenna]` keys such as guard_check_minutes / site_url) with its
default and meaning, plus the env-file secrets SMTP_USERNAME, SMTP_PASSWORD (a Gmail App Password) and
NTFY_TOKEN, and R4's constraint `guard_stale_minutes >= guard_check_minutes + 16`. Defaults must match
DEFAULT_CONFIG_TOML.
