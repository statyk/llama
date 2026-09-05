# Spec-compliance verdict — Tasks 5 & 6 (usage-pacing phase 1)

Reviewer: spec-compliance (Opus). Read-only; no edits, no commits.
Diff reviewed: `19a4aa9..f403239` (2 commits, 6 files).
Authorities: `task-5-brief.md`, `task-6-brief.md`, and above them
`docs/superpowers/specs/2026-09-04-usage-pacing-design.md`
("Integration", "CLI and config", "Testing").

## Verdict

- **Task 5 — ✅ PASS**
- **Task 6 — ✅ PASS**
- **Overall — ✅ PASS.** Both tasks are implemented byte-for-byte as briefed,
  the authorized `_ATTENTION_LABELS`/`_ATTENTION_HINTS` addition is correct
  against every call site, and nothing in the diff starts building phase 2.
  Findings are all Minor.

Method note: I did not re-run the suite (per instruction). I did run three
small read-only `python -c` probes against the checked-out tree to answer
questions the diff alone cannot settle — whether the template test actually
pins the new block, whether all three duration fields validate, and whether a
bad duration surfaces as `ConfigError`. All three are recorded below with their
results.

---

## Task 5 — `llama/pacing.py` and the `[pacing]` config table

| # | Requirement (brief / spec) | Where met | Note |
|---|---|---|---|
| 5.1 | Create `packages/llama/src/llama/pacing.py` | `pacing.py:1-49` | **Byte-identical** to the brief's code block (diffed programmatically). |
| 5.2 | `parse_duration(text) -> float`, seconds, `ValueError` otherwise | `pacing.py:20-27` | Accepts `6h`/`90m`/`5h30m`/`45s`; regex anchors order h→m→s. |
| 5.3 | `format_delta(seconds) -> str` | `pacing.py:29-33` | Floors at 60 s; `4h 12m` / `1m`. |
| 5.4 | `sleep_until(when, echo)` chunked | `pacing.py:36-49` | `chunk_s=900` default; returns at once when `when` has passed. |
| 5.5 | Module-level `_sleep` / `_now` indirections | `pacing.py:15-17` | Both monkeypatched in the tests; no real clock, no real sleep. |
| 5.6 | Create `packages/llama/tests/test_pacing.py` | `tests/test_pacing.py:1-56` | **Byte-identical** to the brief. 7 tests — matches the report's +7. |
| 5.7 | `PacingConfig` with `enabled`/`wait`/`max_wait`/`unknown_reset_wait`/`reset_skew` | `config.py:98-116` | **Byte-identical** to the brief, docstring included. |
| 5.8 | `field_validator` added to the pydantic import | `config.py:5` | Additive; `model_validator` retained. |
| 5.9 | Duration strings validated at **load time** | `config.py:111-116` | **Verified by probe:** all three duration fields raise `ValidationError` on `"whenever"`; via `load_config` it surfaces as `ConfigError: invalid config at <path>: … pacing.reset_skew … not a duration`. Every duration-valued field is covered — `enabled`/`wait` are bools, so the field list is exhaustive. |
| 5.10 | `Config.pacing` field | `config.py:130` | Placed with the other nested models, `default_factory`, per the `WinnowConfig` recipe the spec names. |
| 5.11 | `[pacing]` block appended after `[winnow]` in `DEFAULT_CONFIG_TOML` | `config.py:236-256` | **Byte-identical** to the brief — all 21 lines, every comment, every default. Sits between `[winnow]` and `[artists]`. |
| 5.12 | Block must match `PacingConfig` defaults (pinned by `test_default_config_template_matches_defaults`) | `test_config.py:177-185` | **Verified by probe:** `Config().model_dump(exclude={"llm"})` contains `pacing`, parsed == default, and a deliberate perturbation (`max_wait = "7h"` in the template) makes the comparison unequal. The test genuinely covers the new block; it is not passing by omission. |
| 5.13 | `test_config.py` modified only if needed | not modified | Correct — the report says no adjustment was needed, and the probe confirms the block matches. |

**Exact-value fidelity (Task 5):** programmatic diff of the brief's three code
blocks and its TOML block against the shipped files returned **IDENTICAL** for
all four. Zero divergence — no benign drift to adjudicate.

---

## Task 6 — the `paused` session state

