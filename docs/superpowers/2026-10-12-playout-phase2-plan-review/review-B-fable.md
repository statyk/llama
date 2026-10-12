Foundation: SOUND — the plan builds on mechanisms phase 1 measured (account-scoped GraphQL with a read-only token, the pre-created kill-switch rule, cache-served objects) and its arithmetic and discontinuity vectors check out independently; the remaining risk is a handful of Cloudflare API details it could not verify offline, listed at the end.

- **[Important] The metering query's period-long range is an unverified premise, and its failure mode is a false blind trip every long billing period**
  - Where: Task 3, `USAGE_QUERY` — `workersToDate: workersInvocationsAdaptive(limit: 10000, filter: { datetime_geq: $start, datetime_leq: $now })` (and the two R2 datasets likewise), with `$start` = the period start and timestamps formatted `.toISOString()` (`2026-10-11T00:00:00.000Z`).
  - Problem: Every evaluation issues one query spanning the whole period to date (up to 31 days: Oct 11 → Nov 11) with millisecond timestamps. Phase 1 only verified these datasets "over the last hour" (`docs/superpowers/2026-10-11-playout-phase1-verification.md`, GraphQL row). Cloudflare's adaptive datasets carry per-dataset maximum query ranges and retention; if any of the three refuses a range past 30 days, or the `Time` scalar rejects fractional seconds, `parseUsage` throws on every attempt.
  - Evidence: plan lines 1061–1071 (query), 1078–1083 (`usageVariables`); verification doc line 24 ("for the account over the last hour").
  - Failure scenario: a 31-day period; from day 30 on, every evaluation fails → `guard-reading-failing` after 1 h → `tripped: blind` after 6 h → kill switch on, ENDLIST, off-air page, until the next period starts and the range shrinks. The station is off the air for ~a day a month with nothing actually wrong. (Fail-closed, so spend is safe; on-air continuity is not.)
  - Setup and likelihood: this account's anniversary (day 11) gives 31-day periods for Oct, Dec, Jan, Mar, May, Jul, Aug. Likelihood unknown — that is the point; the first live evaluation (Task 20 item 1) happens on day ~2 of a period and would not reveal it.
  - Suggested fix: before Task 3 is built, run the exact `USAGE_QUERY` once with the existing token for a synthetic 31-day range and `.000Z` timestamps (one curl); if a range limit exists, meter the period as a sum of daily chunks (one extra loop in `readUsage`, ~15 lines) rather than one span. Adds a verification step and possibly a small loop; removes nothing.

- **[Important] Task 12 checks the fallback loop length after the segment uploads, which the phase-1 code's own comment forbids (a re-PUT loop)**
  - Where: Task 12, `publish.py` edit 3: "Immediately after the `if state.high_water is not None and last < state.high_water:` block … insert `try: disc, disc_len = next_horizon_disc(…) except PublishError as exc: report.error = str(exc); return report`".
  - Problem: `_fallback_len` raises when the loop length is unknown, but at that point the batch's segments have already been PUT (`uploaded`), `state.runs` has been saved, and nothing is unlinked locally. The next tick re-sends the same batch and fails the same way, every minute.
  - Evidence: `packages/transmitter/src/transmitter/publish.py:284-292` — the existing `fallback_version is None` refusal sits *before* any PUT precisely because "segment files are dropped only after a horizon PUT, so segments uploaded now would be re-PUT on every tick". The plan's own test `test_an_unknown_fallback_length_publishes_no_horizon` (lines 4706–4714) asserts no horizon but not "no segment PUT".
  - Failure scenario: a phase-1 workspace whose `fallback.json` has no `len` and whose local `render/fallback/<v>/index.json` is missing (e.g. after a `render/` cleanup): 360 segments × every tick until the daily PUT budget (17,500) stops it → ~17k Class A/day wasted, an alert storm, and no horizon advance.
  - Setup and likelihood: needs a phase-1 workspace missing its local fallback index — low, but the comment-documented invariant is being broken on the spend-adjacent path for no reason.
  - Suggested fix: resolve `disc_len = _fallback_len(p.ws, fallback_version)` right after the `fallback_version is None` check (before the first PUT) and compute `disc` later with `next_horizon_disc(..., length=disc_len)`; extend the test to assert `bucket.puts() == []`. Moves ~5 lines; adds one assertion.

