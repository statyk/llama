VERDICT: READY WITH FIXES

Range ccf0f16..01186ea (34 commits), worktree /Users/shawn/projects/llama/.claude/worktrees/playout-phase2, read-only; no commits, no stash, no deploy, no network. Reviewed in five passes (log: $D/final-review/final-review.log): (1) antenna guard/latch/waf/bucket/conditions/period/meter/pricing/clock/index/alerts, (2) antenna player + test support + wrangler config, (3) transmitter cloudstate/deadclock/sdnotify/service/cli/alerts/publish/config/unit, (4) runbook, (5) public-repo sweep and the deferred-minor greps. Mutants ran only in a scratch `git archive` of `antenna/` (removed afterwards).

Reason for the verdict: no Critical finding. The spend surface holds everywhere I traced it (unknown state writes nothing; a lost race never loses a trip; missing secrets throw before any network call; the kill switch is matched by description and refused when ambiguous or not a block rule; MAX_PUTS/d-refusal/75 s clamp intact). Three MUST-FIX items are OPEN, all small: two missing test pins on correct code (items 1 and 3, both proven by a surviving mutant and a probe that catches it) and the unguarded `AbortSignal.timeout` in the player (item 2). Plus four one-line doc fixes on the checkpoint checklist.

### MUST-FIX 1-4

**1. (T6) Blind still trips while `state/budget.json` gets keep throwing -- OPEN (test pin missing; code correct).**
Code: `antenna/src/guard.ts:268` gates only the evaluation on `!budgetReadFailed`; `applyBlindRule` runs unconditionally in the `finally` at `guard.ts:282`, and `evaluated_at` is not advanced, so blind counts from `last_success`/`since`. The committed test `guard.test.ts:447` covers a single throwing minute and the next minute's recovery, never the 6 h case.
Mutant A (scratch): `if (!budgetReadFailed) doc = applyBlindRule(...)` -- prediction "all 39 guard tests stay green": **39 passed**. My probe ("blind still trips 6 h after the last success while state/budget.json gets keep throwing": seed `failGets.add(BUDGET_KEY)`, step at T0, step at T0+6h+1min, expect `{blocked: true, tripped: true}` and `reason: "blind"`) is green on HEAD and **red under mutant A**. Fix: add that probe to `antenna/test/guard.test.ts` (the exact test is in the log and below under Checks run).

**2. (T11) `AbortSignal.timeout` guarded for pre-2022 browsers -- OPEN.**
`antenna/public/player.js:125` calls `AbortSignal.timeout(8000)` bare inside the probe's `try`. On iOS 15 / Safari 15 WebKit `AbortSignal.timeout` is undefined, the call throws synchronously, the catch swallows it, `status` stays 0, `classifyProbe` returns "unknown", and `StallWatch.verdict` resets the count: the mid-play kill-switch detection (amendment A2, Review Focus 5) silently never fires on those devices, while a fresh Play still works. No test can see it (player.js has none). Fix (3 lines): `const signal = typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function" ? AbortSignal.timeout(8000) : undefined;` then `fetch(STREAM, { cache: "no-store", ...(signal ? { signal } : {}) })`.

**3. (T9, spend surface) Test P10 -- OPEN (test pin missing; code correct).**
Code: `antenna/src/alerts.ts:348-349` keeps `wasDelivered(prev)` (false) for a failed "alert" over a still-active never-delivered episode; the re-clear then hits the `!wasDelivered(e)` arm at `:150` and drops the entry without a "resolved". No committed test exercises that arm (the describe block at `alerts.test.ts:434-485` covers delivered episodes only, and `:419` covers the "repeat" kind).
Mutant M1' (scratch, narrowed to the arm the t9-rerev3 sequence names): `delivered: o.kind === "alert" ? !!prev[o.key]?.active : wasDelivered(prev[o.key])` -- prediction "all 40 alerts tests stay green": **40 passed**. (My first, broader M1 -- `true` for any active prev -- was caught by `:419`, so that arm is pinned; the "alert"-kind arm is not.) My P10 probe (broken-channel alert at T0; absent on a complete batch at +1m; incomplete batches +2m..+20m; failed re-alert at +21m asserting `{active: true, delivered: false, last_sent_at: null}`; healthy absent +22m..+37m asserting `got == []` and state `{}`) is green on HEAD and **red under M1'**. Fix: add it as the fourth test of the `:434` describe block.

