# Playout incident runbook

What each playout alert means, how urgent it is, and what to do. The setup
and the full operating reference are in `docs/playout-setup.md`; this file
links to its sections rather than repeating them. Alert keys are listed in
section 7.1 there.

## 1. How to read an alert

Alerts come from two places, and each one handles repeats differently.

| Source | Subject looks like | State file | Repeats while active | "resolved" message |
|---|---|---|---|---|
| **hugo** (`transmitter`) | `<station>: <code>` | `~/.transmitter/alerts.json` on hugo | at most once per 6 h (`[alerts] repeat_hours`), with "(N more since the last message)" | **level codes only**: `dead-clock`, `guard-stale`, `station-root`, `plan`, `render` |
| **cloud** (antenna Worker) | `<station>: <title>` | `state/alerts.json` in R2 | every 6 h (`ALERT_REPEAT_HOURS`) | every key except the three "once" keys (`budget-50…`, `budget-80…`, `budget-file-invalid`) and `waf-corrected`; it arrives **15 min** after the condition clears (cooldown) |

**Silence after the first message is not evidence of recovery.**

- **An alert that sends "resolved":** treat it as still broken until the
  "resolved" message arrives.
- **A hugo event alert** (`prune`, `publish`, `put-budget`, `horizon-held`,
  `frame-count-drift`, `publish-state`, `dead-clock-check`): you get
  one message, then nothing for 6 h even if it fires every minute. It never
  sends "resolved". The journal is the only place that shows whether it is
  still happening, because every fire is logged there:

  ```
  ssh hugo 'journalctl -u "transmitter@*" --since "-1h" --no-pager | grep ALERT | tail'
  ```

  No new line for the code in the last ~10 minutes means it has stopped.
  `transmitter status` does not answer this: it keeps an event code active
  until 6 h pass without a fire.
- **A second message for the same hugo event code** (with "(N more…)")
  means it has been firing for 6 h. Treat that as persistent.

## 2. First look, any alert

1. **Is the stream playing?** Open the player, or
   `curl -s https://listen.lma-radio.com/live.m3u8 | tail -3`. The newest
   segment number should advance about every 10 s.
2. **Overall state:** on hugo, as `<user>` with the env file loaded (section
   7 of `playout-setup.md`: `set -a; . /etc/transmitter/<user>.env; set +a`),
   run `transmitter status`. It shows the lead, the cost guard, the off-air
   flag, and active alerts on both hugo and the cloud.
3. **Is a hugo alert still firing?** Use the journal grep above.
4. **Cloud detail:** `cd antenna && npx wrangler tail` shows the Worker's
   log lines live.

## 3. Urgency at a glance

The runway: hugo keeps about 20–24 h of audio published ahead (`lead_hours`
24, refilled below `low_water_hours` 20). Most hugo failures stop **new**
audio being published without touching what is already up, so listeners
are unaffected until the lead runs out. `lead-low` fires at 16 h of lead
left (`LEAD_FLOOR_HOURS`).

| Urgency | Alerts |
|---|---|
| **Now: listeners affected or about to be** | `dead-clock`, `tripped-spend`, `tripped-blind`, `guard-state-corrupt`, `offair-corrupt`, `clock-inputs`, `clock-failed` (if it repeats), `guard-crashed`, `guard-unknown` (if it persists), `horizon-refused`, `offair-without-fallback` |
| **Today: will affect listeners within hours if ignored** | `frame-count-drift` (never recovers alone), `lead-low`, `put-budget`, `horizon-held`, `publish-state`, `station-root`, `plan`/`render` (if they persist), `publish` (if it persists), `guard-reading-failing`, `metronome-down` (if it persists), `waf-api` (while blocked), `guard-stale` |
| **When convenient: no listener impact** | `prune`, `dead-clock-check`, `index-write`, `budget-unreadable`, `budget-file-invalid`, `guard-write`, `waf-corrected`, `budget-50…`, `budget-80…`, `horizon-missing` (on a fresh start) |

## 4. hugo alerts

### `dead-clock` (level, has "resolved")
**Means:** hugo fetches `<site_url>/live.m3u8` every minute and it is wrong,
in one of three ways:
- stale (newest segment over 120 s old on 2 consecutive checks);
- answering 403 while the guard says the station is not blocked (17
  consecutive checks);
- unreachable (10 consecutive checks).

