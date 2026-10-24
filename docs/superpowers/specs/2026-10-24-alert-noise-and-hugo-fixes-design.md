# Alert noise, the hugo ntfy relay, and two hugo service fixes

Date: 2026-10-24. Branch `alert-noise`, worktree `.claude/worktrees/alert-noise`,
based on `725b38c` (the phase-2 verification doc, not yet on main).

## Kickoff

- **Review mode: Opus.** Spec, plan and final branch reviewers run on Opus.
- **Stakes.** This is the alerting and service loop of a live, unattended radio
  station (antenna on Cloudflare, transmitter on hugo). Nothing here deletes or
  rewrites user data. What it can break: (a) an alert the operator needs never
  arrives, or arrives late; (b) the transmitter service loop stalls, crashes or
  restart-loops; (c) new R2 traffic. **Strict surfaces:** the spend and off-air
  alerts (`tripped-spend`, `tripped-blind`, the budget levels, `put-budget`,
  `guard-state-corrupt`, `offair-corrupt`) must never be gated, delayed or
  silenced; a gate must never be able to silence a one-shot key forever; the
  new monitor thread must never write to R2 (it reads only); the Worker's new
  R2 write must stay within the existing spend bounds (class A is at 52% of
  the free tier, see `docs/superpowers/2026-10-23-playout-phase2-verification.md` L2).

## Why

1. **Alert noise.** Single transient blips page at high priority. The 10-23
   triage found that every `waf-api` alert lands at :00/:30, each one a single
   5 s WAF API timeout at Cloudflare's busy minute, then "resolved" 15 min
   later (11 episodes since 10-21). **Operator rule (Shawn): any check that runs
   about every minute needs 3 consecutive failures before it alerts.**
2. **antenna's ntfy never works.** ntfy.sh limits an account with no paid tier
   per IP, like an anonymous sender, and Workers share egress IPs, so the daily
   quota is always spent (429 `42908`) whatever `NTFY_TOKEN` says. The operator
   will not pay for a tier. hugo's ntfy works (its own home IP). So hugo relays
   antenna's alerts to ntfy; the Worker keeps email and drops ntfy.
3. **hugo's dead-clock check is starved (J2).** `DeadClockMonitor.check` runs
   inside the sequential service tick after plan, render and publish
   (`service.py` `Runner.tick`). On 10-23 a plan step analysing shows over NFS
   ran ~17 min and `dead-clock` arrived at 00:34:43Z instead of ~00:22Z.
   `guard-stale` is in the same call.
4. **The plan step never feeds the watchdog (K1 follow-up).** Render
   (`pipeline.py:273`) and publish (`service.py:148`) ping `WATCHDOG=1` inside
   long steps; `plan_step` does not. A fill analysing several new shows over NFS
   could pass `WatchdogSec=45min` and cause a spurious (self-healing, but noisy)
   restart.
5. **Runbook corrections** found by the §8 run (listed in Part 5).

## Goals

- Every check on the approved list sends (first alert or repeat) only on a
  streak of 3 consecutive failing observations; every other existing key
  behaves exactly as today.
- antenna alerts reach the operator's phone through hugo's ntfy.
- `dead-clock` and `guard-stale` are detected on time whatever plan/render do,
  and a stalled monitor thread is itself alerted.
- A long plan step keeps the watchdog fed.
- `docs/playout-setup.md` (§6, §7.1, §8) and `docs/playout-incident-runbook.md`
  describe the new behaviour; CLAUDE.md's antenna secret list is updated.

## Non-goals

- Player auto-retry (deferred by the operator to the post-phase-3 player polish).
- Changing any existing debounce (`dead-clock`'s 2/10/17, `guard-stale` 45 min,
  `guard-reading-failing` 1 h, `horizon-held` 3, `lead-low`). Do not stack the
  new gate on them.
- A paid ntfy tier, Telegram, or Gmail-push alternatives (considered, rejected).
- Changing alert titles, priorities, repeat intervals or the 15-min cooldown.

## Anti-goals (a failure even if it "works")

- A one-shot or latch key that can never fire because the gate swallowed it.
- A spend or off-air alert that is delayed by even one minute.
- The relay paging the operator with alerts older than `RELAY_MAX_AGE` after
  hugo was down, or re-sending the same antenna alert every minute.
- The monitor thread masking a hung main loop (it must not feed the watchdog).
- Any new R2 PUT from hugo's monitor thread, or an R2 write per minute from the
  Worker in steady state (a key failing in alternate minutes is the accepted
  exception, see Limits).

## Part 1. The 3-consecutive gate

