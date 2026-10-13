VERDICT: OPEN FINDINGS

One finding is open: F9, Minor, partly done. Hugo's guard cache still records `offair: None` (meaning "on the air" to the dead-clock check) for the most common kind of corrupt `offair.json`: bytes that are not JSON at all. The Worker reads those bytes as off the air. This is alert noise only. It does not touch spend and it does not change what blocks publishing. The other eleven findings are ADDRESSED. The mutant evidence for F1, F3, F8 and F10 was reproduced in a scratch copy.

### Finding verdicts

- **F1: ADDRESSED.** The test is at `antenna/test/guard.test.ts:505-516` ("blind still trips 6 h after the last success while state/budget.json gets keep throwing"), at the end of the "races and failure paths" describe. It matches the reviewer's probe: `failGets.add(BUDGET_KEY)`, a step at T0 and a step at T0+6h+1min, expecting `{blocked:true, tripped:true}` and `reason:"blind"`. The committed test also asserts `evaluated_at: null` after the first step, which shows the evaluation really is skipped. I ran it in a scratch `git archive` with node_modules symlinked. HEAD: guard+alerts 81/81 passed. Mutant A (`guard.ts:285`, `if (!budgetReadFailed) doc = applyBlindRule(...)`): I predicted exactly this test would fail, and it did. Result: `× blind still trips 6 h …`, 1 failed / 80 passed.
- **F2: ADDRESSED.** The fix is at `antenna/public/player.js:125-128`. Its `typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function"` check short-circuits, so an undeclared `AbortSignal` cannot throw a ReferenceError. The signal goes into the init only when it is defined. I checked this under node `vm`:
  - with no `AbortSignal` global, the init is `{cache}` and nothing throws;
  - with `AbortSignal` but no `.timeout`, the init is `{cache}`;
  - with the real `AbortSignal`, the init is `{cache, signal}`, and a real `AbortSignal.timeout(50)` aborts with `TimeoutError`.

  Object spread is supported on iOS 15. player.js is not inlined: `src/pages.ts` only references `<script type="module" src="player.js">` and is unchanged.
- **F3: ADDRESSED.** P10 is at `antenna/test/alerts.test.ts:486-499`, the fourth `it` in the `:434` describe (after P6, P7 and "a failed return after a DELIVERED resolved…"). Its sequence and assertions match the reviewer's probe. Green on HEAD. Mutant M1' (`alerts.ts:349`, `delivered: o.kind === "alert" ? !!prev[o.key]?.active : wasDelivered(prev[o.key])`): I predicted P10 alone would fail, and it did. Result: `× P10 …` with `AssertionError … toMatchObject`, 1 failed / 80 passed.
- **F4: ADDRESSED.** `test_systemd.py:45` now reads "far in the future".
- **F5: ADDRESSED.** `docs/playout-setup.md:382` (section 7 spend bullet) and `:452` (checklist step 2) both say a raise must exceed BOTH the projected figure AND actual/0.9, and both state the trip rule (actual ≥ 90% OR projected ≥ 100%).
- **F6: ADDRESSED.** `docs/playout-setup.md:453` says the 50% alert at $7 is expected, and the 80% one only if max(actual, projected) ≥ $5.60, so its absence is not a failure. (There is a small wording loss; see New breakage.)
- **F7: ADDRESSED.** Section 6.1 step 3 (`docs/playout-setup.md:315`) says to paste the App Password WITHOUT the spaces, and why.
- **F8: ADDRESSED.**
  - The step is renamed `"dead-clock-check"` at `service.py:245`, with a comment.
  - `dead-clock` is still raised and resolved only in `deadclock.py:85-104`, and is still in `LEVEL_CODES` (`alerts.py:33`). `dead-clock-check` is not in `LEVEL_CODES`, so it behaves as an event code.
  - Nothing else expected the old step name. The cli/status has no hard-coded code list. The tests that use `"dead-clock"` (`test_alerts.py:64-84`) exercise the level code directly. The runbook's level-code line (`:428`) and the dead-clock checklist item are still correct. `dead-clock-check` was added to 7.1's event list (`:429`).
  - Test: `test_service.py::test_a_monitor_that_raises_alerts_the_event_code_not_the_level_code`. Scratch mutant: I reverted the step name to `"dead-clock"`, with PYTHONPATH shadowing proven (both `transmitter.__file__` and `tests_transmitter.__file__` resolved inside the scratch tree). I predicted that test alone would fail, and it did: 1 failed / 71 passed / 1 skipped over test_service, test_systemd and test_deadclock. With the name restored, those plus test_publish and test_alerts: 109 passed, 1 skipped.
