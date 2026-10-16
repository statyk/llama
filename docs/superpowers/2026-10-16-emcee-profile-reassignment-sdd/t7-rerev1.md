### Finding Verdicts

- **EOF-at-prompt test passes when EOF is treated as yes, because `run`'s per-package `except Exception` swallows forbid_spend's AssertionError into an error row (fix both (a) and (b), test-only)** — ADDRESSED.
  - (a): `packages/emcee/tests/test_run_plan.py` `test_eof_at_the_prompt_spends_nothing` now asserts `exit_code == 1`, `"Aborted" in result.stderr`, `"error:" not in result.stderr`, `"voiced:" not in result.stdout`, unchanged manifests, and `spent == []` (diff hunk @@ -175 to +176, lines ~200-210). A swallowed spend now produces an `error: <pkg>: AssertionError: LLM or TTS spend` row, and the test fails on it.
  - (b): `packages/emcee/tests/helpers.py:226-240`. `forbid_spend` still raises, and it now appends one entry per attempt to a list it returns. All 11 `forbid_spend` call sites in test_run_plan.py bind the list and assert `spent == []`.
  - Coverage of the patch: both patched names are the module globals that `_process_one` reaches. `speech_for_voicing` is called from `cli.py:244` and resolves `speech_provider_for` from `emcee.process`, which imports it at `process.py:34` and calls it at `process.py:170/173`. `provider_for` is used at `process.py:290/314`. So an attempted spend is recorded before `preflight()` or any LLM call.
  - Mutant proof in the report: M1 (Abort treated as proceed) gives 1 failed / 18 passed, failing at the `Aborted` assertion as predicted. M1b (the same mutant with the (a) assertions stripped) fails at `spent == []` with 4 entries, which shows (b) is independently load-bearing. The control gives 19 passed. The run used a scratch copy, the shadowing was checked, and the bytecode cache was isolated. The proof is credible as described.
  - The same blindness in `test_any_error_row_exits_1[declined]`: ADDRESSED. The non-proceeded modes now assert `spent == []` and `"voiced:" not in result.stdout`, and `declined` also asserts `"nothing voiced" in result.stdout`.
  - Covering tests are named in the report with output: 105 passed (test_run_plan, test_move_cmd, test_recording, test_profile_readiness), and the full suite gives 3129 passed. No production change: the diff touches only `tests/helpers.py` and `tests/test_run_plan.py`.

### New Breakage in the Fix Diff

None.
- The return-type change is backward compatible. The other callers (test_move_cmd.py:26, test_recording.py:194/208/227, test_profile_readiness.py:168/196) ignore the return value and keep raise-only behaviour.
- Minor, non-blocking: those other callers do not yet assert the returned list empty. None of them is in Task 7's scope, and whether a broad `except` could swallow the raise there was not assessed in this round. See below.

### Out-of-Scope Observations

- test_recording.py and test_profile_readiness.py use `forbid_spend` without checking the attempts list. If any of those tests drives `emcee run` (whose per-package `except Exception` turns the raise into an error row), it has the same latent blindness this round fixed in test_run_plan.py. Worth a look in the whole-branch review: assert `spent == []` wherever the code under test has a broad catch.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.

Checks run: read the diff, the fix report, `cli.py:225-262` (`_process_one` order) and the provider call sites in `process.py`, and grepped every `forbid_spend` caller. No tests were re-run: no specific doubt arose that the report's runs and mutant proof do not already answer.
