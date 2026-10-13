# t9-impl handback: Task 9, cloud alerts (dedupe, ntfy, email)

Status: DONE_WITH_CONCERNS (the concerns are review notes, not blockers)
Commit: 733439f feat(antenna): cloud alerts deduped in state/alerts.json, sent to ntfy and Email Routing
Tests: `cd antenna && npm test && npx tsc --noEmit`: 13 files, 197 tests pass; tsc clean. 11 of 11 mutants caught by the test predicted for each.

## What I implemented
- `antenna/src/alerts.ts`: the brief's module (ALERTS_KEY, COOLDOWN_MS, AlertEntry/AlertState/Outgoing, planAlerts, Channel, ntfyChannel, rawEmail, EmailBinding, emailChannel, AlertEnv, channelsFromEnv, repeatMsFromEnv, dispatchAlerts, alertSink), plus the rulings:
  - A (R16): `planAlerts(..., batch = {complete:true, guardComplete:true})` and `dispatchAlerts(..., batch = same)`. When a batch is incomplete, an active key that is absent from it is copied through unchanged: no "resolved", no cleared_at, so no cooldown starts. Present conditions are still sent and repeated. `alertSink` returns `(conditions, nowMs, batch) => Promise<void>` (the shape of ClockDeps.alerts) and passes the batch through.
  - B (R19): exported `CLOCK_KEYS` (explicit set), `keyFamily(key)`. Guard-family keys are an explicit set plus `/^budget-\d+:/`. A key in neither family counts as clock-family. An absent key resolves when `batch.complete || (batch.guardComplete && keyFamily(key) === "guard")`.
  - D (redaction): exported `redact(text, values)` removes `/zones/<x>`, `/accounts/<x>`, `/rulesets/<x>` (but not `/rulesets/phases/`), `/rules/<x>`, any bare 32-hex token (the shape of every CF account, zone, ruleset and rule ID), and each configured value of 8+ characters. It runs inside each channel (the ntfy Title header and body, the email subject and body), so every off-account channel gets it. The configured values are CF_ACCOUNT_ID, CF_ZONE_ID, CF_ANALYTICS_TOKEN and CF_WAF_TOKEN, which AlertEnv now declares (optional) so channelsFromEnv can read them. The console `alert` line and the guard's own text keep the IDs.
  - E: `RESOLVED_NOTE["guard-state-corrupt"]` adds: "state/guard.json reads cleanly again; any spend trip it caused stays until a raise or a new billing period."
- `antenna/src/clock.ts`:
  - B: `AlertBatch` gains `guardComplete: boolean` (doc comment extended). runClock sets it as soon as the guard returns a non-null `blocked`, so it is false on unknown or crash. `logAlerts` logs it.
  - C (R18): a `failureNamed` flag is set by `failedInputs` (clock-inputs). The outer catch pushes `clock-failed` (urgent, resolvable, "Clock invocation failed", message carries the error) when the flag is unset, before the ClockError is built. It therefore lands in the flushed incomplete batch and in `partial.alerts`.
- `antenna/src/env.ts`: extends AlertEnv. `antenna/src/index.ts`: `alerts: alertSink(bucket, env, fetchFn, now)`. I kept the existing ClockError partial-result handling, which is newer than the brief's copy of index.ts.
- `antenna/wrangler.jsonc`: ALERT_REPEAT_HOURS "6" and STATION_NAME "llama radio", with the brief's comment. No address and no account detail.
- `antenna/worker-configuration.d.ts`: regenerated with `npx wrangler types`, which is local and offline. The diff is only the two new vars and the hash.
- `antenna/test/alerts.test.ts`: the brief's tests verbatim, plus tests for A, B, D and E and the two retry fixes. `antenna/test/clock.test.ts`: three new tests (guardComplete; clock-failed on a failing playlist PUT; no clock-failed after clock-inputs). I also extended the default-sink test with `guardComplete`. `noSecrets()` in the scheduled-handler tests now also unsets NTFY_URL/NTFY_TOKEN/ALERT_EMAIL/ALERT_EMAIL_FROM/ALERT_EMAIL_TO, so a future antenna/.dev.vars cannot make a test POST to ntfy.

