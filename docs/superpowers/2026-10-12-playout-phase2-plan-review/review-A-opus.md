Foundation: UNVERIFIED. The guard depends on one GraphQL request covering the whole billing period, up to 31 days (plan-frozen.md:1061-1081). Nothing I can read shows that Cloudflare's datasets accept a range that long. If they don't, every evaluation fails late in a period and the station trips blind, which fails closed. Everything else the plan rests on is either confirmed by the phase-1 measurements or checked by Task 20.

- **[Important] Whole-period GraphQL query may exceed the datasets' range limits**
  - Where: Task 3 `USAGE_QUERY`. `workersToDate`/`r2ToDate`/`storage` filter `datetime_geq: $start` with `start: iso(period.startMs)` (plan:1064-1068, 1081).
  - Problem: Each dataset has a `maxDuration` and a `notOlderThan` limit. The query's range grows to about 31 days, and the plan never checks those limits.
  - Evidence: The phase-1 verification (2026-10-11-playout-phase1-verification.md, GraphQL row) measured only token scope and lag, not range. No task chunks the query.
  - Failure scenario: Suppose a dataset allows, say, 7 days or 30 days. The Task 20 check runs about 2 days after the 11th and passes. From day 8, or in the last day of a 31-day period, every evaluation throws. Six hours later the station trips blind and blocks: dead air until the next period. There is no spend risk, but the outage is silent until then (only `guard-reading-failing` warns).
  - Setup and likelihood: The real setup. Likelihood unknown; the cost to check is one curl.
  - Suggested fix: Before Task 3, query `settings { workersInvocationsAdaptive{maxDuration notOlderThan} r2OperationsAdaptiveGroups{…} r2StorageAdaptiveGroups{…} }`. If a limit is under 31 d, sum the period-to-date in ≤limit chunks (a loop plus one parse test). Also add a Task 20 item that runs the query with a 31-day range.

- **[Important] Task 12 checks "loop length unknown" only after uploading the segments, so they are re-PUT every tick**
  - Where: Task 12 publish.py edit 3: "Immediately after the … 'horizon held' … block … insert `next_horizon_disc` … `report.error = …; return report`" (plan:4959-4967).
  - Problem: At that point the batch's segments are already uploaded. Local files are deleted only after a horizon PUT, so each later tick uploads the same batch again (up to 360 PUTs).
  - Evidence: publish.py:284-292 refuses before any PUT for exactly this reason. The existing test test_publish.py:383-397 pins "never re-puts". The plan's new test (plan:4706-4714) asserts only "no horizon".
  - Failure scenario: `fallback.json` has no `len` (a phase-1 record) and `render/fallback/<v>/index.json` is gone (for example, a restored `~/.transmitter`). Every minute re-PUTs about 360 segments until the daily PUT budget stops publishing. That wastes Class A and drains the lead toward fallback.
  - Setup and likelihood: hugo after the upgrade. Unlikely, because `fallback render` wrote the local index there, but this is the per-write billing surface, and the new test does not pin it.
  - Suggested fix: Do the length lookup right after the `NO_FALLBACK` check, before `_extend_runs` and any PUT. Assert `bucket.puts() == []` and no PUT-budget file in the test. Consider putting Task 12 under the post-Task-8 spend review gate.

- **[Important] A manual kill-switch toggle is silently reverted, and the runbook drops the Mac-side off-air lever**
  - Where: R14 "a manual toggle in the dashboard is undone within a minute" (plan:133). Task 20 edit 4 replaces "Off-air by hand" (`wrangler r2 object put … state/offair.json`) with `transmitter offair` only (plan:7231).
  - Problem: When `blocked` is false, `reconcileKillSwitch` disables a hand-enabled rule (`changed: true`) and raises no condition (plan:1725-1739, 2280-2282). The only documented takedown lever now needs hugo's R2 keys.
  - Evidence: hugo powered itself off on day 1 (verification doc, "Other findings").
  - Failure scenario: hugo is down, and an objection or a random-key flood arrives before the guard's next evaluation (up to about 17 min). The operator enables the kill switch in the dashboard. The guard turns it off within a minute and nothing says so.
  - Setup and likelihood: The real setup; plausible, since hugo outages happen.
  - Suggested fix: Keep the `wrangler r2 object put state/offair.json` recipe in the runbook as the Mac-side lever. Raise a `waf-corrected` alert when the GET shows a state that differs from `prev.waf.enabled` (about 5 lines plus 1 test).