### Key inventory (operator-approved 2026-10-23)

**antenna** (`antenna/src/alerts.ts` and the raise sites):

| Key | Treatment |
|---|---|
| `waf-api`, `guard-unknown`, `guard-write`, `budget-unreadable`, `index-write`, `clock-inputs`, `clock-failed`, `guard-crashed`, `horizon-missing` | **gated at 3** |
| `metronome-down` from its immediate branches (renew threw / timed out; the DO answered a play lease wrongly) | **gated at 3** |
| `metronome-down` from the stall branch (`STALLS_FALLBACK` = 2 consecutive stalled renews) | **sent at once** (already debounced) |
| `waf-corrected`, `budget-50/80:*`, `budget-file-invalid` | sent at once (single-minute or `once`: a gate would silence them forever) |
| `tripped-spend`, `tripped-blind`, `guard-state-corrupt`, `offair-corrupt` | sent at once (deliberate off-air latches) |
| `horizon-refused` | sent at once (a config error that never self-clears) |
| `guard-reading-failing`, `lead-low` | unchanged (already debounced) |
| `offair-without-fallback` | unchanged (not on the approved list; a lasting state) |

**transmitter** (`packages/transmitter/src/transmitter/alerts.py` and callers):

| Code | Treatment |
|---|---|
| `prune`, `publish`, `publish-state`, `station-root`, `plan`, `render`, `dead-clock-check` | **gated at 3** |
| `put-budget` | sent at once (spend is the strict surface) |
| `frame-count-drift` | sent at once (it latches `halted`; it fires once) |
| `monitor-stalled` | sent at once (new; debounced by its own 5-min threshold, Part 3) |
| `dead-clock`, `guard-stale`, `horizon-held` | unchanged (already debounced) |

`GATE = 3` is a named constant on each side, not config.

### Semantics (both sides)

An **observation** of a key is one run of the code that can raise it:

- antenna: one invocation whose batch is allowed to clear the key
  (`clearedIn(key, batch)`), or any invocation in which the key is present.
- transmitter: one service tick, aggregated across its steps, for the tick
  codes; one monitor pass, its own observation, for `dead-clock-check`.
  Within a tick a gated code advances if ANY step raised it; it resets only if
  EVERY step that can raise it ran this tick and none raised it; otherwise it
  is unchanged. Repeated fires within a tick count once (`publish-state` is
  read twice per tick; `publish` can fire from both `_report_stop` and the
  step handler when prune throws). The steps that can raise each code: plan →
  `plan`, `station-root`; render → `render`, `station-root`; publish →
  `publish`, `prune`; the lead read → `publish-state`. The caller (the Runner,
  the monitor loop) ends each observation explicitly; the Dispatcher does not
  infer tick boundaries from `fire` calls.

Rules:

1. A gated key present in an observation advances its **streak** by one.
2. A gated key absent from an observation that could have raised it (the
   antenna batch could clear it; on transmitter, every step that can raise it
   ran) **resets** its streak to 0.
3. A gated key absent from an observation that could NOT have raised it (an
   incomplete antenna batch; plan/render on a tick that is not filling) neither
   advances nor resets.
4. Any send of a gated key, first alert or repeat, requires its current streak
   to be at least `GATE`; "resolved" is never gated. Streaks are therefore
   tracked for every gated key, active or not.
5. Where a new episode would start (antenna's new-alert branch,
   `!e || !e.active || clearing elapsed`; transmitter's "not active or expired"
   branch), while the streak is below 3 nothing is sent and the key is NOT
   active (not listed by `transmitter status`, not in the cloud `alerts` line,
   not relayed). On the 3rd consecutive observation the episode starts and is
   sent as today (first message, repeats every `repeat_hours`, "resolved" for
   resolvable/level keys).
6. Inside an active episode, presence and absence keep today's meaning (a
   return inside antenna's clearing window is continuing, a transmitter event
   code keeps deduping until `repeat_hours`, level codes resolve on success),
   except that a due repeat is sent only under rule 4. So a single blip inside
   an active episode never sends a repeat.
