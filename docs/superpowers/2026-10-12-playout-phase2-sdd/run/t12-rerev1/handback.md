VERDICT: ALL ADDRESSED

### Finding verdicts

1. **R7 PUT-budget half — ADDRESSED.** `test_cloudstate.py` `_spend_the_put_budget` writes `{"day": <real UTC today>, "count": 999999}` to `$TRANSMITTER_ROOT/puts.json`. That is the path `service.py:83` builds PutBudget on (`ws.puts_path` = `root / "puts.json"`, `workspace.py:94`). The count is far above the default limit of 17,500. The fixture is used by the `offair on` R7 test and by the new `test_cli_raise_works_while_tripped_and_over_the_put_budget` (spend-tripped GUARD).
   - The implementer's reasoning holds. `PutBudget.__init__`'s `today=_utc_today` default is bound at definition (`publish.py:75`), so monkeypatching `publish._utc_today` would not reach a mutant that copies `service.py:83`'s `PutBudget(path, limit)` shape.
   - I confirmed it independently with my own mutant (a `git archive` scratch copy with PYTHONPATH shadowing proven). It routes `offair on` through `PutBudget(default_root()/"puts.json", cfg.publish.daily_put_budget).take()`. Predicted red: `test_cli_offair_on_requires_a_reason_and_works_while_tripped_and_over_the_put_budget`. Result: exactly that test failed with `PutBudgetExceeded('daily PUT budget of 17500 reached for 2026-10-12 (UTC)')`, 1 failed, 6 passed.
   - Midnight robustness: if UTC midnight falls between the helper's `datetime.now()` and the mutant's `take()` (a sub-second window within one test), the day resets to 0 and the mutant passes. The failure is one-directional: a mutant can escape in that window, but correct code can never go red. So the test cannot flake, and the escape window is negligible. Acceptable.
   - A fully robust alternative, optional (Minor, not blocking): `_utc_today`'s body resolves the module global `datetime` at call time, so `monkeypatch.setattr(publish, "datetime", <frozen class>)` would pin the day even through the definition-time default. Pinning only `_utc_today` would not, as the implementer says.
2. **`offair off` notes an unreadable or corrupt guard and exits 0 — ADDRESSED.** `cli.py:100-110`: a `TransmitterError` from `get_json` prints a note and returns; a shape-mirror failure prints a note. Covered by `test_cli_offair_off_notes_an_unreadable_guard_and_still_succeeds` [corrupt, unreadable, shape]. The test asserts exit 0, the flag written, and the note.
3. **`budget` view prints a guard error line and carries on — ADDRESSED.** `cli.py:127-141`. Covered by `test_cli_budget_view_reports_an_unreadable_guard_carries_on_and_exits_1` [corrupt, unreadable, shape]. The test asserts the first line is `guard      …state/guard.json…` and that the raise line still prints.
4. **`budget` view exits 1 after printing on any failed read — ADDRESSED.** `failed` is set on a guard read error, a guard shape failure and a budget.json read error, and `raise typer.Exit(1)` comes after all printing (`cli.py:150-151`). An absent file is not a failure (`test_cli_budget_view_exits_0_with_no_guard_and_no_raise`). An unreadable and a corrupt budget.json both exit 1 (`test_cli_budget_view_exits_1_when_the_raise_cannot_be_read`).
5. **Raise line says whether the Worker honours it — ADDRESSED.** `cloudstate.raise_verdict` (diff `cloudstate.py:312-337`) reaches the same honoured/not-honoured outcome as latch.ts `effectiveBudget`: a finite number, `expires > now`, `usd > base`, `expires <= periodEnd`, then `min(usd, 100)`. The checks run in a different order, which changes only which reason is printed. `_raise_status` (`cli.py:154-166`) judges against `period.end` and `evaluation.base_budget_usd` when they are known. All six labels are covered by `test_cli_budget_view_says_whether_the_worker_honours_the_raise`. `_pending_raise_usd` delegates with the base check skipped, which is harmless as the docstring says.
6. **raise_budget refuses a guard.json parseGuardDoc would reject — ADDRESSED.** I checked `guard_doc_problem` clause by clause against `antenna/src/latch.ts:82-107`:
   - schema: `!== 1`, with a bool excluded. Python's `True == 1` is handled, and `1.0` behaves the same on both sides.
   - tripped: a bool.
   - reason: in {null, spend, blind}, and missing is rejected. `tripped == (reason != null)`.
   - The five string-or-null keys: missing is rejected (`get(k, 0)`), matching JS `undefined`.
   - `tripped_budget_usd`: null or finite, with bools excluded, matching `typeof === "number"`.
   - waf: an object with `enabled` null or bool and `error` string or null, each required.
   - period: null or `{start: str, end: str}`.
   - evaluation: null or `{at: str, three num-or-null amounts}`, with missing keys rejected.

   Every clause matches the Worker for any document the Worker itself writes. The one divergence is on `since` (Minor, below). The guard is checked first in `raise_budget`, before the period, evaluation and budget.json reads, which is correct: guard.ts:249-252 confirms that `corruptGuardDoc(nowMs, period, budget.budgetUsd)` latches at the effective budget including the raise, so the swallow the mirror prevents is real.

   Fixture fields added to the brief's GUARD: `since`, `tripped_period_start` (= period start), `tripped_budget_usd: 15` (= the evaluated budget, which is what `applyAttempt` writes on an over-threshold evaluation), `last_success` and `evaluated_at` (= evaluation.at). All are consistent with `applyAttempt`/`freshGuardDoc`. No assertion in the brief's tests changed. The `freshGuardDoc` shape passes the mirror (`test_the_worker_shaped_documents_pass_the_shape_mirror`).