- **[Minor] `guard-stale` false alarms come from the 15-minute guard cache**
  - Where: Task 16 `_check_guard` uses the cached `guard_evaluated_at`; `guard_stale_minutes = 30` with a floor of 16 (plan:6241, 6620-6634).
  - Problem: The cache is refreshed only every 15 min (publish.py:145), and the guard evaluates on a 15–16 min cadence. The evaluated time can therefore look up to about 32 min old when the guard is healthy.
  - Evidence: As above.
  - Failure scenario: The cache read lands about 15 min after an evaluation and is kept another 15 min. Each such cycle produces a `guard-stale` alert followed by "resolved", possibly many times a day while the two phases stay aligned.
  - Setup and likelihood: Default config; likely.
  - Suggested fix: Measure staleness at read time (`checked_at − evaluated_at`), or set default ≥ 45 min and floor ≥ `guard_check_minutes + 16`.

- **[Minor] A 403 after `offair on` or a trip is reported as "kill switch left on?"**
  - Where: Task 16 `check()`: `blocked` comes from the cache; 10 trouble checks trigger an alert (plan:6596, 6610-6618).
  - Problem: The cache can say "not blocked" for up to 15 min after the WAF goes on, but the alert fires after 10.
  - Evidence: publish.py:141-153.
  - Failure scenario: Roughly a third of off-air events or trips produce a misleading dead-clock alert.
  - Setup and likelihood: Every offair or trip; likely.
  - Suggested fix: On an unexpected 403, re-read the guard and the flag, bypassing the cache, before counting. Or make the threshold larger than `guard_check_minutes + 2`.

- **[Minor] The clock does not clamp a raise's `expires` to the current period**
  - Where: `effectiveBudget` honours any `expires > now` (plan:1502-1514).
  - Problem: R3 says a raise lasts until the period ends, but the clock trusts the writer's expiry date.
  - Evidence: The guard knows `period.endMs` and does not apply it.
  - Failure scenario: A hand-written `budget.json`, or skewed or buggy writer, with a far-future `expires` raises the budget across periods, up to $100/month.
  - Setup and likelihood: Needs R2 write access; unlikely.
  - Suggested fix: Ignore a raise whose `expires` is after the current `period.endMs` (one comparison plus one test).

- **[Minor] `disc` is not crash-safe, and a phase-1 state is numbered with the new fallback**
  - Where: Task 12. The horizon is PUT with `disc`, then `save_publish_state(... disc=...)` (plan:4969-4975). `published_numbering` falls back to `load_fallback_version` (plan:4945), which `upload_fallback` has already overwritten (plan:4998).
  - Problem: After a crash between the PUT and the save on a fresh run, the re-sent batch recomputes `disc` from the old numbering at a different `now_index`.
  - Evidence: `high_water` is persisted before the PUT for the same reason (publish.py:13-16); `disc` is not.
  - Failure scenario: A rare `DISCONTINUITY-SEQUENCE` drop, so VLC goes silent (the phase-1 symptom).
  - Setup and likelihood: Crash window during a recovery; very rare.
  - Suggested fix: Persist the candidate `disc`/`len`/`version` with `high_water` and reuse them on re-send, or document it as accepted.

- **[Minor] `guard-unknown` cannot reach a channel when R2 is the failure**
  - Where: `dispatchAlerts` reads `alerts.json` first (plan:3602). `flush` only logs `alert-dispatch-failed` (plan:3054-3058).
  - Problem: The alert for "R2 unreadable" is routed through R2.
  - Evidence: As above.
  - Failure scenario: An R2 binding outage triggers no cloud ntfy or email; only hugo's dead-clock check catches it, about 2–4 min later.
  - Setup and likelihood: Rare.
  - Suggested fix: Document that hugo's dead-clock check is the channel for this case, or send `guard-unknown`/`guard-crashed` undeduped when the state read throws.