**4. (Ruling 18) `clock-failed` covers a failed playlist PUT and is not double-raised after `clock-inputs` -- CONFIRMED FIXED.**
`antenna/src/clock.ts:337-343`: the outer catch pushes urgent resolvable `clock-failed` only when `failureNamed` is false; `failedInputs` (`:253-259`) sets it. Pinned by `clock.test.ts:302` ("a failing playlist PUT raises the catch-all clock-failed ... in the flushed incomplete batch": keys `["tripped-spend","clock-failed"]`, batch `{complete:false, guardComplete:true}`, `partial.alerts` contains it) and `:318` ("a failure already named by clock-inputs does not also raise clock-failed": keys `[["clock-inputs"]]`). `clock-failed` is in `CLOCK_KEYS` (`alerts.ts:35-38`) and in the runbook table (`docs/playout-setup.md` 7.1).

### Findings

**Critical:** none.

**Important**

- I1. `antenna/public/player.js:125` -- MUST-FIX 2 above (mid-play kill-switch detection silently off on iOS/Safari 15; fix is a typeof guard).
- I2. `antenna/test/guard.test.ts` -- MUST-FIX 1 above: the blind backstop for the T6 I1 ruling ("a throwing budget read skips evaluation") is unpinned; a future edit gating `applyBlindRule` on the same flag would ship unguarded minutes while R2 is flaky on one key. Add the probe.
- I3. `antenna/test/alerts.test.ts` -- MUST-FIX 3 above: the never-delivered-episode arm of the failed-alert retry is unpinned; under M1' a `tripped-spend` the operator never received would get a "resolved". Add P10.

**Minor**

