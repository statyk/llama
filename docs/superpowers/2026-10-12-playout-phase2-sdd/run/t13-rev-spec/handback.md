VERDICT: APPROVED

### Findings
#### Critical
None.

#### Important
None.

#### Minor
1. **The new corrupt-state test does not pin the non-dict-entry hardening.** test_alerts.py:649-655 ends with `assert len(rec.sent) >= 4`. I traced it: the hardened code sends about 13 messages here. With the brief's original `state.get(code) or {...}`, the `"render": [1]` entry makes `fire` raise AttributeError, which `alert()` swallows, yet the count would still clear 4. So only the `_load` try/except (the `{not json` half, lines 646-648) is pinned. The `isinstance(entry, dict)` and `count`/`last_sent_at` coercions in `fire` (alerts.py:142-150) could be reverted and stay green. Fix: assert the exact sends per code, or that `render` is active after its fire. This is a test-quality issue, not a missing requirement.
2. **test_channels_carry_a_timeout (test_alerts.py:676-677) is weak.** It asserts `timeout_s > 0` on the dataclass defaults, not that `send` passes the timeout on. SMTP is already pinned at 20.0 by the brief's FakeSMTP test. The brief's ntfy test records `seen["timeout"]` but never asserts it (that gap is in the brief's own code), so nothing pins ntfy's `timeout=` reaching `urlopen`. Fix: add `assert seen["timeout"] == 10.0` to the ntfy test.
3. **A side effect of the resolve-retry deviation, noted but accepted.** Suppose `resolve(code)` fails to deliver: every channel is down, so the code stays active. If the condition comes back before a later resolve gets through, `fire` dedupes the return against the original `last_sent_at` and does not send at once (alerts.py:147-153: a level code is never `_expired`). For the operator this is consistent: they never saw "resolved", so to them the alarm never cleared. The brief's version would have cleared silently and then re-sent. I judge the deviation better and within R16. It only needs a line in the code comment so a later reader doesn't "fix" it back.

### Judgment on the three hardening deviations (R16 and the brief's intent)
- **Corrupt or unreadable alerts.json starts afresh** (`Dispatcher._load` catches OSError/ValueError; `fire` tolerates non-dict entries and non-numeric fields). This is justified. I checked `workspace.read_json` (workspace.py:47-51): it catches only FileNotFoundError. Under the brief's code, one corrupt file would make every `fire` raise. `alert()` swallows that, so nothing would ever be sent again: alerting wedged with no message, the exact lesson. Starting afresh loses only dedupe history, and the next `write_json` rewrites the file atomically. R16 is not affected. The scope is small and stays inside alerts.py.
- **An undelivered "resolved" keeps the code active** (alerts.py:166-169). This matches R16 and the "undelivered is retried, not recorded" lesson. It works only because every resolver is level-triggered. I checked: `Runner._step` resolves on every successful plan or render tick, and Task 14's planned `Monitor.check` (plan lines ~5613-5644) calls `alerts.resolve("dead-clock")` / `alerts.resolve("guard-stale")` on every healthy check, not on transitions. So the retry really happens. With no channels configured it still clears (`and self.channels`), so a log-only install cannot get stuck. This is pinned by test_a_message_no_channel_accepted_is_not_recorded_as_sent (lines 668-673).
- **Undelivered fire and hung channels.** No change was needed: the brief already keeps `last_sent_at` None on a failed send (pinned by the same test, lines 662-667), and the channels carry 20 s / 10 s timeouts. The implementer correctly made no code change here and added only a test. Their stated concern (up to ~30 s blocking per attempt while a channel is down, inside the service loop) is real but bounded, and belongs to the quality seat. It does not touch the spend surface: publish/prune and the PUT budget logic are untouched.

### ⚠️ Cannot verify from diff
- **Docs for the new `[alerts]` keys.** The Global Constraints require "the model, the DEFAULT_CONFIG_TOML template, and the docs" for a new key. The brief's file list names no doc, and the diff touches none. Presumably this lands with the runbook task (Task 17). Check it there.
- **The rest of R4.** The 120 s / two consecutive checks, the 17-check 403 threshold and the guard-cache refresh are Task 14. This task delivers only `dead_clock_seconds` ge 31 and the `guard_stale_minutes >= guard_check_minutes + 16` validator, both present and tested.
- **`status` listing `active_codes`** is Task 16. `active_codes` and `LEVEL_CODES` exist with the brief's signature and contents.
- **A stale `plan`/`render` alarm (brief-mandated design, not a defect of this diff).** These codes resolve only when the plan or render step runs, which happens only while `filling` (and never while `halted`). If a plan failure persists while render refills the lead from already-planned shows, `filling` goes False with `plan` still active until the next low-water dip. This follows R16 as written ("by a successful plan step"); flagging it for the whole-branch review.

### Strengths
- Every brief test exists under the brief's name with the brief's assertions, verbatim: all 8 in test_alerts.py, `test_alerts_defaults_and_floors` appended to test_config.py, and both test_service.py edits exactly as specified. `StationRootError` was already imported in test_service.py:7.
- The production code matches the brief exactly apart from the three declared deviations. That covers signatures (`Dispatcher`, `SmtpChannel`, `NtfyChannel`, `dispatcher_from_config`, `Runner._step(..., *, resolves=())`), the `LEVEL_CODES` contents per R16, the config defaults and floors, the cross-section validator, the template text, `Workspace.alerts_path` placed after `lock_path`, and `cli run`'s configure/finally. Only `transmitter run` configures a dispatcher, so manual commands keep logging only.
- Every file the brief lists was touched as specified. No extra files, and nothing in llama, emcee, herder or antenna. The commit 6f52067 touches only packages/transmitter; the antenna changes in the 24bb50b.. range belong to 7f30c7b (Task 9).
- The public-repo rule holds: tests use example.com and `tk_x`, and the template has only commented placeholders (`you@example.com`, `<your-topic>`).
- The deviations are small, declared up front, and each comes with a test that goes red without it, except Minor 1's sub-part.

### Checks run
- **Risk: a StationRootError in render could flap `station-root`.** Plan resolves it every tick and render re-fires it, which would send a resolved/fire pair every minute. Checked: `grep StationRootError` across src. It is raised only by `station.require_root` and `station.scan`, reached through `pipeline.scan_now` from `plan_step` (pipeline.py:131); `render_step` never scans. No flap is possible.
- **Risk: the corrupt-JSON hardening is redundant.** Checked `workspace.read_json`: it catches only FileNotFoundError, so the hardening is load-bearing.
- **Risk: the resolve-retry deviation depends on resolvers that only fire on transitions.** Checked the phase-2 plan's Task 14 `Monitor.check` / `_check_guard`: they resolve on every healthy check, so the deviation is effective.
- **Risk: the config validator does not surface as ConfigError.** Checked config.py: `model_validator` is imported (line 9), and `load_config` maps `ValidationError` to ConfigError (line 143). The brief's test covers the `guard_check_minutes = 30` case.
- **Brief vs diff, line by line,** for alerts.py, config.py, service.py, workspace.py, cli.py and all three test files.
- No tests were run: no doubt arose that the implementer's reported runs (384 on py3.14/3.11/Debian-12) leave open. I traced Minor 1 by hand rather than running a mutant.
