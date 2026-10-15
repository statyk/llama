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
neither priced by the cost guard nor bounded by construction, is an uncapped
bill with nothing watching it. Treat the metronome's PUT bound, its lease
expiry and the guard's new meters with the rigor of a migration. Fail-closed
semantics must survive: an unknown verdict is never treated as unblocked, and
spend must not depend on cron being alive.

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

- 6,131 alarms: lateness median 1 ms, p99 0.33 s, max 4.5 s; no retry. The
  probe's `skipped` field is computed against the re-armed target, so it cannot
  see a chain break. Weekday daytime :00-:02 / :30-:32, 10:00-18:00: 264
  alarms, max 1.3 s late, while the probe's own cron at those minutes lagged a
  median 35 s, max 67 s.
- One chain break (17:33:28): an alarm invocation completed with no log line and
  left no alarm pending; the cron backstop re-armed it 7 s later. That is one
  missed boundary: writes were 18.6 s apart instead of 10.24. 64 more alarm
  invocations were reported `canceled` with no output (delivery is
  at-least-once).
- Measured usage (GraphQL, 18 h): DO `activeTime` 334 s (~0.5% of wall time:
  the object does not stay billed between alarms); `duration` 42.7 =
  `activeTime` × 0.128 GB, so the field is GB-s (inference from the data, the
  docs are silent); `rowsWritten` ≈ 1 per alarm; alarm invocations 6,388
  (70 `clientDisconnected`), jsrpc 1,080. `workersInvocationsAdaptive` reported
  only the probe's cron invocations: **DO requests are absent from the dataset
  the guard reads today.**
