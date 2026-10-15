# Known findings after round 1 (and how the spec now handles each)

1. A blocked lease kept the alarm chain ticking, so a spend trip had no lever on DO spend → only a current, valid, unblocked play lease ticks; blocked: renew writes the notice once per call, no alarm.
2. The off-air pin / highestListed machinery → removed; the DO numbers the notice with `offairSequence(g, now, now + 75 s, lookahead)`, above any live segment either writer listed and non-decreasing across renews.
3. The lease's `validUntil`/`scheduledTime` trusted, NaN fails open → full lease validation on apply and load (invalid = hold); the DO computes `expiresAt = min(validUntil, now + 15 min)` itself and checks it negated.
4. Ordering by `scheduledTime` could reject a newer blocked verdict from a lagging run → blocked/hold accepted unconditionally; unblocked play accepted only if its `verdictAt` (guard step start) is strictly newer. Limitation: a stale blocked lease can block until the next run.
5. A known blocked verdict was dropped when inputs failed → `renew(hold)` on that path.
6. Cron's early-return paths and the fallback on an unknown verdict were undefined → per-path table (renew argument + whether the fallback may write); the fallback writes only with a known verdict and an accepted horizon.
7. `lastGoodAt`, `lastRenewAt`, last bytes in memory, but the DO is likely evicted between alarms → all state in DO storage (memory is a cache), including a hash of the last written bytes.
8. The failures table and the fallback rule disagreed on a broken chain; a single break would page daily → fallback only on renew throw/timeout, a failed renew write, or `stalls >= 2` consecutive stalled renews; a single stall is logged only; the residual freeze (≤ one cron gap, about daily) is a documented limitation.
9. The probe's "no skipped boundary" claim was wrong (its instrument could not see a chain break) → corrected.
10. `alarm()`'s finally re-armed after a failed lease read and could throw → order: validate → (not current unblocked play: delete alarm, return) → re-arm first, in its own try/catch → build → bounded PUT → storage; nothing throws to the runtime.
11. Re-arm rule bounded the target, not the rate (early delivery could hot-loop) → target strictly after `max(now, lastTarget)`; alarm-invocation cap 12 per 60 s.
12. Cap semantics and the combined two-writer Class A bound unstated → renew's write obeys the cap; a cap skip is `wrote: null`, not a failure; combined worst case stated (≤ ~40 playlist PUTs/min).
13. renew/alarm interleave across the R2 await → all write paths serialized; the cap slot is reserved before the PUT; the lease read-compare-write happens before any non-storage await; the PUT has a 5 s timeout.
14. Rollback switch depended on the DO's RPC, unknown values undefined → only "on" enables; the DO reads `env.METRONOME` itself; cron runs the legacy loop first, then a bounded `stop()`.
15. An empty DO dataset is read as zero → while METRONOME is "on", recent `doRequests` = 0 is a failed reading.
16. "evaluateSpend unchanged" was false (meters are enumerated in pricing.ts and latch.ts) → touch points named; a per-meter finiteness test; rollout step 2 checks all meters in `guard.json`.
17. DO dataset range/lag/units unmeasured → measured 2026-10-14 (32-day range OK, lag < 1 min, empty → `[]`).
18. `cron-silent` alert: inline sends, failed-send retry storm, resolve inside renew, the 4-min margin → REMOVED; the DO sends no alerts. A dead cron is detected by hugo (dead-clock after the lease lapses; `guard_stale_minutes` 45).
19. Null playlist under a play lease → a confirmed tick.
20. `offair-without-fallback` lived in cron's write path; batch completeness after a healthy renew → cron computes it from its inputs before the lease; `complete = true` after a healthy renew or a finished fallback loop.
21. Per-tick log volume → the DO logs on state change; volume restated (~10k events/day, inside the allowance).
22. Testability of DO time → pure `metronome-core.ts` with a fake clock plus a thin DO wrapper.
23. Single-instance invariant → a test; `locationHint: "enam"`.
24. rowsWritten under-reports setAlarm → noted; rows ~100× under the allowance; verified against the dashboard.

## Removed by the revision
- the `offairSeq` pin and `highestListed`;
- the `cron-silent` alert and `CRON_SILENT_MS`;
- the `doStorageGbMonth` meter (the storage dataset returns no rows for this account; storage is bounded structurally by a fixed key set);
- the status fields `putsSinceRenew`, `maxLateMsSinceRenew`, and `armed` in the fallback decision;
- `scheduledTime` as the ordering key;
- the forced (uncompared) renew write.
