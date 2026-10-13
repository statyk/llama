VERDICT: APPROVED

### Findings
#### Critical
None.

#### Important
None.

#### Minor
1. **`packages/transmitter/src/transmitter/cli.py` `budget` (the `try: raised = cloudstate.get_json(... BUDGET_KEY)` block): this deviates from the brief, and a failed read exits 0.** The brief's view code let a budget.json read error propagate, which exits 1 through `main_cli`. The implementation prints `raise      <error>` and returns 0. This is a read-only view, so no spend surface is involved, and the guard lines have already printed. Still, a script that checks `transmitter budget`'s exit status cannot tell "no raise" from "could not read the raise". Option: keep the printed line but `raise typer.Exit(1)` afterwards. Your call.
2. **`cli.py` `offair_off`: when guard.json cannot be read, the command exits 1 after a successful write.** The flag is written first. Then `get_json(GUARD_KEY)` raises on a corrupt or unreachable guard.json, so the operator sees "on the air since …" followed by `error: …` and exit 1. This matches the brief's code verbatim, so it is not a deviation. The case it hits is the one where a warning matters most: a corrupt guard.json is a spend trip at the Worker, so the station stays blocked. Option: catch `CloudStateError` there and print "note: could not read state/guard.json (…); the station may stay blocked", exit 0.
3. **`cloudstate.py` `raise_budget`: the cap check now runs after rounding.** Because of deviation #4 (compare the value rounded to cents), `100.004` rounds to `100.0` and is accepted, where the brief's `usd > MAX_RAISE_USD` on the raw value would refuse it. The clock caps at `MAX_BUDGET_USD` independently, so the effect is nil. Noted only as an exact-value difference from the brief.
4. **The corrupt-guard window (the implementer's own concern; I confirmed it).** `antenna/src/guard.ts:254-256` tells the operator to "Clear it with `transmitter budget --raise-to <usd>`". After `corruptGuardDoc`, guard.json has `period: null` and `evaluation: null`, so `raise_budget` refuses with "no billing period yet". The refusal fails closed, and the window is short: `corruptGuardDoc` builds on `freshGuardDoc`, whose `evaluated_at` is null, so `shouldEvaluate` evaluates at the next invocation. If readings keep failing, a raise could not clear the trip anyway. This is safe. Only the two messages disagree. A later docs or runbook task could add "wait for the next successful evaluation".

### Judgement on the three-way raise floor (the named deviation)
**It matches the Worker and the brief's intent. I accept it.**
- **The field the Worker compares against.** `latch.ts applyAttempt` (lines 148-150) clears a `spend` trip only when `e.budgetUsd > prev.tripped_budget_usd`. When that field is null, it requires `e.budgetUsd > a.baseBudgetUsd`. The brief's floor (`evaluation.budget_usd` alone) is therefore not the comparison field.
- **Over-threshold evaluations.** `applyAttempt` sets `tripped_budget_usd = e.budgetUsd`, so the two are equal right after an over-threshold evaluation.
- **When the two diverge.** On an under-threshold evaluation that does not clear, the latch keeps the old `tripped_budget_usd` while `evaluation.budget_usd` takes the new effective budget. This happens, for example, when a raise is removed and the projection then drops. `tripped_budget_usd` can then exceed `evaluation.budget_usd`.
- **Why the tripped term helps.** A raise between the two values would pass the brief's check, give no headroom (the evaluation is already under threshold) and never clear. Refusing it is what R3 means ("strictly greater than the budget at the latch's last over-threshold evaluation") and what R5 wants. Scoping the term to `tripped is True and reason == "spend"` is correct: a blind trip clears on any successful under-threshold reading (`if (!prev.tripped || prev.reason === "blind") return cleared`), and `applyBlindRule` nulls `tripped_budget_usd`.
- **Null `tripped_budget_usd`.** The Worker then requires a value above base. Python's floor is `evaluation.budget_usd`, which is always at least base because `effectiveBudget` only raises. So Python is at least as strict.
- **The pending-raise term.** `_pending_raise_usd` mirrors `effectiveBudget` (latch.ts 197-213): a finite `typeof number` value, `expires > now`, `expires <= periodEnd`, `min(usd, MAX_BUDGET_USD)`. The Worker's extra condition `usd <= baseUsd → none` is subsumed, because the pending value only matters when it exceeds the floor, which is at least base. The term only differs from the brief in the window between a raise being written and its evaluation. That window is about a minute, because `shouldEvaluate` fires on `written_at > evaluated_at`. Closing it keeps "a raise only ever raises" consistent. Under the brief's own floor, an evaluated raise could not be lowered via `--raise-to` either. So this is not a new restriction.
- **Brief test strings.** They still match ("above the budget" via "above the budget the guard uses now"; "capped").

### ⚠️ Cannot verify from diff
- Whether the runbook and docs describe `offair` / `budget` and the "wait for the first successful evaluation" caveat. That belongs to the later docs task.
- Task 16's reuse of `cli._cloud` and `guard_summary` in `status`. The `_cloud` signature matches the brief: `(config) -> (client, bucket)`.

### Strengths
- **Verbatim tests.** All 11 of the brief's tests are present and verbatim, including the helpers `_seed` and `_cli` and both CLI tests. I diffed the brief's test block against the committed file: byte-identical.
- **Interfaces match the brief exactly:**
  - the keys `OFFAIR_KEY`, `BUDGET_KEY`, `GUARD_KEY` and `ALERTS_KEY`, and `MAX_RAISE_USD = 100.0`;
  - `put_state(..., attempts=3, sleep=time.sleep)`;
  - the signatures of `set_offair`, `guard_period_end_us`, `current_budget_usd`, `raise_budget` and `guard_summary`;
  - `errors.CloudStateError(TransmitterError)`;
  - the CLI shapes `offair on --reason [--until]`, `offair off [--reason]` and `budget [--raise-to]`;
  - the docstring "within about a minute".

  `get_json` gained only a keyword-only `corrupt_as_absent=False`, which is backward-compatible.
- **The four listed files** are touched as stated. Nothing outside them changed.
- **R7.** `cloudstate` imports only `grid` and `errors`: no lock, no guard check, no PutBudget. The writes are `no-store` and `application/json`, and the pinning test (tripped plus `puts.json` count 999999) exists.
- **The Worker contract holds:**
  - `guard.ts:231` reads only the `offair` boolean, which Python always writes as a bool;
  - `budget.json`'s `expires` equals the guard's period end, which the Worker honours (`expires > periodEnd` is the only rejection);
  - `written_at` is ISO with ms, which `Date.parse` accepts.
- **The reader tolerates everything the Worker can write**, per latch.ts `GuardDoc`: null `evaluation.*_usd`, null `period` / `evaluation` / `tripped_budget_usd`, and null `waf.enabled`. The summary shows `unknown`, and the raise refuses (fails closed) when `budget_usd` is null. Bools are not treated as numbers, which matches JS `typeof`.
- **budget.json handling** matches the Worker: a corrupt file (which the Worker ignores, and whose `budget-unreadable` alert says to rewrite it with `--raise-to`) is overwritable, while a transport failure refuses.

### Checks run
- **Risk: does the raise floor read the field the Worker compares against?** I read `git show HEAD:antenna/src/latch.ts`: `GuardDoc` (28-60), `corruptGuardDoc`, `applyAttempt`, `applyBlindRule` and `effectiveBudget` (105-215). Conclusion above.
- **Risk: is the offair.json shape the Worker accepts?** I grepped `antenna/src/*.ts` at HEAD for `offair`. `guard.ts:231-237` accepts `typeof value.offair === "boolean"`, and anything else fails closed as `offair-corrupt`. Python writes a bool. OK.
- **Risk: does the Worker's advice disagree with the raise refusal (the implementer's concern)?** `guard.ts` 214-256: the `budget-unreadable` and `guard-state-corrupt` messages. Result: Minor 4. The `budget-unreadable` advice is consistent with `corrupt_as_absent=True`.
- **Missing tests.** I extracted the brief's test block and diffed it against the first 136 lines of `HEAD:test_cloudstate.py`: VERBATIM.
- **The failure path of the `put_state` retry test.** `helpers.py` `FakeBucket.put_object` raises `ClientError` per `fail_puts` and returns HTTP 200 on success, so the 2-failure and 5-failure cases exercise the retry and the loud failure as the brief intends.
- **Error exit path.** `cli.py main_cli` turns `TransmitterError` into `error:` and exit 1, which grounds Minors 1 and 2.
- No tests run: no doubt arose that the implementer's reported runs (332 on 3.14, 3.11 and Debian-12) do not answer. No mutants.