- **[Minor] An overlapping invocation can hold the live playlist for about a minute after a trip**
  - Where: Task 8 identical-bytes skip (plan:3130); `offairSeqMs` is constant per invocation.
  - Problem: Invocation A (not blocked) writes at its last boundary after invocation B (just tripped) has written ENDLIST. B's later off-air writes are byte-identical and skipped.
  - Evidence: The spec's "overlapping invocations are harmless" assumes the inputs agree.
  - Failure scenario: ENDLIST is delayed until the next invocation, up to about 55 s. It only matters while the WAF is failing (a cooperative-only block).
  - Setup and likelihood: Lag outliers plus a trip; rare.
  - Suggested fix: Document it in the runbook's WAF-failure limitation.

- **[Minor] Budget alerts repeat every 6 h for the rest of the period**
  - Where: `budget-50`/`budget-80` are `resolvable: false` and recomputed from the stored evaluation (plan:2051-2058); `planAlerts` repeats them (plan:3497).
  - Problem: Once spend crosses 50%, the operator gets about 4 messages a day for weeks.
  - Evidence: As above.
  - Failure scenario: Alert fatigue on the spend channel.
  - Setup and likelihood: Any overage early in a period.
  - Suggested fix: Send threshold alerts once per level per period (key them by period, no repeat).

- **[Minor] hugo event alert codes never become inactive, so `status` shows stale alarms**
  - Where: R16; `Dispatcher.fire` and `active()` (plan:6140-6168); `status` lists `active` (plan:7037-7039).
  - Problem: `publish`, `prune` and `put-budget` are never resolved.
  - Evidence: As above.
  - Failure scenario: One transient PUT failure leaves `alerts hugo: publish` in `status` forever.
  - Setup and likelihood: Likely over weeks.
  - Suggested fix: Treat an event code as inactive once `repeat_s` has passed without a fire, or resolve it on a clean publish pass.

- **[Minor] The watchdog assumes the longest step is one encode**
  - Where: R15 "the longest step is one show's encode" (plan:134); `WatchdogSec=45min`.
  - Problem: `publish_all` loops up to `MAX_BATCHES = 100` × 360 PUTs in one step (service.py:137-146), with backoff retries.
  - Evidence: A backlog builds whenever publishing is stopped (trip, PUT budget, R2 outage) while rendering continues, up to about 8.4k segments.
  - Failure scenario: On a slow link the catch-up step exceeds 45 min. The watchdog aborts mid-batch, which re-PUTs that batch (duplicate Class A), and this repeats each restart.
  - Setup and likelihood: After a long stop; plausible.
  - Suggested fix: Send `WATCHDOG=1` after each batch in `publish_all`, or document it.

- **[Minor] R12 treats the anniversary as a secret, but the plan and tests commit it**
  - Where: R12 (plan:119) vs "anniversary is day **11**" (plan:30), `BILLING_ANNIVERSARY_DAY: "11"` (plan:1797), and the period tests.
  - Problem: The secret adds deploy steps and failure modes while the value is public anyway.
  - Evidence: As above.
  - Failure scenario: The secret mechanism is pure overhead; it hides nothing.
  - Setup and likelihood: Certain.
  - Suggested fix: Make it a committed var (removes one secret and one "problem" path), or scrub "11" from the plan and tests.

- **[Minor] A3 is over-built and has two sources of truth for the destination**
  - Where: A3 / Task 10 (`deploy.mjs`, `deploy-config.mjs`, `raw.d.ts`, `wrangler.deploy.json`) plus the secret `ALERT_EMAIL_TO`.
  - Problem: A send_email binding without a destination attribute can reach only the account's verified destinations, so pinning adds little. The address also lives in both `.env` and a secret; if they disagree, every email fails.
  - Evidence: plan:78-87, 3587-3589, 7294. The phase-1 note asked for pinning.
  - Failure scenario: The two values diverge and email alerts fail.
  - Setup and likelihood: Possible.
  - Suggested fix: For the operator to decide. Either commit an unrestricted `send_email: [{name:"ALERT_EMAIL"}]` and drop about 150 lines and the generated config, or keep pinning and stop using a separate `ALERT_EMAIL_TO` secret.