- The DO GraphQL datasets (measured 2026-10-14 against this account,
  read-only): `durableObjectsInvocationsAdaptiveGroups` and
  `durableObjectsPeriodicGroups` accept 31- and 32-day ranges
  (`datetime`/`datetimeMinute` filters), and their totals matched the probe's
  expected counts (~9.67k requests, ~8.25k rows over 23.5 h). Both carry the
  current minute (lag < 1 min, within `meter.ts`'s `LAG_MS` of 5 min). A range
  with no DO activity returns `[]`, indistinguishable from zero.
  `durableObjectsStorageGroups` returned no rows, even over 32 days while the
  probe held keys.

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
entry module, one instance: cron addresses it as `idFromName("metronome")` and
passes `locationHint: "enam"` on `get`. Still no routes, `workers_dev = false`, `preview_urls = false`. Listener paths
are unchanged: only cache-served R2 objects.

### Cron invocation (every minute)

1. **Guard step**: unchanged (`guard.ts`).
2. **`index.html`**: unchanged.
3. **Inputs**: unchanged (`readInputs`, `horizon-missing`, `horizon-refused`,
   `gridOf`, `lead-low`).
4. **Lease** (new): `metronome.renew(lease | null)` over RPC, bounded by a 10 s
   timeout, called **every** invocation with the argument the table below
   names (`null` leaves the DO's lease alone: a health check). The DO applies
   the lease if any, writes the playlist at once if its current lease is an
   unexpired `play` (the off-air notice when that lease is blocked), arms its
   alarm only under an unblocked `play` lease, and returns its status (below).
5. **Fallback** (new): cron runs today's playlist loop (write now and at each
   boundary until `scheduledTime + 75 s`, `MAX_PUTS` 10) and raises
   `metronome-down` only when:
   - `renew` throws or times out; or
   - the DO holds a current unblocked `play` lease and renew's write failed
     (`wrote: false`); or
   - `stalls >= 2`: two consecutive renews found the chain had stopped
     confirming the playlist for over `METRONOME_STALE_MS` (30 s) under a
     current unblocked `play` lease.

   A single stall (the 17:33 class) is repaired by that renew's own write and
   re-arm; it is logged on the clock line only (`metronome.stalledMs`), with no
   alert. A DO with no current unblocked `play` lease (none, `hold`, blocked,
   expired) is not "dead": it is doing what it was told. The loop writes only
   where the table below allows; `metronome-down` is raised whenever a trigger
   fires, whether or not the loop may write.
6. **Alerts**: unchanged, after the last write.

What cron passes to `renew`, by its own outcome, and whether its fallback loop
may run:

| Cron outcome | `renew` argument | Fallback loop |
|---|---|---|
| guard verdict unknown, or guard crashed | `renew(null)` | never writes (no known verdict) |
| verdict known unblocked; inputs read threw (`clock-inputs`), or horizon missing/unreadable | `renew(null)` | never writes |
| verdict known blocked; inputs unusable (read threw, horizon missing or unreadable) | `renew({kind: "hold"})` | never writes |
| horizon refused (`d` ≠ 10.24) | `renew({kind: "hold"})` | never writes |
| verdict known, horizon accepted | `renew({kind: "play", blocked, horizon, fallback})` | may run |

The fallback loop runs only with a known verdict and an accepted horizon; with
anything less it writes nothing, as today. `null` never turns into unblocked: a
lease is only ever issued from a known verdict, and a known blocked verdict is
always passed on, as a blocked `play` lease or as `hold`. `hold` exists because
a refused horizon is a spend refusal, not a transient. **Behaviour change,
accepted:** today an unknown verdict or unreadable inputs stall the playlist
that minute; now the previous lease plays on for up to 15 min.

`runClock`'s contract around this:

- Every early-return path still calls `renew` as the table says before it
  returns.
- `offairWithoutFallback` is computed by cron from its own inputs before it
  issues the lease. Cron raises the condition as today; the DO only logs on a
  change of state.
- The alert batch is `complete = true` after a healthy renew (no fallback
  trigger fired) or a finished fallback loop.

**The rollback switch.** Only the exact string `METRONOME = "on"` (new var)
enables the metronome; anything else (unset, `"off"`, a typo) is off. Off: cron
runs today's loop exactly as now and, after its first write, calls
`metronome.stop()` (delete the alarm, clear the lease) bounded by the same 10 s
timeout; a failed `stop()` is logged only. The DO also reads `env.METRONOME`
itself at the top of `alarm()` and `renew()`: not `"on"` ⇒ delete the alarm, no
write, no re-arm. Deploying the var change therefore reaches the DO directly,
and `stop()` is a courtesy.

### The lease

```ts
interface Lease {
  kind: "play" | "hold";
  verdictAt: number;      // when the issuing cron's guard step began (its state reads started): the ordering key
  validUntil: number;     // Date.now() at issue + METRONOME_LEASE_MS (15 min)
  blocked?: boolean;      // play only
  horizon?: Horizon;      // play only
  fallback?: FallbackIndex | null; // play only
}
```

- **Validation.** The lease is data from another isolate. The DO validates
  every lease when applying it **and** on every load from storage: `kind` is
  `play` or `hold`; for `play`, `typeof blocked === "boolean"`, the horizon
  passes `gridOf` with `d === GRID_D`, and `fallback` is null or an object with
  a numeric `len` and a string `notice`; `verdictAt` and `validUntil` are
  finite. Anything invalid is treated as `hold` (stamped with the DO's own
  `now` as its `verdictAt` and `now + METRONOME_LEASE_MS` as its expiry) and
  logged `metronome-lease-invalid`. A stored
  lease that cannot be read or parsed is "no lease": no write, no re-arm.
- **Ordering.** Overlapping cron runs are common, so leases can arrive out of
  order. A blocked `play` lease or a `hold` is accepted unconditionally:
  blocking is fail-closed. An unblocked `play` lease is accepted only if its
  `verdictAt` is strictly greater than the current lease's (none, or expired:
  accepted); there is no tie rule. Limitation, accepted as the fail-closed
  direction: a stale blocked lease from a lagging older run can block the
  station until the next run's lease, at most about one cron gap. A rejected
  lease still gets a status reply.
- **Atomic apply.** `renew`'s read-compare-write of the lease touches DO
  storage only, before any R2 PUT or other awaited fetch, so the DO's input
  gates serialize it against concurrent calls.
- **Expiry** is computed by the DO, not trusted: on accepting a lease it stores
  `expiresAt = min(lease.validUntil, now + METRONOME_LEASE_MS)` by its own
  clock. The check is written negated, `!(now < expiresAt)` ⇒ expired, so a
  NaN or missing value fails closed (the idiom of `pricing.ts`
  `overThreshold`).
- Persisted in DO storage, so a restart or redeploy resumes it.

### Metronome (the DO)

**State lives in DO storage; memory is a cache only.** The probe measured
~0.5% active time, consistent with the object being evicted between alarms
(the docs: hibernation after ~10 s idle), so nothing the logic depends on may
live only in memory. The stored keys are a fixed set:

- `lease`: validated, with its `expiresAt`;
- `lastGoodAt`: the last confirmed tick (below);
- `lastTarget`: the last armed alarm time;
- `lastBytesHash`: a hash of the last successfully written body;
- the PUT window counter and the alarm-invocation window counter;
- `stalls`: consecutive renews that found `stalledMs` > 30 s under a current
  unblocked `play` lease.