7. The first message of a gated episode says it followed 3 consecutive
   failures (wording is the builder's).

### antenna specifics

- Streaks are persisted in `state/alerts.json` (every invocation is a fresh
  isolate). A pending-only entry is `active: false` and must be
  distinguishable from a cleared entry; it is **dropped** (not kept for
  `KEEP_INACTIVE_MS`) when rule 2 resets it. A key that already has a kept,
  inactive entry from an earlier episode keeps that history while pending.
- **Pending over a still-active entry** (clearing elapsed): while the return is
  pending, the old entry stays exactly as it is and may finish clearing (and
  send "resolved") normally; when the streak reaches `GATE` the new episode
  replaces it as today. A test pins this.
- Writing alerts.json while a streak is pending costs one PUT per minute for at
  most the 2 pending minutes per episode; acceptable. The stored streak stops
  changing once it reaches `GATE`, so a steady active episode adds no writes.
  A key failing in alternate minutes is the exception (see Limits).
- `dispatchAlerts` currently assumes every sent key is active and every planned
  entry is real; a pending entry is neither sent nor active.
- The metronome stall branch must be distinguishable at the raise site
  (`clock.ts` `renew` → `fallbackReason`); a condition-level flag that bypasses
  the gate is the suggested mechanism. Builder's call how, but the set of gated
  keys must be one reviewable list in `alerts.ts`, pinned by a test next to
  `classifies every key the guard and the clock raise`.
- Overlapping invocations (deploy overlap, double cron fire) may advance a
  streak twice in one minute. Accepted: it can only shorten the gate to ~2 min.
- **Runway note.** `clock-inputs`, `clock-failed` and `guard-crashed` mean
  "live.m3u8 was not written by cron this minute". While the metronome's
  Durable Object writes from its 15-min lease, a 3-minute gate is safe. But
  cron's own loop runs only when the DO is already judged down, so with
  `METRONOME` "on" `clock-failed` then means cron, the only writer, failed;
  with `METRONOME` off (the rollback) cron is always the only writer. In both
  cases the 3-minute gate exceeds the ~123 s player runway. hugo's
  `dead-clock` needs ~3–4 min (2 stale checks over 120 s), so it is not
  faster; it is the independent cover. See the open question below.

### transmitter specifics

- The gate lives in `Dispatcher` (`alerts.py`), before the send decision;
  `entry["count"]` resets on every send, so it cannot be the streak counter.
- Event codes have no success signal today (`_report_stop` returns silently on
  success). Rule 2's reset is therefore driven by the caller, per the
  aggregation rule above: the Runner tells the Dispatcher which steps ran and
  ends the tick's observation; the monitor loop ends each pass's. `HeldTracker`
  is the in-process precedent.
- Required test: in one tick plan raises `station-root`, then render succeeds
  without scanning; the `station-root` streak advances (it is not reset).
- Streaks are in-process (reset by a restart). A service that restarts more
  often than every 3 ticks would never alert a gated code. A crash-looping
  service is surfaced by antenna's `lead-low` (hours later), as today; startup
  crashes never alerted, so this is not a regression. Persisting streaks in
  `alerts.json` would not change that.

## Part 2. antenna → hugo ntfy relay

### antenna side

- Remove the Worker's ntfy channel (`ntfyChannel`, the `NTFY_URL`/`NTFY_TOKEN`
  env, its tests). The operator deletes both Worker secrets after deploy
  (`npx wrangler secret delete NTFY_URL`, `... NTFY_TOKEN`).
- Add a **relay channel**: its `send` appends the outgoing message to a new R2
  object, **`state/alert-relay.json`**: a random `stream` id plus a bounded
  ring (the last 50 messages) of `{seq, at, key, kind, priority, title,
  message}`, `seq` strictly increasing within the stream. Title and message
  pass through `redact` (with the same secrets as email) BEFORE they are
  written: this text leaves the account via hugo.
- The Worker generates a fresh `stream` whenever it creates or recreates the
  object. The first write is create-only (etag precondition), falling back to
  an unconditional put when the store refuses the precondition, as
  `createAlerts` does. Later writes are etag-conditional; a lost race is
  re-read and retried once, then the channel throws (a channel failure, logged
  as today). An unparseable object is overwritten unconditionally (over its
  etag) with a fresh stream, and the overwrite is logged.
- A relay write that succeeds counts as a delivery (like email), so an episode
  whose email failed but whose relay write succeeded is not re-sent next
  minute. Email and relay are independent channels; either alone delivers.
- R2 cost: one class-A PUT per sent message (alert, repeat, resolved). With
  the gate in place that is a handful a day.
- Why a separate object, not fields in `alerts.json` (my call): `alerts.json`
  has no priority or message, its entries are rewritten every minute while
  anything is pending or clearing, and a retried send would look like a new
  message. A message log with a stream id and a sequence number lets hugo keep
  a cursor and send each message once.

### hugo side

- Each monitor pass (Part 3) GETs `state/alert-relay.json` (one class-B read a
  minute, ~43k/month, inside the free tier) and sends qualifying messages to
  hugo's **ntfy channel only** (email already went from the Worker), bypassing
  the Dispatcher's dedupe (antenna already deduped). The relay uses its own
  ntfy channel instance and does not share the Dispatcher's per-channel
  cool-down.