- **[Important] The runbook loses the only takedown path that does not need hugo, while R14 makes the dashboard toggle self-reverting**
  - Where: Task 20 step 4 — "Replace section 4, step 4 ('Off-air by hand …') with: 'Off-air: `transmitter offair on …`' … Do **not** toggle the kill-switch rule in the dashboard: the guard reconciles it every minute and undoes a manual toggle."; ruling R14.
  - Problem: Both off-air levers now route through hugo (`transmitter offair`, R2 keys in hugo's env file). The phase-1 runbook's hugo-independent lever (`npx wrangler r2 object put lma-radio/state/offair.json …` from the Mac, `docs/playout-setup.md:198-203`) is deleted, and the dashboard lever is actively undone within a minute. An objection with standing (the spec's stated shutdown trigger) arriving while hugo is down leaves the operator with no documented way to stop the station short of deleting the Worker's cron trigger first.
  - Evidence: spec "Blocking": "So `offair on` blocks fully — the takedown path for an objection is not cooperative-only"; verification doc line 29: hugo powered itself off once already during phase 1 ("Power key pressed short", IR receiver).
  - Failure scenario: hugo off or its NFS/network broken; operator toggles the kill switch in the dashboard; one minute later the guard disables it and the station is back on air; the operator does not notice because nothing alerts on a *successful* reconcile.
  - Setup and likelihood: hugo unavailability is measured, not hypothetical; an urgent takedown is rare but is the one path the spec calls strict for standing.
  - Suggested fix: keep the `wrangler r2 object put … state/offair.json` instruction as the "hugo is down" path (it is one command and the guard honours the file), and state the emergency order for a broken Worker (delete the cron trigger, then toggle the rule). Doc-only; adds two sentences.

- **[Minor] `guard_stale_minutes`'s floor and default sit below the mechanism's own worst case, so a spurious `guard-stale` is reachable**
  - Where: Task 15 `AlertsConfig.guard_stale_minutes: float = Field(default=30.0, ge=16)`; Task 16 `_check_guard`.
  - Problem: hugo sees `guard_evaluated_at` through `guard-cache.json`, refreshed at most every 15 min (`guard_check_minutes`), and the guard evaluates every 15 min plus cron lag (up to ~60 s measured). The observed age can therefore reach ~31 min with everything healthy; a configured value of 16–30 is accepted and alerts.
  - Evidence: `publish.py:141-146` (cache interval); Task 6 `evalIntervalMs` clamp to 900 s; verification doc (lag max 59 s).
  - Failure scenario: cache read at minute 14:59 of the guard's cycle, next read at 29:59, guard's evaluation delayed by a 60 s cron lag → `age_s` ≈ 30.5 min → `guard-stale` alert, resolved on the next tick (an alert + a "resolved" for nothing).
  - Setup and likelihood: the default setup; a few times a month at the measured lag distribution.
  - Suggested fix: floor `ge=31`, default 40 (or compute the floor from `guard_check_minutes + 15 + 1`). One-line change.

- **[Minor] After `transmitter offair on`, the dead-clock monitor can raise a spurious "kill switch left on?" alert because its cache of the flag is up to 15 min old**
  - Where: Task 16 `DeadClockMonitor.check` — `blocked = bool(guard_cache and (…"blocked") or …"offair"))`, `TROUBLE_CHECKS = 10`.
  - Problem: the 403 becomes "expected" only once `guard-cache.json` has `offair: true`, which `guard_blocks_publishing` refreshes every 15 min; the 403 starts within a minute of the command.
  - Evidence: plan lines 6596–6618; `publish.py:145`.
  - Failure scenario: cache refreshed at T−1 min when `offair on` runs at T → 403s counted for 14 min → `trouble >= 10` at T+10 → `dead-clock` alert "answers 403 although the guard says the station is not blocked", resolved at T+14.
  - Setup and likelihood: about one in three `offair on` invocations (cache age uniform over 15 min).
  - Suggested fix: on an unexpected 403 re-read `state/offair.json` once (one Class B) before counting, or set `TROUBLE_CHECKS` to 16. A few lines.

- **[Minor] R3's "an over evaluation consumes the raise" burns a raise made while a transient burst is still inside the 3-h projection window**
  - Where: R3; Task 4 `applyAttempt` — on `overThreshold(e)`: `tripped_budget_usd: e.budgetUsd`.
  - Problem: a trip caused by projection (e.g. a re-render's Class A burst) stays over for up to 3 h after the burst; a raise evaluated in that window is recorded as the new `tripped_budget_usd`, so the operator must raise again above it even once the rate has fallen. The CLI then refuses anything at or below the consumed value.
  - Evidence: plan lines 1458–1461, 5715–5717 (`usd <= current` refusal).
  - Failure scenario: tripped at projected $15.2 of $15; `--raise-to 16` evaluated 20 min later while projected is still $15.5 → consumed; an hour later projected is $9 but the latch holds until `--raise-to 17`.
  - Setup and likelihood: any projection trip followed by a prompt raise; the runbook (section 7) does not say to raise above *projected*.
  - Suggested fix: either keep `tripped_budget_usd` at the value of the *original* trip when an over evaluation happens at a raised budget (so the next under evaluation at the raised budget clears — no spend risk, the station stays blocked meanwhile), or add one runbook sentence: raise above the `projected` figure `transmitter budget` prints. Removes a few lines or adds one sentence.

- **[Minor] Guard and alert-dispatch latency sit inside the clock's write loop; A4's stall analysis does not count them**
  - Where: Task 8 `runClock` — the guard (GraphQL 15 s timeout, Rulesets GET 10 s, PATCH 10 s) precedes `write(true)`, and `flush()` (ntfy 10 s + email) runs between the first write and the boundary loop; amendment A4 — "players stall once lag exceeds about 25 s".
  - Problem: a slow or timing-out API adds up to ~35 s before the first playlist write, and a slow alert channel up to ~20 s before the next boundary write, on top of the measured cron lag; A4's trigger counts only `lagMs`.
  - Evidence: plan lines 3061–3076, 3141–3142; `TIMEOUT_MS` in meter.ts/waf.ts/alerts.ts.
  - Failure scenario: a Cloudflare API slowdown for 10 minutes: every invocation's first write lands ~25 s late, the window does not advance for players for that stretch → stalls, with `lagMs` looking normal.
  - Setup and likelihood: API slowness is occasional; worst case is a stall, not spend.
  - Suggested fix: dispatch alerts in the `finally` after the loop instead of after the first write (same guarantees, zero extra PUTs), and have the Task 19 checkpoint add the guard's measured duration (log `guardMs` on the clock line) to the lag before deciding. ~5 lines.

- **[Minor] Cloud alert state lives in R2, so the "R2 unreadable" path both writes a state object and cannot alert**
  - Where: Task 8 behaviour summary "An unknown outcome (null) … writes nothing at all" vs. Task 9 `alertSink` → `dispatchAlerts` → `putJson(bucket, ALERTS_KEY, …)` from the `finally` flush; Task 6 `guard-unknown`.
  - Problem: on `blocked: null` the invocation still attempts a `state/alerts.json` read/write (contradicting the stated contract, though only a state object), and when R2 is actually unreadable that read throws inside `flush`'s catch, so `guard-unknown` is only logged; when R2 recovers the condition is gone and is never sent.
  - Evidence: plan lines 3050–3059, 3072–3076, 3600–3604.
  - Failure scenario: a 2-hour R2 binding outage: no cloud alert at all; hugo's dead-clock check (stale playlist after 2 checks) is the only signal — which does cover it.
  - Setup and likelihood: rare; worst case a missed alert.
  - Suggested fix: document that `blocked: null` may still touch `state/alerts.json`, or skip dispatch on `blocked: null` and rely on the log plus hugo's dead-clock alert. Either is a sentence or a two-line guard.

- **[Minor] A flapping condition sends a "resolved" notice at every clearing inside the cooldown**
  - Where: Task 9 `planAlerts` — `if (e.active) { next[key] = {…inactive…}; if (e.resolvable) send.push({ kind: "resolved" …}) }`.
  - Problem: the cooldown suppresses the re-*alert* when a condition returns within 15 min, but not the *resolved* message each time it clears, so a WAF API flapping minute-by-minute produces one "resolved" per clearing.
  - Evidence: plan lines 3504–3512; the test at 3336–3344 does not assert the second clearing's output.
  - Failure scenario: Rulesets API alternating 200/5xx for 20 minutes → ~10 "resolved: Kill switch not reconciled" messages, one real alert.
  - Setup and likelihood: API flaps are uncommon; duplicate alerts only.
  - Suggested fix: send "resolved" only once the condition has stayed clear for `COOLDOWN_MS` (check `cleared_at` age on the following invocation). ~6 lines.

- **[Minor] Latch edge cases: a lost race can carry a blind trip over a newer successful reading, and a future `written_at` evaluates every minute**
  - Where: Task 6 `persist` — merges `tripped/reason/tripped_at/…` from ours onto theirs whenever `doc.tripped && !theirs.tripped`; Task 4 `shouldEvaluate` — `budgetWrittenAtMs > last`.
  - Problem: (1) if our invocation applied the blind rule while the overlapping one just recorded a successful under-threshold reading, the merge produces a document that is both `last_success: fresh` and `tripped: blind`; it clears at the next evaluation (≤ 15 min) but blocks until then. (2) a `written_at` ahead of the Worker's clock (hugo skew) keeps `shouldEvaluate` true until `evaluated_at` passes it — a GraphQL call per minute (unbilled).
  - Evidence: plan lines 2202–2212, 1485–1491.
  - Failure scenario: (1) overlap exactly at the 6-h blind boundary — a ≤15-min false block; (2) hugo 2 min ahead → 2 extra evaluations.
  - Setup and likelihood: both rare (one overlapping minute was observed in 69 invocations; hugo runs NTP).
  - Suggested fix: in `persist`, only merge a *blind* trip when `theirs.last_success` is not newer than ours; in `effectiveBudget`, clamp `writtenAtMs` to `nowMs`. Two lines.

- **[Minor] Fresh-start and upgrade-window alert noise**
  - Where: Task 8 `lead-low` (any lead below 16 h, suppressed only while tripped) and `horizon-missing`; Task 16 `_check_guard` ("state/guard.json has no evaluation time") during the mandated transmitter-first deploy.
  - Problem: every first start spends hours below the floor while the lead builds (~10 min encode per show, verification doc line 31), and the runbook's deploy order guarantees a `guard-stale` from hugo before antenna is deployed.
  - Evidence: plan lines 3103–3109, 6621–6629; Task 20 section 6 "Order matters: transmitter first, then antenna".
  - Failure scenario: first start → `lead-low` alert at minute 1, "resolved" hours later; upgrade → `guard-stale` until the antenna deploy.
  - Setup and likelihood: every fresh run / this upgrade. Alerts only.
  - Suggested fix: suppress `lead-low` while `horizon.last - horizon.first` is below the floor itself (the lead has never been reached), and have the runbook say the `guard-stale` during the deploy window is expected. A line each.

### Unverified premises

- **GraphQL maximum query range and retention for `workersInvocationsAdaptive`, `r2OperationsAdaptiveGroups`, `r2StorageAdaptiveGroups` cover a 31-day period, and the `Time` scalar accepts `.000Z`.** Test: run `USAGE_QUERY` once via curl with the phase-1 token for a 31-day range (see the first finding).
- **`r2StorageAdaptiveGroups` exposes `max { payloadSize metadataSize }` with `dimensions { bucketName }`, and `limit: 10000` is accepted.** Test: the same curl.
- **The Rulesets entrypoint GET always returns `enabled` on a disabled rule** (Task 5 reads an absent `enabled` as *true*; if the API omitted it when false, a block would be cooperative-only with `changed: false` and no alert). Test: one `GET /zones/<zone>/rulesets/phases/http_request_firewall_custom/entrypoint` while the rule is disabled; Task 20's "Off-air blocks fully" item would also expose it.
- **PATCH `/zones/{zone}/rulesets/{ruleset}/rules/{rule}` accepts `ref` back and returns the whole ruleset; the token permission is "Zone → WAF → Edit".** Test: Task 20's Rulesets item (one toggle).
- **`cloudflare:email` resolves in the `@cloudflare/vitest-plugin` pool without a `send_email` binding in `wrangler.jsonc`** (Task 9 imports it at module top, so every antenna test depends on it). Test: a one-line import in a scratch test file before Task 9 starts.
- **R2 `put(..., { onlyIf: { etagMatches } })` returns `null` on a failed precondition in production** (documented; Task 1 pins Miniflare's emulation only). Test: none cheap beyond Task 20's overlapping-invocation observation; the merge logic degrades to "last writer wins" if wrong.
- **`wrangler deploy --config wrangler.deploy.json` picks up `CLOUDFLARE_ACCOUNT_ID` from `antenna/.env` and accepts `send_email` with `destination_address` in a JSON config.** Test: Task 20 6.3 step 2's `--dry-run`.
- **Cloudflare clamps a day-31 anniversary to the last day of shorter months** (Task 1 `billingPeriod`). Irrelevant for day 11; test: none.
- **The `wrangler types`-generated `worker-configuration.d.ts` stays compatible as vars are added without regeneration** (`index.ts` uses `AntennaEnv`, so likely fine). Test: `npx tsc --noEmit` at Task 8, already in the plan.

TOTAL: 10 findings (0 Critical, 3 Important, 7 Minor)