The "already logged" marks behind once-per-lease anomaly logs are memory only:
an eviction can repeat a log line, never a write.

**Confirmed ticks.** `lastGoodAt` is the last time the DO knew `live.m3u8`
held the playlist for that moment: a successful PUT; **or** a skip because the
body hashes equal to `lastBytesHash`; **or** a tick where `buildPlaylist`
returns null (before the epoch, or no usable fallback), which writes nothing
by rule (`wrote: null`, logged once per lease). A write skipped by the cap is
not a confirmed tick.

**Serialized writes.** Every write path (`alarm()` and `renew()`) runs build →
cap reservation → PUT → state update behind one in-object promise chain (or
`ctx.blockConcurrencyWhile`). The cap slot is reserved, its storage write
awaited, before the PUT is issued.

**`renew(lease | null)`**:

1. `env.METRONOME` not `"on"`: delete the alarm, return; no write.
2. Load and validate the stored lease. Compute `stalledMs = now − lastGoodAt`
   as it stood before this call: 0 unless that lease was a current unblocked
   `play` (no ticks were expected otherwise). Update `stalls`: one more when
   `stalledMs` > `METRONOME_STALE_MS`, else 0.
3. Apply the lease if given (ordering above), in storage, before any R2 call.
4. If the current lease is an unexpired `play`, write once now: the live
   playlist, or the off-air notice when blocked. The write is skipped only when
   the body hashes equal to `lastBytesHash` **and** `now − lastGoodAt` < d. It
   obeys the PUT cap; a cap-skipped write returns `wrote: null` and is not a
   failure.
5. Under an unblocked `play` lease, if no alarm is pending, arm one (target as
   in `alarm()` step 4). Otherwise delete any pending alarm.
6. Return:

```ts
interface MetronomeStatus {
  accepted: boolean;        // logged only; not a fallback input
  lease: "play" | "blocked" | "hold" | "none"; // after this call; "none" = absent or expired
  wrote: boolean | null;    // this call's write succeeded; null = no write due (no play lease, identical bytes, cap, nothing to build)
  lastGoodAt: number | null;
  stalledMs: number;        // before this call; see above
  stalls: number;           // fallback at >= 2
  leaseVerdictAt: number | null;
}
```

**`alarm()`**:

1. `env.METRONOME` not `"on"`: delete the alarm, return.
2. Load and validate the lease. Not a current unblocked `play` lease (none,
   `hold`, blocked, expired): delete any pending alarm and return without
   re-arming. The next `renew` restarts the chain. The object cannot tick
   forever on its own.
3. Count the invocation. More than 12 `alarm()` invocations in a rolling 60 s:
   do not re-arm, log `metronome-alarm-cap`, return. The next `renew` restarts
   the chain.
4. **Re-arm first**, to the first `startMs(n) + 25 ms` strictly after
   `max(now, lastTarget)`, and persist it as `lastTarget`. The target comes
   from the wall clock, never "previous target + d", so lateness never
   accumulates and missed boundaries are skipped, never written in a burst;
   `max(now, lastTarget)` rules out a hot loop when an alarm is delivered
   before the DO's clock passes the boundary. The re-arm has its own
   try/catch: on failure, log `metronome-rearm-failed` and return.
5. Build the playlist for `now` from the lease (below); PUT unless the body
   hashes equal to `lastBytesHash`, subject to the cap and the PUT timeout.
6. Update storage (`lastGoodAt`, `lastBytesHash`, counters).

Nothing in `alarm()` ever throws to the runtime: an escaping exception would
hand the chain to the platform's 6-retry backoff. A duplicate or retried alarm
rebuilds the same bytes and skips the PUT: the handler is idempotent.

**Spend bounds (hard, independent of inputs):**

- At most one PUT per `alarm()` and one per `renew()`.
- At most `MAX_DO_PUTS_PER_MINUTE` = 10 PUTs per rolling 60 s window, `renew`'s
  write included; over it the write is skipped and logged (`metronome-cap`),
  and the chain still re-arms. Normal is ~6-8.
- At most 12 `alarm()` invocations per rolling 60 s; over it the chain is not
  re-armed (`metronome-alarm-cap`).
- Each R2 PUT is bounded by a 5 s timeout (`Promise.race`, as `alerts.ts`
  bounds its sends); a timeout is a failed write.
