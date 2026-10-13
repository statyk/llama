# Binding constraints for every task (verbatim from the plan)

## Stakes

Money and on-air continuity are at risk. Data is not. **Spend is the one strict surface.** Cloudflare has no account spending cap, so a defect in the guard, the blocking reconciliation, the kill switch or the fail-closed blind rule can run up an uncapped bill silently. Treat those paths with the rigor of a migration. **No failure mode may silently leave the station unblocked while over budget, and no listener path may ever bill per request.** Concretely:

- an unreadable state never unblocks;
- a lost race never loses a trip;
- a missing secret fails closed (blind) and loudly;
- the kill switch is found by its description and never toggled if it is ambiguous;
- the clock's spend bounds stay intact: `MAX_PUTS = 10`, the `d ≠ 10.24` refusal and the 75 s loop clamp.

Secondary: the station must never list a segment that does not exist, and must never cut a performance mid-song.

**This repo is public.** No committed file may contain an account ID, zone ID, token, key, email address or other account detail. That covers this plan, code, config templates, tests and `wrangler.jsonc`. Use placeholders (`<host>`, `you@example.com`, `<your-topic>`) and keep the real values in Worker secrets, the git-ignored `antenna/.env`, or hugo's env file (mode 600). Never add `account_id` or an address to `antenna/wrangler.jsonc`. The one address that may appear in the plan and the runbook is the alert sender `alerts@lma-radio.com`: it sits on the station's already-public domain and identifies no account (operator ruling, 2026-10-12).

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