| # | Requirement (brief / spec) | Where met | Note |
|---|---|---|---|
| 6.1 | `STATE_PAUSED = "paused"` next to the other states | `sessions.py:17` | Spec ("Integration → Session state") asks for exactly this at `sessions.py:13-16`. ✓ |
| 6.2 | `_write` carries the pause block, **wholesale rewrite preserved** | `sessions.py:20-32` | **Byte-identical** to the brief. `_write` still constructs a fresh dict and hands it to `write_artifact` (`workspace.py:41-44`, unique-temp + atomic rename) — no read-modify-write, no partial update. `mark_complete` (`sessions.py:40`) calls `_write` with the new params defaulted to `None`, so it erases `resume_after`/`pause_scope`/`pause_reason` for free, exactly as it already erases `failures`. Pinned by `test_completing_a_paused_run_erases_the_pause_block`. |
| 6.3 | `mark_paused(ws, outcome, failures, resume_after, scope, reason)` | `sessions.py:59-67` | **Byte-identical** to the brief; signature matches the spec's "Integration" text verbatim. |
| 6.4 | `_state_of` whitelist admits `STATE_PAUSED` | `sessions.py:82-86` | **Byte-identical.** **Confirmed no silent degradation:** without this line a `"paused"` marker would fall through to `STATE_INCOMPLETE`; with it, `session_state` returns `STATE_PAUSED`, pinned by `test_paused_round_trips_the_resume_time`. Unrecognized states still fall back to `STATE_INCOMPLETE`. |
| 6.5 | `SessionInfo.resume_after` / `.pause_reason` | `sessions.py:102-103` | Both `str \| None = None`, additive defaults — no existing constructor call breaks. |
| 6.6 | Populate both in `iter_sessions` | `sessions.py:133-134` | `marker.get(...)`, so a pre-existing marker without the keys yields `None`. |
| 6.7 | `attention_sessions` surfaces a paused run with no change | `sessions.py:140-142` | **Confirmed by reading, not assumed:** the predicate is literally `s.state != STATE_COMPLETE` and is untouched by the diff. `test_a_paused_run_is_on_the_attention_list` pins it. |
| 6.8 | Render the resume time in `_print_sessions` | `cli.py:461-462` | Placed after the `if s.outcome:` append, before the per-failure loop — exactly where the brief says. Guarded on both `state == STATE_PAUSED` and `resume_after` truthiness. |
| 6.9 | Import `STATE_PAUSED` in `cli.py` | `cli.py:29` | Additive to the existing `from llama.sessions import (...)` block. |
| 6.10 | **(authorized addition)** `STATE_PAUSED` in `_ATTENTION_LABELS` and `_ATTENTION_HINTS` | `cli.py:2180-2183` | **Verified correct against every call site.** Both dicts have exactly two consumers: `_print_sessions` (`cli.py:456`, `_ATTENTION_LABELS.get(s.state, s.state)`) and `_print_attention` (`cli.py:2197-2198`, `.get(s.state, s.state)` and `.get(s.state, "llama run resume {id}").format(id=s.id)`). Both are `.get`-with-fallback, so the entries are purely additive — no `KeyError` surface added and no existing row changed. The value shapes match the existing entries: plain string label, `{id}`-templated hint. The label `"paused"` (6 chars) fits the `{label:<18}` column in both renderers without reflowing. `_ATTENTION_HINTS`'s `"llama run resume {id}"` is the right hint: `run_resume` (`cli.py:518-537`) gates only on `criteria.json` existing and does **not** filter on session state, so a paused run genuinely resumes with that command. Without the addition a paused run would have rendered the raw string `paused` (harmless via the label fallback) but `_print_attention` would have offered the default hint by accident rather than by design — the addition makes it intentional. |
| 6.11 | Tests appended to `test_sessions.py`, reusing `_run_ws` | `tests/test_sessions.py:290-321` | The brief's three tests **verbatim**; `_run_ws` (`test_sessions.py:202-205`) is reused and is `tmp_path`-only. Imports folded into the existing top-of-file block rather than re-imported inline — a deviation in *form* from the brief's snippet, **benign** and arguably better (matches the file's existing convention). 3 tests — matches the report's +3. |

**Exact-value fidelity (Task 6):** programmatic diff of `_write`, `mark_paused`
and `_state_of` against the brief returned **IDENTICAL** for all three. The
`cli.py` render line and the two dict entries match the brief / dispatch text
character-for-character.

---

## Scope creep

**None found.** Files touched are exactly the six expected:
`pacing.py` + `test_pacing.py` (new), `config.py`, `sessions.py`, `cli.py`,
`test_sessions.py`.

- `PaceOptions`, `pace_options`, `resume_at` — **all three ABSENT.** A
  repo-wide grep over `packages/**/*.py` returns zero hits. ✓
- `_execute` — **untouched.** The `cli.py` diff is three hunks only: the import
  line, the `_print_sessions` render line, and the two `_ATTENTION_*` dicts. No
  command signature changed anywhere.
- **No phase-2 groundwork smuggled in.** Checked explicitly against the spec's
  "CLI and config" block: the shipped `PacingConfig` carries **only** the five
  phase-1 fields. `shows_per_batch`, `batch_pause`, `five_hour_threshold`,
  `seven_day_stop`, `seven_day_warn` and `trust_age` are all absent, from both
  the model and the TOML. `pacing.py` contains no `decide()`, no snapshot
  reader, no EWMA, no `pacing-state.json`, no percent thresholds, no fixed rail,
  and no `llama pacing` command was added. The module docstring says so in
  prose, and the code matches the prose.
- `herder` is untouched by this diff and still imports nothing from `llama` or
  `emcee` (grep-verified). `llama.pacing` imports only `re`, `time`, `datetime`.

---

## Findings

**F1 (Minor) — the `cli.py` rendering has no test at all.**
Nothing in the suite exercises the `resumes {resume_after}` line
(`cli.py:461-462`) or the two new `_ATTENTION_*` entries (`cli.py:2180-2183`) —
a grep of `packages/llama/tests/` for `"resumes "`, `_print_sessions` and
`_ATTENTION` returns nothing. Deleting all three lines would leave the suite
green. This is faithful to the brief (Step 4 specified no test) and to the
dispatch text, so it is **not** a compliance failure — but given the project's
own "green suite ≠ pinned" lesson, and that the labels/hints addition was added
precisely because the fallback rendering was judged unacceptable, the fallback
being untestable-by-omission is worth one CLI-render test when Task 7 wires the
paused path end-to-end.

**F2 (Minor) — `_session_json` omits `resume_after`/`pause_reason`.**
`cli.py:2186-2189` still emits `{id, state, updated_at, query, profile,
outcome, failures}`. So `llama run list --json` (`cli.py:480`) and `llama
status --json` (`cli.py:2268`, `2295`) show a machine consumer `state:
"paused"` with no resume time, while the human table shows it. The briefs did
not ask for this and the spec only says `run list` "needs no change beyond
rendering the resume time", so this is within scope-as-briefed — flagging it so
Task 7 (or a follow-up) makes the choice deliberately rather than by omission.

**F3 (Minor) — `SessionInfo.state`'s inline comment is now stale.**
`sessions.py:96` still reads `# STATE_AWAITING | STATE_COMPLETE |
STATE_INCOMPLETE`. It should list `STATE_PAUSED`. Comment-only; the brief did
not call it out.

**F4 (Minor, informational) — `pacing.py` is not "pure" in the sense the spec's
"llama changes" paragraph asserts.**
That paragraph says "Same shape as `siblings.py` and `structure.py`: pure
functions, IO in the caller", but `sleep_until` performs the sleep itself via
`_sleep`. This is **not** a defect: the spec's own "Testing" section says "the
sleep is injected the way `tasks.py` already injects `_sleep`", which is exactly
what shipped, and the brief specifies this design literally. Noted only so the
tension is on the record before phase 2 adds the genuinely-pure `decide()`
alongside it.

**F5 (Minor, informational) — `test_default_config_template_matches_defaults`
pins values, not presence.**
Verified by probe that a wrong value in the `[pacing]` block fails the test.
But if the block were deleted from `DEFAULT_CONFIG_TOML` entirely, `parsed`
would fall back to the model defaults and the test would still pass. That is a
pre-existing property of the test's design (it affects `[winnow]`, `[artists]`
etc. identically), not something this diff introduced, and the block *is*
present. No action asked.

