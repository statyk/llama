### Finding Verdicts

- **[Important] `-dirty` code identity accepted by string equality in `load_list`** — ADDRESSED. `packages/llama/src/llama/reapply.py:171-177` refuses before the equality check when `str(list_sha).endswith("-dirty") or sha.endswith("-dirty")` ("commit first and re-run the harness"). `str()` handles a `None` sha safely. The CLI resolves `code_identity` at call time (`cli.py:3147`, a function-local import), so the test patch of `llama.replay.code_identity` reaches it. Tests: `test_a_dirty_code_identity_is_refused_on_either_side` (test_reapply.py:708) covers a dirty list against a dirty running identity (the case the bug was about) and against a clean one, then a clean list against a dirty running identity. Each case asserts "commit first", so the pre-fix mismatch message would fail it. It also checks that clean/clean is still accepted. `test_the_cli_refuses_a_list_when_the_running_tree_is_dirty` checks exit 1 and that no batch dir is created. The autouse patch to `CLEAN_SHA` (test_reapply.py:419) keeps the suite independent of whether the checkout is committed.
- **[Ruled] Last-resort `except Exception` arm: FAILED, retryable, not counted, batch continues** — ADDRESSED. `cli.py` (the diff's +66-71) puts it after `RateLimited`, `(TaskFailed, HerderError)` and `(IAError, LlamaError, ValueError, OSError)`. It goes through `fail()`, which records `retryable=True` (not in dry-run) and sets `failed`, and it leaves `consecutive` alone. KeyboardInterrupt and SystemExit are BaseException, so they still propagate. `test_any_other_exception_fails_only_its_row` runs HerderError, RuntimeError, HerderError, success. The run does not stop (so the arm does not increment the counter), prints no traceback, records held-3 as retryable and exits 1.
- **[Ruled] Counter resets only on a real LLM success** — ADDRESSED. The guard is `out.briefing == "fresh" and out.outcome in ("cleared", "held")` (diff +80-85). The implementer's extra outcome guard is correct and necessary. `reapply.py:96` returns `needs-llm` carrying `legs.brief`, which can be "fresh", with no call made. `cleared`/`held` come back only from the apply path (`reapply.py:149`), and there `legs.brief == "fresh"` means `generate_briefing` ran and returned. The ruling's literal `briefing == "fresh"` alone would wrongly reset on a needs-llm row. `test_rows_that_made_no_llm_call_do_not_reset_the_failure_count` runs fail, reuse, fail, needs-llm/fresh, fail and asserts the stop, exit 1, and held-7 never reached. It would fail both under "reset on any success" and under "reset on briefing==fresh alone".
- **[Ruled] Both pause paths exit 1 after an earlier failed row, else 0** — ADDRESSED. Both the `PauseUntil` path and the `RateLimited` path now `raise typer.Exit(1 if failed else 0)` (diff +29, +52). `failed` is set only by `fail()`. `test_a_pause_after_a_failed_row_exits_1` covers both paths: LlamaError then RateLimited, then a re-run where the row fails again and the gate pauses. The existing pause tests with no prior failure still assert exit 0.
- **[Ruled] Test coverage: dry-run over an existing batch; held/needs-llm excluded from fresh and downloads; the 3-failure stop asserts exit 1** — ADDRESSED.
  - `test_dry_run_over_an_existing_batch_counts_and_skips_finished_rows`: `1 already finished`, no `would:` line, `progress.jsonl` byte-identical.
  - `test_dry_run_counts_fresh_briefs_and_downloads_only_for_rows_it_would_apply`: cleared, held, needs-llm and needs-brief, all fresh, give `2 fresh briefs, 2 first-time downloads`. `needs-brief` is a real `_PREDICTED` value (`reapply.py:43`).
  - test_reapply.py:213 adds `assert r.exit_code == 1`.
- **[Check] `test_reapply.py` emits no warnings under `-W error`** — ADDRESSED on the report's evidence. handback.md fix round 1 §6 shows `-W error` → `47 passed`, and says `-rw` listed no warnings. I did not re-run it: nothing in the diff raised a specific doubt, since the new tests only patch modules and invoke the CLI.

### New Breakage in the Fix Diff

- Minor — `cli.py` (diff +66-71): the last-resort arm prints `FAILED {slug}: {exc}` without the exception type. An unexpected `KeyError('x')` therefore shows as `FAILED slug: 'x'`, which is opaque for exactly the class of error this arm exists to catch. The same text goes into the `failed: ...` progress row. Suggest `f"{type(exc).__name__}: {exc}"` in this arm. Non-blocking.

No Critical or Important breakage.

### Out-of-Scope Observations

- `scripts/replay_holds.py:146` stamps `code_identity()` into the list unconditionally. A harness run from a dirty tree therefore produces a list that `reapply --from-list` is now guaranteed to refuse, and the operator finds out only after the full harness run. The harness could warn or refuse up front. Non-blocking.
- `replay.code_identity()` (`replay.py:129-142`) falls back to `version:{__version__}` when git is unavailable. Two different dev trees with the same version string would compare equal. The same non-uniqueness class as `-dirty`, but it applies only to non-git installs; the signed release binaries are fine. Non-blocking.
- (Pre-existing, from the implementer's own report) Minor 6: two concurrent runs of the same list can interleave outcome rows. It is unchanged and does not affect finished-ness.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.
