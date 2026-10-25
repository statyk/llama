# Final whole-branch review: alert-noise (df17931..7ff372c)

Reviewer: Opus, read-only. I read the 364 KB diff in four passes: (1) the antenna sources (alerts.ts in full, plus clock, guard, metronome-core, conditions, index and wrangler.jsonc); (2) the transmitter sources (alerts, service, monitor, relay, deadclock, publish, pipeline, r2, cli, sdnotify, workspace); (3) the three docs; (4) the test diffs, checked for weakened or removed assertions and for the strict-surface tests the plan names. I ran no suites, as the brief asked: no reading raised a doubt that the existing runs leave open. I made no mutants and no commits, and I did not touch the working tree.

### Strengths

- **The gate's semantics match on both sides and follow the spec rule by rule.**
  - antenna: the streak advances on a presence, resets on an absence `clearedIn` allows, and is left alone on an incomplete batch. A pending-only entry is dropped on reset. A kept inactive entry keeps its history. A still-active entry whose clearing elapsed stays as it is, can still resolve, and is replaced at GATE.
  - transmitter: one observation per observer, counted at the first fire. `end_observation` resets only the codes declared by steps that ran. The observer of each code is derived from `STEP_CODES`/`OBSERVER_STEPS` and checked at import (`code_observers`), so a wrong table fails loudly instead of gating silently.
- **The strict surfaces hold.**
  - `GATED_KEYS` and `GATED_CODES` are exactly the approved lists, and every spend and off-air key is outside them (tests A and K; `test_each_ungated_code_sends_on_its_first_fire`).
  - `put-budget` reaches the Dispatcher only through `_report_stop`, never through the gated `publish` step handler. I traced every `PutBudgetExceeded` site in publish.py: all of them become `stopped="put-budget"`.
  - A text pin enforces that exactly two raise sites carry `immediate`.
  - No one-shot key can be swallowed: `gated()` excludes `once`.
- **No gate can silence a key forever.** An undelivered first message is resent at once and never re-gated, including the Q4 path, where a failed alert replaced a still-active episode. `first_undelivered` handles that path, and test U pins it.
- **The relay contract is the same on both sides.** The key, ring of 50, stream and seq, and the malformed-document rule match (one caveat on hand-edited floats, Minor 1). `test_relay_key_matches_antenna` reads alerts.ts. Email is sent before the relay write, and the relay write is bounded at 10 s for both attempts together. Delivered means email OR relay.
- **The Worker's R2 spend stays within bounds.**
  - The relay adds at most 2 PUTs and 1 GET per invocation that sends anything; with the gate that is a few a day.
  - alerts.json is written only while a streak is pending, because the streak is capped at GATE and the serialization is stable (test L).
  - `MAX_PUTS` is the playlist ceiling and is not affected. `state/` is not allowlisted, so the relay object is not public.
- **The monitor thread has a narrow surface.**
  - Its R2 access is get-only (`R2Reader` exposes only `get_json`, pinned), on its own client made on the main thread, with 5 s/10 s timeouts.
  - It never touches `guard_cache_path`; the single-writer pin is now widened to `atomic_write_text` and `.write`.
  - It never pings the watchdog (`monitor.py` does not import sdnotify, pinned).
  - All its network I/O runs outside the Dispatcher lock.
  - `run_pass` cannot raise. `_check_monitor` cannot raise (BM1 fixed). A failed `Thread.start()` leaves `stop()` harmless (BM2 fixed).
  - The tick's `finally` runs `_check_monitor` and then `end_observation` on every path, the failed lead read included. I found no new way for `run()` to end or the unit to restart-loop.
- **Watchdog.** `frames_of` pings in a `finally`, on the main thread only. It covers `plan_step` and render's re-plan path.
- **Python 3.11.** I found nothing newer than 3.11. `fromisoformat` with `Z` and milliseconds needs 3.11+, and the debian12 run covers it.
- **Docs.** Every constant I checked against the code matches: GATE 3, ring 50, 10 s, 1 h, 30 s, 60 s, 5 min, the cursor path, the ntfy priorities and tags, the body marker, and which codes are level codes. No doc still tells the operator to set an ntfy Worker secret.

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