- Only an unblocked `play` lease runs the alarm chain. Under a blocked lease
  `renew` writes the off-air notice once per call (the minutely cadence today's
  cron already has) and nothing ticks: a spend trip must reduce DO spend too,
  and off-air bytes gain nothing from ticking. A `hold`, an expired lease and
  no lease write nothing.
- A refused horizon (`d` ≠ 10.24) is never in a `play` lease, and the DO's
  validation treats one as `hold` anyway.
- The alarm is always armed to the first boundary strictly after
  `max(now, lastTarget)`: never in the past, never the same target twice.
- The DO's storage is the fixed key set above and never grows; a test pins the
  key set. This is how storage spend is bounded (it cannot be metered, see the
  cost guard).
- Combined worst case, Class A: the DO ≤ 10 PUTs/min plus the cron fallback
  ≤ 10 per invocation, with up to ~3 overlapping invocations, is ≤ 40 playlist
  PUTs in the worst minute. Bounded, and visible to the guard through
  `r2OperationsAdaptiveGroups`. A minute with both writers is the accepted,
  bounded cost of the fallback; Decision 1 rejects double writing as the
  normal mode, not as a failure mode.

### Playlist contents

Unchanged rules: `buildPlaylist` with window 16, lookahead 12, hold-back 12,
grace, the fallback loop, the 24 h stale-horizon off-air, ENDLIST-only when
off air without a usable fallback (`offair-without-fallback` is raised by cron
from its own inputs, as now; the DO logs it on a change of state). One
implementation serves both writers: the per-write body of `runClock` (build,
detect off-air-without-fallback, compare bytes, cap, PUT) moves into a shared
module used by the cron loop and the DO.

**Off-air numbering in the DO.** The DO numbers the notice with the existing
`offairSequence(g, now, now + MAX_LOOP_MS, lookahead)`, i.e. it passes
`offairSeqMs = now + 75 s`: the same rule shape as the cron loop's
`max(scheduledTime + loopMs, now)`. Any live playlist written at t ≤ now lists
at most `indexAt(t) + lookahead`, so the notice is strictly above every live
segment either writer has listed (the cron fallback's invocation was scheduled
at or before now), and it never decreases across renews. `buildPlaylist` needs
no new input. The bytes change from one renew to the next, so a blocked station
costs about one PUT per minute (1,440/day), the same as today. Both notices end
in ENDLIST, so a player that saw one stops reloading.

Unblocking and epoch changes behave exactly as today (players that hit ENDLIST
must press play; a new `epoch_id` restarts numbering).

## Cost guard: Durable Object meters

`pricing.ts` gains four meters, at the published Workers Paid prices (re-check
on the pricing page when the plan is written; checked 2026-10-14 by research,
quotes in the plan):

| Meter | Included / month | Overage | GraphQL (account-scoped) |
|---|---|---|---|
| `doRequests` | 1,000,000 | $0.15 / M | `durableObjectsInvocationsAdaptiveGroups` `sum.requests`, all types and statuses |
| `doDurationGbS` | 400,000 | $12.50 / M | `durableObjectsPeriodicGroups` `sum.duration` |
| `doRowsWritten` | 50,000,000 | $1.00 / M | same, `sum.rowsWritten` |
| `doRowsRead` | 25,000,000,000 | $0.001 / M | same, `sum.rowsRead` |

They are added to `USAGE_QUERY` as period-to-date and recent-window queries,
like the existing four. The touch points: `METERS`, `Usage`, `OpCounts`,
`Reading`, `evaluateSpend`'s literals, `meter.ts`'s parsing, and `latch.ts`
`stored()` (what `guard.json` shows). The datasets' range, lag and units were
measured (above): both serve a 32-day period and the current minute, so the
existing `LAG_MS` holds. A dataset that cannot serve the period is a failed
reading. Never price a meter at zero for want of data; the blind rule then
trips after 6 h as today.

- **Empty is not zero.** A range with no DO activity reads as `[]`. While
  `METRONOME` is `"on"`, a reading whose recent-window `doRequests` is 0 is a
  failed reading: cron renews every minute, so the true count cannot be 0. For
  up to `LAG_MS` after the switch is flipped on, readings fail this way;
  harmless, since the blind rule needs 6 h.
- **Storage is not metered.** `durableObjectsStorageGroups` returns no rows for
  this account, so stored bytes cannot be read. They are bounded by
  construction instead (the fixed key set, under Spend bounds), far inside the
  5 GB-month allowance.