**Effect:** monitoring only; hugo keeps rendering and publishing. It means
listeners probably have a frozen or blocked stream.
**Do:**
- **Stale:** the antenna clock may have stopped. Check the Worker dashboard
  and `npx wrangler tail`. With the metronome on, a dead cron freezes the
  stream about 15 min after its last lease renewal (`playout-setup.md`
  section 9).
- **403:** the kill switch was probably left on. Check the WAF rule
  "station: kill switch"; if you enabled it by hand, see section 4 step 4.
- **Unreachable:** check the domain and DNS, and hugo's own network.

### `guard-stale` (level, has "resolved")
**Means:** hugo's copy of the cloud guard (`state/guard.json`) is unreadable,
or the guard last evaluated more than 45 min ago (it should every 15).
**Effect:** monitoring only. An unreadable guard is treated as blocked, so
hugo also pauses publishing.
**Do:** suspect the antenna clock (same checks as a stale `dead-clock`). It is
expected right after upgrading transmitter before antenna (section 6 intro).

### `station-root` (level, has "resolved")
**Means:** hugo cannot read the station folder (NFS share not mounted,
`.station-root` marker missing, or the folder unlistable).
**Effect:** planning stops, so no new shows are added. Publishing continues,
and the existing lead keeps playing.
**Do:** check the NFS mount on hugo and that `<root>/.station-root` exists
(section 3 step 2). It resolves on the next successful plan step.

### `plan` / `render` (level, has "resolved")
**Means:** the plan or render step threw an unexpected error (the message
carries the exception).
**Effect:** that step makes no progress; publishing continues. It retries
every minute.
**Do:** if a "resolved" follows within a few minutes, nothing. If not, read
the traceback in the journal
(`journalctl -u "transmitter@*" --since "-1h" | grep -A20 "step failed"`).
The lead buys hours, and `lead-low` is the backstop.

### `frame-count-drift` (event, no "resolved") — needs a restart
**Means:** the AAC encoder's output no longer matches the frame-count model
the timeline relies on.
**Effect:** **latched.** Filling (plan and render) stops for good until
transmitter restarts. Publishing continues, so the stream plays out the
existing lead and then runs dry. The alert disappears from `status` after 6 h,
**but the halt does not**.
**Do:** check what changed (an ffmpeg upgrade, an unusual source file), then
`sudo systemctl restart transmitter@<user>`. If it fires again right after
the restart, stop and investigate rather than looping restarts.

### `publish` (event, no "resolved")
**Means:** a publish pass failed. The cause is in the message:

| Message | Meaning | Do |
|---|---|---|
| `PUT <key> failed after 4 attempts` | R2 refused or was unreachable; retried next minute | journal grep: still firing after ~10 min → check R2 status; otherwise nothing |
| `PUT <key> failed: … AccessDenied / InvalidAccessKeyId / NoSuchBucket / SignatureDoesNotMatch` | credentials or bucket wrong; retrying cannot help | fix `R2_ACCESS_KEY_ID`/`R2_SECRET_ACCESS_KEY` in the env file or the bucket config, restart |
| `no fallback rendered: run transmitter fallback render first…` | nothing at all is published until a fallback exists | `transmitter fallback render <loop> [--notice <file>]` |
| `horizon: …` | segments uploaded but the horizon PUT failed; retried next pass | as for a failed PUT |
| `site: …` | show pages/timeline failed; the stream itself advanced | low priority; check after it persists |
| `PublishError: published state belongs to epoch X, not Y…` | the epoch changed under the published state; this is a deliberate re-render-everything operation | stop: work out why the epoch differs before doing anything |

**Effect:** the batch stops, the horizon does not advance past what failed,
and the next minute retries. The lead covers short outages.

### `prune` (event, no "resolved")
**Means:** deleting old segments failed (`DELETE <key> failed`), the horizon
rewrite before the deletes failed (`horizon: …`), or `fallback.json` was lost
(`stopped: no-fallback`).
**Effect:** none on air. The horizon is moved past old segments **before**
they are deleted, so nothing points at them. Publishing is unaffected.
**If a delete keeps failing:** prune stops at the first failure and retries
that key every pass, so nothing behind it is deleted (about 1.4 GB/day of
leftover segments). The horizon is also rewritten every minute instead of
every ten (about +1,300 PUTs/day, within the 17,500 daily budget). Waiting
6 h for the repeat costs nothing that matters, and a few days is survivable.
**Do:**
- **One message, then silence in the journal:** nothing. R2 had a bad
  minute (2026-10-15: two failures on one key, then it cleared). To confirm,
  `publish.json`'s first `runs` entry should start past the failed segment:
  `ssh hugo 'python3 -c "import json; print(json.load(open(\"/home/$USER/.transmitter/publish.json\"))[\"runs\"])"'`.
