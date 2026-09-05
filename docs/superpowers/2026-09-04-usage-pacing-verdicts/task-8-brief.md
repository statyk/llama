### Task 8: Mutation pass and documentation

A green suite is not evidence a constraint is load-bearing. Each mutation below is a one-line change that a loosely written test would happily keep passing.

**Files:**
- Modify: `CLAUDE.md` (the `llama get` command list and the LLM-layer bullet)
- Modify: `docs/workflow.md` (wherever the "usage limit reached" example failure is described)

- [ ] **Step 1: Mutation 1 — the catch ordering**

In `cli.py`'s `_process`, move the `except RateLimited` clause *below* the
`except (TaskFailed, HerderError, IAError)` clause. Python does **not** reject
this — the clause is simply unreachable, which is the whole point of the
mutation. Then run:

Run: `./.venv/bin/python -m pytest packages/llama/tests -q -k rate_limit`
Expected: FAIL — `RateLimited` subclasses `HerderError`, so the broad clause
swallows it and the run records a failure instead of pausing.
Restore the original order and confirm green.

- [ ] **Step 2: Mutation 2 — the no-retry set**

In `tasks.py:36`, remove `RateLimited` from the tuple.

Run: `./.venv/bin/python -m pytest packages/herder/tests/test_llm_tasks.py -q -k rate_limit`
Expected: FAIL — `assert 3 == 1`.
Restore and confirm green.

- [ ] **Step 3: Mutation 3 — the reset sanity bound**

In `limits.py`, raise `MAX_RESET_AHEAD_S` to `48 * 3600`.

Run: `./.venv/bin/python -m pytest packages/herder/tests/test_limits.py -q`
Expected: FAIL — `test_reset_past_today_rolls_to_tomorrow_only_within_the_bound`.
Restore and confirm green.

- [ ] **Step 4: Mutation 4 — the negative classification**

In `limits.py`, add `(re.compile(r"error", re.I), None)` to `_SIGNATURES`.

Run: `./.venv/bin/python -m pytest packages/herder/tests -q`
Expected: FAIL — the dropped-connection tests, which is exactly the guard that
keeps a network blip from idling a run for hours.
Restore and confirm green.

- [ ] **Step 4b: Mutation 5 — the gather re-raise**

In `stages/gather.py`, delete the `except RateLimited: raise` clause added in
Task 4b, leaving only the broad `except (TaskFailed, HerderError)`.

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_stage_gather.py -q -k rate_limit`
Expected: FAIL — the limit is swallowed and a `low-confidence structure
alignment` flag is written in its place, which is the permanent-wrong-flag
defect Task 4b exists to prevent.
Restore and confirm green.

- [ ] **Step 5: Update CLAUDE.md**

In the `## Commands` section, extend the `llama get` entry:

```
`llama get` takes `--wait/--no-wait`, `--max-wait <dur>` and `--no-pacing`
(also on `run approve`/`run resume`): when the claude_cli backend refuses
because a usage window is exhausted, the run pauses at the show boundary
rather than failing every remaining show — sleeping until the reset the
refusal names, or checkpointing the session as `paused` when the wait
exceeds `--max-wait` (default 6h). Resuming costs nothing for shows already
packaged: stage-level `should_run` skips them.
```

In the architecture section's LLM-layer bullet, add:

```
A usage-window refusal is classified as `herder.limits.RateLimited` (measured
signature: `You've hit your session limit · resets 11:10am (America/New_York)`),
carrying the reset instant parsed from the message itself — so pausing needs no
access to Claude Code's internal state. It is excluded from
`_with_transport_retry`, which would otherwise spend three more calls against
an empty window. Every failed `claude -p` is captured whole under
`~/.llama/llm-failures/`; the 7-day refusal's wording is still unobserved and
that capture is how it will be learned.
```

- [ ] **Step 6: Update docs/workflow.md**

Find the passage using `"usage limit reached"` as an illustrative
`failures[].error` string and add a sentence noting that such a failure now
pauses the run instead of being recorded per-show, with the session state
`paused` and a `resume_after` instant.

- [ ] **Step 7: Full suite and commit**

```bash
./.venv/bin/python -m pytest -q
git add CLAUDE.md docs/workflow.md
git commit -m "docs: record usage pacing and the measured rate-limit signature"
```

---

## Out of scope (phase 2)

Listed so no task quietly grows into them. All are specified in
`docs/superpowers/specs/2026-09-04-usage-pacing-design.md`:

- The usage-cache reader (`cachedUsageUtilization`) and its staleness ladder.
- Per-show cost capture (`UsageMeter`) and the learned Δ-utilization EWMA.
- Proactive percent thresholds (`five_hour_threshold`, `seven_day_stop`) and
  the pre-flight projection warning.
- The fixed rail (`shows_per_batch` / `--batch N`).
- The `llama pacing` read-only command.
- Backend gating of percent rules — irrelevant in phase 1, since the reactive
  path is driven by a refusal any backend could in principle raise.