- **F9: NOT ADDRESSED (partial). Minor; noise only.**
  - What changed: `publish.py:155-162` now mirrors the Worker for valid JSON only. Absent → False, a bool → that value, any other JSON value → True. `guard_blocks_publishing` is unaffected: `blocked`, `error` and the return value are unchanged, and the existing test `test_the_guard_cache_records_evaluation_time_and_offair_but_gating_stays_on_…` (`test_publish.py:338`) is untouched and still asserts `offair is None` for a failed GET.
  - What is still wrong: `Uploader.get_json` (`publish.py:133`) calls `json.loads` itself. A body that is not JSON raises `JSONDecodeError`, and the generic `except Exception: offair = None` catches it. I checked this in scratch:

    | `offair.json` body | hugo cache records | Worker (`guard.ts:234-240` via `readJsonDoc`, `bucket.ts:45-53`) |
    |---|---|---|
    | `b"{not json"` | `None` | `corrupt`, so off the air + `offair-corrupt` |
    | `b""` | `None` | off the air |
    | `b"null"` | `False` | off the air |
    | `b"false"` | `True` | off the air (matches) |

    `DeadClockMonitor.check` (`deadclock.py:77`) reads `None` as not blocked. So a truly corrupt flag still produces the unexpected-403 `dead-clock` "kill switch left on?" alert after 17 checks. That is exactly the M2 noise, and the ruling's "anything else present → True" is not met for it. The parametrized test (`test_publish.py:354-370`, test at `:363`) has no non-JSON case.
  - Fix: add `except ValueError: offair = True` before the generic `except Exception`, with a comment that the body is present but not JSON, which the Worker reads as off the air. `JSONDecodeError` and `UnicodeDecodeError` are both `ValueError`; botocore read errors are not. Add `b"{not json"` and `b""` to the parametrize.
  - The implementer's deviation (JSON `null` reads as absent): noise only, I agree. It has the same single consequence (one hugo `dead-clock` 403 alert after 17 checks, next to the cloud's `offair-corrupt`), the failure is loud rather than silent, and nothing on the spend or publishing path reads this field. Accept it, but say it in the comment.
- **F10: ADDRESSED.**
  - The predicate is now `subject.isascii()`, and non-ASCII titles are encoded with `Header(subject, "utf-8").encode(maxlinelen=0)` (`alerts.py:102-106`).
  - Rewriting the old assertion was forced. It pinned `Title == "café: x"`, the raw-latin-1 behaviour that the ruling explicitly replaces, so no implementation following the ruling could keep it green. The new assertions check that the title is ASCII and starts with `=?utf-8?`, that it decodes back to "café: x", and that a long non-ASCII title has no CR/LF and round-trips.
  - Scratch mutants, each predicted to fail `test_ntfy_title_is_rfc2047_encoded_when_not_latin1`. Both did (1 failed / 16 passed each time):
    - (a) the latin-1 predicate restored;
    - (b) a default `encode()` (obs-fold).
- **F11: ADDRESSED.** The comment-only change is in the `mergeLostRace` docblock (`guard.ts:115-118`). `git diff --stat 01186ea..HEAD -- antenna/src` shows only `guard.ts | 5 ++++-`, all of it comment lines. No other antenna/src file changed.
- **F12: ADDRESSED.** `docs/playout-setup.md:200` (section 4 step 4): "then redeploy with the committed `wrangler.jsonc` (its output ends with `schedule: * * * * *`)".

### New breakage in the fix diff
- Minor, `docs/playout-setup.md:453` (F6). The old text also said the 50%/80% alerts at **$5.50** are expected. The new text names only the $7 pair, under a general "Extra once-only spend-level alerts are expected". The $5.50 alerts (both levels fire, since actual ≥ $4.40) are now covered only by that generic clause. It is not wrong. Optionally add "(50% and 80% at $5.50 arrive with the trip)".
- Minor (cosmetic), `test_alerts.py`: the test is still named `test_ntfy_title_is_rfc2047_encoded_when_not_latin1`, but the predicate is now "not ASCII".
- Minor (cosmetic), `alerts.test.ts:434`: the describe is titled "…over a still-active **delivered** episode keeps it delivered", but its fourth test (P10) pins the never-delivered arm. The placement follows the ruling; a rename can wait until the file is next touched.
- Otherwise none.

### Out-of-scope observations
- F2 lives in `public/player.js`, which ships through `npm run deploy:assets`, not the Worker deploy. At the checkpoint the operator must re-run `deploy:assets` for the iOS 15 fix to reach listeners.
- On browsers without `AbortSignal.timeout` the probe is unbounded, as the new comment says. `probe()` is fired from the 1 s interval whenever `watch.tick` says so, with no in-flight guard, so a hung fetch there can stack up probes. Each one is a cache hit (never billed per request) and the `gen`/`session` checks discard stale answers. Phase-4 player UX; not spend.

### Checks run
(log: `$D/final-rerev/final-rerev.log`)
- antenna, scratch `git archive HEAD antenna packages/transmitter` under the session scratchpad, node_modules symlinked, vitest run from the scratch dir:
  - HEAD, guard+alerts: 81 passed.
  - Mutant A: 1 failed (F1's test, as predicted).
  - Mutant M1': 1 failed (P10, as predicted).
  - Source files restored and diffed clean afterwards.
- F2: node `vm` evaluation of the guarded expression in three global environments, plus a real `AbortSignal.timeout` abort.
- transmitter, scratch with `PYTHONPATH=<scratch>/packages/transmitter/src:<scratch>/packages/transmitter`, run as `.venv/bin/python -m pytest -p no:cacheprovider` from the scratch cwd. Shadowing was proven by printing `__file__`; `PYTHONDONTWRITEBYTECODE` was set for the later runs and `__pycache__` purged between them.
  - F8 mutant: predicted red, got red.
  - F10 mutants (a) and (b): predicted red, got red.
  - Restored: 109 passed, 1 skipped.
  - F9 probe over four bodies, table above. The probe file existed only in scratch.
- Email grep on `docs/playout-setup.md` (with the example/alerts@lma-radio.com exclusions): no output. No added line in the fix diff matches the email pattern.
- I did not re-run the full suites (rereview rules). The implementer reports antenna 217 passed with tsc clean; transmitter 451 passed / 1 skipped on 3.14 and on 3.11; Debian-12 gate 452 passed. The diff is consistent with those reports.
- No network, no wrangler, no dry-run, no deploy, no systemctl. The live worktree is unchanged (clean, HEAD 6b42bde). The scratch tree has been removed.
