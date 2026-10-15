# Round-1 decisions for the metronome spec

Apply each decision exactly. "Remove" means remove every trace (tables, status fields, tests,
rollout, observability, failures table, open questions).

## A. Blocked and hold stop the chain (all 4 reviewers; L + D)

A1. A `play` lease with `blocked: true` no longer runs an alarm chain. The DO ticks ONLY under a
    current, valid, unblocked `play` lease. Under a blocked lease, `renew` writes the off-air
    playlist once per call (the minutely cadence today's cron already has) and does not arm;
    `alarm()` under a blocked lease writes nothing, does not re-arm, and deletes any pending alarm.
    Rationale to state: a spend trip must reduce DO spend too; constant off-air bytes gain nothing
    from ticking.
A2. Off-air numbering in the DO: remove the `offairSeq` pin and `highestListed` (state, text,
    tests). The DO numbers the notice with the existing `offairSequence(g, now, now + 75_000,
    lookahead)` (i.e. `seqMs = now + MAX_LOOP_MS`), the same rule shape as cron's
    `max(scheduledTime + loopMs, now)`. Justify in one or two sentences: any live playlist written at
    t ≤ now lists at most `indexAt(t) + lookahead`, so the notice is strictly above every live segment
    either writer has listed (the cron fallback's invocation was scheduled ≤ now), and it never
    decreases across renews. `buildPlaylist` therefore needs no new input; remove the sentence saying
    it gains one. Note the bytes change every renew, so blocked costs ~1 PUT per minute (1,440/day),
    the same as today.
A3. Remove the "Blocked steady state … one PUT then skips … cron does not fall back" test and the
    "While blocked the off-air bytes are constant and the DO PUTs once then skips" rationale from
    "Confirmed ticks". Replace the test with: "blocked lease: renew writes the notice, no alarm is
    pending afterwards, an alarm delivered anyway writes nothing and does not re-arm".

## B. Lease validation, local expiry, ordering (all 4; L)

B1. The DO validates every lease on apply AND on every load from storage: `kind` ∈ {play, hold};
    for play: `typeof blocked === "boolean"`, horizon passes `gridOf` and `d === GRID_D`,
    `fallback` is null or an object with numeric `len` and string `notice`; `verdictAt` and
    `validUntil` finite. Anything invalid is treated as `hold` and logged `metronome-lease-invalid`.
    An unreadable or unparseable stored lease is "no lease" (no write, no re-arm).
B2. Expiry is computed by the DO, not trusted: on accept it stores
    `expiresAt = min(lease.validUntil, now + METRONOME_LEASE_MS)` (DO clock). The check is written
    negated, `!(now < expiresAt)` ⇒ expired, so NaN/undefined fail closed. Cite the existing idiom
    (pricing.ts `overThreshold`). Remove "both from Cloudflare clocks" reasoning.
B3. Ordering. Replace the `scheduledTime` key with `verdictAt` = the time cron's guard step began
    (the moment its state reads started). Rules:
    - a blocked `play` lease or a `hold` is accepted unconditionally (blocking is fail-closed);
    - an unblocked `play` lease is accepted only if its `verdictAt` > the current lease's
      `verdictAt` (strictly; no tie rule);
    - limitation to state: a stale blocked lease from a lagging older run can block the station
      until the next run's lease (≤ about one cron gap); accepted as the fail-closed direction.
    The lease type gains `verdictAt`, loses `scheduledTime` as the ordering key (keep `scheduledTime`
    only if needed for logs; prefer removing it). `issuedAt` stays only if used; otherwise remove.
B4. The lease read-compare-write in `renew` touches DO storage only, before any R2 PUT or fetch
    await (so input gates serialize it).

## C. Which lease cron issues (L/P; Opus strict, Fable strict, Opus breadth, Fable breadth)

C1. Replace the lease table with a per-path table that names, for each cron outcome, the `renew`
    argument AND whether the fallback loop may run:
    | guard unknown / crashed | `renew(null)` | fallback never writes (no known verdict) |
    | verdict known, inputs read threw, or horizon missing/unreadable, blocked=false | `renew(null)` | fallback never writes |
    | verdict known blocked, inputs unusable (threw, missing, unreadable) | `renew(hold)` | fallback never writes |
    | horizon refused (d ≠ 10.24) | `renew(hold)` | fallback never writes |
    | verdict known, horizon accepted | `renew(play{blocked, horizon, fallback})` | fallback may run |
    State plainly: the fallback loop runs only with a known verdict and an accepted horizon; with
    anything less it writes nothing, as today.
C2. runClock restructure, stated as a contract (no code): every early-return path still calls
    `renew` as in the table before returning; `offairWithoutFallback` is computed by cron from its
    inputs before issuing the lease (the condition is raised by cron as today; the DO only logs on
    the state change); the alert batch is `complete = true` after a healthy renew or a finished
    fallback loop.

## D. State lives in storage; memory is a cache (both breadth reviewers; P)

D1. State list in DO storage: `lease` (validated, with `expiresAt`), `lastGoodAt`, `lastTarget`
    (the last armed alarm time), `lastBytesHash` (hash of the last successfully written body), the
    PUT window counter, the alarm-invocation window counter, `stalls` (C/E below). Memory is a cache
    only. State why: the probe measured 0.5% active time, consistent with the object being evicted
    between alarms (the docs: hibernation after ~10 s idle).
D2. Status: remove `putsSinceRenew` and `maxLateMsSinceRenew` (and from the clock line description);
    the DO's own `metronome-late` log covers lateness. Remove `armed` (renew ensures it; tautological)
    and `accepted` from the fallback decision (keep `accepted` in the status only as a logged field).
D3. A tick where `buildPlaylist` returns null (before the epoch; no usable fallback) is a confirmed
    tick: `lastGoodAt` advances, `wrote: null`, logged once per lease.
D4. Identical-bytes skip compares against `lastBytesHash` in storage; a skip is a confirmed tick.
    `renew` writes (not forced) unless the body hashes equal to `lastBytesHash` AND
    `now - lastGoodAt` < d; this replaces "force: bytes are not compared".

## E. Health, fallback trigger, broken chain (both breadth; P)

E1. Cron falls back (and raises `metronome-down`) only when: `renew` throws or times out; or under
    a current unblocked `play` lease, renew's write failed (`wrote: false`); or `stalls >= 2`.
    `stalls` is a DO-stored count of consecutive renews that found `stalledMs > 30 s` under a
    current unblocked play lease (reset to 0 by a renew that does not). A single stall (the 17:33
    class) is repaired by that renew's write and re-arm and is logged on the clock line only
    (`metronome.stalledMs`), with no alert.
E2. Write the residual into the spec as a documented limitation: a silent chain break (measured
    once in ~21 h) freezes the playlist until the next renew, up to one cron gap (≤ ~200 s on a bad
    day); the rollout pass criterion counts such freezes and expects ≤ 1-2 per day, each tied to a
    logged single stall.
E3. Fix the failures table to match E1 (broken chain: log only, single stall; repeated: fallback +
    `metronome-down`).
E4. Correct the "Problem (measured)" probe text: the probe's `skipped` field cannot see a chain
    break (it is computed against the re-armed target); the 17:33 event was one missed boundary
    (writes 18.6 s apart). Do not claim "no skipped boundary".

## F. alarm() structure and runaway bounds (both strict + breadth; L)

F1. Order inside `alarm()`: validate/load lease (B1) → if not a current unblocked play lease:
    delete any pending alarm, return (no re-arm) → re-arm FIRST to the next target (F2) → build →
    write (bounded, F4) → update storage. The re-arm is in its own try/catch: on failure log
    `metronome-rearm-failed` and return; nothing in `alarm()` ever throws to the runtime (state that
    an escaping exception would hand the chain to the platform's 6-retry backoff). Remove "finally
    re-arms unless step 1 returned".
F2. Re-arm target = the first `startMs(n) + 25 ms` strictly after `max(now, lastTarget)`, and
    persist it as `lastTarget`. This rules out a hot loop when an alarm is delivered before the DO's
    clock passes the boundary.
F3. Add an alarm-invocation cap: more than 12 `alarm()` invocations in a rolling 60 s ⇒ do not
    re-arm, log `metronome-alarm-cap`; the next renew restarts the chain. Keep the PUT cap
    (`MAX_DO_PUTS_PER_MINUTE` = 10) and state that renew's write obeys it; a cap-skipped write
    returns `wrote: null` and is not a failure (does not trigger fallback).
F4. The R2 PUT is bounded by a timeout (5 s, `Promise.race`, as alerts.ts bounds its sends); a
    timeout is a failed write.
F5. Serialize all write paths in the DO (alarm and renew) behind one in-object promise chain or
    `ctx.blockConcurrencyWhile` around build → cap reservation → PUT → state update; the cap slot is
    reserved (storage write awaited) before the PUT is issued.
F6. State the combined worst-case Class A: DO ≤ 10/min + cron fallback ≤ 10 per invocation, with up
    to ~3 overlapping invocations ⇒ ≤ 40 playlist PUTs/min in the worst minute; bounded, and visible
    to the guard via `r2OperationsAdaptiveGroups`. Note the double-writer minute is the accepted
    bounded cost of the fallback (Decision 1 rejected double writing as the NORMAL mode).
F7. Add to "Spend bounds": the DO's storage is a fixed set of keys (D1) and never grows; a test
    pins the key set. (This is how storage spend is bounded; see G3.)
F8. Location: `idFromName("metronome")` with `locationHint: "enam"` on `get`; one sentence.
F9. Add a test that cron addresses the stub by the fixed name (single instance).

## G. Cost guard (strict + breadth; L/P)

G1. Replace "flow through `evaluateSpend` … unchanged" with the touch points: `METERS`, `Usage`,
    `OpCounts`, `Reading`, `evaluateSpend`'s literals, `meter.ts` parsing, `latch.ts` `stored()`
    (what `guard.json` shows). Test: every `METERS` entry is finite in `periodToDate`, `projected`
    and the stored doc; a meter with a zero price fails a per-meter pricing test.
G2. Record the measurements made 2026-10-14 (author, against this account, read-only): the DO
    invocations and periodic datasets accept 31- and 32-day ranges (`datetime`/`datetimeMinute`
    filters) and their totals matched the probe's expected counts (~9.67k requests, ~8.25k rows over
    23.5 h); both have the current minute (lag < 1 min, within `LAG_MS` 5 min); a range with no DO
    activity returns `[]` (indistinguishable from zero). Move these from "Open questions" to the
    measured context; remove the corresponding open-question bullet.
G3. Remove the `doStorageGbMonth` meter: `durableObjectsStorageGroups` returned no rows for this
    account even over 32 days while the probe held keys, so it cannot be read; storage is bounded
    structurally instead (F7). Keep four DO meters: requests, duration, rowsWritten, rowsRead.
G4. Empty-is-zero guard: while `METRONOME` is "on", a reading whose recent-window `doRequests` is
    0 is a failed reading (cron renews every minute, so the true count cannot be 0). State the
    transient: for up to `LAG_MS` after flipping on, readings fail; harmless (the blind rule needs
    6 h).
G5. Note: the probe's `rowsWritten` (~1 per alarm) is below the docs' billing (put + setAlarm = 2
    rows); rows are ~100× under the allowance, so no correction; verification compares the meter to
    the dashboard's billable usage. Rollout step 2 passes only when `guard.json`'s `last_error` is
    null and `period_to_date` carries all eight meters.

## H. Rollback switch (all 4; L)

H1. Only the exact string `"on"` enables the metronome; anything else (unset, typo) is off.
H2. The DO reads `env.METRONOME` itself at the top of `alarm()` and `renew()`: not "on" ⇒ delete
    the alarm, no write, no re-arm. So deploying the var change reaches the DO directly.
H3. With the switch off, cron runs the legacy loop first and calls `stop()` after its first write,
    bounded by the same 10 s timeout; a failed `stop()` is logged only (H2 makes it redundant).

## I. Remove `cron-silent` (D; Fable breadth suggestion, all four found defects in it)

I1. Remove the `cron-silent` alert entirely: the alarm step, the flag in storage, the resolve in
    renew, `CRON_SILENT_MS`, the failures-table row's alert, the tests, the channel plumbing in the
    DO. The DO then sends no alerts at all.
I2. State the replacement: a dead cron keeps the station playing for at most 15 min on its lease;
    then the playlist freezes and hugo's dead-clock check alerts; independently hugo alerts when
    `guard.json`'s evaluation is older than `guard_stale_minutes` (45). Detection of a cron outage is
    therefore ~15-17 min instead of ~2-4 min today; accepted.

## J. Observability, testability (P)

J1. The DO logs anomalies on state change, not per tick (e.g. `offair-without-fallback`, lease
    invalid, cap hit: once per lease or per episode). Restate the volume: each DO invocation is
    itself a Workers Logs event when observability is on, so expect ~10k events/day, far inside the
    included allowance; drop "near today's ~1,440".
J2. Testability: the DO's logic lives in a pure module (`metronome-core.ts`: e.g.
    `applyLease(state, lease, now)`, `tick(state, now)` returning the actions) tested with a fake
    clock; a thin DO wrapper is tested with `runInDurableObject`/`runDurableObjectAlarm` for storage
    and alarm plumbing.
J3. Add an interleave test: a fake bucket whose `put` resolves on demand plus a concurrent `renew`;
    the cap and the identical-bytes state stay consistent.

## Not accepted (record in known-findings)

- Location-hint as a correctness issue: accepted only as F8 (one argument).
- Pricing rows ×2: rejected (G5).
- Ordering by `issuedAt` (Opus strict's suggestion): rejected in favour of `verdictAt` (B3) because a
  lagging run's later `issuedAt` can carry an older guard reading.