## Deviations from the brief
1. **A failed new alert is retried the next minute.** The brief restored `last_sent_at` to prev's value. For a condition that comes back after the cooldown, that is the PREVIOUS episode's send time, often less than 6 h old, so the retry would wait up to ~6 h. Now any failed alert or repeat sets `last_sent_at: null`, which makes it due at once (it goes out as kind "repeat"; the channel text is the same apart from resolved). Pinned by "a failed alert for a condition back after the cooldown is retried the next minute".
2. **A failed "resolved" notice is retried.** The brief marked the entry inactive anyway, which broke the "a message no channel accepted ... the next invocation retries it" rule. Now prev's (still active) entry is restored. Pinned by "a resolved notice no channel accepted is retried the next minute".
3. `channelsFromEnv` takes an optional 4th `Message` constructor (default EmailMessage), and `ntfyChannel`/`emailChannel` take a trailing optional `secrets` list. All are additive, so the brief's call shapes still work. I did this so the redaction test can drive the real env-to-channel wiring with a fake EmailMessage.
4. The rulings beyond the brief (A to E) are as above.

## Condition keys planAlerts can see (F), verified against src
None is missing from both families. Every `key:` literal in src/guard.ts, src/conditions.ts and src/clock.ts is classified.

| key | family | priority | status |
|---|---|---|---|
| tripped-spend | guard | urgent | resolvable |
| tripped-blind | guard | urgent | resolvable |
| budget-50:<period-start>:<budget> | guard | default | once |
| budget-80:<period-start>:<budget> | guard | high | once |
| guard-reading-failing | guard | high | resolvable |
| guard-unknown | guard | high | resolvable |
| budget-unreadable | guard | high | resolvable |
| offair-corrupt | guard | high | resolvable |
| budget-file-invalid | guard | high | once |
| guard-state-corrupt | guard | urgent | resolvable (special resolved wording, E) |
| waf-api | guard | high | resolvable |
| waf-corrected | guard | high | neither: not resolvable and not once. An event: sent on first appearance, never "resolved"; a return within 15 min of clearing is continuing |
| guard-write | guard | high | resolvable |
| guard-crashed | clock | urgent | resolvable |
| index-write | clock | high | resolvable |
| clock-inputs | clock | urgent | resolvable |
| horizon-missing | clock | default | resolvable |
| horizon-refused | clock | urgent | resolvable |
| lead-low | clock | high | resolvable |
| offair-without-fallback | clock | high | resolvable |
| clock-failed | clock | urgent | resolvable (new, R18) |

## TDD evidence
- RED (alerts): `cd antenna && npx vitest run test/alerts.test.ts` gave `FAIL test/alerts.test.ts ... Error: Cannot find module '../src/alerts'` (no tests run).
- RED (clock): `npx vitest run test/clock.test.ts` gave `× guardComplete is true ...`, `× a failing playlist PUT raises the catch-all clock-failed ...` (`expected [ 'tripped-spend' ] to deeply equal [ 'tripped-spend', 'clock-failed' ]`), `× the default sink logs the flag ...`, so `Tests 3 failed | 30 passed (33)`. The clock-inputs no-double test passed at RED, since there was no clock-failed yet; mutant M4 shows it is load-bearing.
- GREEN: `npx vitest run test/clock.test.ts test/alerts.test.ts` gave `Tests 57 passed (57)`.
- Full: `npm test && npx tsc --noEmit` gave `Test Files 13 passed (13)`, `Tests 197 passed (197)`, tsc clean.
- Mutation, in a `git archive 733439f` scratch copy run from that copy's dir; each mutant failed exactly the predicted test(s):
  M1 clearedIn always true: 4 incomplete-batch/family/alertSink tests. M2 ntfy body unredacted and M3 email body unredacted: the WafError redaction test. M4 failureNamed never set: both existing clock-inputs tests plus the no-double test. M5 spend-level pattern dropped: the classify test. M6 resolved not restored: the resolved-retry test. M7 the brief's last_sent_at restore: the after-cooldown retry test. M8 note dropped: the guard-state-corrupt wording test. M9 guardComplete never set: the guardComplete, clock-failed and default-sink tests. M10 hex rule dropped: the redact unit test and the WafError test. M11 literal-value redaction dropped: the redact unit test.

