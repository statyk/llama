### Spec Compliance

- ✅ Spec compliant. `packages/emcee/src/emcee/cli.py` matches the brief's Step 3 code, and the spec §5 behaviour holds:
  - The plan and the prompt go to stderr (cli.py:360-400, :518 `err=True`).
  - `--yes/-y` exists (diff L175-177).
  - No TTY and no `--yes` prints the plan, then refuses with exit 1 (cli.py:514-517).
  - A decline prints `nothing voiced` and exits 1 only if an error row was printed (cli.py:518-520).
  - `--dry-run` returns before the question (diff L292-297).
  - Nothing to voice means no plan and no prompt, but the stale-move note still prints (diff L287-290).
  - A move_problem row is checked before the ready check (cli.py:481).
  - A package missing track audio is skipped ahead of the dry-run row and the plan (diff L270-273).
  - Voicing runs over `to_voice` from the single `_load_station` scan (diff L307-311).
  - Step 4's `--yes` edits are in all three listed test files (diff L355, 382, 405, 428, and the test_run_cmd hunks).
- ⚠️ Cannot verify from the diff alone: that `PackageStatus.profile` is the EFFECTIVE profile everywhere (Task 4). The plan's TTS grouping (`assignment_for(config, s.profile)`, diff L140) depends on it. The ttb tests resolving to gregg are indirect evidence.

### Strengths
- Strict surface 1 is structurally sound in the production code. `_process_one` (the only spend path) is reachable only from the loop at diff L308. That loop sits after the dry-run `return`, the non-TTY `Exit(1)` and the declined `Exit`. EOF and Ctrl-C at `typer.confirm` raise `Abort`. I probed HEAD: `Proceed? [y/N]:Aborted.`, exit 1, nothing spent.
- Named risk: a spend path that `forbid_spend` does not cover. Checked: `_process_one` builds TTS through `process.speech_for_voicing` → `_speech_from` → `process_mod.speech_provider_for` (process.py:129). Preflight runs on that object. So `forbid_spend` (helpers.py:226-233) patches the right module globals.
- Named risk: the plan prints `-` instead of the model for hosted backends. Checked tts/resolve.py:70-74: hosted backends always resolve a concrete model. Only fake/unknown backends give `None`, so `-` appears only on the test backend, as the brief intends.
- The `_presenter_or_marker` refactor keeps `_dry_run_marker`'s output byte-identical (the leading two spaces moved to the caller, diff L59-61). It shares the never-raises marker logic between `--dry-run` and the plan, without copying it.
- `test_the_plan_is_printed_before_the_first_llm_or_tts_provider` and `test_run_voices_from_the_one_scan_it_planned_from` pin ordering and single-scan by spying on real call order rather than mocking.
- Coverage of decline, dry-run, `--yes --dry-run` and the no-TTY path is strong. Those tests assert exit 0, the refusal message, or the absence of `Proceed?`, so they do catch spend that leaks.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
- **packages/emcee/tests/test_run_plan.py:197-206 (`test_eof_at_the_prompt_spends_nothing`): the test passes when EOF at the prompt is treated as yes and spend is attempted on every package (plan-mandated, verbatim from the brief).**
  - Why it is vacuous: `forbid_spend`'s `AssertionError` is raised inside `_process_one`, and `run`'s per-package `except Exception` (cli.py ~527) swallows it into an error row. The run then exits 1 and the manifests stay untouched, because provider construction comes before the manifest clear. The test asserts only `exit_code != 0` and unchanged manifests, so the failure it exists to catch satisfies both.
  - Measured with a mutant in a scratch `git archive` copy, imports proven to resolve inside the copy. I wrapped `typer.confirm` so that `Abort` yields `True`. Prediction: the EOF test survives. Result: all 19 tests in test_run_plan.py passed. A probe of the mutant shows stderr `error: emerson/fresh/ttb1/ttb2: AssertionError: LLM or TTS spend`, exit 1.
  - Why it matters: this is strict surface 1's EOF path, and it is the only test of it.
  - Fix, either of:
    - (a) Assert `"error:" not in result.stderr` and `"voiced:" not in result.stdout` (and optionally `"Aborted" in result.stderr`, `exit_code == 1`).
    - (b) Better, since it fixes the class: make `forbid_spend` also record attempts in a list the tests assert empty, so a spend signal cannot be swallowed by `run`'s error-row handler.
  - The same blindness affects `test_any_error_row_exits_1[declined]` (test_run_plan.py ~256-275): exit 1 is expected anyway, and nothing asserts `nothing voiced` / no `voiced:`. A decline-ignored mutant is still caught there by `test_a_declined_prompt_voices_nothing_and_exits_0`, whose exit-0 assertion makes it sensitive.

#### Minor (Nice to Have)
- **cli.py:323-325 `_stdin_is_tty`:** `sys.stdin.isatty()` raises `AttributeError` when fd 0 is closed (`sys.stdin is None`, e.g. `emcee run <&-`). It fails closed (no spend), but with a traceback instead of the refusal message. Fix: `return sys.stdin is not None and sys.stdin.isatty()`.
- **Untested inputs:**
  - Nothing tests the `-y` short alias.
  - Nothing tests bare Enter at the prompt (default decline). The `[y/N]` string assertions pin `default=False` only indirectly.
- **packages/emcee/tests/test_run_cmd.py:437 (brief-mandated):** `assert result.stderr == ""` was weakened to `"error:" not in result.stderr`. That no longer detects stray non-`error:` stderr output from the raising `close()`, such as a traceback or warning. A tighter form would assert that every stderr line comes from the plan block.
- **cli.py:464-471 with :481, `--assigned`:** a package whose recorded move targets a profile with no `[assign.profiles]` entry is dropped silently. Its effective profile is that target, so `assignment_for(...).source != "profile"` filters it out before the move_problem error row (the same holds under a `--profile` that does not name the target). It is never voiced, so no spend risk. But the spec's run error row for that package is only shown unfiltered. This is pre-existing filter semantics; consider whether the operator should still see it.
- **Not a defect:** EOF/Ctrl-C at the prompt exits 1 with `Aborted.` even when no error row exists. Spec §5 does not define EOF, so this is fine, but the docstring's exit-code paragraph (diff L229-230) does not mention it.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The production code meets spec §5 and strict surface 1. Every spend path is gated behind the dry-run return, the TTY refusal and the confirm, and the confirm fails closed on EOF. But the only test of the EOF path survives an "EOF means yes" mutant, because `run` swallows `forbid_spend`'s exception into an error row. That is a test-only fix: tighten that test's assertions, or make `forbid_spend` record attempts.
