# t12-impl handback: Task 12, `transmitter offair` and `transmitter budget`

**Status: DONE_WITH_CONCERNS.** The work is complete and all gates are green. The concerns are design notes for the reviewer, not defects.

**Commit:** `8da34f0 feat(transmitter): offair on|off and budget --raise-to write the station's cloud state`

**Tests:** transmitter 332 passed on py3.14, 332 on py3.11 and 332 in Debian-12 (docker). The full llama suite gave 2488 passed and 7 deselected. 8 of 8 predicted mutants were caught.

## What I implemented
- `errors.CloudStateError(TransmitterError)`.
- `transmitter/cloudstate.py` has the brief's API: `OFFAIR_KEY`, `BUDGET_KEY`, `GUARD_KEY`, `ALERTS_KEY` (`state/alerts.json`, matching antenna `alerts.ts`), `MAX_RAISE_USD = 100.0`, `get_json`, `put_state`, `set_offair`, `guard_period_end_us`, `current_budget_usd`, `raise_budget` and `guard_summary`. I also added `usd_text` (public, because the CLI uses it) and the private helpers `_finite` and `_pending_raise_usd`.
- In `cli.py`:
  - `transmitter offair on --reason TEXT [--until ISO]`;
  - `transmitter offair off [--reason TEXT]`;
  - `transmitter budget [--raise-to USD]`;
  - the helper `cli._cloud(config) -> (client, bucket)`.
- R7: the writes are a direct `put_object` with `CacheControl: no-store`. They take no publish lock, make no guard check and do not touch the PutBudget. A test pins that `offair on` works while the guard is tripped and `puts.json` is spent.
- `written_at` and `since` come from `service.now_us()`, i.e. `time.time_ns()`, the real clock.