## Self-review / concerns
1. **guard-unknown does not always mean an unknown outcome.** guard.ts raises it at two sites. The R2 read failure gives `blocked: null`, so guardComplete is false. The post-unblock re-check failure (`raceUnknown`) returns a KNOWN outcome (`blocked: true`), so guardComplete is true and guard-unknown is present in that batch. Behaviour is still correct: it is active there and resolves on the next guard-complete batch where it is absent. The brief's phrase "arise exactly when the guard did NOT return a known outcome" is only true of the first site; the runbook should not repeat that phrase.
2. **guard-crashed is clock-family (per the ruling)**, so it stays active until a complete batch, even after the guard recovers, for example while the horizon stays missing. This is the conservative side, as ruled.
3. **If alerts.json cannot be read (R2 get throws), dispatchAlerts throws.** The clock logs `alert-dispatch-failed` and nothing is sent that minute; the condition keys still appear on the clock line's `alerts`. That is the brief's design. During an R2 outage cloud alerts therefore go silent, and hugo's dead-clock monitor (R4) is the alert that covers it. Choosing instead to send undeduped every minute during an outage would be a design decision for the orchestrator. A corrupt alerts.json is treated as {} and overwritten over its etag.
4. Redaction is pattern-plus-configured-values. It catches Rulesets path IDs, any 32-hex token and the configured CF_* values. It would not catch a non-hex, non-path, unconfigured ID in free text; real CF IDs are 32-hex. The ntfy and email `from`/`to` are never placed in text.
5. waf-corrected is not resolvable and not once, so if it persisted (it cannot, being per-invocation) it would repeat every 6 h. It is listed above as "neither".
6. I did not touch Task 11's files (antenna/public/*.js, test/nowplaying.test.ts) and committed by explicit paths only.

---

# Fix round 1

Status: DONE
Commit: 9664254 fix(antenna): alerts review round 1 -- resolved waits out the cooldown, tolerant state, create-only, email timeout
Command: `cd antenna && npm test && npx tsc --noEmit` passes: 13 files, 207 tests (was 197); tsc clean.
Only antenna/src/alerts.ts and antenna/test/alerts.test.ts changed. Nothing in packages/transmitter/ or Task 11's files.

## What changed
1. **"Resolved" waits out the cooldown (ruled, option a).**
   - `AlertEntry` gains an optional `clearing_since`. Parsing tolerates it being missing or null (`== null`).
   - On a batch that is allowed to resolve the key (rulings A/B via `clearedIn`), an active non-once key that is absent gets `clearing_since = now`. The entry stays active, and nothing is sent.
   - While the key stays absent for less than COOLDOWN_MS, the entry is copied unchanged. At COOLDOWN_MS or more, the entry goes inactive with `cleared_at = clearing_since` (when it was first absent), `clearing_since` is removed, and "resolved" is sent if the key is resolvable.
   - On a batch that may not resolve the key, the entry is copied unchanged, as before. The window neither starts nor runs on.
   - A return inside the window removes `clearing_since`. That counts as continuing: no alert, and `last_sent_at` and the repeat clock are untouched.
   - Because an inactive entry has, by construction, been absent for COOLDOWN_MS, a return after a delivered "resolved" is a new alert at once. A return when the entry has been clearing for COOLDOWN_MS or more with no batch in between is also a new alert; this keeps brief test 3 unchanged.
   - Once-conditions keep their immediate deactivation, with no window.
   - **Ruled deviation:** brief test 1 now expects no send on the first absent minute (entry active, with `clearing_since`) and "resolved" at +COOLDOWN_MS. I updated other tests the same way: the incomplete-batch, guardComplete, neither-family and guard-state-corrupt wording tests, the two dispatch retry tests, and the alertSink test.
   - **Interaction with the retry deviation:** a failed "resolved" still restores prev's entry (active, `clearing_since` kept), so the next allowed minute retries it. Pinned in "a resolved notice no channel accepted is retried the next minute", which now also asserts the restored entry.
