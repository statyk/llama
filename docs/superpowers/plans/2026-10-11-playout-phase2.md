# Playout Phase 2 ("Guard + operations") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the station safe to share publicly. The antenna clock Worker gets a cost guard: it meters account usage through GraphQL, prices it, latches `tripped`, reconciles the blocked state on every invocation (ENDLIST playlist, off-air `index.html`, WAF kill switch) and sends cloud alerts. transmitter gets `offair` and `budget` commands, hugo-side alerts with a dead-clock check, a systemd unit with a watchdog, and a full `status`. The phase also folds in the phase-1 findings: kill-switch detection in an already-playing page, an unrestricted `send_email` binding whose destination lives only in a Worker secret, a documented VLC limitation at a fallback→live switch, and a lookahead that only lands if the measured cron lag plus guard time calls for it.

**Architecture:** The guard runs first in every clock invocation. It reads `state/guard.json`, `state/offair.json` and `state/budget.json` through the R2 binding. When the last attempt is 15 minutes old, it reads usage from the account-scoped GraphQL Analytics API and prices it through the allowances, projecting each meter from its last-3-hour rate. It then applies the latch. In a `finally` it applies the blind rule, makes the kill switch's `enabled` match `blocked = tripped OR offair` through the Rulesets API, and saves `guard.json` with an etag-conditional PUT. After the guard, the clock makes `index.html` follow the blocked state, writes the playlist (the ENDLIST off-air playlist while blocked), and after its last playlist write dispatches deduped alerts to ntfy and email. If the guard cannot read its state, the invocation writes nothing at all. transmitter's operator commands write `state/` directly: they bypass the guard and the PUT budget, because they are how the operator stops the station or clears a trip. hugo's alerts go out by SMTP and ntfy, deduped in `~/.transmitter/alerts.json`.

**Tech Stack:** TypeScript, wrangler 4, vitest with `@cloudflare/vitest-plugin` (workerd), Cloudflare GraphQL Analytics API, Rulesets API, Email Routing `send_email` binding (`cloudflare:email`), ntfy HTTP. Python ≥3.11 (hugo runs 3.11), typer, pydantic v2, boto3, smtplib/ssl/urllib from the stdlib, systemd `Type=notify`.

**Spec:** `docs/superpowers/specs/2026-10-09-playout-design.md`: sections "Cost guard (phase 2)", "Alerts and operations (phase 2)", Phases item 2, and the Stakes section, which governs. The phase-1 plan (`docs/superpowers/plans/2026-10-10-playout-phase1.md`) and `CLAUDE.md` describe the as-built code this plan extends.

## Stakes

Money and on-air continuity are at risk. Data is not. **Spend is the one strict surface.** Cloudflare has no account spending cap, so a defect in the guard, the blocking reconciliation, the kill switch or the fail-closed blind rule can run up an uncapped bill silently. Treat those paths with the rigor of a migration. **No failure mode may silently leave the station unblocked while over budget, and no listener path may ever bill per request.** Concretely:

- an unreadable state never unblocks;
- a lost race never loses a trip;
- a missing secret fails closed (blind) and loudly;
- the kill switch is found by its description and never toggled if it is ambiguous;
- the clock's spend bounds stay intact: `MAX_PUTS = 10`, the `d ≠ 10.24` refusal and the 75 s loop clamp.

Secondary: the station must never list a segment that does not exist, and must never cut a performance mid-song.

**This repo is public.** No committed file may contain an account ID, zone ID, token, key, email address or other account detail. That covers this plan, code, config templates, tests and `wrangler.jsonc`. Use placeholders (`<host>`, `you@example.com`, `<your-topic>`) and keep the real values in Worker secrets, the git-ignored `antenna/.env`, or hugo's env file (mode 600). Never add `account_id` or an address to `antenna/wrangler.jsonc`. The one address that may appear in the plan and the runbook is the alert sender `alerts@lma-radio.com`: it sits on the station's already-public domain and identifies no account (operator ruling, 2026-10-12).

## Operator inputs (decided 2026-10-11)

- `MONTHLY_BUDGET_USD = 15`, **including** the $5 Workers Paid base. Alerts fire at actual or projected 50% and 80%. The guard trips at actual ≥ 90% or projected ≥ 100%.
- The billing period's anniversary is day **11** of each month (UTC). It is the committed var `BILLING_ANNIVERSARY_DAY = "11"` (ruling R12).
- hugo SMTP uses Gmail: `smtp.gmail.com:587` with STARTTLS and an App Password. The credentials live only in hugo's env file. The destination is `[alerts] email_to` in hugo's config (a placeholder in the template).
- The ntfy topic is an operator value. The cloud uses the `NTFY_URL` secret and hugo uses `[alerts] ntfy_url`; they may be different topics.
- Cloud alert email goes from `alerts@lma-radio.com` (the Worker secret `ALERT_EMAIL_FROM`) to the verified Email Routing destination, which lives only in the Worker secret `ALERT_EMAIL_TO` (amendment A3).
- Alert defaults (approved 2026-10-12): the lead-floor alert at 16 h (R6), the dead-clock alert at 120 s on two consecutive checks (R4), and a 6 h repeat for an alert that stays active (R13, R16).
- An *Account Analytics: Read* token already exists; it becomes the Worker secret `CF_ANALYTICS_TOKEN`. A zone-scoped token for editing WAF rules is created at deploy (Task 17) and becomes `CF_WAF_TOKEN`.
- The kill-switch custom rule already exists in the zone, deployed and then disabled, with the description `station: kill switch`. The guard finds it by that description.

## Spec amendments (approved by the operator 2026-10-12)

The operator approved A2, A4 and A5 as proposed and A3 as revised below, and rejected A1 in favour of a documented limitation. The spec file is not edited until Task 19, which records them as as-built notes. Each amendment names the task that implements it.

**A1. VLC at a fallback→live switch: a documented limitation, no code (Tasks 17, 19).** At a fallback→live switch — a fresh run: the first start, an outage longer than the published lead, or a re-epoch — `EXT-X-DISCONTINUITY-SEQUENCE` restarts at 0 (phase 1 measured a drop from about 2,790 to 0). hls.js and Safari follow it; VLC goes silent and needs stop/play once. Phase 1's numbering stays as built; the runbook (Task 17) and the spec note (Task 19) record the limitation.

**A2. An already-playing page detects the kill switch (Task 11).**

*Finding.* With the kill switch on, an already-playing page just went silent; only a fresh Play showed the notice.

*Proposal.* The player watches playback progress itself rather than trusting error events.

- After 15 s without progress it probes `live.m3u8` (`cache: "no-store"`). The answer is a cache hit or the WAF's 403, never billed per request: even with `Cache-Control: no-cache` the edge answers from cache (A5), refetching `live.m3u8` from R2 at most every 5 s whoever asks.
- It probes at most every 10 s, one probe at a time.
- Two consecutive *definitive* verdicts (403, or a playlist ending in `#EXT-X-ENDLIST`) show the off-air notice with its retry button.
- Network errors, 5xx, 429 or a live playlist are not verdicts, and any progress resets the watch, so a blip that recovers never shows the notice.
- While stalled, the now-playing line says "Reconnecting…".
- hls.js errors also map `networkDetails.status` 403 to off-air.

**A3. An unrestricted `send_email` binding; the destination lives only in a Worker secret (Task 10).**

*Finding.* Pinning the binding's `destination_address` puts the address in the Worker config, and no address may be committed.

*Proposal (as revised).*
- `antenna/wrangler.jsonc` commits an unrestricted binding, `"send_email": [{ "name": "ALERT_EMAIL" }]`. A `send_email` binding can only send to the account's verified destination addresses, so pinning one added little.
- The destination is only the Worker secret `ALERT_EMAIL_TO`: one source of truth. The sender, `alerts@lma-radio.com`, is the Worker secret `ALERT_EMAIL_FROM`, which keeps `wrangler.jsonc` free of addresses.
- A test keeps `wrangler.jsonc` free of any email address and of `account_id`.
- The deploy stays `npx wrangler deploy`, plus `wrangler secret put` for the secrets.
- Mail is built as a minimal RFC 5322 `text/plain` (base64 body, RFC 2047 subject) and sent with `EmailMessage` from `cloudflare:email`, with no npm dependency.

**A4. The cron-lag lookahead is conditional on a day of measured lag plus guard time (Task 18).**

*Finding.* Measured lag: median 10.8 s, min 6.9 s, one 59 s outlier in the first 69 invocations. The 24 h capture finishes on the evening of 2026-10-12.

*Assessment.* hls.js sits about 3 target durations (33 s) behind the live edge. Safari and VLC behave alike. After the clock's last write, a player therefore has about 33 s of runway before it reaches the end of the listed window. The next write comes `lag + guard time − 4.8 s` after the last one (worst case), plus up to ~10 s for max-age and the player's reload. So players stall once **lag exceeds about 25 s**. The 59 s outlier would stall them for roughly 30 s.

*Proposal.* A `PLAYLIST_LOOKAHEAD` var (default 0, capped at 4) lists that many segments past the one airing. Every listed segment exists, because the lead is ~24 h. With lookahead 3, players sit at the wall clock and have about 64 s of runway, which tolerates a ~58 s lag. This changes no PUT count. The off-air MEDIA-SEQUENCE stays at or above live: the clock numbers it from `max(scheduledTime + loopMs, invocation start + lookahead·d)`, so an invocation running late cannot drop it below the live window it replaces (a test pins this at the cap of 4).

*Trigger.* The guard's own time sits on the same critical path as the cron lag, so the trigger is their sum. Task 18 runs **only if** a day of phase-2 clock lines shows **more than 5 invocations with `lagMs + guardMs` > 25 s** (≥ 0.35%). `guardMs` is logged on the clock line from Task 8 on, so the data exists only after Task 17's deploy, and Task 18 follows it. Otherwise Task 18 is skipped and the summary is recorded in the ledger. The human checkpoint at Task 18's start is where the operator supplies the numbers.

**A5. Free-plan facts the guard respects (Tasks 3, 5, 6).**

- **Custom rules.** Free zones get at most 5 custom rules, and 2 are already used. The guard creates no rules; it only toggles the existing kill switch. That rule is found by its exact description; zero or more than one match is an error, and so is an action other than `block`.
- **Rate limiting.** The single rate-limit rule matches on path only; this is irrelevant to the guard.
- **`wildcard`.** It is available but not needed; the rule expressions stay as in the runbook.
- **GraphQL lag.** Operations lag 1–2 minutes and storage about 45 minutes, in coarse steps. The 3-hour rate window therefore ends 5 minutes before now. Storage is priced at the period's peak bytes (summed across buckets) held for the elapsed and the whole period, which is an upper bound on R2's average-of-daily-peaks.
- **GraphQL range** (measured 2026-10-12). `workersInvocationsAdaptive`, `r2OperationsAdaptiveGroups` and `r2StorageAdaptiveGroups` each accept a range of up to 32 days (`maxDuration` 2,764,800 s) within the last 90 days (`notOlderThan` 7,776,000 s), and the exact usage query (`.000Z` timestamps, `$account: string!`) succeeded over 31- and 32-day ranges. One whole-period query therefore fits every billing period (at most 31 days).
- **R2 action types** (measured over 3 days, 2026-10-12): DeleteObject, GetBucketCors, GetBucketLifecycleConfiguration, GetBucketNotificationConfiguration, GetBucketSippyConfiguration, GetObject, HeadBucket, ListBuckets, ListMultipartUploads, ListObjects, PutBucket, PutObject. The guard's class lists cover all of them; an unknown one is still priced as Class A and listed in `guard.json`.
- **Edge caching of `live.m3u8`** (measured 2026-10-12). `curl -H 'Cache-Control: no-cache' https://listen.lma-radio.com/live.m3u8` returns `cf-cache-status: HIT`, so the player's probe (A2) and hugo's dead-clock check are cache hits. The edge refetches `live.m3u8` from R2 at most every 5 s, whoever asks.

## Rulings on spec ambiguities (approved by the operator 2026-10-12)

- **R1.** "Evaluation ≥ 15 min old" is measured from the last *attempt*, successful or not (`evaluated_at`). Blindness is measured from the last *success*, or from the document's creation (`since`) if none has succeeded. A raise newer than the last attempt triggers an evaluation at once.
- **R2.** If R2 cannot be read at the start of an invocation (`guard.json` or `offair.json` get throws), the blocked state is unknown. The clock then writes nothing: no WAF change, no `index.html`, no playlist. Players stall on a stale playlist, which costs nothing, and nothing is unblocked. A *corrupt* `guard.json` becomes a spend trip, which clears only with a raise or a new period. A *corrupt* `offair.json` means off the air. Both raise alerts.
- **R3.** "After `--raise-to`" means: the effective budget is strictly greater than the budget at the latch's last over-threshold evaluation. An evaluation after a raise that is still over the threshold consumes the raise, and a further raise is needed. "At a new billing period" means the evaluation's period start differs from the latch's.
- **R4.** The dead-clock alert threshold is 120 s on two consecutive checks, not "~3·d", because of the measured cron lag (amendment A4). `dead_clock_seconds` has a floor of 31 s (3·d). hugo learns that the station is blocked through a cache it refreshes every `[publish] guard_check_minutes` (15), so an unexpected 403 alerts only after `guard_check_minutes + 2` consecutive checks (17), and `guard_stale_minutes` defaults to 45 and must be at least `guard_check_minutes + 16` (the cache plus the guard's 15-minute cadence and the cron lag).
- **R5.** `--raise-to` must exceed the budget the guard uses now and may be at most $100. The clock caps any raise at $100 independently (`MAX_BUDGET_USD`).
- **R6.** The lead-floor alert defaults to 16 h (low water is 20 h). It is suppressed while tripped, because publishing stops by design then.
- **R7.** `offair` and `budget` bypass the publish lock, the guard check and the daily PUT budget. They must work while tripped and over budget, and each is one manual PUT.
- **R8.** `index.html` belongs to the clock. Both pages are bundled into the Worker (`src/pages.ts`, generated from `public/`). The clock writes the right one when the `sha256` in the object's `customMetadata` differs, checked level-triggered with one HEAD per invocation. `deploy-assets` no longer uploads `index.html`.
- **R9.** `offair.json`'s `until` is informational; nothing clears the flag automatically.
- **R10.** CPU is not metered (spec). Storage is the period peak (A5). An R2 action type the code does not know is priced as Class A, the dearer class, and listed in `guard.json` (`evaluation.unknown_action_types`).
- **R11.** A missing or invalid `MONTHLY_BUDGET_USD` or analytics secret is a *problem* that fails every evaluation and so trips blind after 6 h; an invalid `BILLING_ANNIVERSARY_DAY` does the same, because `billingPeriod` refuses it. None is ever silently defaulted. `GUARD_EVAL_SECONDS` is clamped to 60–900 and `BLIND_AFTER_SECONDS` to 900–21,600, so a typo cannot weaken the guard.
- **R12.** `BILLING_ANNIVERSARY_DAY` is a committed var (`"11"` in `wrangler.jsonc`). The day is no secret (the plan and its tests carry it), so a secret only added a deploy step and a failure path. (Cloudflare's subscriptions API could read it, but that needs a Billing-read token; that idea was rejected.)
- **R13.** Cloud alert conditions go beyond the spec's four (thresholds, tripped, Rulesets failures, lead floor). The extras:
  - `guard-reading-failing`: an early warning after 1 h of failed readings, before the 6 h blind trip;
  - `guard-unknown`;
  - `guard-state-corrupt`;
  - `offair-corrupt`;
  - `horizon-refused`;
  - `offair-without-fallback`;
  - `horizon-missing`;
  - `index-write`;
  - `guard-write`;
  - `guard-crashed`;
  - `waf-corrected`: the guard undid a hand toggle of the kill switch;
  - `budget-file-invalid`: a raise that expires after the current billing period, ignored.

  Each condition is deduped per key, repeated every 6 h while active, and resolved aloud when it is a latch or outage. A condition that returns within 15 minutes counts as continuing. Three are sent once, never repeated or resolved: `budget-file-invalid`, and the spend levels `budget-50` and `budget-80`, once per billing period and budget (their key carries both, so a raise starts the levels afresh).
- **R14.** The kill switch is reconciled every minute, so a manual toggle in the dashboard is undone within a minute and alerted (`waf-corrected`). A manual block is `transmitter offair on`, or, with hugo down, `state/offair.json` written from the Mac. If the Worker itself is broken, nothing reconciles: remove its cron trigger, then enable the kill switch by hand. The runbook says so.
- **R15.** The unit is a template, `transmitter@<user>.service`: it runs as the operator's account, which owns `~/.transmitter` and has NFS access. `WatchdogSec=45min`: transmitter pings after every step and `publish_all` after every batch, so the longest gap is one show's encode (~10–20 min on hugo), not a long catch-up publish.
- **R16.** hugo alerts dedupe per *code* (the messages vary). Level conditions are resolved explicitly:
  - `dead-clock` and `guard-stale` by the monitor;
  - `station-root` and `plan` by a successful plan step;
  - `render` by a successful render step.

  Every other code is an event (publish/prune errors, PUT budget, …): it re-sends at most every `repeat_hours`, and stops counting as active once `repeat_hours` pass without a new fire, so `status` shows no stale alarms.
- **R17.** "Upcoming window misses" (a hugo alert, and a `status` line) belongs to phase 3, which has the scheduler. `status` prints `anchors none (the scheduler and its window misses are phase 3)`.

## Global Constraints

- **Scope:** `antenna/` and `packages/transmitter/` only, plus docs. llama, emcee and herder are untouched. transmitter imports neither llama nor emcee (`test_no_llama_or_emcee_imports.py`).
- **Python 3.11** (hugo is Debian 12). No 3.12+ APIs (`itertools.batched`, `Path.walk`, PEP 695, `datetime.UTC`). Every transmitter task ends by running the suite on 3.11: `./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q`, plus the Debian-12 gate `packages/transmitter/scripts/test-in-debian12.sh` when Docker is available. Tests live in the package `packages/transmitter/tests_transmitter/` (not `tests/`). ffmpeg-dependent tests skip without ffmpeg.
- **Config is strict:** every pydantic model inherits `_StrictModel` (`extra="forbid"`). A new key needs the model, the `DEFAULT_CONFIG_TOML` template, and the docs. `test_template_parses_to_the_defaults` keeps the template equal to the defaults.
- **Atomic writes** for everything under `~/.transmitter/` (`workspace.write_json`).
- **antenna:** TypeScript strict mode. `npm test` = `node scripts/build-pages.mjs --check && vitest run` (from Task 7). `npx tsc --noEmit` must pass. **No test may reach the network.**
  - Every `fetch` is injected: `test/support.ts`'s `fakeFetch` throws on any unmatched call.
  - The email binding is injected: `emailChannel` takes the binding and the `EmailMessage` constructor.
- **The clock's spend bounds stay intact and are extended, never weakened:**
  - `MAX_PUTS = 10` per invocation;
  - a horizon whose `d` is not 10.24 is refused;
  - `LOOP_SECONDS` is clamped to 75;
  - `LIVE_MAX_AGE` is at least 1.

  The guard adds at most:
  - one GraphQL POST per 15 minutes;
  - one Rulesets GET per invocation, plus a PATCH only on a state change;
  - Class B reads (`guard.json`, `offair.json`, `budget.json`, `alerts.json`, plus one `index.html` HEAD), about 7.2k per day;
  - Class A writes only on change.
- **Guard first.** The guard runs first in every invocation; its blind rule and reconciliation run in its own `finally`. `index.html` and playlist work follow and never precede it.
- **Worktree:** `.claude/worktrees/playout-phase2` (Task 0). It has its own `.venv` and `.venv311`. Always run `./.venv/bin/python -m pytest …` from the worktree root, and check that `./.venv/bin/python -c "import transmitter; print(transmitter.__file__)"` resolves inside the worktree. **Never run a `.venv/bin/*` console script from a copy of the tree** (CLAUDE.md).
- **No deploys by implementers:**
  - no `wrangler deploy`, `wrangler secret put`, `deploy:assets`, or anything that touches the real account;
  - no `wrangler deploy --dry-run` either: the operator runs it at the checkpoint.

  Deploy, secrets and live verification are the operator's, at Task 17's human checkpoint (and Task 18's, if it runs).
- **Commit trailer:** end each commit with the attribution lines the harness supplies to you.

## Review Focus

1. **R2 cannot be read at the moment an invocation starts**, for example a transient binding error on `state/guard.json`. Expected: no unblocking of any kind — no WAF change, no `index.html`, no playlist — and an alert. Tests:
   - Task 6: `"when state cannot be read the outcome is unknown: no evaluation, no WAF change, no write"`;
   - Task 8: `"writes nothing at all when the guard cannot tell whether the station is blocked"` and `"a guard that throws is treated as unknown"`.
2. **Two overlapping invocations evaluate at once and race on `guard.json`.** One evaluation trips and the other does not. Expected: the trip is never lost. Test: Task 6 `"never loses a trip to an overlapping invocation's write"`.
3. **The kill-switch rule is renamed, duplicated, deleted or edited to a non-block action in the dashboard.** Expected:
   - the guard refuses to toggle anything and alerts `waf-api`;
   - a block stays cooperative (ENDLIST plus the off-air page);
   - the guard never touches another rule.

   Tests: Task 5 `"refuses when the rule is missing, ambiguous or not a block rule"`; Task 6 `"a WAF failure while blocked alerts and leaves the decision blocked"`.
4. **Secrets are missing or mistyped after deploy.** Expected: no network call is made with an empty token, every evaluation fails loudly, and the guard trips blind after 6 h rather than running unguarded. Tests: Task 6 `"missing secrets fail every evaluation and the WAF reconcile, loudly"` and `"a failing reading is recorded; after blind_after without success the station blocks (blind)"`.
5. **A listener's network blips mid-play while the station is fine**, versus the kill switch going on while they listen. Expected: the blip never shows the off-air notice, and the kill switch does within about 45 s. Tests: Task 11 `"a blip: network errors while stalled, then progress resumes -- never off-air"` and `"goes off-air on two consecutive off-air verdicts"`.

---

## File Structure

```
antenna/
  src/bucket.ts          BucketLike (get/head/conditional put), r2Bucket, readJsonDoc, putJson   [T1]
  src/period.ts          billing period from the anniversary day (UTC)                            [T1]
  src/pricing.ts         price table, allowances, actual + per-meter projection, thresholds       [T2]
  src/meter.ts           GraphQL account-scoped usage query + parser                              [T3]
  src/latch.ts           state/guard.json schema, the tripped latch, blind rule, budget raises     [T4]
  src/waf.ts             kill switch: find by description, reconcile enabled (Rulesets API)       [T5]
  src/conditions.ts      AlertCondition + conditions derived from guard state                     [T6]
  src/guard.ts           guardStep (read state → evaluate → finally: blind, WAF, persist)         [T6]
  src/pages.ts           GENERATED from public/index.html + public/offair.html                    [T7]
  src/indexpage.ts       index.html follows blocked (customMetadata sha256)                       [T7]
  src/clock.ts           guard first, unknown → write nothing, index, playlist, lead floor        [T1,T8,T18]
  src/env.ts             AntennaEnv (vars + secrets + bindings)                                   [T8,T9]
  src/index.ts           scheduled handler wiring                                                 [T8,T9]
  src/alerts.ts          dedupe in state/alerts.json, ntfy + email channels                       [T9]
  src/playlist.ts        lookahead (only if Task 18 is triggered)                                  [T18]
  public/nowplaying.js, public/player.js   stall watch + probe                                    [T11]
  scripts/build-pages.mjs                                                                         [T7]
  scripts/deploy-assets.mjs   no longer uploads index.html                                        [T10]
  test/support.ts        MemoryBucket, fakeTime, fakeFetch, json, usageResponse                   [T1,T3]
  test/wrangler-config.test.ts   no account details or addresses in wrangler.jsonc                [T10]
  test/*.test.ts
  wrangler.jsonc, tsconfig.json, package.json
packages/transmitter/
  src/transmitter/publish.py      guard cache also notes evaluated_at + offair                    [T14]
  src/transmitter/cloudstate.py   offair/budget writes, guard summary                             [T12]
  src/transmitter/alerts.py       Dispatcher, SMTP + ntfy channels, dedupe, active codes           [T13]
  src/transmitter/deadclock.py    dead-clock + guard-stale monitor                                 [T14]
  src/transmitter/sdnotify.py     READY/WATCHDOG/STOPPING                                          [T15]
  src/transmitter/config.py, workspace.py, errors.py, service.py, cli.py
  systemd/transmitter@.service                                                                     [T15]
  tests_transmitter/test_cloudstate.py, test_alerts.py, test_deadclock.py, test_systemd.py, …
docs/playout-setup.md               phase-2 setup + verification checklist                         [T17]
docs/superpowers/2026-10-1x-playout-phase2-verification.md   live results (operator)                [T17]
CLAUDE.md                                                                                          [T19]
```

Task order and model hints. The orchestrator assigns the model; reviewers stay on Opus. The spend-critical path (Tasks 1–8) is built and reviewed before alerts and ops.

| # | Task | Model hint |
|---|---|---|
| 0 | Worktree and environments | sonnet |
| 1 | antenna storage seam, test support, billing period | sonnet |
| 2 | Price table, spend evaluation, thresholds | opus |
| 3 | GraphQL usage meter | opus |
| 4 | The latch: guard.json, blind rule, budget raises | opus |
| 5 | Kill switch reconciliation (Rulesets API) | opus |
| 6 | guardStep: guard first, try/finally, persistence | opus |
| 7 | Bundled pages and index.html reconciliation | opus |
| 8 | Clock integration and Worker wiring | opus |
| 9 | Cloud alerts: dedupe, ntfy, email | sonnet |
| 10 | The send_email binding; index.html left to the clock | sonnet |
| 11 | Player: kill switch detected mid-play | sonnet |
| 12 | `transmitter offair` and `transmitter budget` | opus |
| 13 | hugo alerts: SMTP + ntfy, dedupe | sonnet |
| 14 | Dead-clock and guard-stale monitor | sonnet |
| 15 | sd_notify, watchdog, systemd unit | sonnet |
| 16 | Extended `transmitter status` | sonnet |
| 17 | Runbook, deploy, verification — **HUMAN CHECKPOINT** | sonnet |
| 18 | **CONDITIONAL** playlist lookahead (a day of lag + guard time) | opus |
| 19 | CLAUDE.md and approved spec amendments | sonnet |

**Dependencies.**

- Tasks 1–8 are strictly sequential. Task 9 needs Task 8. Task 10 needs Tasks 7 and 9. Task 11 is independent. Tasks 12–16 are sequential (`service.py`/`cli.py`). Task 17 needs every code task above; its checkpoint is the deploy. Task 18 needs a day of clock lines from that deploy, runs only if triggered, and ends with its own small deploy. Task 19 comes last.
- **Review gate after Task 8:** the spend path is complete. The orchestrator reports to the parent before starting Task 9.

---
### Task 0: Worktree and environments

**Model hint:** sonnet

**Files:** none committed. This task sets up the workspace every later task uses.

**Interfaces:**
- Produces: `.claude/worktrees/playout-phase2` on branch `playout-phase2` from `main`, with `./.venv` (3.14 or the system Python, all packages editable from the worktree), `./.venv311` (CPython 3.11, transmitter only), and `antenna/node_modules`.

- [ ] **Step 1: Create the worktree and its environments**

```bash
cd /Users/shawn/projects/llama
git worktree add .claude/worktrees/playout-phase2 -b playout-phase2 main
cd .claude/worktrees/playout-phase2
python3 -m venv .venv
./.venv/bin/python -m pip install -q -e packages/herder -e "packages/llama[dev]" -e packages/emcee -e "packages/transmitter[dev]"
uv venv -q --python 3.11 .venv311
uv pip install -q --python .venv311/bin/python -e "packages/transmitter[dev]"
(cd antenna && npm ci)
grep -qx '.venv311/' "$(git rev-parse --git-common-dir)/info/exclude" || echo '.venv311/' >> "$(git rev-parse --git-common-dir)/info/exclude"
```

- [ ] **Step 2: Check that the environments test this tree, and the baseline is green**

Run: `./.venv/bin/python -c "import transmitter; print(transmitter.__file__)" && ./.venv311/bin/python -c "import transmitter, sys; print(transmitter.__file__, sys.version)"`
Expected: both paths are inside `.claude/worktrees/playout-phase2/packages/transmitter/src/`; the second reports 3.11.

Run: `./.venv/bin/python -m pytest -q && ./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q && (cd antenna && npm test && npx tsc --noEmit)`
Expected: all pass (the same counts as `main`).

No commit.

---

### Task 1: antenna storage seam, test support, billing period

**Model hint:** sonnet

**Files:**
- Create: `antenna/src/bucket.ts`, `antenna/src/period.ts`
- Create: `antenna/test/support.ts`, `antenna/test/bucket.test.ts`, `antenna/test/period.test.ts`
- Modify: `antenna/src/clock.ts` (the bucket types move to `bucket.ts`), `antenna/test/clock.test.ts` (uses `test/support.ts`)

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `bucket.ts`: `interface StoredObject { text(); etag? }`, `interface ObjectInfo { etag; customMetadata? }`, `interface PutOptions { httpMetadata: {contentType, cacheControl}; customMetadata?; onlyIf?: { etagMatches } }`, `interface BucketLike { get; head; put }` (put resolves to `null` when `onlyIf` fails), `r2Bucket(b: R2Bucket): BucketLike`, `type JsonRead<T> = {kind:"absent"} | {kind:"ok"; value; etag?} | {kind:"corrupt"; error; etag?}`, `readJsonDoc<T>(bucket, key): Promise<JsonRead<T>>` (a read error propagates), `STATE_HTTP = { contentType: "application/json", cacheControl: "no-store" }`, `putJson(bucket, key, value, etag?): Promise<boolean>` (false = precondition failed).
  - `period.ts`: `interface Period { startMs; endMs }`, `billingPeriod(nowMs, day): Period` (throws for a day outside 1..31).
  - `test/support.ts`: `class MemoryBucket implements BucketLike` (`objects`, `log` of `"get k"`/`"head k"`/`"put k"`, `failGets`, `failPuts`, `seed(key, value)`, `json(key)`, `puts(key?)`), `fakeTime(start) -> { now, sleep }`, `interface FetchCall`, `type Route`, `fakeFetch(routes) -> { fetch, calls }` (routes keyed by the prefix of `"METHOD url"`; unmatched calls throw), `json(value, status?) -> Response`.
  - `clock.ts` re-exports `BucketLike`, `StoredObject`, `r2Bucket` from `bucket.ts`, so existing imports keep working.

- [ ] **Step 1: Write the failing tests**

`antenna/test/support.ts` (shared by every later antenna test):

```ts
import type { BucketLike, ObjectInfo, PutOptions } from "../src/bucket";

export interface MemoryObject {
  body: string;
  etag: string;
  contentType?: string;
  cacheControl?: string;
  customMetadata?: Record<string, string>;
}

/** In-memory BucketLike with etags and conditional puts. `log` records every
 * call ("get k", "head k", "put k"); `failGets`/`failPuts` make calls throw. */
export class MemoryBucket implements BucketLike {
  objects = new Map<string, MemoryObject>();
  log: string[] = [];
  failGets = new Set<string>();
  failPuts = new Set<string>();
  private n = 0;

  async get(key: string) {
    this.log.push(`get ${key}`);
    if (this.failGets.has(key)) throw new Error(`injected get failure: ${key}`);
    const o = this.objects.get(key);
    return o ? { text: async () => o.body, etag: o.etag } : null;
  }

  async head(key: string): Promise<ObjectInfo | null> {
    this.log.push(`head ${key}`);
    if (this.failGets.has(key)) throw new Error(`injected head failure: ${key}`);
    const o = this.objects.get(key);
    return o ? { etag: o.etag, customMetadata: o.customMetadata } : null;
  }

  async put(key: string, value: string, options: PutOptions) {
    this.log.push(`put ${key}`);
    if (this.failPuts.has(key)) throw new Error(`injected put failure: ${key}`);
    const cur = this.objects.get(key);
    if (options.onlyIf && cur?.etag !== options.onlyIf.etagMatches) return null;
    const etag = `etag-${++this.n}`;
    this.objects.set(key, { body: value, etag, ...options.httpMetadata, customMetadata: options.customMetadata });
    return { etag };
  }

  seed(key: string, value: unknown) {
    this.objects.set(key, { body: typeof value === "string" ? value : JSON.stringify(value), etag: `seed-${++this.n}` });
  }

  json(key: string): any {
    return JSON.parse(this.objects.get(key)!.body);
  }

  puts(key?: string): number {
    return this.log.filter((l) => (key ? l === `put ${key}` : l.startsWith("put "))).length;
  }
}

export function fakeTime(start: number) {
  let t = start;
  return { now: () => t, sleep: async (ms: number) => { t += ms; } };
}

export interface FetchCall {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: string | null;
}

export type Route = (call: FetchCall) => Response | Promise<Response>;

/** A fetch stand-in: each call goes to the first route whose prefix matches
 * `METHOD url`; an unmatched call throws (no test may reach the network). */
export function fakeFetch(routes: Record<string, Route>) {
  const calls: FetchCall[] = [];
  const fn = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const method = (init?.method ?? "GET").toUpperCase();
    const headers: Record<string, string> = {};
    new Headers(init?.headers).forEach((v, k) => { headers[k] = v; });
    const call = { url, method, headers, body: typeof init?.body === "string" ? init.body : null };
    calls.push(call);
    for (const [prefix, route] of Object.entries(routes)) {
      if (`${method} ${url}`.startsWith(prefix)) return route(call);
    }
    throw new Error(`unexpected fetch: ${method} ${url}`);
  };
  return { fetch: fn as typeof fetch, calls };
}

export const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status, headers: { "content-type": "application/json" } });
```

`antenna/test/bucket.test.ts`:

```ts
import { env } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { putJson, r2Bucket, readJsonDoc } from "../src/bucket";
import { MemoryBucket } from "./support";

describe("readJsonDoc / putJson", () => {
  it("distinguishes absent, parsed and corrupt objects", async () => {
    const b = new MemoryBucket();
    expect(await readJsonDoc(b, "k")).toEqual({ kind: "absent" });
    b.seed("k", { a: 1 });
    expect(await readJsonDoc(b, "k")).toMatchObject({ kind: "ok", value: { a: 1 } });
    b.seed("k", "{nope");
    expect(await readJsonDoc(b, "k")).toMatchObject({ kind: "corrupt" });
  });

  it("propagates a read error rather than calling it absent", async () => {
    const b = new MemoryBucket();
    b.failGets.add("k");
    await expect(readJsonDoc(b, "k")).rejects.toThrow(/injected/);
  });

  it("a conditional put over a stale etag writes nothing and reports it", async () => {
    const b = new MemoryBucket();
    expect(await putJson(b, "k", { v: 1 })).toBe(true);
    const first = await readJsonDoc(b, "k");
    expect(await putJson(b, "k", { v: 2 }, first.kind === "ok" ? first.etag : undefined)).toBe(true);
    expect(await putJson(b, "k", { v: 3 }, first.kind === "ok" ? first.etag : undefined)).toBe(false);
    expect(b.json("k")).toEqual({ v: 2 });
    expect(b.objects.get("k")!.cacheControl).toBe("no-store");
  });

  it("the R2 binding honours the same contract (etag, conditional put, head metadata)", async () => {
    const b = r2Bucket(env.BUCKET);
    expect(await putJson(b, "state/test.json", { v: 1 })).toBe(true);
    const r = await readJsonDoc(b, "state/test.json");
    expect(r.kind).toBe("ok");
    const etag = r.kind === "ok" ? r.etag : undefined;
    expect(typeof etag).toBe("string");
    expect(await putJson(b, "state/test.json", { v: 2 }, etag)).toBe(true);
    expect(await putJson(b, "state/test.json", { v: 3 }, etag)).toBe(false);
    expect(await (await env.BUCKET.get("state/test.json"))!.json()).toEqual({ v: 2 });
    await b.put("h", "x", { httpMetadata: { contentType: "text/plain", cacheControl: "no-store" }, customMetadata: { a: "1" } });
    expect((await b.head("h"))!.customMetadata).toEqual({ a: "1" });
    expect(await b.head("missing")).toBeNull();
  });
});
```

`antenna/test/period.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { billingPeriod } from "../src/period";

const iso = (ms: number) => new Date(ms).toISOString();
const at = (s: string) => Date.parse(s);

describe("billingPeriod", () => {
  it("runs from the anniversary day at 00:00 UTC to the next", () => {
    const p = billingPeriod(at("2026-10-20T15:00:00Z"), 11);
    expect(iso(p.startMs)).toBe("2026-10-11T00:00:00.000Z");
    expect(iso(p.endMs)).toBe("2026-11-11T00:00:00.000Z");
  });

  it("before the anniversary in a month belongs to the previous period", () => {
    const p = billingPeriod(at("2026-10-10T23:59:59Z"), 11);
    expect(iso(p.startMs)).toBe("2026-09-11T00:00:00.000Z");
    expect(iso(p.endMs)).toBe("2026-10-11T00:00:00.000Z");
  });

  it("the anniversary instant itself starts the new period", () => {
    const p = billingPeriod(at("2026-10-11T00:00:00Z"), 11);
    expect(iso(p.startMs)).toBe("2026-10-11T00:00:00.000Z");
  });

  it("crosses the year", () => {
    const p = billingPeriod(at("2027-01-05T00:00:00Z"), 11);
    expect(iso(p.startMs)).toBe("2026-12-11T00:00:00.000Z");
    expect(iso(p.endMs)).toBe("2027-01-11T00:00:00.000Z");
  });

  it("clamps day 31 to the last day of shorter months", () => {
    const p = billingPeriod(at("2027-02-15T00:00:00Z"), 31);
    expect(iso(p.startMs)).toBe("2027-01-31T00:00:00.000Z");
    expect(iso(p.endMs)).toBe("2027-02-28T00:00:00.000Z");
    expect(iso(billingPeriod(at("2027-03-01T00:00:00Z"), 31).startMs)).toBe("2027-02-28T00:00:00.000Z");
  });

  it("refuses a day outside 1..31", () => {
    for (const d of [0, 32, 1.5, Number.NaN]) expect(() => billingPeriod(Date.now(), d)).toThrow(/1\.\.31/);
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd antenna && npx vitest run test/bucket.test.ts test/period.test.ts`
Expected: FAIL. The imports `../src/bucket` and `../src/period` cannot be resolved.

- [ ] **Step 3: Implement**

`antenna/src/bucket.ts`:

```ts
/** The R2 surface the clock and the guard use, narrowed so tests can supply an
 * in-memory bucket. Conditional puts are how two overlapping invocations avoid
 * overwriting each other's guard state (spec "Cost guard"). */

export interface StoredObject {
  text(): Promise<string>;
  etag?: string;
}

export interface ObjectInfo {
  etag: string;
  customMetadata?: Record<string, string>;
}

export interface PutOptions {
  httpMetadata: { contentType: string; cacheControl: string };
  customMetadata?: Record<string, string>;
  /** Write only if the stored object still has this etag. */
  onlyIf?: { etagMatches: string };
}

export interface BucketLike {
  get(key: string): Promise<StoredObject | null>;
  head(key: string): Promise<ObjectInfo | null>;
  /** Resolves to null when an onlyIf precondition failed (nothing was written). */
  put(key: string, value: string, options: PutOptions): Promise<unknown>;
}

export function r2Bucket(b: R2Bucket): BucketLike {
  return {
    get: (key) => b.get(key),
    head: (key) => b.head(key),
    put: (key, value, options) => b.put(key, value, options),
  };
}

export type JsonRead<T> =
  | { kind: "absent" }
  | { kind: "ok"; value: T; etag?: string }
  | { kind: "corrupt"; error: string; etag?: string };

/** Read and parse a JSON object. A read error (R2 unreachable) propagates: the
 * caller decides; unparseable bytes are reported as "corrupt", never as absent. */
export async function readJsonDoc<T = unknown>(bucket: BucketLike, key: string): Promise<JsonRead<T>> {
  const obj = await bucket.get(key);
  if (obj === null) return { kind: "absent" };
  const text = await obj.text();
  try {
    return { kind: "ok", value: JSON.parse(text) as T, etag: obj.etag };
  } catch (e) {
    return { kind: "corrupt", error: e instanceof Error ? e.message : String(e), etag: obj.etag };
  }
}

export const STATE_HTTP = { contentType: "application/json", cacheControl: "no-store" };

/** PUT a state document; with `etag`, only over that version. False = precondition failed. */
export async function putJson(bucket: BucketLike, key: string, value: unknown, etag?: string): Promise<boolean> {
  const result = await bucket.put(key, JSON.stringify(value) + "\n", {
    httpMetadata: STATE_HTTP,
    ...(etag ? { onlyIf: { etagMatches: etag } } : {}),
  });
  return result !== null;
}
```

`antenna/src/period.ts`:

```ts
/** Cloudflare billing periods are anniversary-based (UTC), not calendar months
 * (spec "Platform facts"). The anniversary day comes from the Billing page. */

export interface Period {
  startMs: number;
  endMs: number;
}

/** Midnight UTC on `day` of the month; a month without that day uses its last day. */
function anniversary(year: number, month: number, day: number): number {
  const lastDay = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  return Date.UTC(year, month, Math.min(day, lastDay));
}

export function billingPeriod(nowMs: number, day: number): Period {
  if (!Number.isInteger(day) || day < 1 || day > 31) {
    throw new Error(`billing anniversary day must be an integer 1..31, not ${day}`);
  }
  const now = new Date(nowMs);
  let year = now.getUTCFullYear();
  let month = now.getUTCMonth();
  let startMs = anniversary(year, month, day);
  if (startMs > nowMs) {
    month -= 1;
    if (month < 0) {
      month = 11;
      year -= 1;
    }
    startMs = anniversary(year, month, day);
  }
  const endMs = month === 11 ? anniversary(year + 1, 0, day) : anniversary(year, month + 1, day);
  return { startMs, endMs };
}
```

In `antenna/src/clock.ts`, replace the head of the file, from the first import through the closing brace of `r2Bucket`:

```ts
import { type Horizon, gridOf, indexAt, startMs } from "./grid";
import { buildPlaylist, type FallbackIndex, isOffair, type PlaylistConfig, usableFallback } from "./playlist";

export interface StoredObject {
  text(): Promise<string>;
}

export interface BucketLike {
  get(key: string): Promise<StoredObject | null>;
  put(key: string, value: string, options: { httpMetadata: { contentType: string; cacheControl: string } }): Promise<unknown>;
}

export function r2Bucket(b: R2Bucket): BucketLike {
  return {
    get: (key) => b.get(key),
    put: (key, value, options) => b.put(key, value, options),
  };
}
```

with:

```ts
import type { BucketLike } from "./bucket";
import { type Horizon, gridOf, indexAt, startMs } from "./grid";
import { buildPlaylist, type FallbackIndex, isOffair, type PlaylistConfig, usableFallback } from "./playlist";

export { type BucketLike, r2Bucket, type StoredObject } from "./bucket";
```

In `antenna/test/clock.test.ts`, make three edits:

1. Delete the local `class MemoryBucket implements BucketLike { … }` and the local `function fakeTime(start: number) { … }`.
2. Change the clock import line to `import { type ClockConfig, configFromEnv, MAX_PUTS, putCap, r2Bucket, runClock } from "../src/clock";`.
3. Add `import { fakeTime, MemoryBucket } from "./support";` after `import worker from "../src/index";`.

Nothing else in that file changes in this task.

- [ ] **Step 4: Run the tests and the type check**

Run: `cd antenna && npx vitest run && npx tsc --noEmit`
Expected: PASS (5 files: the three existing ones plus `bucket` and `period`); no type errors. `bucket.test.ts`'s last test also proves that the R2 binding in the Workers runtime honours `onlyIf: { etagMatches }`, returning `null` for a stale etag.

- [ ] **Step 5: Commit**

```bash
git add antenna/src/bucket.ts antenna/src/period.ts antenna/src/clock.ts antenna/test/support.ts antenna/test/bucket.test.ts antenna/test/period.test.ts antenna/test/clock.test.ts
git commit -m "feat(antenna): storage seam with etags and conditional puts; billing period; shared test support"
```

---

### Task 2: Price table, spend evaluation, thresholds

**Model hint:** opus (spend path)

**Files:**
- Create: `antenna/src/pricing.ts`, `antenna/test/pricing.test.ts`

**Interfaces:**
- Consumes: `Period` (Task 1).
- Produces:
  - `type Meter = "workersRequests" | "r2ClassA" | "r2ClassB" | "r2StorageGbMonth"`, `METERS`, `interface PriceTable`, `PRICES` ($5 base; 10M Workers requests then $0.30/M; R2 Class A 1M then $4.50/M; Class B 10M then $0.36/M; storage 10 GB-month then $0.015/GB-month).
  - `type Usage = Record<Meter, number>`, `priceUsage(u, p?) -> { totalUsd, perMeterUsd }`.
  - `interface OpCounts { workersRequests; r2ClassA; r2ClassB }`, `interface Reading { periodToDate: OpCounts; recent: OpCounts; recentMs; storageBytes; unknownActionTypes: string[] }`.
  - `interface Evaluation { atMs; actualUsd; projectedUsd; budgetUsd; periodToDate: Usage; projected: Usage; unknownActionTypes }`, `evaluateSpend(reading, period, nowMs, budgetUsd, p?) -> Evaluation`.
  - `TRIP_ACTUAL = 0.9`, `TRIP_PROJECTED = 1.0`, `ALERT_LEVELS = [0.5, 0.8]`, `overThreshold({actualUsd, projectedUsd, budgetUsd}) -> boolean`.

- [ ] **Step 1: Write the failing test**

`antenna/test/pricing.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { evaluateSpend, overThreshold, PRICES, priceUsage, type Reading } from "../src/pricing";

const DAY = 86_400_000;
const PERIOD = { startMs: Date.parse("2026-10-11T00:00:00Z"), endMs: Date.parse("2026-11-11T00:00:00Z") };
const zero = { workersRequests: 0, r2ClassA: 0, r2ClassB: 0 };

describe("priceUsage", () => {
  it("is the $5 base while every meter is inside its allowance", () => {
    expect(priceUsage({ workersRequests: 9_999_999, r2ClassA: 1_000_000, r2ClassB: 10_000_000, r2StorageGbMonth: 10 }).totalUsd)
      .toBe(5);
  });

  it("prices only the usage beyond each allowance", () => {
    const r = priceUsage({ workersRequests: 12_000_000, r2ClassA: 3_000_000, r2ClassB: 20_000_000, r2StorageGbMonth: 30 });
    expect(r.perMeterUsd.workersRequests).toBeCloseTo(0.6, 10);
    expect(r.perMeterUsd.r2ClassA).toBeCloseTo(9.0, 10);
    expect(r.perMeterUsd.r2ClassB).toBeCloseTo(3.6, 10);
    expect(r.perMeterUsd.r2StorageGbMonth).toBeCloseTo(0.3, 10);
    expect(r.totalUsd).toBeCloseTo(5 + 0.6 + 9 + 3.6 + 0.3, 10);
  });

  it("carries the published prices", () => {
    expect(PRICES.baseUsd).toBe(5);
    expect(PRICES.meters.r2ClassA).toEqual({ included: 1_000_000, usdPerUnit: 4.5e-6 });
  });
});

describe("evaluateSpend", () => {
  it("projects each meter from the recent rate through the allowances, not a dollar average", () => {
    const now = PERIOD.startMs + 10 * DAY; // 21 days left
    const r: Reading = {
      periodToDate: { workersRequests: 100_000, r2ClassA: 500_000, r2ClassB: 0 },
      recent: { workersRequests: 0, r2ClassA: 30_000, r2ClassB: 0 }, // 10k Class A per hour
      recentMs: 3 * 3_600_000, storageBytes: 0, unknownActionTypes: [],
    };
    const e = evaluateSpend(r, PERIOD, now, 15);
    expect(e.actualUsd).toBe(5); // 0.5M Class A is inside the 1M allowance
    // 500k + 10k/h * 504 h = 5.54M Class A: 4.54M billable * $4.50/M
    expect(e.projected.r2ClassA).toBeCloseTo(5_540_000, 3);
    expect(e.projectedUsd).toBeCloseTo(5 + 4.54 * 4.5, 6);
  });

  it("holds the peak storage over the elapsed and the whole period", () => {
    const now = PERIOD.startMs + 15 * DAY;
    const e = evaluateSpend({ periodToDate: zero, recent: zero, recentMs: 3_600_000, storageBytes: 60e9,
                              unknownActionTypes: [] }, PERIOD, now, 15);
    expect(e.periodToDate.r2StorageGbMonth).toBeCloseTo(30, 10); // 60 GB * 15/30
    expect(e.projected.r2StorageGbMonth).toBeCloseTo(62, 10); // 60 GB * 31/30
  });

  it("has nothing left to project at the period's end", () => {
    const e = evaluateSpend({ periodToDate: zero, recent: { ...zero, r2ClassA: 1e9 }, recentMs: 1, storageBytes: 0,
                              unknownActionTypes: [] }, PERIOD, PERIOD.endMs, 15);
    expect(e.projectedUsd).toBe(5);
  });
});

describe("overThreshold", () => {
  it("trips at actual >= 90% or projected >= 100%", () => {
    expect(overThreshold({ actualUsd: 13.49, projectedUsd: 14.99, budgetUsd: 15 })).toBe(false);
    expect(overThreshold({ actualUsd: 13.5, projectedUsd: 13.5, budgetUsd: 15 })).toBe(true);
    expect(overThreshold({ actualUsd: 5, projectedUsd: 15, budgetUsd: 15 })).toBe(true);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd antenna && npx vitest run test/pricing.test.ts`
Expected: FAIL. `../src/pricing` cannot be resolved.

- [ ] **Step 3: Implement**

`antenna/src/pricing.ts`:

```ts
/** The guard's price table and spend arithmetic (spec "Cost guard"). Prices
 * and allowances are Cloudflare's published ones (Workers Paid, R2 Standard),
 * checked 2026-10-11; the $5 Workers Paid base is part of every total, so
 * monthly_budget_usd includes it. Workers CPU time is not metered: the dataset
 * exposes it only as percentiles and the clock's CPU is bounded by design. */

import type { Period } from "./period";

export type Meter = "workersRequests" | "r2ClassA" | "r2ClassB" | "r2StorageGbMonth";
export const METERS: Meter[] = ["workersRequests", "r2ClassA", "r2ClassB", "r2StorageGbMonth"];

export interface PriceTable {
  baseUsd: number;
  meters: Record<Meter, { included: number; usdPerUnit: number }>;
}

export const PRICES: PriceTable = {
  baseUsd: 5,
  meters: {
    workersRequests: { included: 10_000_000, usdPerUnit: 0.3 / 1_000_000 },
    r2ClassA: { included: 1_000_000, usdPerUnit: 4.5 / 1_000_000 },
    r2ClassB: { included: 10_000_000, usdPerUnit: 0.36 / 1_000_000 },
    r2StorageGbMonth: { included: 10, usdPerUnit: 0.015 },
  },
};

export type Usage = Record<Meter, number>;

export function priceUsage(u: Usage, p: PriceTable = PRICES): { totalUsd: number; perMeterUsd: Usage } {
  const perMeterUsd = {} as Usage;
  let totalUsd = p.baseUsd;
  for (const m of METERS) {
    const { included, usdPerUnit } = p.meters[m];
    perMeterUsd[m] = Math.max(0, u[m] - included) * usdPerUnit;
    totalUsd += perMeterUsd[m];
  }
  return { totalUsd, perMeterUsd };
}

/** Request counts from the analytics read (storage is reported separately). */
export interface OpCounts {
  workersRequests: number;
  r2ClassA: number;
  r2ClassB: number;
}

export interface Reading {
  periodToDate: OpCounts; // period start .. now
  recent: OpCounts; // the last recentMs (ending a few minutes ago: analytics lag)
  recentMs: number;
  storageBytes: number; // peak bytes stored in the period, summed over buckets
  unknownActionTypes: string[];
}

export interface Evaluation {
  atMs: number;
  actualUsd: number;
  projectedUsd: number;
  budgetUsd: number;
  periodToDate: Usage;
  projected: Usage;
  unknownActionTypes: string[];
}

/** R2 bills storage as the average of daily peaks over 30 days. */
const STORAGE_MONTH_MS = 30 * 86_400_000;
/** Conservative: decimal GB (more GB than GiB for the same bytes). */
const BYTES_PER_GB = 1e9;

export const TRIP_ACTUAL = 0.9;
export const TRIP_PROJECTED = 1.0;
export const ALERT_LEVELS = [0.5, 0.8] as const;

/**
 * Actual = period-to-date usage priced through the allowances. Projected =
 * per meter, period-to-date plus the recent rate times the time left, then
 * priced through the allowances (never a linear month-to-date dollar average).
 * Storage is the period's peak held for the elapsed (actual) or whole
 * (projected) period: an upper bound of R2's average-of-daily-peaks.
 */
export function evaluateSpend(r: Reading, period: Period, nowMs: number, budgetUsd: number,
                              p: PriceTable = PRICES): Evaluation {
  const elapsedMs = Math.max(0, Math.min(nowMs, period.endMs) - period.startMs);
  const remainingMs = Math.max(0, period.endMs - nowMs);
  const gb = r.storageBytes / BYTES_PER_GB;
  const rate = (m: keyof OpCounts) => (r.recentMs > 0 ? r.recent[m] / r.recentMs : 0);
  const periodToDate: Usage = {
    workersRequests: r.periodToDate.workersRequests,
    r2ClassA: r.periodToDate.r2ClassA,
    r2ClassB: r.periodToDate.r2ClassB,
    r2StorageGbMonth: (gb * elapsedMs) / STORAGE_MONTH_MS,
  };
  const projected: Usage = {
    workersRequests: periodToDate.workersRequests + rate("workersRequests") * remainingMs,
    r2ClassA: periodToDate.r2ClassA + rate("r2ClassA") * remainingMs,
    r2ClassB: periodToDate.r2ClassB + rate("r2ClassB") * remainingMs,
    r2StorageGbMonth: (gb * (period.endMs - period.startMs)) / STORAGE_MONTH_MS,
  };
  return {
    atMs: nowMs,
    actualUsd: priceUsage(periodToDate, p).totalUsd,
    projectedUsd: priceUsage(projected, p).totalUsd,
    budgetUsd,
    periodToDate,
    projected,
    unknownActionTypes: r.unknownActionTypes,
  };
}

/** Trip when actual >= 90% or projected >= 100% of the budget. */
export function overThreshold(e: Pick<Evaluation, "actualUsd" | "projectedUsd" | "budgetUsd">): boolean {
  return e.actualUsd >= TRIP_ACTUAL * e.budgetUsd || e.projectedUsd >= TRIP_PROJECTED * e.budgetUsd;
}
```

- [ ] **Step 4: Run the tests and the type check**

Run: `cd antenna && npx vitest run test/pricing.test.ts && npx tsc --noEmit`
Expected: PASS; no type errors.

- [ ] **Step 5: Commit**

```bash
git add antenna/src/pricing.ts antenna/test/pricing.test.ts
git commit -m "feat(antenna): guard price table and per-meter spend projection through the allowances"
```

---
### Task 3: GraphQL usage meter

**Model hint:** opus (spend path)

**Files:**
- Create: `antenna/src/meter.ts`, `antenna/test/meter.test.ts`
- Modify: `antenna/test/support.ts` (append `usageResponse`)

**Interfaces:**
- Consumes: `Period` (Task 1); `OpCounts`, `Reading` (Task 2); `fakeFetch`, `json` (Task 1).
- Produces:
  - `GRAPHQL_URL`, `RECENT_MS` (3 h), `LAG_MS` (5 min), `ROW_LIMIT` (10,000), `CLASS_A`, `CLASS_B`, `FREE_OPS` (Sets of R2 `actionType` strings), `USAGE_QUERY`.
  - `interface MeterCredentials { accountId; token }`, `usageVariables(accountId, period, nowMs)`.
  - `parseUsage(body: unknown): Reading` (throws on GraphQL errors, no account, a missing dataset, a non-count value, or a truncated result).
  - `readUsage(fetchFn, creds, period, nowMs): Promise<Reading>` (POST with a bearer token and a 15 s timeout; throws on HTTP errors or a non-JSON body).
  - `test/support.ts`: `usageResponse({ workers?, workersRecent?, ops?, opsRecent?, buckets? })`, a canned account-scoped response.

Notes for the implementer:

- This reads **account-scoped** datasets (all Workers and all buckets): the spec's account is dedicated to the station, so the meters mean what they say.
- Sampled estimates are fine.
- Storage is the sum over buckets of each bucket's peak in the period. A `max` with no `bucketName` dimension would return one bucket's peak, not the account's.
- One query covers the whole period to date. That is valid: each dataset accepts up to 32 days per query within the last 90 days, and a billing period is at most 31 days (measured 2026-10-12, amendment A5). The comment above `USAGE_QUERY` says so.
- The three Sets cover every `actionType` this account reported over 3 days (measured 2026-10-12, A5). One in none of them is priced as Class A and reported in `guard.json` (`evaluation.unknown_action_types`); Task 17's checklist confirms the list stays empty.

- [ ] **Step 1: Write the failing test**

Append to `antenna/test/support.ts`:

```ts
/** A canned account-scoped response, shaped as the API returns it. */
export function usageResponse(o: { workers?: number; workersRecent?: number; ops?: Record<string, number>;
                                   opsRecent?: Record<string, number>; buckets?: [number, number][] } = {}) {
  const ops = (m: Record<string, number>) =>
    Object.entries(m).map(([actionType, requests]) => ({ sum: { requests }, dimensions: { actionType } }));
  return {
    data: { viewer: { accounts: [{
      workersToDate: [{ sum: { requests: o.workers ?? 40_000 } }],
      workersRecent: [{ sum: { requests: o.workersRecent ?? 180 } }],
      r2ToDate: ops(o.ops ?? { PutObject: 200_000, GetObject: 300_000, DeleteObject: 80_000 }),
      r2Recent: ops(o.opsRecent ?? { PutObject: 3_000, GetObject: 4_000 }),
      storage: (o.buckets ?? [[1.4e9, 2e6]]).map(([payloadSize, metadataSize], i) =>
        ({ max: { payloadSize, metadataSize }, dimensions: { bucketName: `b${i}` } })),
    }] } },
    errors: null,
  };
}
```

`antenna/test/meter.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { GRAPHQL_URL, LAG_MS, parseUsage, readUsage, RECENT_MS, ROW_LIMIT, usageVariables } from "../src/meter";
import { fakeFetch, json, usageResponse } from "./support";

const PERIOD = { startMs: Date.parse("2026-10-11T00:00:00Z"), endMs: Date.parse("2026-11-11T00:00:00Z") };
const NOW = Date.parse("2026-10-20T12:00:00Z");

describe("parseUsage", () => {
  it("sums Workers requests, classes R2 operations and sums per-bucket peak storage", () => {
    const r = parseUsage(usageResponse({ ops: { PutObject: 10, ListObjects: 1, GetObject: 5, HeadObject: 2, DeleteObject: 99 },
                                         buckets: [[1e9, 1e6], [2e9, 0]] }));
    expect(r.periodToDate).toEqual({ workersRequests: 40_000, r2ClassA: 11, r2ClassB: 7 });
    expect(r.recent).toEqual({ workersRequests: 180, r2ClassA: 3_000, r2ClassB: 4_000 });
    expect(r.recentMs).toBe(RECENT_MS);
    expect(r.storageBytes).toBe(3e9 + 1e6);
    expect(r.unknownActionTypes).toEqual([]);
  });

  it("prices an unknown action type as Class A and reports it", () => {
    const r = parseUsage(usageResponse({ ops: { PutObject: 1, SomethingNew: 7 } }));
    expect(r.periodToDate.r2ClassA).toBe(8);
    expect(r.unknownActionTypes).toEqual(["SomethingNew"]);
  });

  it("knows every action type the account reported (measured 2026-10-12)", () => {
    const seen = ["DeleteObject", "GetBucketCors", "GetBucketLifecycleConfiguration", "GetBucketNotificationConfiguration",
                  "GetBucketSippyConfiguration", "GetObject", "HeadBucket", "ListBuckets", "ListMultipartUploads",
                  "ListObjects", "PutBucket", "PutObject"];
    const r = parseUsage(usageResponse({ ops: Object.fromEntries(seen.map((a) => [a, 1])) }));
    expect(r.unknownActionTypes).toEqual([]);
    expect(r.periodToDate).toMatchObject({ r2ClassA: 5, r2ClassB: 6 }); // DeleteObject is free
  });

  it("throws on GraphQL errors, a missing account, a missing dataset, a bad count or a truncated result", () => {
    expect(() => parseUsage({ data: null, errors: [{ message: "not authorized" }] })).toThrow(/not authorized/);
    expect(() => parseUsage({ data: { viewer: { accounts: [] } }, errors: null })).toThrow(/CF_ACCOUNT_ID/);
    const noStorage = usageResponse();
    delete (noStorage.data.viewer.accounts[0] as Record<string, unknown>).storage;
    expect(() => parseUsage(noStorage)).toThrow(/storage missing/);
    const bad = usageResponse();
    bad.data.viewer.accounts[0].workersToDate = [{ sum: { requests: "lots" as unknown as number } }];
    expect(() => parseUsage(bad)).toThrow(/not a count/);
    const truncated = usageResponse();
    truncated.data.viewer.accounts[0].r2ToDate = Array.from({ length: ROW_LIMIT },
      () => ({ sum: { requests: 1 }, dimensions: { actionType: "GetObject" } }));
    expect(() => parseUsage(truncated)).toThrow(/truncated/);
  });
});

describe("readUsage", () => {
  it("POSTs the account-scoped query with the bearer token and the windows", async () => {
    const f = fakeFetch({ [`POST ${GRAPHQL_URL}`]: () => json(usageResponse()) });
    const r = await readUsage(f.fetch, { accountId: "acct", token: "tok" }, PERIOD, NOW);
    expect(r.periodToDate.r2ClassA).toBe(200_000);
    expect(f.calls).toHaveLength(1);
    expect(f.calls[0].headers.authorization).toBe("Bearer tok");
    const sent = JSON.parse(f.calls[0].body!);
    expect(sent.variables).toEqual(usageVariables("acct", PERIOD, NOW));
    expect(sent.variables.start).toBe("2026-10-11T00:00:00.000Z");
    expect(Date.parse(sent.variables.recentEnd)).toBe(NOW - LAG_MS);
    expect(Date.parse(sent.variables.recentEnd) - Date.parse(sent.variables.recentStart)).toBe(RECENT_MS);
    expect(sent.query).toContain("accountTag: $account");
  });

  it("throws on an HTTP error or a non-JSON body", async () => {
    const e403 = fakeFetch({ "POST ": () => new Response("forbidden", { status: 403 }) });
    await expect(readUsage(e403.fetch, { accountId: "a", token: "t" }, PERIOD, NOW)).rejects.toThrow(/HTTP 403/);
    const html = fakeFetch({ "POST ": () => new Response("<html>", { status: 200 }) });
    await expect(readUsage(html.fetch, { accountId: "a", token: "t" }, PERIOD, NOW)).rejects.toThrow(/not JSON/);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd antenna && npx vitest run test/meter.test.ts`
Expected: FAIL. `../src/meter` cannot be resolved.

- [ ] **Step 3: Implement**

`antenna/src/meter.ts`:

```ts
/** Usage read from Cloudflare's GraphQL Analytics API, account-scoped (all
 * Workers and buckets), with an Account Analytics: Read token. The adaptive
 * datasets are sampled estimates; operations lag ~1-2 min and storage ~45 min
 * (measured 2026-10-11), so the recent window ends LAG_MS before now. Any
 * failure -- HTTP, GraphQL errors, a missing account, a truncated result --
 * throws: the guard counts it as a failed reading. */

import type { Period } from "./period";
import type { OpCounts, Reading } from "./pricing";

export const GRAPHQL_URL = "https://api.cloudflare.com/client/v4/graphql";
export const RECENT_MS = 3 * 3_600_000;
export const LAG_MS = 5 * 60_000;
export const ROW_LIMIT = 10_000;
const TIMEOUT_MS = 15_000;

/** R2 operation classes (R2 pricing page). Free operations are not billed; an
 * actionType in no list is priced as Class A, the dearer class, and reported.
 * Every actionType this account reported over 3 days is listed (measured
 * 2026-10-12). */
export const CLASS_A = new Set([
  "ListBuckets", "PutBucket", "ListObjects", "PutObject", "CopyObject", "CompleteMultipartUpload",
  "CreateMultipartUpload", "LifecycleStorageTierTransition", "ListMultipartUploads", "UploadPart",
  "UploadPartCopy", "ListParts", "PutBucketEncryption", "PutBucketCors", "PutBucketLifecycleConfiguration",
]);
export const CLASS_B = new Set([
  "HeadBucket", "HeadObject", "GetObject", "UsageSummary", "GetBucketEncryption", "GetBucketLocation",
  "GetBucketCors", "GetBucketLifecycleConfiguration", "GetBucketNotificationConfiguration", "GetBucketSippyConfiguration",
]);
export const FREE_OPS = new Set(["DeleteObject", "DeleteBucket", "AbortMultipartUpload"]);

/** One query covers the whole period to date. Each dataset accepts a range of up
 * to 32 days (maxDuration 2,764,800 s) within the last 90 days (notOlderThan
 * 7,776,000 s), and a billing period is at most 31 days. Measured for this
 * account 2026-10-12, when this exact query (`.000Z` timestamps, `$account:
 * string!`) succeeded over 31- and 32-day ranges. */
export const USAGE_QUERY = `query StationUsage($account: string!, $start: Time!, $now: Time!, $recentStart: Time!, $recentEnd: Time!) {
  viewer {
    accounts(filter: { accountTag: $account }) {
      workersToDate: workersInvocationsAdaptive(limit: ${ROW_LIMIT}, filter: { datetime_geq: $start, datetime_leq: $now }) { sum { requests } }
      workersRecent: workersInvocationsAdaptive(limit: ${ROW_LIMIT}, filter: { datetime_geq: $recentStart, datetime_leq: $recentEnd }) { sum { requests } }
      r2ToDate: r2OperationsAdaptiveGroups(limit: ${ROW_LIMIT}, filter: { datetime_geq: $start, datetime_leq: $now }) { sum { requests } dimensions { actionType } }
      r2Recent: r2OperationsAdaptiveGroups(limit: ${ROW_LIMIT}, filter: { datetime_geq: $recentStart, datetime_leq: $recentEnd }) { sum { requests } dimensions { actionType } }
      storage: r2StorageAdaptiveGroups(limit: ${ROW_LIMIT}, filter: { datetime_geq: $start, datetime_leq: $now }) { max { payloadSize metadataSize } dimensions { bucketName } }
    }
  }
}`;

export interface MeterCredentials {
  accountId: string;
  token: string;
}

export function usageVariables(accountId: string, period: Period, nowMs: number) {
  const iso = (ms: number) => new Date(ms).toISOString();
  const recentEnd = nowMs - LAG_MS;
  return { account: accountId, start: iso(period.startMs), now: iso(nowMs),
           recentStart: iso(recentEnd - RECENT_MS), recentEnd: iso(recentEnd) };
}

type Rows = { sum?: { requests?: unknown }; max?: Record<string, unknown>; dimensions?: Record<string, unknown> }[];

function rows(acct: Record<string, unknown>, name: string): Rows {
  const r = acct[name];
  if (!Array.isArray(r)) throw new Error(`analytics: ${name} missing from the response`);
  if (r.length >= ROW_LIMIT) throw new Error(`analytics: ${name} returned ${r.length} rows (truncated)`);
  return r as Rows;
}

function count(v: unknown, what: string): number {
  if (typeof v !== "number" || !Number.isFinite(v) || v < 0) throw new Error(`analytics: ${what} is not a count: ${JSON.stringify(v)}`);
  return v;
}

function sumRequests(rs: Rows, what: string): number {
  return rs.reduce((t, r) => t + count(r.sum?.requests, what), 0);
}

function r2Counts(rs: Rows, unknown: Set<string>): Pick<OpCounts, "r2ClassA" | "r2ClassB"> {
  let r2ClassA = 0;
  let r2ClassB = 0;
  for (const r of rs) {
    const action = String(r.dimensions?.actionType ?? "");
    const n = count(r.sum?.requests, `r2 ${action} requests`);
    if (CLASS_B.has(action)) r2ClassB += n;
    else if (FREE_OPS.has(action)) continue;
    else {
      if (!CLASS_A.has(action)) unknown.add(action);
      r2ClassA += n;
    }
  }
  return { r2ClassA, r2ClassB };
}

/** Parse a GraphQL response body into a Reading (throws on anything unexpected). */
export function parseUsage(body: unknown): Reading {
  const b = body as { data?: { viewer?: { accounts?: unknown[] } }; errors?: { message?: string }[] | null };
  if (b?.errors && b.errors.length > 0) {
    throw new Error(`analytics: ${b.errors.map((e) => e?.message ?? "error").join("; ")}`);
  }
  const accounts = b?.data?.viewer?.accounts;
  if (!Array.isArray(accounts) || accounts.length !== 1) {
    throw new Error("analytics: no account in the response (check CF_ACCOUNT_ID and the token's account scope)");
  }
  const acct = accounts[0] as Record<string, unknown>;
  const unknown = new Set<string>();
  const periodToDate = { workersRequests: sumRequests(rows(acct, "workersToDate"), "workers requests"),
                         ...r2Counts(rows(acct, "r2ToDate"), unknown) };
  const recent = { workersRequests: sumRequests(rows(acct, "workersRecent"), "workers requests"),
                   ...r2Counts(rows(acct, "r2Recent"), unknown) };
  const storageBytes = rows(acct, "storage").reduce(
    (t, r) => t + count(r.max?.payloadSize, "payloadSize") + count(r.max?.metadataSize ?? 0, "metadataSize"), 0);
  return { periodToDate, recent, recentMs: RECENT_MS, storageBytes, unknownActionTypes: [...unknown].sort() };
}

export async function readUsage(fetchFn: typeof fetch, creds: MeterCredentials, period: Period,
                                nowMs: number): Promise<Reading> {
  const res = await fetchFn(GRAPHQL_URL, {
    method: "POST",
    headers: { authorization: `Bearer ${creds.token}`, "content-type": "application/json" },
    body: JSON.stringify({ query: USAGE_QUERY, variables: usageVariables(creds.accountId, period, nowMs) }),
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`analytics: HTTP ${res.status}: ${text.slice(0, 200)}`);
  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch {
    throw new Error(`analytics: response is not JSON: ${text.slice(0, 200)}`);
  }
  return parseUsage(body);
}
```

- [ ] **Step 4: Run the tests and the type check**

Run: `cd antenna && npx vitest run && npx tsc --noEmit`
Expected: PASS; no type errors.

- [ ] **Step 5: Commit**

```bash
git add antenna/src/meter.ts antenna/test/meter.test.ts antenna/test/support.ts
git commit -m "feat(antenna): account-scoped GraphQL usage meter (Workers requests, R2 classes, storage)"
```

---

### Task 4: The latch — guard.json, blind rule, budget raises

**Model hint:** opus (spend path)

**Files:**
- Create: `antenna/src/latch.ts`, `antenna/test/latch.test.ts`

**Interfaces:**
- Consumes: `Period` (Task 1); `Evaluation`, `overThreshold`, `PRICES`, `Usage` (Task 2).
- Produces:
  - `GUARD_KEY = "state/guard.json"`, `BUDGET_KEY = "state/budget.json"`, `OFFAIR_KEY = "state/offair.json"`, `MAX_BUDGET_USD = 100`.
  - `type TripReason = "spend" | "blind"`, `interface StoredEvaluation`, and `interface GuardDoc`, which is the `state/guard.json` schema transmitter reads (Task 12). Its fields:
    - `schema: 1`, `tripped`, `reason`, `tripped_at`;
    - `tripped_period_start`, `tripped_budget_usd`, `since`, `last_success`;
    - `evaluated_at`, `last_error`, `period: {start, end}`, `evaluation`, `waf: {enabled, error}`.
  - `freshGuardDoc(nowMs)`, `parseGuardDoc(raw) -> GuardDoc | null`, `corruptGuardDoc(nowMs, period | null, budgetUsd)`.
  - `type Attempt = { ok: true; evaluation; period; baseBudgetUsd } | { ok: false; atMs; error }`, `applyAttempt(prev, attempt) -> GuardDoc`, `applyBlindRule(doc, nowMs, blindAfterMs) -> GuardDoc`, `shouldEvaluate(doc, nowMs, intervalMs, budgetWrittenAtMs | null) -> boolean`.
  - `interface EffectiveBudget { budgetUsd; raisedUntil; writtenAtMs; invalid }`, `effectiveBudget(baseUsd, raw, nowMs, periodEndMs)` (a raise that expires after `periodEndMs` is ignored and described in `invalid`; a `written_at` ahead of `nowMs` is clamped to it), `validBaseBudget(v)`.

The latch rules (spec "Blocking", rulings R1 and R3) are in the module docstring below. The tests are the authority. Each rule:
- **set spend:** an evaluation over a threshold always leaves or sets reason `spend`;
- **set blind:** no successful reading for `blind_after`;
- **clear blind:** the first successful reading under the thresholds;
- **clear spend:** a successful reading under the thresholds in a new period, or with a budget above the one it last tripped at;
- **failed reading:** never sets or clears the latch;
- **blind vs spend:** blind never downgrades spend.

- [ ] **Step 1: Write the failing test**

`antenna/test/latch.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { type Attempt, applyAttempt, applyBlindRule, corruptGuardDoc, effectiveBudget, freshGuardDoc, type GuardDoc,
         MAX_BUDGET_USD, parseGuardDoc, shouldEvaluate, validBaseBudget } from "../src/latch";
import type { Evaluation } from "../src/pricing";

const H = 3_600_000;
const T0 = Date.parse("2026-10-20T00:00:00Z");
const P1 = { startMs: Date.parse("2026-10-11T00:00:00Z"), endMs: Date.parse("2026-11-11T00:00:00Z") };
const P2 = { startMs: P1.endMs, endMs: Date.parse("2026-12-11T00:00:00Z") };
const usage = { workersRequests: 0, r2ClassA: 0, r2ClassB: 0, r2StorageGbMonth: 0 };

function ok(atMs: number, actualUsd: number, projectedUsd: number, budgetUsd = 15, period = P1): Attempt {
  const evaluation: Evaluation = { atMs, actualUsd, projectedUsd, budgetUsd, periodToDate: usage, projected: usage,
                                   unknownActionTypes: [] };
  return { ok: true, evaluation, period, baseBudgetUsd: 15 };
}
const fail = (atMs: number): Attempt => ({ ok: false, atMs, error: "boom" });
const UNDER = [5.2, 6] as const;
const OVER = [5.2, 15] as const;

describe("the tripped latch", () => {
  it("sets reason spend on a reading over a threshold and records the period and budget", () => {
    const d = applyAttempt(freshGuardDoc(T0), ok(T0, ...OVER));
    expect(d).toMatchObject({ tripped: true, reason: "spend", tripped_period_start: "2026-10-11T00:00:00.000Z",
                              tripped_budget_usd: 15, last_success: new Date(T0).toISOString() });
    expect(d.evaluation).toMatchObject({ actual_usd: 5.2, projected_usd: 15, budget_usd: 15, base_budget_usd: 15 });
  });

  it("does not clear spend on a later reading under the thresholds in the same period at the same budget", () => {
    let d = applyAttempt(freshGuardDoc(T0), ok(T0, ...OVER));
    d = applyAttempt(d, ok(T0 + H, ...UNDER));
    expect(d).toMatchObject({ tripped: true, reason: "spend", tripped_at: new Date(T0).toISOString() });
  });

  it("clears spend in a new period, only when that period's reading is under the thresholds", () => {
    let d = applyAttempt(freshGuardDoc(T0), ok(T0, ...OVER));
    expect(applyAttempt(d, ok(P2.startMs + H, 5, 15, 15, P2)).tripped).toBe(true); // over again: stays
    d = applyAttempt(d, ok(P2.startMs + H, 5, 6, 15, P2));
    expect(d).toMatchObject({ tripped: false, reason: null, tripped_at: null, tripped_budget_usd: null });
  });

  it("clears spend after a raise, only if that evaluation is under; an over evaluation consumes the raise", () => {
    const d = applyAttempt(freshGuardDoc(T0), ok(T0, ...OVER));
    expect(applyAttempt(d, ok(T0 + H, 5.2, 19, 20)).tripped).toBe(false);
    const stillOver = applyAttempt(d, ok(T0 + H, 5.2, 21, 20));
    expect(stillOver).toMatchObject({ tripped: true, reason: "spend", tripped_budget_usd: 20 });
    expect(applyAttempt(stillOver, ok(T0 + 2 * H, 5.2, 6, 20)).tripped).toBe(true); // needs a further raise
  });

  it("a failed reading never clears or sets the latch; it records the attempt", () => {
    const tripped = applyAttempt(freshGuardDoc(T0), ok(T0, ...OVER));
    const d = applyAttempt(tripped, fail(T0 + H));
    expect(d).toMatchObject({ tripped: true, reason: "spend", last_error: "boom", evaluated_at: new Date(T0 + H).toISOString(),
                              last_success: new Date(T0).toISOString() });
    expect(applyAttempt(freshGuardDoc(T0), fail(T0)).tripped).toBe(false);
  });

  it("trips blind after blind_after without a success, and only the first success under clears it", () => {
    const six = 6 * H;
    let d = freshGuardDoc(T0);
    d = applyBlindRule(applyAttempt(d, fail(T0 + six - 1)), T0 + six - 1, six);
    expect(d.tripped).toBe(false);
    d = applyBlindRule(d, T0 + six, six);
    expect(d).toMatchObject({ tripped: true, reason: "blind" });
    expect(applyAttempt(d, ok(T0 + six + 1, ...UNDER)).tripped).toBe(false);
    expect(applyAttempt(d, ok(T0 + six + 1, ...OVER))).toMatchObject({ tripped: true, reason: "spend" });
  });

  it("measures blindness from the last success, and never turns spend into blind", () => {
    const six = 6 * H;
    const d = applyAttempt(freshGuardDoc(T0), ok(T0 + H, ...UNDER));
    expect(applyBlindRule(d, T0 + H + six - 1, six).tripped).toBe(false);
    expect(applyBlindRule(d, T0 + H + six, six).reason).toBe("blind");
    const spend = applyAttempt(freshGuardDoc(T0), ok(T0, ...OVER));
    expect(applyBlindRule(spend, T0 + 10 * six, six).reason).toBe("spend");
  });
});

describe("parseGuardDoc and corruptGuardDoc", () => {
  it("round-trips what this code writes and rejects anything else", () => {
    const d = applyAttempt(freshGuardDoc(T0), ok(T0, ...OVER));
    expect(parseGuardDoc(JSON.parse(JSON.stringify(d)))).toEqual(d);
    for (const bad of [null, 7, {}, { ...d, schema: 2 }, { ...d, tripped: "yes" }, { ...d, reason: "bored" },
                       { ...d, tripped: false }, { ...d, since: "never" }, { ...d, waf: null }]) {
      expect(parseGuardDoc(bad)).toBeNull();
    }
  });

  it("a corrupt document becomes a spend trip that only a raise or a new period clears", () => {
    const d: GuardDoc = corruptGuardDoc(T0, P1, 15);
    expect(d).toMatchObject({ tripped: true, reason: "spend", tripped_budget_usd: 15 });
    expect(applyAttempt(d, ok(T0 + H, ...UNDER)).tripped).toBe(true);
    expect(applyAttempt(d, ok(T0 + H, 5.2, 6, 16)).tripped).toBe(false);
  });
});

describe("shouldEvaluate", () => {
  const at = (ms: number) => ({ ...freshGuardDoc(T0), evaluated_at: new Date(ms).toISOString() });
  it("evaluates when never evaluated, >= 15 min old, after a clock step back, or after a newer raise", () => {
    const m15 = 15 * 60_000;
    expect(shouldEvaluate(freshGuardDoc(T0), T0, m15, null)).toBe(true);
    expect(shouldEvaluate(at(T0), T0 + m15 - 1, m15, null)).toBe(false);
    expect(shouldEvaluate(at(T0), T0 + m15, m15, null)).toBe(true);
    expect(shouldEvaluate(at(T0), T0 - 1, m15, null)).toBe(true);
    expect(shouldEvaluate(at(T0), T0 + 60_000, m15, T0 + 30_000)).toBe(true);
    expect(shouldEvaluate(at(T0), T0 + 60_000, m15, T0 - 30_000)).toBe(false);
  });
});

describe("effectiveBudget", () => {
  const raise = (budget_usd: unknown, expires: string, written_at = "2026-10-20T00:00:00.000Z") =>
    ({ budget_usd, expires, written_at });
  it("honours an unexpired raise above the base, capped at the maximum", () => {
    expect(effectiveBudget(15, raise(25, "2026-11-11T00:00:00Z"), T0, P1.endMs)).toEqual(
      { budgetUsd: 25, raisedUntil: "2026-11-11T00:00:00.000Z", writtenAtMs: T0, invalid: null });
    expect(effectiveBudget(15, raise(5000, "2026-11-11T00:00:00Z"), T0, P1.endMs).budgetUsd).toBe(MAX_BUDGET_USD);
  });
  it("ignores an expired, lowering, malformed or absent raise", () => {
    expect(effectiveBudget(15, raise(25, "2026-10-19T00:00:00Z"), T0, P1.endMs).budgetUsd).toBe(15);
    expect(effectiveBudget(15, raise(10, "2026-11-11T00:00:00Z"), T0, P1.endMs).budgetUsd).toBe(15);
    expect(effectiveBudget(15, raise("25", "2026-11-11T00:00:00Z"), T0, P1.endMs).budgetUsd).toBe(15);
    expect(effectiveBudget(15, raise(25, "soon"), T0, P1.endMs).budgetUsd).toBe(15);
    expect(effectiveBudget(15, null, T0, P1.endMs)).toEqual({ budgetUsd: 15, raisedUntil: null, writtenAtMs: null,
                                                              invalid: null });
  });
  it("ignores and reports a raise that outlives the billing period", () => {
    const r = effectiveBudget(15, raise(25, "2026-12-11T00:00:00Z"), T0, P1.endMs);
    expect(r).toMatchObject({ budgetUsd: 15, raisedUntil: null });
    expect(r.invalid).toMatch(/after this billing period ends/);
  });
  it("clamps a written_at ahead of the Worker's clock to now", () => {
    expect(effectiveBudget(15, raise(25, "2026-11-11T00:00:00Z", "2026-10-20T00:05:00.000Z"), T0, P1.endMs).writtenAtMs)
      .toBe(T0);
  });
  it("validates the configured base", () => {
    expect([15, 5.01, 100].map(validBaseBudget)).toEqual([true, true, true]);
    expect([5, 4, 100.01, Number.NaN].map(validBaseBudget)).toEqual([false, false, false, false]);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd antenna && npx vitest run test/latch.test.ts`
Expected: FAIL. `../src/latch` cannot be resolved.

- [ ] **Step 3: Implement**

`antenna/src/latch.ts`:

```ts
/** state/guard.json and the `tripped` latch (spec "Cost guard"). Pure: no IO.
 *
 * Set: a successful evaluation over a threshold (reason "spend"; a successful
 * reading over a threshold always leaves or sets reason "spend"), or no
 * successful reading for blind_after (reason "blind").
 * Cleared, only: "blind" by the first successful reading under the thresholds;
 * "spend" by a successful reading under the thresholds in a new billing period
 * or with a budget raised above the one it last tripped at. Nothing else. */

import type { Period } from "./period";
import { type Evaluation, overThreshold, PRICES, type Usage } from "./pricing";

export const GUARD_KEY = "state/guard.json";
export const BUDGET_KEY = "state/budget.json";
export const OFFAIR_KEY = "state/offair.json";
/** No raise (state/budget.json) or configured budget is honoured above this. */
export const MAX_BUDGET_USD = 100;

export type TripReason = "spend" | "blind";

export interface StoredEvaluation {
  at: string;
  actual_usd: number;
  projected_usd: number;
  budget_usd: number;
  base_budget_usd: number;
  period_to_date: Usage;
  projected: Usage;
  unknown_action_types: string[];
}

export interface GuardDoc {
  schema: 1;
  tripped: boolean;
  reason: TripReason | null;
  tripped_at: string | null;
  /** For "spend": the period and effective budget of the last over-threshold evaluation. */
  tripped_period_start: string | null;
  tripped_budget_usd: number | null;
  /** When this document was first written: the blind clock's baseline. */
  since: string;
  last_success: string | null;
  /** The last evaluation attempt, successful or not (drives the 15-minute cadence). */
  evaluated_at: string | null;
  last_error: string | null;
  period: { start: string; end: string } | null;
  evaluation: StoredEvaluation | null;
  /** The kill switch as last observed by reconciliation. */
  waf: { enabled: boolean | null; error: string | null };
}

const iso = (ms: number) => new Date(ms).toISOString();

export function freshGuardDoc(nowMs: number): GuardDoc {
  return {
    schema: 1, tripped: false, reason: null, tripped_at: null, tripped_period_start: null, tripped_budget_usd: null,
    since: iso(nowMs), last_success: null, evaluated_at: null, last_error: null, period: null, evaluation: null,
    waf: { enabled: null, error: null },
  };
}

const isStr = (v: unknown) => typeof v === "string";
const isStrOrNull = (v: unknown) => v === null || typeof v === "string";
const isNumOrNull = (v: unknown) => v === null || (typeof v === "number" && Number.isFinite(v));

/** The document, or null when its shape is not one this code wrote. */
export function parseGuardDoc(raw: unknown): GuardDoc | null {
  const d = raw as Partial<GuardDoc> | null;
  if (!d || typeof d !== "object" || d.schema !== 1) return null;
  if (typeof d.tripped !== "boolean") return null;
  if (!(d.reason === null || d.reason === "spend" || d.reason === "blind")) return null;
  if (d.tripped !== (d.reason !== null)) return null;
  if (!isStr(d.since) || Number.isNaN(Date.parse(d.since!))) return null;
  for (const k of ["tripped_at", "tripped_period_start", "last_success", "evaluated_at", "last_error"] as const) {
    if (!isStrOrNull(d[k])) return null;
  }
  if (!isNumOrNull(d.tripped_budget_usd)) return null;
  if (!d.waf || typeof d.waf !== "object") return null;
  return d as GuardDoc;
}

/** What an unreadable state/guard.json becomes: tripped for spend, so only a
 * raise or a new period (with an evaluation under the thresholds) clears it. */
export function corruptGuardDoc(nowMs: number, period: Period | null, budgetUsd: number): GuardDoc {
  return {
    ...freshGuardDoc(nowMs),
    tripped: true, reason: "spend", tripped_at: iso(nowMs),
    tripped_period_start: period ? iso(period.startMs) : null, tripped_budget_usd: budgetUsd,
  };
}

export type Attempt =
  | { ok: true; evaluation: Evaluation; period: Period; baseBudgetUsd: number }
  | { ok: false; atMs: number; error: string };

function stored(e: Evaluation, baseBudgetUsd: number): StoredEvaluation {
  const r4 = (x: number) => Math.round(x * 10_000) / 10_000;
  const usage = (u: Usage): Usage => ({ workersRequests: Math.round(u.workersRequests), r2ClassA: Math.round(u.r2ClassA),
                                        r2ClassB: Math.round(u.r2ClassB), r2StorageGbMonth: r4(u.r2StorageGbMonth) });
  return { at: iso(e.atMs), actual_usd: r4(e.actualUsd), projected_usd: r4(e.projectedUsd), budget_usd: e.budgetUsd,
           base_budget_usd: baseBudgetUsd, period_to_date: usage(e.periodToDate), projected: usage(e.projected),
           unknown_action_types: e.unknownActionTypes };
}

export function applyAttempt(prev: GuardDoc, a: Attempt): GuardDoc {
  if (!a.ok) return { ...prev, evaluated_at: iso(a.atMs), last_error: a.error };
  const e = a.evaluation;
  const at = iso(e.atMs);
  const periodStart = iso(a.period.startMs);
  const base: GuardDoc = { ...prev, last_success: at, evaluated_at: at, last_error: null,
                           period: { start: periodStart, end: iso(a.period.endMs) }, evaluation: stored(e, a.baseBudgetUsd) };
  if (overThreshold(e)) {
    return { ...base, tripped: true, reason: "spend",
             tripped_at: prev.tripped && prev.reason === "spend" ? prev.tripped_at : at,
             tripped_period_start: periodStart, tripped_budget_usd: e.budgetUsd };
  }
  const cleared: GuardDoc = { ...base, tripped: false, reason: null, tripped_at: null, tripped_period_start: null,
                              tripped_budget_usd: null };
  if (!prev.tripped || prev.reason === "blind") return cleared;
  const newPeriod = prev.tripped_period_start !== periodStart;
  const raised = prev.tripped_budget_usd !== null && e.budgetUsd > prev.tripped_budget_usd;
  return newPeriod || raised ? cleared : { ...base, tripped: true, reason: "spend", tripped_at: prev.tripped_at,
                                           tripped_period_start: prev.tripped_period_start,
                                           tripped_budget_usd: prev.tripped_budget_usd };
}

/** Trip "blind" when no reading has succeeded for blindAfterMs (since the
 * document was first written, if none ever has). Never downgrades "spend". */
export function applyBlindRule(doc: GuardDoc, nowMs: number, blindAfterMs: number): GuardDoc {
  if (doc.tripped) return doc;
  const baseline = Date.parse(doc.last_success ?? doc.since);
  if (Number.isFinite(baseline) && nowMs - baseline < blindAfterMs) return doc;
  return { ...doc, tripped: true, reason: "blind", tripped_at: iso(nowMs), tripped_period_start: null,
           tripped_budget_usd: null };
}

/** Evaluate when the last attempt is intervalMs old (a negative age -- a clock
 * step back -- counts as old), or when a budget raise was written after it. */
export function shouldEvaluate(doc: GuardDoc, nowMs: number, intervalMs: number, budgetWrittenAtMs: number | null): boolean {
  if (doc.evaluated_at === null) return true;
  const last = Date.parse(doc.evaluated_at);
  const age = nowMs - last;
  if (!Number.isFinite(age) || age < 0 || age >= intervalMs) return true;
  return budgetWrittenAtMs !== null && budgetWrittenAtMs > last;
}

export interface EffectiveBudget {
  budgetUsd: number;
  raisedUntil: string | null;
  writtenAtMs: number | null;
  /** Why a raise in state/budget.json is ignored as invalid (the guard alerts), or null. */
  invalid: string | null;
}

/** The configured budget, or a raise from state/budget.json ({budget_usd,
 * expires, written_at}, written by `transmitter budget --raise-to`) while it is
 * unexpired. A raise only ever raises, and never past MAX_BUDGET_USD. A raise
 * lasts until the end of the period it was made in (R3), so one expiring after
 * the current period ends (`periodEndMs`; null when the period is unknown) is
 * ignored and reported. A written_at ahead of the Worker's clock (a skewed
 * writer) is clamped to now. */
export function effectiveBudget(baseUsd: number, raw: unknown, nowMs: number,
                                periodEndMs: number | null): EffectiveBudget {
  const none = { budgetUsd: baseUsd, raisedUntil: null, writtenAtMs: null, invalid: null };
  const d = raw as { budget_usd?: unknown; expires?: unknown; written_at?: unknown } | null;
  if (!d || typeof d !== "object") return none;
  const usd = d.budget_usd;
  const expires = typeof d.expires === "string" ? Date.parse(d.expires) : Number.NaN;
  const written = typeof d.written_at === "string" ? Date.parse(d.written_at) : Number.NaN;
  const writtenAtMs = Number.isFinite(written) ? Math.min(written, nowMs) : null;
  if (typeof usd !== "number" || !Number.isFinite(usd) || !(expires > nowMs) || usd <= baseUsd) {
    return { ...none, writtenAtMs };
  }
  if (periodEndMs !== null && expires > periodEndMs) {
    return { ...none, writtenAtMs, invalid: `state/budget.json raises the budget to $${usd} until ${iso(expires)}, ` +
                                            `after this billing period ends (${iso(periodEndMs)}); it is ignored` };
  }
  return { budgetUsd: Math.min(usd, MAX_BUDGET_USD), raisedUntil: iso(expires), writtenAtMs, invalid: null };
}

/** MONTHLY_BUDGET_USD: above the $5 base (else nothing is left to spend) and at most MAX_BUDGET_USD. */
export function validBaseBudget(v: number): boolean {
  return Number.isFinite(v) && v > PRICES.baseUsd && v <= MAX_BUDGET_USD;
}
```

- [ ] **Step 4: Run the tests and the type check**

Run: `cd antenna && npx vitest run test/latch.test.ts && npx tsc --noEmit`
Expected: PASS; no type errors.

- [ ] **Step 5: Commit**

```bash
git add antenna/src/latch.ts antenna/test/latch.test.ts
git commit -m "feat(antenna): the tripped latch (spend/blind), state/guard.json schema, budget raises"
```

---

### Task 5: Kill switch reconciliation (Rulesets API)

**Model hint:** opus (blocking path)

**Files:**
- Create: `antenna/src/waf.ts`, `antenna/test/waf.test.ts`

**Interfaces:**
- Consumes: `fakeFetch`, `json`, `FetchCall` (Task 1).
- Produces: `API = "https://api.cloudflare.com/client/v4"`, `PHASE = "http_request_firewall_custom"`, `interface WafConfig { zoneId; token; description }`, `class WafError extends Error`, and `reconcileKillSwitch(fetchFn, cfg, blocked): Promise<{ enabled: boolean; changed: boolean }>`.

`reconcileKillSwitch` works in four steps:

1. **Find.** It GETs `/zones/{zone}/rulesets/phases/http_request_firewall_custom/entrypoint` and finds exactly one rule whose `description` equals `cfg.description`, with action `block`.
2. **Compare.** It reads `enabled` as `true` when the field is absent. If that already equals `blocked`, it returns `changed: false`.
3. **Update.** Otherwise it PATCHes `/zones/{zone}/rulesets/{ruleset}/rules/{rule}` with the rule's full definition and only `enabled` changed.
4. **Verify.** It checks the PATCH response.

It throws `WafError` in four cases: an API failure, zero or more than one matching rule, a non-`block` action, or an update that did not take.

Notes for the implementer:

- The PATCH resends `action`, `expression`, `description`, `ref`, and `action_parameters` if present. The API's update replaces the rule definition, so every field must be there.
- It never touches another rule: the allowlist rule lives in the same ruleset.
- Required token permission: Zone → WAF → Edit, scoped to the station zone (Task 17 verifies it live).
- Each API call times out after 5 s: the reconcile runs before the playlist write in every invocation (amendment A4).

- [ ] **Step 1: Write the failing test**

`antenna/test/waf.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { API, reconcileKillSwitch, WafError } from "../src/waf";
import { type FetchCall, fakeFetch, json } from "./support";

const CFG = { zoneId: "zone1", token: "waf-token", description: "station: kill switch" };
const ENTRY = `GET ${API}/zones/zone1/rulesets/phases/http_request_firewall_custom/entrypoint`;
const PATCH = `PATCH ${API}/zones/zone1/rulesets/rs1/rules/`;

function rules(killEnabled: boolean | undefined, extra: Record<string, unknown>[] = []): Record<string, unknown>[] {
  const kill: Record<string, unknown> = { id: "r2", ref: "r2", action: "block", description: "station: kill switch",
                                          expression: 'http.host eq "h" and not (http.request.uri.path in {"/"})' };
  if (killEnabled !== undefined) kill.enabled = killEnabled;
  return [{ id: "r1", action: "block", description: "station: allowlist", expression: "x", enabled: true }, kill, ...extra];
}
const ok = (result: unknown) => json({ success: true, errors: [], messages: [], result });

/** The Rulesets API: GET returns `state`; PATCH applies the body to it. */
function api(state: { rules: Record<string, unknown>[] }) {
  return fakeFetch({
    [ENTRY]: () => ok({ id: "rs1", rules: state.rules }),
    [PATCH]: (c: FetchCall) => {
      const id = c.url.split("/").pop()!;
      const body = JSON.parse(c.body!);
      state.rules = state.rules.map((r) => (r.id === id ? { id, ...body } : r));
      return ok({ id: "rs1", rules: state.rules });
    },
  });
}

describe("reconcileKillSwitch", () => {
  it("only reads when the rule already matches", async () => {
    const f = api({ rules: rules(false) });
    expect(await reconcileKillSwitch(f.fetch, CFG, false)).toEqual({ enabled: false, changed: false });
    expect(f.calls.map((c) => c.method)).toEqual(["GET"]);
    expect(f.calls[0].headers.authorization).toBe("Bearer waf-token");
  });

  it("enables it when blocked, resending the whole rule with only enabled changed", async () => {
    const state = { rules: rules(false) };
    const f = api(state);
    expect(await reconcileKillSwitch(f.fetch, CFG, true)).toEqual({ enabled: true, changed: true });
    expect(f.calls[1].url).toBe(`${API}/zones/zone1/rulesets/rs1/rules/r2`);
    expect(JSON.parse(f.calls[1].body!)).toEqual({ action: "block", description: "station: kill switch", enabled: true, ref: "r2",
      expression: 'http.host eq "h" and not (http.request.uri.path in {"/"})' });
    expect(state.rules[0]).toMatchObject({ id: "r1", enabled: true }); // the allowlist is untouched
  });

  it("treats a missing enabled field as enabled, and disables it when not blocked", async () => {
    const f = api({ rules: rules(undefined) });
    expect(await reconcileKillSwitch(f.fetch, CFG, false)).toEqual({ enabled: false, changed: true });
  });

  it("refuses when the rule is missing, ambiguous or not a block rule", async () => {
    await expect(reconcileKillSwitch(api({ rules: [] }).fetch, CFG, true)).rejects.toThrow(/found 0/);
    await expect(reconcileKillSwitch(api({ rules: rules(false, [{ id: "r3", action: "block",
      description: "station: kill switch", expression: "y" }]) }).fetch, CFG, true)).rejects.toThrow(/found 2/);
    const skip = rules(false).map((r) => (r.id === "r2" ? { ...r, action: "skip" } : r));
    const f = api({ rules: skip });
    await expect(reconcileKillSwitch(f.fetch, CFG, true)).rejects.toThrow(/not "block"/);
    expect(f.calls.map((c) => c.method)).toEqual(["GET"]);
  });

  it("raises a WafError on an API failure or an update that did not take", async () => {
    const denied = fakeFetch({ [ENTRY]: () => json({ success: false, errors: [{ code: 10000, message: "Authentication error" }] }, 403) });
    await expect(reconcileKillSwitch(denied.fetch, CFG, true)).rejects.toThrow(WafError);
    await expect(reconcileKillSwitch(denied.fetch, CFG, true)).rejects.toThrow(/403: 10000 Authentication error/);
    const ignored = fakeFetch({ [ENTRY]: () => ok({ id: "rs1", rules: rules(false) }),
                                [PATCH]: () => ok({ id: "rs1", rules: rules(false) }) });
    await expect(reconcileKillSwitch(ignored.fetch, CFG, true)).rejects.toThrow(/did not take/);
    const html = fakeFetch({ [ENTRY]: () => new Response("<html>", { status: 502 }) });
    await expect(reconcileKillSwitch(html.fetch, CFG, true)).rejects.toThrow(/not JSON/);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd antenna && npx vitest run test/waf.test.ts`
Expected: FAIL. `../src/waf` cannot be resolved.

- [ ] **Step 3: Implement**

`antenna/src/waf.ts`:

```ts
/** The kill switch: a pre-created WAF custom rule on the station zone, found
 * by its description (never a hard-coded rule ID) and toggled through the
 * Rulesets API with a zone-scoped WAF-edit token. Level-triggered: every run
 * reads the rule's actual state and corrects it (spec "Blocking"). */

export const API = "https://api.cloudflare.com/client/v4";
export const PHASE = "http_request_firewall_custom";
/** Short: the reconcile runs before the playlist write in every invocation. */
const TIMEOUT_MS = 5_000;

export interface WafConfig {
  zoneId: string;
  token: string;
  description: string; // the rule's description, e.g. "station: kill switch"
}

interface Rule {
  id: string;
  action: string;
  expression: string;
  description?: string;
  enabled?: boolean;
  ref?: string;
  action_parameters?: unknown;
}

interface Envelope<T> {
  success?: boolean;
  errors?: { code?: number; message?: string }[];
  result?: T;
}

export class WafError extends Error {}

async function call<T>(fetchFn: typeof fetch, cfg: WafConfig, method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetchFn(`${API}${path}`, {
    method,
    headers: { authorization: `Bearer ${cfg.token}`, "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  const text = await res.text();
  let env: Envelope<T>;
  try {
    env = JSON.parse(text) as Envelope<T>;
  } catch {
    throw new WafError(`${method} ${path}: HTTP ${res.status}, not JSON: ${text.slice(0, 200)}`);
  }
  if (!res.ok || env.success !== true || env.result === undefined) {
    const msg = (env.errors ?? []).map((e) => `${e.code ?? ""} ${e.message ?? ""}`.trim()).join("; ");
    throw new WafError(`${method} ${path}: HTTP ${res.status}${msg ? `: ${msg}` : ""}`);
  }
  return env.result;
}

function killSwitch(rules: Rule[], description: string): Rule {
  const matches = rules.filter((r) => r.description === description);
  if (matches.length !== 1) {
    throw new WafError(`expected exactly one custom rule described "${description}", found ${matches.length}`);
  }
  if (matches[0].action !== "block") {
    throw new WafError(`the rule described "${description}" has action "${matches[0].action}", not "block"; refusing to toggle it`);
  }
  return matches[0];
}

/** Make the kill switch's enabled state equal `blocked`. Returns its state
 * after the call; throws WafError (or a network error) when it cannot. */
export async function reconcileKillSwitch(fetchFn: typeof fetch, cfg: WafConfig, blocked: boolean):
    Promise<{ enabled: boolean; changed: boolean }> {
  const base = `/zones/${encodeURIComponent(cfg.zoneId)}/rulesets`;
  const ruleset = await call<{ id: string; rules?: Rule[] }>(fetchFn, cfg, "GET", `${base}/phases/${PHASE}/entrypoint`);
  const rule = killSwitch(ruleset.rules ?? [], cfg.description);
  const enabled = rule.enabled !== false; // the API may omit enabled when true
  if (enabled === blocked) return { enabled, changed: false };
  // Resend the whole rule definition with only `enabled` changed: the update
  // replaces the rule, so every field must be present.
  const update: Record<string, unknown> = { action: rule.action, expression: rule.expression,
                                            description: rule.description, enabled: blocked };
  if (rule.ref !== undefined) update.ref = rule.ref;
  if (rule.action_parameters !== undefined) update.action_parameters = rule.action_parameters;
  const after = await call<{ rules?: Rule[] }>(fetchFn, cfg, "PATCH",
    `${base}/${encodeURIComponent(ruleset.id)}/rules/${encodeURIComponent(rule.id)}`, update);
  const now = (after.rules ?? []).find((r) => r.id === rule.id);
  const nowEnabled = now ? now.enabled !== false : undefined;
  if (nowEnabled !== blocked) {
    throw new WafError(`the kill switch update did not take: enabled is ${String(nowEnabled)}, wanted ${blocked}`);
  }
  return { enabled: blocked, changed: true };
}
```

- [ ] **Step 4: Run the tests and the type check**

Run: `cd antenna && npx vitest run test/waf.test.ts && npx tsc --noEmit`
Expected: PASS; no type errors.

- [ ] **Step 5: Commit**

```bash
git add antenna/src/waf.ts antenna/test/waf.test.ts
git commit -m "feat(antenna): kill switch found by description and reconciled through the Rulesets API"
```

---

### Task 6: guardStep — guard first, try/finally, persistence

**Model hint:** opus (spend + blocking path)

**Files:**
- Create: `antenna/src/conditions.ts`, `antenna/src/guard.ts`, `antenna/test/guard.test.ts`

**Interfaces:**
- Consumes: Tasks 1–5 (`readJsonDoc`, `putJson`, `JsonRead`, `billingPeriod`, `evaluateSpend`, `ALERT_LEVELS`, `readUsage`, the latch functions and keys, `reconcileKillSwitch`).
- Produces:
  - `conditions.ts`: `type Priority = "urgent" | "high" | "default"`, `interface AlertCondition { key; priority; title; message; resolvable; once? }`, `READING_WARN_MS` (1 h), `guardConditions(doc, nowMs, blindAfterMs) -> AlertCondition[]`. Its keys are `budget-50:<period start date>:<budget>` and `budget-80:…` (both `once`: sent once per billing period and budget, R13), `tripped-spend`, `tripped-blind` and `guard-reading-failing`.
  - `guard.ts`:
    - `interface GuardEnv`, with vars `MONTHLY_BUDGET_USD`, `BILLING_ANNIVERSARY_DAY`, `GUARD_EVAL_SECONDS`, `BLIND_AFTER_SECONDS` and `KILL_SWITCH_DESCRIPTION`, and secrets `CF_ACCOUNT_ID`, `CF_ZONE_ID`, `CF_ANALYTICS_TOKEN` and `CF_WAF_TOKEN`.
    - `interface GuardConfig` (incl. `meterProblems`, `wafProblems`), `DEFAULT_BLIND_AFTER_S = 21600`, `guardConfigFromEnv(env)`.
    - `interface GuardDeps { bucket; now; fetch; config }`, `interface GuardOutcome { blocked: boolean | null; tripped; offair; doc; conditions }`, `guardStep(deps): Promise<GuardOutcome>`, `mergeLostRace(ours, theirs) -> GuardDoc | null`.
    - Further condition keys: `guard-unknown`, `offair-corrupt`, `guard-state-corrupt`, `waf-api`, `waf-corrected`, `budget-file-invalid` (`once`), `guard-write`.

The order inside `guardStep` is the spec's:
1. **Read state.** If the read fails, the outcome is unknown (`blocked: null`): no evaluation, no WAF call, no write. A raise in `budget.json` that expires after the current billing period ends is ignored and alerted (`budget-file-invalid`).
2. **Evaluate.** In a `try`, when `shouldEvaluate` says so. Any exception there, including a missing secret, counts as a failed reading.
3. **Finally.** In the `finally`:
   1. the blind rule;
   2. `blocked = tripped || offair`;
   3. the kill switch is reconciled to `blocked`; a change that undoes a hand toggle (the rule was the opposite of what the guard last set or saw, `prev.waf.enabled`) alerts `waf-corrected`;
   4. `guard.json` is persisted if it changed, with an etag-conditional PUT. On a lost race a trip is merged onto the winner's document (`mergeLostRace`), so a trip is never lost; only a blind trip yields, and only to a winner holding a newer successful reading, which would have cleared it.

- [ ] **Step 1: Write the failing test**

`antenna/test/guard.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { guardConfigFromEnv, type GuardEnv, guardStep, mergeLostRace } from "../src/guard";
import { BUDGET_KEY, freshGuardDoc, GUARD_KEY, OFFAIR_KEY } from "../src/latch";
import { GRAPHQL_URL } from "../src/meter";
import { API } from "../src/waf";
import { type FetchCall, fakeFetch, json, MemoryBucket, usageResponse } from "./support";

const T0 = Date.parse("2026-10-20T12:00:00Z");
const M = 60_000;
const ENV: GuardEnv = { MONTHLY_BUDGET_USD: "15", BILLING_ANNIVERSARY_DAY: "11", CF_ACCOUNT_ID: "acct",
                        CF_ZONE_ID: "zone1", CF_ANALYTICS_TOKEN: "an-tok", CF_WAF_TOKEN: "waf-tok" };
const ENTRY = `GET ${API}/zones/zone1/rulesets/phases/http_request_firewall_custom/entrypoint`;
const PATCH = `PATCH ${API}/zones/zone1/rulesets/rs1/rules/`;
/** 3M Class A to date and 30k/h recently: actual $14 (> 90% of 15). */
const OVER = usageResponse({ ops: { PutObject: 3_000_000 }, opsRecent: { PutObject: 90_000 } });
const UNDER = usageResponse();
/** 3M Class A to date and none recently: actual = projected = $14 (over at 15, under at 40). */
const FLAT14 = usageResponse({ ops: { PutObject: 3_000_000 }, opsRecent: {} });

function cloud(o: { usage?: object | (() => Response); killEnabled?: boolean } = {}) {
  const state = { enabled: o.killEnabled ?? false };
  const rule = () => ({ id: "r2", action: "block", description: "station: kill switch", expression: "x", enabled: state.enabled });
  const usage = o.usage ?? UNDER;
  const f = fakeFetch({
    [`POST ${GRAPHQL_URL}`]: () => (typeof usage === "function" ? (usage as () => Response)() : json(usage)),
    [ENTRY]: () => json({ success: true, result: { id: "rs1", rules: [rule()] } }),
    [PATCH]: (c: FetchCall) => {
      state.enabled = JSON.parse(c.body!).enabled;
      return json({ success: true, result: { id: "rs1", rules: [rule()] } });
    },
  });
  return { ...f, state, graphqlCalls: () => f.calls.filter((c) => c.url === GRAPHQL_URL).length };
}

function step(bucket: MemoryBucket, c: ReturnType<typeof cloud>, nowMs = T0, env: GuardEnv = ENV) {
  return guardStep({ bucket, now: () => nowMs, fetch: c.fetch, config: guardConfigFromEnv(env) });
}

describe("guardStep", () => {
  it("first run: evaluates, writes guard.json, leaves the kill switch off, not blocked", async () => {
    const bucket = new MemoryBucket();
    const c = cloud();
    const out = await step(bucket, c);
    expect(out).toMatchObject({ blocked: false, tripped: false, offair: false });
    expect(c.graphqlCalls()).toBe(1);
    const doc = bucket.json(GUARD_KEY);
    expect(doc).toMatchObject({ tripped: false, evaluated_at: new Date(T0).toISOString(), waf: { enabled: false, error: null },
                                period: { start: "2026-10-11T00:00:00.000Z", end: "2026-11-11T00:00:00.000Z" } });
    expect(doc.evaluation.budget_usd).toBe(15);
    expect(bucket.objects.get(GUARD_KEY)!.cacheControl).toBe("no-store");
  });

  it("an evaluation over a threshold trips spend and enables the kill switch in the same run", async () => {
    const bucket = new MemoryBucket();
    const c = cloud({ usage: OVER });
    const out = await step(bucket, c);
    expect(out).toMatchObject({ blocked: true, tripped: true });
    expect(c.state.enabled).toBe(true);
    expect(bucket.json(GUARD_KEY)).toMatchObject({ tripped: true, reason: "spend", waf: { enabled: true } });
    expect(out.conditions.map((x) => x.key))
      .toEqual(expect.arrayContaining(["budget-50:2026-10-11:15", "budget-80:2026-10-11:15", "tripped-spend"]));
  });

  it("does not re-evaluate within 15 minutes but reconciles the kill switch every run", async () => {
    const bucket = new MemoryBucket();
    const c = cloud();
    await step(bucket, c);
    c.state.enabled = true; // someone turned it on by hand
    const out = await step(bucket, c, T0 + 14 * M);
    expect(c.graphqlCalls()).toBe(1);
    expect(out.blocked).toBe(false);
    expect(c.state.enabled).toBe(false);
    await step(bucket, c, T0 + 15 * M);
    expect(c.graphqlCalls()).toBe(2);
  });

  it("alerts waf-corrected when it undoes a hand toggle, not when it carries out its own decision", async () => {
    const bucket = new MemoryBucket();
    const c = cloud();
    await step(bucket, c);
    c.state.enabled = true; // turned on by hand in the dashboard
    const out = await step(bucket, c, T0 + M);
    expect(c.state.enabled).toBe(false);
    expect(out.conditions.find((x) => x.key === "waf-corrected")!.message).toMatch(/was on, set to off to match blocked=false/);
    bucket.seed(OFFAIR_KEY, { offair: true }); // the guard's own change: no alert
    const own = await step(bucket, c, T0 + 2 * M);
    expect(c.state.enabled).toBe(true);
    expect(own.conditions.map((x) => x.key)).not.toContain("waf-corrected");
  });

  it("offair blocks fully without touching the latch, and the guard never writes offair.json", async () => {
    const bucket = new MemoryBucket();
    bucket.seed(OFFAIR_KEY, { offair: true, reason: "objection", since: "2026-10-20T00:00:00Z", until: null });
    const c = cloud();
    const out = await step(bucket, c);
    expect(out).toMatchObject({ blocked: true, tripped: false, offair: true });
    expect(c.state.enabled).toBe(true);
    expect(bucket.puts(OFFAIR_KEY)).toBe(0);
    bucket.seed(OFFAIR_KEY, { offair: false, reason: "back", since: "2026-10-20T01:00:00Z", until: null });
    expect((await step(bucket, c, T0 + M)).blocked).toBe(false);
    expect(c.state.enabled).toBe(false);
  });

  it("an unreadable offair.json fails closed: blocked, with an alert", async () => {
    const bucket = new MemoryBucket();
    bucket.seed(OFFAIR_KEY, "{not json");
    const out = await step(bucket, cloud());
    expect(out).toMatchObject({ blocked: true, offair: true });
    expect(out.conditions.map((x) => x.key)).toContain("offair-corrupt");
  });

  it("when state cannot be read the outcome is unknown: no evaluation, no WAF change, no write", async () => {
    const bucket = new MemoryBucket();
    bucket.failGets.add(GUARD_KEY);
    const c = cloud({ killEnabled: true });
    const out = await step(bucket, c);
    expect(out.blocked).toBeNull();
    expect(out.conditions.map((x) => x.key)).toEqual(["guard-unknown"]);
    expect(c.calls).toHaveLength(0);
    expect(bucket.puts()).toBe(0);
  });

  it("a corrupt guard.json becomes a spend trip that an evaluation under the same budget does not clear", async () => {
    const bucket = new MemoryBucket();
    bucket.seed(GUARD_KEY, "garbage");
    const c = cloud();
    const out = await step(bucket, c);
    expect(out).toMatchObject({ blocked: true, tripped: true });
    expect(out.conditions.map((x) => x.key)).toContain("guard-state-corrupt");
    expect(bucket.json(GUARD_KEY).reason).toBe("spend");
  });

  it("a failing reading is recorded; after blind_after without success the station blocks (blind)", async () => {
    const bucket = new MemoryBucket();
    const failing = cloud({ usage: () => new Response("upstream", { status: 503 }) });
    let out = await step(bucket, failing);
    expect(out.blocked).toBe(false);
    expect(bucket.json(GUARD_KEY).last_error).toMatch(/HTTP 503/);
    out = await step(bucket, failing, T0 + 61 * M);
    expect(out.conditions.map((x) => x.key)).toContain("guard-reading-failing");
    out = await step(bucket, failing, T0 + 6 * 60 * M);
    expect(out).toMatchObject({ blocked: true, tripped: true });
    expect(bucket.json(GUARD_KEY).reason).toBe("blind");
    expect(failing.state.enabled).toBe(true);
    // The first successful reading under the thresholds clears blind.
    const healthy = cloud({ killEnabled: true });
    out = await step(bucket, healthy, T0 + 6 * 60 * M + 15 * M);
    expect(out).toMatchObject({ blocked: false, tripped: false });
    expect(healthy.state.enabled).toBe(false);
  });

  it("a thrown fetch (network error) is a failed reading, not a crash", async () => {
    const bucket = new MemoryBucket();
    const f = fakeFetch({ [ENTRY]: () => json({ success: true, result: { id: "rs1", rules: [
      { id: "r2", action: "block", description: "station: kill switch", expression: "x", enabled: false }] } }) });
    const out = await guardStep({ bucket, now: () => T0, fetch: f.fetch, config: guardConfigFromEnv(ENV) });
    expect(out.blocked).toBe(false);
    expect(bucket.json(GUARD_KEY).last_error).toMatch(/unexpected fetch: POST/);
  });

  it("missing secrets fail every evaluation and the WAF reconcile, loudly", async () => {
    const bucket = new MemoryBucket();
    const c = cloud();
    const out = await step(bucket, c, T0, { MONTHLY_BUDGET_USD: "15" });
    expect(c.calls).toHaveLength(0);
    expect(bucket.json(GUARD_KEY).last_error).toMatch(/CF_ACCOUNT_ID/);
    expect(out.conditions.map((x) => x.key)).toContain("waf-api");
    expect(bucket.json(GUARD_KEY).waf.error).toMatch(/CF_ZONE_ID/);
  });

  it("a WAF failure while blocked alerts and leaves the decision blocked (cooperative block)", async () => {
    const bucket = new MemoryBucket();
    bucket.seed(OFFAIR_KEY, { offair: true });
    const f = fakeFetch({ [`POST ${GRAPHQL_URL}`]: () => json(UNDER),
                          [ENTRY]: () => json({ success: false, errors: [{ code: 10000, message: "Authentication error" }] }, 403) });
    const out = await guardStep({ bucket, now: () => T0, fetch: f.fetch, config: guardConfigFromEnv(ENV) });
    expect(out.blocked).toBe(true);
    const waf = out.conditions.find((x) => x.key === "waf-api")!;
    expect(waf.message).toMatch(/cooperative-only/);
  });

  it("a raise newer than the last evaluation is evaluated at once and clears spend when under", async () => {
    const bucket = new MemoryBucket();
    await step(bucket, cloud({ usage: FLAT14 }));
    expect(bucket.json(GUARD_KEY).tripped).toBe(true);
    bucket.seed(BUDGET_KEY, { budget_usd: 40, expires: "2026-11-11T00:00:00.000Z", written_at: new Date(T0 + M).toISOString() });
    const c = cloud({ usage: FLAT14, killEnabled: true });
    const out = await step(bucket, c, T0 + 2 * M);
    expect(c.graphqlCalls()).toBe(1);
    expect(out).toMatchObject({ blocked: false, tripped: false });
    expect(bucket.json(GUARD_KEY).evaluation.budget_usd).toBe(40);
  });

  it("ignores and alerts a raise that outlives the billing period", async () => {
    const bucket = new MemoryBucket();
    bucket.seed(BUDGET_KEY, { budget_usd: 40, expires: "2026-12-11T00:00:00.000Z", written_at: new Date(T0 - M).toISOString() });
    const out = await step(bucket, cloud({ usage: FLAT14 }));
    expect(out).toMatchObject({ blocked: true, tripped: true });
    expect(bucket.json(GUARD_KEY).evaluation.budget_usd).toBe(15);
    expect(out.conditions.map((x) => x.key)).toContain("budget-file-invalid");
  });

  it("a bad BILLING_ANNIVERSARY_DAY fails every evaluation, loudly, without reading usage", async () => {
    const bucket = new MemoryBucket();
    const c = cloud();
    await step(bucket, c, T0, { ...ENV, BILLING_ANNIVERSARY_DAY: "32" });
    expect(c.graphqlCalls()).toBe(0);
    expect(bucket.json(GUARD_KEY).last_error).toMatch(/1\.\.31/);
  });

  it("never loses a trip to an overlapping invocation's write", async () => {
    const bucket = new MemoryBucket();
    bucket.seed(GUARD_KEY, { ...freshGuardDoc(T0 - 60 * M), evaluated_at: new Date(T0 - 20 * M).toISOString() });
    const c = cloud({ usage: OVER });
    // Another invocation rewrites guard.json (untripped) between our read and our write.
    const realPut = bucket.put.bind(bucket);
    let raced = false;
    bucket.put = async (key, value, options) => {
      if (key === GUARD_KEY && !raced) {
        raced = true;
        await realPut(key, JSON.stringify({ ...freshGuardDoc(T0 - 60 * M), evaluated_at: new Date(T0).toISOString() }),
                      { httpMetadata: { contentType: "application/json", cacheControl: "no-store" } });
      }
      return realPut(key, value, options);
    };
    const out = await step(bucket, c);
    expect(out.blocked).toBe(true);
    expect(bucket.json(GUARD_KEY)).toMatchObject({ tripped: true, reason: "spend" });
  });

  it("writes guard.json only when something changed", async () => {
    const bucket = new MemoryBucket();
    const c = cloud();
    await step(bucket, c);
    const before = bucket.puts(GUARD_KEY);
    await step(bucket, c, T0 + M);
    expect(bucket.puts(GUARD_KEY)).toBe(before);
  });
});

describe("mergeLostRace", () => {
  const iso = (ms: number) => new Date(ms).toISOString();
  const lastOk = T0 - 7 * 60 * M;
  const blind = { ...freshGuardDoc(lastOk), last_success: iso(lastOk), tripped: true, reason: "blind" as const,
                  tripped_at: iso(T0) };
  it("carries our trip onto theirs, and drops anything else", () => {
    const theirs = { ...freshGuardDoc(lastOk), last_success: iso(lastOk), evaluated_at: iso(T0) };
    expect(mergeLostRace(blind, theirs)).toMatchObject({ tripped: true, reason: "blind", evaluated_at: iso(T0) });
    expect(mergeLostRace(theirs, blind)).toBeNull();
  });
  it("drops a blind trip when theirs has a newer successful reading", () => {
    expect(mergeLostRace(blind, { ...freshGuardDoc(lastOk), last_success: iso(T0) })).toBeNull();
    const spend = { ...blind, reason: "spend" as const };
    expect(mergeLostRace(spend, { ...freshGuardDoc(lastOk), last_success: iso(T0) })).toMatchObject({ reason: "spend" });
  });
});

describe("guardConfigFromEnv", () => {
  it("bounds the cadence and blind window so a typo cannot weaken the guard", () => {
    expect(guardConfigFromEnv(ENV)).toMatchObject({ evalIntervalMs: 900_000, blindAfterMs: 21_600_000,
      killSwitchDescription: "station: kill switch", baseBudgetUsd: 15, anniversaryDay: 11, meterProblems: [], wafProblems: [] });
    const c = guardConfigFromEnv({ ...ENV, GUARD_EVAL_SECONDS: "86400", BLIND_AFTER_SECONDS: "1e9" });
    expect(c.evalIntervalMs).toBe(900_000);
    expect(c.blindAfterMs).toBe(21_600_000);
    expect(guardConfigFromEnv({ ...ENV, GUARD_EVAL_SECONDS: "1", BLIND_AFTER_SECONDS: "1" }))
      .toMatchObject({ evalIntervalMs: 60_000, blindAfterMs: 900_000 });
  });
  it("reports a bad budget as a problem, not a default", () => {
    expect(guardConfigFromEnv({ ...ENV, MONTHLY_BUDGET_USD: "5" }).meterProblems.join()).toMatch(/MONTHLY_BUDGET_USD/);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd antenna && npx vitest run test/guard.test.ts`
Expected: FAIL. `../src/guard` cannot be resolved.

- [ ] **Step 3: Implement**

`antenna/src/conditions.ts`:

```ts
/** Alert conditions: what is wrong right now, recomputed every invocation from
 * state, so a condition that stops being computed has cleared. Dispatch and
 * dedupe live in alerts.ts. */

import type { GuardDoc } from "./latch";
import { ALERT_LEVELS } from "./pricing";

export type Priority = "urgent" | "high" | "default";

export interface AlertCondition {
  key: string; // dedupe key, stable for the condition
  priority: Priority;
  title: string;
  message: string;
  /** Send a "resolved" notice when it clears (latches and outages). */
  resolvable: boolean;
  /** Send it when it first appears and never again -- no repeat, no "resolved",
   * not even if it clears and returns. The key carries what makes a new one
   * (the budget levels: the billing period and the budget). */
  once?: boolean;
}

const usd = (x: number) => `$${x.toFixed(2)}`;
/** A reading failing this long raises an early warning before the blind trip. */
export const READING_WARN_MS = 3_600_000;

/** Conditions that follow from the guard's own state. */
export function guardConditions(doc: GuardDoc, nowMs: number, blindAfterMs: number): AlertCondition[] {
  const out: AlertCondition[] = [];
  const e = doc.evaluation;
  if (e) {
    // Once per level per billing period (and budget: a raise starts the levels afresh).
    const period = (doc.period?.start ?? e.at).slice(0, 10);
    const peak = Math.max(e.actual_usd, e.projected_usd) / e.budget_usd;
    for (const level of ALERT_LEVELS) {
      if (peak >= level) {
        out.push({ key: `budget-${Math.round(level * 100)}:${period}:${e.budget_usd}`,
                   priority: level >= 0.8 ? "high" : "default", resolvable: false, once: true,
                   title: `Station spend at ${Math.round(level * 100)}% of budget`,
                   message: `Actual ${usd(e.actual_usd)}, projected ${usd(e.projected_usd)} of ${usd(e.budget_usd)} ` +
                            `this billing period (evaluated ${e.at}).` });
      }
    }
  }
  if (doc.tripped && doc.reason === "spend") {
    out.push({ key: "tripped-spend", priority: "urgent", resolvable: true, title: "Station blocked: spend",
               message: `The cost guard tripped at ${doc.tripped_at}: ` +
                        (e ? `actual ${usd(e.actual_usd)}, projected ${usd(e.projected_usd)} of ${usd(e.budget_usd)}. ` : "") +
                        "The station is off the air (ENDLIST, off-air page, kill switch). It clears only in a new " +
                        "billing period or after `transmitter budget --raise-to <usd>`, at an evaluation under the thresholds." });
  }
  if (doc.tripped && doc.reason === "blind") {
    out.push({ key: "tripped-blind", priority: "urgent", resolvable: true, title: "Station blocked: guard blind",
               message: `No usage reading has succeeded since ${doc.last_success ?? doc.since}; the guard fails closed. ` +
                        `Last error: ${doc.last_error ?? "none"}. It clears at the first successful reading under the thresholds.` });
  }
  const lastOk = Date.parse(doc.last_success ?? doc.since);
  if (!doc.tripped && doc.last_error !== null && nowMs - lastOk >= READING_WARN_MS) {
    const hoursLeft = Math.max(0, (lastOk + blindAfterMs - nowMs) / 3_600_000);
    out.push({ key: "guard-reading-failing", priority: "high", resolvable: true, title: "Cost guard cannot read usage",
               message: `Usage readings have failed since ${doc.last_success ?? doc.since}: ${doc.last_error}. ` +
                        `The station blocks itself (blind) in ${hoursLeft.toFixed(1)} h unless a reading succeeds.` });
  }
  return out;
}
```

`antenna/src/guard.ts`:

```ts
/** The cost guard step: first in every clock invocation (spec "Cost guard").
 *
 * 1. Read state/guard.json, state/offair.json and state/budget.json. If R2
 *    cannot be read the blocked state is unknown: the outcome is
 *    `blocked: null` and the clock writes nothing this invocation (players
 *    stall on a stale playlist -- toward zero cost -- and nothing is unblocked).
 * 2. try: evaluate (read usage, price it, apply the latch) when the last
 *    attempt is >= 15 min old or a raise is newer; any exception there is a
 *    failed reading.
 * 3. finally: the blind rule, then reconciliation of the kill switch to
 *    blocked = tripped OR offair, then persist guard.json if it changed.
 * The clock does the playlist and index.html work after this returns.
 */

import { type BucketLike, type JsonRead, putJson, readJsonDoc } from "./bucket";
import { type AlertCondition, guardConditions } from "./conditions";
import { applyAttempt, applyBlindRule, BUDGET_KEY, corruptGuardDoc, effectiveBudget, freshGuardDoc, GUARD_KEY,
         type GuardDoc, OFFAIR_KEY, parseGuardDoc, shouldEvaluate, validBaseBudget } from "./latch";
import { readUsage } from "./meter";
import { billingPeriod, type Period } from "./period";
import { evaluateSpend } from "./pricing";
import { reconcileKillSwitch } from "./waf";

export interface GuardEnv {
  MONTHLY_BUDGET_USD?: string;
  /** The day of the month the billing period starts, 00:00 UTC (R12). */
  BILLING_ANNIVERSARY_DAY?: string;
  GUARD_EVAL_SECONDS?: string;
  BLIND_AFTER_SECONDS?: string;
  KILL_SWITCH_DESCRIPTION?: string;
  // Worker secrets (account details never live in the repo):
  CF_ACCOUNT_ID?: string;
  CF_ZONE_ID?: string;
  CF_ANALYTICS_TOKEN?: string;
  CF_WAF_TOKEN?: string;
}

export interface GuardConfig {
  baseBudgetUsd: number;
  anniversaryDay: number;
  evalIntervalMs: number;
  blindAfterMs: number;
  killSwitchDescription: string;
  accountId: string;
  zoneId: string;
  analyticsToken: string;
  wafToken: string;
  /** Why an evaluation cannot run (each attempt fails with these). */
  meterProblems: string[];
  /** Why the kill switch cannot be reconciled. */
  wafProblems: string[];
}

export const DEFAULT_BLIND_AFTER_S = 21_600;
const clampedSeconds = (v: string | undefined, dflt: number, min: number, max: number) => {
  const x = v === undefined || v.trim() === "" ? Number.NaN : Number(v);
  return (Number.isFinite(x) ? Math.min(max, Math.max(min, x)) : dflt) * 1000;
};

/** Bounds keep a typo from weakening the guard: evaluation at least every
 * 15 min (900 s; lower only for verification, floor 60 s), blind after at most
 * 6 h (floor 15 min). A missing or invalid budget or secret is a problem that
 * fails every evaluation -- and so trips blind -- rather than a silent default;
 * so does an invalid BILLING_ANNIVERSARY_DAY, through billingPeriod's refusal. */
export function guardConfigFromEnv(env: GuardEnv): GuardConfig {
  const meterProblems: string[] = [];
  const wafProblems: string[] = [];
  const budget = Number(env.MONTHLY_BUDGET_USD);
  if (!validBaseBudget(budget)) meterProblems.push(`MONTHLY_BUDGET_USD must be a number above 5 and at most 100, not ${JSON.stringify(env.MONTHLY_BUDGET_USD)}`);
  const day = Number(env.BILLING_ANNIVERSARY_DAY);
  const need = (name: keyof GuardEnv, list: string[]) => {
    const v = env[name];
    if (typeof v !== "string" || v.trim() === "") list.push(`secret ${name} is not set`);
    return (v ?? "").trim();
  };
  const accountId = need("CF_ACCOUNT_ID", meterProblems);
  const analyticsToken = need("CF_ANALYTICS_TOKEN", meterProblems);
  const zoneId = need("CF_ZONE_ID", wafProblems);
  const wafToken = need("CF_WAF_TOKEN", wafProblems);
  return {
    baseBudgetUsd: budget, anniversaryDay: day,
    evalIntervalMs: clampedSeconds(env.GUARD_EVAL_SECONDS, 900, 60, 900),
    blindAfterMs: clampedSeconds(env.BLIND_AFTER_SECONDS, DEFAULT_BLIND_AFTER_S, 900, DEFAULT_BLIND_AFTER_S),
    killSwitchDescription: env.KILL_SWITCH_DESCRIPTION?.trim() || "station: kill switch",
    accountId, zoneId, analyticsToken, wafToken, meterProblems, wafProblems,
  };
}

export interface GuardDeps {
  bucket: BucketLike;
  now: () => number;
  fetch: typeof fetch;
  config: GuardConfig;
}

export interface GuardOutcome {
  /** tripped OR offair; null = unknown (state could not be read): write nothing. */
  blocked: boolean | null;
  tripped: boolean | null;
  offair: boolean | null;
  doc: GuardDoc | null;
  conditions: AlertCondition[];
}

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));

function periodOrNull(nowMs: number, cfg: GuardConfig): Period | null {
  try {
    return billingPeriod(nowMs, cfg.anniversaryDay);
  } catch {
    return null;
  }
}

/** After losing the etag race to `theirs`: the document to write so our trip
 * is not lost, or null when theirs stands (a clear or an evaluation that loses
 * the race is dropped: theirs is as recent). A blind trip carries over only if
 * theirs has no newer successful reading -- a newer success would clear it. */
export function mergeLostRace(ours: GuardDoc, theirs: GuardDoc): GuardDoc | null {
  if (!ours.tripped || theirs.tripped) return null;
  if (ours.reason === "blind" && theirs.last_success !== null &&
      (ours.last_success === null || Date.parse(theirs.last_success) > Date.parse(ours.last_success))) {
    return null;
  }
  return { ...theirs, tripped: true, reason: ours.reason, tripped_at: ours.tripped_at,
           tripped_period_start: ours.tripped_period_start, tripped_budget_usd: ours.tripped_budget_usd };
}

/** Persist with the etag read; if another invocation wrote meanwhile, never
 * let our trip be lost (mergeLostRace). */
async function persist(bucket: BucketLike, doc: GuardDoc, etag: string | undefined): Promise<void> {
  if (await putJson(bucket, GUARD_KEY, doc, etag)) return;
  const latest = await readJsonDoc(bucket, GUARD_KEY);
  if (latest.kind !== "ok") return;
  const theirs = parseGuardDoc(latest.value);
  const merged = theirs ? mergeLostRace(doc, theirs) : null;
  if (merged) await putJson(bucket, GUARD_KEY, merged, latest.etag);
}

export async function guardStep(deps: GuardDeps): Promise<GuardOutcome> {
  const { bucket, config: cfg } = deps;
  const nowMs = deps.now();
  const conditions: AlertCondition[] = [];
  let guardRead: JsonRead<unknown>;
  let offairRead: JsonRead<{ offair?: unknown }>;
  try {
    guardRead = await readJsonDoc(bucket, GUARD_KEY);
    offairRead = await readJsonDoc<{ offair?: unknown }>(bucket, OFFAIR_KEY);
  } catch (e) {
    conditions.push({ key: "guard-unknown", priority: "high", resolvable: true, title: "Cost guard cannot read its state",
                      message: `Reading state/ failed (${msg(e)}); the clock wrote nothing this minute and changed nothing.` });
    return { blocked: null, tripped: null, offair: null, doc: null, conditions };
  }
  let budgetRaw: unknown = null;
  try {
    const b = await readJsonDoc(bucket, BUDGET_KEY);
    budgetRaw = b.kind === "ok" ? b.value : null;
  } catch {
    budgetRaw = null; // unreadable raise: the configured budget (stricter) applies
  }

  // The operator's flag. Unreadable bytes fail closed: off the air.
  let offair = false;
  if (offairRead.kind === "ok" && typeof offairRead.value?.offair === "boolean") {
    offair = offairRead.value.offair;
  } else if (offairRead.kind !== "absent") {
    offair = true;
    conditions.push({ key: "offair-corrupt", priority: "high", resolvable: true, title: "state/offair.json unreadable",
                      message: "state/offair.json is not a valid flag; treating the station as off the air. " +
                               "Rewrite it with `transmitter offair on|off`." });
  }

  const budget = effectiveBudget(cfg.baseBudgetUsd, budgetRaw, nowMs, periodOrNull(nowMs, cfg)?.endMs ?? null);
  if (budget.invalid !== null) {
    conditions.push({ key: "budget-file-invalid", priority: "high", resolvable: false, once: true,
                      title: "Budget raise ignored",
                      message: `${budget.invalid}. A raise lasts until the end of the billing period it was made ` +
                               "in: write it with `transmitter budget --raise-to <usd>`." });
  }
  let prev: GuardDoc;
  const parsed = guardRead.kind === "ok" ? parseGuardDoc(guardRead.value) : null;
  if (guardRead.kind === "absent") prev = freshGuardDoc(nowMs);
  else if (parsed) prev = parsed;
  else {
    prev = corruptGuardDoc(nowMs, periodOrNull(nowMs, cfg), budget.budgetUsd);
    conditions.push({ key: "guard-state-corrupt", priority: "urgent", resolvable: true, title: "state/guard.json unreadable",
                      message: "state/guard.json could not be read as guard state; the guard treats the station as " +
                               "tripped for spend. Clear it with `transmitter budget --raise-to <usd>` or wait for the " +
                               "next billing period." });
  }

  const etag = guardRead.kind === "absent" ? undefined : guardRead.etag;
  let doc = prev;
  let blocked = true;
  try {
    if (shouldEvaluate(prev, nowMs, cfg.evalIntervalMs, budget.writtenAtMs)) {
      try {
        if (cfg.meterProblems.length > 0) throw new Error(cfg.meterProblems.join("; "));
        const period = billingPeriod(nowMs, cfg.anniversaryDay);
        const reading = await readUsage(deps.fetch, { accountId: cfg.accountId, token: cfg.analyticsToken }, period, nowMs);
        const evaluation = evaluateSpend(reading, period, nowMs, budget.budgetUsd);
        doc = applyAttempt(doc, { ok: true, evaluation, period, baseBudgetUsd: cfg.baseBudgetUsd });
      } catch (e) {
        doc = applyAttempt(doc, { ok: false, atMs: nowMs, error: msg(e) });
      }
    }
  } finally {
    doc = applyBlindRule(doc, nowMs, cfg.blindAfterMs);
    blocked = doc.tripped || offair;
    try {
      if (cfg.wafProblems.length > 0) throw new Error(cfg.wafProblems.join("; "));
      const r = await reconcileKillSwitch(deps.fetch, { zoneId: cfg.zoneId, token: cfg.wafToken,
                                                        description: cfg.killSwitchDescription }, blocked);
      if (r.changed && prev.waf.enabled === r.enabled) {
        // It was the opposite of what the guard last set or saw: a hand toggle, undone.
        conditions.push({ key: "waf-corrected", priority: "high", resolvable: false, title: "Kill switch toggled by hand",
                          message: `The kill switch was ${r.enabled ? "off" : "on"}, set to ${r.enabled ? "on" : "off"} ` +
                                   `to match blocked=${blocked}. The guard reconciles it every minute: use ` +
                                   "`transmitter offair on|off` instead of the dashboard." });
      }
      doc = { ...doc, waf: { enabled: r.enabled, error: null } };
    } catch (e) {
      doc = { ...doc, waf: { enabled: prev.waf.enabled, error: msg(e) } };
      conditions.push({ key: "waf-api", priority: "high", resolvable: true, title: "Kill switch not reconciled",
                        message: `The WAF kill switch could not be set to ${blocked ? "enabled" : "disabled"}: ${msg(e)}. ` +
                                 (blocked ? "The block is cooperative-only (ENDLIST + off-air page) until a later run succeeds."
                                          : "Retrying every minute.") });
    }
    if (guardRead.kind !== "ok" || JSON.stringify(doc) !== JSON.stringify(prev)) {
      try {
        await persist(bucket, doc, etag);
      } catch (e) {
        conditions.push({ key: "guard-write", priority: "high", resolvable: true, title: "Cost guard cannot save its state",
                          message: `Writing state/guard.json failed: ${msg(e)}.` });
      }
    }
  }
  conditions.push(...guardConditions(doc, nowMs, cfg.blindAfterMs));
  return { blocked, tripped: doc.tripped, offair, doc, conditions };
}
```

- [ ] **Step 4: Run the tests and the type check**

Run: `cd antenna && npx vitest run && npx tsc --noEmit`
Expected: PASS; no type errors.

- [ ] **Step 5: Commit**

```bash
git add antenna/src/conditions.ts antenna/src/guard.ts antenna/test/guard.test.ts
git commit -m "feat(antenna): guardStep -- evaluate, blind rule and kill-switch reconciliation in its finally"
```

---
### Task 7: Bundled pages and index.html reconciliation

**Model hint:** opus (blocking path)

**Files:**
- Create: `antenna/scripts/build-pages.mjs`, `antenna/src/pages.ts` (generated, committed), `antenna/src/indexpage.ts`, `antenna/test/indexpage.test.ts`
- Modify: `antenna/package.json` (scripts)

**Interfaces:**
- Consumes: `BucketLike`, `r2Bucket` (Task 1); `MemoryBucket` (Task 1).
- Produces:
  - `src/pages.ts`: `PLAYER_PAGE`, `OFFAIR_PAGE` (strings, generated from `public/index.html` and `public/offair.html`).
  - `src/indexpage.ts`: `INDEX_KEY = "index.html"`, `INDEX_HTTP` (`text/html; charset=utf-8`, `public, max-age=60`), `sha256Hex(text)`, `reconcileIndex(bucket, blocked): Promise<"written" | "unchanged">`.
  - npm scripts: `pages` (regenerate), and `test` = `node scripts/build-pages.mjs --check && vitest run`.

Notes for the implementer:

- **Why bundle the pages.** The clock owns `index.html` (ruling R8). It must be able to swap in the off-air page with no R2 read of a template, so both pages are bundled as strings.
- **Why a generator.** wrangler's Text-module import and vite's `?raw` do not agree on one import syntax, so a small generator plus a staleness check in `npm test` keeps one source of truth: `public/`.
- **Level-triggered.** The HEAD reads R2's own state each invocation, so a `deploy:assets` run or a hand upload is corrected within a minute.

- [ ] **Step 1: Write the failing test**

`antenna/test/indexpage.test.ts`:

```ts
import { env } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { r2Bucket } from "../src/bucket";
import { INDEX_KEY, reconcileIndex, sha256Hex } from "../src/indexpage";
import { OFFAIR_PAGE, PLAYER_PAGE } from "../src/pages";
import { MemoryBucket } from "./support";

describe("reconcileIndex", () => {
  it("writes the player page when not blocked and the off-air page when blocked, each once", async () => {
    const bucket = new MemoryBucket();
    expect(await reconcileIndex(bucket, false)).toBe("written");
    expect(bucket.objects.get(INDEX_KEY)!.body).toBe(PLAYER_PAGE);
    expect(await reconcileIndex(bucket, false)).toBe("unchanged");
    expect(await reconcileIndex(bucket, true)).toBe("written");
    expect(bucket.objects.get(INDEX_KEY)!.body).toBe(OFFAIR_PAGE);
    expect(bucket.objects.get(INDEX_KEY)!.customMetadata).toEqual({ sha256: await sha256Hex(OFFAIR_PAGE), page: "offair" });
    expect(await reconcileIndex(bucket, true)).toBe("unchanged");
    expect(bucket.puts(INDEX_KEY)).toBe(2);
  });

  it("corrects a hand-uploaded index.html (no metadata) at once", async () => {
    const bucket = new MemoryBucket();
    bucket.seed(INDEX_KEY, "<html>old</html>");
    expect(await reconcileIndex(bucket, false)).toBe("written");
  });

  it("the off-air page has no player scripts (the kill switch would block them)", () => {
    expect(OFFAIR_PAGE).toContain("The station is off the air.");
    expect(OFFAIR_PAGE).not.toContain("player.js");
    expect(PLAYER_PAGE).toContain("player.js");
  });

  it("writes through the R2 binding with its content type, max-age and metadata", async () => {
    await reconcileIndex(r2Bucket(env.BUCKET), true);
    const obj = await env.BUCKET.get(INDEX_KEY);
    expect(obj!.httpMetadata!.contentType).toBe("text/html; charset=utf-8");
    expect(obj!.httpMetadata!.cacheControl).toBe("public, max-age=60");
    expect(obj!.customMetadata!.page).toBe("offair");
    expect(await obj!.text()).toBe(OFFAIR_PAGE);
    expect(await reconcileIndex(r2Bucket(env.BUCKET), true)).toBe("unchanged");
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd antenna && npx vitest run test/indexpage.test.ts`
Expected: FAIL. `../src/indexpage` cannot be resolved.

- [ ] **Step 3: Implement**

`antenna/scripts/build-pages.mjs`:

```js
#!/usr/bin/env node
// The clock writes index.html itself (the player page, or the off-air page
// while the station is blocked), so both pages are bundled into the Worker as
// strings: this script generates src/pages.ts from public/index.html and
// public/offair.html. `--check` exits 1 if src/pages.ts is stale (npm test runs it).
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (f) => readFileSync(join(root, f), "utf8");
const out =
  "// GENERATED by scripts/build-pages.mjs from public/index.html and public/offair.html -- do not edit.\n" +
  `export const PLAYER_PAGE = ${JSON.stringify(read("public/index.html"))};\n` +
  `export const OFFAIR_PAGE = ${JSON.stringify(read("public/offair.html"))};\n`;
const target = join(root, "src", "pages.ts");
if (process.argv.includes("--check")) {
  let current = "";
  try {
    current = readFileSync(target, "utf8");
  } catch {
    // missing counts as stale
  }
  if (current !== out) {
    console.error("src/pages.ts is stale: run `npm run pages`");
    process.exit(1);
  }
} else {
  writeFileSync(target, out);
  console.log("wrote src/pages.ts");
}
```

`antenna/src/indexpage.ts`:

```ts
/** index.html is the clock's: the player page normally, the off-air page while
 * the station is blocked (spec "Blocking"). Level-triggered against R2 itself:
 * the object's customMetadata carries the SHA-256 of the body last written, so
 * a HEAD (Class B) per invocation decides, and a deploy that changed either
 * page, or a hand upload, is corrected within a minute. */

import type { BucketLike } from "./bucket";
import { OFFAIR_PAGE, PLAYER_PAGE } from "./pages";

export const INDEX_KEY = "index.html";
export const INDEX_HTTP = { contentType: "text/html; charset=utf-8", cacheControl: "public, max-age=60" };

export async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function reconcileIndex(bucket: BucketLike, blocked: boolean): Promise<"written" | "unchanged"> {
  const body = blocked ? OFFAIR_PAGE : PLAYER_PAGE;
  const sha256 = await sha256Hex(body);
  const info = await bucket.head(INDEX_KEY);
  if (info?.customMetadata?.sha256 === sha256) return "unchanged";
  await bucket.put(INDEX_KEY, body, { httpMetadata: INDEX_HTTP,
                                      customMetadata: { sha256, page: blocked ? "offair" : "player" } });
  return "written";
}
```

In `antenna/package.json`, set `"scripts"` to exactly:

```json
  "scripts": {
    "test": "node scripts/build-pages.mjs --check && vitest run",
    "typecheck": "tsc --noEmit",
    "types": "wrangler types",
    "pages": "node scripts/build-pages.mjs",
    "deploy": "wrangler deploy",
    "deploy:assets": "node scripts/deploy-assets.mjs"
  },
```

Then generate the bundle: `cd antenna && npm run pages` (writes `src/pages.ts`; never edit it by hand).

- [ ] **Step 4: Run the tests and the type check**

Run: `cd antenna && npm test && npx tsc --noEmit`
Expected: PASS; no type errors.

Then check that staleness is caught. Run:

```bash
cd antenna && echo "<!-- x -->" >> public/offair.html && npm test; git checkout public/offair.html
```

Expected: `npm test` exits 1 with `src/pages.ts is stale: run \`npm run pages\`` (and no vitest run).

- [ ] **Step 5: Commit**

```bash
git add antenna/scripts/build-pages.mjs antenna/src/pages.ts antenna/src/indexpage.ts antenna/test/indexpage.test.ts antenna/package.json
git commit -m "feat(antenna): index.html follows the blocked state from pages bundled into the Worker"
```

---

### Task 8: Clock integration and Worker wiring

**Model hint:** opus (spend + blocking path)

**Files:**
- Modify: `antenna/src/clock.ts` (replace the whole file), `antenna/src/index.ts` (replace), `antenna/wrangler.jsonc` (replace)
- Create: `antenna/src/env.ts`
- Modify: `antenna/test/clock.test.ts` (replace the whole file)

**Interfaces:**
- Consumes:
  - `GuardOutcome`, `guardStep`, `guardConfigFromEnv`, `GuardEnv` (Task 6);
  - `AlertCondition` (Task 6);
  - `reconcileIndex`, `INDEX_KEY` (Task 7);
  - `PLAYER_PAGE`, `OFFAIR_PAGE` (Task 7);
  - the bucket seam (Task 1).
- Produces:
  - `ClockConfig.leadFloorMs` (var `LEAD_FLOOR_HOURS`, default 16).
  - `ClockDeps.guard: () => Promise<GuardOutcome>` (**required**) and `ClockDeps.alerts?: (conditions, nowMs) => Promise<void>` (default `logAlerts`).
  - `ClockResult` gains `blocked: boolean | null`, `guardMs: number | null` (how long the guard took; logged on the clock line), `index: "written" | "unchanged" | "failed" | "skipped"` and `alerts: string[]` (the condition keys).
  - `readInputs(bucket, blocked)`; `offair.json` is no longer read here, because the guard reads it.
  - `logAlerts(conditions, nowMs)`.
  - `src/env.ts`: `interface AntennaEnv extends ClockEnv, GuardEnv { BUCKET: R2Bucket }`.
  - New clock condition keys: `guard-crashed`, `index-write`, `horizon-missing`, `horizon-refused`, `lead-low` and `offair-without-fallback`.

The phase-1 `guardStep` seam disappears: the real guard is passed in by `index.ts`. Behaviour summary:

- The guard runs first.
- An unknown outcome (null), or a guard that throws, writes nothing at all.
- `index.html` follows `blocked`.
- The playlist is the off-air playlist while blocked.
- The lead-floor condition is suppressed while tripped.
- Alerts are flushed once, after the invocation's last playlist write (or at an early return), never before the guard. A slow alert channel therefore never delays a boundary write.
- The guard's duration is recorded as `guardMs` and logged on the per-invocation clock line: amendment A4's trigger adds it to the cron lag.

All phase-1 spend bounds and their tests are kept. The existing tests are adapted: they now pass a guard stand-in.

- [ ] **Step 1: Write the failing tests**

Replace `antenna/test/clock.test.ts` with:

```ts
import { createExecutionContext, createScheduledController, env, waitOnExecutionContext } from "cloudflare:test";
import { afterEach, describe, expect, it, vi } from "vitest";
import { type ClockConfig, configFromEnv, MAX_PUTS, putCap, r2Bucket, runClock } from "../src/clock";
import type { AlertCondition } from "../src/conditions";
import type { AntennaEnv } from "../src/env";
import type { GuardOutcome } from "../src/guard";
import worker from "../src/index";
import { INDEX_KEY } from "../src/indexpage";
import { OFFAIR_PAGE, PLAYER_PAGE } from "../src/pages";
import { fakeTime, MemoryBucket } from "./support";

const E = Date.parse("2026-10-10T12:00:00.000Z");
const D = 10_240;
const CFG: ClockConfig = { window: 6, grace: 3, offairAfterMs: 86_400_000, loopMs: 75_000, liveMaxAge: 5,
                           leadFloorMs: 16 * 3_600_000 };

/** A guard stand-in with a fixed verdict (guard.ts has its own tests). */
const guardSays = (blocked: boolean | null, tripped = false, conditions: AlertCondition[] = []) =>
  async (): Promise<GuardOutcome> => ({ blocked, tripped: blocked === null ? null : tripped,
                                        offair: blocked === null ? null : blocked && !tripped, doc: null, conditions });
const onAir = guardSays(false);

function horizonDoc(epochMs: number, first = 0, last = 1_000_000) {
  const iso = new Date(epochMs).toISOString();
  return { epoch_id: "e1", epoch: iso, d: 10.24, first, last, published_at: iso, container: "adts", fallback_version: "v1" };
}
const FALLBACK = { len: 7, notice: "fallback/v1/notice.aac", d: 10.24 };

function station(bucket: MemoryBucket) {
  bucket.seed("state/horizon.json", horizonDoc(E));
  bucket.seed("fallback/v1/index.json", FALLBACK);
}

const playlistPuts = (b: MemoryBucket) => b.puts("live.m3u8");
const structured = (spy: { mock: { calls: unknown[][] } }, event: string) =>
  spy.mock.calls
    .map((c) => { try { return JSON.parse(String(c[0])); } catch { return null; } })
    .filter((o) => o?.event === event);

afterEach(() => {
  vi.restoreAllMocks();
});

describe("runClock", () => {
  it("writes immediately, then at every grid boundary until fire + 75 s", async () => {
    const bucket = new MemoryBucket();
    station(bucket);
    const scheduledTime = E + 50 * D + 300;
    const clock = fakeTime(scheduledTime + 40);
    const r = await runClock({ bucket, ...clock, scheduledTime, config: CFG, guard: onAir });
    expect(r.puts).toBe(8); // immediate + boundaries 51..57; 58 starts after fire + 75 s
    expect(playlistPuts(bucket)).toBe(8);
    expect(clock.now()).toBeLessThanOrEqual(scheduledTime + CFG.loopMs);
    expect(bucket.objects.get("live.m3u8")!.body).toContain("seg/e1/57.aac");
  });

  it("never exceeds ceil(75/d) + 2 PUTs, even with a skewed fire time", async () => {
    const bucket = new MemoryBucket();
    station(bucket);
    const clock = fakeTime(E + 100 * D);
    const r = await runClock({ bucket, ...clock, scheduledTime: E + 100 * D + 600_000, config: CFG, guard: onAir });
    expect(putCap(CFG, D)).toBe(10);
    expect(r.puts).toBe(10);
  });

  it("blocked: the off-air playlist, one PUT per invocation (identical bytes skipped)", async () => {
    const bucket = new MemoryBucket();
    station(bucket);
    const scheduledTime = E + 50 * D + 300;
    const r = await runClock({ bucket, ...fakeTime(scheduledTime + 40), scheduledTime, config: CFG, guard: guardSays(true) });
    expect(r.puts).toBe(1);
    expect(r.skipped).toBe(7);
    expect(bucket.objects.get("live.m3u8")!.body).toContain("#EXT-X-ENDLIST");
  });

  it("runs the guard before reading or writing anything", async () => {
    const bucket = new MemoryBucket();
    station(bucket);
    const seen: string[] = [];
    await runClock({ bucket, ...fakeTime(E + 10 * D), scheduledTime: E + 10 * D, config: { ...CFG, loopMs: 0 },
                     guard: async () => { seen.push("guard", ...bucket.log); return onAir(); } });
    expect(seen).toEqual(["guard"]);
    expect(bucket.log.slice(0, 2)).toEqual([`head ${INDEX_KEY}`, `put ${INDEX_KEY}`]);
  });

  it("records how long the guard took (guardMs, on the clock line)", async () => {
    const bucket = new MemoryBucket();
    station(bucket);
    const clock = fakeTime(E + 10 * D);
    const r = await runClock({ bucket, ...clock, scheduledTime: E + 10 * D, config: { ...CFG, loopMs: 0 },
                               guard: async () => { await clock.sleep(1_234); return onAir(); } });
    expect(r.guardMs).toBe(1_234);
  });

  it("writes nothing at all when the guard cannot tell whether the station is blocked", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    station(bucket);
    const r = await runClock({ bucket, ...fakeTime(E + 10 * D), scheduledTime: E + 10 * D, config: CFG, guard: guardSays(null) });
    expect(r).toMatchObject({ puts: 0, blocked: null, index: "skipped" });
    expect(bucket.puts()).toBe(0);
  });

  it("a guard that throws is treated as unknown: nothing written, an urgent alert", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    station(bucket);
    const sent: AlertCondition[] = [];
    const r = await runClock({ bucket, ...fakeTime(E + 10 * D), scheduledTime: E + 10 * D, config: CFG,
                               guard: async () => { throw new Error("kaboom"); },
                               alerts: async (cs) => { sent.push(...cs); } });
    expect(r.puts).toBe(0);
    expect(bucket.puts()).toBe(0);
    expect(sent.map((c) => c.key)).toEqual(["guard-crashed"]);
  });

  it("index.html follows the blocked state", async () => {
    const bucket = new MemoryBucket();
    station(bucket);
    const run = (guard: () => Promise<GuardOutcome>) =>
      runClock({ bucket, ...fakeTime(E + 10 * D), scheduledTime: E + 10 * D, config: { ...CFG, loopMs: 0 }, guard });
    expect((await run(onAir)).index).toBe("written");
    expect(bucket.objects.get(INDEX_KEY)!.body).toBe(PLAYER_PAGE);
    expect((await run(onAir)).index).toBe("unchanged");
    expect((await run(guardSays(true, true))).index).toBe("written");
    expect(bucket.objects.get(INDEX_KEY)!.body).toBe(OFFAIR_PAGE);
  });

  it("a failed index.html write still writes the playlist, and alerts", async () => {
    const bucket = new MemoryBucket();
    station(bucket);
    bucket.failPuts.add(INDEX_KEY);
    const sent: string[] = [];
    const r = await runClock({ bucket, ...fakeTime(E + 10 * D), scheduledTime: E + 10 * D, config: { ...CFG, loopMs: 0 },
                               guard: onAir, alerts: async (cs) => { sent.push(...cs.map((c) => c.key)); } });
    expect(r.index).toBe("failed");
    expect(r.puts).toBe(1);
    expect(sent).toEqual(["index-write"]);
  });

  it("writes no playlist without a horizon, and says so", async () => {
    const bucket = new MemoryBucket();
    const r = await runClock({ bucket, ...fakeTime(E), scheduledTime: E, config: CFG, guard: onAir });
    expect(r.puts).toBe(0);
    expect(playlistPuts(bucket)).toBe(0);
    expect(r.alerts).toEqual(["horizon-missing"]);
  });

  it("alerts when the published lead is below the floor, except while tripped (publishing stops then)", async () => {
    const bucket = new MemoryBucket();
    bucket.seed("state/horizon.json", horizonDoc(E, 0, 1000));
    bucket.seed("fallback/v1/index.json", FALLBACK);
    const now = E + 1001 * D - 3_600_000; // the lead is 1 h
    const r = await runClock({ bucket, ...fakeTime(now), scheduledTime: now, config: { ...CFG, loopMs: 0 }, guard: onAir });
    expect(r.alerts).toContain("lead-low");
    const t = await runClock({ bucket, ...fakeTime(now), scheduledTime: now, config: { ...CFG, loopMs: 0 },
                               guard: guardSays(true, true) });
    expect(t.alerts).not.toContain("lead-low");
  });

  it("passes the guard's conditions to the alert sink once, after the last playlist write", async () => {
    const bucket = new MemoryBucket();
    station(bucket);
    const order: string[] = [];
    const cond: AlertCondition = { key: "budget-50", priority: "default", resolvable: false, title: "t", message: "m" };
    const realPut = bucket.put.bind(bucket);
    bucket.put = async (k, v, o) => { order.push(`put ${k}`); return realPut(k, v, o); };
    await runClock({ bucket, ...fakeTime(E + 10 * D + 40), scheduledTime: E + 10 * D, config: CFG,
                     guard: guardSays(false, false, [cond]),
                     alerts: async (cs) => { order.push(`alerts ${cs.map((c) => c.key).join()}`); } });
    expect(order.filter((o) => o.startsWith("alerts"))).toEqual(["alerts budget-50"]);
    expect(order.filter((o) => o === "put live.m3u8").length).toBeGreaterThan(1);
    expect(order.at(-1)).toBe("alerts budget-50"); // after every boundary write
  });

  it("writes live.m3u8 through the R2 binding with its content type and max-age", async () => {
    await env.BUCKET.put("state/horizon.json", JSON.stringify(horizonDoc(E)));
    await env.BUCKET.put("fallback/v1/index.json", JSON.stringify(FALLBACK));
    await runClock({ bucket: r2Bucket(env.BUCKET), ...fakeTime(E + 10 * D + 40), scheduledTime: E + 10 * D,
                     config: { ...CFG, loopMs: 0 }, guard: onAir });
    const obj = await env.BUCKET.get("live.m3u8");
    expect(obj!.httpMetadata!.contentType).toBe("application/vnd.apple.mpegurl");
    expect(obj!.httpMetadata!.cacheControl).toBe("public, max-age=5");
    expect(await obj!.text()).toContain("seg/e1/10.aac");
  });
});

describe("off-air without a usable fallback", () => {
  const uriLines = (body: string) => body.split("\n").filter((l) => l !== "" && !l.startsWith("#"));

  it("writes the ENDLIST-only playlist once and reports it loudly, once per invocation", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    bucket.seed("state/horizon.json", horizonDoc(E));
    const scheduledTime = E + 50 * D + 300;
    const r = await runClock({ bucket, ...fakeTime(scheduledTime + 40), scheduledTime, config: CFG, guard: guardSays(true) });
    expect(r.puts).toBe(1);
    expect(playlistPuts(bucket)).toBe(1);
    expect(r.skipped).toBeGreaterThan(0);
    const body = bucket.objects.get("live.m3u8")!.body;
    expect(uriLines(body)).toEqual([]);
    expect(body.trimEnd().endsWith("#EXT-X-ENDLIST")).toBe(true);
    expect(r.offairWithoutFallback).toMatch(/blocked/);
    expect(r.offairWithoutFallback).toMatch(/ENDLIST-only/);
    expect(r.offairWithoutFallback).toMatch(/fallback\/v1\/index\.json/);
    const logged = structured(spy, "offair-without-fallback");
    expect(logged).toHaveLength(1);
    expect(logged[0].reason).toBe(r.offairWithoutFallback);
    expect(r.alerts).toContain("offair-without-fallback");
  });

  it("reports the staleness rule and a null fallback_version", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    bucket.seed("state/horizon.json", { ...horizonDoc(E, 0, 100), fallback_version: null });
    const now = E + 101 * D + CFG.offairAfterMs + 1;
    const r = await runClock({ bucket, ...fakeTime(now), scheduledTime: now, config: CFG, guard: onAir });
    expect(r.puts).toBe(1);
    expect(uriLines(bucket.objects.get("live.m3u8")!.body)).toEqual([]);
    expect(r.offairWithoutFallback).toMatch(/stale/);
    expect(r.offairWithoutFallback).toMatch(/fallback_version/);
    expect(structured(spy, "offair-without-fallback")).toHaveLength(1);
  });

  it("stays silent when off-air has a fallback, or the station is on air without one", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const offairOk = new MemoryBucket();
    station(offairOk);
    const r1 = await runClock({ bucket: offairOk, ...fakeTime(E + 10 * D), scheduledTime: E + 10 * D, config: CFG,
                                guard: guardSays(true) });
    expect(r1.puts).toBe(1);
    expect(r1.offairWithoutFallback).toBeNull();
    const onAirNoFallback = new MemoryBucket();
    onAirNoFallback.seed("state/horizon.json", horizonDoc(E));
    const r2 = await runClock({ bucket: onAirNoFallback, ...fakeTime(E + 10 * D), scheduledTime: E + 10 * D,
                                config: CFG, guard: onAir });
    expect(r2.puts).toBeGreaterThan(0);
    expect(r2.offairWithoutFallback).toBeNull();
    expect(structured(spy, "offair-without-fallback")).toHaveLength(0);
  });
});

describe("spend bounds hold regardless of inputs", () => {
  it("caps PUTs at 10 absolutely, whatever d and loopMs say", () => {
    expect(MAX_PUTS).toBe(10);
    for (const [loopMs, dMs] of [[75_000, 10], [900_000, 10_240], [75_000, 1], [10_000_000, 1_000]]) {
      expect(putCap({ ...CFG, loopMs }, dMs)).toBeLessThanOrEqual(10);
    }
  });

  it("refuses a horizon whose d is not 10.24: zero playlist PUTs, one structured error, an alert, returns promptly", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    for (const d of [0.01, 1, 10.25, "10.24"]) {
      spy.mockClear();
      const bucket = new MemoryBucket();
      station(bucket);
      bucket.seed("state/horizon.json", { ...horizonDoc(E), d });
      const start = E + 50 * D;
      const clock = fakeTime(start);
      const r = await runClock({ bucket, ...clock, scheduledTime: start, config: CFG, guard: onAir });
      expect(r.puts).toBe(0);
      expect(playlistPuts(bucket)).toBe(0);
      expect(clock.now()).toBe(start); // never slept
      expect(r.refused).toMatch(/d/);
      expect(r.alerts).toContain("horizon-refused");
      const logged = structured(spy, "horizon-refused");
      expect(logged).toHaveLength(1);
      expect(logged[0].d).toEqual(d);
    }
  });

  it("clamps LOOP_SECONDS=900 to 75 s: at most 10 PUTs, ends by scheduledTime + 75 s, logged once", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    station(bucket);
    const scheduledTime = E + 50 * D + 300;
    const clock = fakeTime(scheduledTime + 40);
    const r = await runClock({ bucket, ...clock, scheduledTime, config: configFromEnv({ LOOP_SECONDS: "900" }), guard: onAir });
    expect(r.puts).toBeLessThanOrEqual(10);
    expect(r.puts).toBe(8); // same as the 75 s default
    expect(clock.now()).toBeLessThanOrEqual(scheduledTime + 75_000);
    const logged = structured(spy, "loop-clamped");
    expect(logged).toHaveLength(1);
    expect(logged[0]).toMatchObject({ configuredMs: 900_000, usedMs: 75_000 });
  });

  it("never writes max-age=0: LIVE_MAX_AGE is at least 1", async () => {
    expect(configFromEnv({ LIVE_MAX_AGE: "0" }).liveMaxAge).toBe(1);
    const bucket = new MemoryBucket();
    station(bucket);
    await runClock({ bucket, ...fakeTime(E + 10 * D), scheduledTime: E + 10 * D,
                     config: { ...CFG, loopMs: 0, liveMaxAge: 0 }, guard: onAir });
    expect(bucket.objects.get("live.m3u8")!.cacheControl).toBe("public, max-age=1");
  });
});

describe("configFromEnv", () => {
  it("parses the vars with defaults", () => {
    expect(configFromEnv({})).toEqual({ window: 6, grace: 3, offairAfterMs: 86_400_000, loopMs: 75_000, liveMaxAge: 5,
                                        leadFloorMs: 16 * 3_600_000 });
    expect(configFromEnv({ LOOP_SECONDS: "0", PLAYLIST_WINDOW: "8" })).toMatchObject({ loopMs: 0, window: 8 });
    expect(configFromEnv({ GRACE_SEGMENTS: "nonsense" }).grace).toBe(3);
    expect(configFromEnv({ LEAD_FLOOR_HOURS: "6" }).leadFloorMs).toBe(6 * 3_600_000);
  });
});

describe("scheduled handler", () => {
  // env carries the wrangler vars but no secrets: the guard cannot read usage
  // or reach the WAF (no network in tests), records that, and is not blocked
  // (blind trips only after BLIND_AFTER_SECONDS).
  it("runs the guard then one clock invocation against the bound bucket", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    const now = Date.now();
    await env.BUCKET.put("state/horizon.json", JSON.stringify(horizonDoc(now - 100 * D)));
    await env.BUCKET.put("fallback/v1/index.json", JSON.stringify(FALLBACK));
    const ctrl = createScheduledController({ scheduledTime: now, cron: "* * * * *" });
    const ctx = createExecutionContext();
    await worker.scheduled!(ctrl, { ...env, LOOP_SECONDS: "0" } as unknown as AntennaEnv, ctx);
    await waitOnExecutionContext(ctx);
    const body = await (await env.BUCKET.get("live.m3u8"))!.text();
    expect(body).toContain("#EXTM3U");
    expect(body).toContain("seg/e1/");
    const guard = await (await env.BUCKET.get("state/guard.json"))!.json<{ tripped: boolean; last_error: string }>();
    expect(guard.tripped).toBe(false);
    expect(guard.last_error).toMatch(/CF_ACCOUNT_ID/);
    expect((await env.BUCKET.head("index.html"))!.customMetadata!.page).toBe("player");
    expect(structured(log, "clock")[0].guardMs).toEqual(expect.any(Number));
  });

  it("emits the per-invocation clock line even when runClock throws", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const spy = vi.spyOn(console, "log").mockImplementation(() => {});
    await env.BUCKET.put("state/horizon.json", JSON.stringify({ ...horizonDoc(Date.now()), epoch: "nonsense" }));
    const ctrl = createScheduledController({ scheduledTime: Date.now(), cron: "* * * * *" });
    const ctx = createExecutionContext();
    await expect(worker.scheduled!(ctrl, { ...env, LOOP_SECONDS: "0" } as unknown as AntennaEnv, ctx)).rejects.toThrow(/epoch/);
    await waitOnExecutionContext(ctx);
    const lines = structured(spy, "clock");
    expect(lines).toHaveLength(1);
    expect(lines[0].error).toMatch(/epoch/);
    expect(lines[0].lagMs).toEqual(expect.any(Number));
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd antenna && npx vitest run test/clock.test.ts`
Expected: FAIL. `../src/env` cannot be resolved, and `leadFloorMs`, `guard` and `alerts` are unknown to the current clock.

- [ ] **Step 3: Implement**

Replace `antenna/src/clock.ts` with:

```ts
import type { BucketLike } from "./bucket";
import type { AlertCondition } from "./conditions";
import { type Horizon, gridOf, indexAt, startMs } from "./grid";
import type { GuardOutcome } from "./guard";
import { reconcileIndex } from "./indexpage";
import { buildPlaylist, type FallbackIndex, isOffair, type PlaylistConfig, usableFallback } from "./playlist";

export { type BucketLike, r2Bucket, type StoredObject } from "./bucket";

export interface ClockConfig extends PlaylistConfig {
  loopMs: number;
  liveMaxAge: number;
  /** Alert when the published lead (end of horizon.last - now) is below this. */
  leadFloorMs: number;
}

export interface ClockEnv {
  PLAYLIST_WINDOW?: string;
  GRACE_SEGMENTS?: string;
  OFFAIR_AFTER_SECONDS?: string;
  LOOP_SECONDS?: string;
  LIVE_MAX_AGE?: string;
  LEAD_FLOOR_HOURS?: string;
}

function num(v: string | undefined, fallback: number): number {
  const x = v === undefined ? Number.NaN : Number(v);
  return Number.isFinite(x) && x >= 0 ? x : fallback;
}

export function configFromEnv(env: ClockEnv): ClockConfig {
  return {
    window: Math.max(1, Math.floor(num(env.PLAYLIST_WINDOW, 6))),
    grace: Math.floor(num(env.GRACE_SEGMENTS, 3)),
    offairAfterMs: num(env.OFFAIR_AFTER_SECONDS, 86_400) * 1000,
    loopMs: num(env.LOOP_SECONDS, 75) * 1000,
    liveMaxAge: Math.max(1, Math.floor(num(env.LIVE_MAX_AGE, 5))),
    leadFloorMs: num(env.LEAD_FLOOR_HOURS, 16) * 3_600_000,
  };
}

export interface ClockDeps {
  bucket: BucketLike;
  now: () => number;
  sleep: (ms: number) => Promise<void>;
  scheduledTime: number;
  config: ClockConfig;
  /** The cost guard step (guard.ts), run first; it decides blocked. */
  guard: () => Promise<GuardOutcome>;
  /** Where this invocation's alert conditions go (alerts.ts); default: logged. */
  alerts?: (conditions: AlertCondition[], nowMs: number) => Promise<void>;
}

export interface ClockResult {
  puts: number;
  skipped: number;
  /** Set when off-air was in force but no usable fallback/notice exists, so
   * the ENDLIST-only playlist (no notice) was written instead (also logged
   * once per invocation as a structured console.error). */
  offairWithoutFallback: string | null;
  /** Set when the horizon was refused (d is not the grid constant); nothing written. */
  refused: string | null;
  /** The guard's verdict: null = unknown, nothing written this invocation. */
  blocked: boolean | null;
  /** How long the guard step took. Logged on the clock line: amendment A4's
   * trigger adds it to the cron lag. */
  guardMs: number | null;
  index: "written" | "unchanged" | "failed" | "skipped";
  /** Keys of the alert conditions raised this invocation. */
  alerts: string[];
}

export const LIVE_KEY = "live.m3u8";

// Spend is the strict surface (Cloudflare has no spending cap), so the PUT
// bound is absolute and never derived from inputs alone: d comes from
// state/horizon.json and loopMs from a wrangler var, and either could
// otherwise turn the cap into thousands of Class-A writes per invocation.
/** The grid constant transmitter always writes: 441 * 1024 / 44100 s. */
export const GRID_D = 10.24;
/** The spec's run length: write until scheduledTime + 75 s, never longer. */
export const MAX_LOOP_MS = 75_000;
/** ceil(75 / 10.24) + 2: the per-invocation PUT ceiling, whatever the inputs. */
export const MAX_PUTS = 10;
const BOUNDARY_SLACK_MS = 25;

export interface ClockInputs {
  horizon: Horizon | null;
  fallback: FallbackIndex | null;
  /** Blocked (tripped OR offair), from the guard: the off-air playlist. */
  offair: boolean;
}

async function readJson<T>(bucket: BucketLike, key: string): Promise<T | null> {
  const obj = await bucket.get(key);
  if (obj === null) return null;
  try {
    return JSON.parse(await obj.text()) as T;
  } catch {
    return null;
  }
}

/** The horizon and its fallback, read once per invocation via the binding
 * (never through the cache). The blocked state comes from the guard. */
export async function readInputs(bucket: BucketLike, blocked: boolean): Promise<ClockInputs> {
  const horizon = await readJson<Horizon>(bucket, "state/horizon.json");
  const fallback = horizon?.fallback_version
    ? await readJson<FallbackIndex>(bucket, `fallback/${horizon.fallback_version}/index.json`)
    : null;
  return { horizon, fallback, offair: blocked };
}

/** Default alert sink until alerts.ts dispatches: one structured line each. */
export async function logAlerts(conditions: AlertCondition[], _nowMs: number): Promise<void> {
  for (const c of conditions) console.error(JSON.stringify({ event: "alert", key: c.key, title: c.title, message: c.message }));
}

export function putCap(cfg: ClockConfig, dMs: number): number {
  return Math.min(MAX_PUTS, Math.ceil(cfg.loopMs / dMs) + 2);
}

/** Why off-air is in force at nowMs and no usable fallback exists, or null. */
function offairWithoutFallback(inputs: ClockInputs, horizon: Horizon, nowMs: number, cfg: ClockConfig): string | null {
  const inp = { nowMs, horizon, fallback: inputs.fallback, offair: inputs.offair };
  if (!isOffair(inp, cfg) || usableFallback(inp) !== null) return null;
  const cause = inputs.offair
    ? "the station is blocked (tripped or state/offair.json)"
    : `horizon is stale (now is more than ${cfg.offairAfterMs / 1000} s past the end of segment ${horizon.last})`;
  const missing =
    horizon.fallback_version === null || horizon.fallback_version === ""
      ? "horizon.fallback_version is null"
      : inputs.fallback === null
        ? `fallback/${horizon.fallback_version}/index.json is missing or unreadable`
        : `fallback/${horizon.fallback_version}/index.json has len < 1`;
  return `off-air (${cause}) but no usable fallback (${missing}): live.m3u8 written as an ENDLIST-only playlist (no notice), so players stop`;
}

/**
 * One cron invocation. First the cost guard (guard.ts): it decides blocked =
 * tripped OR offair and reconciles the kill switch; when it cannot tell, the
 * invocation writes nothing at all. Then index.html follows the blocked state,
 * and the playlist is written immediately and at every grid boundary
 * E + N*d until scheduledTime + loopMs (the off-air playlist while blocked).
 * Alerts go out after the last playlist write, so a slow channel never delays
 * a boundary write. Only CPU time is billed, so the waiting is free.
 * Overlapping invocations are harmless: the playlist is a pure function of the
 * clock and the inputs.
 *
 * Epoch change: inputs are read once per invocation, so an epoch never changes
 * inside one. When state/horizon.json's epoch_id changes between invocations,
 * segment numbering restarts (N from 0 at the new epoch E) and
 * EXT-X-MEDIA-SEQUENCE drops. That is deliberate, not a defect: a new epoch is
 * an operator re-render event (transmitter re-renders and republishes under
 * seg/<new epoch_id>/), and players must reload the stream to follow it.
 */
export async function runClock(deps: ClockDeps): Promise<ClockResult> {
  const { bucket } = deps;
  const config: ClockConfig = {
    ...deps.config,
    loopMs: Math.min(deps.config.loopMs, MAX_LOOP_MS),
    liveMaxAge: Math.max(1, Math.floor(deps.config.liveMaxAge)),
  };
  if (config.loopMs !== deps.config.loopMs) {
    console.error(JSON.stringify({ event: "loop-clamped", configuredMs: deps.config.loopMs, usedMs: config.loopMs,
                                   scheduled: deps.scheduledTime }));
  }
  const result: ClockResult = { puts: 0, skipped: 0, offairWithoutFallback: null, refused: null, blocked: null,
                                guardMs: null, index: "skipped", alerts: [] };
  const conditions: AlertCondition[] = [];
  let flushed = false;
  const flush = async () => {
    if (flushed) return;
    flushed = true;
    result.alerts = conditions.map((c) => c.key);
    try {
      await (deps.alerts ?? logAlerts)(conditions, deps.now());
    } catch (e) {
      console.error(JSON.stringify({ event: "alert-dispatch-failed", error: e instanceof Error ? e.message : String(e) }));
    }
  };
  try {
    // 1. The guard, first: it decides blocked and reconciles the kill switch.
    const startedMs = deps.now();
    let outcome: GuardOutcome;
    try {
      outcome = await deps.guard();
    } catch (e) {
      outcome = { blocked: null, tripped: null, offair: null, doc: null, conditions: [{
        key: "guard-crashed", priority: "urgent", resolvable: true, title: "Cost guard crashed",
        message: `The guard step threw (${e instanceof Error ? e.message : String(e)}); the clock wrote nothing.` }] };
    }
    result.guardMs = deps.now() - startedMs;
    conditions.push(...outcome.conditions);
    result.blocked = outcome.blocked;
    if (outcome.blocked === null) {
      // Unknown: change nothing (players stall on a stale playlist, toward zero cost).
      console.error(JSON.stringify({ event: "guard-unknown", scheduled: deps.scheduledTime }));
      return result;
    }
    const blocked = outcome.blocked;
    // 2. index.html follows the blocked state.
    try {
      result.index = await reconcileIndex(bucket, blocked);
    } catch (e) {
      result.index = "failed";
      conditions.push({ key: "index-write", priority: "high", resolvable: true, title: "index.html not reconciled",
                        message: `Writing index.html (${blocked ? "off-air" : "player"} page) failed: ${e instanceof Error ? e.message : String(e)}` });
    }
    // 3. The playlist.
    const inputs = await readInputs(bucket, blocked);
    const horizon = inputs.horizon;
    if (horizon === null) {
      conditions.push({ key: "horizon-missing", priority: "default", resolvable: true, title: "No horizon published",
                        message: "state/horizon.json is absent: nothing is on air yet (transmitter has not published)." });
      return result;
    }
    if (horizon.d !== GRID_D) {
      result.refused = `state/horizon.json d is ${JSON.stringify(horizon.d)}, not the grid constant ${GRID_D}: live.m3u8 not written`;
      console.error(JSON.stringify({ event: "horizon-refused", reason: result.refused, d: horizon.d,
                                     epoch_id: horizon.epoch_id, scheduled: deps.scheduledTime }));
      conditions.push({ key: "horizon-refused", priority: "urgent", resolvable: true, title: "Horizon refused",
                        message: result.refused });
      return result;
    }
    const g = gridOf(horizon);
    const leadMs = startMs(g, horizon.last + 1) - deps.now();
    // While tripped, transmitter stops publishing by design: the lead drains then.
    if (!outcome.tripped && leadMs < config.leadFloorMs) {
      conditions.push({ key: "lead-low", priority: "high", resolvable: true, title: "Published lead below floor",
                        message: `The published lead is ${(leadMs / 3_600_000).toFixed(1)} h (floor ` +
                                 `${(config.leadFloorMs / 3_600_000).toFixed(1)} h): is transmitter on hugo publishing?` });
    }
    const cap = putCap(config, g.dMs);
    let lastBody: string | null = null;
    const write = async (force: boolean) => {
      const nowMs = deps.now();
      const body = buildPlaylist({ nowMs, horizon, fallback: inputs.fallback, offair: inputs.offair,
                                   offairSeqMs: deps.scheduledTime + config.loopMs }, config);
      // Ruling: off-air without a usable fallback writes the ENDLIST-only
      // playlist through the normal path below (cap and identical-bytes skip
      // apply), but stays loud: the notice is missing. Once per invocation.
      if (result.offairWithoutFallback === null) {
        const reason = offairWithoutFallback(inputs, horizon, nowMs, config);
        if (reason !== null) {
          result.offairWithoutFallback = reason;
          console.error(JSON.stringify({ event: "offair-without-fallback", reason, epoch_id: horizon.epoch_id,
                                         fallback_version: horizon.fallback_version, scheduled: deps.scheduledTime }));
          conditions.push({ key: "offair-without-fallback", priority: "high", resolvable: true,
                            title: "Off-air without a notice", message: reason });
        }
      }
      if (body === null) return;
      if (!force && body === lastBody) {
        result.skipped++;
        return;
      }
      if (result.puts >= cap) return;
      await bucket.put(LIVE_KEY, body, {
        httpMetadata: { contentType: "application/vnd.apple.mpegurl", cacheControl: `public, max-age=${config.liveMaxAge}` },
      });
      result.puts++;
      lastBody = body;
    };
    await write(true);
    const deadline = deps.scheduledTime + config.loopMs;
    while (result.puts < cap) {
      const now = deps.now();
      const next = startMs(g, indexAt(g, now) + 1);
      if (next > deadline) break;
      await deps.sleep(next - now + BOUNDARY_SLACK_MS);
      await write(false);
    }
    return result;
  } finally {
    await flush(); // after the last playlist write (or an early return), never before the guard
  }
}
```

`antenna/src/env.ts`:

```ts
import type { ClockEnv } from "./clock";
import type { GuardEnv } from "./guard";

/** Everything the Worker reads from its environment: wrangler vars, Worker
 * secrets (account details and tokens, never in the repo) and bindings. */
export interface AntennaEnv extends ClockEnv, GuardEnv {
  BUCKET: R2Bucket;
}
```

Replace `antenna/src/index.ts` with:

```ts
import { r2Bucket } from "./bucket";
import { type ClockResult, configFromEnv, runClock } from "./clock";
import type { AntennaEnv } from "./env";
import { guardConfigFromEnv, guardStep } from "./guard";

export default {
  async scheduled(controller, env, _ctx): Promise<void> {
    const started = Date.now();
    const bucket = r2Bucket(env.BUCKET);
    const now = () => Date.now();
    const fetchFn: typeof fetch = (input, init) => fetch(input, init);
    let result: ClockResult | undefined;
    let error: string | undefined;
    try {
      result = await runClock({
        bucket,
        now,
        sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
        scheduledTime: controller.scheduledTime,
        config: configFromEnv(env),
        guard: () => guardStep({ bucket, now, fetch: fetchFn, config: guardConfigFromEnv(env) }),
      });
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
      throw e; // still a failed invocation in observability
    } finally {
      // One line per invocation, ALWAYS (including when runClock throws); the
      // phase-1 verification compares scheduled vs actual fire times (lagMs).
      console.log(JSON.stringify({ event: "clock", scheduled: controller.scheduledTime, started,
                                   lagMs: started - controller.scheduledTime, ...result, ...(error ? { error } : {}) }));
    }
  },
} satisfies ExportedHandler<AntennaEnv>;
```

Replace `antenna/wrangler.jsonc` with (no account details: the account comes from `CLOUDFLARE_ACCOUNT_ID` in the git-ignored `antenna/.env`, and secrets are set with `wrangler secret put` in Task 17; `BILLING_ANNIVERSARY_DAY` is a plain var, ruling R12):

```jsonc
{
  "$schema": "node_modules/wrangler/config-schema.json",
  "name": "antenna",
  "main": "src/index.ts",
  "compatibility_date": "2026-10-01",
  // Cron-only: no routes, no fetch handler, and no public URL. A routeless
  // Worker otherwise gets a public, billed *.workers.dev URL that the zone's
  // WAF kill switch cannot reach (spec "Architecture").
  "workers_dev": false,
  "preview_urls": false,
  "triggers": { "crons": ["* * * * *"] },
  // The bucket name must match transmitter's [publish] bucket.
  "r2_buckets": [{ "binding": "BUCKET", "bucket_name": "lma-radio" }],
  "vars": {
    "PLAYLIST_WINDOW": "6",
    "GRACE_SEGMENTS": "3",
    "OFFAIR_AFTER_SECONDS": "86400",
    "LOOP_SECONDS": "75",
    "LIVE_MAX_AGE": "5",
    "LEAD_FLOOR_HOURS": "16",
    // The cost guard (spec "Cost guard"). MONTHLY_BUDGET_USD includes the $5
    // Workers Paid base; the billing period starts on BILLING_ANNIVERSARY_DAY
    // at 00:00 UTC. Account details are Worker secrets, never here:
    // CF_ACCOUNT_ID, CF_ZONE_ID, CF_ANALYTICS_TOKEN, CF_WAF_TOKEN
    // (see docs/playout-setup.md).
    "MONTHLY_BUDGET_USD": "15",
    "BILLING_ANNIVERSARY_DAY": "11",
    "GUARD_EVAL_SECONDS": "900",
    "BLIND_AFTER_SECONDS": "21600",
    "KILL_SWITCH_DESCRIPTION": "station: kill switch"
  },
  // One log line per invocation (~1,440/day) stays inside the free allowance.
  "observability": { "enabled": true }
}
```

- [ ] **Step 4: Run the tests and the type check**

Run: `cd antenna && npm test && npx tsc --noEmit`
Expected: PASS; no type errors. The `scheduled handler` test runs the **real** guard against the bound bucket with the wrangler vars and no secrets. It records the missing secrets in `state/guard.json` and makes no network call (both `meterProblems` and `wafProblems` short-circuit before any fetch). It is not blocked and writes the player `index.html`.

- [ ] **Step 5: Commit**

```bash
git add antenna/src/clock.ts antenna/src/env.ts antenna/src/index.ts antenna/wrangler.jsonc antenna/test/clock.test.ts
git commit -m "feat(antenna): the clock runs the cost guard first; blocked drives index.html and the off-air playlist"
```

- [ ] **Step 6: Review gate (orchestrator).** The spend-critical path is complete. Report to the parent and list:
- each dispatch since the last report, with its model;
- the review verdicts for Tasks 1–8;
- any ruling taken.

Then continue with Task 9.

---
### Task 9: Cloud alerts — dedupe, ntfy, email

**Model hint:** sonnet

**Files:**
- Create: `antenna/src/alerts.ts`, `antenna/test/alerts.test.ts`
- Modify: `antenna/src/env.ts`, `antenna/src/index.ts`, `antenna/wrangler.jsonc`

**Interfaces:**
- Consumes: `AlertCondition`, `Priority` (Task 6); the bucket seam (Task 1); `ClockDeps.alerts` (Task 8).
- Produces:
  - `ALERTS_KEY = "state/alerts.json"`, `COOLDOWN_MS` (15 min), `interface AlertEntry`, `type AlertState`, `interface Outgoing { key; kind: "alert" | "repeat" | "resolved"; priority; title; message }`.
  - `planAlerts(prev, conditions, nowMs, repeatMs) -> { next, send }`.
  - `interface Channel { name; send(o) }`, `ntfyChannel(fetchFn, url, token, station)`, `rawEmail(from, to, subject, text, nowMs, id)`, `interface EmailBinding`, `emailChannel(binding, from, to, station, now, Message?)`.
  - `interface AlertEnv`: secrets `NTFY_URL`, `NTFY_TOKEN`, `ALERT_EMAIL_FROM` and `ALERT_EMAIL_TO`; the binding `ALERT_EMAIL` (committed in Task 10; until then the email channel is off); vars `ALERT_REPEAT_HOURS` and `STATION_NAME`.
  - `channelsFromEnv(env, fetchFn, now)`, `repeatMsFromEnv(env)`, `dispatchAlerts(bucket, channels, conditions, nowMs, repeatMs) -> { sent, failed }`, `alertSink(bucket, env, fetchFn, now)`.

Rules (ruling R13). Conditions are recomputed every invocation, so a condition that is not computed has cleared.

- **Send:** when a condition first appears.
- **Repeat:** every `ALERT_REPEAT_HOURS` (6) while it lasts.
- **Resolved:** a notice when a resolvable condition clears.
- **Cooldown:** a condition that returns within 15 minutes counts as continuing (no new message).
- **Once:** a `once` condition (the spend levels, keyed by billing period and budget; `budget-file-invalid`) is sent when it first appears and never again: no repeat, no "resolved", not even when it returns. Its entry is kept 35 days after it clears, longer than a billing period.
- **Failure:** a message no channel accepted is not recorded as sent, so the next invocation retries it (a `once` alert included).
- **No channel configured:** the structured log line is the only output.
- **Overlap:** `alerts.json` is written with an etag-conditional PUT; overlapping invocations may duplicate a message, never lose one.

- [ ] **Step 1: Write the failing test**

`antenna/test/alerts.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { ALERTS_KEY, type AlertState, channelsFromEnv, COOLDOWN_MS, dispatchAlerts, emailChannel, ntfyChannel,
         type Outgoing, planAlerts, rawEmail } from "../src/alerts";
import type { AlertCondition } from "../src/conditions";
import { fakeFetch, MemoryBucket } from "./support";

const T0 = Date.parse("2026-10-20T12:00:00Z");
const H = 3_600_000;
const REPEAT = 6 * H;
const cond = (key: string, resolvable = true): AlertCondition =>
  ({ key, priority: "high", resolvable, title: `${key} title`, message: `${key} message` });

afterEach(() => {
  vi.restoreAllMocks();
});

describe("planAlerts", () => {
  it("sends a new condition once, repeats it every REPEAT, and resolves it when it clears", () => {
    let s: AlertState = {};
    let r = planAlerts(s, [cond("waf-api")], T0, REPEAT);
    expect(r.send.map((o) => o.kind)).toEqual(["alert"]);
    s = r.next;
    r = planAlerts(s, [cond("waf-api")], T0 + H, REPEAT);
    expect(r.send).toEqual([]);
    s = r.next;
    r = planAlerts(s, [cond("waf-api")], T0 + REPEAT, REPEAT);
    expect(r.send.map((o) => o.kind)).toEqual(["repeat"]);
    s = r.next;
    r = planAlerts(s, [], T0 + REPEAT + H, REPEAT);
    expect(r.send.map((o) => [o.kind, o.key])).toEqual([["resolved", "waf-api"]]);
    expect(r.next["waf-api"].active).toBe(false);
  });

  it("does not resolve a non-resolvable condition aloud", () => {
    const s = planAlerts({}, [cond("budget-50", false)], T0, REPEAT).next;
    expect(planAlerts(s, [], T0 + H, REPEAT).send).toEqual([]);
  });

  it("a condition that returns within the cooldown is continuing, not new", () => {
    let s = planAlerts({}, [cond("waf-api")], T0, REPEAT).next;
    s = planAlerts(s, [], T0 + 60_000, REPEAT).next;
    const back = planAlerts(s, [cond("waf-api")], T0 + 120_000, REPEAT);
    expect(back.send).toEqual([]);
    expect(back.next["waf-api"].active).toBe(true);
    s = planAlerts(back.next, [], T0 + 180_000, REPEAT).next;
    expect(planAlerts(s, [cond("waf-api")], T0 + 180_000 + COOLDOWN_MS, REPEAT).send.map((o) => o.kind)).toEqual(["alert"]);
  });

  it("sends a once condition when it first appears, never repeats it, and not again when it returns", () => {
    const once = (key: string): AlertCondition => ({ ...cond(key, false), once: true });
    let r = planAlerts({}, [once("budget-50:2026-10-11:15")], T0, REPEAT);
    expect(r.send.map((o) => o.kind)).toEqual(["alert"]);
    r = planAlerts(r.next, [once("budget-50:2026-10-11:15")], T0 + REPEAT, REPEAT);
    expect(r.send).toEqual([]);
    r = planAlerts(r.next, [], T0 + REPEAT + H, REPEAT); // the projection dipped under 50%
    expect(r.send).toEqual([]);
    r = planAlerts(r.next, [once("budget-50:2026-10-11:15")], T0 + 2 * REPEAT, REPEAT);
    expect(r.send).toEqual([]);
    // The next billing period is a new key.
    r = planAlerts(r.next, [once("budget-50:2026-11-11:15")], T0 + 3 * REPEAT, REPEAT);
    expect(r.send.map((o) => o.key)).toEqual(["budget-50:2026-11-11:15"]);
  });

  it("forgets inactive entries after a week", () => {
    let s = planAlerts({}, [cond("x")], T0, REPEAT).next;
    s = planAlerts(s, [], T0 + H, REPEAT).next;
    expect(planAlerts(s, [], T0 + 8 * 24 * H, REPEAT).next).toEqual({});
  });
});

describe("channels", () => {
  const o: Outgoing = { key: "tripped-spend", kind: "alert", priority: "urgent", title: "Station blocked: spend", message: "m" };

  it("ntfy: POST with title, priority, tags and the bearer token", async () => {
    const f = fakeFetch({ "POST https://ntfy.example/topic": () => new Response("{}") });
    await ntfyChannel(f.fetch, "https://ntfy.example/topic", "tk_1", "llama radio").send(o);
    expect(f.calls[0].headers).toMatchObject({ title: "llama radio: Station blocked: spend", priority: "5",
                                               tags: "rotating_light", authorization: "Bearer tk_1" });
    expect(f.calls[0].body).toBe("m");
    const bad = fakeFetch({ "POST ": () => new Response("no", { status: 429 }) });
    await expect(ntfyChannel(bad.fetch, "https://ntfy.example/topic", undefined, "s").send(o)).rejects.toThrow(/429/);
  });

  it("email: a send_email message from the configured sender to the configured recipient", async () => {
    const sent: { from: string; to: string; raw: string }[] = [];
    class FakeMessage {
      constructor(public from: string, public to: string, public raw: string) {}
    }
    const ch = emailChannel({ send: async (m) => { sent.push(m as unknown as FakeMessage); } }, "radio@example.org",
                            "ops@example.net", "llama radio", () => T0, FakeMessage as never);
    await ch.send(o);
    expect(sent[0]).toMatchObject({ from: "radio@example.org", to: "ops@example.net" });
    expect(sent[0].raw).toContain("Subject: llama radio: Station blocked: spend\r\n");
  });

  it("rawEmail: headers, an encoded non-ASCII subject, a base64 body", () => {
    const raw = rawEmail("a@example.org", "b@example.net", "Spend — 80%", "héllo", T0, "id1");
    expect(raw).toContain("From: a@example.org\r\nTo: b@example.net\r\n");
    expect(raw).toMatch(/Subject: =\?UTF-8\?B\?[A-Za-z0-9+/=]+\?=\r\n/);
    expect(raw).toContain("Message-ID: <id1@example.org>\r\n");
    expect(raw).toContain("Content-Transfer-Encoding: base64\r\n\r\n");
    const body = raw.split("\r\n\r\n")[1].replace(/\r\n/g, "");
    expect(new TextDecoder().decode(Uint8Array.from(atob(body), (c) => c.charCodeAt(0)))).toBe("héllo");
  });

  it("channelsFromEnv: only what is fully configured", () => {
    const f = fakeFetch({});
    expect(channelsFromEnv({}, f.fetch, () => T0)).toEqual([]);
    expect(channelsFromEnv({ NTFY_URL: "https://n/t" }, f.fetch, () => T0).map((c) => c.name)).toEqual(["ntfy"]);
    const binding = { send: async () => undefined };
    expect(channelsFromEnv({ ALERT_EMAIL: binding, ALERT_EMAIL_FROM: "a@x" }, f.fetch, () => T0)).toEqual([]);
    expect(channelsFromEnv({ ALERT_EMAIL: binding, ALERT_EMAIL_FROM: "a@x", ALERT_EMAIL_TO: "b@y" }, f.fetch, () => T0)
      .map((c) => c.name)).toEqual(["email"]);
  });
});

describe("dispatchAlerts", () => {
  it("sends to every channel, records the send, and does not resend the next minute", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    const got: string[] = [];
    const ch = (name: string) => ({ name, send: async (o: Outgoing) => { got.push(`${name}:${o.key}`); } });
    expect(await dispatchAlerts(bucket, [ch("a"), ch("b")], [cond("lead-low")], T0, REPEAT)).toEqual({ sent: 1, failed: 0 });
    expect(got).toEqual(["a:lead-low", "b:lead-low"]);
    expect(bucket.json(ALERTS_KEY)["lead-low"].active).toBe(true);
    await dispatchAlerts(bucket, [ch("a")], [cond("lead-low")], T0 + 60_000, REPEAT);
    expect(got).toHaveLength(2);
  });

  it("one working channel is enough; when every channel fails the next invocation retries", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    const broken = { name: "x", send: async () => { throw new Error("down"); } };
    const got: string[] = [];
    const ok = { name: "ok", send: async (o: Outgoing) => { got.push(o.key); } };
    expect(await dispatchAlerts(bucket, [broken], [cond("waf-api")], T0, REPEAT)).toEqual({ sent: 0, failed: 1 });
    expect(await dispatchAlerts(bucket, [broken, ok], [cond("waf-api")], T0 + 60_000, REPEAT)).toEqual({ sent: 1, failed: 0 });
    expect(got).toEqual(["waf-api"]);
  });

  it("a once alert no channel accepted is sent at the next invocation", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    const broken = { name: "x", send: async () => { throw new Error("down"); } };
    const got: string[] = [];
    const ok = { name: "ok", send: async (o: Outgoing) => { got.push(o.key); } };
    const c: AlertCondition = { ...cond("budget-80:2026-10-11:15", false), once: true };
    expect(await dispatchAlerts(bucket, [broken], [c], T0, REPEAT)).toEqual({ sent: 0, failed: 1 });
    expect(await dispatchAlerts(bucket, [ok], [c], T0 + 60_000, REPEAT)).toEqual({ sent: 1, failed: 0 });
    expect(got).toEqual(["budget-80:2026-10-11:15"]);
  });

  it("writes alerts.json only when the state changed", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    await dispatchAlerts(bucket, [], [], T0, REPEAT);
    expect(bucket.puts(ALERTS_KEY)).toBe(0);
    await dispatchAlerts(bucket, [], [cond("x")], T0, REPEAT);
    await dispatchAlerts(bucket, [], [cond("x")], T0 + 60_000, REPEAT);
    expect(bucket.puts(ALERTS_KEY)).toBe(1);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd antenna && npx vitest run test/alerts.test.ts`
Expected: FAIL. `../src/alerts` cannot be resolved.

- [ ] **Step 3: Implement**

`antenna/src/alerts.ts` (`cloudflare:email` is a workerd built-in, available in the vitest pool too):

```ts
/** Cloud alerts (spec "Alerts and operations"): conditions computed each
 * invocation are deduped per key in state/alerts.json and sent to ntfy (HTTP
 * POST) and email (Email Routing's send_email binding, to the ALERT_EMAIL_TO
 * secret). Sent when a condition appears, repeated every ALERT_REPEAT_HOURS
 * while it lasts, "resolved" when a resolvable one clears; a `once` condition
 * is sent when it first appears and never again. A condition that clears and
 * returns within COOLDOWN_MS is treated as continuing (no new message), so a
 * flapping API does not page every minute. */

import { EmailMessage } from "cloudflare:email";
import { type BucketLike, putJson, readJsonDoc } from "./bucket";
import type { AlertCondition, Priority } from "./conditions";

export const ALERTS_KEY = "state/alerts.json";
export const COOLDOWN_MS = 15 * 60_000;
const KEEP_INACTIVE_MS = 7 * 86_400_000;
/** A `once` entry is kept this long after it clears: longer than a billing period. */
const ONCE_KEEP_MS = 35 * 86_400_000;
const TIMEOUT_MS = 10_000;

export interface AlertEntry {
  active: boolean;
  resolvable: boolean;
  title: string;
  first_at: string;
  last_sent_at: string | null;
  cleared_at: string | null;
  once?: boolean;
}
export type AlertState = Record<string, AlertEntry>;

export interface Outgoing {
  key: string;
  kind: "alert" | "repeat" | "resolved";
  priority: Priority;
  title: string;
  message: string;
}

const iso = (ms: number) => new Date(ms).toISOString();
const age = (nowMs: number, at: string | null) => (at === null ? Number.POSITIVE_INFINITY : nowMs - Date.parse(at));

export function planAlerts(prev: AlertState, conditions: AlertCondition[], nowMs: number,
                           repeatMs: number): { next: AlertState; send: Outgoing[] } {
  const next: AlertState = {};
  const send: Outgoing[] = [];
  const seen = new Set<string>();
  for (const c of conditions) {
    if (seen.has(c.key)) continue;
    seen.add(c.key);
    const e = prev[c.key];
    const out = { key: c.key, priority: c.priority, title: c.title, message: c.message };
    if (c.once) {
      // Sent once; its entry stays (active or not) so it is never sent again.
      next[c.key] = e ? { ...e, active: true, cleared_at: null }
                      : { active: true, resolvable: false, once: true, title: c.title, first_at: iso(nowMs),
                          last_sent_at: iso(nowMs), cleared_at: null };
      if (!e) send.push({ ...out, kind: "alert" });
    } else if (!e || (!e.active && age(nowMs, e.cleared_at) >= COOLDOWN_MS)) {
      next[c.key] = { active: true, resolvable: c.resolvable, title: c.title, first_at: iso(nowMs),
                      last_sent_at: iso(nowMs), cleared_at: null };
      send.push({ ...out, kind: "alert" });
    } else if (age(nowMs, e.last_sent_at) >= repeatMs) {
      next[c.key] = { ...e, active: true, resolvable: c.resolvable, title: c.title, last_sent_at: iso(nowMs), cleared_at: null };
      send.push({ ...out, kind: "repeat" });
    } else {
      next[c.key] = { ...e, active: true, resolvable: c.resolvable, title: c.title, cleared_at: null };
    }
  }
  for (const [key, e] of Object.entries(prev)) {
    if (seen.has(key)) continue;
    if (e.active) {
      next[key] = { ...e, active: false, cleared_at: iso(nowMs) };
      if (e.resolvable) send.push({ key, kind: "resolved", priority: "default", title: e.title,
                                    message: `Resolved: ${e.title} (active since ${e.first_at}).` });
    } else if (age(nowMs, e.cleared_at) < (e.once ? ONCE_KEEP_MS : KEEP_INACTIVE_MS)) {
      next[key] = e;
    }
  }
  return { next, send };
}

export interface Channel {
  name: string;
  send(o: Outgoing): Promise<void>;
}

const NTFY_PRIORITY: Record<Priority, string> = { urgent: "5", high: "4", default: "3" };
const NTFY_TAGS: Record<Priority, string> = { urgent: "rotating_light", high: "warning", default: "information_source" };

export function ntfyChannel(fetchFn: typeof fetch, url: string, token: string | undefined, station: string): Channel {
  return {
    name: "ntfy",
    async send(o) {
      const headers: Record<string, string> = {
        Title: `${station}: ${o.kind === "resolved" ? "resolved: " : ""}${o.title}`,
        Priority: o.kind === "resolved" ? "3" : NTFY_PRIORITY[o.priority],
        Tags: o.kind === "resolved" ? "white_check_mark" : NTFY_TAGS[o.priority],
      };
      if (token) headers.Authorization = `Bearer ${token}`;
      const res = await fetchFn(url, { method: "POST", headers, body: o.message, signal: AbortSignal.timeout(TIMEOUT_MS) });
      if (!res.ok) throw new Error(`ntfy: HTTP ${res.status}`);
    },
  };
}

function b64(text: string): string {
  let bin = "";
  for (const byte of new TextEncoder().encode(text)) bin += String.fromCharCode(byte);
  return btoa(bin);
}

/** A minimal RFC 5322 text/plain message (base64 body, RFC 2047 subject). */
export function rawEmail(from: string, to: string, subject: string, text: string, nowMs: number, id: string): string {
  const subj = /^[\x20-\x7e]*$/.test(subject) ? subject : `=?UTF-8?B?${b64(subject)}?=`;
  const domain = from.includes("@") ? from.slice(from.lastIndexOf("@") + 1) : "localhost";
  const body = (b64(text).match(/.{1,76}/g) ?? []).join("\r\n");
  return [`From: ${from}`, `To: ${to}`, `Subject: ${subj}`, `Date: ${new Date(nowMs).toUTCString()}`,
          `Message-ID: <${id}@${domain}>`, "MIME-Version: 1.0", "Content-Type: text/plain; charset=utf-8",
          "Content-Transfer-Encoding: base64", "", body, ""].join("\r\n");
}

export interface EmailBinding {
  send(message: EmailMessage): Promise<unknown>;
}

export function emailChannel(binding: EmailBinding, from: string, to: string, station: string, now: () => number,
                             Message: typeof EmailMessage = EmailMessage): Channel {
  return {
    name: "email",
    async send(o) {
      const subject = `${station}: ${o.kind === "resolved" ? "resolved: " : ""}${o.title}`;
      const text = `${o.message}\n\n-- antenna clock, ${iso(now())}\n`;
      await binding.send(new Message(from, to, rawEmail(from, to, subject, text, now(), crypto.randomUUID())));
    },
  };
}

export interface AlertEnv {
  NTFY_URL?: string;
  NTFY_TOKEN?: string;
  ALERT_EMAIL?: EmailBinding;
  ALERT_EMAIL_FROM?: string;
  ALERT_EMAIL_TO?: string;
  ALERT_REPEAT_HOURS?: string;
  STATION_NAME?: string;
}

export function channelsFromEnv(env: AlertEnv, fetchFn: typeof fetch, now: () => number): Channel[] {
  const station = env.STATION_NAME?.trim() || "llama radio";
  const out: Channel[] = [];
  if (env.NTFY_URL?.trim()) out.push(ntfyChannel(fetchFn, env.NTFY_URL.trim(), env.NTFY_TOKEN?.trim() || undefined, station));
  if (env.ALERT_EMAIL && env.ALERT_EMAIL_FROM?.trim() && env.ALERT_EMAIL_TO?.trim()) {
    out.push(emailChannel(env.ALERT_EMAIL, env.ALERT_EMAIL_FROM.trim(), env.ALERT_EMAIL_TO.trim(), station, now));
  }
  return out;
}

export function repeatMsFromEnv(env: AlertEnv): number {
  const h = Number(env.ALERT_REPEAT_HOURS);
  return (Number.isFinite(h) && h >= 1 ? h : 6) * 3_600_000;
}

/** Plan, send, persist. Every message is also logged. A message no channel
 * accepted is not recorded as sent, so the next invocation retries it. */
export async function dispatchAlerts(bucket: BucketLike, channels: Channel[], conditions: AlertCondition[],
                                     nowMs: number, repeatMs: number): Promise<{ sent: number; failed: number }> {
  const read = await readJsonDoc<AlertState>(bucket, ALERTS_KEY);
  const prev: AlertState = read.kind === "ok" && read.value && typeof read.value === "object" ? read.value : {};
  const { next, send } = planAlerts(prev, conditions, nowMs, repeatMs);
  let sent = 0;
  let failed = 0;
  for (const o of send) {
    console.error(JSON.stringify({ event: "alert", kind: o.kind, key: o.key, title: o.title, message: o.message }));
    let delivered = channels.length === 0; // with no channel configured the log line is all there is
    for (const ch of channels) {
      try {
        await ch.send(o);
        delivered = true;
      } catch (e) {
        console.error(JSON.stringify({ event: "alert-channel-failed", channel: ch.name, key: o.key,
                                       error: e instanceof Error ? e.message : String(e) }));
      }
    }
    if (delivered) sent++;
    else {
      failed++;
      if (next[o.key]?.once) delete next[o.key]; // never sent: the next invocation sends it as new
      else if (o.kind !== "resolved" && next[o.key]) {
        next[o.key] = { ...next[o.key], last_sent_at: prev[o.key]?.last_sent_at ?? null };
      }
    }
  }
  if (JSON.stringify(next) !== JSON.stringify(prev)) {
    // A lost race means an overlapping invocation recorded the same sends.
    await putJson(bucket, ALERTS_KEY, next, read.kind === "absent" ? undefined : read.etag);
  }
  return { sent, failed };
}

export function alertSink(bucket: BucketLike, env: AlertEnv, fetchFn: typeof fetch, now: () => number) {
  const channels = channelsFromEnv(env, fetchFn, now);
  const repeatMs = repeatMsFromEnv(env);
  return async (conditions: AlertCondition[], nowMs: number) => {
    await dispatchAlerts(bucket, channels, conditions, nowMs, repeatMs);
  };
}
```

Replace `antenna/src/env.ts` with:

```ts
import type { AlertEnv } from "./alerts";
import type { ClockEnv } from "./clock";
import type { GuardEnv } from "./guard";

/** Everything the Worker reads from its environment: wrangler vars, Worker
 * secrets (account details and tokens, never in the repo) and bindings. */
export interface AntennaEnv extends ClockEnv, GuardEnv, AlertEnv {
  BUCKET: R2Bucket;
}
```

Replace `antenna/src/index.ts` with:

```ts
import { alertSink } from "./alerts";
import { r2Bucket } from "./bucket";
import { type ClockResult, configFromEnv, runClock } from "./clock";
import type { AntennaEnv } from "./env";
import { guardConfigFromEnv, guardStep } from "./guard";

export default {
  async scheduled(controller, env, _ctx): Promise<void> {
    const started = Date.now();
    const bucket = r2Bucket(env.BUCKET);
    const now = () => Date.now();
    const fetchFn: typeof fetch = (input, init) => fetch(input, init);
    let result: ClockResult | undefined;
    let error: string | undefined;
    try {
      result = await runClock({
        bucket,
        now,
        sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
        scheduledTime: controller.scheduledTime,
        config: configFromEnv(env),
        guard: () => guardStep({ bucket, now, fetch: fetchFn, config: guardConfigFromEnv(env) }),
        alerts: alertSink(bucket, env, fetchFn, now),
      });
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
      throw e; // still a failed invocation in observability
    } finally {
      // One line per invocation, ALWAYS (including when runClock throws); the
      // phase-1 verification compares scheduled vs actual fire times (lagMs).
      console.log(JSON.stringify({ event: "clock", scheduled: controller.scheduledTime, started,
                                   lagMs: started - controller.scheduledTime, ...result, ...(error ? { error } : {}) }));
    }
  },
} satisfies ExportedHandler<AntennaEnv>;
```

In `antenna/wrangler.jsonc`, replace the line `    "KILL_SWITCH_DESCRIPTION": "station: kill switch"` with:

```jsonc
    "KILL_SWITCH_DESCRIPTION": "station: kill switch",
    // Cloud alerts: ntfy (secrets NTFY_URL, optional NTFY_TOKEN) and email
    // through the ALERT_EMAIL send_email binding, from ALERT_EMAIL_FROM to
    // ALERT_EMAIL_TO (secrets). Never put an address in this file.
    "ALERT_REPEAT_HOURS": "6",
    "STATION_NAME": "llama radio"
```

- [ ] **Step 4: Run the tests and the type check**

Run: `cd antenna && npm test && npx tsc --noEmit`
Expected: PASS (the `scheduled handler` test now also writes `state/alerts.json`); no type errors.

- [ ] **Step 5: Commit**

```bash
git add antenna/src/alerts.ts antenna/test/alerts.test.ts antenna/src/env.ts antenna/src/index.ts antenna/wrangler.jsonc
git commit -m "feat(antenna): cloud alerts deduped in state/alerts.json, sent to ntfy and Email Routing"
```

---

### Task 10: The send_email binding; index.html left to the clock

**Model hint:** sonnet

**Files:**
- Create: `antenna/test/wrangler-config.test.ts`
- Modify: `antenna/wrangler.jsonc` (the binding), `antenna/tsconfig.json` (Vite's client types), `antenna/scripts/deploy-assets.mjs` (no `index.html`)

**Interfaces:**
- Consumes: `antenna/wrangler.jsonc` (Tasks 8–9); `AlertEnv.ALERT_EMAIL` (Task 9); the clock's ownership of `index.html` (Tasks 7–8).
- Produces: the committed, unrestricted binding `"send_email": [{ "name": "ALERT_EMAIL" }]`, and a test that keeps `wrangler.jsonc` free of account details and addresses.

Amendment A3. The binding names no destination: a `send_email` binding can only reach the account's verified destination addresses, and the one the Worker writes to is the `ALERT_EMAIL_TO` secret. The deploy stays `npx wrangler deploy`. The test reads `wrangler.jsonc` as text through Vite's `?raw` import; `tsc` learns that import from `vite/client`'s types (Vite comes with vitest), so no declaration file is needed. The vitest pool binds `ALERT_EMAIL` from the same file, which the test also checks.

- [ ] **Step 1: Write the failing test**

`antenna/test/wrangler-config.test.ts`:

```ts
import { env } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import wranglerText from "../wrangler.jsonc?raw";

/** wrangler.jsonc uses whole-line // comments only. */
const config = JSON.parse(wranglerText.split("\n").filter((l) => !l.trim().startsWith("//")).join("\n"));

describe("wrangler.jsonc (this repo is public)", () => {
  it("carries no account details and no email address", () => {
    expect(config).not.toHaveProperty("account_id");
    expect(wranglerText).not.toMatch(/@[a-z0-9-]+\.[a-z]/i);
    expect(config.workers_dev).toBe(false);
    expect(config.preview_urls).toBe(false);
  });

  it("binds send_email unrestricted: the destination is the ALERT_EMAIL_TO secret", () => {
    expect(config.send_email).toEqual([{ name: "ALERT_EMAIL" }]);
    const bound = (env as unknown as { ALERT_EMAIL?: { send?: unknown } }).ALERT_EMAIL;
    expect(typeof bound?.send).toBe("function");
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd antenna && npx vitest run test/wrangler-config.test.ts`
Expected: FAIL. `config.send_email` is undefined and `env.ALERT_EMAIL` is not bound.

- [ ] **Step 3: Implement**

In `antenna/wrangler.jsonc`, insert before the line `  // One log line per invocation (~1,440/day) stays inside the free allowance.`:

```jsonc
  // Alert email (Email Routing). Unrestricted on purpose: a send_email binding
  // can only reach the account's verified destination addresses, and the one
  // used is the ALERT_EMAIL_TO secret. Never put an address in this file.
  "send_email": [{ "name": "ALERT_EMAIL" }],
```

In `antenna/tsconfig.json`, change `"types": ["@cloudflare/vitest-plugin/types"]` to `"types": ["@cloudflare/vitest-plugin/types", "vite/client"]` (Vite's own declaration of `?raw` imports).

In `antenna/scripts/deploy-assets.mjs`, make two edits:

1. Delete the `ASSETS` entry `["index.html", "public/index.html", HTML, "public, max-age=60"],` and its comment line `// last: short TTL, and it references everything above`.
2. Replace the header comment's second sentence with:

```js
// Upload antenna's static assets to the station's R2 bucket (spec "R2 object
// contract": offair.html and the app assets incl. hls.js). index.html is NOT
// uploaded: the clock writes it (the player page, or the off-air page while the
// station is blocked) from the copies bundled into the Worker (src/pages.ts).
```

- [ ] **Step 4: Run the tests and the checks**

Run: `cd antenna && npm test && npx tsc --noEmit && ANTENNA_BUCKET=b node scripts/deploy-assets.mjs --dry-run | grep -c "index.html"`
Expected:
- the tests pass, and `tsc` is clean (it now knows the `?raw` import);
- `grep -c` prints `0`.

Do **not** run `wrangler deploy`, not even `--dry-run`: the operator does, at Task 17.

- [ ] **Step 5: Commit**

```bash
git add antenna/wrangler.jsonc antenna/tsconfig.json antenna/scripts/deploy-assets.mjs antenna/test/wrangler-config.test.ts
git commit -m "feat(antenna): unrestricted send_email binding, destination in a secret; index.html left to the clock"
```

---

### Task 11: Player — kill switch detected mid-play

**Model hint:** sonnet

**Files:**
- Modify: `antenna/public/nowplaying.js`, `antenna/public/player.js` (replace both whole files), `antenna/test/nowplaying.test.ts` (import line + appended tests)

**Interfaces:**
- Consumes: the phase-1 player.
- Produces:
  - `nowplaying.js`: `hlsErrorNotice` also reads `data.networkDetails.status`;
  - `classifyProbe(status, body) -> "offair" | "unknown"`;
  - `class StallWatch({ stallMs = 15000, probeEveryMs = 10000, verdictsNeeded = 2 })` with `reset(nowMs)`, `tick(positionS, nowMs) -> boolean` (probe now?), `verdict(v) -> boolean` (go off-air?) and `stalled(nowMs)`.

Amendment A2. The probe is `fetch("live.m3u8", { cache: "no-store" })`. It is answered at the edge: a cache hit (the `Cache-Control: no-cache` that `no-store` adds does not bypass the edge cache, measured 2026-10-12; the edge refetches `live.m3u8` from R2 at most every 5 s, whoever asks), or the WAF's 403 while blocked. It is never billed per request, and at most one runs per 10 s per stalled listener. `index.html` is unchanged, so `src/pages.ts` stays fresh.

- [ ] **Step 1: Write the failing tests**

In `antenna/test/nowplaying.test.ts`, change the import to:

```ts
import { classifyProbe, findNowPlaying, hlsErrorNotice, playBlockedNotice, nowPlayingText, prefersNativeHls,
         StallWatch } from "../public/nowplaying.js";
```

and append:

```ts
describe("hlsErrorNotice: the 403 can arrive on networkDetails", () => {
  it("treats networkDetails.status 403 as off-air", () => {
    expect(hlsErrorNotice({ fatal: false, networkDetails: { status: 403 } })).toBe("The station is off the air.");
  });
});

describe("classifyProbe", () => {
  it("only a 403 or an ENDLIST playlist is off-air", () => {
    expect(classifyProbe(403, "")).toBe("offair");
    expect(classifyProbe(200, "#EXTM3U\n#EXT-X-ENDLIST\n")).toBe("offair");
    for (const [s, b] of [[0, ""], [200, "#EXTM3U\nseg/e1/1.aac\n"], [503, ""], [429, ""], [404, ""]] as const) {
      expect(classifyProbe(s, b)).toBe("unknown");
    }
  });
});

describe("StallWatch", () => {
  const playFor = (w: StallWatch, fromS: number, fromMs: number, seconds: number) => {
    for (let i = 0; i <= seconds; i++) expect(w.tick(fromS + i, fromMs + i * 1000)).toBe(false);
  };

  it("never probes while playback advances", () => {
    const w = new StallWatch();
    w.reset(0);
    playFor(w, 0, 0, 120);
  });

  it("probes after 15 s without progress, at most every 10 s, one at a time", () => {
    const w = new StallWatch();
    w.reset(0);
    playFor(w, 0, 0, 10); // position 10 at t=10 s
    const probes: number[] = [];
    for (let t = 11_000; t <= 60_000; t += 1000) {
      if (w.tick(10, t)) {
        probes.push(t);
        expect(w.tick(10, t + 500)).toBe(false); // still probing
        w.verdict("unknown");
      }
    }
    expect(probes).toEqual([25_000, 35_000, 45_000, 55_000]);
  });

  it("goes off-air on two consecutive off-air verdicts (the kill switch mid-play)", () => {
    const w = new StallWatch();
    w.reset(0);
    playFor(w, 0, 0, 10);
    expect(w.tick(10, 25_000)).toBe(true);
    expect(w.verdict("offair")).toBe(false);
    expect(w.tick(10, 35_000)).toBe(true);
    expect(w.verdict("offair")).toBe(true);
  });

  it("a blip: network errors while stalled, then progress resumes -- never off-air", () => {
    const w = new StallWatch();
    w.reset(0);
    playFor(w, 0, 0, 10);
    expect(w.tick(10, 25_000)).toBe(true);
    expect(w.verdict("offair")).toBe(false); // one stray 403 is not enough...
    expect(w.tick(10, 35_000)).toBe(true);
    expect(w.verdict("unknown")).toBe(false); // ...and a non-verdict resets the count
    expect(w.tick(10, 45_000)).toBe(true);
    expect(w.verdict("offair")).toBe(false);
    expect(w.tick(11, 46_000)).toBe(false); // playing again
    expect(w.stalled(47_000)).toBe(false);
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd antenna && npx vitest run test/nowplaying.test.ts`
Expected: FAIL. `classifyProbe`/`StallWatch` are not exported.

- [ ] **Step 3: Implement**

Replace `antenna/public/nowplaying.js` with:

```js
// Pure helpers for the player (unit-tested). The player computes now-playing
// client-side: program-date-time of the playback position, looked up in
// timeline.json -- no request stream bills per listener.

/** Native HLS on Apple WebKit (Safari and every iOS browser -- all WebKit);
 * hls.js everywhere else, including Chrome whose native HLS is buggy. Detected
 * by vendor, not canPlayType alone (also true on Chrome). */
export function prefersNativeHls(nav, canPlayNative) {
  const vendor = typeof nav.vendor === "string" ? nav.vendor : "";
  return Boolean(canPlayNative) && vendor.startsWith("Apple");
}

/** Notice text for a rejected audio.play(), or null to ignore it. Only a
 * NotAllowedError while still playing is a real "blocked"; an AbortError is
 * play() being interrupted by our own stop()/offAir() and must not overwrite
 * the off-air notice. */
export function playBlockedNotice(err, stillPlaying) {
  if (!stillPlaying || !err || err.name !== "NotAllowedError") return null;
  return "Playback was blocked; press Try again.";
}

/** Notice text for an hls.js ERROR event, or null to let hls.js recover. A
 * 403 is the kill switch; levelEmptyError is the clock's ENDLIST-only
 * playlist (off-air with no notice), which hls.js reports as a non-fatal
 * error rather than a LEVEL_LOADED it would otherwise keep reloading. */
export function hlsErrorNotice(data) {
  const code = (data && data.response && data.response.code) || (data && data.networkDetails && data.networkDetails.status);
  if (code === 403 || (data && data.details === "levelEmptyError")) return "The station is off the air.";
  if (data && data.fatal) return "The stream is unavailable right now.";
  return null;
}

/** Timeline contract: shows[].files[] are sorted by start (the writer emits
 * them in play order); the early `break` below relies on it. */
export function findNowPlaying(timeline, atMs) {
  if (!timeline || !Array.isArray(timeline.shows)) return null;
  for (const show of timeline.shows) {
    if (atMs >= Date.parse(show.start) && atMs < Date.parse(show.end)) {
      let file = null;
      for (const f of show.files || []) {
        if (Date.parse(f.start) <= atMs) file = f;
        else break;
      }
      return { show, file };
    }
  }
  return null;
}

export function nowPlayingText(np, timelineLoaded) {
  if (!np) return timelineLoaded ? "We'll be back shortly." : "Tuning in…";
  const s = np.show;
  const where = [s.venue, s.city].filter(Boolean).join(", ");
  const head = [s.artist, [s.date, where].filter(Boolean).join(", ")].filter(Boolean).join(" — ");
  return np.file ? `${head} · ${np.file.title}` : head;
}

/** A probe of live.m3u8 made while playback is stalled. "offair" is
 * definitive: the WAF kill switch answers 403, and the clock's off-air
 * playlist ends with #EXT-X-ENDLIST. Anything else -- a network error
 * (status 0), a 5xx, a 429, a live playlist -- is not a reason to stop. */
export function classifyProbe(status, body) {
  if (status === 403) return "offair";
  if (status === 200 && typeof body === "string" && body.includes("#EXT-X-ENDLIST")) return "offair";
  return "unknown";
}

/** Notices playback that stopped advancing without trusting the player's
 * error events (an already-playing page went silent on the kill switch:
 * phase-1 verification, 2026-10-11). Fed the playback position about once a
 * second while playing. After stallMs without progress it asks for a probe
 * (at most one every probeEveryMs, one at a time); `verdictsNeeded`
 * consecutive "offair" verdicts stop the player. Any progress resets it, so a
 * network blip that recovers never shows the off-air notice. */
export class StallWatch {
  constructor({ stallMs = 15000, probeEveryMs = 10000, verdictsNeeded = 2 } = {}) {
    this.stallMs = stallMs;
    this.probeEveryMs = probeEveryMs;
    this.verdictsNeeded = verdictsNeeded;
    this.reset(0);
  }

  reset(nowMs) {
    this.lastPos = null;
    this.lastProgressMs = nowMs;
    this.lastProbeMs = null;
    this.probing = false;
    this.offairCount = 0;
  }

  /** True when the caller should probe now. */
  tick(positionS, nowMs) {
    if (this.lastPos === null || positionS > this.lastPos + 0.05) {
      this.lastPos = positionS;
      this.lastProgressMs = nowMs;
      this.offairCount = 0;
      return false;
    }
    if (!this.stalled(nowMs) || this.probing) return false;
    if (this.lastProbeMs !== null && nowMs - this.lastProbeMs < this.probeEveryMs) return false;
    this.lastProbeMs = nowMs;
    this.probing = true;
    return true;
  }

  /** Feed a classifyProbe verdict; true when the player should go off-air. */
  verdict(v) {
    this.probing = false;
    this.offairCount = v === "offair" ? this.offairCount + 1 : 0;
    return this.offairCount >= this.verdictsNeeded;
  }

  stalled(nowMs) {
    return nowMs - this.lastProgressMs >= this.stallMs;
  }
}
```

Replace `antenna/public/player.js` with:

```js
import { classifyProbe, findNowPlaying, hlsErrorNotice, nowPlayingText, playBlockedNotice, prefersNativeHls,
         StallWatch } from "./nowplaying.js";

const STREAM = "live.m3u8";
const TIMELINE = "timeline.json";
const TIMELINE_REFRESH_MS = 3 * 60 * 1000;

const audio = document.getElementById("audio");
const playButton = document.getElementById("play");
const nowPlaying = document.getElementById("now-playing");
const notice = document.getElementById("notice");
const noticeText = document.getElementById("notice-text");
const retryButton = document.getElementById("retry");
document.getElementById("stream-url").textContent = new URL(STREAM, location.href).href;

let hls = null;
let playing = false;
let timeline = null;
let timelineFetchedAt = 0;
const watch = new StallWatch();

const useNative = () => prefersNativeHls(navigator, audio.canPlayType("application/vnd.apple.mpegurl") !== "");

function showNotice(text) {
  noticeText.textContent = text;
  notice.hidden = false;
}

function stop() {
  playing = false;
  if (hls) {
    hls.destroy();
    hls = null;
  }
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  playButton.textContent = "Play";
}

// Off-air (ENDLIST) or blocked (403): stop, show the notice, never auto-reconnect.
function offAir(text) {
  stop();
  showNotice(text);
  nowPlaying.textContent = "";
}

// Radio semantics: every start joins the live edge (pause = stop).
function start() {
  stop();
  notice.hidden = true;
  playing = true;
  watch.reset(Date.now());
  playButton.textContent = "Stop";
  if (useNative()) {
    audio.src = STREAM;
  } else if (window.Hls && window.Hls.isSupported()) {
    hls = new window.Hls({ liveSyncDurationCount: 3 });
    hls.on(window.Hls.Events.LEVEL_LOADED, (_event, data) => {
      if (data.details && data.details.live === false) offAir("The station is off the air.");
    });
    hls.on(window.Hls.Events.ERROR, (_event, data) => {
      const text = hlsErrorNotice(data);
      if (text) offAir(text);
    });
    hls.loadSource(STREAM);
    hls.attachMedia(audio);
  } else {
    offAir("This browser cannot play the stream here; open the stream URL in VLC.");
    return;
  }
  audio.play().catch((err) => {
    const text = playBlockedNotice(err, playing);
    if (text) offAir(text);
  });
  refreshTimeline(true);
}

audio.addEventListener("ended", () => offAir("The station is off the air."));
audio.addEventListener("error", () => {
  if (playing) offAir("The stream is unavailable right now.");
});
// Pause from OS/lock-screen controls: treat as stop (stop() sets playing=false
// before its own pause, so this cannot recurse).
// A natural end fires pause then ended with audio.ended already true; stop()'s
// load() would cancel that pending ended event and swallow the off-air notice.
audio.addEventListener("pause", () => {
  if (playing && !audio.ended) stop();
});
playButton.addEventListener("click", () => (playing ? stop() : start()));
retryButton.addEventListener("click", start);

function playbackDateMs() {
  if (hls && hls.playingDate) return hls.playingDate.getTime();
  if (typeof audio.getStartDate === "function") {
    const startMs = audio.getStartDate().getTime();
    if (Number.isFinite(startMs)) return startMs + audio.currentTime * 1000;
  }
  return null;
}

// Fetched only while playing, at most every few minutes, never while hidden.
async function refreshTimeline(force) {
  if (!playing || document.hidden) return;
  if (!force && Date.now() - timelineFetchedAt < TIMELINE_REFRESH_MS) return;
  timelineFetchedAt = Date.now();
  try {
    const res = await fetch(TIMELINE);
    if (res.ok) timeline = await res.json();
  } catch {
    // keep the last timeline
  }
}

// Stalled playback: ask live.m3u8 directly whether the station is off the air.
// The answer is a cache hit (the edge refetches live.m3u8 from R2 at most every
// 5 s, whoever asks) or the kill switch's 403: never billed per request.
async function probe() {
  let status = 0;
  let body = "";
  try {
    const res = await fetch(STREAM, { cache: "no-store" });
    status = res.status;
    if (res.ok) body = await res.text();
  } catch {
    // a network error is not a verdict
  }
  if (!playing) return;
  if (watch.verdict(classifyProbe(status, body))) offAir("The station is off the air.");
}

// All timeline-derived text goes to the DOM via textContent only.
setInterval(() => {
  if (!playing) return;
  const now = Date.now();
  if (watch.tick(audio.currentTime, now)) probe();
  refreshTimeline(false);
  if (watch.stalled(now)) {
    nowPlaying.textContent = "Reconnecting…";
    return;
  }
  const at = playbackDateMs();
  if (at !== null) nowPlaying.textContent = nowPlayingText(findNowPlaying(timeline, at), timeline !== null);
}, 1000);
```

- [ ] **Step 4: Run the tests and the type check**

Run: `cd antenna && npm test && npx tsc --noEmit`
Expected: PASS; no type errors.

- [ ] **Step 5: Commit**

```bash
git add antenna/public/nowplaying.js antenna/public/player.js antenna/test/nowplaying.test.ts
git commit -m "feat(antenna): an already-playing page notices the kill switch (stall watch + probe), ignoring blips"
```

---
### Task 12: `transmitter offair` and `transmitter budget`

**Model hint:** opus (the takedown lever and the spend-trip clearance)

**Files:**
- Create: `packages/transmitter/src/transmitter/cloudstate.py`, `packages/transmitter/tests_transmitter/test_cloudstate.py`
- Modify: `packages/transmitter/src/transmitter/errors.py`, `packages/transmitter/src/transmitter/cli.py`

**Interfaces:**
- Consumes:
  - `state/guard.json` as the guard writes it (Task 4's `GuardDoc`): `tripped`, `reason`, `tripped_at`, `period.{start,end}`, `evaluation.{at, actual_usd, projected_usd, budget_usd}`, `last_error`, `last_success`, `since` and `waf.{enabled, error}`.
  - The clock's raise cap (`MAX_BUDGET_USD = 100`).
- Produces:
  - `errors.CloudStateError(TransmitterError)`.
  - `cloudstate`: `OFFAIR_KEY`, `BUDGET_KEY`, `GUARD_KEY`, `ALERTS_KEY`, `MAX_RAISE_USD = 100.0`; `get_json(client, bucket, key) -> dict | None`; `put_state(client, bucket, key, doc, *, attempts=3, sleep=time.sleep)`; `set_offair(client, bucket, on, reason, until, now_us) -> dict`; `guard_period_end_us(guard)`; `current_budget_usd(guard)`; `raise_budget(client, bucket, usd, now_us) -> dict`; `guard_summary(guard | None) -> list[str]`.
  - CLI: `transmitter offair on --reason TEXT [--until ISO]`, `transmitter offair off [--reason TEXT]`, `transmitter budget [--raise-to USD]`; helper `cli._cloud(config) -> (client, bucket)` (Task 16 reuses it).

Ruling R7: these writes bypass the publish lock, the guard check and the daily PUT budget. A test pins that `offair on` works while the guard is tripped and the PUT budget is spent. The JSON is written `no-store`.

`raise_budget`:
- refuses without a `guard.json`, without a period or evaluation, or after the period has ended;
- refuses a value at or below the budget the guard uses now, or above $100;
- writes `{budget_usd, expires: <the guard's period end>, written_at}`.

- [ ] **Step 1: Write the failing test**

`packages/transmitter/tests_transmitter/test_cloudstate.py`:

```python
import json

import pytest
from typer.testing import CliRunner

from tests_transmitter.helpers import FakeBucket
from transmitter import cloudstate, grid, service
from transmitter.cli import app
from transmitter.errors import CloudStateError

NOW = grid.iso_to_us("2026-10-20T12:00:00Z")
GUARD = {"schema": 1, "tripped": True, "reason": "spend", "tripped_at": "2026-10-20T11:00:00.000Z",
         "period": {"start": "2026-10-11T00:00:00.000Z", "end": "2026-11-11T00:00:00.000Z"},
         "evaluation": {"at": "2026-10-20T11:45:00.000Z", "actual_usd": 14.0, "projected_usd": 14.0,
                        "budget_usd": 15}, "last_error": None, "waf": {"enabled": True, "error": None}}


def _seed(bucket, key, doc):
    bucket.objects[key] = {"Body": json.dumps(doc).encode(), "ContentType": "application/json", "CacheControl": "no-store"}


def test_offair_on_and_off_write_the_flag_uncached():
    b = FakeBucket()
    doc = cloudstate.set_offair(b, "b", True, "objection received", "2026-10-21T00:00:00Z", NOW)
    assert b.json("state/offair.json") == doc == {"offair": True, "reason": "objection received",
                                                    "since": "2026-10-20T12:00:00.000Z",
                                                    "until": "2026-10-21T00:00:00.000Z"}
    assert b.objects["state/offair.json"]["CacheControl"] == "no-store"
    cloudstate.set_offair(b, "b", False, "back", None, NOW + 1)
    assert b.json("state/offair.json")["offair"] is False


def test_offair_needs_a_reason_and_a_valid_until():
    with pytest.raises(CloudStateError, match="reason"):
        cloudstate.set_offair(FakeBucket(), "b", True, "  ", None, NOW)
    with pytest.raises(CloudStateError, match="ISO-8601"):
        cloudstate.set_offair(FakeBucket(), "b", True, "x", "tomorrow", NOW)


def test_writes_retry_then_fail_loudly():
    b = FakeBucket()
    b.fail_puts["state/offair.json"] = 2
    cloudstate.put_state(b, "b", "state/offair.json", {"offair": True}, sleep=lambda s: None)
    assert b.json("state/offair.json") == {"offair": True}
    b.fail_puts["state/offair.json"] = 5
    with pytest.raises(CloudStateError, match="after 3 attempts"):
        cloudstate.put_state(b, "b", "state/offair.json", {"offair": False}, sleep=lambda s: None)


def test_raise_writes_the_budget_until_the_guards_period_end():
    b = FakeBucket()
    _seed(b, "state/guard.json", GUARD)
    doc = cloudstate.raise_budget(b, "b", 20, NOW)
    assert doc == {"budget_usd": 20, "expires": "2026-11-11T00:00:00.000Z", "written_at": "2026-10-20T12:00:00.000Z"}
    assert b.json("state/budget.json") == doc


@pytest.mark.parametrize("usd, match", [(15, "above the budget"), (10, "above the budget"),
                                        (float("nan"), "above the budget"), (101, "capped")])
def test_raise_must_raise_and_stay_under_the_cap(usd, match):
    b = FakeBucket()
    _seed(b, "state/guard.json", GUARD)
    with pytest.raises(CloudStateError, match=match):
        cloudstate.raise_budget(b, "b", usd, NOW)
    assert "state/budget.json" not in b.objects


def test_raise_refuses_without_a_guard_state_period_or_evaluation():
    with pytest.raises(CloudStateError, match="has not run"):
        cloudstate.raise_budget(FakeBucket(), "b", 20, NOW)
    b = FakeBucket()
    _seed(b, "state/guard.json", {**GUARD, "period": None})
    with pytest.raises(CloudStateError, match="billing period"):
        cloudstate.raise_budget(b, "b", 20, NOW)
    _seed(b, "state/guard.json", {**GUARD, "evaluation": None})
    with pytest.raises(CloudStateError, match="no evaluation"):
        cloudstate.raise_budget(b, "b", 20, NOW)
    _seed(b, "state/guard.json", GUARD)
    with pytest.raises(CloudStateError, match="period ended"):
        cloudstate.raise_budget(b, "b", 20, grid.iso_to_us("2026-11-12T00:00:00Z"))


def test_get_json_absent_corrupt_and_unreachable():
    b = FakeBucket()
    assert cloudstate.get_json(b, "b", "state/guard.json") is None
    b.objects["state/guard.json"] = {"Body": b"{nope", "ContentType": "x", "CacheControl": "x"}
    with pytest.raises(CloudStateError, match="not JSON"):
        cloudstate.get_json(b, "b", "state/guard.json")
    b.fail_gets.add("state/guard.json")
    with pytest.raises(CloudStateError, match="cannot read"):
        cloudstate.get_json(b, "b", "state/guard.json")


def test_guard_summary_lines():
    lines = cloudstate.guard_summary(GUARD)
    assert lines[0].startswith("guard      TRIPPED (spend)")
    assert "actual $14.00, projected $14.00 of $15.00" in lines[1]
    assert lines[-1] == "killswitch enabled"
    assert cloudstate.guard_summary(None)[0].startswith("guard      no state/guard.json")


def _cli(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSMITTER_ROOT", str(tmp_path / "tx"))
    bucket = FakeBucket()
    monkeypatch.setattr(service, "make_client", lambda cfg: bucket)
    monkeypatch.setattr(service, "now_us", lambda: NOW)
    cfgp = tmp_path / "c.toml"
    cfgp.write_text('[publish]\nbucket = "b"\n')
    return bucket, cfgp


def test_cli_offair_on_off_and_budget(tmp_path, monkeypatch):
    bucket, cfgp = _cli(tmp_path, monkeypatch)
    r = CliRunner().invoke(app, ["offair", "on", "--reason", "maintenance", "--config", str(cfgp)])
    assert r.exit_code == 0, r.output
    assert "within about a minute" in r.output and bucket.json("state/offair.json")["offair"] is True
    _seed(bucket, "state/guard.json", GUARD)
    r = CliRunner().invoke(app, ["offair", "off", "--config", str(cfgp)])
    assert r.exit_code == 0 and bucket.json("state/offair.json")["offair"] is False
    assert "cost guard is tripped" in r.output
    r = CliRunner().invoke(app, ["budget", "--config", str(cfgp)])
    assert r.exit_code == 0 and "TRIPPED (spend)" in r.output
    r = CliRunner().invoke(app, ["budget", "--raise-to", "20", "--config", str(cfgp)])
    assert r.exit_code == 0 and bucket.json("state/budget.json")["budget_usd"] == 20
    r = CliRunner().invoke(app, ["budget", "--config", str(cfgp)])
    assert "raise      $20.00 until 2026-11-11T00:00:00.000Z" in r.output


def test_cli_offair_on_requires_a_reason_and_works_while_tripped_and_over_the_put_budget(tmp_path, monkeypatch):
    bucket, cfgp = _cli(tmp_path, monkeypatch)
    assert CliRunner().invoke(app, ["offair", "on", "--config", str(cfgp)]).exit_code != 0
    _seed(bucket, "state/guard.json", GUARD)                     # tripped: publishing is stopped
    (tmp_path / "tx").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tx" / "puts.json").write_text('{"day": "2026-10-20", "count": 999999}')
    r = CliRunner().invoke(app, ["offair", "on", "--reason", "x", "--config", str(cfgp)])
    assert r.exit_code == 0, r.output
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_cloudstate.py -q`
Expected: FAIL. `cannot import name 'cloudstate'`.

- [ ] **Step 3: Implement**

Append to `packages/transmitter/src/transmitter/errors.py`:

```python


class CloudStateError(TransmitterError):
    """An operator command could not read or write the station's cloud state
    (state/offair.json, state/budget.json, state/guard.json)."""
```

`packages/transmitter/src/transmitter/cloudstate.py`:

```python
"""The operator's levers in the cloud (spec "Blocking"): state/offair.json,
written by `transmitter offair on|off`, and state/budget.json, written by
`transmitter budget --raise-to`; plus read-only access to the clock's
state/guard.json and state/alerts.json for `budget` and `status`.

These writes must work while the cost guard is tripped and whatever the daily
PUT budget says -- they are how the operator takes the station off the air or
clears a spend trip -- so they bypass the publish lock, the guard check and the
PUT budget. Each is one small PUT made by hand. The guard never writes
offair.json; `offair off` clears only the operator's flag."""

import json
import math
import time
from typing import Any, Callable

from transmitter import grid
from transmitter.errors import CloudStateError

OFFAIR_KEY = "state/offair.json"
BUDGET_KEY = "state/budget.json"
GUARD_KEY = "state/guard.json"
ALERTS_KEY = "state/alerts.json"
JSON_TYPE = "application/json"
STATE_CACHE = "no-store"
# antenna's MAX_BUDGET_USD: the clock never honours a raise above it.
MAX_RAISE_USD = 100.0


def _code(exc: Exception) -> str | None:
    response = getattr(exc, "response", None)
    return response.get("Error", {}).get("Code") if isinstance(response, dict) else None


def get_json(client: Any, bucket: str, key: str) -> dict | None:
    """The object as a dict; None when absent. Anything else is a CloudStateError."""
    try:
        resp = client.get_object(Bucket=bucket, Key=key)
    except Exception as exc:
        if _code(exc) in ("NoSuchKey", "404"):
            return None
        raise CloudStateError(f"cannot read {key}: {exc}") from exc
    try:
        doc = json.loads(resp["Body"].read())
    except ValueError as exc:
        raise CloudStateError(f"{key} is not JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise CloudStateError(f"{key} is not a JSON object")
    return doc


def put_state(client: Any, bucket: str, key: str, doc: dict, *, attempts: int = 3,
              sleep: Callable[[float], None] = time.sleep) -> None:
    body = (json.dumps(doc, sort_keys=True) + "\n").encode()
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            resp = client.put_object(Bucket=bucket, Key=key, Body=body, ContentType=JSON_TYPE,
                                     CacheControl=STATE_CACHE)
            if resp.get("ResponseMetadata", {}).get("HTTPStatusCode") == 200:
                return
            last = CloudStateError(f"PUT {key}: HTTP {resp.get('ResponseMetadata', {}).get('HTTPStatusCode')}")
        except Exception as exc:
            last = exc
        if attempt + 1 < attempts:
            sleep(2.0 ** attempt)
    raise CloudStateError(f"could not write {key} after {attempts} attempts: {last}") from last


def _iso_or_none(value: str | None, what: str) -> str | None:
    if value is None:
        return None
    try:
        return grid.us_to_iso(grid.iso_to_us(value))
    except ValueError as exc:
        raise CloudStateError(f"{what} must be an ISO-8601 UTC time like 2026-10-20T18:00:00Z: {value!r}") from exc


def set_offair(client: Any, bucket: str, on: bool, reason: str, until: str | None, now_us: int) -> dict:
    """Write the operator's flag. `until` is informational: the flag stays
    until `offair off` (nothing clears it automatically)."""
    if not reason.strip():
        raise CloudStateError("give a --reason (it is shown in `transmitter status`)")
    doc = {"offair": on, "reason": reason.strip(), "since": grid.us_to_iso(now_us),
           "until": _iso_or_none(until, "--until") if on else None}
    put_state(client, bucket, OFFAIR_KEY, doc)
    return doc


def guard_period_end_us(guard: dict) -> int:
    try:
        return grid.iso_to_us(guard["period"]["end"])
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise CloudStateError("state/guard.json has no billing period yet: wait for the guard's first "
                              "successful evaluation (within 15 minutes of deploying antenna)") from exc


def current_budget_usd(guard: dict) -> float:
    evaluation = guard.get("evaluation") or {}
    value = evaluation.get("budget_usd")
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        raise CloudStateError("state/guard.json has no evaluation yet: wait for the guard's first successful "
                              "evaluation")
    return float(value)


def raise_budget(client: Any, bucket: str, usd: float, now_us: int) -> dict:
    """Write state/budget.json {budget_usd, expires: the guard's period end,
    written_at}. It must raise the budget the guard uses now, and stays at or
    under MAX_RAISE_USD. The guard evaluates at its next run (a raise newer than
    its last evaluation triggers one) and clears a spend trip only if that
    evaluation is under the thresholds."""
    guard = get_json(client, bucket, GUARD_KEY)
    if guard is None:
        raise CloudStateError("no state/guard.json: the cost guard has not run yet (is antenna deployed?)")
    end_us = guard_period_end_us(guard)
    if end_us <= now_us:
        raise CloudStateError(f"state/guard.json's billing period ended at {grid.us_to_iso(end_us)}; wait for "
                              "the guard to evaluate the new period")
    current = current_budget_usd(guard)
    if not math.isfinite(usd) or usd <= current:
        raise CloudStateError(f"--raise-to must be above the budget the guard uses now (${current:.2f})")
    if usd > MAX_RAISE_USD:
        raise CloudStateError(f"--raise-to is capped at ${MAX_RAISE_USD:.0f} (the clock ignores more); the "
                              "station's policy is to shut down, not to keep raising")
    doc = {"budget_usd": round(usd, 2), "expires": grid.us_to_iso(end_us), "written_at": grid.us_to_iso(now_us)}
    put_state(client, bucket, BUDGET_KEY, doc)
    return doc


def guard_summary(guard: dict | None) -> list[str]:
    """Human lines for `budget` and `status`."""
    if guard is None:
        return ["guard      no state/guard.json yet (antenna not deployed, or not run)"]
    lines = []
    if guard.get("tripped"):
        lines.append(f"guard      TRIPPED ({guard.get('reason')}) since {guard.get('tripped_at')}")
    else:
        lines.append("guard      not tripped")
    ev = guard.get("evaluation")
    if isinstance(ev, dict):
        lines.append(f"spend      actual ${ev.get('actual_usd', 0):.2f}, projected ${ev.get('projected_usd', 0):.2f} "
                     f"of ${ev.get('budget_usd', 0):.2f} (evaluated {ev.get('at')})")
    period = guard.get("period") or {}
    if period:
        lines.append(f"period     {period.get('start')} .. {period.get('end')}")
    if guard.get("last_error"):
        lines.append(f"reading    failing since {guard.get('last_success') or guard.get('since')}: "
                     f"{guard.get('last_error')}")
    waf = guard.get("waf") or {}
    state = {True: "enabled", False: "disabled", None: "unknown"}.get(waf.get("enabled"), "unknown")
    lines.append(f"killswitch {state}" + (f" (error: {waf['error']})" if waf.get("error") else ""))
    return lines
```

In `cli.py`, change `from transmitter import aacenc, fallback, grid, pipeline, service` to `from transmitter import aacenc, cloudstate, fallback, grid, pipeline, service`. Then insert after `app.add_typer(fallback_app, name="fallback")`:

```python

offair_app = typer.Typer(help="Take the station off the air (state/offair.json), or put it back",
                         pretty_exceptions_enable=False, no_args_is_help=True)
app.add_typer(offair_app, name="offair")


def _cloud(config: Path | None):
    """(client, bucket) for the operator commands: R2 keys from the environment."""
    from transmitter.errors import ConfigError

    cfg = load_config(config)
    if not cfg.publish.bucket:
        raise ConfigError("set [publish] bucket in transmitter's config.toml")
    return service.make_client(cfg), cfg.publish.bucket


@offair_app.command("on")
def offair_on(
    reason: str = typer.Option(..., "--reason", help="Why (shown in `transmitter status`)"),
    until: str = typer.Option(None, "--until", help="Expected end, ISO-8601 UTC (informational only)"),
    config: Path = CONFIG_OPT,
):
    """Off the air: within about a minute the clock lists the off-air notice and
    ENDLIST, index.html becomes the off-air page and the WAF kill switch is on."""
    client, bucket = _cloud(config)
    doc = cloudstate.set_offair(client, bucket, True, reason, until, service.now_us())
    typer.echo(f"state/offair.json: off the air since {doc['since']} ({doc['reason']}). The clock blocks the "
               "station within about a minute: the off-air playlist and page, and the kill switch.")


@offair_app.command("off")
def offair_off(
    reason: str = typer.Option("back on air", "--reason", help="Why (shown in `transmitter status`)"),
    config: Path = CONFIG_OPT,
):
    """Back on the air (clears only the operator's flag; a tripped cost guard keeps the station blocked)."""
    client, bucket = _cloud(config)
    doc = cloudstate.set_offair(client, bucket, False, reason, None, service.now_us())
    typer.echo(f"state/offair.json: on the air since {doc['since']}.")
    guard = cloudstate.get_json(client, bucket, cloudstate.GUARD_KEY)
    if guard and guard.get("tripped"):
        typer.echo(f"note: the cost guard is tripped ({guard.get('reason')}); the station stays blocked until it "
                   "clears (see `transmitter budget`).", err=True)


@app.command()
def budget(
    raise_to: float = typer.Option(None, "--raise-to", help="Raise this billing period's budget to USD"),
    config: Path = CONFIG_OPT,
):
    """Show the cost guard's state, or raise the budget for the rest of this billing period."""
    client, bucket = _cloud(config)
    if raise_to is not None:
        doc = cloudstate.raise_budget(client, bucket, raise_to, service.now_us())
        typer.echo(f"state/budget.json: ${doc['budget_usd']:.2f} until {doc['expires']}. The guard evaluates at its "
                   "next run; a spend trip clears only if that evaluation is under the thresholds.")
        return
    for line in cloudstate.guard_summary(cloudstate.get_json(client, bucket, cloudstate.GUARD_KEY)):
        typer.echo(line)
    raised = cloudstate.get_json(client, bucket, cloudstate.BUDGET_KEY)
    if raised:
        typer.echo(f"raise      ${float(raised.get('budget_usd', 0)):.2f} until {raised.get('expires')}")
```

- [ ] **Step 4: Run the transmitter suite on both Pythons**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q && ./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter/src/transmitter/cloudstate.py packages/transmitter/src/transmitter/errors.py packages/transmitter/src/transmitter/cli.py packages/transmitter/tests_transmitter/test_cloudstate.py
git commit -m "feat(transmitter): offair on|off and budget --raise-to write the station's cloud state"
```

---

### Task 13: hugo alerts — SMTP + ntfy, dedupe

**Model hint:** sonnet

**Files:**
- Modify: `packages/transmitter/src/transmitter/alerts.py` (replace the whole file), `config.py` (`[alerts]`), `workspace.py` (`alerts_path`), `service.py` (`_step`), `cli.py` (`run`)
- Create: `packages/transmitter/tests_transmitter/test_alerts.py`
- Modify (tests): `test_config.py` (append), `test_service.py` (two assertions)

**Interfaces:**
- Consumes: `TransmitterConfig`, `Workspace`.
- Produces:
  - `alerts`:
    - `alert(code, message)` keeps its signature and every call site;
    - `resolve(code)`, `configure(dispatcher | None)`, `dispatcher_from_config(cfg, ws, env=os.environ)`;
    - classes `Dispatcher(path, channels, repeat_s, station="llama radio", now=time.time)` with `fire`, `resolve` and `active() -> list[str]`; `SmtpChannel(host, port, username, password, sender, to)`; `NtfyChannel(url, token=None)`;
    - `LEVEL_CODES` (the codes R16 resolves explicitly) and `active_codes(state, now, repeat_s) -> list[str]`: a level code is active until it is resolved, any other (event) code until `repeat_s` passes without a new fire. `Dispatcher.active()` and `status` (Task 16) both use it.
  - `config.AlertsConfig`: `email_to`, `email_from`, `smtp_host = "smtp.gmail.com"`, `smtp_port = 587`, `ntfy_url`, `repeat_hours = 6.0`, `dead_clock_seconds = 120.0` (ge 31), `guard_stale_minutes = 45.0`. `TransmitterConfig.alerts`, and a `TransmitterConfig` validator: `guard_stale_minutes` ≥ `[publish] guard_check_minutes + 16` (ruling R4).
  - `Workspace.alerts_path` (`<root>/alerts.json`).
  - `Runner._step(name, fn, *, resolves=())`. A `StationRootError` in any step alerts under the code `station-root`. A successful plan step resolves `plan` and `station-root`; a successful render step resolves `render`.

Secrets come from the env file: `SMTP_USERNAME`, `SMTP_PASSWORD` (a Gmail App Password) and `NTFY_TOKEN`. Dedupe follows ruling R16. Without channels the dispatcher only logs. Only `transmitter run` configures the dispatcher, so manual commands keep logging only.

- [ ] **Step 1: Write the failing tests**

`packages/transmitter/tests_transmitter/test_alerts.py`:

```python
import logging

import pytest

from transmitter import alerts
from transmitter.alerts import Dispatcher, NtfyChannel, SmtpChannel, dispatcher_from_config
from transmitter.config import TransmitterConfig
from transmitter.workspace import Workspace, read_json

H = 3600.0


class Recorder:
    name = "rec"

    def __init__(self, fail: bool = False):
        self.sent: list[tuple[str, str, int]] = []
        self.fail = fail

    def send(self, subject, body, priority):
        if self.fail:
            raise OSError("down")
        self.sent.append((subject, body, priority))


@pytest.fixture(autouse=True)
def _unconfigure():
    yield
    alerts.configure(None)


def _dispatcher(tmp_path, *channels, now=None):
    clock = {"t": 1000.0}
    d = Dispatcher(tmp_path / "alerts.json", list(channels), 6 * H, "llama radio", now=lambda: clock["t"])
    return d, clock


def test_unconfigured_alerts_only_log(caplog):
    with caplog.at_level(logging.ERROR, logger="transmitter.alerts"):
        alerts.alert("render", "boom")
    assert "ALERT render: boom" in caplog.text


def test_first_occurrence_is_sent_then_deduped_until_the_repeat_window(tmp_path):
    rec = Recorder()
    d, clock = _dispatcher(tmp_path, rec)
    alerts.configure(d)
    alerts.alert("publish", "PUT failed")
    clock["t"] += 60
    alerts.alert("publish", "PUT failed again")
    assert [s[0] for s in rec.sent] == ["llama radio: publish"]
    clock["t"] += 6 * H
    alerts.alert("publish", "still failing")
    assert len(rec.sent) == 2
    assert "(1 more since the last message)" in rec.sent[1][1]
    assert read_json(tmp_path / "alerts.json")["publish"]["active"] is True


def test_resolve_says_so_and_rearms_the_code(tmp_path):
    rec = Recorder()
    d, clock = _dispatcher(tmp_path, rec)
    alerts.configure(d)
    alerts.alert("dead-clock", "stale")
    alerts.resolve("dead-clock")
    assert rec.sent[-1][0] == "llama radio: resolved: dead-clock" and rec.sent[-1][2] == 3
    clock["t"] += 60
    alerts.alert("dead-clock", "stale again")                 # sent at once, not after 6 h
    assert [s[0] for s in rec.sent].count("llama radio: dead-clock") == 2
    alerts.resolve("never-fired")                             # a no-op
    assert d.active() == ["dead-clock"]


def test_an_event_code_stops_counting_as_active_after_the_repeat_window(tmp_path):
    rec = Recorder()
    d, clock = _dispatcher(tmp_path, rec)
    alerts.configure(d)
    alerts.alert("publish", "PUT failed")
    alerts.alert("dead-clock", "stale")
    assert d.active() == ["dead-clock", "publish"]
    clock["t"] += 6 * H + 1
    assert d.active() == ["dead-clock"]                       # a level code stays until resolved
    alerts.alert("publish", "PUT failed again")               # a new occurrence: sent at once
    assert d.active() == ["dead-clock", "publish"] and len(rec.sent) == 3


def test_a_failing_channel_never_raises_and_the_next_occurrence_retries(tmp_path, caplog):
    broken, ok = Recorder(fail=True), Recorder()
    d, clock = _dispatcher(tmp_path, broken)
    alerts.configure(d)
    with caplog.at_level(logging.WARNING, logger="transmitter.alerts"):
        alerts.alert("render", "x")
    assert "alert channel rec failed" in caplog.text
    d.channels = [broken, ok]
    clock["t"] += 60
    alerts.alert("render", "x")
    assert len(ok.sent) == 1


def test_dispatcher_from_config_builds_the_configured_channels(tmp_path, caplog):
    cfg = TransmitterConfig(root=tmp_path, alerts={"email_to": "ops@example.com", "ntfy_url": "https://ntfy.example/t"})
    d = dispatcher_from_config(cfg, Workspace(tmp_path), env={"SMTP_USERNAME": "u@example.com", "SMTP_PASSWORD": "pw",
                                                              "NTFY_TOKEN": "tk_x"})
    smtp, ntfy = d.channels
    assert isinstance(smtp, SmtpChannel) and (smtp.host, smtp.port, smtp.sender, smtp.to) == (
        "smtp.gmail.com", 587, "u@example.com", "ops@example.com")
    assert isinstance(ntfy, NtfyChannel) and ntfy.token == "tk_x"
    assert d.repeat_s == 6 * H and d.path == tmp_path / "alerts.json"
    with caplog.at_level(logging.WARNING, logger="transmitter.alerts"):
        d = dispatcher_from_config(cfg, Workspace(tmp_path), env={})
    assert [c.name for c in d.channels] == ["ntfy"] and "email alerts are off" in caplog.text


def test_smtp_channel_uses_starttls_and_login(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, context):
            calls.append(("starttls",))

        def login(self, user, password):
            calls.append(("login", user, password))

        def send_message(self, msg):
            calls.append(("send", msg["From"], msg["To"], msg["Subject"], msg.get_content().strip()))

    monkeypatch.setattr(alerts.smtplib, "SMTP", FakeSMTP)
    SmtpChannel("smtp.gmail.com", 587, "u@example.com", "pw", "u@example.com", "ops@example.com").send("subj", "body", 4)
    assert calls == [("connect", "smtp.gmail.com", 587, 20.0), ("starttls",), ("login", "u@example.com", "pw"),
                     ("send", "u@example.com", "ops@example.com", "subj", "body")]


def test_ntfy_channel_posts_with_headers(monkeypatch):
    seen = {}

    class Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout):
        seen.update(url=req.full_url, method=req.get_method(), headers=dict(req.header_items()), body=req.data,
                    timeout=timeout)
        return Resp()

    monkeypatch.setattr(alerts.urllib.request, "urlopen", fake_urlopen)
    NtfyChannel("https://ntfy.example/t", "tk_1").send("llama radio: dead-clock", "stale", 4)
    assert seen["url"] == "https://ntfy.example/t" and seen["method"] == "POST" and seen["body"] == b"stale"
    assert seen["headers"]["Title"] == "llama radio: dead-clock"
    assert seen["headers"]["Priority"] == "4" and seen["headers"]["Authorization"] == "Bearer tk_1"
```

Append to `tests_transmitter/test_config.py`:

```python
def test_alerts_defaults_and_floors(tmp_path):
    from transmitter.config import AlertsConfig

    a = AlertsConfig()
    assert (a.smtp_host, a.smtp_port, a.repeat_hours, a.dead_clock_seconds, a.guard_stale_minutes) == \
        ("smtp.gmail.com", 587, 6.0, 120.0, 45.0)
    assert a.email_to is None and a.ntfy_url is None
    path = tmp_path / "c.toml"
    for bad in ('[alerts]\ndead_clock_seconds = 30\n', '[alerts]\nguard_stale_minutes = 30\n',
                '[publish]\nguard_check_minutes = 30\n',          # 30 + 16 is above the default 45
                '[alerts]\nsmtp_password = "x"\n'):
        path.write_text(bad)
        with pytest.raises(ConfigError):
            load_config(path)
    path.write_text('[publish]\nguard_check_minutes = 5\n[alerts]\nguard_stale_minutes = 21\n')
    assert load_config(path).alerts.guard_stale_minutes == 21
```

In `tests_transmitter/test_service.py`, make two changes:

1. In `test_runner_alerts_and_keeps_publishing_when_planning_fails`, change `assert "ALERT plan" in caplog.text and ".station-root" in caplog.text` to `assert "ALERT station-root" in caplog.text and ".station-root" in caplog.text`.
2. In `test_plan_errors_alert_and_the_loop_continues`, replace the line `assert f"ALERT plan: {type(exc).__name__}: {exc}" in caplog.text` with:

```python
    code = "station-root" if isinstance(exc, StationRootError) else "plan"
    assert f"ALERT {code}: {type(exc).__name__}: {exc}" in caplog.text
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_alerts.py packages/transmitter/tests_transmitter/test_config.py packages/transmitter/tests_transmitter/test_service.py -q`
Expected: FAIL. `cannot import name 'Dispatcher'`, `AlertsConfig` is unknown, and the `ALERT station-root` assertion fails.

- [ ] **Step 3: Implement**

Replace `packages/transmitter/src/transmitter/alerts.py` with:

```python
"""Hugo-side alerts (spec "Alerts and operations"). Every alert is logged at
ERROR (journald under systemd). Once `configure()` has installed a
Dispatcher -- `transmitter run` does it at start -- each alert is also sent by
email (SMTP with STARTTLS) and ntfy, deduped per code in
~/.transmitter/alerts.json: sent when a code first fires, then at most once
per `repeat_hours` while it keeps firing. `resolve(code)` marks a level
condition clear (and says so, if it had been sent) so that its next occurrence
is sent at once. Any other code is an event: it stops counting as active once
`repeat_hours` pass without a new fire, so `status` shows no stale alarms. A
failing channel is logged, never raised: alerting must not take the service
down."""

import logging
import os
import smtplib
import ssl
import time
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Callable, Mapping, Protocol

from transmitter.workspace import Workspace, read_json, write_json

log = logging.getLogger("transmitter.alerts")

# Level conditions, resolved explicitly (ruling R16). Every other code is an
# event: active only until `repeat_hours` pass without a new fire.
LEVEL_CODES = frozenset({"dead-clock", "guard-stale", "station-root", "plan", "render"})


def _expired(code: str, entry: dict, now: float, repeat_s: float) -> bool:
    """An event code that has not fired for longer than `repeat_s`."""
    last = entry.get("last_fired_at", entry.get("first_at"))
    return code not in LEVEL_CODES and (not isinstance(last, (int, float)) or now - last > repeat_s)


def active_codes(state: dict, now: float, repeat_s: float) -> list[str]:
    """The codes still alarming (what `status` lists): a level code until it is
    resolved, an event code until `repeat_s` passes without a new fire."""
    return sorted(code for code, e in state.items()
                  if isinstance(e, dict) and e.get("active") and not _expired(code, e, now, repeat_s))


class Channel(Protocol):
    name: str

    def send(self, subject: str, body: str, priority: int) -> None: ...


@dataclass
class SmtpChannel:
    host: str
    port: int
    username: str
    password: str
    sender: str
    to: str
    timeout_s: float = 20.0
    name: str = "email"

    def send(self, subject: str, body: str, priority: int) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.sender, self.to, subject
        msg.set_content(body)
        with smtplib.SMTP(self.host, self.port, timeout=self.timeout_s) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(self.username, self.password)
            smtp.send_message(msg)


@dataclass
class NtfyChannel:
    url: str
    token: str | None = None
    timeout_s: float = 10.0
    name: str = "ntfy"

    def send(self, subject: str, body: str, priority: int) -> None:
        headers = {"Title": subject, "Priority": str(priority), "Tags": "warning" if priority >= 4 else "white_check_mark"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(self.url, data=body.encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            if resp.status >= 300:
                raise OSError(f"ntfy: HTTP {resp.status}")


@dataclass
class Dispatcher:
    path: Path                         # ~/.transmitter/alerts.json
    channels: list
    repeat_s: float
    station: str = "llama radio"
    now: Callable[[], float] = time.time

    def _load(self) -> dict:
        data = read_json(self.path, {})
        return data if isinstance(data, dict) else {}

    def _send(self, subject: str, body: str, priority: int) -> bool:
        delivered = False
        for ch in self.channels:
            try:
                ch.send(subject, body, priority)
                delivered = True
            except Exception as exc:              # never let alerting break the service
                log.warning("alert channel %s failed: %s", ch.name, exc)
        return delivered

    def fire(self, code: str, message: str) -> None:
        state = self._load()
        now = self.now()
        entry = state.get(code) or {"active": False, "first_at": now, "last_sent_at": None, "count": 0}
        if not entry.get("active") or _expired(code, entry, now, self.repeat_s):
            entry.update(active=True, first_at=now, last_sent_at=None, count=0)
        entry["count"] = int(entry.get("count", 0)) + 1
        entry["last_fired_at"] = now
        last = entry.get("last_sent_at")
        if self.channels and (last is None or now - last >= self.repeat_s):
            suppressed = entry["count"] - 1
            body = message + (f"\n\n({suppressed} more since the last message)" if last and suppressed else "")
            if self._send(f"{self.station}: {code}", body, 4):
                entry["last_sent_at"], entry["count"] = now, 0
        state[code] = entry
        write_json(self.path, state)

    def resolve(self, code: str) -> None:
        state = self._load()
        entry = state.get(code)
        if not entry or not entry.get("active"):
            return
        if entry.get("last_sent_at") is not None:
            self._send(f"{self.station}: resolved: {code}", f"{code} has cleared.", 3)
        entry["active"] = False
        state[code] = entry
        write_json(self.path, state)

    def active(self) -> list[str]:
        return active_codes(self._load(), self.now(), self.repeat_s)


_dispatcher: Dispatcher | None = None


def configure(dispatcher: Dispatcher | None) -> None:
    global _dispatcher
    _dispatcher = dispatcher


def alert(code: str, message: str) -> None:
    log.error("ALERT %s: %s", code, message)
    if _dispatcher is not None:
        try:
            _dispatcher.fire(code, message)
        except Exception:
            log.warning("alert dispatch failed for %s", code, exc_info=True)


def resolve(code: str) -> None:
    if _dispatcher is not None:
        try:
            _dispatcher.resolve(code)
        except Exception:
            log.warning("alert resolve failed for %s", code, exc_info=True)


def dispatcher_from_config(cfg, ws: Workspace, env: Mapping[str, str] = os.environ) -> Dispatcher:
    """Channels from `[alerts]` and the environment (SMTP_USERNAME,
    SMTP_PASSWORD, NTFY_TOKEN). A half-configured channel is skipped with a
    warning; with no channel the dispatcher only dedupes the log."""
    a = cfg.alerts
    channels: list = []
    if a.email_to:
        user, password = env.get("SMTP_USERNAME"), env.get("SMTP_PASSWORD")
        if user and password:
            channels.append(SmtpChannel(a.smtp_host, a.smtp_port, user, password, a.email_from or user, a.email_to))
        else:
            log.warning("[alerts] email_to is set but SMTP_USERNAME/SMTP_PASSWORD are not: email alerts are off")
    if a.ntfy_url:
        channels.append(NtfyChannel(a.ntfy_url, env.get("NTFY_TOKEN") or None))
    if not channels:
        log.warning("no alert channel configured ([alerts] in config.toml): alerts go to the log only")
    return Dispatcher(ws.alerts_path, channels, a.repeat_hours * 3600, cfg.antenna.station_name)
```

`workspace.py`: add after the `lock_path` property:

```python

    @property
    def alerts_path(self) -> Path:
        return self.root / "alerts.json"
```

`config.py`: add the model before `class AntennaConfig`:

```python
class AlertsConfig(_StrictModel):
    """hugo's alert channels (spec "Alerts and operations"). Secrets come from
    the service's env file: SMTP_USERNAME, SMTP_PASSWORD, NTFY_TOKEN."""
    email_to: str | None = None
    email_from: str | None = None                  # default: SMTP_USERNAME
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = Field(default=587, ge=1, le=65535)
    ntfy_url: str | None = None                    # https://ntfy.sh/<topic>
    repeat_hours: float = Field(default=6.0, gt=0)
    # Dead clock: the public live.m3u8's newest segment older than this, twice
    # in a row. At least 3 d (spec); the default allows the measured cron lags.
    dead_clock_seconds: float = Field(default=120.0, ge=31)
    # Dead guard: state/guard.json last evaluated longer ago than this. hugo
    # sees the evaluation time through a cache refreshed every [publish]
    # guard_check_minutes, and the guard evaluates every 15 minutes plus the
    # cron lag: at least guard_check_minutes + 16 (TransmitterConfig checks).
    guard_stale_minutes: float = Field(default=45.0, gt=0)
```

Then add `alerts: AlertsConfig = Field(default_factory=AlertsConfig)` as the last field of `TransmitterConfig`, followed by this validator (the floor spans two sections, so it lives on `TransmitterConfig`):

```python

    @model_validator(mode="after")
    def _guard_stale_outlasts_the_cache(self):
        floor = self.publish.guard_check_minutes + 16
        if self.alerts.guard_stale_minutes < floor:
            raise ValueError(f"alerts.guard_stale_minutes must be at least publish.guard_check_minutes + 16 ({floor:g}): "
                             "anything shorter alarms while the guard is healthy")
        return self
```

In `DEFAULT_CONFIG_TOML`, replace the `[antenna]` tail:

```
# public base URL, for Open Graph links on show pages
# site_url = "https://radio.example.org"
station_name = "llama radio"
"""
```

with:

```
# public base URL, for Open Graph links on show pages and the dead-clock
# check (which fetches <site_url>/live.m3u8 once a minute; unset = no check)
# site_url = "https://radio.example.org"
station_name = "llama radio"

[alerts]
# Email over SMTP with STARTTLS (credentials from the env file: SMTP_USERNAME,
# SMTP_PASSWORD -- for Gmail an App Password) and ntfy (NTFY_TOKEN, optional).
# With neither, alerts only reach the log (journald).
# email_to = "you@example.com"
# email_from = "station@example.com"      # default: SMTP_USERNAME
smtp_host = "smtp.gmail.com"
smtp_port = 587
# ntfy_url = "https://ntfy.sh/<your-topic>"
# re-send a still-firing alert at most this often
repeat_hours = 6.0
# the public live.m3u8 older than this (twice in a row): the clock is dead
dead_clock_seconds = 120.0
# state/guard.json not evaluated for this long: the guard is dead
# (at least [publish] guard_check_minutes + 16)
guard_stale_minutes = 45.0
"""
```

`service.py`, three edits:

1. Change the errors import to `from transmitter.errors import ConfigError, FrameCountDrift, PublishLocked, StationRootError, TransmitterError`.
2. Replace the head of `Runner._step`, through `fn()`:

```python
    def _step(self, name: str, fn: Callable[[], object]) -> None:
        """Run one step; no error ends the loop (the next tick retries)."""
        try:
            fn()
        except FrameCountDrift as exc:
```

   with:

```python
    def _step(self, name: str, fn: Callable[[], object], *, resolves: tuple[str, ...] = ()) -> None:
        """Run one step; no error ends the loop (the next tick retries). A step
        that succeeds resolves `resolves`."""
        try:
            fn()
            for code in resolves:
                alerts.resolve(code)
        except StationRootError as exc:
            log.error("%s step: %s", name, exc)
            alerts.alert("station-root", f"{type(exc).__name__}: {exc}")
        except FrameCountDrift as exc:
```

3. In `tick`, the fill steps resolve their codes:

```python
        if self.filling:
            self._step("plan", lambda: pipeline.plan_step(self.st, t_us, max_new=1),
                       resolves=("plan", "station-root"))
            self._step("render", lambda: pipeline.render_step(
                self.st, t_us, limit=self.st.cfg.publish.batch_segments), resolves=("render",))
```

`cli.py` `run`: configure the dispatcher for the service's lifetime:

```python
    """The service loop: plan/render below low water, publish and prune every minute."""
    from transmitter import alerts

    cfg = load_config(config)
    t = service.now_us()
    st = service.open_station(cfg, t)
    alerts.configure(alerts.dispatcher_from_config(cfg, st.ws))
    try:
        service.Runner(st, service.open_publisher(st)).run(max_ticks=1 if once else None)
    finally:
        alerts.configure(None)
```

- [ ] **Step 4: Run the transmitter suite on both Pythons**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q && ./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q`
Expected: PASS. Then run `./.venv/bin/transmitter config init --stdout | grep -A3 '\[alerts\]'`. Expected: it prints the commented `[alerts]` section with placeholder addresses only.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): hugo alerts by SMTP (STARTTLS) and ntfy, deduped per code in alerts.json"
```

---

### Task 14: Dead-clock and guard-stale monitor

**Model hint:** sonnet

**Files:**
- Create: `packages/transmitter/src/transmitter/deadclock.py`, `packages/transmitter/tests_transmitter/test_deadclock.py`
- Modify: `publish.py` (`guard_blocks_publishing` caches `guard_evaluated_at` and `offair`), `service.py` (`open_monitor`, `Runner(monitor=…)`), `cli.py` (`run`)
- Modify (tests): `test_publish.py` (one assertion), `test_service.py` (append)

**Interfaces:**
- Consumes: `alerts.alert`/`alerts.resolve` (Task 13); `AlertsConfig.dead_clock_seconds`/`guard_stale_minutes` (Task 13); `[antenna] site_url`; `[publish] guard_check_minutes`.
- Produces:
  - `deadclock`: `playlist_age_s(text, now_us, epoch_us) -> float | None`, `fetch_text(url, timeout_s=10) -> (status, body)` (status 0 = no response), and `@dataclass DeadClockMonitor(url, epoch_us, dead_clock_s, guard_stale_s, forbidden_checks=17, fetch=fetch_text)` with `check(now_us, guard_cache)`. It uses the alert codes `dead-clock` and `guard-stale`.
  - `publish.OFFAIR_KEY`. `guard-cache.json` gains `guard_evaluated_at` and `offair`. These are informational: publishing is still gated on `tripped` only.
  - `service.open_monitor(st) -> DeadClockMonitor | None` and `Runner(..., monitor=None)`. The tick runs the step `dead-clock` after `publish`, passing `read_json(ws.guard_cache_path)`.

Rules (ruling R4):
- **Stale:** 120 s on two consecutive checks.
- **Off-air:** an off-air playlist (no PROGRAM-DATE-TIME) is dated by its MEDIA-SEQUENCE.
- **403:** expected while the guard cache says blocked or off the air; otherwise an alert after `guard_check_minutes + 2` consecutive checks (17). The cache is refreshed only every `guard_check_minutes`, so after `offair on` or a trip it can say "not blocked" for that long, and a shorter threshold would alarm then.
- **Unreachable:** network errors alert after 10 consecutive minutes.
- **Guard stale:** `guard_evaluated_at` older than `guard_stale_minutes` (45; or a readable `guard.json` with none) alerts `guard-stale`.

The fetch hits the public `live.m3u8`: a cache hit (measured 2026-10-12, A5), never billed per request; the edge refetches it from R2 at most every 5 s, whoever asks.

- [ ] **Step 1: Write the failing tests**

`packages/transmitter/tests_transmitter/test_deadclock.py`:

```python
import logging

import pytest

from transmitter import alerts, grid
from transmitter.deadclock import DeadClockMonitor, playlist_age_s

E = grid.iso_to_us("2026-10-10T12:00:00Z")
D = grid.D_US


def live_playlist(cur: int) -> str:
    lines = ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-TARGETDURATION:11", f"#EXT-X-MEDIA-SEQUENCE:{cur - 5}",
             "#EXT-X-DISCONTINUITY-SEQUENCE:0"]
    for n in range(cur - 5, cur + 1):
        lines += [f"#EXT-X-PROGRAM-DATE-TIME:{grid.us_to_iso(E + n * D)}", "#EXTINF:10.240,", f"seg/e1/{n}.aac"]
    return "\n".join(lines) + "\n"


def offair_playlist(seq: int) -> str:
    return (f"#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:11\n#EXT-X-MEDIA-SEQUENCE:{seq}\n"
            "#EXT-X-DISCONTINUITY-SEQUENCE:3\n#EXT-X-DISCONTINUITY\n#EXTINF:10.240,\nfallback/v1/notice.aac\n"
            "#EXT-X-ENDLIST\n")


def test_age_from_the_newest_program_date_time():
    assert playlist_age_s(live_playlist(100), E + 100 * D + 4_000_000, E) == pytest.approx(4.0)


def test_age_of_an_offair_playlist_from_its_media_sequence():
    # The clock numbers it indexAt(scheduledTime + 75 s): ahead of now, so negative while fresh.
    assert playlist_age_s(offair_playlist(107), E + 100 * D, E) < 0
    assert playlist_age_s(offair_playlist(100), E + 120 * D, E) == pytest.approx(20 * 10.24)


def test_age_is_none_without_dates_or_sequence():
    assert playlist_age_s("#EXTM3U\n", E, E) is None
    assert playlist_age_s("<html>", E, E) is None


@pytest.fixture
def fired(monkeypatch):
    events = []
    monkeypatch.setattr(alerts, "alert", lambda code, msg: events.append(("alert", code, msg)))
    monkeypatch.setattr(alerts, "resolve", lambda code: events.append(("resolve", code)))
    return events


FRESH_GUARD = {"blocked": False, "offair": False, "error": None, "guard_evaluated_at": None}


def _monitor(responses):
    it = iter(responses)
    return DeadClockMonitor("https://radio.example.org/live.m3u8", E, 120.0, 2700.0, 17, fetch=lambda url: next(it))


def _guard(now_us, minutes_ago=5, **kw):
    return {**FRESH_GUARD, "guard_evaluated_at": grid.us_to_iso(now_us - minutes_ago * 60_000_000), **kw}


def test_a_fresh_playlist_resolves_and_one_stale_read_is_not_a_death(fired):
    now = E + 1000 * D
    m = _monitor([(200, live_playlist(1000)), (200, live_playlist(990)), (200, live_playlist(1000))])
    m.check(now, _guard(now))
    m.check(now, _guard(now))           # 102 s old... still under 120 s
    m.check(now, _guard(now))
    assert not [e for e in fired if e[0] == "alert"]
    assert ("resolve", "dead-clock") in fired and ("resolve", "guard-stale") in fired


def test_two_stale_reads_in_a_row_alert(fired):
    now = E + 1000 * D
    m = _monitor([(200, live_playlist(985))] * 2)
    m.check(now, _guard(now))
    assert not [e for e in fired if e[0] == "alert"]
    m.check(now, _guard(now))
    assert [e[1] for e in fired if e[0] == "alert"] == ["dead-clock"]


def test_a_403_is_expected_while_blocked_and_alarms_only_once_the_guard_cache_has_caught_up(fired):
    now = E + 1000 * D
    m = _monitor([(403, "")] * 18)
    m.check(now, _guard(now, offair=True))
    assert not [e for e in fired if e[0] == "alert"]
    for _ in range(16):                     # the cache may say "not blocked" for guard_check_minutes after `offair on`
        m.check(now, _guard(now))
    assert not [e for e in fired if e[0] == "alert"]
    m.check(now, _guard(now))
    alerted = [e for e in fired if e[0] == "alert"]
    assert alerted[0][1] == "dead-clock" and "kill switch" in alerted[0][2]


def test_network_errors_alert_only_when_they_persist(fired):
    now = E + 1000 * D
    m = _monitor([(0, "")] * 9 + [(200, live_playlist(1000))] + [(0, "")] * 10)
    for _ in range(10):
        m.check(now, _guard(now))
    assert not [e for e in fired if e[0] == "alert"]
    for _ in range(10):
        m.check(now, _guard(now))
    assert [e[1] for e in fired if e[0] == "alert"] == ["dead-clock"]


def test_a_stale_guard_alerts(fired):
    now = E + 1000 * D
    m = _monitor([(200, live_playlist(1000))] * 2)
    m.check(now, _guard(now, minutes_ago=46))
    assert [e[1] for e in fired if e[0] == "alert"] == ["guard-stale"]
    fired.clear()
    m.check(now, {**FRESH_GUARD})                     # guard.json read fine but carries no evaluation
    assert [e[1] for e in fired if e[0] == "alert"] == ["guard-stale"]
```

Append to `tests_transmitter/test_service.py`:

```python
def test_the_runner_runs_the_dead_clock_check_every_tick_with_the_guard_cache(tmp_path):
    st, _ = make_station(tmp_path)
    calls = []

    class Monitor:
        def check(self, now_us, guard_cache):
            calls.append((now_us, guard_cache))

    runner = service.Runner(st, _publisher(st, FakeBucket()), sleep=lambda s: None, monitor=Monitor())
    runner.tick(NOW)
    runner.tick(NOW + 60_000_000)
    assert [c[0] for c in calls] == [NOW, NOW + 60_000_000]
    assert calls[0][1]["blocked"] is False and calls[0][1]["offair"] is False   # written by publish's guard read


def test_open_monitor_needs_site_url(tmp_path):
    st, _ = make_station(tmp_path)
    assert service.open_monitor(st) is None
    st.cfg.antenna.site_url = "https://radio.example.org/"
    m = service.open_monitor(st)
    assert m.url == "https://radio.example.org/live.m3u8" and m.dead_clock_s == 120.0 and m.guard_stale_s == 2700.0
    assert m.forbidden_checks == 17                     # guard_check_minutes 15 + 2
```

In `tests_transmitter/test_publish.py` `test_tripped_guard_stops_publishing_and_is_read_at_most_every_15_minutes`, the guard read now also reads the flag. Change `assert bucket.log == [("get", "state/guard.json")]` to `assert bucket.log == [("get", "state/guard.json"), ("get", "state/offair.json")]`.

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_deadclock.py packages/transmitter/tests_transmitter/test_service.py packages/transmitter/tests_transmitter/test_publish.py -q`
Expected: FAIL. `No module named 'transmitter.deadclock'`; `Runner` has no `monitor` parameter.

- [ ] **Step 3: Implement**

`packages/transmitter/src/transmitter/deadclock.py`:

```python
"""The dead-clock check (spec "Alerts and operations"). If the antenna clock
stops, live.m3u8 goes stale, players stall and the cloud side fails toward
zero cost -- but silently, so `transmitter run` watches it: once a minute it
fetches the public live.m3u8 (a cache hit: the edge refetches it from R2 at
most every 5 s, whoever asks) and alerts when its newest segment is older than
`dead_clock_seconds` on two checks in a row (the measured cron lag reaches
~60 s, so one stale read is not a death). An off-air playlist has no
PROGRAM-DATE-TIME; its MEDIA-SEQUENCE (a grid index the clock computes per
invocation) dates it instead. A 403 is the kill switch: expected while the
guard says blocked, alarming otherwise -- but only after `forbidden_checks`
checks, because the guard cache that says "blocked" can be one
guard_check_minutes late. It also alerts when state/guard.json's last
evaluation is older than `guard_stale_minutes` (the guard evaluates every 15)."""

import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from transmitter import alerts, grid

PROGRAM_DATE_TIME = "#EXT-X-PROGRAM-DATE-TIME:"
MEDIA_SEQUENCE = "#EXT-X-MEDIA-SEQUENCE:"
STALE_CHECKS = 2           # consecutive stale reads before alerting
TROUBLE_CHECKS = 10        # consecutive unreachable reads before alerting


def playlist_age_s(text: str, now_us: int, epoch_us: int) -> float | None:
    """Seconds since the playlist's newest segment started, or None if it names none."""
    dates = [line[len(PROGRAM_DATE_TIME):].strip() for line in text.splitlines()
             if line.startswith(PROGRAM_DATE_TIME)]
    if dates:
        try:
            return (now_us - max(grid.iso_to_us(d) for d in dates)) / 1e6
        except ValueError:
            return None
    for line in text.splitlines():
        if line.startswith(MEDIA_SEQUENCE):
            try:
                n = int(line[len(MEDIA_SEQUENCE):].strip())
            except ValueError:
                return None
            return (now_us - grid.segment_start_us(epoch_us, n)) / 1e6
    return None


def fetch_text(url: str, timeout_s: float = 10.0) -> tuple[int, str]:
    """(HTTP status, body); status 0 = no response (network error)."""
    req = urllib.request.Request(url, headers={"User-Agent": "transmitter-dead-clock-check"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except (urllib.error.URLError, OSError):
        return 0, ""


@dataclass
class DeadClockMonitor:
    url: str                       # https://<host>/live.m3u8
    epoch_us: int
    dead_clock_s: float
    guard_stale_s: float
    forbidden_checks: int = 17     # unexpected 403s before alerting: guard_check_minutes + 2
    fetch: Callable[[str], tuple[int, str]] = fetch_text
    stale: int = 0
    unreachable: int = 0
    forbidden: int = 0

    def check(self, now_us: int, guard_cache: dict | None) -> None:
        blocked = bool(guard_cache and (guard_cache.get("blocked") or guard_cache.get("offair")))
        status, text = self.fetch(self.url)
        if status == 200:
            self.unreachable = self.forbidden = 0
            age = playlist_age_s(text, now_us, self.epoch_us)
            if age is None or age > self.dead_clock_s:
                self.stale += 1
                if self.stale >= STALE_CHECKS:
                    alerts.alert("dead-clock", f"{self.url} is stale ("
                                 + ("no segment in it" if age is None else f"newest segment {age:.0f} s old")
                                 + "): the antenna clock Worker may have stopped (Workers dashboard, wrangler tail)")
            else:
                self.stale = 0
                alerts.resolve("dead-clock")
        elif status == 403 and blocked:
            self.stale = self.unreachable = self.forbidden = 0
            alerts.resolve("dead-clock")
        elif status == 403:
            # The guard cache is refreshed only every guard_check_minutes, so a
            # fresh `offair on` or trip reads "not blocked" here for that long.
            self.forbidden += 1
            if self.forbidden >= self.forbidden_checks:
                alerts.alert("dead-clock", f"{self.url} answers 403 although the guard says the station is not "
                                           f"blocked (kill switch left on?) for {self.forbidden} minutes")
        else:
            self.unreachable += 1
            if self.unreachable >= TROUBLE_CHECKS:
                alerts.alert("dead-clock", f"{self.url} cannot be fetched (status {status or 'none'}) "
                                           f"for {self.unreachable} minutes")
        self._check_guard(now_us, guard_cache)

    def _check_guard(self, now_us: int, guard_cache: dict | None) -> None:
        at = (guard_cache or {}).get("guard_evaluated_at")
        try:
            age_s = (now_us - grid.iso_to_us(at)) / 1e6 if at else None
        except ValueError:
            age_s = None
        if age_s is None:
            if guard_cache and guard_cache.get("error") is None:
                alerts.alert("guard-stale", "state/guard.json has no evaluation time: is the antenna clock deployed?")
        elif age_s > self.guard_stale_s:
            alerts.alert("guard-stale", f"the cost guard last evaluated {age_s / 60:.0f} minutes ago (at {at}); "
                                        "it should every 15: the antenna clock may have stopped")
        else:
            alerts.resolve("guard-stale")
```

`publish.py`: add `OFFAIR_KEY = "state/offair.json"` after `GUARD_KEY`. In `guard_blocks_publishing`, replace:

```python
    try:
        doc = uploader.get_json(GUARD_KEY)
        blocked, error = bool(doc and doc.get("tripped")), None
    except Exception as exc:                        # cannot see the guard: do not spend
        blocked, error = True, str(exc)
    write_json(ws.guard_cache_path, {"checked_at": now_s, "blocked": blocked, "error": error})
    return blocked
```

with:

```python
    evaluated_at = offair = None
    try:
        doc = uploader.get_json(GUARD_KEY)
        blocked, error = bool(doc and doc.get("tripped")), None
        evaluated_at = doc.get("evaluated_at") if doc else None
    except Exception as exc:                        # cannot see the guard: do not spend
        blocked, error = True, str(exc)
    try:                                            # for the dead-clock check only: never gates publishing
        flag = uploader.get_json(OFFAIR_KEY)
        offair = bool(flag and flag.get("offair") is True)
    except Exception:
        offair = None
    write_json(ws.guard_cache_path, {"checked_at": now_s, "blocked": blocked, "error": error,
                                     "guard_evaluated_at": evaluated_at, "offair": offair})
    return blocked
```

`service.py`, five edits:

1. Add `import math` and `from transmitter.deadclock import DeadClockMonitor`.
2. Extend the workspace import with `read_json`.
3. Add before `class Runner`:

```python
def open_monitor(st: pipeline.Station) -> DeadClockMonitor | None:
    """The dead-clock check, when [antenna] site_url says where live.m3u8 is."""
    url = st.cfg.antenna.site_url
    if not url:
        log.warning("[antenna] site_url is not set: the dead-clock check is off")
        return None
    a = st.cfg.alerts
    # An unexpected 403 must outlast the guard cache (refreshed every
    # guard_check_minutes) before it alarms.
    return DeadClockMonitor(url.rstrip("/") + "/live.m3u8", st.epoch.epoch_us, a.dead_clock_seconds,
                            a.guard_stale_minutes * 60, math.ceil(st.cfg.publish.guard_check_minutes) + 2)
```

4. `Runner.__init__` gains the parameter:

```python
    def __init__(self, st: pipeline.Station, p: publish.Publisher, *, clock: Callable[[], int] = now_us,
                 sleep: Callable[[float], None] = time.sleep, tick_s: float = 60.0,
                 monitor: DeadClockMonitor | None = None):
        self.st, self.p, self.clock, self.sleep, self.tick_s = st, p, clock, sleep, tick_s
        self.monitor = monitor
```

5. In `tick`, after `self._step("publish", lambda: publish_all(self.p, t_us, self.held))`:

```python
        if self.monitor is not None:
            monitor = self.monitor
            self._step("dead-clock", lambda: monitor.check(t_us, read_json(self.st.ws.guard_cache_path)))
```

`cli.py` `run`: `service.Runner(st, service.open_publisher(st), monitor=service.open_monitor(st)).run(max_ticks=1 if once else None)`.

- [ ] **Step 4: Run the transmitter suite on both Pythons**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q && ./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): dead-clock check on the public live.m3u8 and a stale-guard alert"
```

---

### Task 15: sd_notify, watchdog, systemd unit

**Model hint:** sonnet

**Files:**
- Create: `packages/transmitter/src/transmitter/sdnotify.py`, `packages/transmitter/systemd/transmitter@.service`, `packages/transmitter/tests_transmitter/test_systemd.py`
- Modify: `service.py` (`Runner(notify=…)`; pings)

**Interfaces:**
- Consumes: `Runner` and `publish_all` (Task 14 state).
- Produces:
  - `sdnotify.notify(message, env=os.environ) -> bool` (no-op without `NOTIFY_SOCKET`; `@` = an abstract socket; errors are logged, never raised).
  - `Runner(..., notify=sdnotify.notify)`: `READY=1` when `run` starts, `WATCHDOG=1` after every step (in `_step`'s `finally`) and `STOPPING=1` when `run` ends.
  - `publish_all(p, t_us, held=None, notify=None)`: `WATCHDOG=1` after every publish batch, so a long catch-up publish (up to `MAX_BATCHES` batches after a stop) is not killed by `WatchdogSec`; the runner passes its notifier.
  - The template unit `transmitter@<user>.service` (ruling R15).

- [ ] **Step 1: Write the failing test**

`packages/transmitter/tests_transmitter/test_systemd.py`:

```python
import configparser
import socket
import tempfile
from pathlib import Path

from tests_transmitter.helpers import FakeBucket, make_station
from tests_transmitter.test_service import _publisher
from transmitter import sdnotify, service

UNIT = Path(__file__).resolve().parents[1] / "systemd" / "transmitter@.service"


def test_notify_is_a_no_op_outside_systemd():
    assert sdnotify.notify("READY=1", env={}) is False


def test_notify_sends_one_datagram_to_notify_socket():
    with tempfile.TemporaryDirectory(dir="/tmp") as d:      # AF_UNIX paths are short (104 bytes on macOS)
        path = str(Path(d) / "n")
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as server:
            server.bind(path)
            assert sdnotify.notify("WATCHDOG=1", env={"NOTIFY_SOCKET": path}) is True
            assert server.recv(64) == b"WATCHDOG=1"


def test_notify_failure_is_logged_not_raised():
    assert sdnotify.notify("READY=1", env={"NOTIFY_SOCKET": "/nonexistent/socket"}) is False


def test_the_runner_says_ready_pings_the_watchdog_after_every_step_and_says_stopping(tmp_path):
    st, _ = make_station(tmp_path)
    sent: list[str] = []
    runner = service.Runner(st, _publisher(st, FakeBucket()), sleep=lambda s: None,
                            notify=lambda m: sent.append(m) or True)
    runner.run(max_ticks=1)
    assert sent[0] == "READY=1" and sent[-1] == "STOPPING=1"
    assert sent.count("WATCHDOG=1") == 4                    # plan, render, publish, and its one batch


def test_publish_all_feeds_the_watchdog_after_every_batch(tmp_path, monkeypatch):
    from transmitter import publish

    st, _ = make_station(tmp_path)
    batches = iter([publish.PublishReport(uploaded=[1]), publish.PublishReport(uploaded=[2]), publish.PublishReport()])
    monkeypatch.setattr(publish, "publish_batch", lambda p, t_us: next(batches))
    monkeypatch.setattr(publish, "prune", lambda p, t_us: publish.PruneReport())
    sent: list[str] = []
    service.publish_all(_publisher(st, FakeBucket()), 0, notify=lambda m: sent.append(m) or True)
    assert sent == ["WATCHDOG=1"] * 3


def test_the_unit_runs_transmitter_under_a_watchdog_and_always_restarts():
    unit = configparser.ConfigParser(strict=False, interpolation=None)
    unit.optionxform = str
    unit.read_string(UNIT.read_text())
    s = unit["Service"]
    assert s["Type"] == "notify" and s["NotifyAccess"] == "main"
    assert s["Restart"] == "always" and s["RestartSec"] == "30"
    assert s["WatchdogSec"] == "45min"
    assert s["User"] == "%i"
    assert s["EnvironmentFile"] == "/etc/transmitter/%i.env"
    assert s["ExecStart"].endswith("/bin/transmitter run")
    assert s["StandardOutput"] == "journal"
    assert unit["Install"]["WantedBy"] == "multi-user.target"
    assert "network-online.target" in unit["Unit"]["After"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_systemd.py -q`
Expected: FAIL. `cannot import name 'sdnotify'`.

- [ ] **Step 3: Implement**

`packages/transmitter/src/transmitter/sdnotify.py`:

```python
"""systemd notifications without libsystemd (sd_notify(3)): one datagram to
$NOTIFY_SOCKET (a leading "@" names an abstract socket). The unit is
Type=notify with WatchdogSec: `transmitter run` sends READY=1 once, then
WATCHDOG=1 after every step of every tick and after every publish batch, so a
hang longer than WatchdogSec (e.g. a hard NFS mount) gets the service killed
and restarted. Outside systemd (no NOTIFY_SOCKET) every call is a no-op."""

import logging
import os
import socket
from typing import Mapping

log = logging.getLogger("transmitter")


def notify(message: str, env: Mapping[str, str] = os.environ) -> bool:
    addr = env.get("NOTIFY_SOCKET")
    if not addr:
        return False
    if addr.startswith("@"):
        addr = "\0" + addr[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.connect(addr)
            sock.sendall(message.encode())
        return True
    except OSError as exc:
        log.warning("sd_notify(%s) failed: %s", message, exc)
        return False
```

`packages/transmitter/systemd/transmitter@.service`:

```ini
# transmitter as a system service: `transmitter@<user>.service` runs
# `transmitter run` as <user> (the account that owns ~/.transmitter and can
# read the station root over NFS). Install: docs/playout-setup.md, section 6.
[Unit]
Description=llama station playout (transmitter run) as %i
After=network-online.target remote-fs.target
Wants=network-online.target

[Service]
Type=notify
NotifyAccess=main
User=%i
# R2 keys, SMTP credentials, NTFY_TOKEN; owned by %i, mode 600.
EnvironmentFile=/etc/transmitter/%i.env
ExecStart=/home/%i/.venvs/transmitter/bin/transmitter run
Restart=always
RestartSec=30
# transmitter pings after every step and every publish batch; the longest gap is one
# show's encode (~10-20 min on hugo).
WatchdogSec=45min
TimeoutStartSec=2min
StandardOutput=journal
StandardError=journal
SyslogIdentifier=transmitter

[Install]
WantedBy=multi-user.target
```

`service.py`, five edits:

1. Add `sdnotify` to `from transmitter import …`.
2. `Runner.__init__` becomes:

```python
    def __init__(self, st: pipeline.Station, p: publish.Publisher, *, clock: Callable[[], int] = now_us,
                 sleep: Callable[[float], None] = time.sleep, tick_s: float = 60.0,
                 monitor: DeadClockMonitor | None = None, notify: Callable[[str], bool] = sdnotify.notify):
        self.st, self.p, self.clock, self.sleep, self.tick_s = st, p, clock, sleep, tick_s
        self.monitor, self.notify = monitor, notify
```

3. In `_step`, extend the docstring's last sentence to "… resolves `resolves`; every step ends with a watchdog ping." and add a `finally` after the last `except` clause:

```python
        except Exception as exc:
            log.exception("%s step failed", name)
            alerts.alert(name, f"{type(exc).__name__}: {exc}")
        finally:
            self.notify("WATCHDOG=1")
```

4. `publish_all` feeds the watchdog after every batch. Its signature and loop head become:

```python
def publish_all(p: publish.Publisher, t_us: int, held: HeldTracker | None = None,
                notify: Callable[[str], object] | None = None
                ) -> tuple[list[publish.PublishReport], publish.PruneReport]:
    reports = []
    for _ in range(MAX_BATCHES):
        r = publish.publish_batch(p, t_us)
        reports.append(r)
        if notify is not None:
            notify("WATCHDOG=1")    # a catch-up is many batches: one step must not outlast WatchdogSec
```

   (the rest of the loop is unchanged), and in `tick` the publish step passes the notifier: `self._step("publish", lambda: publish_all(self.p, t_us, self.held, self.notify))`.

5. `run` becomes:

```python
    def run(self, max_ticks: int | None = None) -> None:
        self.notify("READY=1")
        ticks = 0
        try:
            while max_ticks is None or ticks < max_ticks:
                started = time.monotonic()
                self.tick(self.clock())
                ticks += 1
                if max_ticks is not None and ticks >= max_ticks:
                    break
                self.sleep(max(0.0, self.tick_s - (time.monotonic() - started)))
        finally:
            self.notify("STOPPING=1")
```

- [ ] **Step 4: Run the transmitter suite on both Pythons (and the Debian-12 gate)**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q && ./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q`
Expected: PASS. If Docker is available, also run `packages/transmitter/scripts/test-in-debian12.sh -q`, which exercises the real AF_UNIX datagram on Linux.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): systemd unit (Type=notify, WatchdogSec, Restart=always) and sd_notify pings"
```

---

### Task 16: Extended `transmitter status`

**Model hint:** sonnet

**Files:**
- Modify: `service.py` (`cloud_lines`, `status_lines`), `cli.py` (`status`)
- Modify (tests): `test_service.py` (append)

**Interfaces:**
- Consumes: `cloudstate.get_json`, `guard_summary`, the keys (Task 12); `cli._cloud` (Task 12); `Workspace.alerts_path` and `alerts.active_codes` (Task 13).
- Produces:
  - `service.cloud_lines(read) -> list[str]`, where `read(key) -> dict | None` and a `TransmitterError` is printed as `cloud      unavailable: …`.
  - `service.status_lines(cfg, t_us, cloud=None, cloud_error=None)`, with new lines after `fallback`:
    - `anchors    none (the scheduler and its window misses are phase 3)`;
    - `alerts     hugo: …` (`alerts.active_codes`: an event code drops off once `repeat_hours` pass without a new fire);
    - then the guard (`guard`, `spend`, `period`, `reading`, `killswitch`), `offair`, `raise`, and `alerts     cloud: …`.

Spec "Alerts and operations": status shows what is on air, the lead, next anchors, misses, empty-anchor warnings (those three are phase 3), `tripped` with its reason, `offair`, and active alarms. It needs R2 keys for the cloud half; without them, the local half still prints.

- [ ] **Step 1: Write the failing tests**

Append to `tests_transmitter/test_service.py`:

```python
def _with_epoch(st):
    from transmitter.workspace import write_json
    write_json(st.ws.epoch_path, {"epoch_id": "etest", "epoch": st.epoch.iso, "d": 10.24})
    return st


def test_status_shows_the_cloud_state_and_active_alerts(tmp_path):
    import json as _json

    st = _with_epoch(make_station(tmp_path)[0])
    (st.ws.root / "alerts.json").write_text(_json.dumps({"dead-clock": {"active": True}, "render": {"active": False},
                                                         "publish": {"active": True, "last_fired_at": 0.0}}))
    docs = {
        "state/guard.json": {"tripped": True, "reason": "blind", "tripped_at": "2026-10-20T06:00:00.000Z",
                             "last_error": "analytics: HTTP 503", "last_success": "2026-10-20T00:00:00.000Z",
                             "waf": {"enabled": True, "error": None}},
        "state/offair.json": {"offair": True, "reason": "objection", "since": "2026-10-20T05:00:00.000Z", "until": None},
        "state/alerts.json": {"tripped-blind": {"active": True}},
    }
    lines = service.status_lines(st.cfg, NOW, cloud=docs.get)
    text = "\n".join(lines)
    assert "alerts     hugo: dead-clock" in lines           # the 1970 publish event has gone stale
    assert "guard      TRIPPED (blind)" in text and "reading    failing since 2026-10-20T00:00:00.000Z" in text
    assert "killswitch enabled" in text
    assert "offair     ON since 2026-10-20T05:00:00.000Z (objection)" in text
    assert "alerts     cloud: tripped-blind" in text
    assert "anchors    none" in text


def test_status_without_cloud_access_still_prints_the_local_half(tmp_path):
    from transmitter.errors import CloudStateError

    st = _with_epoch(make_station(tmp_path)[0])

    def broken(key):
        raise CloudStateError("cannot read state/guard.json: boom")

    assert service.status_lines(st.cfg, NOW, cloud=broken)[-1] == "cloud      unavailable: cannot read state/guard.json: boom"
    assert service.status_lines(st.cfg, NOW, cloud_error="set R2_ACCESS_KEY_ID")[-1] == \
        "cloud      unavailable: set R2_ACCESS_KEY_ID"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_service.py -q`
Expected: FAIL. `status_lines()` does not take `cloud`.

- [ ] **Step 3: Implement**

`service.py`: add `cloudstate` to `from transmitter import …`, add this before `status_lines`, and change the signature of `status_lines`:

```python
def cloud_lines(read: Callable[[str], dict | None]) -> list[str]:
    """`status`'s cloud half: the guard, the operator's flag, a raise, cloud
    alerts. `read(key)` returns a state/ document or None (cloudstate.get_json)."""
    try:
        guard = read(cloudstate.GUARD_KEY)
        offair = read(cloudstate.OFFAIR_KEY)
        raised = read(cloudstate.BUDGET_KEY)
        cloud_alerts = read(cloudstate.ALERTS_KEY) or {}
    except TransmitterError as exc:
        return [f"cloud      unavailable: {exc}"]
    lines = cloudstate.guard_summary(guard)
    if offair and offair.get("offair") is True:
        lines.append(f"offair     ON since {offair.get('since')} ({offair.get('reason')})"
                     + (f", expected until {offair['until']}" if offair.get("until") else ""))
    else:
        lines.append("offair     off")
    if raised:
        lines.append(f"raise      ${float(raised.get('budget_usd', 0)):.2f} until {raised.get('expires')}")
    active = sorted(k for k, e in cloud_alerts.items() if isinstance(e, dict) and e.get("active"))
    lines.append(f"alerts     cloud: {', '.join(active) if active else 'none'}")
    return lines


def status_lines(cfg: TransmitterConfig, t_us: int, cloud: Callable[[str], dict | None] | None = None,
                 cloud_error: str | None = None) -> list[str]:
```

and replace the end of `status_lines`:

```python
    lines.append(f"fallback   {fb}" if fb else "fallback   none (run `transmitter fallback render`)")
    return lines
```

with:

```python
    lines.append(f"fallback   {fb}" if fb else "fallback   none (run `transmitter fallback render`)")
    lines.append("anchors    none (the scheduler and its window misses are phase 3)")
    hugo = alerts.active_codes(read_json(ws.alerts_path, {}) or {}, t_us / 1e6, cfg.alerts.repeat_hours * 3600)
    lines.append(f"alerts     hugo: {', '.join(hugo) if hugo else 'none'}")
    if cloud is not None:
        lines += cloud_lines(cloud)
    elif cloud_error:
        lines.append(f"cloud      unavailable: {cloud_error}")
    return lines
```

`cli.py` `status` becomes:

```python
@app.command()
def status(config: Path = CONFIG_OPT):
    """Epoch, plan, on air, lead, fallback; the cost guard, off-air flag, kill switch and active alerts."""
    cfg = load_config(config)
    cloud, error = None, None
    try:
        client, bucket = _cloud(config)
        cloud = lambda key: cloudstate.get_json(client, bucket, key)  # noqa: E731
    except TransmitterError as exc:                # no bucket or no R2 keys: the local half still prints
        error = str(exc)
    for line in service.status_lines(cfg, service.now_us(), cloud, error):
        typer.echo(line)
```

- [ ] **Step 4: Run the transmitter suite on both Pythons, and the Debian-12 gate**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q && ./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q`
Expected: PASS. If Docker is available, `packages/transmitter/scripts/test-in-debian12.sh -q` passes too.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): status shows the cost guard, off-air flag, kill switch and active alerts"
```

---
### Task 17: Runbook, deploy, phase-2 verification — HUMAN CHECKPOINT

**Model hint:** sonnet

**Files:**
- Modify: `docs/playout-setup.md`
- Create (by the operator's results, at the checkpoint): `docs/superpowers/2026-10-1X-playout-phase2-verification.md` (X = the day it is run)

**Interfaces:**
- Consumes: every name above, namely:
  - the secrets `CF_ACCOUNT_ID`, `CF_ZONE_ID`, `CF_ANALYTICS_TOKEN`, `CF_WAF_TOKEN`, `NTFY_URL`, `NTFY_TOKEN`, `ALERT_EMAIL_FROM` and `ALERT_EMAIL_TO`;
  - the vars `MONTHLY_BUDGET_USD`, `BILLING_ANNIVERSARY_DAY`, `GUARD_EVAL_SECONDS`, `BLIND_AFTER_SECONDS`, `KILL_SWITCH_DESCRIPTION`, `LEAD_FLOOR_HOURS`, `ALERT_REPEAT_HOURS` and `STATION_NAME`, and the committed `send_email` binding `ALERT_EMAIL`;
  - `npx wrangler deploy`, with `--dry-run` and `--var`;
  - transmitter's `[alerts]` keys and env `SMTP_USERNAME` / `SMTP_PASSWORD` / `NTFY_TOKEN`;
  - the commands `transmitter offair|budget|status`;
  - the unit `transmitter@<user>.service`.
- Produces: the operator runbook for phase 2 and its verification checklist. No code. The implementer writes the doc and commits it. **The deploy and every checklist item are the operator's, at the checkpoint (Step 3).**

- [ ] **Step 1: Edit `docs/playout-setup.md`**

Make these edits, keeping every placeholder literal (`<host>`, `<user>`, `<repo>`, `<your-topic>`, `you@example.com`, `<zone>`). No real address, ID or token may appear; the one exception is the alert sender `alerts@lma-radio.com` (Stakes).

1. In the intro, replace "**Do not share the station publicly until phase 2 (the cost guard) ships.**" with "**Do not share the station publicly until the phase-2 checklist (section 8) passes.**"
2. In section 3, step 5, add as the first sentence: "Phase 2 replaces this transient unit with the system unit in section 6 step 2; follow that instead on an existing install."
3. In section 4, step 3, add: "`index.html` is not uploaded: the clock writes it, the player page normally and the off-air page while the station is blocked."
4. In section 4, step 4, replace the opening ("Off-air by hand …" through "… and back.") with the text below. Keep the paragraph that follows it, about a missing fallback and the ENDLIST-only playlist.

   "Off-air: `transmitter offair on --reason \"…\"` / `transmitter offair off` (section 7). Within about a minute the clock serves the notice and ENDLIST, swaps `index.html` to the off-air page and enables the kill switch, and reverses all three after `off`. **If hugo is down**, write the flag from the Mac instead: from `antenna/`, put `{"offair": true, "reason": "…", "since": "<iso>", "until": null}` in `offair.json` and run `npx wrangler r2 object put lma-radio/state/offair.json --file offair.json --content-type application/json --remote` (`"offair": false` to come back). The guard honours the file within a minute, exactly as if `transmitter offair` had written it. Do **not** toggle the kill-switch rule in the dashboard: the guard reconciles it every minute, undoes the toggle and alerts `waf-corrected`. **If the clock Worker itself is broken** (nothing reconciles, so neither lever acts), first remove the Worker's cron trigger (dashboard: Workers & Pages → `antenna` → Settings → Trigger events; or `npx wrangler triggers deploy` from a config with no crons), then enable the kill-switch rule by hand. In that order: a Worker that is still running would undo the rule within a minute."
5. After section 5, append sections 6–8 exactly as below.

````markdown
## 6. Phase 2: the cost guard, alerts and the service

The guard runs in the clock Worker. It reads the account's usage every 15 minutes and prices it (budget $15 a month, including the $5 Workers Paid base). It **blocks** the station (ENDLIST playlist, off-air `index.html`, the WAF kill switch) when actual spend reaches 90% or projected spend reaches 100%, or when it has had no successful reading for 6 hours. It alerts at 50% and 80%. `transmitter offair on` blocks the station too. Design: `docs/superpowers/specs/2026-10-09-playout-design.md` ("Cost guard", "Alerts and operations").

The billing period starts on day 11 of each month, 00:00 UTC (the committed var `BILLING_ANNIVERSARY_DAY`). Upgrade transmitter and antenna in either order. If transmitter is upgraded first, hugo alerts `guard-stale` until antenna is deployed (no guard has evaluated yet): expected.

### 6.1 transmitter on hugo

1. `cd <repo> && git pull && ~/.venvs/transmitter/bin/pip install -e packages/transmitter`.
2. **System unit.** It replaces the phase-1 `systemd-run --user` unit:
   ```
   systemctl --user stop transmitter                       # the phase-1 transient unit
   sudo install -d -m 755 /etc/transmitter
   sudo install -m 600 -o <user> -g <user> <env file> /etc/transmitter/<user>.env
   sudo cp <repo>/packages/transmitter/systemd/transmitter@.service /etc/systemd/system/
   sudo systemd-analyze verify /etc/systemd/system/transmitter@.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now transmitter@<user>
   systemctl status transmitter@<user>                      # active (running)
   journalctl -u transmitter@<user> -f                      # ALERT lines appear here
   ```
   The unit expects the venv at `/home/<user>/.venvs/transmitter`; edit `ExecStart` in the copied file if yours differs. It is `Type=notify` with `WatchdogSec=45min` and `Restart=always`, and it starts at boot (`sudo loginctl enable-linger` is no longer needed for it).
3. **Alerts.** Add to `<env file>`, which is `/etc/transmitter/<user>.env` from now on (mode 600, owned by `<user>`):
   ```
   SMTP_USERNAME=you@example.com
   SMTP_PASSWORD=<a Google App Password: Google Account -> Security -> 2-Step Verification -> App passwords>
   NTFY_TOKEN=<optional ntfy access token>
   ```
   and to `config.toml`:
   ```
   [alerts]
   email_to = "you@example.com"
   ntfy_url = "https://ntfy.sh/<your-topic>"
   ```
   `[antenna] site_url` must be set: the dead-clock check fetches `<site_url>/live.m3u8` once a minute. Then `sudo systemctl restart transmitter@<user>`.

### 6.2 Tokens and email (dashboard)

1. **WAF token.** My Profile → API Tokens → Create Token → Custom token. Permissions: *Zone · WAF · Edit*. Zone resources: *Include · Specific zone · <zone>*. Keep the token for 6.3.
2. **Analytics token.** The existing *Account Analytics: Read* token (phase 1).
3. **Zone ID.** The zone's overview page → API → *Zone ID*.
4. **Email.** Email Routing must be enabled on the zone, with the destination address verified (phase 1). The sender is `alerts@lma-radio.com`, on the zone's domain. The `send_email` binding `ALERT_EMAIL` in `wrangler.jsonc` is unrestricted: it can only reach the account's verified destinations, and the one the Worker uses is the `ALERT_EMAIL_TO` secret (6.3), so the destination never enters the repo.
5. **Kill switch.** The custom rule *"station: kill switch"* (section 2 step 7) must exist **exactly once**, with action Block. The guard finds it by that description and refuses to touch it if it is missing, duplicated or not a Block rule.

### 6.3 antenna

From `antenna/`, with `.env` holding `CLOUDFLARE_ACCOUNT_ID`:

1. Secrets (each command prompts for the value; nothing is echoed or committed):
   ```
   npx wrangler secret put CF_ACCOUNT_ID
   npx wrangler secret put CF_ZONE_ID
   npx wrangler secret put CF_ANALYTICS_TOKEN
   npx wrangler secret put CF_WAF_TOKEN
   npx wrangler secret put NTFY_URL                    # https://ntfy.sh/<your-topic>
   npx wrangler secret put NTFY_TOKEN                  # optional
   npx wrangler secret put ALERT_EMAIL_FROM            # alerts@lma-radio.com
   npx wrangler secret put ALERT_EMAIL_TO              # the verified destination (its only copy)
   npx wrangler secret list
   ```
2. `npm ci && npm test`, then `npx wrangler deploy --dry-run` and check the output (it bundles and lists the bindings, `ALERT_EMAIL` among them). Then `npx wrangler deploy`.
3. `ANTENNA_BUCKET=lma-radio npm run deploy:assets` (the player's stall watch is in `player.js`/`nowplaying.js`).
4. Within two minutes, `npx wrangler r2 object get lma-radio/state/guard.json --remote --pipe` shows the following. `transmitter status` shows the same picture from hugo.
   - `evaluated_at` recent, `last_error: null`;
   - an `evaluation` with `actual_usd` ≈ 5 plus usage, and `budget_usd: 15`;
   - `waf.enabled: false`, `waf.error: null`;
   - `evaluation.unknown_action_types: []`.
5. Optional second channel for a dead clock: Notifications → Add → Workers → the Worker-error alert for `antenna`.

## 7. Operating

- **Take the station off the air / back on:** `transmitter offair on --reason "…" [--until <iso>]` / `transmitter offair off`. These work while the guard is tripped and whatever the daily PUT budget says. With hugo down, write `state/offair.json` from the Mac; with the clock Worker broken, remove its cron trigger, then enable the kill switch by hand (both in section 4 step 4).
- **The guard tripped for spend:** it clears only in the next billing period, or after `transmitter budget --raise-to <usd>`. Either way it clears only if the guard's next evaluation is under the thresholds. `transmitter budget` shows the guard's state. A raise must exceed the current budget and may not exceed $100. It expires at the period's end. Raise above the *projected* figure `transmitter budget` shows, or the next evaluation re-trips and consumes the raise. A `state/budget.json` that expires after the current billing period is ignored and alerted (`budget-file-invalid`); `transmitter budget --raise-to` always writes the period's end. The station's policy is to shut down on overrun, not to keep raising.
- **Tripped "blind"** (no reading for 6 h): fix the cause (analytics token, `CF_ACCOUNT_ID`, a Cloudflare API outage; see `last_error` in `transmitter budget`). The first successful reading under the thresholds clears it.
- **Alerts.** Cloud alerts come from the clock Worker (ntfy + email). hugo alerts come from transmitter (email + ntfy). Each repeats every 6 h while active and says "resolved" when a latch or outage clears. The 50% and 80% spend alerts come once per billing period (and budget). A dashboard toggle of the kill switch is undone and alerted (`waf-corrected`). `transmitter status` lists both sets; a hugo event alert (a publish error, the PUT budget) drops off once 6 h pass without a new one.
- **Known limitations.**
  - *VLC at a fallback→live switch.* At a fresh run — the first start, an outage longer than the published lead, or a re-epoch — `EXT-X-DISCONTINUITY-SEQUENCE` restarts at 0. hls.js and Safari follow it; VLC goes silent and needs stop/play once.
  - *Cloud alerts need R2.* While R2 itself is unreadable, the cloud cannot send alerts (their state lives in R2); hugo's dead-clock check is the channel for that case. An invocation whose guard could not read its state (`blocked: null`) may still try to read `state/alerts.json`.
  - *ENDLIST may lag a trip.* With two invocations overlapping right after a trip, the ENDLIST playlist can lag by up to about a minute. That matters only while the WAF API is also failing (a cooperative-only block).
  - *`lead-low` on a fresh start.* A fresh run (first start, or a restart after an outage longer than the lead) builds its lead from zero, so `lead-low` fires and later resolves while the lead grows (about 10 minutes of encoding per show on hugo). That alert is expected after a fresh start and needs no action.
  - *A future-dated budget raise.* If `state/budget.json`'s `written_at` is ahead of the Worker's clock (hugo's clock skewed ahead), the guard re-evaluates every minute until that time passes. Those are GraphQL reads, which are not billed; NTP on hugo keeps the window to seconds.

## 8. Phase-2 verification checklist

Run with the station up and **not yet shared**. Record each result (date, observation) in `docs/superpowers/<date>-playout-phase2-verification.md`. Restore the normal deploy (`npx wrangler deploy`, with no `--var`) after each item that changes it.

- [ ] **The guard reads and prices usage.** `guard.json` → `evaluation`: compare `period_to_date` with the dashboard's R2 and Workers metrics for the period (sampled; expect agreement within a few percent). `unknown_action_types` is `[]`; otherwise record the strings.
- [ ] **Off-air blocks fully and comes back.** `transmitter offair on --reason test`. Within ~1 min:
      - `curl -s https://<host>/live.m3u8` → 403 (kill switch);
      - the dashboard shows the kill-switch rule enabled;
      - `curl -s https://<host>/` → the off-air page;
      - `transmitter status` → `offair ON`, `killswitch enabled`.

      Then `transmitter offair off`. Within ~1 min everything reverses and players can tune in again. Repeat once with the Mac-side write of `state/offair.json` (section 4 step 4) in place of `transmitter offair`.
- [ ] **An already-playing page shows the notice** (amendment A2). Play in Chrome and in Safari, then `transmitter offair on`. Each page shows "The station is off the air." with *Try again* within about a minute (the buffer drains, then two probes 10 s apart). VLC stops on ENDLIST. Then `offair off`.
- [ ] **A network blip shows no notice.** While playing in Chrome, toggle the Mac's Wi-Fi off for ~20 s, then on. The page says "Reconnecting…" while stalled, never the off-air notice, and resumes (or needs one *Play*).
- [ ] **A spend trip and a raise.**
      1. `npx wrangler deploy --var MONTHLY_BUDGET_USD:5.5`. Within 15 min (the next evaluation), the actual $5+ is ≥ 90% of $5.50, so you see:
         - an urgent ntfy and email "Station blocked: spend";
         - the station blocked as above;
         - `transmitter budget` → `TRIPPED (spend)`.
      2. `transmitter budget --raise-to 7`. Within ~1 min the raise triggers an evaluation; it is under the thresholds, so the station is unblocked and a "resolved" message arrives.
      3. Restore: `npx wrangler deploy` (the budget is back to 15; the $7 raise is below it and ignored).
- [ ] **A blind trip.**
      1. Set `CF_ANALYTICS_TOKEN` to a wrong value (`npx wrangler secret put CF_ANALYTICS_TOKEN`), then `npx wrangler deploy --var BLIND_AFTER_SECONDS:900 --var GUARD_EVAL_SECONDS:60`. About 15 min after the last success the station blocks with "Station blocked: guard blind", and `guard.json` `last_error` names the failure.
      2. Restore the real token. The next evaluation unblocks the station.
      3. Restore the deploy.
- [ ] **A dashboard toggle is undone and alerted.** Enable the kill-switch rule in the dashboard while the station is on air. Within ~1 min it is disabled again and a "Kill switch toggled by hand" (`waf-corrected`) alert arrives.
- [ ] **A Rulesets failure.** Set `CF_WAF_TOKEN` to a wrong value. Within ~1 min a "Kill switch not reconciled" alert arrives, and `guard.json` `waf.error` is set. With `offair on` at the same time, `live.m3u8` is the ENDLIST playlist and `/` is the off-air page (the block is cooperative). Restore the token: the rule is enabled within a minute, then `offair off`.
- [ ] **Lead floor.** `npx wrangler deploy --var LEAD_FLOOR_HOURS:30`: a "Published lead below floor" alert arrives within a minute. Restore.
- [ ] **A dead clock.** Workers & Pages → `antenna` → Settings → Trigger events → delete the cron trigger. Within ~3 min hugo sends `dead-clock` (email + ntfy). Within about an hour it sends `guard-stale`. Restore with `npx wrangler deploy`; both send "resolved".
- [ ] **The watchdog.** `sudo systemctl edit transmitter@<user>` → `[Service]` `WatchdogSec=2min`. Then `sudo systemctl kill -s STOP transmitter@<user>`. Within ~2 min the journal shows a watchdog timeout and the service restarts. Remove the override, restart the service, and reboot hugo once to see it come back by itself.
- [ ] **Cron lag, 24 h** (carried from phase 1): median, p99, max, and the count over 25 s, from the phase-1 capture.
- [ ] **Cron lag plus guard time, 24 h** (Task 18's input): from a day of phase-2 clock lines, the median, p99 and max of `lagMs` and of `lagMs + guardMs`, and the count with `lagMs + guardMs` over 25 s, together with the Task 18 decision.
- [ ] **A week of op counts** (carried from phase 1, due 2026-10-18), now with the guard's own reads and writes: compare with `guard.json`'s `period_to_date`.

When every item passes, the station may be shared publicly (spec, Phases item 2).
````

- [ ] **Step 2: Check the doc against the code**

Run: `grep -nE "CF_ACCOUNT_ID|CF_ZONE_ID|CF_ANALYTICS_TOKEN|CF_WAF_TOKEN|BILLING_ANNIVERSARY_DAY|NTFY_URL|ALERT_EMAIL_(FROM|TO)|MONTHLY_BUDGET_USD|BLIND_AFTER_SECONDS|GUARD_EVAL_SECONDS|LEAD_FLOOR_HOURS|transmitter@" docs/playout-setup.md | wc -l`
Expected: each name appears, matching `antenna/src/guard.ts`, `antenna/src/alerts.ts`, `antenna/src/clock.ts`, `antenna/wrangler.jsonc`, `packages/transmitter/src/transmitter/config.py` and `packages/transmitter/systemd/transmitter@.service`. Then:

Run: `grep -nE "[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}" docs/playout-setup.md | grep -v "example\.\(com\|org\|net\)\|alerts@lma-radio\.com"`
Expected: no output (only placeholder addresses and the alert sender).

Commit:

```bash
git add docs/playout-setup.md
git commit -m "docs(playout): phase-2 runbook (guard, alerts, systemd unit) and verification checklist"
```

- [ ] **Step 3: HUMAN CHECKPOINT. The operator deploys and verifies (orchestrator: stop and escalate).**

The orchestrator stops here and reports to the parent. The parent explains the material to the operator before asking, following `explain-human-test-procedures`.

What the operator does, in order:
1. Section 6: transmitter, then tokens and email, then antenna.
2. Section 8: every checklist item.
3. A day later, the clock-line summary that Task 18's checkpoint needs.

What each part checks:
- **Spend path:** the guard's metering, pricing and latch, and the blocking reconciliation.
- **Cloud alerts:** ntfy and email delivery.
- **hugo side:** dead-clock, the watchdog and status.
- **Phase-1 findings:** the player stall (VLC at a fresh run is a documented limitation, amendment A1).

How to report: paste the results into the verification file. The template has one row per item: Item | Result (pass / fail / partial) | Observation (times, alert subjects, any deviation).

Failures:
- **On the spend or blocking path** (guard, latch, WAF, `offair`): stop. Do not share the station. Bring the failure back as a fix task.
- **Anywhere else:** record it and continue.

---

### Task 18: CONDITIONAL — playlist lookahead (amendment A4)

**Model hint:** opus

**Run this task only if it is triggered.** First, a **HUMAN CHECKPOINT**, a day after Task 17's deploy. The orchestrator stops and asks the operator, through the parent, for a 24 h summary of the phase-2 clock lines (`event: "clock"` in the Worker's logs): the count of invocations; the median, p99 and max of `lagMs` and of `lagMs + guardMs`; and **the count with `lagMs + guardMs` > 25,000**. The guard's own time sits on the same critical path as the cron lag, so the sum is the trigger.

- **More than 5 invocations over 25 s:** do the steps below.
- **Otherwise:** record the summary and the "not triggered" ruling in the ledger and in Task 17's verification file, and go on to Task 19. Nothing changes.

**Files:**
- Modify: `antenna/src/playlist.ts`, `antenna/src/clock.ts`, `antenna/wrangler.jsonc`, `antenna/test/playlist.test.ts`, `antenna/test/clock.test.ts`

**Interfaces:**
- Consumes: `windowEntries`, `PlaylistConfig` (phase 1); `configFromEnv`, `runClock` and its invocation start `startedMs` (Task 8).
- Produces: `PlaylistConfig.lookahead?: number`; the var `PLAYLIST_LOOKAHEAD` (set to `"3"`); `clock.MAX_LOOKAHEAD = 4`; the off-air MEDIA-SEQUENCE numbered from `max(scheduledTime + loopMs, startedMs + lookahead·d)`.

**Effect.** The window lists 3 segments past the one airing, so players that sit ~3 target durations behind the edge play at the wall clock, with ~64 s of runway against a late cron fire. Every listed segment exists (the lead is ~24 h), and the PUT count is unchanged. The grace hold and fallback switch now apply to the target `cur + lookahead`.

**Invariants.** The off-air MEDIA-SEQUENCE must stay at or above the live one it replaces, which now reaches `lookahead` segments past the clock. `scheduledTime + loopMs` alone no longer guarantees that: an invocation that starts more than about 75 s late (cron lag plus guard time) would number it below live. The clock therefore takes the later of that and `startedMs + lookahead·d` (a test pins this at the cap of 4). The prune floor still holds, since a lookahead shortens how long a segment stays listed. Phase 1's discontinuity numbering is untouched (amendment A1).

- [ ] **Step 1: Write the failing tests**

`antenna/test/playlist.test.ts`: insert before `it("returns null before the epoch", …)`:

```ts
  it("lookahead lists segments past the one airing, holding at last and falling back as before", () => {
    const la = { ...CFG, lookahead: 3 };
    const pl = buildPlaylist({ nowMs: at(1000), horizon: horizon(0, 5000), fallback: FB, offair: false }, la)!;
    expect(entries(pl).map((e) => e.uri)).toEqual(live([998, 999, 1000, 1001, 1002, 1003]));
    expect(mediaSequence(pl)).toBe(998);
    // The lead nearly gone: hold at last for up to `grace` past it, then the loop.
    const hold = buildPlaylist({ nowMs: at(99), horizon: horizon(0, 100), fallback: FB, offair: false }, la)!;
    expect(entries(hold).at(-1)!.uri).toBe("seg/e1/100.aac");
    const fb = buildPlaylist({ nowMs: at(101), horizon: horizon(0, 100), fallback: FB, offair: false }, la)!;
    expect(entries(fb).at(-1)!.uri).toBe(loop([104])[0]);
  });
```

`antenna/test/clock.test.ts`: in `describe("runClock")`, insert before `it("runs the guard before reading or writing anything", …)`:

```ts
  it("a late invocation's off-air MEDIA-SEQUENCE never drops below the live one (lookahead)", async () => {
    const cfg = { ...CFG, lookahead: 4 };
    const scheduledTime = E + 50 * D;
    const late = scheduledTime + 100_000; // cron lag plus guard time beyond the 75 s loop
    const seq = async (guard: () => Promise<GuardOutcome>) => {
      const bucket = new MemoryBucket();
      station(bucket);
      await runClock({ bucket, ...fakeTime(late), scheduledTime, config: cfg, guard });
      return Number(/#EXT-X-MEDIA-SEQUENCE:(\d+)/.exec(bucket.objects.get("live.m3u8")!.body)![1]);
    };
    expect(await seq(guardSays(true))).toBeGreaterThanOrEqual(await seq(onAir));
  });
```

In `describe("configFromEnv")`, the default config now carries `lookahead: 0`. Replace the first `expect(configFromEnv({})).toEqual(…)` with:

```ts
    expect(configFromEnv({})).toEqual({ window: 6, grace: 3, offairAfterMs: 86_400_000, loopMs: 75_000, liveMaxAge: 5,
                                        leadFloorMs: 16 * 3_600_000, lookahead: 0 });
    expect(configFromEnv({ PLAYLIST_LOOKAHEAD: "3" }).lookahead).toBe(3);
    expect(configFromEnv({ PLAYLIST_LOOKAHEAD: "50" }).lookahead).toBe(4);
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd antenna && npx vitest run test/playlist.test.ts test/clock.test.ts`
Expected: FAIL. `lookahead` is ignored, so the window still ends at the segment airing, and `configFromEnv` has no `lookahead`. The late-invocation test passes for now (without a lookahead the live window never runs ahead); it guards Step 3, and fails if the window honours `lookahead` while the off-air sequence still comes from `scheduledTime + loopMs` alone.

- [ ] **Step 3: Implement**

`antenna/src/playlist.ts`: add to `PlaylistConfig`:

```ts
  /** Segments listed past the one airing now (amendment A4): players that sit
   * ~3 segments behind the live edge then play at the wall clock, with that
   * much more runway when a cron invocation fires late. Each listed segment
   * exists (horizon.last is ~24 h ahead). Default 0. */
  lookahead?: number;
```

and in `windowEntries` replace the first two lines of the body with:

```ts
  const target = cur + (cfg.lookahead ?? 0);
  const behind = target - h.last;
  const end = behind > 0 && behind <= cfg.grace ? h.last : target;
```

`antenna/src/clock.ts`: add `PLAYLIST_LOOKAHEAD?: string;` to `ClockEnv`. Below `ClockEnv`, add:

```ts
/** The lookahead never exceeds this (amendment A4). */
export const MAX_LOOKAHEAD = 4;
```

In `configFromEnv` add `lookahead: Math.min(MAX_LOOKAHEAD, Math.floor(num(env.PLAYLIST_LOOKAHEAD, 0))),`. In `runClock`'s `write`, replace:

```ts
      const body = buildPlaylist({ nowMs, horizon, fallback: inputs.fallback, offair: inputs.offair,
                                   offairSeqMs: deps.scheduledTime + config.loopMs }, config);
```

with:

```ts
      // The off-air MEDIA-SEQUENCE must not fall below the live window it
      // replaces, which reaches `lookahead` segments past the clock: a late
      // invocation (cron lag plus guard time) cannot number it from
      // scheduledTime alone.
      const offairSeqMs = Math.max(deps.scheduledTime + config.loopMs, startedMs + (config.lookahead ?? 0) * g.dMs);
      const body = buildPlaylist({ nowMs, horizon, fallback: inputs.fallback, offair: inputs.offair, offairSeqMs },
                                 config);
```

`antenna/wrangler.jsonc`: add `"PLAYLIST_LOOKAHEAD": "3",` after `"GRACE_SEGMENTS": "3",`.

- [ ] **Step 4: Run everything**

Run: `cd antenna && npm test && npx tsc --noEmit`
Expected: PASS; no type errors.

- [ ] **Step 5: Commit**

```bash
git add antenna/src/playlist.ts antenna/src/clock.ts antenna/wrangler.jsonc antenna/test/playlist.test.ts antenna/test/clock.test.ts
git commit -m "feat(antenna): playlist lookahead 3 (players at the wall clock, ~64 s runway against late cron fires)"
```

- [ ] **Step 6: HUMAN CHECKPOINT. The operator deploys the lookahead (orchestrator: stop and escalate).**

From `antenna/`: `npx wrangler deploy --dry-run`, then `npx wrangler deploy`. Within a minute, `curl -s https://<host>/live.m3u8` lists its last three segments with a `PROGRAM-DATE-TIME` ahead of the wall clock, and Chrome and Safari keep playing. Then `transmitter offair on --reason test` and `off` once: players show the off-air notice and come back as in Task 17's checklist. Record both in Task 17's verification file.

---

### Task 19: CLAUDE.md and the approved spec amendments

**Model hint:** sonnet

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/superpowers/specs/2026-10-09-playout-design.md`, with the amendments the operator approved on 2026-10-12. Each becomes an *(As built, <date>: …)* note in the matching section, in the style of the phase-1 notes: A2, A3 (the unrestricted binding), A5, A4 only if Task 18 ran (otherwise a one-line note that its trigger did not fire, with the numbers), and A1 as a documented limitation (VLC needs stop/play at a fresh run; no code).

**Interfaces:**
- Consumes: the names above. The code wins over this text on any mismatch: verify every quantitative claim against the source before writing it.
- Produces: guidance for the next session.

- [ ] **Step 1: Edit CLAUDE.md**

1. In **Commands**, extend the transmitter bullet with the following. Then add one sentence on hugo's alerts:
   - `transmitter offair on --reason … | off` and `transmitter budget [--raise-to <usd>]`. Both write `state/` directly and bypass the guard and the PUT budget.
   - `transmitter status`, which now shows the cost guard, the kill switch, the off-air flag and the active alerts.
   - The system unit `packages/transmitter/systemd/transmitter@.service`: `Type=notify`, `WatchdogSec=45min`, env file `/etc/transmitter/<user>.env`.

   hugo's alerts sentence: `[alerts]` in config.toml; `SMTP_USERNAME`/`SMTP_PASSWORD`/`NTFY_TOKEN` in the env file; dedupe in `~/.transmitter/alerts.json`; the dead-clock check on `<site_url>/live.m3u8`.
2. In the antenna bullet:
   - `npm test` now first checks that `src/pages.ts` is fresh (`npm run pages` regenerates it).
   - The deploy is still `npx wrangler deploy` (`--dry-run` first; `--var` overrides for the verification items).
   - Secrets are set with `wrangler secret put` (list them); `BILLING_ANNIVERSARY_DAY` is a committed var.
   - The committed `send_email` binding `ALERT_EMAIL` is unrestricted; the destination exists only as the `ALERT_EMAIL_TO` secret. Never put `account_id` or an address in `wrangler.jsonc`; a test enforces this.
3. In **What this is**, after the antenna sentences, add one paragraph covering:
   - the guard runs first in every invocation;
   - it evaluates every 15 minutes through the account-scoped GraphQL API, prices through the allowances including the $5 base, and projects per meter from the last 3 hours;
   - the `tripped` latch: spend at actual ≥ 90% or projected ≥ 100% of `MONTHLY_BUDGET_USD`; blind after 6 h without a reading;
   - `blocked = tripped OR offair` is reconciled every invocation (ENDLIST, off-air `index.html`, the kill switch found by description), with an etag-conditional PUT so a trip is never lost;
   - an unreadable state means the invocation writes nothing;
   - alerts go out after the last playlist write, and the clock line logs `guardMs`;
   - VLC needs stop/play at a fallback→live switch of a fresh run (`EXT-X-DISCONTINUITY-SEQUENCE` restarts at 0): a documented limitation;
   - the spend bounds (`MAX_PUTS = 10` etc.) are unchanged.
4. Change "(phase 1 built; the cost guard, scheduler and full player are phases 2–4)" to "(phases 1–2 built; the scheduler and the full player are phases 3–4)".

- [ ] **Step 2: Add the approved as-built notes to the spec** (see Files above).

- [ ] **Step 3: Verify**

Run: `./.venv/bin/python -m pytest -q && (cd antenna && npm test)`
Expected: both PASS.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/superpowers/specs/2026-10-09-playout-design.md
git commit -m "docs: CLAUDE.md and spec as-built notes for playout phase 2"
```

---

## Phase-1 deferred items folded in, or left

The sources are `final-review/handback.md` and `final-review-deferred.md`.

**Folded in:**

| Item | Where it went |
|---|---|
| Phase 2's dead-clock check should notice `fallback_version: null` | The cloud alert `offair-without-fallback` (Task 8), plus hugo's publish gate (phase 1). The dead-clock check also alerts on a stale or empty playlist (Task 14). |
| Collapse the per-tick `ALERT publish: PUT … failed` | Dedupe per code (Task 13). |
| Kill-switch verification vs allowlist (Minor 7) | `index.html` becomes the off-air page while blocked (Task 7/8), and an already-playing page detects the 403 (Task 11). |

**Left deferred, with reasons:**
- **M4, fold the publish lock/guard/state/epoch preambles.** The new phase-2 writers deliberately bypass the guard and the lock (R7), so the risk M4 named does not grow.
- **Minor 6, exercise live↔fallback with real players.** Amendment A1 was rejected: VLC needing stop/play at a fresh run is a documented limitation (runbook section 7, spec note), and hls.js and Safari already follow the switch.
- **D5, the floor(N/len)+1 spec deviation.** Phase 1's numbering stays as built (A1 rejected), so the deviation stands as phase 1 documented it.
- **Minor 4, manual `plan`/`render` take no lock against `run`.** This is an ops convenience: the runbook already forbids it, and it is not on the spend path.
- **Minor 5, invalidate the analysis cache.** A render concern, not phase 2.
- **Minor 13, `row_analysis` under the flock.** As ruled.
- **All "minor (deferred)" items from Tasks 1–19 of phase 1.** The final review triaged these as defer/none, and none touches phase-2 code.

## Out of scope here (phases 3–4) and the seams left for them

- **Phase 3.** The scheduler; window misses and their hugo alert; `status` anchors, misses and empty-anchor warnings. `status` prints the placeholder line `anchors none (…phase 3)`. `alerts.alert()` takes any code, so `window-miss` needs no new plumbing.
- **Phase 4.** `index.html` per show (Open Graph at show boundaries). `src/indexpage.ts` is the one writer: it chooses between the two bundled pages today, and phase 4 renders the player page from a template with the show on air, so the HEAD/`sha256` reconcile stays. Also phase 4: the full player and embed, and the Playwright smoke test.

---

## Self-review (against the spec)

**Spec requirement → task:**

| Spec (phase 2) | Task |
|---|---|
| Guard in the clock Worker, first in every invocation, its own try/finally | 6, 8 |
| Evaluates when guard.json's evaluation is ≥ 15 min old, not on a minute modulo; any exception there is a failed reading | 4 (`shouldEvaluate`), 6 |
| Blind rule and reconciliation in the finally, every invocation; playlist and index.html work follow | 6, 8 |
| GraphQL account-scoped: Workers requests, R2 Class A/B ops, R2 storage; read-only token as a Worker secret; CPU not metered | 3, 6, 17 |
| Price table in antenna's config incl. the $5 base; current billing period from the UTC anniversary | 2, 1, 6, 8 (a committed var, R12) |
| Projection per meter from the last 3 h, through the allowances | 2 |
| Alerts at actual or projected 50% / 80% | 6 (`guardConditions`), 9 |
| `tripped` set: actual ≥ 90% or projected ≥ 100% (spend), or no reading for `blind_after` 6 h (blind); a successful over reading always leaves/sets spend | 4 |
| Cleared only: blind by the first successful reading under; spend at a new period or after a raise, only if the next evaluation is under; nothing else | 4 (R3) |
| `transmitter budget --raise-to` writes `state/budget.json {budget_usd, expires: period end}` | 12; 4 and 6 ignore a raise that outlives the period |
| `offair` owned by the operator; `transmitter offair on\|off`; the guard never writes it; `off` clears only the flag | 12, 6 |
| Blocked = tripped OR offair, reconciled every invocation: ENDLIST playlist, off-air index.html, kill-switch WAF rule | 6, 7, 8 |
| Level-triggered: reads the rule's actual state, corrects it (and alerts a hand toggle it undid); a Rulesets API failure alerts (deduped) and retries next run | 5, 6, 9 |
| Cloud alerts: thresholds, tripped, Rulesets failures, lead below floor; ntfy + Email Routing send-email to a verified address; deduped in `state/alerts.json` | 6, 8, 9, 10 |
| hugo alerts: station-root marker missing, render or publish errors, daily PUT budget exceeded (window misses → phase 3, R17); SMTP + ntfy | 13 |
| Dead clock: fetch the public live.m3u8 once a minute, alert when stale (~3·d → 120 s ×2, R4) or guard.json older than ~30 min (45 min here, R4); optional Worker-error notification | 14, 17 |
| systemd: Restart=always, WatchdogSec, journald; secrets in an env file readable only by the service user; analytics/WAF tokens as Worker secrets | 15, 17 |
| `transmitter status`: on air, lead, next anchors/misses/empty-anchor warnings (phase 3), tripped (reason), offair, active alarms | 16 |
| Testing: guard-first ordering and its finally; pricing; projection; tripped set/clear per reason; offair independence; WAF reconciliation and API-failure retry; rollover and raise; canned GraphQL | 2–8 |
| Testing (transmitter): the dead-clock alert | 14 |
| Phase-2 gate: not shared publicly before it ships | 17 (checklist + runbook intro) |
| Phase-1 findings 1–5 | A1 (a documented limitation) → 17, 19; A2 → 11; A3 → 10; A4 → 18; A5 → 3, 5, 6 |

**Placeholder scan.** No "TBD" or "similar to Task N". The deliberate placeholders are the account-detail ones (`<host>`, `<user>`, `<zone>`, `you@example.com`, `<your-topic>`), as the stakes require.

**Type consistency.** The plan text comes from one scratch build of the end state; all of it passed:
- antenna: 13 test files, 137 tests; `tsc --noEmit` clean.
- transmitter: 346 tests on CPython 3.14 and on 3.11.
- The intermediate Task 1 state was built and run separately (5 files, 51 tests).
- The Task 18 variant was built and run separately (antenna 139 tests).

The names checked across tasks:
- `GuardOutcome` (6 → 8);
- `AlertCondition` and its `once` (6 → 8, 9);
- `effectiveBudget(…, periodEndMs)` (4 → 6);
- `mergeLostRace` (6);
- `reconcileIndex` (7 → 8);
- `ClockResult.guardMs` and `startedMs` (8 → 18);
- `cloudstate.*` (12 → 16);
- `Dispatcher`/`dispatcher_from_config`/`active_codes` (13 → 16);
- `DeadClockMonitor`/`open_monitor` (14);
- `Runner(monitor=, notify=)` and `publish_all(notify=)` (14 → 15).

**Review Focus.** Each of the five lines names its pinning test. They are in Tasks 5, 6, 8 and 11.