7. **$100 cap on the raw value too — ADDRESSED.** Diff `cloudstate.py:383`: `usd > MAX_RAISE_USD or round(usd, 2) > MAX_RAISE_USD`, with the rounded value written. NaN and inf are still refused earlier by the floor's `math.isfinite`. Covered by `test_the_cap_applies_before_rounding_too` (100.004 refused, 100 accepted).
8. **put_state does not retry NON_RETRYABLE; reuses `_error_code` and `GUARD_KEY` — ADDRESSED.** Diff `cloudstate.py:168-169` and `207-209`. publish imports nothing that imports cloudstate; only `cli.py` imports it, so there is no cycle. Covered by `test_put_state_fails_at_once_on_an_error_no_retry_can_fix` (one PUT, no sleep).
9. **ConfigError at top level — ADDRESSED.** `cli.py:12`; the local import in `_cloud` is removed.

### New breakage in the fix diff

None at Critical or Important. Minor:
- **M1. The mirror's `since` check is not exactly `Date.parse` (`cloudstate.py` `_iso_ok`).** I measured node's `Date.parse` against `_iso_ok` on 3.14 and 3.11. They agree on every string the Worker writes (`toISOString`). They diverge only on hand-edited values, in both directions:
  - Stricter: `2026-10-11T00:01:00` (naive), `2026-10-11` (date only), and `Oct 11 2026 00:01:00 UTC` are accepted by JS but refused by the mirror. On 3.11 only, `…T24:00:00Z` is also refused. Because the Worker carries `since` forward unchanged on every rewrite (`{...prev}`), such a hand edit would refuse every raise permanently. The refusal message's "it rewrites the document within a minute; retry" would then be untrue.
  - Looser: `20261011T000100Z` and `2026-W41-1T00:00:00Z` are accepted by the mirror but rejected by JS. A raise would be written and then swallowed once, though the Worker then rewrites `since` validly.

  This is reachable only by hand-editing guard.json, so it is not blocking. A tighter mirror would accept only the `toISOString` shape plus whatever else the operator might type, or tell the operator in the refusal message to fix `since` by hand.
- **M2. Non-standard JSON tokens.** `get_json` uses `json.loads`, which accepts `NaN` and `Infinity` tokens; JS `JSON.parse` rejects the whole document (bucket.ts:50-52 gives "corrupt", which leads to corruptGuardDoc). A guard.json with such a token in a field the mirror does not inspect (for example `evaluation.base_budget_usd` or `period_to_date.*`) passes the mirror, but the Worker swallows the raise. The Worker never writes these tokens (`JSON.stringify` writes null), so this too needs a hand edit. The fix would be `json.loads(..., parse_constant=<raise>)` for GUARD_KEY.
- **M3. Wording.**
  - The `offair off` shape note (`cli.py:108-109`) says the guard treats the station as tripped "until it rewrites it". In fact the rewrite is a spend trip (corruptGuardDoc), which persists until a raise or a new period.
  - With a shape-failed guard, the `budget` view's raise line can read `(honoured)` (the test asserts it). That is true in the `effectiveBudget` sense, but corruptGuardDoc will latch at that budget, so it does not clear anything. The guard line above it does say "treats it as a spend trip".

### Out-of-scope observations

- `get_json` catches only `ValueError` around `resp["Body"].read()`. A botocore streaming error during the body read (for example `ReadTimeoutError` or `IncompleteReadError`, which are not ValueError) escapes as a non-TransmitterError. In `offair off` that means a traceback and exit 1 after the flag was written successfully. The same applies to the `budget` view's tolerance. This code predates the fix diff; it is rare and not spend-relevant.
- `_finite(int)` on a huge JSON integer literal (hundreds of digits) raises OverflowError from `math.isfinite`, where JS yields Infinity and rejects the value. This predates the fix diff and is absurd input.
- WORKER_GUARD now re-spreads fields GUARD already carries. This is redundant but harmless.
- The implementer's standing concern (a corrupt guard with a failing reading means the raise is refused with "no billing period" while the Worker's alert suggests `--raise-to`) is accurately characterised. It is safe, and any fix belongs in the alert text.

### Checks run

- I read the brief, the constraints, both handback sections, the fix diff, latch.ts (whole: `parseGuardDoc`, `corruptGuardDoc`, `applyAttempt`, `effectiveBudget`), guard.ts:235-300, `bucket.ts` read kinds, and publish.py's `PutBudget`, `_error_code` and NON_RETRYABLE.
- `Date.parse` vs `_iso_ok` on 13 strings, with node, `.venv` (3.14) and `.venv311` (3.11). Results are as in M1.
- One mutant, in a scratch `git archive HEAD packages/transmitter` copy run from an empty cwd. I proved PYTHONPATH shadowing first: `transmitter` and `tests_transmitter` both resolved in the copy. `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`. The mutant routes `offair on` through `PutBudget(...).take()`. Predicted red was the `offair on` R7 test, and that test went red as predicted. The scratch copy was removed afterwards.
- I did not re-run the suite. The fix report names the covering tests, the commands and their outputs (372/372/372, full repo 2528), and the tests it names match the diff.
- The worktree is unmodified (`git status --short` is empty).
