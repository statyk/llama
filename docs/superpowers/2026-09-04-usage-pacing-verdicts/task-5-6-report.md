# Task 5 & 6 report — usage-pacing phase 1 groundwork

Branch: `usage-pacing` (worked directly in `/Users/shawn/projects/llama`, no worktree, no venv created).
Baseline suite: 1684 passed, 7 deselected.

## Task 5 — `llama/pacing.py` and `[pacing]` config

**Files:**
- Created `packages/llama/src/llama/pacing.py`
- Created `packages/llama/tests/test_pacing.py`
- Modified `packages/llama/src/llama/config.py`: added `field_validator` to the pydantic import, added `PacingConfig` (fields `enabled`, `wait`, `max_wait`, `unknown_reset_wait`, `reset_skew`, with a `field_validator` on the three duration strings that imports `parse_duration` inside the function body, per the brief), added `pacing: PacingConfig = Field(default_factory=PacingConfig)` to `Config`, and appended the `[pacing]` block to `DEFAULT_CONFIG_TOML` right after `[winnow]`.
- `packages/llama/tests/test_config.py` was **not** touched — `test_default_config_template_matches_defaults` passed against the TOML block exactly as given in the brief, no adjustment needed.

**What it does:** `parse_duration` parses `6h`/`90m`/`5h30m`/`45s` forms into seconds and raises `ValueError` on anything else (including bare numbers, negative signs, unknown suffixes, empty string). `format_delta` renders `4h 12m` / `1m`-style human strings, floored at 60s. `sleep_until(when, echo, chunk_s=900)` naps in chunks via the module-level `_sleep`/`_now` indirections (so tests never touch the real clock or `time.sleep`), echoing progress after each nap that still leaves time remaining, and returning immediately if `when` has already passed.

