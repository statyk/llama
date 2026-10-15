# antenna metronome: a Durable Object writes the playlist on the grid

Status: design, approved section by section by the operator 2026-10-14.
Parent design: `docs/superpowers/specs/2026-10-09-playout-design.md` (antenna,
cost guard). This spec changes only what drives `live.m3u8` writes and what the
cost guard prices; every playlist rule is unchanged.

**Review mode: Fable** (operator, 2026-10-14: "Opus/Fable reviewers"). The
second spec/plan reviewer and the final branch reviewer are Fable.

## Stakes

What is at risk is **money and on-air continuity**, not data. Nothing here reads
or writes the station root, llama or emcee state. antenna writes only its own R2
bucket and, new, its own Durable Object storage.

**Strict surface: spend.** Cloudflare has no account spending cap. This design
adds a new billed product (Durable Objects: requests, duration, storage rows,
storage bytes) and a new writer of a billed R2 object (`live.m3u8`, Class A per
PUT). A defect that lets the alarm chain run away, or that leaves a DO meter
unpriced by the cost guard, is an uncapped bill with nothing watching it. Treat
the metronome's PUT bound, its lease expiry and the guard's new meters with the
rigor of a migration. Fail-closed semantics must survive: an unknown verdict is
never treated as unblocked, and spend must not depend on cron being alive.

**The goal: continuity.** iOS drops audio once `live.m3u8` stops advancing for
~60-75 s, whatever the hold-back (measured 2026-10-13: the tolerance is a
playlist-staleness limit, not buffer exhaustion). The target is **no playlist
freeze over ~45 s** in normal operation.

## Problem (measured)

The clock is a cron-only Worker: each minutely invocation writes the playlist at
every grid boundary until `scheduledTime + 75 s`. When an invocation starts late,
the playlist freezes from the previous run's end to the late run's start.

- 24 h, 2026-10-13 01:19 → 10-14 01:19 (`wrangler tail antenna`, 1,432 fires):
  lag median 16.9 s, p90 51.2, p99 99.8, max 143.1; 473 fires > 25 s, 39 > 75 s.
  Freezes: 118 > 45 s, 52 > 60 s, 30 > 75 s, 13 > 90 s, concentrated at :00/:30
  between 04:00 and 17:30 EDT.
- 2026-10-14 to 19:40 was much better (median 9.9 s, max 93.6 s; 3 real freezes
  > 60 s): cron quality varies day to day and cannot be relied on.

**Durable Object alarm probe** (throwaway Worker `alarm-probe`, an alarm re-armed
at every 10.24 s station boundary, cron backstop; 2026-10-13 22:35 → 10-14 19:41):

- 6,131 alarms: lateness median 1 ms, p99 0.33 s, max 4.5 s; no skipped
  boundary, no retry. Weekday daytime :00-:02 / :30-:32, 10:00-18:00: 264
  alarms, max 1.3 s late, while the probe's own cron at those minutes lagged a
  median 35 s, max 67 s.
- One hiccup (17:33:28): an alarm invocation completed with no log line and left
  no alarm pending; the cron backstop re-armed it 7 s later. Writes were 18.6 s
  apart instead of 10.24. 64 more alarm invocations were reported `canceled`
  with no output, with no missed boundary (delivery is at-least-once).
- Measured usage (GraphQL, 18 h): DO `activeTime` 334 s (~0.5% of wall time:
  the object does not stay billed between alarms); `duration` 42.7 =
  `activeTime` × 0.128 GB, so the field is GB-s (inference from the data, the
  docs are silent); `rowsWritten` ≈ 1 per alarm; alarm invocations 6,388
  (70 `clientDisconnected`), jsrpc 1,080. `workersInvocationsAdaptive` reported
  only the probe's cron invocations: **DO requests are absent from the dataset
  the guard reads today.**

Projected for the metronome: ~255k alarm + ~43k RPC requests/month (1M
included), ~2k GB-s/month (400k included), ~500k rows written/month (50M
included). Marginal cost ≈ $0; the risk is a runaway, not the steady state.

## Decisions (operator, 2026-10-14)