1. **Incident runbook `monitor-stalled`, "Do" step (docs/playout-incident-runbook.md:217-221). This is RR1, and I would fold it before merge.**
   - **What's wrong:** `grep -E 'transmitter\.(monitor|relay)'` matches only the first line of each record. Under systemd, journald splits stderr on newlines, so a traceback's frame lines become separate entries without the logger name. The line Python prints when a thread dies, `Exception in thread transmitter-monitor:`, comes from `threading.excepthook`, not from a logger, so it never matches. The parenthetical "(a traceback, ...)" promises output this grep cannot show.
   - **Why it matters:** the next sentence reads silence as R2 latency. In the dead-thread case the grep is always silent, so the runbook points the operator at R2. Both cases go out as `monitor-stalled`, and only the message text tells them apart ("thread is not running" against "has completed no pass for N minutes"). The runbook does not say to read it.
   - **How to fix (docs only, no code re-review):**
     - use `grep -E -A20 'transmitter\.(monitor|relay)|transmitter-monitor'`;
     - add one sentence: if the message says "thread is not running", the thread died, so read the `Exception in thread transmitter-monitor:` block;
     - optionally widen "R2 latency" to "a slow network read (R2, the `live.m3u8` fetch, DNS)". getaddrinfo is not bounded by the socket timeouts, so DNS can stall a pass past them.

#### Minor (Nice to Have)

1. **A relay contract edge on a hand-edited float seq** (packages/transmitter/src/transmitter/relay.py:61-64, `doc_problem`).
   - **What's wrong:** a hand-edited `"seq": 2.0` is an integer to antenna, because `JSON.parse` makes it one. Python calls the whole document malformed. The plan's rule was "malformed exactly when antenna would".
   - **Why it matters:** the Worker keeps appending to such a document, while hugo logs a WARNING every minute and relays nothing until that entry slides off the 50-entry ring, which can take weeks. Only a hand edit can produce it.
   - **How to fix:** accept an integral float (`isinstance(v, float) and v.is_integer()`) and coerce it to int. Or leave it as is and document it.
2. **The relay does not detect a seq gap** (relay.py:163-166).
   - **What's wrong:** a cursor in the same stream that has fallen more than 50 messages behind loses the overwritten messages without a log line.
   - **Why it matters:** this is mostly harmless, since `RELAY_MAX_AGE_S` would skip most of them anyway.
   - **How to fix:** add one INFO line, "seq N..M fell off the ring", when `min(ring seq) > cursor.seq + 1`. Optional.