- **Cursor:** hugo's cursor is `(stream, seq)`, persisted in `~/.transmitter/`
  (a new small file). A message is sent when it is above the cursor in the
  document's current stream AND younger than `RELAY_MAX_AGE` (1 h, a
  constant). No cursor file, or a stream different from the cursor's, means
  cursor `seq` 0 in the document's stream. `RELAY_MAX_AGE` is what prevents
  backlog storms; older messages are skipped with one log line.
- **ntfy refusals:** the cursor advances past each message ntfy accepts, and
  past one it refuses with a 4xx other than 429 (one WARNING log with the
  status). On 429, 5xx or a transport error the pass stops and the message is
  retried next pass.
- Formatting: title `<station>: [resolved: ]<title>` (the station name is the
  existing `[antenna] station_name`), body = message. Priority: urgent→5,
  high→4, default→3, resolved→3. Tags are passed explicitly (e.g. an optional
  `tags` argument on `NtfyChannel.send`), matching antenna: urgent
  `rotating_light`, high `warning`, default `information_source`, resolved
  `white_check_mark`. A default-priority alert must never carry the check
  mark. A visible marker that the alert came from antenna is the builder's
  call.
- A missing object is "nothing to relay" (the cursor stays); an unreadable or
  malformed one is a WARNING log, never a crash and never an alert (a relay
  failure is not a station failure; email covers it).
- With no ntfy configured on hugo, the relay is off (one startup warning).

## Part 3. The dead-clock monitor off the tick (J2)

- `DeadClockMonitor.check` and the relay run in **their own loop on a
  dedicated thread**, every 60 s, independent of plan, render and publish.
  `Runner.tick` no longer calls the monitor.
- The monitor thread **never pings the watchdog**: the watchdog must keep
  meaning "the main loop is alive".
- **Its own guard view.** Each monitor pass GETs `state/guard.json` and
  `state/offair.json` itself and builds the same view `DeadClockMonitor.check`
  takes today (`blocked`, `offair`, `error`, `guard_evaluated_at`). It never
  reads or writes `guard_cache_path`: that file stays publish's spend control,
  written only by `publish.guard_blocks_publishing`. Why: on its own thread
  the monitor would otherwise read a cache refreshed only by the main loop, up
  to 15 min plus a whole tick old, which raises false `guard-stale` and false
  403 `dead-clock` alerts during long fills. Cost: 2 class-B GETs a minute
  (~86k/month, under 1% of the 10M allowance). `forbidden_checks` and every
  other debounce stay unchanged (the fresher view only makes the 403 branch
  more accurate).
- **R2 client:** the monitor has its own read-only R2 client for the guard
  reads and the relay, created on the main thread before the thread starts and
  used only by the monitor thread (boto3 clients are thread-safe once made;
  creating one concurrently from the default session is not). The monitor
  makes no R2 writes.
- **Order within a pass:** the dead-clock check (with its guard reads) first,
  then the relay in its own try. A failure of the dead-clock check fires the
  gated event code `dead-clock-check` (Part 1) and the loop goes on. A relay
  failure is a WARNING log only, never `dead-clock-check` and never an alert.