- **Rows written.** The probe's `rowsWritten` (~1 per alarm) is below what the
  docs bill (a put plus a `setAlarm` = 2 rows). Rows run ~100× under the
  allowance, so no correction is made; verification compares the meter with
  the dashboard's billable usage.

## Observability

The DO logs only anomalies, on a change of state rather than per tick (once per
lease or per episode): `metronome-late` > 2 s, `metronome-put-failed`,
`metronome-expired`, `metronome-cap`, `metronome-alarm-cap`,
`metronome-rearm-failed`, `metronome-lease-rejected`,
`metronome-lease-invalid`, `metronome-hold`, `offair-without-fallback`, and a
null build. Each DO invocation is itself a Workers Logs event when
observability is on, so expect ~10k events/day, far inside the included
allowance. Cron's existing per-invocation `clock` line gains a `metronome`
object (the `renew` status, including `stalledMs`, or the fallback reason). The
verification capture analyses freezes from the clock lines plus a
`wrangler tail` of the DO's anomaly lines.

## Failures and alerts

| Failure | Behaviour | Alert |
|---|---|---|
| DO PUT fails or times out (5 s) | logged; the next tick retries; under a current unblocked `play` lease a failed renew write (`wrote: false`) makes cron run the loop | `metronome-down` (renew's write failed) |
| `renew` throws or times out | cron runs the loop where the lease table allows | `metronome-down` |
| `alarm()` throws after re-arming | caught; the chain continues | log only |
| re-arm fails | logged `metronome-rearm-failed`; the next `renew` restarts the chain | log only |
| alarm chain broken once (as 2026-10-14 17:33) | the next `renew`'s write and re-arm repair it | log only (`metronome.stalledMs` on the clock line) |
| alarm chain broken on consecutive renews (`stalls >= 2`) | cron runs the loop | `metronome-down` |
| alarm-invocation cap hit | no re-arm; the next `renew` restarts the chain | log only |
| cron silent | the DO plays on its lease for up to 15 min, then stops writing and re-arming; the playlist freezes | hugo: dead-clock, then guard-stale |
| guard verdict unknown | `renew(null)`; the current lease plays to expiry; the fallback never writes | existing `guard-unknown` |
| horizon refused | `hold` lease: the DO stops writing at once | existing `horizon-refused` |

- `metronome-down` is a clock-family key (add it to `alerts.ts` `CLOCK_KEYS`):
  raised by cron, it resolves only on a complete batch.
- The DO sends no alerts.
- **A dead cron.** The station keeps playing for at most 15 min on its lease;
  then the playlist freezes and hugo's dead-clock check alerts (newest segment
  older than `dead_clock_seconds`, 120 s, on two checks a minute apart).
  Independently, hugo alerts when `guard.json`'s evaluation is older than
  `guard_stale_minutes` (45). A cron outage is therefore detected ~17-18 min
  after the last renew instead of ~3-4 min today; accepted.
- **Known limitation: a silent chain break.** An alarm chain that breaks with no
  error (measured once in ~21 h) freezes the playlist until the next renew, up
  to one cron gap (≤ ~200 s on a bad day). The rollout pass criterion counts
  such freezes.

## Rollout

1. Tear down `alarm-probe` per its README (`STOP=1` deploy, then
   `wrangler delete`); its DO would otherwise appear in the account-wide meters.
2. Deploy with `METRONOME` not `"on"`: the DO class exists (SQLite-backed;
   migration form per the current wrangler: `new_sqlite_classes` or the
   declarative `exports` field, checked with `wrangler deploy --dry-run`), and
   the guard's new meters read. **Pass** only when `state/guard.json`'s
   `last_error` is null and its `period_to_date` carries all eight meters.
3. Flip to `METRONOME = "on"`.
4. Verification day: a 24 h `wrangler tail antenna` including a weekday daytime.
   **Pass:**
   - no playlist freeze > 45 s outside a reported `metronome-down`, except
     silent chain breaks: at most 1-2 in the day, each tied to a logged single
     stall;
   - the DO meters in `guard.json` agree with the dashboard's billable usage;
   - the playlist Class A rate is within ±15% of the pre-change rate.

   **Also:** deploy twice during the day to observe what a deploy does to a
   pending alarm (the docs are silent), and confirm the chain survives or the
   next `renew` repairs it within a minute.

`docs/playout-setup.md` gets the rollout and rollback (`METRONOME` not `"on"`).
`CLAUDE.md`'s antenna paragraph and the parent spec get as-built notes.

## Testing

