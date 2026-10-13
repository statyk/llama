VERDICT: NEEDS FIXES

### Findings

#### Critical
None.

#### Important
1. **The PUT-budget half of the R7 test cannot fail (plan-mandated: the brief's test, copied verbatim).** See `packages/transmitter/tests_transmitter/test_cloudstate.py:134`.
   - What is wrong: the fixture writes `puts.json` as `{"day": "2026-10-20", "count": 999999}`. `PutBudget.take()` reads the day from the real `publish._utc_today()`, not from `service.now_us`, which is the only clock the test monkeypatches. Today is 2026-10-12, so the stored day is stale and the count resets to 0. The "over the PUT budget" condition the test name claims never holds.
   - Measured: in a scratch copy I made a mutant that routes `offair on` through `PutBudget(ws.puts_path, cfg.publish.daily_put_budget).take()`. I predicted the R7 test would stay green. It did: 26 passed. When I set the fixture's day to the real UTC date, the same mutant turned that test red, as predicted ("1 failed, 25 passed").
   - Why it matters: R7 is the operator's takedown lever. Nothing pins the rule that a spent PUT budget cannot block `offair on`. The guard-tripped half is still meaningful, because a seeded tripped `guard.json` would refuse a guard-checking implementation.
   - Fix: write the day as `datetime.now(timezone.utc).strftime("%Y-%m-%d")`, or monkeypatch `publish._utc_today` to return `"2026-10-20"`. Ideally add the same over-budget fixture to the `budget --raise-to` path, which R7 covers too.

#### Minor
1. **`offair off` exits non-zero after a successful write when `guard.json` is corrupt or unreadable.** See `cli.py:101`.
   - What is wrong: the follow-up `get_json(GUARD_KEY)` is not guarded. A corrupt `guard.json` (bytes that are not JSON) or a transport error raises `CloudStateError` after "on the air since ..." has printed, and `main_cli` exits 1.
   - Why it matters: a corrupt `guard.json` is exactly when the Worker treats the station as spend-tripped (`corruptGuardDoc`), so it is when the note matters most. Instead the operator gets an error and may assume the takedown was not cleared. A retry is harmless.
   - The brief's code has the same shape. Fix: catch `TransmitterError` and print "note: could not read state/guard.json (...); if it is corrupt the guard treats the station as tripped".
2. **`budget` view: an unreadable or corrupt `guard.json` aborts before the `raise` line.** See `cli.py:119`. The implementer made the `budget.json` read tolerant (`raise <error>`) but not the `guard.json` read. That is loud, so acceptable, but inconsistent: print a `guard      <error>` line and carry on.
3. **The `raise` line shows the raw `budget_usd`, not what the Worker honours.** See `cli.py:127`. An expired raise, one past the period end, or one above $100 prints as `raise $150.00 until X`. `_pending_raise_usd` already computes whether the Worker honours it. Annotate the line with "(expired)", "(ignored)" or "(capped at $100)".
4. **The raise check does not validate the guard document's shape.** See `cloudstate.py:157`.
   - What is wrong: `raise_budget` accepts a `guard.json` that is valid JSON but that `latch.ts parseGuardDoc` would reject (for example a hand-edit with `schema != 1`, or a string `tripped_budget_usd`).
   - Why it matters: the Worker then replaces it with `corruptGuardDoc(..., budget.budgetUsd)`, whose `tripped_budget_usd` is the effective budget including the just-written raise. That consumes the raise, so the trip does not clear.
   - This needs a hand-edit to reach. A minimal mirror (`schema == 1`, `tripped` a bool, `tripped_budget_usd` null or finite) would close it.
5. **`_code` and `GUARD_KEY` duplicate existing code (brief-mandated).** `cloudstate._code` (`cloudstate.py:34`) is a verbatim copy of `publish._error_code`, and `GUARD_KEY` (`cloudstate.py:26`) duplicates `publish.GUARD_KEY`. Import the existing ones, or make `cloudstate` the owner and have `publish` import from it.
6. **`put_state` retries errors that no retry can fix.** See `cloudstate.py:73`. It retries `AccessDenied`, `InvalidAccessKeyId` and `NoSuchBucket`, which `publish.NON_RETRYABLE` already lists. This costs about 3 s and 2 wasted PUTs on a manual command, with no spend risk, but reusing `NON_RETRYABLE` would fail fast with the real cause.
7. **Odd local import.** `cli.py:70` imports `ConfigError` inside `_cloud`, although `cli` already imports from `transmitter.errors` at the top. This comes from the brief; tidy it with a top-level import.

### ⚠️ Cannot verify from diff
- Task 16's `status` integration with `guard_summary`, and its reuse of `cli._cloud`.
- The alert text disagrees with the raise refusal while readings fail. The Worker's `guard-state-corrupt` alert tells the operator to clear the trip with `budget --raise-to`. While readings are also failing, `corruptGuardDoc` has `period: null` and `evaluation: null`, so the raise is refused. The implementer flagged this. It is safe, since nothing could clear the trip without a successful reading anyway. The fix, if any, belongs to the Worker's alert text.
- Whether hugo's clock is skewed against the Worker's for `written_at`. The Worker clamps a future `written_at` to now and then does not count it as a trigger, so the worst case is a raise waiting up to 15 minutes for its evaluation. This is Worker-side behaviour.

### Strengths
- **The raise floor is right, and better than the brief.** `max(evaluation.budget_usd, tripped_budget_usd when reason == "spend", the pending honoured raise)` matches `latch.ts applyAttempt`: a spend trip clears only when the effective budget is greater than `tripped_budget_usd`. It also matches `effectiveBudget`, where a pending raise counts if `usd` is finite and `now < expires <= periodEnd`, capped at 100. That closes both wrong-acceptance paths: a raise the Worker would never let clear the trip, and a quiet lowering of a pending raise. A blind trip correctly sets no floor (blind clears on a success, not a raise).
- **It fails closed on null or non-finite amounts.** `bool` is excluded from numbers, matching JS `typeof`. The summary prints "unknown" instead of crashing.
- **Corrupt and unreadable `budget.json` are handled the way the Worker handles them.** Corrupt bytes are ignored and overwritten, which is the Worker's own advice. A transport error refuses.
- **The comparison is made after rounding to cents**, so 15.004 against 15 is refused. NaN and infinity are refused before the rounding.
- `expires` equals the period end exactly, and the Worker honours `expires == periodEnd`.
- **Tests run against the document exactly as the Worker writes it** (`WORKER_GUARD`, `NULL_AMOUNTS`), not only the brief's simplified `GUARD`.
- R7 holds in the code: no publish lock, no guard check, no `PutBudget`, and `no-store` on every write.
- A failed `offair` write retries, then raises `CloudStateError`; `main_cli` prints the error and exits 1, so the failure is loud.
- **Repo hygiene:** no account details, and every R2 call goes through the injected `FakeBucket`, so no test reaches the network.

### Checks run
- **R7 actually pinned?** Scratch copy via `git archive 8da34f0 packages/transmitter | tar -x`. Shadowing proven first: `transmitter` and `tests_transmitter` both resolved inside the copy. I then added a mutant: `PutBudget(...).take()` in `offair_on`, run with `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<scratch>/... .venv/bin/python -m pytest -p no:cacheprovider .../test_cloudstate.py -q`.
  - Prediction: stays green. Result: `26 passed`.
  - With the fixture day set to the real UTC date, prediction: `test_cli_offair_on_requires_a_reason_and_works_while_tripped_and_over_the_put_budget` red. Result: `1 failed, 25 passed`.
  - The scratch copy has been removed.
- **The floor matches what the Worker compares?** I read `antenna/src/latch.ts` `applyAttempt` (the `raised` rule), `effectiveBudget`, `corruptGuardDoc`, `parseGuardDoc` and `shouldEvaluate`. The Python floor and the pending-raise rules match. Shape validation is the gap (Minor 4).
- **Offair and budget files parsed as the Worker parses them?** I read the HEAD `guard.ts` read path. The Worker requires `offair` to be a boolean, and corrupt means off the air. `budget.json` that is not JSON is ignored with a `budget-unreadable` alert; a read error skips the evaluation. Python's `corrupt_as_absent` matches, including JSON that is not an object (array or null).
- **R2 404 detection and client failure modes?** I compared `publish.Uploader.get_json` and `_error_code`: the same `NoSuchKey`/`404` handling, duplicated (Minor 5). `r2.make_client` raises `ConfigError` on missing keys, so a missing key is caught by `main_cli` and is loud.
- **Error boundary?** `CloudStateError` subclasses `TransmitterError`, and `main_cli` turns it into `error: ...` and exit 1.
