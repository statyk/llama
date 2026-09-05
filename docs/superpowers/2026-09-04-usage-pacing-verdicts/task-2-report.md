# Task 2 report — RateLimited classification and reset parsing

## Status: DONE

## What was done

Followed `task-2-brief.md` verbatim, in order:

1. **Step 1 — failing test.** Created `packages/herder/tests/test_limits.py`
   with the brief's 10 test functions, copied verbatim (including the
   `SESSION_LIMIT` and `CLOSED_MID` fixtures). Verified the U+00B7 middle
   dot survived the write by grepping the file and counting `chr(0xb7)`
   occurrences in the on-disk content (2, both in `SESSION_LIMIT` /
   `test_reset_survives_a_dst_boundary`'s local `text`).

2. **Step 2 — confirm it fails.**
   ```
   ./.venv/bin/python -m pytest packages/herder/tests/test_limits.py -q
   ```
   Result: `ModuleNotFoundError: No module named 'herder.limits'` (1 error
   during collection), exactly as the brief predicted.

3. **Step 3 — implementation.** Created
   `packages/herder/src/herder/limits.py` with `RateLimited`, `classify`,
   `parse_reset`, and the `_SIGNATURES`/`_RESET_RE` module constants —
   copied verbatim from the brief. No changes, no additions, no broadened
   patterns.

4. **Step 4 — export.** Added
   `from herder.limits import RateLimited, classify, parse_reset` to
   `packages/herder/src/herder/__init__.py`, placed directly after the
   `from herder.fake import FakeProvider` line as instructed (which also
   keeps the import block in alphabetical module order: fake, limits,
   provider, resolve, tasks).

5. **Step 5 — confirm it passes.**
   ```
   ./.venv/bin/python -m pytest packages/herder/tests/test_limits.py -q
   ```
   Result: `10 passed in 0.09s`.

6. **Step 6 — full suite.**
   ```
   ./.venv/bin/python -m pytest -q
   ```
   Result: `1663 passed, 7 deselected, 26 warnings in 5.97s`. This is
   exactly 1653 + 10 = 1663, matching the brief's expectation with no
   other change in count. The 26 warnings are pre-existing
   `DeprecationWarning`s from `multiprocessing.popen_fork` in unrelated
   concurrency tests (`test_atomic_write.py`, `test_concurrency.py`,
   `test_ledger_concurrency.py`, `test_locks.py`, `test_sessions.py`) —
   not touched by this task, not new.

7. **Step 7 — commit.** Staged exactly the three named files and committed
   as `baf633d` on branch `usage-pacing`:
   `feat(herder): classify usage-window exhaustion as RateLimited`
   (commit body states both test commands and their output, per the
   incremental-commit mandate).

## Scope adherence

- Only the three files the brief named were touched:
  `packages/herder/src/herder/limits.py` (new),
  `packages/herder/tests/test_limits.py` (new),
  `packages/herder/src/herder/__init__.py` (one import line added).
- Did not touch `packages/herder/src/herder/claude_cli.py` (Task 3) or
  `packages/herder/src/herder/tasks.py` (Task 4).
- Did not touch `packages/herder/src/herder/failures.py` (Task 1's file,
  landed at `05d6279`) — read nothing from it, imported nothing from it.
- Did not broaden `_SIGNATURES` or add patterns beyond the three the brief
  specifies (`hit your session limit`, the unverified weekly/7-day variant,
  `usage limit reached`).
- Did not relax `MAX_RESET_AHEAD_S` (5.5h) or any other constant.

## Anything surprising

Nothing. The brief's code compiled and passed on the first try with no
edits needed to the test values or implementation. The DST test
(`test_reset_survives_a_dst_boundary`, 2026-11-01) and the
different-caller-zone test both passed as given, confirming the brief's
claim that these values were hand-traced correctly before dispatch.

## Concerns

None. The implementation is pure (no wall-clock reads except the injected
`now` default of `datetime.now(timezone.utc)`, which is only reached when
a caller omits `now` — none of the tests exercise that path), has no new
third-party dependencies, and does not import `llama` or `emcee`.

## Commit

- `baf633d` — `feat(herder): classify usage-window exhaustion as RateLimited`
  (branch `usage-pacing`)

## Test commands and final output

```
$ ./.venv/bin/python -m pytest packages/herder/tests/test_limits.py -q
..........                                                               [100%]
10 passed in 0.09s

$ ./.venv/bin/python -m pytest -q
...
1663 passed, 7 deselected, 26 warnings in 5.97s
```

---

# Fix round 1 — mutation-testing findings (I1–I4, minors 5 & 10)

## Status: DONE

Dispatched by `sdd-orchestrator` after code-quality review found 7 of 8
one-line mutations survived the original 10 tests — the suite pinned the
message truncation but not the am/pm conversion, the 5.5h bound, the minute
guard, the rollover comparison, two of three `_SIGNATURES` entries, or the
entry ordering. Full findings in `task-2-quality-verdict.md`.

## What was done

### I1 + I2 — pinning tests (no behavior change)

Added 9 new test functions to `packages/herder/tests/test_limits.py`,
each targeted at exactly one surviving mutation:

- `test_reset_12am_resolves_to_midnight_not_noon` /
  `test_reset_12pm_resolves_to_noon_not_midnight` — pins the `% 12`
  am/pm conversion (M1). Every prior test used `11:10am`, where the
  correct formula and a naive `int(hour12) + 12` agree.
- `test_reset_just_over_the_bound_is_refused` (~6h10m out → `None`) /
  `test_reset_just_under_the_bound_is_accepted` (~5h10m out → accepted)
  — pins both edges of `MAX_RESET_AHEAD_S` (M2). Confirmed a bound of
  20h — a genuine day-long-sleep permission — passed all 10 original
  tests before this fix.
- `test_reset_out_of_range_minute_yields_no_reset` (`11:75am` → `None`)
  — pins the minute-range guard (M3).
- `test_reset_exactly_now_rolls_to_tomorrow` — pins `target <= local`
  over `<` (M4): `now` exactly equal to the named wall-clock time rolls
  forward and is then refused by the bound.
- `test_classifies_usage_limit_reached` (M5) and
  `test_classifies_seven_day_variant` (M6) — one text per previously
  untested `_SIGNATURES` entry.
- `test_specific_pattern_wins_when_generic_also_matches` — a text
  matching both the specific and the generic pattern; pins
  first-match-wins ordering (M8).

### I3 — widened the zone regex (production change)

`_RESET_RE`'s zone group changed from `[A-Za-z_]+/[A-Za-z_+-]+`
(exactly one slash, no digits) to `[A-Za-z_]+(?:/[A-Za-z0-9_+-]+)*`
(zero or more slash-segments, digits allowed within a segment). This
recognizes `UTC` — the likely zone on an unattended headless host,
the target deployment, and the previous regex's most consequential
miss — and multi-segment zones like `America/Indiana/Indianapolis`.
Added a comment above `_RESET_RE` recording which shapes are
deliberately still unhandled (`resets at ...`, `resets 11am` with no
minutes, a missing zone — all correctly yield `None`). Added
`test_reset_zone_utc_is_recognized` and
`test_reset_zone_multi_segment_is_recognized`.

This is the one behavior change beyond test additions. It only
*recognizes* previously-missed zone shapes; it cannot turn a
previously-accepted result into a wrong one, since the bound and
rollover logic are untouched and apply identically regardless of
which zone matched.

### I4 — labelled the speculative pattern, documented the ordering

Gave `usage limit reached` the same "Unverified: wording not observed"
comment its `seven_day` sibling already had (previously no comment at
all). Added a one-line comment above `_SIGNATURES` recording that
order is load-bearing ("most specific first ... first-match-wins").

### Minor 5 — noqa on the broad except

`except Exception:` at (now) `limits.py:82` gained
`# noqa: BLE001 - a malformed or unknown zone name must not crash the
caller`, matching the repo's own convention
(`failures.py:48`, `emcee/speech_text.py:91,99`, `llama/jerrybase.py:128`).
Per the orchestrator's explicit framing of this minor as a labelling/
consistency fix, the exception type itself was left broad (`Exception`),
not narrowed to `(ZoneInfoNotFoundError, ValueError)` as the reviewer's
fuller note also suggested — narrowing was not in the orchestrator's
scoped instruction and risked drifting into territory the orchestrator
marked deferred (minors 6–9, 11 were explicitly out of scope this round).

### Minor 10 — docstring fidelity

Fixed the module docstring's captured-string example (`limits.py:5`) to
use the real U+00B7 middle dot instead of an ASCII hyphen, matching the
test fixture.

## Mutation kill/restore evidence

Each of the 7 surviving mutations was re-applied verbatim to the fixed
module, run against the fixed test suite (confirmed RED — specifically
against the new test targeting it), then the file was restored from a
pre-fix-round backup and re-run (confirmed GREEN). One caveat found and
handled during this process: rapid in-place rewrites within the same
filesystem-mtime second occasionally left a stale `__pycache__/*.pyc` that
Python reused despite content changing — `find ... -name __pycache__
-exec rm -rf {} +` before each run avoided false readings; this was
caught once (an M8 restore initially read RED from stale bytecode) and
the sequence was redone cleanly with cache-clearing, which is the run
recorded below.

**M1** (`% 12` → naive `int(hour12) + 12`):
```
$ ./.venv/bin/python -m pytest packages/herder/tests/test_limits.py -q -k "12am or 12pm"
FF
2 failed, 19 deselected   # 12am: wrong instant; 12pm: ValueError (hour=24)
# restored:
$ ./.venv/bin/python -m pytest packages/herder/tests/test_limits.py -q -k "12am or 12pm"
2 passed, 19 deselected
```

**M2** (`MAX_RESET_AHEAD_S` 5.5h → 20h):
```
$ ./.venv/bin/python -m pytest packages/herder/tests/test_limits.py -q -k "bound"
...F.
1 failed, 4 passed, 16 deselected   # test_reset_just_over_the_bound_is_refused
# restored:
5 passed, 16 deselected
```

**M3** (delete the minute-range guard):
```
$ ./.venv/bin/python -m pytest packages/herder/tests/test_limits.py -q -k "out_of_range_minute"
F
1 failed, 20 deselected   # ValueError: minute must be in 0..59, not 75
# restored:
1 passed, 20 deselected
```

**M4** (rollover `target <= local` → `<`):
```
$ ./.venv/bin/python -m pytest packages/herder/tests/test_limits.py -q -k "exactly_now"
F
1 failed, 20 deselected
# restored:
1 passed, 20 deselected
```

**M5** (delete the `usage limit reached` signature):
```
$ ./.venv/bin/python -m pytest packages/herder/tests/test_limits.py -q -k "usage_limit_reached"
F
1 failed, 20 deselected
# restored:
1 passed, 20 deselected
```

**M6** (delete the `seven_day` signature):
```
$ ./.venv/bin/python -m pytest packages/herder/tests/test_limits.py -q -k "seven_day_variant"
F
1 failed, 20 deselected
# restored:
1 passed, 20 deselected
```

**M8** (reorder `_SIGNATURES`, generic pattern first) — redone with
explicit `__pycache__` clearing after the stale-bytecode false reading
noted above:
```
$ ./.venv/bin/python -m pytest packages/herder/tests/test_limits.py -q -k "specific_pattern_wins"
F
1 failed, 20 deselected   # scope == None, expected "five_hour"
# restored (cache cleared):
1 passed, 20 deselected
```

**I3 sanity check** (old narrow zone regex, to confirm the two new zone
tests actually depend on the widening rather than passing vacuously):
```
$ ./.venv/bin/python -m pytest packages/herder/tests/test_limits.py -q -k "zone_utc or zone_multi_segment"
FF
2 failed, 19 deselected   # both: parse_reset returned None
# restored (widened regex):
2 passed, 19 deselected
```

Final restore verified byte-identical to the pre-mutation fixed file via
`diff` (exit 0) before every commit-adjacent test run.

## Full test run after all fixes

```
$ ./.venv/bin/python -m pytest packages/herder/tests/test_limits.py -q
.....................                                                    [100%]
21 passed in 0.09s

$ ./.venv/bin/python -m pytest -q
...
1674 passed, 7 deselected, 26 warnings in 6.34s
```

1674 = 1663 (post-Task-2) + 11 new tests. Warnings are the same
pre-existing, unrelated `multiprocessing.popen_fork` deprecations noted
in the original report.

## Scope adherence

- Only the two files named by the orchestrator's fix request were
  touched: `packages/herder/src/herder/limits.py`,
  `packages/herder/tests/test_limits.py`.
- Did not touch `__init__.py` (Minor 11's namespace suggestion was not
  in scope this round).
- Fixed exactly I1, I2, I3, I4, minor 5, minor 10 — did not touch
  minors 6, 7, 8, 9, or 11, per explicit instruction to defer them.
- Did not narrow the `except Exception` beyond adding the noqa/reason
  comment (see Minor 5 discussion above) — a deliberate scope choice,
  not an oversight.

## Concerns

None. Every new test was proven load-bearing by mutation kill/restore
before commit. The one production behavior change (I3's zone-regex
widening) is additive-only and was independently sanity-checked against
the old regex to confirm the new tests actually depend on it.

## Commit

- `8433771` — `fix(herder): pin limits.py's unpinned constraints, widen zone regex`
  (branch `usage-pacing`)