3. **The gate note is worded differently on the two sides.**
   - **What's wrong:** antenna says "(Alerted after 3 consecutive failing minutes.)" and transmitter says "(alerted after 3 consecutive failures)".
   - **Why it matters:** both satisfy rule 7 (the wording is the builder's), and the docs paraphrase both correctly. The asymmetry is only in AL1: transmitter keeps the note on a resend after a clean observation and antenna drops it.
   - **How to fix:** no action needed. Recorded so nobody "unifies" them into a wrong claim.
4. **The no-put test does not exercise the relay path.** The 4b strict-surface test builds `MonitorLoop` without a relay, so the relay's read-only behaviour is pinned by construction rather than by that test. `Relay` holds only a `get_json` callable, and `R2Reader` exposes nothing else, which is pinned. A pass with a real `Relay` over the same `FakeBucket` would close it for little cost. Optional.

### Triage of deferred minors, AL1, FU1, FU2

**AL1, FU1, FU2**

- **AL1** (antenna drops the gate note on a resend after a clean minute): OK as ruled. It is wording only; the message is still sent at once and never re-gated.
- **FU1** (`guard_view`'s `bool(doc and ...)`: a falsy non-dict guard.json reads as not tripped): not worse than recorded. It now also feeds the monitor's view, but the only effect there is the 403 branch counting toward its 17-check debounce. antenna turns such a document into a tripped `guard-state-corrupt` and overwrites it within about a minute, and hugo's PUT budget still bounds spend. Out of scope.
- **FU2** (relay skips messages on config-class ValueErrors): not worse than recorded. Email covers those messages, and the Dispatcher's own ntfy fails visibly on the same bad config. A startup `ntfy_url` check stays the right follow-up. Out of scope.

**Task 1**

- rule-7 edge (gated-start, failed, clean reset, resent without the note): OK to defer. It is AL1.
- rule-3 edge (a pending streak over a kept entry is lost when it ages out on an incomplete batch): OK to defer. It delays a send by at most 2 min and never silences one.
- test N loop is tautological: OK to defer. Literal-string tests pin the reasons.
- Q1 (same as test N): OK to defer.
- Q2 (no test for a gated first alert failing at GATE; storedStreak reads): already fixed (tests S and T).
- Q3 (header says "the one exception"): already fixed (the header now names two exceptions).
- Q4 (the delivered-inheritance path is re-gated): already fixed (`first_undelivered`, c5b519a, test U).
- Q5 (a comment reads unrealistically): OK to defer. Comment only.

**Task 2**

- rule-7 note dropped on the clean-minute resend: OK to defer. It is AL1.
- `msgs().slice(-RELAY_RING)` with more than 50 messages in one invocation: OK to defer. Unreachable, since the key inventory is under 50.
- next seq follows the ring's max seq, not its last: OK to defer. An accepted deviation, and the safer one.
- QM1 (`relayDocProblem` called twice; a redundant assertion): OK to defer. Cosmetic.
- QM2 (`alert-relay-failed` logs carry no keys or count): OK to defer. It would help `wrangler tail`; worth folding next time alerts.ts is touched.
- QM3 (inner slice untested): OK to defer. Theoretical.
- QM4 (no test for an R2 read failure inside the relay): OK to defer. The `try` covers it, and it would show as the existing alert-relay-failed path.
- QM5 (contrived 3-PUT path; the fallback put can overwrite a racer): OK to defer. It is the spec-mandated createAlerts pattern.
- QM6 (alerts.ts is 578 lines): OK to defer.
- QM7 (the resolved text says "active since" the failed episode's first_at): OK to defer. Cosmetic.

**Task 3**

- TM1 (observer routing hard-coded): already fixed (`code_observers`, `CODE_OBSERVER`).
- TM2 (lock tests hang on a deadlock): already fixed (daemon threads plus release in a `finally`).
- TM3 (wrapper test precision): OK to defer.
- TM4 (docstring mentions "the monitor thread" before 4b made one): already fixed. Moot now that the thread exists.
- TM5 (a test name over-claims): OK to defer.

**Task 4a**

- guard_view test is not parametrized: OK to defer.
- AM1 (a raising guard callable could stop the check): already fixed (`check()` wraps `guard_view()` and fails closed).
- AM2 (single-writer pin too narrow): already fixed (the regex covers `atomic_write_text` and `.write`).
- AM3 (cache test compares guard_view to itself): OK to defer.
- AM4 (a test name over-claims): OK to defer.
- AM6 (empty `str(exc)`): OK to defer. The deadclock wrapper now falls back to the type name; `guard_view`'s own `str(exc)` can still be "", which is cosmetic and still read as an error.

**Task 4b**

- a raising `stalled()` propagates out of tick: already fixed (BM1, 59bad2f).
- `code_observers` also refuses an undeclared gated code: fine. It is a strengthening.
- BM1: already fixed. BM2: already fixed. BM3: already fixed (`r2.error_code`).
- BM4 (the guard-cache half of the strict-surface test is near vacuous): OK to defer. Single-writer is pinned separately by text.
- BM5 (redundant assertion): OK to defer.
- BM6 (import shadowing): OK to defer. Cosmetic.
- BM7 (`started` stays True after `stop()`): OK to defer. Nothing reads it after stop.

**Task 5**

- RM1: OK to defer. It is FU2.
- QM1 (a same-stream cursor above the ring's max relays nothing): OK to defer. Hand edit or backup restore only.
- QM2 (a bad NTFY_TOKEN means one WARNING per message): OK to defer. Spec-mandated, and the Dispatcher's ntfy shows the same fault.
- QM3 (`monkeypatch.undo()` reverts the fixture): OK to defer.
- QM4 (urllib follows redirects on POST): OK to defer. Pre-existing and shared with the Dispatcher.
- QM5 (`error_code as _code` alias): OK to defer. Cosmetic.
- body marker `({key}, {at})`: accepted.
- cursor written only when it changes: accepted (spec Limits).
- 4b's no-put test has no relay: OK to defer (Minor 4).

**Task 6**

- the brief's systemd assertion was wrong in the plan: already fixed (corrected and commented).
- render_step's direct analyze is unpinged: OK to defer. The gap is one analysis (~8 min) plus one encode (10-20 min), well inside 45 min, and usually a cache hit.
- TQ1 (derived expected count): OK to defer. The derivation still catches both "no ping" and "double ping" mutants; adding the concrete count beside it would be nice.
- TQ2 (a near-tautological test): OK to defer. Its real job is "no error with `notify` None", and it does that.
- TQ3 (FailingEngine duplicates bookkeeping): OK to defer.

**Task 7**

- SM1 (the grep names a thread the log never shows): already fixed (7ff372c names the loggers). The grep is still incomplete; that is RR1.
- SM2 (the watchdog line lost the encode estimate): already fixed (~10-20 min encode, ~8 min analysis).
- SM3 (`station_name` row in the phase-2 table): already fixed. The row is labelled "(phase 1)".
- SM4 ("~27 min in all" reads as measured): already fixed. It now says the alert came at ~40 min because of the starvation.
- SM5 (a), (b), (c): already fixed. The "never the spend or off-air alerts" wording is in place, CLAUDE.md's "the fallback check sits before the first PUT" is unambiguous, and the docs say "at most 2 PUTs on a lost race".
- **RR1: MUST FIX before merge.** It is cheap and docs-only; see Important 1.
- RR2 (the §6.4 gap sentence assumes the Worker deploys first): OK to defer. If hugo updates first, the Worker's ntfy is 429-dead anyway, so "email only" holds in both orders.
- RR3 ("measured 10-23" overstates A2): OK to defer. Wording only.

### Declined to judge

- Player auto-retry: deferred by the operator, a non-goal.
- Whether the gate should persist transmitter streaks across restarts: the spec rules it out and states the limit.
- Changing any existing debounce (dead-clock 2/10/17, guard-stale, forbidden_checks): a non-goal. I checked only that they are unchanged.
- FU1 and FU2 fixes: out of scope by operator ruling; weighed above.
- QM4, urllib following redirects on POST: pre-existing NtfyChannel behaviour, out of scope.
- `row_analysis` inside publish being unpinged: the spec leaves it, and its docstring records the gap.
- ntfy.sh's per-IP limits on hugo's combined volume (its own pushes plus relayed ones): spec silent; with the gate the volume is a handful a day. Not re-measured.
- R2 class-A and class-B figures in the docs (~130k GETs a month, under 1.3%): I checked the arithmetic, not the meters.
- What the Workers runtime does with a relay promise still pending after the 10 s timeout fires: the worst case is a duplicate relayed message, never a loss or a delayed email.
- §8's phase-1 corrections (dashboard paths, Cache Rule labels, the workers.dev prerequisite): I checked that they are present, not that they match today's dashboard.
- Antenna's per-invocation wall time with the relay added: bounded by the same 10 s pattern as email, so I did not measure it.

### Recommendations

1. Fold RR1 (Important 1) into the runbook before merge: two lines, docs only. The suites need no re-run beyond the docs-only checks Task 7 already ran.
2. Optionally fold Minor 1 (the float seq rule in `doc_problem`) and Minor 4 (a no-put pass with a real `Relay`) now, while the relay is fresh. Neither blocks merge.
3. Carry QM2 (keys and count on `alert-relay-failed`) and a startup `ntfy_url` check (FU2) into the follow-up list.

### Assessment

**Ready to merge?** With fixes

**Reasoning:** I found no code defect, and every strict surface holds by construction and by a named test: spend and off-air keys are ungated, no one-shot key can be silenced, the monitor thread only reads, the watchdog is pinged from the main thread only, and the Worker's PUTs stay bounded. The one fix I would make first is the docs-only RR1 correction to the `monitor-stalled` runbook step, whose grep cannot show the traceback it promises and, when the thread has died, points the operator at R2.
