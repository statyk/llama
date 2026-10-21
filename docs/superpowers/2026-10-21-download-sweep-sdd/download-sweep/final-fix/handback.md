# final-fix handback (download-sweep, final-review fix wave), implementer on Opus

Status: DONE_WITH_CONCERNS (concerns are notes for the re-reviewer, not blockers)
Base 3f48bc0. Commits:
- 78886dc test(pacing): pin the per-show LLM-call baseline with a mixed run   (F1)
- fae128c fix(sweep): never answer a prompt or a human gate; survive a bad updated_at   (F2+F3)
- 931d2dd docs: sweep eligibility rulings (no human decisions, bad updated_at)   (F4)
Each commit was preceded by a green full suite; the log is in final-fix.log.

## F1: per-show LLM-call baseline pinned
- packages/llama/tests/test_pace_loop.py:1578 `_boundaries` takes `pids=("a",)`, and its docstring notes that `record` is stubbed.
- :1618 adds `test_a_mixed_run_records_only_the_show_that_called_the_llm`, parametrized over ("a","b") and ("b","a") with `llm=lambda pid: pid == "a"`. It asserts exactly one boundary.
- The vacuous `pacing-state.json`-absent assertions are removed from `test_a_download_only_resume_records_no_boundary` and `test_an_already_packaged_show_records_no_boundary`. The `recorded == []` and read-count assertions stay. I kept the already-packaged test rather than folding it into the new one.
- The new test passes on HEAD; it is a pin. The RED evidence is the mutant below.

**M1 mutant.** Method:
- Scratch copy made by `git archive HEAD` plus the F1 patch, in the session scratchpad.
- One edit in cli.py:646: `llm_calls() > calls_before` became `llm_calls() > 0`.
- Run from an empty cwd with the worktree venv's `python -m pytest`, `PYTHONPATH=<copy>/packages/llama/src:<copy>/packages/herder/src` and `PYTHONDONTWRITEBYTECODE=1`.
- Shadowing proven by a planted `SENTINEL_PLANTED` in the copy's locks.py: `llama.__file__` resolved inside the copy and the sentinel was True.

Prediction (written to the log before the run): `[pids0]` (a,b) goes RED with 2 boundaries, and `[pids1]` (b,a) stays green.

Result over test_pace_loop + test_sweep: `1 failed, 110 passed`. The one failure was `test_a_mixed_run_records_only_the_show_that_called_the_llm[pids0]`, with `E assert 2 == 1`. M1 is CAUGHT, as predicted.

## F2: the sweep makes no human decisions
All changes are in packages/llama/src/llama/sessions.py.

**`sweep_verdict` (:267):**
- :301: the `auto` check now applies in ANY state. It used to apply only when there was no marker. A request whose `auto` key is present and not `True` gets `needs attention`.
- :303: a run is `needs attention` when `_human_gated(req, run_dir.parent.parent)` is true.
- The request is read once, via `read_request`, so the read stays permissive.

**`_human_gated` (:246):**
- A recorded `human_gate` key decides on its own: any value other than `False` is gated.
- No key and `mode` is not `profile` (a missing `mode` counts as query): not gated.
- No key and `mode` is `profile`: the function calls `load_profile(root, name)` and reads `.human_gate`. These all count as gated:
  - a `profile` value that is not a non-empty str;
  - `ProfileError`, which covers a missing file, bad TOML or a schema failure;
  - `OSError` or `ValueError`.
- sessions.py now imports `llama.profiles`. There is no cycle: profiles imports only errors, models and workspace.

**`request.json` writers in cli.py:**
- :865: `_get_query` writes `"human_gate": False`.
- :905: `_get_profile` writes `"human_gate": profile.human_gate`.
- `_resume_locked` is unchanged and still passes `human_gate=False`.

**Tests:**
- packages/llama/tests/test_sweep.py `ELIGIBILITY` (from :169) gains these cases:
  - paused-past-auto-false and incomplete-auto-false: needs attention.
  - incomplete-auto-true: eligible.
  - recorded-human-gate, both incomplete and paused: needs attention.
  - recorded-no-human-gate: eligible, with no profile file present, so the recorded key decided.
  - profile-request-naming-no-profile (`profile: null`): needs attention.
  - query-without-gate-key and no-mode-without-gate-key: eligible.