- **Still firing:** check the Cloudflare status page for R2, then delete the
  key by hand from the Mac:
  `cd antenna && npx wrangler r2 object delete lma-radio/<key> --remote`.
  The next pass carries on by itself. A restart does not help: prune retries
  the same key.
- **`stopped: no-fallback`:** `transmitter fallback render <loop>`.

### `put-budget` (event, no "resolved")
**Means:** hugo's own cap of 17,500 PUTs per UTC day (`[publish]
daily_put_budget`) was reached.
**Effect:** publishing and pruning stop until 00:00 UTC; rendering
continues. Normal use is about 8,900/day, so hitting it means something is
re-sending (for example a `horizon-held` streak).
**Do:** find what spent it (`horizon-held` alerts, journal) before raising
anything. It resumes by itself at midnight UTC. If the lead will not last
until then, raise `daily_put_budget` in `config.toml` and restart.
`transmitter offair` and `budget --raise-to` are not subject to this cap.

### `horizon-held` (event, no "resolved")
**Means:** 3 consecutive publish passes could not advance the horizon
because a batch is below the high-water mark. Each pass re-sends the same
batch and spends PUT budget.
**Do:** compare `high_water` in `~/.transmitter/publish.json` with `last` in
R2's `state/horizon.json`. Left alone, this burns toward `put-budget`.

### `publish-state` (event, no "resolved")
**Means:** `~/.transmitter/publish.json` cannot be read.
**Effect:** fail-closed: hugo plans, renders, publishes and prunes **nothing**
(and skips the dead-clock check) until it is readable.
**Do:** inspect and repair or restore the file. Do not hand-write values you
cannot verify against R2's `state/horizon.json`.

### `dead-clock-check` (event, no "resolved")
**Means:** the dead-clock monitor itself threw. This is not `dead-clock`.
**Effect:** one minute's check skipped.
**Do:** nothing unless it persists; then read the traceback in the journal.

## 5. Cloud alerts (antenna Worker)

While the station is **blocked** (tripped or off-air), the clock writes an
ENDLIST playlist (players stop), serves the off-air page, enables the WAF kill
switch, and hugo pauses publishing. "Resolved" arrives about 15 min after the
condition clears.

### Spend guard

| Key | Means | Effect | Do |
|---|---|---|---|
| `budget-50:…` / `budget-80:…` | peak of actual/projected spend reached 50% / 80% of the monthly budget ($15 incl. $5 base, period starts day 11) | none; sent once per period and budget | look at `transmitter budget`; find what is spending if it is early in the period |
| `tripped-spend` | actual ≥ 90% or projected ≥ 100% of budget | **station blocked**, latched | policy is to stay down on overrun. To come back: `transmitter budget --raise-to <usd>` (must exceed the projected figure AND actual/0.9; max $100; see section 7), or wait for the new period |
| `tripped-blind` | no successful usage reading for 6 h | **station blocked**; clears by itself at the first good reading under the thresholds | fix the cause: `last_error` in `transmitter budget` (analytics token, `CF_ACCOUNT_ID`, Cloudflare API outage). With the metronome on, a dead metronome makes readings fail; roll it back (section 9) |
| `guard-reading-failing` | readings have failed for 1 h | none yet; becomes `tripped-blind` at 6 h | as for `tripped-blind`, within the next 5 h |
| `guard-state-corrupt` | `state/guard.json` cannot be parsed | treated as a spend trip: **station blocked**, and the trip persists after the file is fixed | `transmitter budget --raise-to <usd>` (it refuses while readings also fail: wait for one), or the new period |
| `offair-corrupt` | `state/offair.json` is not a valid flag | treated as **off-air** until rewritten | `transmitter offair on --reason "…"` or `transmitter offair off` |
| `guard-unknown` | the clock could not read its state from R2 | that minute writes **nothing**: players stall on the stale playlist | self-heals next minute; if it persists, check R2 status. Can also appear from a harmless race between overlapping runs |
| `guard-crashed` | the guard step threw | same as `guard-unknown`: nothing written that minute | if it repeats, `npx wrangler tail` for the exception; consider a rollback deploy |
| `guard-write` | saving `state/guard.json` failed | the decision still stands this minute; re-derived next run | nothing unless it persists |
| `budget-unreadable` | `state/budget.json` is not JSON or unreadable | a raise cannot apply; the configured budget is used | rewrite with `transmitter budget --raise-to <usd>`, or delete the file |
| `budget-file-invalid` | a raise in `state/budget.json` is rejected (e.g. expires after the period end) | raise ignored; sent once | re-raise with `transmitter budget --raise-to <usd>` |
| `waf-api` | the kill-switch rule could not be set | while blocked, the block is cooperative only (ENDLIST + off-air page); after unblocking, the switch may stay on and 403 (→ hugo `dead-clock` after 17 checks) | check `CF_WAF_TOKEN`/`CF_ZONE_ID` and that the rule exists exactly once (section 6.2 step 5). Retries every minute |
| `waf-corrected` | the kill switch differed from the guard's decision (someone toggled it in the dashboard) and was corrected | none; never "resolved" | use `transmitter offair` instead of the dashboard (section 4 step 4) |

### Clock

| Key | Means | Effect | Do |
|---|---|---|---|
| `clock-inputs` | the horizon or fallback index could not be read | **no playlist written** that minute; players stall | self-heals if transient; if it persists, check R2 status |
| `clock-failed` | an invocation threw (e.g. a failed playlist PUT) | that minute's playlist may be missing | one is noise; repeats → `npx wrangler tail` |
| `horizon-missing` | `state/horizon.json` absent or not JSON | no playlist written | expected before the first publish; otherwise check hugo's `publish` alerts |
| `horizon-refused` | the horizon's segment length is not 10.24 s | **nothing written**, metronome stopped at once | hugo published a wrong horizon: stop and investigate on hugo; do not edit the constant |
| `lead-low` | published audio ahead is under 16 h | none yet; at zero the stream runs out | expected after a fresh start. Otherwise hugo has stopped publishing: check hugo for `put-budget`, `frame-count-drift`, `publish-state`, `station-root`, `plan`/`render`, `publish`, `horizon-held` |
| `offair-without-fallback` | off-air but no usable fallback | ENDLIST-only playlist; players stop with no notice | `transmitter fallback render <loop> [--notice <file>]` |
| `metronome-down` | the Durable Object metronome missed its renew, refused a lease, or stalled | the stream keeps playing on cron's own loop (the older, less punctual timing) | brief: nothing. Persists: roll back with `npx wrangler deploy --var METRONOME:off`, then commit `"METRONOME": "off"` (section 9) |
| `index-write` | writing `index.html` failed | the page is stale; the stream is unaffected | nothing unless it persists |

## 6. Procedures

- **Run a `transmitter` command on hugo:** as `<user>`,
  `set -a; . /etc/transmitter/<user>.env; set +a`, then
  `~/.venvs/transmitter/bin/transmitter …`.
- **Restart transmitter:** `sudo systemctl restart transmitter@<user>`; check
  with `systemctl status transmitter@<user>` and the journal.
- **Take the station off the air / back on:** `transmitter offair on --reason "…"`
  / `transmitter offair off`. With hugo down, or the Worker broken, follow
  `playout-setup.md` section 4 step 4. **Never toggle the kill-switch rule in
  the dashboard while the Worker runs**: the guard undoes it.
- **Delete one R2 object by hand:** from `antenna/`,
  `npx wrangler r2 object delete lma-radio/<key> --remote`.
- **Roll the metronome back:** `npx wrangler deploy --var METRONOME:off`,
  then commit `"METRONOME": "off"` in `antenna/wrangler.jsonc` so the next
  plain deploy keeps it off (section 9).
- **A show is being re-voiced by emcee** (an `emcee move` or `[assign.artists]`
  rule changed its profile): nothing to do on hugo. transmitter does not
  see emcee's profile check, so the package keeps airing its old voicing; an
  already-encoded row keeps its stored encode, a planned unencoded row whose
  package changes is re-planned in place, and a package caught mid-re-voice
  (DJ blocks cleared) is ineligible and planned around until the re-voice
  lands. A re-voice cannot cause `LayoutError` (that comes only from an
  on-air row whose encode is missing). A re-voice that FAILS leaves the
  package off the pool until a later `emcee run` or `emcee voice <show>`
  succeeds.
- **Render the fallback:** `transmitter fallback render <loop> [--notice <file>]`.