2. **Non-object entries are dropped.** `validState()` keeps only non-null, non-array object entries, and a non-object document reads as {}. Test: `{stale:null,n:3,a:[1],s:"x"}`, `[null]`, `null` and `7` each still send `tripped-spend`, and alerts.json is rewritten clean.
3. **The first write is create-only.** When the read was absent, `createAlerts` calls `createJson` (`onlyIf: {etagDoesNotMatch:"*"}`). If the store refuses the precondition outright, it falls back to an unconditional `putJson`, the same idiom as the guard's `writeGuard`. A refused create (false) behaves like any lost race. Test: the first write's onlyIf is create-only and the second is etag-conditional. When an overlapping writer creates the file between our read and write, there is no throw, theirs stands, and our send is re-planned and resent next minute (a duplicate, not a loss).
4. **An alert that was never delivered is dropped, not resolved.** When clearing completes for an entry with `last_sent_at === null`, the entry is deleted and nothing is sent. Tested at planAlerts level and through dispatch (a broken channel at T0, then an ok channel: no sends, and alerts.json is `{}`).
5. **The email send has a timeout.** `emailChannel` takes a trailing `timeoutMs = 10_000` and races `binding.send` against a timer, clearing it in `finally`. A timeout throws `email: send timed out after N ms` and counts as a channel failure. Test: a never-resolving binding with an injected 5 ms timeout rejects `/timed out/`, and dispatchAlerts returns `{sent:0, failed:1}`.
6. **The redaction integration test now pins literal values.** `CF_ACCOUNT_ID = "acct-5e1d0042"` (8 or more characters) appears in the PATCH error text. The test asserts the guard's message contains it and that neither the ntfy nor the email text does.
7. **The test sender is `radio@example.org`.**

## New tests (antenna/test/alerts.test.ts)
- "planAlerts: resolution waits out the cooldown (ruled, fix round 1)":
  - flap inside the window: `["alert@0","repeat@360"]` with absences at minutes 1–4, 40 and 200–201. This is the reviewer's probe plus extra flaps.
  - a key absent for COOLDOWN_MS sends "resolved" exactly once: `resolved@16`.
  - after a delivered "resolved", a return is a new alert at once.
  - on incomplete batches the clearing window neither starts nor runs on: `resolved@45` when batches 1–29 are incomplete; `resolved@40` when clearing started and later batches were incomplete.
  - once-conditions are unaffected.
  - an alert never delivered is dropped, not resolved.
- dispatchAlerts:
  - an undelivered alert that clears is dropped, through dispatch;
  - non-object entries are dropped;
  - the first write is create-only, and a refused create loses nothing;
  - a hung email binding times out and counts as a failure.

## Mutants
Run in a `git archive 9664254` scratch copy from that copy's dir. Each expected red test was named in the script before the run, and every result matched it exactly.

| Mutant | What it breaks | Red tests |
|---|---|---|
| F1 | resolves on the 2nd absent minute (`< 0`) | flap; resolved exactly once; return after resolved; incomplete-window |
| F2 | a return keeps `clearing_since` | flap |
| F3 | incomplete batches start clearing | incomplete-window; resolves-nothing-absent; guardComplete family; neither family; alertSink |
| F4 | an undelivered entry is resolved | both undelivered tests |
| F5 | no fresh alert after a long clearing | brief test 3 (cooldown continuing) |
| F6 | no email timeout | hung binding test |
| F7 | unconditional first write | create-only test |
| F8 | no entry filter | non-object entries test |
| M11 (rerun) | literal-value redaction removed | redact unit test AND the WafError integration test (item 6 now pins it end to end) |

---

# Fix round 2

Status: DONE
Commit: 24bb50b fix(antenna): alerts review round 2 -- a failed repeat never drops a delivered episode's resolved
Command: `cd antenna && npm test && npx tsc --noEmit` passes: 13 files, 210 tests (was 207); tsc clean.
Only antenna/src/alerts.ts and antenna/test/alerts.test.ts changed.

## What changed
1. **Delivery is recorded explicitly (the Important regression).**
   - `AlertEntry` gains an optional `delivered`. Read it through `wasDelivered(e) = e.delivered ?? (e.last_sent_at !== null)`; that fallback is the ruling for older entries.
   - planAlerts sets `delivered: true` on a planned new alert or repeat.
   - On a failed send, dispatch sets `last_sent_at: null`. It also sets `delivered: false` if the failed send was kind "alert" (a new, undelivered episode). If it was a "repeat", it sets `delivered` to `wasDelivered(prev entry)`. So a delivered episode stays delivered across failed repeats. A never-delivered alert, which is retried as kind "repeat", stays undelivered because its prev entry says false.
   - The clear-time drop rule is now `!wasDelivered(e)`, no longer `last_sent_at === null`.
   - When a repeat keeps failing, `next` is still byte-identical to `prev`, since the key order is unchanged. So there is no write churn.
