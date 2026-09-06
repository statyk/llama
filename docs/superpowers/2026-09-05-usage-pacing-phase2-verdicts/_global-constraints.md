## Global Constraints

- **Tests are offline and deterministic.** No wall-clock reads, no real `$HOME`, no subprocess spawns, no sleeping. `decide()` takes `now`; `read_usage` takes an injected `runner`.
- **`read_usage` and `parse_usage_text` never raise.** Every failure path returns `None`.
- **Backend gating:** the proactive rules run only when `config.llm_for("default").backend == "claude_cli"`. Under `openrouter` or `fake` the meter is never read.
- **`RateLimited` subclasses `HerderError`**, so every new `except RateLimited` must be ordered **before** any `except HerderError` in the same try block.
- **Do not touch `openrouter.py`.** openrouter pacing is an explicit non-goal.
- **Do not add `--batch`, `--force`, or `trust_age`.** They were proposed in the phase-1 spec and are deliberately not introduced.
- **Venv discipline (from CLAUDE.md):** in a worktree, give the worktree its own `.venv` and run `./.venv/bin/pytest`. Never run a `.venv/bin/*` console script from a copy of the tree. Verify with `./.venv/bin/python -c "import llama; print(llama.__file__)"`.
- Full suite: `pytest -q` from the repo root. Current baseline: 1742 tests passing.

## File Structure

| File | Responsibility |
| --- | --- |
| `packages/herder/src/herder/limits.py` | *Modified.* `parse_reset` gains a dated form and a per-call max-ahead bound. Refusal classification unchanged. |
| `packages/herder/src/herder/usage.py` | *New.* `Meter`, `UsageReading`, `parse_usage_text` (pure), `read_usage` (subprocess). Headroom only — no refusal logic. |
| `packages/llama/src/llama/pacing.py` | *Modified.* Gains `Proceed`, `PauseUntil`, `Progress`, `decide()`. Existing duration/sleep/`PaceOptions` helpers unchanged. |
| `packages/llama/src/llama/pacing_state.py` | *New.* EWMA over per-show deltas, persisted to `<root>/pacing-state.json` under a `file_lock`. |
| `packages/llama/src/llama/config.py` | *Modified.* `PacingConfig` gains two ceilings; `DEFAULT_CONFIG_TOML` gains the matching block. |
| `packages/llama/src/llama/cli.py` | *Modified.* Three new gate points in `_execute`, the run-level catch, the forecast line, and the `llama pacing` command. |
| `packages/herder/tests/test_usage.py` | *New.* Parser and reader tests. |
| `packages/llama/tests/test_pacing_decide.py` | *New.* Policy tables. |
| `packages/llama/tests/test_pacing_state.py` | *New.* EWMA and persistence. |
| `packages/llama/tests/test_pace_loop.py` | *Modified.* Run-level catch and gate integration. |

---

## Notes for the executor

- **The four constants** (`FIVE_HOUR_MAX_AHEAD_S`, `SEVEN_DAY_MAX_AHEAD_S`, `EWMA_ALPHA`, the two ceilings) are policy, not tuning targets. Do not sweep them.
- **Do not unify `_meter` with the provider construction in `pipeline.make_providers`.** The meter read is not an LLM call and must not go through the tier/model resolution ladder.
- **`herder` must not import from `llama`** — enforced by `packages/herder/tests/test_no_llama_imports.py` and `packages/emcee/tests/test_no_llama_imports.py`.
- If a task's test needs a workspace fixture that `test_pace_loop.py` does not already have, add it to that file rather than to `conftest.py`; the phase-1 pause tests live there and the helpers should stay beside them.