## Files
- created `packages/transmitter/src/transmitter/cloudstate.py`
- created `packages/transmitter/tests_transmitter/test_cloudstate.py` (the brief's tests verbatim, plus 14 more test functions, 17 cases with parametrisation)
- modified `packages/transmitter/src/transmitter/errors.py`
- modified `packages/transmitter/src/transmitter/cli.py`

## Deviations from the brief (each with its reason)
1. **The raise floor is not just `evaluation.budget_usd`.** You asked me to check that the refusal reads the field the Worker compares against. The Worker clears a spend trip only when the effective budget is greater than `tripped_budget_usd` (latch.ts `applyAttempt`, R3). The floor a raise must exceed is therefore the highest of three values:
   - `evaluation.budget_usd`;
   - `tripped_budget_usd`, when tripped with reason `spend` and the value is finite. It can sit above the evaluated budget, for example after a budget.json is removed, and a raise between the two would never clear the trip;
   - a raise already in `state/budget.json` that the Worker would honour now, using latch.ts `effectiveBudget`'s rules: a finite numeric `budget_usd`, `now < expires <= period end`, capped at 100. That raise is part of "the budget the guard uses now" even before the guard has evaluated it, so without this a second `--raise-to` could quietly lower a pending raise.

   The refusal message names which of the three set the floor. The brief's test strings ("above the budget") still match.
2. **Fail closed on null amounts.** `current_budget_usd` refuses when `evaluation.budget_usd` is null or non-finite, with a message of its own ("recorded no valid budget"). Bools and strings do not count as numbers, matching JS `typeof`. `guard_summary` prints `unknown` for null amounts instead of crashing (`usd_text`), and it tolerates a `period` or `waf` that is not an object.
3. **budget.json read in `raise_budget`.**
   - A corrupt budget.json (not JSON, or not an object) is ignored and overwritten, via `get_json(..., corrupt_as_absent=True)`. The Worker ignores it too, and its `budget-unreadable` alert tells the operator to fix it with `--raise-to`; refusing would make that advice fail.
   - A budget.json that cannot be read (transport error) refuses: fail closed.
4. **The comparison uses the rounded value.** The raise is rounded to cents before it is compared, so 15.004 against a budget of 15 is refused rather than written as 15.0, which is not a raise. `raise_budget` checks finiteness before rounding, so NaN and inf are still refused.
5. **`budget` view.** The `raise` line uses `usd_text`, so an odd `budget_usd` cannot crash the command. A budget.json that fails to read prints `raise      <error>` instead of aborting after the guard lines.

## TDD evidence
- RED: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_cloudstate.py -q` → `ImportError: cannot import name 'cloudstate' from 'transmitter'`, `1 error in 0.74s`.
- GREEN, the same command → `26 passed in 1.09s`.
- `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q` → `332 passed in 53.84s`.
- `./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q` → `332 passed in 53.27s`.
- `docker info`: OK. `packages/transmitter/scripts/test-in-debian12.sh` → `332 passed in 26.17s`, exit 0.
- `./.venv/bin/python -m pytest -q -p no:cacheprovider` (whole repo, run on the committed tree) → `2488 passed, 7 deselected, 26 warnings in 99.99s`, exit 0.
- Mutation run:
  - Setup: one fresh `git archive HEAD` copy per mutant in the scratchpad, `PYTHONPATH`-shadowed with `PYTHONDONTWRITEBYTECODE=1` and run from the scratch cwd. Before each run I checked that both `transmitter` and `tests_transmitter` resolved inside the copy.
  - Each mutant was caught by its predicted test: M1 tripped floor, M2 pending floor, M3 unrounded comparison, M4 corrupt budget.json made fatal, M5 null `usd_text`, M6 a blind trip setting the floor, M7 the period-end bound dropped, M8 a null budget accepted.

## Self-review
- I checked the Worker interfaces against latch.ts (`GuardDoc`, `parseGuardDoc`, `effectiveBudget`, `MAX_BUDGET_USD`) and guard.ts (offair parsing reads the `offair` boolean; budget.json corrupt vs unreadable).
- `expires` = the guard's period end exactly. The Worker ignores only `expires > periodEnd`, so equality is honoured.
- The `--until` check uses `grid.iso_to_us`, which rejects naive timestamps and words like "tomorrow".
- Python 3.11: no 3.12+ APIs, confirmed by the 3.11 suite and the Debian-12 gate.

## Concerns (for the reviewer)
- **A corrupt guard.json blocks a raise.** When the Worker has replaced an unreadable guard.json with `corruptGuardDoc` and its reading also fails, guard.json has `period: null` and `evaluation: null`. `raise_budget` then refuses ("no billing period yet"), while the Worker's `guard-state-corrupt` alert says "clear it with `transmitter budget --raise-to`". Once a reading succeeds, the period and evaluation exist and the raise works. Until then nothing could clear the trip anyway, because clearing needs a successful reading. So it is safe, but the two messages disagree slightly in that window.
- **One extra Class B read per raise.** `raise_budget` now reads budget.json as well. It is a manual command, so I judge this negligible.
- **Unknown amounts.** `guard_summary` prints `unknown` for null amounts. `status` integration is Task 16's.

---

# Fix round 1 (quality review items 1-9)

**Status: DONE.** All 9 items are fixed.

**Commit:** `67c9247 fix(transmitter): task 12 review -- R7 pinned on a really spent PUT budget, guard shape mirror, tolerant views`

**Tests:**
- transmitter: 372 passed on py3.14, 372 on py3.11 and 372 in Debian-12 (`docker info` OK first);
- llama, the full suite: 2528 passed, 7 deselected;
- mutants: 7 of 7 caught by their predicted test.

## Changes
1. **R7 now runs on a PUT budget that is really spent** (Important).
   - Monkeypatching `publish._utc_today` would not have worked. `PutBudget.__init__`'s default `today=_utc_today` is bound when the function is defined, so a mutant that builds `PutBudget(path, limit)` would still read the real clock.
   - The fixture helper `_spend_the_put_budget` therefore writes today's real UTC day (`datetime.now(timezone.utc)`, the same format as `_utc_today`) with `count: 999999`.
   - The `offair on` R7 test uses the helper, and a new test, `test_cli_raise_works_while_tripped_and_over_the_put_budget`, covers `budget --raise-to` with a spend-tripped guard.json and the spent budget.
2. **`offair off` notes an unreadable guard and still succeeds.** Once the flag write has succeeded, an unreadable or corrupt guard.json prints `note: could not read state/guard.json (…); the station may stay blocked …`. A guard.json that latch.ts would call corrupt prints a "not a document the guard wrote" note. Both exit 0.
3. **`budget` view, guard line.** An unreadable or corrupt guard.json prints `guard      <error>`. A guard.json the shape mirror rejects prints `guard      state/guard.json is not a document the guard wrote (…)`. Either way the view carries on to the raise line.
4. **`budget` view, exit code.** After printing everything, the view exits 1 if the guard.json read or the budget.json read failed (unreadable, corrupt, or failing the shape check). An absent file is not a failure: no guard and no raise exits 0.
5. **`budget` view, honoured status.** The raise line ends with `(honoured)`, `(honoured, capped at $100)`, `(expired)`, `(ignored: expires after the billing period ends)`, `(ignored: not above the configured budget ($X))`, `(ignored: budget_usd is not a number)` or `(ignored: expires is not a time)`.
   - It is computed by the new `cloudstate.raise_verdict(raised, now_us, period_end_us|None, base_usd|None)`, which applies latch.ts `effectiveBudget`'s rules.
   - `_pending_raise_usd` now delegates to it, keeping the same floor semantics. It skips the base check, which is harmless because such a raise sits below the evaluated budget anyway.
   - The view judges against guard.json's period end and `evaluation.base_budget_usd` when they are known, and skips those checks when they are not.
6. **`raise_budget` refuses a guard.json the Worker would call corrupt.** The new `cloudstate.guard_doc_problem(guard) -> str | None` mirrors every check in latch.ts `parseGuardDoc`:
   - `schema == 1`, with a bool excluded;
   - `tripped` is a bool;
   - `reason` is null, `spend` or `blind`, and `tripped == (reason != null)`;
   - `since` is a parseable time;
   - `tripped_at`, `tripped_period_start`, `last_success`, `evaluated_at` and `last_error` are each a string or null, and present;
   - `tripped_budget_usd` is a finite number or null (a bool or string is rejected);
   - `waf` is `{enabled: bool|null, error: str|null}`;
   - `period` is null or `{start: str, end: str}`;
   - `evaluation` is null or `{at: str, actual_usd, projected_usd, budget_usd}`, each amount a finite number or null.

   A missing key is rejected, as JS `undefined` is. `raise_budget` refuses before any other check: the Worker's `corruptGuardDoc` would latch `tripped_budget_usd` at the effective budget including the new raise, which swallows it.
7. **The $100 cap is checked twice.** It applies to the raw value as well as the rounded one: `usd > MAX_RAISE_USD or round(usd, 2) > MAX_RAISE_USD`. 100.004 is refused and 100 is accepted.
8. **`put_state` stops at once on unfixable errors.** An error whose code is in `publish.NON_RETRYABLE` raises `CloudStateError("could not write <key>: …")` on the first attempt, with no sleep. `cloudstate` now imports `GUARD_KEY`, `NON_RETRYABLE` and `_error_code` (as `_code`) from `publish`, which adds no import cycle: publish imports nothing that imports cloudstate.
9. **`cli.py` imports cleanly.** `ConfigError` is imported at the top level, and the local import in `_cloud` is gone.

## Deviations from the brief's verbatim code (ruled)
- Items 2–9 as listed above.
- **Test fixture change.** The brief's `GUARD` fixture lacked five fields latch.ts always writes (`since`, `tripped_period_start`, `tripped_budget_usd`, `last_success`, `evaluated_at`). `parseGuardDoc`, and so the new mirror, rejects it. I added the fields with Worker-consistent values (`tripped_budget_usd: 15`, the same as the evaluated budget). This follows directly from item 6; no assertion in the brief's tests changed.
- The R7 fixture day changed from the literal `"2026-10-20"` to the real UTC day (item 1).

## Covering tests (all in `test_cloudstate.py`; 66 cases, up from 26)
- **Item 1:** `test_cli_offair_on_requires_a_reason_and_works_while_tripped_and_over_the_put_budget` (fixed), `test_cli_raise_works_while_tripped_and_over_the_put_budget` (new).
- **Item 2:** `test_cli_offair_off_notes_an_unreadable_guard_and_still_succeeds` [corrupt, unreadable, shape].
- **Items 3–4:**
  - `test_cli_budget_view_reports_an_unreadable_guard_carries_on_and_exits_1` [corrupt, unreadable, shape];
  - `test_cli_budget_view_exits_1_when_the_raise_cannot_be_read` (unreadable, then corrupt budget.json);
  - `test_cli_budget_view_exits_0_with_no_guard_and_no_raise`.
- **Item 5:** `test_cli_budget_view_says_whether_the_worker_honours_the_raise` (6 cases), plus the updated `test_cli_budget_tolerates_an_odd_raise_file`.
- **Item 6:**
  - `test_a_raise_refuses_a_guard_document_the_worker_would_call_corrupt` (12 cases);
  - `test_a_raise_refuses_a_guard_document_missing_a_field` (10 cases);
  - `test_the_worker_shaped_documents_pass_the_shape_mirror` (GUARD, WORKER_GUARD, NULL_AMOUNTS, and latch.ts `freshGuardDoc`'s shape).
- **Item 7:** `test_the_cap_applies_before_rounding_too`.
- **Item 8:** `test_put_state_fails_at_once_on_an_error_no_retry_can_fix` (AccessDenied: one PUT, no sleep).

## Commands and output
- Focused run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_cloudstate.py -q` → `66 passed in 1.89s`.
  - Before the fixture fix, the same run gave `7 failed, 19 passed`. The 7 failures were the brief's GUARD fixture being rejected by the new mirror ("since is not a time" and the like), as expected.
- `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q` → `372 passed in 56.42s`.
- `./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q` → `372 passed in 55.14s`.
- `docker info`: OK. `packages/transmitter/scripts/test-in-debian12.sh` → `372 passed in 27.18s`, exit 0.
- `./.venv/bin/python -m pytest -q -p no:cacheprovider` (whole repo, on committed HEAD 67c9247) → `2528 passed, 7 deselected, 26 warnings in 115.37s`, exit 0.

## Mutant results
- Setup: one fresh `git archive HEAD packages/transmitter` per mutant in the scratchpad, run from the scratch cwd with `PYTHONDONTWRITEBYTECODE=1`, using `.venv/bin/python -m pytest -p no:cacheprovider`. Before each run I checked that `PYTHONPATH` shadowing resolved both `transmitter` and `tests_transmitter` inside the copy. Every scratch copy was removed afterwards.
- The expected red test was named before each run:
  - **MA:** `offair on` routed through `PutBudget(...).take()`. Predicted red: `test_cli_offair_on_requires_a_reason_and_works_while_tripped_and_over_the_put_budget`. **Caught** (1 failed, 65 passed).
  - **MB:** `budget --raise-to` routed through `PutBudget(...).take()`. Predicted red: `test_cli_raise_works_while_tripped_and_over_the_put_budget`. **Caught** (1 failed).
  - **MC:** the shape mirror disabled in `raise_budget`. Predicted red: `test_a_raise_refuses_a_guard_document_the_worker_would_call_corrupt`. **Caught** (22 failed, together with the missing-field test).
  - **MD:** the cap checked on the rounded value only. Predicted red: `test_the_cap_applies_before_rounding_too`. **Caught** (1 failed).
  - **ME:** the NON_RETRYABLE short-circuit removed. Predicted red: `test_put_state_fails_at_once_on_an_error_no_retry_can_fix`. **Caught** (1 failed).
  - **MF:** the guard-read catch in `offair off` disabled. Predicted red: `test_cli_offair_off_notes_an_unreadable_guard_and_still_succeeds`. **Caught** (2 failed: the corrupt and unreadable cases; the shape case does not raise, so it correctly stays green).
  - **MG:** the view's exit 1 removed. Predicted red: `test_cli_budget_view_exits_1_when_the_raise_cannot_be_read`. **Caught** (4 failed, together with the unreadable-guard view test).

## Concerns
- None new. The round-1 concern still stands: while a corrupt guard.json is being re-read and the Worker's reading also fails, the Worker's alert text and the raise refusal disagree. It is safe, and any fix belongs in the Worker's alert text.