---

## Global constraints

| Constraint | Status |
|---|---|
| Python 3.11+, no new third-party deps | ✓ `pacing.py` imports `re`, `time`, `datetime` only; `config.py` adds `field_validator` from the already-imported pydantic. |
| Tests offline / deterministic — no wall clock in logic under test | ✓ `_now` monkeypatched in both `sleep_until` tests. |
| No real `$HOME` | ✓ `test_sessions` uses `tmp_path` throughout via `_run_ws`. `test_pacing`'s `Config()` reads `DEFAULT_ROOT` as a default *value* only — no filesystem access. |
| No real sleeping | ✓ `_sleep` monkeypatched; `test_sleep_until_returns_at_once_when_the_time_has_passed` monkeypatches it to `pytest.fail`, so a regression that sleeps is caught rather than merely slow. |
| `herder` must not import `llama`/`emcee` | ✓ grep-verified clean; `herder` untouched by this diff. |
| Commit style `type(scope): subject` + test command in body | ✓ `f894b34` "feat(llama): add [pacing] config and duration/sleep helpers" / `f403239` "feat(llama): add a paused session state carrying its resume time", both with `Test: ./.venv/bin/python -m pytest -q -> …` in the body. |
| Suite green, counts add up | ✓ per the report: 1684 baseline → 1691 (+7, `test_pacing.py`) → 1694 (+3, `test_sessions.py`). The +7/+3 are confirmed against the actual test-function counts in the two files. Not re-run, per instruction. |
| Correct interpreter (`python -m pytest`, not `.venv/bin/pytest`) | ✓ report used `./.venv/bin/python -m pytest -q` throughout; my own probes confirmed `llama` resolves to `/Users/shawn/projects/llama/packages/llama/src/llama/__init__.py`, i.e. the tree under review. |

## ⚠️ Cannot verify from diff

- **The suite results themselves** (1691 / 1694, 7 deselected). Taken from the
  report as instructed; not independently re-run. The delta arithmetic is
  internally consistent and the new-test counts match the files.
- **Whether the two commits were individually green.** The report asserts a
  full-suite run at each; only the final tree is checkable here.
- **The report's claim that the expected-fail steps were observed** (Step 2 of
  each brief). Plausible — the reported divergence for Task 5 (`ImportError:
  cannot import name 'pacing' from 'llama'` rather than the brief's predicted
  `ModuleNotFoundError`) is exactly what the `from llama import pacing` form
  produces, which is corroborating detail rather than a discrepancy — but it
  leaves no artifact in the diff.
- **`__pycache__` clearing before the runs.** Reported, not observable.

## Blocked

Not blocked. No orchestrator message needed.
