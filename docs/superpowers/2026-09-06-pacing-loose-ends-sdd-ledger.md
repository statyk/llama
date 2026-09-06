# SDD ledger — plan: docs/superpowers/plans/2026-09-06-pacing-loose-ends.md

Spec: `docs/superpowers/specs/2026-09-06-pacing-loose-ends-design.md`
Worktree: `/Users/shawn/projects/llama-wt-pacing-loose-ends`, branch `pacing-loose-ends`, base `660f588`
Test command (the ONLY valid one): `cd /Users/shawn/projects/llama-wt-pacing-loose-ends && ./.venv/bin/python -m pytest -q`
Baseline: 1871 passed, 7 deselected.

## Pre-flight conflict scan (2026-09-06 13:54 EDT)

Every symbol, helper and file the plan names was checked against the real tree before Task 1.

### Cross-task shared surfaces

| Tasks | Shared surface | Producer says | Consumer says | Finding |
|---|---|---|---|---|
| 3 → 6 | `CountingProvider` in `test_sessions.py` | T3 defines it | T6 "do not define a second copy" | Consistent; T6 must run after T3 |
| 4 → 5,6,7 | `RunWorkspace.request` + request.json shape | T4 adds `self.request` beside `self.criteria` (workspace.py:119 confirmed) | T5 reads it in `run_resume`; T6 gates after its write; T7 needs `iter_sessions` fallback for `info.query` | Consistent |
| 5 → 7 | `_interpret_and_stamp(config, ws, req)` | T5 creates it | T7 wraps its call in the RateLimited loop | Consistent |
| 6 → 7 | `PF_NOW` module constant in `test_sessions.py` | T6 Step 1 adds it | T7 uses it | Consistent; T7 must run after T6 |
| 4,5,6,7 | `_get_query` body | Edit order: request.json write (T4) → preflight gate (T6) → interpret loop (T5 then T7) | — | Sequential, non-overlapping regions. No conflict |
| 6 | `_execute` preflight vs `_get_query` preflight | T6 gates both | — | Two meter reads at query-mode start; spec accepts explicitly ("Accepted cost, stated rather than engineered away") |

### Per-task self-consistency

| Task | Tests vs code it specifies | Files created vs later touched | Finding |
|---|---|---|---|
| 1 | 3 tests; 2 drive the loop, 1 pins `decide()` untouched | cli.py `_pacing_line` at 295; insert point after `seven_day` block confirmed present | Agrees |
| 2 | 1 new test + 1 retired (`test_default_config_template_documents_every_pacing_knob`, confirmed at test_config.py:188) | needs `import re` — confirmed ABSENT, plan says add it | Agrees |
| 3 | 1 test, non-empty precondition before the equality | `fake_providers`/`FakeIA`/`JB_OFF` imported at test_sessions.py:21 | Agrees |
| 4 | 3 tests | `cli.py` has no module-level `import json` — confirmed (only `_json` inside `run_list`); plan says add it | Agrees |
| 5 | 3 tests; `read_model`, `Criteria`, `mark_paused`, `iter_sessions`, `write_artifact` all imported at test_sessions.py:9-16 | `run_resume`'s `if not ws.criteria.exists():` block confirmed verbatim at cli.py:939 | Agrees |
| 6 | 1 test; `cli.read_usage` is a module-level name (cli.py:16) so the monkeypatch resolves | `_execute`'s `slept = False` / `while True:` block confirmed verbatim at cli.py:346 | Agrees |
| 7 | 2 tests; `LimitedProvider(resets_at, times=1, then=None)` with `.calls` confirmed at test_sessions.py:328-343 | `_get_query`'s T6b comment block confirmed at cli.py:667-670 — T7 Step 6 must also fix CLAUDE.md | Agrees |

### Rulings from the scan

Ruling: the plan's Global Constraints name baseline `main @ 45f009b`, the spec names `origin/main @ 2386eb9`, and the worktree base is `660f588`. All three name the SAME measured baseline (1871 passed / 7 deselected), which I verified resolves inside the worktree. Treating the SHA divergence as cosmetic bookkeeping and proceeding. — Cost if wrong: the expected per-task test-count deltas (1874/1874/1875/1878/1881/1882/1884) would be offset by a constant, which the first task's full-suite run would surface immediately.

Ruling: test-count arithmetic across all seven tasks is internally consistent from 1871 (+3, +1-1, +1, +3, +3, +1, +2 = 1884). Adopting these as hard gates: a task reporting a lower total than predicted has lost an existing test and is a finding, not a rounding error. — Cost if wrong: a false BLOCKED on a legitimate count change.

No conflicts found requiring a ruling against plan text.

## Progress