- M1. `packages/transmitter/src/transmitter/service.py:243` names the monitor step `"dead-clock"`, and `_step`'s generic handler (`:208`) alerts with the step name. An exception inside `DeadClockMonitor.check` (a bug, a corrupt `guard-cache.json` making `read_json` raise) therefore fires the LEVEL code `dead-clock` with a traceback message, indistinguishable from "the clock is dead", and it stays active until the monitor's own `resolve("dead-clock")` on a good read. Fail-loud, never silent, but the operator is told the wrong thing. Fix: name the step `"dead-clock-check"` (an event code; list it in the runbook's event codes), or catch in `check` and alert a distinct code.
- M2. `packages/transmitter/src/transmitter/publish.py:155-159` -- hugo's guard cache reads a corrupt or non-bool `offair.json` as `offair: None` (on air), while `antenna/src/guard.ts:231-238` treats the same bytes as off the air and enables the kill switch. Net effect: an unexpected-403 `dead-clock` alert on hugo after 17 checks with the text "kill switch left on?", alongside the cloud's `offair-corrupt`. Noise, fail-closed. Fix (two lines): mirror the Worker -- absent => False, `offair` bool => its value, anything else => True.
- M3. `docs/playout-setup.md:452` (N1) "any figure above the projected one": a raise must also clear actual/0.9 (trip = actual >= 90% OR projected >= 100%), or the next evaluation re-trips and consumes it. Say "above max(projected, actual / 0.9)" -- at the checkpoint the operator reads this line while tripped.
- M4. `docs/playout-setup.md:453` (N2) "Extra ... 80% alerts at $5.50 and $7 are expected": `budget-80:<period>:7` fires only if max(actual, projected) >= $5.60; with actual ~$5.05 it likely does not, and the checklist then reads as a failure. Say "50% at both, and 80% at $7 only if max(actual, projected) >= $5.60".
- M5. `docs/playout-setup.md:315` (N3) a Google App Password is displayed with spaces; `set -a; . env` then errors. Add "paste it without the spaces".
- M6. `packages/transmitter/tests_transmitter/test_systemd.py:45` says helpers.E "is far in the past"; `helpers.py:141-143` puts it in 2096 (the future). One word.
- M7. `packages/transmitter/src/transmitter/alerts.py:104` -- the ntfy Title predicate is latin-1, but http.client sends latin-1 bytes and ntfy reads UTF-8, so a latin-1 non-ASCII station name ("cafe" with an accent) arrives as invalid UTF-8; `str.isascii()` is the right predicate, and `Header(...).encode(maxlinelen=0)` avoids obs-fold on a long title. STATION_NAME defaults to ASCII and the runbook (6.2.6) says ASCII, so this is latent.
- M8. `antenna/src/guard.ts:123-132` (`mergeLostRace`) -- a loser whose `doc` is spend-tripped because it merely carried `prev`'s trip forward (its own evaluation was skipped, e.g. a throwing budget read) re-imposes that trip over a winner that legitimately CLEARED it at an evaluation under the thresholds with a raise. Fail-closed; self-heals at the merged document's next evaluation (<= 15 min, since `evaluated_at` is the winner's). Worth a comment next to the accepted one-minute-window residual; no code change needed for phase 2.

### Deferred-minor triage

| line | verdict | why / commit |
|---|---|---|
| T1 putJson etag-truthiness / first-creation race | already resolved | aba89a5 (create-only first write; `guard.ts:141-152`) |
| T1 corrupt read carries the etag unpinned | already resolved | aba89a5 ("pin that a corrupt read carries its etag") |
| T1 billingPeriod(NaN) returns NaN period | already resolved | `period.ts:16` `Number.isInteger(day)` refuses NaN (present since f13191c); `guard.ts:203` test pins a bad day failing loudly |
| T1 fakeFetch ignores Request-object input / non-string bodies | defer | `support.ts:79` now handles Request/URL input; non-string bodies still read as null -- no production caller sends one |
| T1 MemoryBucket failGets also fails head; puts() counts failed preconditions | defer | used deliberately (`clock.test.ts:141` HEAD failure); cosmetic test-support shape |
| T1 clock.test.ts playlistPuts duplicates MemoryBucket.puts | defer | `clock.test.ts:34` is a one-line alias; cosmetic |
| T1 period tests lack a leap-year case | defer | `anniversary()` uses `Date.UTC(y, m+1, 0)`; a 29 Feb anniversary is impossible for this account (day 11); add when touched |
| T2 analytics lag window counted in neither term | defer | ~0.01% of a projection that already trips at 100%; not a fail-open |
| T2 METERS/PRICES exported mutable | defer | no writer exists; `Object.freeze` when touched |
| T2 ALERT_LEVELS untested in pricing.test | already resolved | consumed and pinned in `conditions.test.ts:18-25` |
| T2 negated overThreshold not fail-closed for +Inf budget | defer | unreachable: `validBaseBudget` and `effectiveBudget` require finite |
| T3 errors-without-message fallback prints JSON | defer | cosmetic; still a failed reading |
| T3 15 s GraphQL timeout unpinned | defer | `meter.ts:125` sets it; only the value is unpinned; a hung POST delays one invocation (the Workers runtime bounds it anyway); no spend consequence |
| T3 pricing-page-only Class A types unpinned | defer | unknown types price as Class A (dearer) and are listed; fail-closed by construction |
| T3 missing actionType reported as "" | defer | cosmetic |
| T3 empty dataset reads as zero usage | defer | only in the first ~45 min of a period; projection then recovers |
| T3 metadataSize ?? 0 vs payloadSize throws | defer | comment-only |
| T3 five-mode error test lacks labels | defer | test cosmetics |
| T4 parseGuardDoc returns the raw object (unknown keys carried) | defer | harmless; the mirror in `cloudstate.guard_doc_problem` ignores extras too |
| T4 malformed raise (string budget_usd etc.) ignored silently | defer | the Worker ignores it (stricter budget); `transmitter budget` shows the verdict ("ignored: budget_usd is not a number", `cloudstate.py:211-217`), which is the operator's view |
| T4 StoredEvaluation.base_budget_usd unchecked | defer | `cloudstate.py:182` reads it defensively via `_finite` |
| T4 NaN base honours any raise even below $5 | defer | cannot unblock: an invalid base fails every evaluation (R11) |
| T4 latch.test.ts:213 dead reassignment | defer | not reproducible at HEAD (`latch.test.ts:208-216` has no loop reassignment); likely moved in c04c5ab |
| T5 null envelope -> TypeError not WafError | defer | still thrown before any PATCH; alerted as `waf-api` |
| T5 5 s timeout value unpinned | defer | `waf.test.ts:90` pins a live AbortSignal on both calls; the value is a constant |
| T5 post-PATCH verify checks only `enabled` | defer | the update resends action/expression/description verbatim from the GET; a changed expression would be the API's doing, and the checklist item "the PATCH kept the rule whole" covers it live |
| T5 found-0/found-2 refusal tests don't assert GET-only | defer | `killSwitch()` throws before any PATCH is constructed; cheap to add when touched |
| T5 note: WafError messages carry the request path | already resolved | 733439f: `alerts.redact` (`alerts.ts:170-181`) strips /zones, /rulesets, /rules and bare 32-hex from every channel; pinned in alerts.test |
| T6 corrupt-winner path raises guard-state-corrupt one minute late | defer | this run still reports tripped (`guard.ts:330-335`); the alert follows next minute |
| T6 note: waf-api alert text embeds the zone ID | already resolved | 733439f (redaction ruling D) |
| T6 note: guard-state-corrupt "resolved" wording | already resolved | `alerts.ts:60-63` RESOLVED_NOTE |
| T6 no test pins blind-while-budget-throws | **fix before merge** | MUST-FIX 1; probe supplied |
| T6 M1 fold case: waf-corrected text says blocked=false while outcome is blocked | defer | the text already says "or by an overlapping invocation"; the next minute re-enables and the outcome is blocked |
| T6 budget-unreadable not in R13 | already resolved | listed in `alerts.ts:43` and runbook 7.1 |
| T6 ok-but-malformed budget.json silently ignored | defer | same as T4 malformed raise |
| T6 corrupt-budget message renders $NaN with an invalid base | defer | only alongside the louder MONTHLY_BUDGET_USD problem |
| T7 "corrects a hand-uploaded index.html" asserts only the return | defer | `indexpage.test.ts:12-18` asserts body and metadata on the main path |
| T7 off-air page negative check only player.js | defer | one assertion; cosmetic |
| T7 unconditional index PUT race deserves a comment | defer | self-healing within a minute; comment-only |
| T8 worker-configuration.d.ts regenerated | already resolved | accepted at T8 |
| T8 ClockError without { cause } | already resolved | 12f796a: `clock.ts:82` declares `readonly cause` on the instance, which is what `{ cause }` sets |
| T11 note: end-to-end kill-switch latency ~55 s | already resolved | runbook checklist records the measured time against RF5's ~45 s |
| T11 backwards currentTime jump delays progress registration | defer | phase-4 player UX; never off-air |
| T11 permanent stall with a healthy station probes forever | defer | phase-4 player UX |
| T11 player.js has no tests | defer | phase-1 pattern; the pure helpers are tested -- but it is why MUST-FIX 2 slipped |
| T11 networkDetails.status in vendored hls.min.js unverified | already resolved | verified now: 34 occurrences of `networkDetails` in `antenna/node_modules/hls.js/dist/hls.min.js` |
| T11 AbortSignal.timeout on pre-2022 browsers | **fix before merge** | MUST-FIX 2 |
| T9 trailing batch default COMPLETE fails open for a future caller | defer | `alerts.ts:101` default is only for the brief's tests; the one production caller (`alertSink`) passes the batch |
| T9 STATION_NAME must be ASCII (runbook) | already resolved | runbook 6.2 step 6 |
| T9 budget-file-invalid once with a constant key | defer | safe direction (the raise is ignored, budget stays at base); `transmitter budget` shows "ignored: expires after the billing period ends" |
| T9 note: guard-unknown on a known outcome; R2 outage silences cloud alerts | already resolved | runbook 7 "Known limitations" |
| T12 note: guard-state-corrupt says --raise-to but the raise is refused | already resolved | runbook 7 "While guard.json is corrupt and readings fail" |
| T12 _iso_ok vs Date.parse differ on hand-edited `since` | defer | stricter side only (a refusal with a "retry" hint); hand-edited docs only |
| T12 json.loads accepts NaN/Infinity tokens | defer | every checked field rejects NaN via `_finite`; only an unchecked field (e.g. `period_to_date`) can differ, hand-edit only |
| T12 wording: offair off shape note; "(honoured)" with a malformed guard | already resolved | 4ff1126 ("honoured (period end unknown)"; CORRUPT line replaces the verdict) |
| T12 get_json catches only ValueError around body read | already resolved | 76e3c16 (`cloudstate.py:44-47`) |
| T12 _finite OverflowError on huge ints | defer | pre-existing, hand-edit only |
| T12 R7 test midnight window | defer | optional test hardening |
| T9 P10 test | **fix before merge** | MUST-FIX 3; probe supplied |
| T9 prev.active truthiness on hand-edited JSON | defer | conservative side |
| T13 note: docs for [alerts] keys | already resolved | runbook 6.1 step 4 table |
| T13 note: plan/render codes resolve only while filling | defer | a persisting plan failure while not filling shows a stale `plan` in status until the next fill; R16 as written |
| T10 note: playout-setup.md:195 deploy:assets | already resolved | 01186ea/ea3ca04 (section 4 step 3) |
| T10 vite/client widens ambient types | defer | brief's choice; tsc clean |
| T10 vite not an explicit devDependency | defer | needs `npm install`, which implementers may not run; hoisted via vitest today |
| T10 note: deploy:assets before/alongside the Worker deploy | already resolved | runbook section 4 step 3 ("On a fresh bucket ...") |
| T10 32-hex regex rejects a future KV id | defer | intended for a public repo |
| T13 ntfy Title isascii + maxlinelen=0 | defer | M7: latent while STATION_NAME is ASCII (runbook 6.2.6); fold into the fix wave if cheap |
| T13 plan-step resolve unpinned (mutant A); newer-wins merge unpinned (mutant D) | defer | `test_service.py:335` pins step-level resolves for station-root/render via the Dispatcher; mutant D's cost is a repeated "resolved" line after a failed write (disk full), loud not silent |
| T13 cool-down uses wall clock; one-shot event during cool-down is logged only | defer | the event re-fires on its next occurrence; bounded by 5 min |
| T14 corrupt/non-bool offair.json reads as on-air in the cache | defer (or fold, two lines) | M2 above: noise only, fail-closed |
| T14 dead-clock check skipped on fail-closed ticks; thresholds are tick counts | defer | plan wording; `publish-state` alerts cover the skipped tick |
| T14 note: site_url serves live.m3u8; WAF answers 403 | already resolved | checklist items "site_url serves the playlist at its root" and "confirm the WAF block answers 403" |
| T14 guard.json read failures timed from the first failure; timer restarts with the service | defer | alert arrives <= guard_stale_s late; loud either way |
| T14 empty str(exc) message nits; error-clears-but-still-stale untested | defer | cosmetic / test gap off the strict surface |
| T15 STOPPING=1 in run's finally unpinned | defer | SIGTERM skips the finally anyway; informational to systemd |
| T15 After=remote-fs.target without RequiresMountsFor; ExecStart venv path hard-coded | defer | runbook 6.1 step 2 says to edit ExecStart; a missing NFS mount is the `station-root` alert |
| T15 restore without cache/ may meet WatchdogSec | already resolved | runbook 6.1 step 5 |
| T15 no RED capture | defer | tests verbatim from the brief; mutants at review covered the behaviour |
| T15 test_systemd.py "far in the past" | **fix before merge** | M6, one word |
| T15 row_analysis docstring line runs long | defer | cosmetic |
| T16 cli._cloud re-loads the config | defer | harmless double read |
| T16 cloud_lines renders raw values loosely | defer | cosmetic |
| T16 pre-existing local readers traceback on corrupt bytes | defer | phase-1 code; `status` is read-only |
| T16 note: guard_summary field names vs guard.json | already resolved | verified by reading: `actual_usd`/`projected_usd`/`budget_usd`/`at`/`period.start|end`/`last_error`/`last_success`/`since`/`waf.enabled|error` all match `latch.ts` GuardDoc; `test_service.py:393` seeds them |
| T16 cli.status reader wrapper shadowed by cloud_lines' catch | defer | belt-and-braces; untested but cannot fail open |
| T16 nested parens / unknown base prints plain honoured | defer | cosmetic |
| T17 N1 raise above projected only | **fix before merge** | M3 |
| T17 N2 80% at $7 overstated | **fix before merge** | M4 |
| T17 N3 App Password spaces | **fix before merge** | M5 |
| T17 N4 way back: redeploy restores the cron | defer | `npx wrangler deploy` applies the committed `triggers` (crons `* * * * *`); add "(output ends `schedule: * * * * *`)" if cheap |
| T17 broken-Worker order: in-flight invocation; K15 full /etc path | defer | the runbook already says "a Worker that is still running would undo the rule within a minute" and to confirm no cron first |

### Rulings challenged

None. Specifically re-read and agreed: T6 I1 (a throwing budget read skips the evaluation; blind is the backstop -- now proven by mutant A + probe), T6 residual (one-minute unblocked window after a lost race -- documented in the runbook), T9 I1 (resolved only after a 15-min absence), ruling 18/19 (clock-failed; family-scoped resolution), T12 three-way raise floor (matches `applyAttempt` at `latch.ts:146-153`), T14 I2 (monitor-side timing of an unreadable guard), T15 I1 (prune pings, no mid-loop persistence), T16 H1 (CORRUPT line replaces the verdict), T2 negated `overThreshold`. One consequence of the T14 wiring, not a ruling, is M1 (the step named `"dead-clock"`).

### Declined to judge

- `antenna/worker-configuration.d.ts:1` carries a 32-hex `hash:` -- it is `wrangler types`' config hash, not an account, zone or token; the public-repo test scopes to `wrangler.jsonc`.
- hugo keeps publishing while `offair` is on (only `tripped` stops it): the spec's "stop while tripped" is about spend; off-air is cooperative on hugo's side by design.
- The ~55 s mid-play latency versus RF5's "~45 s": the checklist records the measured value; it is buffer-bound, not a defect.
- GraphQL sampling accuracy and the price table's currency (checked 2026-10-11 per `pricing.ts`): no network here; the checklist's "agreement within a few percent" item is the test.
- Phase-1 player code (`prefersNativeHls`, timeline lookup) and the show-page template: unchanged by this range.
- Tasks 18 and 19 (lookahead; CLAUDE.md/spec amendments): not in the range.
- `guard-unknown` reused for the post-unblock race re-check (`guard.ts:340`): the runbook names it a known limitation.
- R2's real `onlyIf` semantics on production: miniflare-only here; the checklist's first item says so.
- Every all-clear waiting out the 15-min cooldown: ruled (T9 I1) and in the runbook.
- The transmitter suites were not re-run in full (443 passed at T16/T17 per the brief); no transmitter doubt needed a test.

### Strengths

- The guard is genuinely guard-first with its blind rule and reconciliation in a `finally` (`guard.ts:281-320`), and `runClock` cannot write a byte before it returns (`clock.ts:224-241`; pinned by "runs the guard before reading or writing anything").
- Fail-closed is consistent on both sides of the seam: an unreadable or corrupt `guard.json` is a spend trip in the Worker and `blocked=True` on hugo (`publish.py:154`); a non-bool `offair.json` is off-air; missing secrets throw before `fetch`; `overThreshold` is negated so NaN trips.
- The persist path (`guard.ts:166-188`) merges a lost race rather than overwriting, keeps spend over blind, re-creates create-only after a delete, and reports its own trip even when the write is lost; every branch has a test.
- The Python mirror (`cloudstate.guard_doc_problem`, `raise_verdict`) tracks `parseGuardDoc`/`effectiveBudget` clause by clause, including JS's `true !== 1` (the `isinstance(bool)` guard), and the raise floor reproduces `applyAttempt`'s clear rule; timestamps cross the seam byte-identical (`grid.us_to_iso` = `toISOString()` format, verified).
- Redaction at the channel boundary, the no-network scheduled-handler tests (secrets forced unset, global fetch rejected), and the wrangler.jsonc public-repo test close the account-detail surface.
- The runbook's broken-Worker order (remove the cron, confirm, then enable the rule) and the "way back" are correct against the code, and the alert-key tables match `CLOCK_KEYS`/`GUARD_KEYS` and `LEVEL_CODES` exactly.

### Checks run

- Read: spec Stakes/Cost guard/Alerts/Phases/Testing; constraints.md (R1-R17, Global Constraints, Review Focus 1-5); plan task headers; final-triage.md; every `Ruling:` line of the three ledgers and task-9-rulings.md; the diff's commit list and stat; all antenna `src/*` touched (guard, latch, waf, bucket, conditions, period, meter, pricing, clock, index, env, indexpage, alerts), `public/player.js`, `public/nowplaying.js`, `test/support.ts`, `test/wrangler-config.test.ts`, `wrangler.jsonc`, `scripts/*`; transmitter `cloudstate.py`, `deadclock.py`, `sdnotify.py`, `alerts.py`, `systemd/transmitter@.service`, and the diffs of `service.py`, `cli.py`, `publish.py`, `pipeline.py`, `config.py`, `workspace.py`, `errors.py`; the full `docs/playout-setup.md` diff; test names on both sides and the bodies named in Review Focus 1-5 and the MUST-FIX items.
- Review Focus 1 (R2 unreadable): `guard.ts:196-203` returns `blocked: null`; `clock.ts:237-241` returns before any write; tests `guard.test.ts:112`, `:436`, `clock.test.ts:95`, `:104`. Confirmed by reading.
- Review Focus 2 (race): `guard.ts:117-188`; tests `guard.test.ts:211`, `:289`, `:301`, `:330`, `:339`, `:398`. Confirmed.
- Review Focus 3 (rule renamed/duplicated/not block): `waf.ts:56-65` refuses on `matches.length !== 1` or action != "block", before any PATCH; `guard.ts:302-308` keeps the decision and alerts `waf-api`; only `rules/{rule.id}` is ever PATCHed. Tests `waf.test.ts:53`, `guard.test.ts:171`, `:355`. Confirmed.
- Review Focus 4 (secrets): `guard.ts:73-81` records problems; `:272` and `:288` throw before `fetch`; blind after 6 h via `applyBlindRule`. Tests `guard.test.ts:161`, `:133`, `:487`, `:496`. Confirmed.
- Review Focus 5 (blip vs kill switch): `nowplaying.js:93-116`; tests `nowplaying.test.ts:133`, `:143` (the extended blip test asserts a second stall starts the count from zero). Confirmed for the pure helper; MUST-FIX 2 is the wiring gap.
- Spend bounds: `clock.ts:114-118` (`GRID_D`, `MAX_LOOP_MS`, `MAX_PUTS = 10`), `:157-159` `putCap`, `:199` clamp, `:273` refusal; `configFromEnv` `liveMaxAge >= 1`. Tests `clock.test.ts:394-446`. Intact.
- Seams: `cloudstate.guard_doc_problem` vs `latch.parseGuardDoc` (clause by clause, incl. bool-as-1, missing keys, NaN tokens); `raise_verdict`/`raise_budget` vs `effectiveBudget`/`applyAttempt`; `cloud_lines` offair reading vs `guard.ts:230-238` vs `publish.py:155-159` (M2); `CLOCK_KEYS`/`GUARD_KEYS` vs runbook 7.1 vs `LEVEL_CODES` vs runbook hugo codes; `deadclock.check` 403 logic vs the cache shape `publish.py:160-161`; ISO formats across the seam (`grid.us_to_iso` -> `2026-10-12T06:00:00.123Z`; V8 `Date.parse` of it and of 6-digit fractions both parse; `grid.iso_to_us` accepts the Worker's `.000Z`).
- Public-repo sweep over the diff's added lines: no email outside example.*/alerts@lma-radio.com, no `account_id`/`zone_id` keys, 32-hex only in test constants and the `wrangler types` hash.
- Scratch copy (`git archive HEAD antenna | tar -x`, node_modules symlinked, run from the scratch dir, removed afterwards):
  - baseline `npx vitest run test/guard.test.ts test/alerts.test.ts`: 79 passed.
  - mutant A (`guard.ts:282` -> `if (!budgetReadFailed) doc = applyBlindRule(...)`), predicted all green: `Tests 39 passed (39)` (guard.test.ts).
  - mutant M1 broad (`alerts.ts:349` -> `: true`), predicted green, actual: 1 failed (`an alert whose first send and retry both failed...`) -- the "repeat" arm is pinned; narrowed to M1'.
  - probes `test/probe-final.test.ts` (P10; blind-while-throwing) on HEAD: 2 passed.
  - mutants A + M1' with committed tests + probes: `2 failed | 79 passed (81)`, the two failures being exactly the two probes. Predictions matched.
  - Live worktree untouched throughout (`git status --short` empty at the end).
- Not run: full antenna/transmitter suites, tsc, Debian-12 gate (no doubt required them; the brief records them green at T16/T17).

Suggested test text for the two pins (TypeScript, drop-in to the named files; imports as in the existing tests):

```ts
// guard.test.ts, in "guardStep: races and failure paths beyond the plan's"
it("blind still trips 6 h after the last success while state/budget.json gets keep throwing", async () => {
  const bucket = new MemoryBucket();
  bucket.failGets.add(BUDGET_KEY);
  const c = cloud();
  const first = await step(bucket, c);
  expect(first.conditions.map((x) => x.key)).toContain("budget-unreadable");
  expect(bucket.json(GUARD_KEY)).toMatchObject({ tripped: false, evaluated_at: null });
  const later = await step(bucket, c, T0 + 6 * 60 * M + M);
  expect(later).toMatchObject({ blocked: true, tripped: true });
  expect(bucket.json(GUARD_KEY)).toMatchObject({ tripped: true, reason: "blind" });
});

// alerts.test.ts, fourth test of the describe at :434
it("P10: a failed re-alert over an active never-delivered episode stays undelivered: dropped on re-clear, no resolved", async () => {
  const { bucket, got, broken, ok } = setup();
  await dispatchAlerts(bucket, [broken], [cond("tripped-spend")], T0, REPEAT);
  await dispatchAlerts(bucket, [ok], [], T0 + M, REPEAT); // clearing, on a complete batch
  for (let m = 2; m <= 20; m++) await dispatchAlerts(bucket, [ok], [], T0 + m * M, REPEAT, { complete: false, guardComplete: false });
  expect(await dispatchAlerts(bucket, [broken], [cond("tripped-spend")], T0 + 21 * M, REPEAT)).toEqual({ sent: 0, failed: 1 });
  expect(bucket.json(ALERTS_KEY)["tripped-spend"]).toMatchObject({ active: true, delivered: false, last_sent_at: null });
  for (let m = 22; m <= 37; m++) await dispatchAlerts(bucket, [ok], [], T0 + m * M, REPEAT);
  expect(got).toEqual([]);
  expect(bucket.json(ALERTS_KEY)).toEqual({});
});
```