1. **The DO is the playlist's only writer; cron falls back to today's loop only
   when the DO looks dead** (option 3 of 3; rejected: DO-only with no fallback,
   and DO + cron both writing).
2. **Cron hands the DO everything in a lease** (verdict + horizon + fallback);
   the DO never reads R2 and derives nothing about blocked state.
3. **Lease lifetime 15 min.** Consequence accepted: during a cron outage the
   station keeps playing up to 15 min on the last verdict, and an operator
   `transmitter offair on` cannot take effect in that window (the WAF kill
   switch still can).
4. On expiry the DO **writes nothing** (stall, like today's guard-unknown),
   never an off-air playlist.

Rejected earlier (2026-10-13): Option 2 (cron runs keep writing past
`sched + 75 s` until a newer run appears) and an external VM metronome.

## Architecture

One Worker, one new Durable Object class `Metronome` exported from `antenna`'s
entry module, one instance (`idFromName("metronome")`). Still no routes,
`workers_dev = false`, `preview_urls = false`. Listener paths are unchanged:
only cache-served R2 objects.

### Cron invocation (every minute)

1. **Guard step**: unchanged (`guard.ts`).
2. **`index.html`**: unchanged.
3. **Inputs**: unchanged (`readInputs`, `horizon-missing`, `horizon-refused`,
   `gridOf`, `lead-low`).
4. **Lease** (new): `metronome.renew(lease | null)` over RPC, bounded by a 10 s
   timeout, called **every** invocation (`null` when the table below issues no
   lease: a health check that leaves the lease alone). The DO applies the lease
   if any, writes the playlist at once from its current lease (if that lease is
   `play` and unexpired), ensures its alarm is armed, and returns its status
   (below).
5. **Fallback** (new): cron runs today's playlist loop (write now and at each
   boundary until `scheduledTime + 75 s`, `MAX_PUTS` 10) and raises
   `metronome-down` when the DO looks dead: `renew` throws or times out; or the
   DO holds a current `play` lease and the status shows `wrote: false` (its forced
   write failed), `armed: false`, or `stalledMs > METRONOME_STALE_MS` (30 s: the
   chain had stopped confirming the playlist before this call despite a current
   lease). A DO with no current `play` lease (none, `hold`, expired) is not
   "dead": it is doing what it was told.
6. **Alerts**: unchanged, after the last write.

Which leases cron issues, by its own outcome:

| Cron outcome | Lease |
|---|---|
| guard verdict known, horizon read and accepted | `{kind: "play", blocked, horizon, fallback}` |
| guard verdict unknown (`blocked: null`, guard crash) | none: the DO keeps its current lease |
| inputs read threw (`clock-inputs`), or horizon missing/unreadable | none: the DO keeps its current lease |
| horizon refused (`d` ≠ 10.24) | `{kind: "hold"}`: the DO stops writing at once |

"None" never turns into unblocked: a lease is only ever issued from a known
verdict. A current lease that said blocked keeps the station off air until it
expires. `hold` exists because a refused horizon is a spend refusal, not a
transient. **Behaviour change, accepted:** today an unknown verdict stalls the
playlist that minute; now the previous lease plays on for up to 15 min.

`METRONOME = "off"` (new var): cron makes a best-effort `metronome.stop()` call
(delete the alarm, clear the lease) and runs today's loop exactly as now. This is
the rollback switch.

### The lease

```ts
interface Lease {
  kind: "play" | "hold";
  scheduledTime: number;  // the issuing cron's scheduledTime: the ordering key
  issuedAt: number;       // Date.now() at issue
  validUntil: number;     // issuedAt + METRONOME_LEASE_MS (15 min)
  blocked?: boolean;      // play only
  horizon?: Horizon;      // play only
  fallback?: FallbackIndex | null; // play only
}
```

- **Ordering.** Overlapping cron runs are common, so leases can arrive out of
  order. The DO accepts a lease only when `scheduledTime` ≥ the current lease's.
  On a tie, the blocked lease (and `hold`) wins. A rejected lease still gets a
  status reply.
