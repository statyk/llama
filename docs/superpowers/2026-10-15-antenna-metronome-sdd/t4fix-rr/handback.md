### Finding Verdicts
- **Item A: renew persists the accepted lease before any alarm op** — ADDRESSED. `antenna/src/metronome-engine.ts:206-207` adds `await this.flush(tx)` inside `if (applied === "accepted")`, right after `s.lease`/`s.playSince` are set and before step 4 (`write`, :213) and step 5 (`setAlarm` :218, `disarm` :222). Path by path (engine :164-227 at d555ee2):
  - **Hold, blocked, play, identical, cap-skipped, null build, accepted-already-expired:** each of these has `applied === "accepted"`, so the lease is stored at :207. The alarm ops are all downstream of that line. An expired-on-accept lease is stored, `cur` is then null, and `disarm` runs after the store.
  - **Invalid:** the existing `flush(tx, true)` runs before `disarm` (:188-189), so it was already correct. An invalid *stored* lease is deleted in `begin()` (:90-94), before anything else.
  - **Superseded and absent (`renew(null)`):** no lease state changes. The stored lease is already correct, so no early store is needed.
  - **Switch off (:166-169):** no lease is applied. Not touched by the fix.

  **Invariants:**
  - **At least one row per renew:** holds. The final `flush(tx, true)` (:224) still writes `stalls` unconditionally on every non-invalid and non-off path. The invalid path's `flush(tx, true)` covers that path.
  - **Cap reservation before the PUT:** holds. `write()` still records `putTimes` and awaits `flush(tx)` before `boundedPut` (:150-152), unchanged. Because the early flush updates `tx.stored` (:103), the reservation diff carries only `putTimes`. That ordering is pinned by the existing "save putTimes before put" test, which the implementer reports passing unchanged.
  - **`lastTarget` after arming:** holds. It is assigned after `setAlarm` (:218-219) and stored in the final flush. If `setAlarm` throws, `lastTarget` is neither assigned nor stored.
  - **No double-counting:** confirmed. `flush` diffs against `tx.stored` and then resets it (:99-104). It touches no counters. `nextStalls` runs once (:180) and `recordTime` once per PUT (:150).

  **Test:** `antenna/test/metronome-renew.test.ts:170-187` adds one `it` with two halves. The hold half replaces a live play lease that has a pending alarm, with `failDeleteAlarm`. The blocked half uses an identical body, so there is no PUT and no reservation flush to mask the bug, plus a pending alarm and `failDeleteAlarm`. Both assert that the renew rejects and that the stored lease is the new one. The new `FakePort.failDeleteAlarm` (`test/metronome-support.ts:69`) throws before it records the op, mirroring `failSetAlarm`. The report shows RED for the hold half on the old code ("expected { kind: 'play' … } to match { kind: 'hold' }"). It also shows RED for the blocked half on its own, run in a scratch copy with the old engine (the old verdictAt T was still stored). GREEN is 56/56 focused, 308/308 on the full suite, and typecheck exits 0. The error model is unchanged: renew rejects, which cron reads as trigger (a).

  **Cost:** no spend bound changes. DO rows are billed per key written, not per `save` call (`stateChanges` emits one entry per changed key). The lease and `playSince` rows used to go out in the final flush and now go out in the early one, so they moved rather than multiplied. The only duplicate is `stalls`, and only on a renew that both accepts a lease and changes the stall count: that renew writes `stalls` in both flushes. The worst case is +1 row per renew. At about one renew a minute that is about 44k rows a month, against the 50M allowance, which the spec already puts 30-50x above use (spec "Rows written"). The guard prices measured `rowsWritten` in any case, so nothing would go unpriced.

- **Item B: trigger (b) covers blocked leases (`s.lease !== (sent.blocked ? "blocked" : "play")`)** — ADDRESSED. The condition is at `antenna/src/metronome-core.ts:303`, inside the unchanged `sent?.kind === "play" && s.applied !== "superseded"` guard, and the doc comment is updated at :296-297.

  **No false positives.** On an accepted renew the engine sets `s.lease = storedLease(sent, now)` (core :122-124) and nothing later in renew changes `s.lease`. The reply's `lease` is `leaseKind(s.lease, now)` (engine :225), with the same `now`. `leaseKind` (core :136-141) returns `"none"` if the lease is expired, and otherwise `c.blocked ? "blocked" : "play"`. So for a sent blocked lease the reply can only be `"blocked"`, or `"none"` when it was accepted already expired; for an unblocked lease, only `"play"` or `"none"`. Trigger (b) fires on `"none"` alone, which is exactly the "neither writer running" case. It cannot fire on a healthy accepted lease.

  **Tests:** the loop test (`test/metronome-core.test.ts:242-253`) now feeds each lease its producible reply (`told`), which fixes the impossible `b`→`"play"` reply. The accepted-not-doing test (:271-278) adds b/none → (b) "…to a blocked play lease" and b/blocked → null. No new `it` was added. RED is shown on the old source: b/none returned null.

### New Breakage in the Fix Diff
None.

Minor note (not blocking): the blocked half of the new test sets `port.alarmAt = T + 5_000` by hand rather than reaching a pending alarm through a prior live lease. It still exercises the real `disarm` → `deleteAlarm` path and is adequate.

### Out-of-Scope Observations
None.

### Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage.
