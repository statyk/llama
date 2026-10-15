# Round-2 decisions: SIMPLIFY (the spec must not grow)

Hard constraint: the spec is 535 lines; after this edit it must be **at most 535 lines, and
shorter is better**. Prefer deleting text to adding it. Where a decision below replaces a
mechanism, delete the old text entirely before writing the new rule.

## R1. Lease handling: replace with this rule (state it in a few lines)

The DO's reply to `renew` carries `applied: "accepted" | "superseded" | "invalid" | "off"` and
`lease: "play" | "blocked" | "hold" | "none"` (the DO's lease after the call).

- `invalid`: the lease failed validation. The DO stores nothing from it, deletes its stored lease
  and its alarm (so it is idle), and says so. An invalid STORED lease on load is likewise deleted
  and treated as no lease. Remove the "stamped with the DO's own now / verdictAt" text entirely.
- `off`: `env.METRONOME !== "on"` in the DO; it deletes its alarm and does nothing else.
- `superseded`: a valid unblocked play lease older (by `verdictAt`) than the DO's current lease.
- Acceptance rules stay: blocked/hold accepted unconditionally; unblocked play accepted when there
  is no current lease or its `verdictAt` is strictly newer than the current one's.
- Validation: as now, plus finite integer `first`/`last`, string `epoch_id`, string-or-null
  `fallback_version`. An UNUSABLE `fallback` index (wrong shape) does not invalidate the lease: it is
  treated as `fallback: null`, which `buildPlaylist` already handles as "no usable fallback"
  (`usableFallback`).

Fallback trigger (replace the current list in "Fallback (new)" and remove the sentence "A DO with
no current unblocked play lease ... is not 'dead'"):

  cron runs its loop (when the per-path table allows) and raises `metronome-down` if
  (a) `renew` throws or times out; or
  (b) cron sent a play lease (blocked or not), `applied` is not `superseded`, and either `applied`
      is not `accepted` or `wrote` is `false`; or
  (c) `stalls >= 2` (R3).

State the scenario check as a short list (this is the rule's justification; keep it to ~6 lines):
normal → accepted, no trigger; DO-side validation mismatch → invalid → trigger, cron writes from its
own known verdict; version skew where the DO reads METRONOME off → off → trigger; a stale stored lease
after a deploy → deleted on load, the fresh lease is accepted; a lagging older blocked lease → accepted,
blocks until the next run's newer unblocked lease supersedes it (documented limitation, fail-closed
direction); a lagging older unblocked lease after a newer blocked one → superseded, no trigger, the
DO stays blocked.

## R2. Alert batch completeness (regression fix; removes a rule)
Replace the `complete = true` sentence with: `complete` is set only at the end of the normal path
(known verdict, accepted horizon, then a healthy renew or a finished fallback loop); every early
return leaves it false exactly as today. Add one test bullet (guard-unknown + healthy renew(null)
must not resolve guard-family keys).

## R3. Stalls measured from alarm-confirmed ticks only (regression fix)
`stalledMs` = now − max(`lastAlarmGoodAt`, the time the current unblocked play lease was first
accepted after no/blocked/hold/expired lease). Only `alarm()` advances `lastAlarmGoodAt`; renew's own
write does not (so overlapping renews all see a dead chain). Rename `lastGoodAt` accordingly
everywhere; delete text that makes renew advance it. `stalls` rule unchanged otherwise.

## R4. Removals (D)
- Remove `stop()` entirely (the DO reads `env.METRONOME` itself): text, timeouts, tests. With the
  switch off, cron just runs today's loop.
- Remove the `doRowsRead` meter (bounded by construction: a fixed key set and capped invocations).
  Three DO meters remain: requests, duration, rowsWritten.
- Replace `lastBytesHash` with `lastBody` (the last successfully written playlist string, ~2-3 KB,
  compared as a string, as `runClock` does). Remove all hash wording/tests.
- Remove renew's extra skip clause (`now − lastGoodAt < d`): renew and alarm() use the same rule
  (skip when the body equals `lastBody`).
- Remove the `locationHint` (the probe measured punctuality without one; keep the placement the probe
  had). Remove its sentence.
- Remove the open question about `setAlarm` override (moot: renew arms only when none is pending).

## R5. Tick only while live
The chain ticks only while the playlist built from the lease is not the off-air / ENDLIST one: if
`alarm()` builds an off-air body (e.g. a horizon > 24 h stale under an unblocked lease), it writes it
once (identical-bytes skip applies) and does not re-arm; the next renew restarts the chain if the
inputs changed. One sentence in alarm(); one test.

## R6. Serialization and timeouts (strict surface; replace text, do not add a new section)
- The whole of `alarm()` after the env check — load+validate lease, re-arm, build, cap check, PUT,
  state update — and the whole of `renew()` run inside the one serialized section. One sentence.
- After a PUT timeout, set `lastBody` to null (the bytes in R2 are unknown), so the next write is
  never skipped as identical. The timeout timer is cleared in `finally`, as `alerts.ts` does.
- Cron's renew timeout becomes 15 s (> 2 × the 5 s PUT timeout plus slack). State it once.
- The PUT and alarm caps are true rolling windows: store the timestamps of the last 10 PUTs / last 12
  alarm invocations (fixed-size lists, part of the fixed key set). One sentence; one window-edge test.

## R7. Small corrections (one line each)
- Early delivery: alarm() builds for the due boundary, `max(now, lastTarget − 25 ms)`.
- "Empty is not zero" also applies to the periodic dataset: while on, recent `doRowsWritten` = 0 is a
  failed reading.
- Spend bounds: one instance ⇒ duration ≤ ~343k GB-s/month (0.128 GB × a 31-day month), inside the
  400k allowance, so the duration meter guards against the single-instance invariant breaking.
- Rollout pass: replace "±15%" with an upper bound: playlist PUTs at most ~one per boundary plus one
  per renew (≈ 7/min, ≈ 10k/day), counted from the DO and clock lines; below today's rate is expected.
- Known limitations gets two sentences: (1) during a fallback minute the two writers' off-air
  MEDIA-SEQUENCE can differ (cosmetic; both end in ENDLIST); (2) the "logged once per lease/episode"
  marks are memory-only and the object is evicted between ticks, so a persisting anomaly may log
  every tick (inside the Workers Logs allowance).
- Probe evidence: say the capture covered ~83% of the probe's boundaries (tail reconnects), so "one
  chain break" is over the captured span; the pass criterion on breaks is provisional on the real
  handler (which does an R2 PUT the probe did not).
- Rows written: replace "~100× under the allowance" with "~30-50× under" (4-6 keys written per tick).