- **[Minor] A1 is large relative to a rare event**
  - Where: Tasks 11–12 (about 1,100 plan lines), the cross-language vectors, the deploy-order constraint and the coupling to Task 19.
  - Problem: The defect it fixes (VLC silent at a fallback→live switch) occurs only at a fresh run: first start, an outage longer than the 24 h lead, or an epoch change.
  - Evidence: The verification doc row "Fallback → live switch"; Chrome and Safari already pass.
  - Failure scenario: Not a failure; this is a cost-versus-benefit point.
  - Setup and likelihood: The event itself is rare.
  - Suggested fix: For the operator to decide. Either keep A1, or replace it with a documented limitation ("VLC: press play again after an outage").

- **[Minor] The lookahead margin and the A4 trigger ignore the guard's time on the critical path**
  - Where: Task 19 test comment "scheduledTime is at most ~75 s before now" (plan:7120). A4 triggers on lag only (plan:97). Guard timeouts are GraphQL 15 s and WAF 2×10 s (plan:1046, 1659).
  - Problem: The first write can come more than 95 s after `scheduledTime`. At lookahead 3–4 the off-air `MEDIA-SEQUENCE`, `indexAt(scheduled+75)`, can then fall below the last live one. A slow API also eats the 33 s runway that A4 assumes.
  - Evidence: A 59 s lag outlier was measured.
  - Failure scenario: Rare stalls, or a decreasing `MEDIA-SEQUENCE` on the off-air playlist.
  - Setup and likelihood: Lag outlier plus a slow API; rare.
  - Suggested fix: Log guard duration in the clock line and trigger A4 on lag + guard time. Lower the WAF timeout to about 5 s. Use `offairSeqMs = max(scheduled+loopMs, invocation start + lookahead·d)`.

### Unverified premises
- The GraphQL `maxDuration`/`notOlderThan` limits for `workersInvocationsAdaptive`, `r2OperationsAdaptiveGroups` and `r2StorageAdaptiveGroups` must be ≥ 31 days on this account. The exact query also needs to work as written (aliases, `$account: string!`, `datetime_leq`). Cheapest test: one curl of `USAGE_QUERY` with `start` = now − 31 d, plus a `settings{…}` query.
- Rulesets PATCH `/zones/{z}/rulesets/{rs}/rules/{id}` must replace the rule from the resent fields, return the full ruleset with `rules[].enabled`, and work with a "Zone · WAF · Edit" token. Cheapest test: a GET plus a no-op PATCH (same `enabled`) with the new token.
- R2 `actionType` strings must match the S3 names in `CLASS_A`/`CLASS_B`/`FREE_OPS`. Cheapest test: one grouped query by `actionType`.
- R2 binding `put(…, {onlyIf:{etagMatches}})` must return null on a stale etag in production as well as in miniflare. Cheapest test: none beyond Task 1's binding test; it is documented behaviour.
- An unrestricted `send_email` binding reaches only verified destinations (relevant only if A3 is reconsidered). Cheapest test: a docs check.
- Cloudflare's edge must ignore the `Cache-Control: no-cache` header that `fetch(..., {cache:"no-store"})` adds, so the probe is a cache hit. Cheapest test: `curl -sI -H 'Cache-Control: no-cache' https://<host>/live.m3u8` and check that `cf-cache-status` is HIT.
- hugo's once-a-minute dead-clock GET is usually a MISS (max-age 5), so it costs about 43k Class B a month. That is negligible, but the "never billed" wording is wrong. Cheapest test: none needed.
- Email Routing must accept the hand-built raw message (Message-ID on the sender's domain; sender on the zone). Cheapest test: Task 20's alert items.
- git must work for the implementers. The review brief says git is broken on this machine, and every task commits. Cheapest test: `git status` in the repo before Task 0.

TOTAL: 16 findings (0 Critical, 3 Important, 13 Minor)