vitest in the Workers runtime (`@cloudflare/vitest-plugin`), fake clock and fake
bucket as the clock tests use. The DO's logic lives in a pure module
(`metronome-core.ts`: e.g. `applyLease(state, lease, now)` and
`tick(state, now)` returning the actions to take), tested with a fake clock. A
thin DO wrapper is tested with `runInDurableObject`/`runDurableObjectAlarm` for
the storage and alarm plumbing.

- Lease validation, on apply and on load: each invalid shape (bad `kind`,
  non-boolean `blocked`, a horizon failing `gridOf` or with `d` ≠ 10.24, a bad
  `fallback`, non-finite `verdictAt` or `validUntil`) is treated as `hold` and
  logged; an unparseable stored lease is no lease (no write, no re-arm).
- Lease ordering: an unblocked `play` lease with `verdictAt` ≤ the current
  lease's is rejected, equal included; a blocked `play` lease and a `hold` are
  accepted whatever their `verdictAt`.
- Expiry: `expiresAt` is `min(validUntil, now + 15 min)`, so a far-future
  `validUntil` still expires at 15 min; a NaN or missing value is expired;
  after expiry an alarm writes nothing and does not re-arm; `renew` with a new
  lease restarts it.
- `hold`: no PUT, no pending alarm.
- Blocked lease: `renew` writes the notice, no alarm is pending afterwards, and
  an alarm delivered anyway writes nothing and does not re-arm.
- Off-air numbering: the notice is numbered above `indexAt(now) + lookahead`
  and never decreases across renews.
- Duplicate alarm for the same boundary: identical bytes, no second PUT, and
  the skip is a confirmed tick.
- A null build (before the epoch; no usable fallback) is a confirmed tick:
  `lastGoodAt` advances, `wrote: null`, one log line per lease.
- `renew` skips its write only when the hash equals `lastBytesHash` and
  `now − lastGoodAt` < d.
- PUT cap: the 11th write in a 60 s window is skipped and logged; a cap-skipped
  `renew` write returns `wrote: null` and does not trigger the fallback; the
  chain re-arms.
- Alarm-invocation cap: the 13th `alarm()` in 60 s does not re-arm and logs
  `metronome-alarm-cap`; the next `renew` restarts the chain.
- Re-arm target: the first boundary + 25 ms strictly after
  `max(now, lastTarget)`; an alarm delivered before the DO's clock passes its
  boundary does not re-arm to the same target; `lastTarget` is persisted.
- A re-arm failure logs `metronome-rearm-failed` and returns; an exception
  anywhere in `alarm()` never propagates.
- A PUT that does not settle within 5 s is a failed write.
- Interleave: a fake bucket whose `put` resolves on demand, plus a concurrent
  `renew`; the cap and the identical-bytes state stay consistent.
- Storage: the DO's stored key set is exactly the fixed set.
- Cron's lease table: each outcome passes the table's `renew` argument, and the
  fallback loop writes only on a known verdict with an accepted horizon; every
  early-return path calls `renew`.
- Cron fallback: `renew` throws or times out, or (under a current unblocked
  `play` lease) reports `wrote: false`, or reports `stalls >= 2` → the legacy
  loop runs where allowed and `metronome-down` is raised; a single stall → no
  fallback, no alert, `stalledMs` on the clock line; a healthy status → no cron
  PUTs and a complete alert batch.
- Cron addresses the stub by the fixed name (one instance).
- `renew(null)` leaves the lease untouched and still writes from a current
  `play` lease.
- The switch: only `"on"` enables; unset, `"off"` or a typo → cron runs the
  legacy loop unchanged and calls `stop()` after its first write (a failed
  `stop()` is logged only), and the DO's `alarm()` and `renew()` delete the
  alarm and write nothing. The existing clock tests keep passing in this mode.
- Pricing: each new meter priced through its allowance; every `METERS` entry is
  finite in `periodToDate`, `projected` and the stored doc; a meter with a zero
  price fails a per-meter pricing test; a NaN or missing DO reading trips
  (`overThreshold`), as for the existing meters; `USAGE_QUERY` parsing of the
  new datasets, including a truncated result; with the switch on, a recent
  `doRequests` of 0 is a failed reading.
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

- The migration syntax the pinned wrangler accepts (`new_sqlite_classes` vs
  `exports`), and the matching teardown form.
- Whether `setAlarm` from inside `renew()` while an alarm is pending replaces it
  cleanly (the docs: one alarm per object, a second `setAlarm` overrides).