- **Expiry** is `now ≥ validUntil`, both from Cloudflare clocks.
- Persisted in DO storage, so a restart or redeploy resumes it.

### Metronome (the DO)

State in DO storage: `lease`, `highestListed` (the highest media sequence
number it has listed live), `offairSeq` (pinned while blocked, else null), the
per-minute PUT counter, the `cron-silent` alert flag. In memory only: the last
written bytes (an identical-bytes skip that is lost on restart costs one PUT).

**Confirmed ticks.** `lastGoodAt` is the last time the DO knew `live.m3u8`
held the playlist for that moment: a successful PUT, **or** a skip because the
bytes equal the last successfully written ones. While blocked the off-air bytes
are constant and the DO PUTs once then skips, so "last PUT" would look dead
while the DO is healthy; `lastGoodAt` does not. A write skipped by the cap is not
a confirmed tick.

**`renew(lease | null)`**: record `lastRenewAt = now`; apply the lease if given
(ordering above); compute `stalledMs = now − lastGoodAt` as it stood *before*
this call (0 when the previous lease was absent, `hold` or expired: no ticks were
expected); if the current lease is an unexpired `play`, write once now (force:
bytes are not compared, as cron's first write today); make sure the alarm is set
to the next boundary; clear the `cron-silent` flag (sending a resolve if it was
raised); return:

```ts
interface MetronomeStatus {
  accepted: boolean;
  wrote: boolean | null;   // this call's forced write succeeded; null = no write due
  lastGoodAt: number | null;
  stalledMs: number;       // before this call; see above
  armed: boolean;
  putsSinceRenew: number;
  maxLateMsSinceRenew: number;
  leaseScheduledTime: number | null;
}
```

**`alarm()`**:

1. No lease, `hold`, or expired: write nothing, **do not re-arm**, return. The
   next `renew` restarts the chain. The object cannot tick forever on its own.
2. `now − lastRenewAt` > `CRON_SILENT_MS` (4 min, above the ~200 s worst gap
   between cron runs measured on 2026-10-13) and the alert flag unset. This is
   measured from the last `renew` call of any kind, not the lease's age: a cron
   that runs but issues no lease (an unknown verdict) is not silent: send `cron-silent`
   to the alert channels and set the flag.
3. Build the playlist for `now` from the lease (below); PUT unless the bytes
   equal the last written, subject to the cap.
4. Re-arm to `startMs(indexAt(now) + 1) + 25 ms`, from the wall clock, never
   "previous target + d", so lateness never accumulates and missed boundaries
   are skipped, never written in a burst.

The whole body runs in a try/catch whose finally re-arms (step 4) unless step 1
returned. An exception never reaches the runtime, so Cloudflare's 6-retry
backoff never governs the chain. A duplicate or retried alarm rebuilds the same
bytes and skips the PUT: the handler is idempotent.

**Spend bounds (hard, independent of inputs):**

- At most one PUT per `alarm()` and one per `renew()`.
- At most `MAX_DO_PUTS_PER_MINUTE` = 10 PUTs per rolling 60 s window; over it
  the write is skipped and logged (`metronome-cap`), the chain still re-arms.
  Normal is ~6-8.
- A refused horizon (`d` ≠ 10.24) is never in a `play` lease. The DO still
  re-checks `horizon.d === GRID_D` and treats a mismatch as `hold`
  (belt and braces: the lease is data from another isolate).
- The alarm never re-arms more than one boundary ahead, and never at a time
  ≤ now (a target in the past is moved to the next boundary after now).

### Playlist contents

Unchanged rules: `buildPlaylist` with window 16, lookahead 12, hold-back 12,
grace, the fallback loop, the 24 h stale-horizon off-air, ENDLIST-only when
off air without a usable fallback (`offair-without-fallback` is logged by the DO
and raised by cron from its own inputs, as now). One implementation serves both
writers: the per-write body of `runClock` (build, detect
off-air-without-fallback, compare bytes, cap, PUT) moves into a shared module
used by the cron loop and the DO.

**Off-air numbering in the DO.** The cron loop numbers the notice from
`scheduledTime + loopMs` (constant within an invocation). The DO has no
invocation, so on the first blocked tick it pins
`offairSeq = max(highestListed, indexAt(now) + lookahead) + 1` and passes it as
the notice's sequence (`buildPlaylist` gains an explicit off-air sequence input
beside `offairSeqMs`) for as long as the lease says blocked, so the bytes are
constant (one PUT, then skips). Unblocking clears the pin. The notice is
therefore always numbered strictly above every live segment the DO has listed,
the property `offairSequence`'s "+ 1" protects. The cron fallback loop keeps its
own rule. Both notices end in ENDLIST, so a player that saw one stops reloading.

