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

- 6,131 alarms: lateness median 1 ms, p99 0.33 s, max 4.5 s; no retry.
  Weekday daytime :00-:02 / :30-:32, 10:00-18:00: 264
  alarms, max 1.3 s late, while the probe's own cron at those minutes lagged a
  median 35 s, max 67 s.
- One chain break over the captured span (the tail caught ~83% of the probe's
  boundaries; reconnects), at 17:33:28: an alarm invocation completed with no
  log line and left no alarm pending; the cron backstop re-armed it 7 s later,
  one missed boundary (writes 18.6 s apart instead of 10.24). 64 more alarm
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
entry module, one instance: cron addresses it as `idFromName("metronome")`.
Still no routes, `workers_dev = false`, `preview_urls = false`. Listener paths
are unchanged: only cache-served R2 objects.

### Cron invocation (every minute)

1. **Guard step**: unchanged (`guard.ts`).
2. **`index.html`**: unchanged.
3. **Inputs**: unchanged (`readInputs`, `horizon-missing`, `horizon-refused`,
   `gridOf`, `lead-low`).
4. **Lease** (new): `metronome.renew(lease | null)` over RPC, bounded by a 15 s
   timeout (over two 5 s PUT timeouts, plus slack), called **every** invocation
   with the argument the table below names (`null` leaves the DO's lease alone:
   a health check). The DO applies the lease if any, writes the playlist at
   once if its current lease is an unexpired `play` (the off-air notice when
   that lease is blocked), arms its alarm only while the lease's playlist is
   live, and returns its status (below).
5. **Fallback** (new): cron runs today's playlist loop (write now and at each
   boundary until `scheduledTime + 75 s`, `MAX_PUTS` 10) where the table below
   allows, and raises `metronome-down`, when:
   - (a) `renew` throws or times out; or
   - (b) cron sent a `play` lease (blocked or not), `applied` is not
     `superseded`, and either `applied` is not `accepted` or `wrote` is `false`; or
   - (c) `stalls >= 2`: two consecutive renews found no alarm-confirmed tick
     for over `METRONOME_STALE_MS` (30 s) while the chain should be ticking.

   A single stall (the 17:33 class) is repaired by that renew's re-arm, logged
   on the clock line only (`metronome.stalledMs`). By case: normal → `accepted`;
   a DO-side validation mismatch → `invalid` → trigger, cron writes from its own
   verdict; the DO reads `METRONOME` off (version skew) → `off` → trigger; a
   stored lease a deploy made invalid → deleted on load, the fresh one accepted;
   a lagging older blocked lease → accepted, blocks until the next run's newer
   unblocked lease (fail-closed, accepted); a lagging older unblocked lease
   after a newer blocked one → `superseded`, no trigger, the DO stays blocked.
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
- `complete` is set only at the end of the normal path (known verdict, accepted
  horizon, then a healthy renew or a finished fallback loop); every early
  return leaves it false, as today.

**The rollback switch.** Only the exact string `METRONOME = "on"` (new var)
enables the metronome; anything else (unset, `"off"`, a typo) is off. Off: cron
runs today's loop exactly as now. The DO reads `env.METRONOME` itself at the
top of `alarm()` and `renew()`: not `"on"` ⇒ delete the alarm, no write, no
re-arm (`renew` replies `applied: "off"`). Deploying the var change therefore
reaches the DO directly.

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

- **Validation**, on apply **and** on every load from storage (the lease is
  data from another isolate): `kind` is `play` or `hold`; `verdictAt` and
  `validUntil` are finite; for `play`, `blocked` is a boolean and the horizon
  passes `gridOf` with `d === GRID_D`, finite integer `first`/`last`, string
  `epoch_id`, string-or-null `fallback_version`. A malformed `fallback` (not
  null or `{len: number, notice: string}`) becomes `null`, which
  `usableFallback` already treats as no usable fallback. An invalid lease is
  `applied: "invalid"`: the DO deletes its stored lease and alarm (idle) and
  logs `metronome-lease-invalid`. An invalid or unreadable stored lease is
  deleted on load: no lease.
- **Ordering.** Overlapping cron runs are common, so leases can arrive out of
  order. A blocked `play` lease or a `hold` is accepted unconditionally:
  blocking is fail-closed. An unblocked `play` lease is accepted only if there
  is no current lease (none, or expired) or its `verdictAt` is strictly greater
  than the current lease's; otherwise it is `applied: "superseded"`.