- **Watching the thread:** the main tick checks the monitor's last completed
  pass (counting from the thread's start until its first pass). When it is
  more than 5 min old, or the thread is not alive, the tick fires the level
  code `monitor-stalled`, sent at once (the 5-min threshold is its debounce);
  the main tick resolves it once passes are fresh again.
- **Thread safety:** `Dispatcher.fire`/`resolve` do a read-modify-write of
  `~/.transmitter/alerts.json` and touch `_mem`/`_failed` and the streaks; both
  threads now call them, so the Dispatcher takes a lock. The module-level
  `alerts.alert`/`resolve` keep their never-raise contract.
- **Shutdown:** the thread is stopped by an event set when `Runner.run` exits
  (its `finally`, before or after `STOPPING=1`), and joined with a short
  timeout; it must not keep the process alive (daemon) and must not hold the
  Dispatcher lock across network I/O longer than a send already does.
- `transmitter run --once` runs one full monitor pass (dead-clock check, then
  relay) on the main thread after the tick; it starts no thread and so makes
  no `monitor-stalled` check. With the gate, `--once` can never page a gated
  code (it logs at ERROR); that is intended for a manual command.
- `DeadClockMonitor`'s own debounce (stale 2, unreachable 10, 403 17) and the
  guard-stale timing are unchanged.

## Part 4. The plan step feeds the watchdog (K1)

- `plan_step` takes an optional `notify` like `render_step`, and the analysis
  path pings `WATCHDOG=1` after each show analysis (`Station.frames_of` /
  `Station.extend` → `planner.extend`'s `frames_of`). `Runner.tick` passes its
  notify.
- That bounds the gap between pings to one analysis (~8 min each on 10-23),
  not one fill.
- `row_analysis` inside publish (a lost `cache/`) is a known, documented gap
  (its docstring); leave it unless the ping is trivial to add there too.

## Part 5. Runbook and docs

`docs/playout-setup.md`:

- §6.1/§6.3/§7: antenna has no ntfy; its pushes come via hugo's relay; hugo
  needs `[alerts] ntfy_url` for them; the Worker secret commands for
  `NTFY_URL`/`NTFY_TOKEN` become delete instructions for an existing deploy.
- §7.1: which keys are gated at 3, which are sent at once, the relay, and
  every item under Limits below.
- §8, from the verification doc:
  - **K:** edit → restart → STOP; every `journalctl` under `sudo`; expect
    ~2.5 min. A `systemctl edit` `WatchdogSec` drop-in does NOT reach a running
    service (measured 10-23).
  - **J:** expect `dead-clock` ~17–18 min after cron actually stops, plus up to
    ~15 min of dashboard propagation (9 min measured).
  - **B2:** the `off the air` grep always matches (a hidden div in the normal
    page); test something only the off-air `index.html` carries.
  - **A2:** Worker requests are read on the billing page, which lags ~1 day
    behind `guard.json`; there is no Workers & Pages graph.
  - **C1:** unmeasurable until the player shows a position (phase 3).
  - Check while editing that the phase-1 corrections are folded in: the Free
    plan's rate limit is path-only, the workers.dev prerequisite, Cache Rule
    labels, the new dashboard paths.
- Add relay verification steps (one antenna alert reaches ntfy via hugo; a
  gated key does not page on a single failure).

`docs/playout-incident-runbook.md`: per-key notes for gated keys ("3 consecutive
minutes"), `monitor-stalled`, and the relay. CLAUDE.md: drop
`NTFY_URL`/`NTFY_TOKEN` from antenna's secret list and mention the relay and
the gate in one line each.

## Limits (stated in the runbook, §7.1)

- A gated key failing in alternate minutes never alerts (the operator's
  consecutive rule), and antenna writes `alerts.json` about once a minute
  while it does (within the spend bounds).
- During an R2 write outage a pending antenna streak cannot be saved, so the
  gated keys that report it (`guard-write`, `index-write`, `clock-failed`)
  stay silent, and an ungated alert goes by email only (its relay write
  fails). During an R2 read outage antenna sends nothing at all, as today
  (dispatch reads `alerts.json` first). hugo's `dead-clock` is the cover in
  both.
- Pushes arrive up to ~1 min after antenna's email.
- hugo down means no relay; email covers it. If email also fails while hugo is
  down (or its ntfy is failing), the relay write still counts as a delivery,
  so the alert is not re-sent until `repeat_hours`.
- A lost cursor file can re-send up to an hour of relayed messages, once.

## Deploys (operator, after merge)

1. Worker: `cd antenna && npx wrangler deploy --dry-run`, then `npx wrangler
   deploy`; then delete the `NTFY_URL` and `NTFY_TOKEN` secrets.
2. hugo: update the checkout, reinstall transmitter, `sudo systemctl restart
   transmitter@<user>`.
   Order does not matter: before hugo updates, `state/alert-relay.json` simply
   accumulates, and on first start hugo sends only messages younger than
   `RELAY_MAX_AGE`, so nothing older pages.

## Left to the builder

- Data-structure shapes (streak and pending fields on `AlertEntry`, the relay
  document layout beyond the fields listed, the cursor file's name).
- The mechanism by which steps declare their gated codes (which step can raise
  which code is fixed in Part 1).
- Message wording for gated first alerts and relayed alerts.
- Test layout, following the existing suites (antenna vitest; transmitter
  `tests_transmitter/`; Python 3.11-compatible, `test-in-debian12.sh` is the gate).

## Open question for the operator

- `clock-inputs`, `clock-failed` and `guard-crashed` mean cron did not write
  the playlist this minute. That is harmless while the metronome's DO writes,
  but not when cron is the only writer: `METRONOME` off (rollback), or the DO
  judged down (`metronome-down`). Should these three skip the gate in those
  cases? Default if unanswered: gated regardless, as approved; hugo's
  `dead-clock` (~3–4 min) is the cover.