Unblocking and epoch changes behave exactly as today (players that hit ENDLIST
must press play; a new `epoch_id` restarts numbering).

## Cost guard: Durable Object meters

`pricing.ts` gains five meters, at the published Workers Paid prices (re-check
on the pricing page when the plan is written; checked 2026-10-14 by research,
quotes in the plan):

| Meter | Included / month | Overage | GraphQL (account-scoped) |
|---|---|---|---|
| `doRequests` | 1,000,000 | $0.15 / M | `durableObjectsInvocationsAdaptiveGroups` `sum.requests`, all types and statuses |
| `doDurationGbS` | 400,000 | $12.50 / M | `durableObjectsPeriodicGroups` `sum.duration` |
| `doRowsWritten` | 50,000,000 | $1.00 / M | same, `sum.rowsWritten` |
| `doRowsRead` | 25,000,000,000 | $0.001 / M | same, `sum.rowsRead` |
| `doStorageGbMonth` | 5 | $0.20 / GB-month | `durableObjectsStorageGroups` `max.storedBytes`, priced at the period peak like R2 storage |

They are added to `USAGE_QUERY` as period-to-date and recent-window queries, like
the existing four, and flow through `evaluateSpend`'s per-meter projection and
`overThreshold` unchanged. **Before the query is trusted, the plan measures** (as
`meter.ts`'s existing claims were measured): whether each DO dataset accepts a
32-day range, its lag (the recent window ends `LAG_MS` before now; widen it if a
DO dataset lags more), and the field units. A dataset that cannot serve the
period is a failed reading. Never price a meter at zero for want of data; the
blind rule then trips after 6 h as today.

## Observability

Workers Logs is a separately billed product, so the log volume stays near today's
~1,440 lines/day: the DO logs only anomalies (`metronome-late` > 2 s,
`metronome-put-failed`, `metronome-expired`, `metronome-cap`,
`metronome-lease-rejected`, `metronome-hold`), and cron's existing per-invocation
`clock` line gains a `metronome` object (the `renew` status, or the fallback
reason). The verification capture analyses freezes from the clock lines plus a
`wrangler tail` of the DO's anomaly lines.

## Failures and alerts

| Failure | Behaviour | Alert |
|---|---|---|
| DO PUT fails | logged; the next tick retries; cron's forced write fails too, or `stalledMs` > 30 s, so cron runs the loop | `metronome-down` |
| `renew` throws or times out | cron runs the loop | `metronome-down` |
| `alarm()` throws | caught, re-armed | log only |
| alarm chain broken (as 2026-10-14 17:33) | the next `renew` re-arms; its immediate write covers the gap | log only |
| cron silent | DO plays on its lease; at 4 min it sends `cron-silent` once; at 15 min it stops writing and re-arming; hugo's dead-clock check then fires | `cron-silent` (DO), then hugo |
| guard verdict unknown | no lease; the current one plays to expiry | existing `guard-unknown` |
| horizon refused | `hold` lease: the DO stops writing at once | existing `horizon-refused` |

- `metronome-down` is a clock-family key (add it to `alerts.ts` `CLOCK_KEYS`):
  raised by cron, it resolves only on a complete batch.
- `cron-silent` is sent by the DO through the same channels
  (`channelsFromEnv`: ntfy, email), with its dedupe flag in **DO storage, not
  `state/alerts.json`**. That file keeps its single writer; a second writer in
  another isolate is a race not worth adding. It sends once per outage and a
  resolve on the next `renew`.

## Rollout

1. Tear down `alarm-probe` per its README (`STOP=1` deploy, then
   `wrangler delete`); its DO would otherwise appear in the account-wide meters.
2. Deploy with `METRONOME = "off"`: the DO class exists (SQLite-backed;
   migration form per the current wrangler: `new_sqlite_classes` or the
   declarative `exports` field, checked with `wrangler deploy --dry-run`), and
   the guard's new meters read. Check `state/guard.json` shows the DO meters
   with sane values.
3. Flip to `METRONOME = "on"`.
4. Verification day: a 24 h `wrangler tail antenna` including a weekday daytime.
   **Pass:**
   - no playlist freeze > 45 s outside a reported `metronome-down`;
   - the DO meters in `guard.json` agree with the dashboard;
   - the playlist Class A rate is within ±15% of the pre-change rate.

   **Also:** deploy twice during the day to observe what a deploy does to a
   pending alarm (the docs are silent), and confirm the chain survives or the
   next `renew` repairs it within a minute.

`docs/playout-setup.md` gets the rollout and rollback (`METRONOME = "off"`).
`CLAUDE.md`'s antenna paragraph and the parent spec get as-built notes.

## Testing

vitest in the Workers runtime (`@cloudflare/vitest-plugin`: `runInDurableObject`,
`runDurableObjectAlarm`), fake clock and fake bucket as the clock tests use.

- Lease ordering: an older `scheduledTime` is rejected; a tie prefers blocked/hold.
- Expiry: after `validUntil` an alarm writes nothing and does not re-arm; `renew`
  restarts it.
- `hold` and a `d` ≠ 10.24 horizon inside a `play` lease: no PUT.
- Off-air pin: numbered above `highestListed` and above `indexAt(now) + lookahead`;
  constant bytes while blocked; cleared on unblock.
- Duplicate alarm for the same boundary: identical bytes, no second PUT.
- PUT cap: the 11th write in a 60 s window is skipped and logged; the chain re-arms.
- Re-arm target: always the next boundary after now plus 25 ms; never in the past.
- An exception inside `alarm()` still re-arms and never propagates.
- `cron-silent`: sent once after 4 min without a renew; resolved by the next renew.
- Cron fallback: `renew` throws, times out, or (with a current `play` lease)
  reports `wrote: false`, `armed: false` or `stalledMs` > 30 s → the legacy loop
  runs and `metronome-down` is raised; a healthy status → no cron PUTs.
- Blocked steady state: constant off-air bytes, one PUT then skips, `lastGoodAt`
  keeps advancing, and cron does **not** fall back.
- `renew(null)` leaves the lease untouched, still writes from a current `play`
  lease, and resets the `cron-silent` timer.
- `METRONOME = "off"` → `stop()` is called and the legacy loop runs unchanged
  (the existing clock tests keep passing in this mode).
- Pricing: each new meter priced through its allowance; a NaN or missing DO
  reading trips (`overThreshold`), as for the existing meters; `USAGE_QUERY`
  parsing of the new datasets, including a truncated result.
- `wrangler-config.test.ts`: the DO binding and migration are present; still no
  routes, `workers_dev` false, no account id or address in the config.

## Non-goals

- Moving the guard, WAF reconcile, `index.html` or alerts into the DO (the guard
  took up to 18 s on 2026-10-14 when the WAF API timed out; it would delay ticks).
- Changing any playlist rule, the window, lookahead or hold-back.
- Fixing ntfy returning HTTP 429 (seen 2026-10-14 on `waf-api` and its resolve):
  a separate open item; check whether hugo shares the topic or IP quota.
- Trimming silence at source disc boundaries (a separate future feature).

## Open questions for the plan (measurement, not design)

- The DO GraphQL datasets' range limits and lag, measured against this account.
- The migration syntax the pinned wrangler accepts (`new_sqlite_classes` vs
  `exports`), and the matching teardown form.
- Whether `setAlarm` from inside `renew()` while an alarm is pending replaces it
  cleanly (the docs: one alarm per object, a second `setAlarm` overrides).