- :232 `PROFILE_GATE` and :243 `test_a_profile_request_without_the_gate_key_reads_the_profile` cover gated, not-gated, missing, unparseable TOML and schema-invalid, each in the incomplete and paused states.
- :256 `test_a_recorded_gate_key_wins_over_the_profile`.
- packages/llama/tests/test_sessions.py:1698 `test_get_records_that_a_query_run_is_not_human_gated` and :1715 `test_get_profile_records_the_profile_human_gate[True|False]` drive the real writers.

**RED, captured before implementing:** 21 failures, every one for the expected reason.
- The eligibility and profile cases returned `None` where `needs attention` was expected.
- The writer tests failed with a KeyError on `human_gate`.

The minimal profile-load failure cases, not-gated and recorded-no-gate, passed on RED as expected, since today's behaviour already treats them as eligible.

## F3: a malformed `updated_at` no longer crashes the sweep
- sessions.py:281: `sweep_verdict` returns `needs attention` when `datetime.fromisoformat(info.updated_at)` raises `TypeError` or `ValueError`. The check runs after the running and awaiting checks. The bad run therefore never reaches `_sweep_runs`' sort and prints `skip <id>: needs attention`.
- sessions.py:183: `_updated_at` always returns a str, stringifying a non-str truthy value. A falsy value still falls back to the mtime. This was needed because a non-string `updated_at` crashed earlier than the sweep's sort: in `iter_sessions`' own sort, with mixed types (RED: `TypeError '<' not supported between instances of 'int' and 'str'`).
- Tests in test_sweep.py:
  - :266 `test_a_malformed_updated_at_is_needs_attention`, over `["not-a-date", 12345, ["2026-10-21"]]`.
  - :276 `test_a_malformed_updated_at_does_not_stop_the_sweep`, over "not-a-date" and 12345. The bad run is skipped, r1 and r2 are resumed oldest first, exit is 0 and the marker is untouched.
- RED: the sweep exited 1 with `ValueError: Invalid isoformat string` or the TypeError above, and the verdict tests returned `None`.

## F4: docs and spec
- Spec docs/superpowers/specs/2026-10-21-download-retry-and-run-sweep-design.md §6, under "Skipped … needs attention", gains three bullets labelled as operator rulings from the final review, 2026-10-21:
  - `auto` not `true` in any state.
  - Human-gated runs: the recorded key, the profile fallback, unloadable counting as gated, query not gated, and resume behaviour unchanged.
  - A malformed or non-string `updated_at` is skipped before the sort.
- CLAUDE.md, in the Commands bullet for `run resume --all`: the needs-attention list now states all three rulings.
- README.md:151-158: the `run resume --all` comment adds "was started without --auto, or is human-gated".
- Beyond the letter of F4, to keep the docs true: CLAUDE.md's "Four readers" note became "Five readers" and names `sessions.sweep_verdict`, which reads `auto` and `human_gate`. `read_request`'s docstring names `sweep_verdict` among the SWEEP callers.

## Full suite
`./.venv/bin/pytest -q -p no:cacheprovider` from the worktree. `llama.__file__` resolves inside the worktree. Result on 931d2dd:
`3964 passed, 1 skipped, 8 deselected, 26 warnings in 69.44s`, rc 0.
F1 alone (78886dc) was 3936 passed; F2+F3 (fae128c) was 3964 passed.

## Interpretations and concerns
1. A recorded `human_gate` that is anything other than `False` (for example `null` or `"yes"`) is treated as gated. This mirrors the existing `auto is not True` rule, in the safe direction.
2. A recorded key wins over the current profile: a profile edited since the run started neither re-gates nor un-gates the run. The ruling only specified the fallback for when the key is absent.
3. A run with criteria.json but NO request.json is not gated, because `{}` reads as a query run. Such a run predates request.json for profiles (before 2026-09-07). Its criteria carries `profile`, but the ruling names only the request, so I did not extend the fallback to `criteria.profile`. Flag this if you want it covered.
4. `run list` (`_humanize_age`) still crashes on a malformed `updated_at`. The ruling covers only the sweep. The final reviewer suggested fixing both readers together; I did not, as that is outside the ruling.
5. The deferred items were not touched: the body-raised Locked/RunMissing in `_resume_run`, the stubbed turned-live test, and the other minors.