2. **The comment is fixed.** It now says an incomplete batch neither starts nor resets the clearing window, that the window's elapsed time is wall-clock from the first allowed absence, and that it may therefore complete on the next allowed batch.

## Covering tests (antenna/test/alerts.test.ts, dispatchAlerts / planAlerts)
- "a failed repeat of a delivered alert keeps it delivered: its resolved still goes out (P1)": the reviewer's P1 sequence. Alert delivered at T0, repeat fails at T0+6h (stored `{last_sent_at:null, delivered:true}`), then absent from +1m with healthy channels. Received `["alert:tripped-spend","resolved:tripped-spend"]`.
- "an alert whose first send and retry both failed is still undelivered: dropped on clear, no resolved": stored `delivered:false` after a failed retry sent as kind "repeat"; nothing is sent, and alerts.json is `{}`.
- "an older entry without `delivered` counts as delivered when a send was recorded": "resolved" goes out.
- The existing never-delivered tests (planAlerts-level and through dispatch) stay green. The planAlerts-level one is the legacy no-field case with `last_sent_at` null.

## Mutants
Run in a `git archive 24bb50b` scratch copy from that copy's dir, with the red test named before each run. All matched.

| Mutant | Change | Red tests |
|---|---|---|
| G1 | drop rule back to `last_sent_at === null` | the P1 test |
| G2 | a failed repeat sets `delivered:false` | the P1 test |
| G3 | legacy fallback `?? false` | the legacy test |
| G4 | a failed alert sets `delivered:true` | both undelivered-through-dispatch tests |

---

# Fix round 3

Status: DONE
Commit: 7f30c7b fix(antenna): alerts review round 3 -- a failed alert over a still-active episode keeps its delivery
Command: `cd antenna && npm test && npx tsc --noEmit` passes: 13 files, 213 tests (was 210); tsc clean.
The commit holds only antenna/src/alerts.ts and antenna/test/alerts.test.ts (checked with `git show --stat`). Task 13's uncommitted transmitter changes in the worktree were left alone.

## Change
On a failed send, dispatch now sets
`delivered: o.kind === "alert" && !prev[o.key]?.active ? false : wasDelivered(prev[o.key])`
(the reviewer's validated line; the comment explains the cases).
- A failed alert over a still-ACTIVE episode inherits that episode's delivery. Such an episode is one whose clearing window aged out after a failed "resolved", or across incomplete batches.
- A failed alert over an absent or inactive prev still starts an undelivered episode.
- An active prev that was never delivered still gives false.

## Tests (alerts.test.ts, under dispatchAlerts, "a failed fresh alert over a still-active delivered episode keeps it delivered")
- **P6:** the reviewer's sequence. Delivered at T0; "resolved" fails at +16m; the fresh alert fails at +17m (stored `{active:true, delivered:true, last_sent_at:null}`); re-clears from +18m; healthy at +33m. Received `["alert:tripped-spend","resolved:tripped-spend"]`.
- **P7:** the reviewer's sequence. Delivered at T0; complete absent at +1m; incomplete batches from +2 to +20m; the fresh alert fails at +21m; absent with healthy channels from +22 to +37m. Received alert then resolved.
- **Control:** after a DELIVERED "resolved", a failed return starts an undelivered episode (`delivered:false`), and its re-clear sends no second "resolved".
- RED before the fix: `npx vitest run test/alerts.test.ts` gave `× P6`, `× P7`, `Tests 2 failed | 38 passed (40)`; the control was green. GREEN after: 40/40 there, 213/213 in the full suite.

## Mutants
Run in a `git archive 7f30c7b` scratch copy from that copy's dir, with the red test named first.
- **H1:** back to `o.kind === "alert" ? false`. Predicted P6 and P7 only; red: P6 and P7 only (2 failed, 38 passed).
- **H2:** a failed alert always inherits `wasDelivered(prev)`. My first H2 replacement produced a syntax error ("no tests"), so it is not counted as a result. Corrected, H2 was predicted to turn only the control red, and only the control went red (1 failed, 39 passed).
