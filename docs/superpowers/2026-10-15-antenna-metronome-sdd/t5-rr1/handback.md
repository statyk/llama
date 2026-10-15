### Finding Verdicts
- **Important: after an early genuine tick, a pre-boundary duplicate (2b) or a pre-boundary renew writes an OLDER playlist, and MEDIA-SEQUENCE goes backwards.** ADDRESSED.
  - The fix is a helper at `antenna/src/metronome-engine.ts:59-60`: `tickBoundary = max(now, (lastTarget ?? now) - gridOf(lease.horizon).dMs - ALARM_SLACK_MS)`. It is used at the duplicate path, `:207`, and at renew step 4's write, `:294`. Both sites pass `s.lastTarget` as loaded. 2b never re-arms. Renew arms only in step 5 (`:298-303`), after the write. This matches the controller's ruling exactly.
  - No "refuse a lower MEDIA-SEQUENCE" rule was added. The genuine tick's step 5 (`:239`) is untouched.
  - Tests: two new `it`s at `antenna/test/metronome-alarm.test.ts:54` (duplicate) and `:69` (renew). They reproduce the reviewer's probes: `deliver` at target(1001)−40, then a duplicate or renew at target(1001)−35. They assert no PUT, identical bytes, MEDIA-SEQUENCE not lower, alarmAt and lastTarget still target(1002), and no alarm ops (duplicate case). The renew case also asserts `wrote: null`.
  - The implementer's report records RED on the pre-fix code: `expected 3 to be 2` (an extra PUT) and `wrote: true`. Those match the probes. GREEN: 336/336, typecheck clean. The existing epoch-change, post-tick-duplicate and duplicate-then-renew tests run unmodified. I did not re-run anything: I had no specific doubt.
- **Minor (folded): the carry test could not tell the step-2 return from a caught exception.** ADDRESSED. `metronome-alarm.test.ts:198` adds `expect(port.events("metronome-alarm-error")).toEqual([])`. That event name matches the catch-all at `metronome-engine.ts:87`.

#### Explicit checks on `tickBoundary`
A genuine tick re-arms `lastTarget = nextTarget(g, max(t0, prev)) = start(k+1)+25`, where `k = indexAt(max(t0, prev) − 25)`. So `tickBoundary = max(now, start(k))`, and `start(k) ≤ max(t0, prev) − 25 ≤ max(t0, prev − 25)`, which is the genuine tick's own `due`.
- **lastTarget set by renew's own arm:** reduces to `now`. Renew arms from `max(now_r, lt_old)`. When `lt_old ≤ now_r`, `start(k) ≤ now_r − 25 < now`.
- **lastTarget absent:** reduces to `now`, since `now − D − 25 < now`.
- **lastTarget stale after a disarm:** reduces to `now`. `disarm()` (`:126-128`) leaves `lastTarget` in place. A past value gives `now`. A pending target left in the future gives `start(k)`, which is at most the tick's own boundary, so it is ≤ now unless that tick was early. See the out-of-scope corner below.
- **Post-boundary duplicate:** reduces to `now`, because `start(k) ≤ t0 ≤ now`. This holds even when `t0` falls in `[start(k), start(k)+25)`.
- **Epoch change** (lastTarget on the old grid, horizon on the new one): sane.
  - The helper works in milliseconds, not segment indices. The old-grid boundary time is mapped onto the new grid by `indexAt` inside `buildPlaylist`.
  - The only overshoot past `now` is the earliness of the old grid's last genuine tick, which is tens of ms.
  - In the existing epoch test the old target is long past, so it reduces to `now`.
- **Never builds further ahead than the genuine tick:** holds. `tickBoundary ≤ due` of the tick that set `lastTarget`, so the build time is at most `max(now, that due)`.
- **Blocked/off-air numbering:** untouched.
  - The alarm path returns on a blocked lease at step 2 (`:194`), before 2b.
  - Renew's write still passes `now + MAX_LOOP_MS` as `offairSeqMs` (`:153`). `offairSequence` numbers from `max(seqMs, nowMs)` (`playlist.ts:79-81`). `tickBoundary` exceeds `now` by at most one segment (10.24 s), well under 75 s, so the number still comes from `now + 75 s`.

### New Breakage in the Fix Diff
None.

### Out-of-Scope Observations
- **Theoretical corner (non-blocking).** This rests on renew's step-5 arm, which predates the fix: renew arms from `max(now, lastTarget)` even when `lastTarget` is a stale future value left by a disarm. The sequence, all in one segment j:
  1. An alarm is pending at start(j+1)+25.
  2. A hold or blocked renew disarms it.
  3. A play renew arms start(j+2)+25. Boundary j+1 is skipped, and that skip predates this fix.
  4. A third renew (or a spurious delivery) builds for start(j+1), up to ~10 s early.
  
  Nothing is built older than before and MEDIA-SEQUENCE never decreases. It needs three renews inside one 10.24 s segment, which a once-a-minute cron cannot produce. No renew call sites are wired yet. Worth a glance when the cron wiring lands; nothing to do in this task.

### Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage.