- **Expiry** is computed by the DO, not trusted: on accepting a lease it stores
  `expiresAt = min(lease.validUntil, now + METRONOME_LEASE_MS)` by its own
  clock. The check is written negated, `!(now < expiresAt)` ⇒ expired, so a
  NaN or missing value fails closed (the idiom of `pricing.ts`
  `overThreshold`).
- Persisted in DO storage, so a restart or redeploy resumes it.

### Metronome (the DO)

**State lives in DO storage; memory is a cache only** (the object is evicted
between alarms: ~0.5% active time). The stored keys are a fixed set:

- `lease`: validated, with its `expiresAt`;
- `playSince`: when the current unblocked `play` lease was accepted after no,
  blocked, `hold` or expired lease;
- `lastAlarmGoodAt`: the last alarm-confirmed tick (below);
- `lastTarget`: the last armed alarm time;
- `lastBody`: the last successfully written playlist string (~2-3 KB);
- the timestamps of the last 10 PUTs and of the last 12 `alarm()` invocations
  (fixed-size lists: the caps are true rolling windows);
- `stalls`: consecutive renews that found `stalledMs` > 30 s.

**Alarm-confirmed ticks.** Only `alarm()` advances `lastAlarmGoodAt`: on a
successful PUT, a skip because the body equals `lastBody`, or a null
`buildPlaylist` (before the epoch, or no usable fallback; writes nothing by
rule, logged once per lease). A cap-skipped write does not. `renew`'s own write
never advances it, so overlapping renews all see a dead chain.

The lease's playlist is **live** when the lease is an unexpired unblocked
`play` and `isOffair` is false for it at `now`; only then does the chain tick.

**Serialized sections.** The whole of `renew()` and the whole of `alarm()`
after its env check (lease load and apply, re-arm, build, cap check, PUT,
state update) run inside one in-object promise chain (or
`ctx.blockConcurrencyWhile`). The cap slot is reserved, its storage write
awaited, before the PUT is issued. A PUT timeout sets `lastBody` to null (the
bytes in R2 are unknown), so the next write is never skipped as identical.

**`renew(lease | null)`**:

1. `env.METRONOME` not `"on"`: delete the alarm, return `applied: "off"`.
2. Load and validate the stored lease. `stalledMs`, as it stood before this
   call, is `now − max(lastAlarmGoodAt, playSince)` if that lease's playlist
   was live, else 0. Update `stalls`: one more when `stalledMs` >
   `METRONOME_STALE_MS`, else 0.
3. Apply the lease if given (validation and ordering above).
4. If the current lease is an unexpired `play`, write once now: the live
   playlist, or the off-air notice. Skip when the body equals `lastBody`. It
   obeys the PUT cap; a cap-skipped write returns `wrote: null` and is not a
   failure.
5. If the lease's playlist is live and no alarm is pending, arm one (target as
   in `alarm()` step 4). If it is not live, delete any pending alarm.
6. Return:

```ts
interface MetronomeStatus {
  applied: "accepted" | "superseded" | "invalid" | "off" | null; // null: renew(null)
  lease: "play" | "blocked" | "hold" | "none"; // after this call; "none" = absent or expired
  wrote: boolean | null;    // this call's write succeeded; null = no write due (no play lease, identical body, cap, nothing to build)
  lastAlarmGoodAt: number | null;
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
3. Count the invocation. 12 `alarm()` invocations already in the rolling 60 s:
   do not re-arm, log `metronome-alarm-cap`, return. The next `renew` restarts
   the chain.
4. **Re-arm first**, to the first `startMs(n) + 25 ms` strictly after
   `max(now, lastTarget)`, and persist it as `lastTarget`. The target comes
   from the wall clock, never "previous target + d", so lateness never
   accumulates and missed boundaries are skipped, never written in a burst;
   `max(now, lastTarget)` rules out a hot loop when an alarm is delivered
   before the DO's clock passes the boundary. The re-arm has its own
   try/catch: on failure, log `metronome-rearm-failed` and return. Skipped
   when the playlist is not live (e.g. a horizon over 24 h stale): the off-air
   body is written once (step 5) and the next `renew` restarts the chain if
   the inputs changed.
5. Build the playlist for the due boundary, `max(now, lastTarget − 25 ms)`
   with `lastTarget` as it stood before step 4; PUT unless the body equals
   `lastBody`, subject to the cap and the PUT timeout.
6. Update storage (`lastAlarmGoodAt`, `lastBody`, timestamps).

Nothing in `alarm()` ever throws to the runtime: an escaping exception would
hand the chain to the platform's 6-retry backoff. A duplicate or retried alarm
rebuilds the same bytes and skips the PUT: the handler is idempotent.

*As built:* a delivery that finds an alarm already pending takes that
idempotent path (build, PUT only if the bytes differ, no re-arm, not
counted). Verification day (`docs/superpowers/2026-10-16-metronome-verification.md`)
showed that a pending alarm is not by itself a redelivery: once the runtime
has taken an alarm, `getAlarm()` reads null, so a `renew` landing a few ms
before the boundary arms the next one, and the in-flight delivery then finds
it pending (13 times in 34 h, none a real redelivery). So
`metronome-duplicate` is logged only when a counted tick also ran within the
last half segment; the path taken is the same either way.

**Spend bounds (hard, independent of inputs):**

- At most one PUT per `alarm()` and one per `renew()`.
- At most `MAX_DO_PUTS_PER_MINUTE` = 10 PUTs per rolling 60 s window, `renew`'s
  write included; over it the write is skipped and logged (`metronome-cap`),
  and the chain still re-arms. Normal is ~6-8.
- At most 12 `alarm()` invocations per rolling 60 s; over it the chain is not
  re-armed (`metronome-alarm-cap`).
- Each R2 PUT is bounded by a 5 s timeout (`Promise.race`, as `alerts.ts`
  bounds its sends, its timer cleared in `finally`); a timeout is a failed write.
- Only a live playlist runs the alarm chain. Under a blocked lease `renew`
  writes the off-air notice once per call (today's minutely cadence) and
  nothing ticks: a spend trip must reduce DO spend too. A `hold`, an expired
  lease and no lease write nothing.
- A refused horizon (`d` ≠ 10.24) is never in a `play` lease, and the DO's
  validation rejects one as invalid anyway.
- One instance ⇒ duration ≤ ~343k GB-s/month (0.128 GB × a 31-day month),
  inside the 400k allowance; the duration meter guards that invariant.
- The DO's storage is the fixed key set above and never grows; a test pins the
  key set. This is how storage spend is bounded (it cannot be metered, see the
  cost guard).
- Combined worst case, Class A: the DO ≤ 10 PUTs/min plus the cron fallback
  ≤ 10 per invocation, with up to ~3 overlapping invocations, is ≤ 40 playlist
  PUTs in the worst minute, visible to the guard through
  `r2OperationsAdaptiveGroups`: the accepted cost of a fallback minute
  (Decision 1 rejects double writing as the normal mode only).

### Playlist contents

Unchanged rules: `buildPlaylist` with window 16, lookahead 12, hold-back 12,
grace, the fallback loop, the 24 h stale-horizon off-air, ENDLIST-only when
off air without a usable fallback (`offair-without-fallback` is raised by cron
from its own inputs, as now; the DO logs it on a change of state). One
implementation serves both writers: the per-write body of `runClock` (build,
detect off-air-without-fallback, compare bytes, cap, PUT) moves into a shared
module used by the cron loop and the DO.

**Off-air numbering in the DO.** The DO passes `offairSeqMs = now + 75 s` to the
existing `offairSequence` (the cron loop's `max(scheduledTime + loopMs, now)`
shape). Any live playlist written at t ≤ now lists at most `indexAt(t) +
lookahead`, so the notice is strictly above every live segment either writer
has listed, and it never decreases across renews; `buildPlaylist` needs no new
input. The bytes change every renew, so a blocked station costs about one PUT
per minute, as today. Both notices end in ENDLIST.

Unblocking and epoch changes behave exactly as today (players that hit ENDLIST
must press play; a new `epoch_id` restarts numbering).

## Cost guard: Durable Object meters

`pricing.ts` gains three meters, at the published Workers Paid prices (re-check
on the pricing page when the plan is written; checked 2026-10-14 by research,
quotes in the plan). Rows read are bounded by construction (a fixed key set,
capped invocations) and not metered.

| Meter | Included / month | Overage | GraphQL (account-scoped) |
|---|---|---|---|
| `doRequests` | 1,000,000 | $0.15 / M | `durableObjectsInvocationsAdaptiveGroups` `sum.requests`, all types and statuses |
| `doDurationGbS` | 400,000 | $12.50 / M | `durableObjectsPeriodicGroups` `sum.duration` |
| `doRowsWritten` | 50,000,000 | $1.00 / M | same, `sum.rowsWritten` |

They join `USAGE_QUERY` as period-to-date and recent-window queries, like the
existing four. Touch points: `METERS`, `Usage`, `OpCounts`, `Reading`,
`evaluateSpend`'s literals, `meter.ts`'s parsing, `latch.ts` `stored()`. Both
datasets serve a 32-day period and the current minute (measured, above), so
`LAG_MS` holds. A dataset that cannot serve the period is a failed reading;
never price a meter at zero for want of data (the blind rule trips after 6 h).

- **Empty is not zero.** A range with no DO activity reads as `[]`. While
  `METRONOME` is `"on"`, a reading whose recent-window `doRequests` or
  `doRowsWritten` is 0 is a failed reading: cron renews every minute, so the
  true count cannot be 0. For up to `LAG_MS` after the switch is flipped on,
  readings fail this way; harmless, since the blind rule needs 6 h.
- **Storage is not metered.** `durableObjectsStorageGroups` returns no rows for
  this account, so stored bytes cannot be read. They are bounded by
  construction instead (the fixed key set, under Spend bounds), far inside the
  5 GB-month allowance.
- **Rows written.** The probe's `rowsWritten` (~1 per alarm) is below what the
  docs bill (a put plus a `setAlarm` = 2 rows). At 4-6 keys written per tick,
  rows run ~30-50× under the allowance, so no correction is made; verification
  compares the meter with the dashboard's billable usage.

## Observability

The DO logs only anomalies, on a change of state rather than per tick (once per
lease or per episode): `metronome-late` > 2 s, `metronome-put-failed`,
`metronome-expired`, `metronome-cap`, `metronome-alarm-cap`,
`metronome-rearm-failed`, `metronome-lease-superseded`,
`metronome-lease-invalid`, `metronome-hold`, `offair-without-fallback`, and a
null build. Each DO invocation is itself a Workers Logs event (~10k/day, far
inside the allowance). Cron's `clock` line gains a `metronome` object (the
`renew` status, or the fallback reason). Verification analyses freezes from
the clock lines plus a `wrangler tail` of the DO's anomaly lines.

## Failures and alerts

| Failure | Behaviour | Alert |
|---|---|---|
| DO PUT fails or times out (5 s) | logged, `lastBody` cleared; the next tick retries | log only |
| `renew` throws or times out, or trigger (b): renew's write failed, or the lease is `invalid` or the DO reads the switch off | cron runs the loop where the lease table allows | `metronome-down` |
| `alarm()` throws after re-arming | caught; the chain continues | log only |
| re-arm fails | logged `metronome-rearm-failed`; the next `renew` restarts the chain | log only |
| alarm chain broken once (as 2026-10-14 17:33) | the next `renew`'s re-arm repairs it | log only (`metronome.stalledMs` on the clock line) |
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
- **Known limitations.** An alarm chain that breaks with no error (measured
  once in the probe's captured span) freezes the playlist until the next renew,
  up to one cron gap (≤ ~200 s on a bad day); the rollout pass criterion counts
  such freezes. During a fallback minute the two writers' off-air
  MEDIA-SEQUENCE can differ (cosmetic: both end in ENDLIST). The "logged once"
  marks are memory only and the object is evicted between ticks, so a
  persisting anomaly may log every tick (inside the Workers Logs allowance).

## Rollout

1. Tear down `alarm-probe` per its README (`STOP=1` deploy, then
   `wrangler delete`); its DO would otherwise appear in the account-wide meters.
2. Deploy with `METRONOME` not `"on"`: the DO class exists (SQLite-backed;
   migration form per the current wrangler: `new_sqlite_classes` or the
   declarative `exports` field, checked with `wrangler deploy --dry-run`), and
   the guard's new meters read. **Pass** only when `state/guard.json`'s
   `last_error` is null and its `period_to_date` carries all seven meters.
3. Flip to `METRONOME = "on"`.
4. Verification day: a 24 h `wrangler tail antenna` including a weekday daytime.
   **Pass:**
   - no playlist freeze > 45 s outside a reported `metronome-down`, except
     silent chain breaks: at most 1-2 in the day, each tied to a logged single
     stall (provisional: the probe's handler did no R2 PUT);
   - the DO meters in `guard.json` agree with the dashboard's billable usage;
   - playlist PUTs at most ~one per boundary plus one per renew (≈ 7/min,
     ≈ 10k/day), counted from the DO and clock lines; below today's rate is
     expected.

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
  non-boolean `blocked`, a horizon failing `gridOf`, with `d` ≠ 10.24 or a bad
  `first`/`last`/`epoch_id`/`fallback_version`, non-finite `verdictAt` or
  `validUntil`) is `invalid`, logged, and leaves no stored lease and no alarm;
  a bad `fallback` is `fallback: null`, not invalid; an invalid or unparseable
  stored lease is deleted on load (no write, no re-arm).
- Lease ordering: an unblocked `play` lease with `verdictAt` ≤ the current
  lease's is `superseded`, equal included; a blocked `play` lease and a `hold`
  are accepted whatever their `verdictAt`.
- Expiry: `expiresAt` is `min(validUntil, now + 15 min)`, so a far-future
  `validUntil` still expires at 15 min; a NaN or missing value is expired;
  after expiry an alarm writes nothing and does not re-arm; `renew` with a new
  lease restarts it.
- `hold`: no PUT, no pending alarm. Blocked: `renew` writes the notice, no
  alarm pending after; an alarm delivered anyway writes nothing, no re-arm.
- Off-air numbering: the notice is numbered above `indexAt(now) + lookahead`
  and never decreases across renews.
- An unblocked lease whose horizon goes over 24 h stale: `alarm()` writes the
  off-air body once and does not re-arm; `stalls` stays 0.
- Confirmed ticks: a duplicate alarm for the same boundary (identical body, no
  second PUT) and a null build (before the epoch; no usable fallback; one log
  line per lease) both advance `lastAlarmGoodAt`.
- Stalls: `renew`'s own write never advances `lastAlarmGoodAt`, so two
  overlapping renews over a dead chain both count; `stalledMs` is measured
  from `playSince` when the play lease is newer than the last alarm tick.
- Caps: the 11th write in 60 s is skipped and logged, a cap-skipped `renew`
  write returns `wrote: null` without triggering the fallback, and the chain
  re-arms; the 13th `alarm()` in 60 s does not re-arm and logs
  `metronome-alarm-cap`. Window edge, for both: just over 60 s after the
  oldest stored timestamp is allowed, just under is not.
- Re-arm target: the first boundary + 25 ms strictly after
  `max(now, lastTarget)`; an alarm delivered before the DO's clock passes its
  boundary builds for that boundary and does not re-arm to the same target;
  `lastTarget` is persisted.
- A re-arm failure logs `metronome-rearm-failed` and returns; an exception
  anywhere in `alarm()` never propagates.
- A PUT that does not settle within 5 s is a failed write and sets `lastBody`
  to null; the next identical body is written.
- Interleave: a fake bucket whose `put` resolves on demand, plus a concurrent
  `renew`; the cap and `lastBody` stay consistent.
- Storage: the DO's stored key set is exactly the fixed set.
- Cron's lease table: each outcome passes the table's `renew` argument, and the
  fallback loop writes only on a known verdict with an accepted horizon; every
  early-return path calls `renew`.
- Cron fallback: each of triggers (a)-(c), including `applied: "invalid"` and
  `"off"` after a `play` lease, → the legacy loop runs where allowed and
  `metronome-down` is raised; `superseded` → no trigger; a single stall → no
  fallback, no alert, `stalledMs` on the clock line; a healthy status → no cron
  PUTs and a complete alert batch, except that guard-unknown with a healthy
  `renew(null)` stays incomplete (no guard-family key resolves).
- Cron addresses the stub by the fixed name; `renew(null)` leaves the lease
  untouched and still writes from a current `play` lease.
- The switch: only `"on"` enables; unset, `"off"` or a typo → cron runs the
  legacy loop unchanged, and the DO's `alarm()` and `renew()` delete the alarm
  and write nothing. The existing clock tests keep passing in this mode.
- Pricing: each new meter priced through its allowance; every `METERS` entry is
  finite in `periodToDate`, `projected` and the stored doc; a meter with a zero
  price fails a per-meter pricing test; a NaN or missing DO reading trips
  (`overThreshold`), as for the existing meters; `USAGE_QUERY` parsing of the
  new datasets, including a truncated result; with the switch on, a recent
  `doRequests` or `doRowsWritten` of 0 is a failed reading.
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