**Step-by-step, exactly as directed:**
1. Wrote `test_pacing.py` verbatim from the brief.
2. Ran it — confirmed `ImportError: cannot import name 'pacing' from 'llama'` (module didn't exist; brief predicted `ModuleNotFoundError` for the module path, actual was an `ImportError` on the `from llama import pacing` form — same root cause, expected-fail confirmed).
3. Wrote `pacing.py` verbatim from the brief; edited `config.py` per the brief's diffs.
4. Cleared `__pycache__` (per the instrument-hazard warning) and ran `./.venv/bin/python -m pytest packages/llama/tests/test_pacing.py packages/llama/tests/test_config.py -q` → **28 passed**.
5. Ran the full suite: `./.venv/bin/python -m pytest -q` → **1691 passed, 7 deselected** (1684 baseline + 7 new tests in `test_pacing.py`). Green.
6. Committed: `f894b34` — "feat(llama): add [pacing] config and duration/sleep helpers", body states the test command and its result.

**Surprises:** None. Traced `sleep_until`'s chunk loop by hand for the 1-hour/900s-chunk test before running it: naps at 8:00→8:15→8:30→8:45→9:00, echoing after the first three (each leaves `left > 0`) and staying silent on the fourth (`left == 0`) before returning on the fifth iteration's `remaining <= 0` check — matches the test's `len(said) == 3` exactly, no fix needed.

**Concerns:** None.

## Task 6 — the `paused` session state

**Files:**
- Modified `packages/llama/src/llama/sessions.py`: added `STATE_PAUSED = "paused"`; widened `_write` to accept and persist `resume_after`/`scope`(as `pause_scope`)/`reason`(as `pause_reason`); added `mark_paused(ws, outcome, failures, resume_after, scope, reason)`; widened `_state_of`'s whitelist to include `STATE_PAUSED`; added `resume_after`/`pause_reason` fields to `SessionInfo`; populated both in `iter_sessions`.
- Modified `packages/llama/src/llama/cli.py`:
  - Added `STATE_PAUSED` to the `from llama.sessions import (...)` block.
  - In `_print_sessions`, added a line appending `"   resumes {s.resume_after}"` when `s.state == STATE_PAUSED and s.resume_after`, placed after the existing `if s.outcome:` block, before the per-failure loop.
  - Added the ONE ADDITION not in the brief: `STATE_PAUSED: "paused"` in `_ATTENTION_LABELS` and `STATE_PAUSED: "llama run resume {id}"` in `_ATTENTION_HINTS` (both near line 2178). Checked `_print_attention`'s consumption first — both dicts are read via `.get(s.state, default)`, so the addition is additive and matches the existing entries' shape exactly (plain string values, `{id}`-templated for hints).
- Modified `packages/llama/tests/test_sessions.py`: added `STATE_PAUSED`, `mark_paused` to the existing top-of-file `from llama.sessions import (...)` block (rather than re-importing inline inside the new tests, since the names weren't already present at module scope), then appended the brief's three test functions verbatim at the end of the file.

**Step-by-step, exactly as directed:**
1. Read `sessions.py` and the existing `_run_ws` helper / `mark_incomplete` tests in `test_sessions.py` to confirm the reuse points before writing.
2. Appended the three test functions; ran `./.venv/bin/python -m pytest packages/llama/tests/test_sessions.py -q` → confirmed failure: `ImportError: cannot import name 'STATE_PAUSED' from 'llama.sessions'`, as predicted.
3. Implemented `sessions.py` per the brief's diffs.
4. Implemented the `cli.py` `_print_sessions` line, the session import, and the `_ATTENTION_LABELS`/`_ATTENTION_HINTS` addition (the extra requirement from the dispatch instructions, not in the brief itself).
5. Cleared `__pycache__` and ran `./.venv/bin/python -m pytest packages/llama/tests/test_sessions.py packages/llama/tests/test_run_namespace.py -q` → **51 passed**.
6. Ran the full suite: `./.venv/bin/python -m pytest -q` → **1694 passed, 7 deselected** (1691 + 3 new tests in `test_sessions.py`). Green.
7. Committed: `f403239` — "feat(llama): add a paused session state carrying its resume time", body states the test command and its result.

**Surprises:** None. `RunWorkspace.name` already exists (set in `__init__`), so the brief's `ws.name` usage in the new tests needed no extra plumbing.

**Concerns:** None. Confirmed I did not touch `_execute`, any command signature, `PaceOptions`, `pace_options`, or `resume_at` — those are Task 7's, out of scope here.

## Final state

- Two commits, in order:
  1. `f894b34` — feat(llama): add [pacing] config and duration/sleep helpers
  2. `f403239` — feat(llama): add a paused session state carrying its resume time
- Full suite green at each commit; final: `./.venv/bin/python -m pytest -q` → **1694 passed, 7 deselected**.
- No takeover sentinels (`.../scratchpad/sdd/TAKEN_OVER` or `.../scratchpad/sdd/taken-over/b56`) were present at either commit point.
- Nothing was left uncommitted; `git status` clean after the second commit.

## Fix round 1 — code-quality verdict (I1-I6 + one-line comment)

Read the full verdict at `.superpowers/sdd/2026-09-04-usage-pacing-phase1/task-5-6-quality-verdict.md`
(55 mutations, 22 genuine survivors after 4 provably-equivalent mutants). All six
Important findings were fixed; the eleven Minor findings were left untouched as
directed.

### I2 — `parse_duration`'s trailing-garbage / out-of-order rejection

`test_parse_duration_rejects_nonsense` (`packages/llama/tests/test_pacing.py`)
gained three cases: `"6h banana"`, `"5h30m!"`, `"6s30m"`. No production code
changed — the `$` anchor was already correct; only the reject-list's coverage
was missing.

- Mutation proved: dropped the `$` anchor from `_DURATION_RE` in `pacing.py`.
- RED: `test_parse_duration_rejects_nonsense` failed —
  `Failed: DID NOT RAISE ValueError` (1 failed, 11 passed).
- Restored, GREEN: 12 passed.

### I3 — `format_delta`'s one-minute floor

Added `test_format_delta_floors_short_deltas_at_one_minute`:
`format_delta(5) == "1m"` and `format_delta(0) == "1m"`.

- Mutation M10 proved (drop the floor: `total = int(seconds)`): RED —
  `assert '0m' == '1m'` (1 failed, 11 passed). Restored, GREEN: 12 passed.
- Mutation M8 also proved (`max(int(seconds), 60)` → `max(int(seconds), 0)`):
  same RED/GREEN result — the one test kills both floor mutations.

### I4 — the validator's per-field coverage

`test_pacing_config_rejects_an_unparseable_duration` is now
`@pytest.mark.parametrize("field", ["max_wait", "unknown_reset_wait", "reset_skew"])`,
constructing `PacingConfig(**{field: "whenever"})`.

- M31 (validator reduced to `("max_wait",)`): RED — the `unknown_reset_wait`
  and `reset_skew` parametrizations both failed `DID NOT RAISE Exception`
  (2 failed, 31 passed). Restored, GREEN: 33 passed.
- M33 (drops `reset_skew` only): RED — `reset_skew` parametrization failed
  (1 failed, 32 passed). Restored, GREEN: 33 passed.
- M34 (drops `unknown_reset_wait` only): RED — that parametrization failed
  (1 failed, 32 passed). Restored, GREEN: 33 passed, byte-identical to
  the pre-mutation file (`diff` confirmed).

### I5 — `sleep_until`'s `chunk_s=900` default

Added `test_sleep_until_defaults_to_900s_chunks`: calls `sleep_until` without
passing `chunk_s`, and asserts the first nap (`naps[0]`) is exactly `900`.

- Mutation `900 → 1`: RED — `assert 1 == 900` (1 failed, 11 passed).
- Mutation `900 → 60000`: RED — `assert 1000.0 == 900` (1 failed, 11 passed).
- Restored after each, GREEN: 12 passed both times.

### I6 — `sleep_until` on a naive `when`

Per the orchestrator's ruling (raise, don't coerce — a wrong UTC coercion on a
sleep duration is a silent multi-hour error), added a guard:
```python
if when.tzinfo is None:
    raise ValueError(f"sleep_until requires a timezone-aware datetime, got naive {when!r}")
```
plus a docstring paragraph stating the aware-only contract, and
`test_sleep_until_rejects_a_naive_when` (asserts `pytest.raises(ValueError)` on
a naive `datetime`, with `_sleep` stubbed to fail the test if ever called).

- Mutation proved: removed the guard entirely. RED — the test failed with the
  *original* bare `TypeError: can't subtract offset-naive and offset-aware
  datetimes` surfacing instead of `ValueError` (1 failed, 11 passed).
- Restored, GREEN: 12 passed, byte-identical to the pre-mutation file
  (`diff` confirmed).

### I1 — the `cli.py` half of Task 6 was entirely unpinned

This was the largest gap: reverting all of `cli.py` to its pre-Task-6 revision
(`19a4aa9`) left the full suite green. Three new CLI-level tests were added,
plus one direct-access unit test, across two files:

- `packages/llama/tests/test_run_namespace.py` (the `run list` surface,
  i.e. `_print_sessions`):
  - `test_run_list_shows_paused_label_and_resume_suffix` — a paused session
    shows a `paused` label (checked as `line.split()[1]`, the exact label
    column) and a `resumes 2026-09-04T15:10:00+00:00` suffix; a sibling
    incomplete session's line carries no `resumes` text.
  - `test_run_list_resume_suffix_requires_paused_state` — writes a
    `session.json` marker directly (state `incomplete`, `resume_after` set)
    to exercise the `s.state == STATE_PAUSED` guard itself. This case can't
    be produced through the public `mark_*` API (`mark_incomplete` never
    sets `resume_after`), but a legacy/corrupted marker could still hit it,
    and the mutation that drops the state check from the `if` (M46) is only
    caught this way.
  - `test_attention_dicts_carry_a_paused_entry` — indexes
    `cli._ATTENTION_LABELS[STATE_PAUSED]` and `cli._ATTENTION_HINTS[STATE_PAUSED]`
    directly (not via `.get(state, default)`), because both dicts' fallback
    defaults happen to equal the values chosen for `STATE_PAUSED` — an
    output-only CLI assertion cannot distinguish "entry present" from "entry
    deleted, default coincides" for M43/M44.
- `packages/llama/tests/test_status_cmd.py` (the `status` surface, i.e.
  `_print_attention`, which is where the hint actually renders —
  `_print_sessions`/`run list` never shows the hint):
  - `test_status_attention_shows_paused_label_and_resume_hint` — asserts the
    exact label column is `paused`, the hint is
    `llama run resume <id>`, and `llama run approve <id>` is absent.

**A self-caught test bug, fixed before use as evidence:** the first draft of
both CLI tests named the workspace `s-paused` / `2026-09-04-paused`, so
`assert "paused" in ...output` was trivially satisfied by the *id* substring
regardless of what the label actually said. Caught while proving M48 (label →
`"zzz"`): only the direct-dict test went red, not the two CLI tests, which
should have also failed. Renamed both workspaces to `s-onhold` /
`2026-09-04-onhold` and switched to exact label-column assertions
(`line.split()[1] == "paused"`); re-ran M48 and all three tests correctly
went red together.

Mutations proved (each: mutate → RED → restore → GREEN, `__pycache__` cleared
and `PYTHONDONTWRITEBYTECODE=1` around every run):

- **M53** (revert all of `cli.py` to `19a4aa9`): RED —
  `test_run_list_shows_paused_label_and_resume_suffix` (assertion on the
  `resumes` suffix) and `test_attention_dicts_carry_a_paused_entry`
  (`KeyError: 'paused'`) both failed; 2 failed, 72 passed. (The `status` test
  did *not* fail here — its label/hint assertions coincide with the
  `.get(..., default)` fallback text for this specific case, same root cause
  as the M43/M44 note above; this is expected and is exactly why the direct
  dict test exists.) Restored, GREEN: 74 passed, file byte-identical
  (`diff` confirmed).
- **M45** (delete the `resumes {resume_after}` line): RED — 1 failed, 52
  passed. Restored.
- **M46** (fire the `resumes` line for every state, not just paused): RED
  against `test_run_list_resume_suffix_requires_paused_state` — 1 failed, 53
  passed. Restored.
- **M47** (paused hint → `llama run approve {id}`): RED against both
  `test_attention_dicts_carry_a_paused_entry` and
  `test_status_attention_shows_paused_label_and_resume_hint` — 2 failed, 52
  passed. Restored.
- **M48** (paused label → `"zzz"`): RED against all three new CLI/dict tests
  — 3 failed, 51 passed. Restored.
- **M43** (delete `STATE_PAUSED` from `_ATTENTION_LABELS`): RED —
  `KeyError: 'paused'` in the direct-dict test; 1 failed, 53 passed. Restored.
- **M44** (delete `STATE_PAUSED` from `_ATTENTION_HINTS`): RED —
  `KeyError: 'paused'` in the direct-dict test; 1 failed, 53 passed. Restored
  to the exact original, `diff` confirmed identical.

### One-line comment fix (m8, not blocking, folded in as instructed)

`packages/llama/src/llama/sessions.py`: `SessionInfo.state`'s inline comment
now reads `STATE_AWAITING | STATE_COMPLETE | STATE_INCOMPLETE | STATE_PAUSED`.

### Final state, fix round 1

- One commit: `42d90a4` — "fix(llama): close mutation-testing gaps in pacing
  and the paused-state CLI rendering".
- Files touched: `packages/llama/src/llama/pacing.py` (the naive-`when` guard
  + docstring only — everything else in I2/I3/I4/I5 was test-only),
  `packages/llama/src/llama/sessions.py` (one-line comment), and three test
  files (`test_pacing.py`, `test_run_namespace.py`, `test_status_cmd.py`).
  `config.py` and `cli.py` needed **no permanent changes** — every finding in
  those two files was a coverage gap in already-correct code, confirmed by
  restoring each file byte-identical after its mutation proofs (`diff`
  checked).
- Full suite: `./.venv/bin/python -m pytest -q` → **1703 passed, 7 deselected**
  (1694 before this round + 9 new/expanded tests: 1 in `format_delta`, 1
  `sleep_until` default-chunk test, 1 `sleep_until` naive-datetime test, 2
  from parametrizing the validator-rejection test 1→3, 3 in
  `test_run_namespace.py`, 1 in `test_status_cmd.py`).
- No takeover sentinels present (`.../scratchpad/sdd/TAKEN_OVER` or
  `.../scratchpad/sdd/taken-over/b56fix1`) at commit time.
- `_execute`, all command signatures, and `PaceOptions`/`pace_options`/
  `resume_at` remained untouched — confirmed by `git diff --stat`, which
  shows only the five files listed above.

**Concerns:** None. All eleven Minor findings (m1-m11) were left exactly as
found, per the orchestrator's instruction not to touch them.
