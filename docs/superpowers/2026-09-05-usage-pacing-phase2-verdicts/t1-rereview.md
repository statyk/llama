# Task 1 — scoped re-review of fix round 1 (`9ee737b..e2ada6a`)

Scope: verdict the two open findings, and flag breakage introduced by the fix
diff itself. Not a re-review of the task.

## Harness (built first, proven before any verdict)

Never touched the worktree. `$D/work/t1-rereview/conftest.py` reads
`packages/herder/src/herder/limits.py` from the worktree, applies one string
mutation in memory, `exec`s it into a fresh `types.ModuleType("herder.limits")`,
and injects it as `sys.modules["herder.limits"]` **and** `herder.limits` before
collection; `test_limits.py` (a copy) then binds against the mutant via both its
`from herder import limits` and its `from herder.limits import ...` forms. Each
mutation asserts its anchor text appears exactly once and aborts otherwise, so a
silently-missed mutation cannot masquerade as a passing control.

Runner: `/Users/shawn/projects/llama-wt-pacing2/.venv/bin/python -m pytest`
(never the shebanged `.venv/bin/pytest`).

    MUTATION=none        → 29 passed                              [control]
    MUTATION=zoneguard   → 1 failed, 28 passed                    [caught]
    MUTATION=valueerror  → 1 failed, 28 passed                    [caught]
    MUTATION=order       → 1 failed, 28 passed                    [caught]
    MUTATION=timeonly_zone → 1 failed, 28 passed                  [caught, pre-existing test]

Control green + four mutants red: the harness demonstrably reaches the code
under test.

## I1 — ADDRESSED

`packages/herder/tests/test_limits.py:222`
(`test_dated_reset_degrades_to_none_on_a_bad_zone_or_impossible_date`).

The implementer's claim that no source change was needed is correct — verified
independently, not taken on trust:

- `git show 9ee737b:.../limits.py` vs the worktree file parse to **identical
  ASTs once docstrings are normalized** (`AST-EQUAL-IGNORING-DOCSTRINGS: True`).
  So the whole `limits.py` half of the fix diff is comment + docstring text and
  cannot have changed behavior. The two guards (`limits.py:88-91`, the
  `try/except Exception` around `ZoneInfo`; `limits.py:96-101`, the year loop's
  `except ValueError: continue`) already existed; only the pin was missing.

- The pin genuinely pins. Both mutations the finding names go red, and red on
  exactly this test:
  - remove the `ZoneInfo` try/except in `_dated_target` →
    `ZoneInfoNotFoundError: 'No time zone found with key Mars/Olympus'`
    propagates out of `parse_reset`; `1 failed, 28 passed`.
  - remove `except ValueError: continue` →
    `ValueError: day 29 must be in range 1..28 for month 2 in year 2026`;
    `1 failed, 28 passed`.

- Blast radius 1 in both cases, which independently reproduces the finding's
  premise: before this test, 28 other tests in the file (and per the full-suite
  run below, the rest of the suite) stayed green under both mutations.

- Bonus check, to confirm the finding's scope was the whole gap: the *time-only*
  branch's `ZoneInfo` guard (`limits.py:154-157`) was already pinned —
  removing it reddens the pre-existing
  `test_unknown_zone_or_unparseable_time_yields_no_reset`. So the dated branch
  was the sole unpinned guard, and it is now covered.

The module contract ("`parse_reset` never raises") is now enforced on both
branches.

## I2 — ADDRESSED

Three things were required; all three landed.

1. **Comment corrected** — `limits.py:57-65`. The false "the time-only pattern
   cannot match it anyway" claim is gone, replaced by the accurate statement
   that ordering decides which clause wins on a multi-clause text and that
   `_RESET_DATED_RE.search` scans the whole string. The replacement text is
   accurate against the code: `parse_reset` searches the dated pattern first and,
   when it matches, never consults the time-only pattern — including when
   `_dated_target` degrades to `None`, in which case `parse_reset` returns `None`
   outright rather than falling back.

2. **Contract documented** — `limits.py:139-143`, in `parse_reset`'s docstring:
   at most one `resets ...` clause per text; on more, the dated form wins
   wherever it appears, silently discarding a time-only clause; multi-clause
   callers slice per-clause.

3. **Winner pinned** — `test_limits.py:236`
   (`test_dated_form_wins_when_a_text_carries_two_reset_clauses`). Mutating the
   dispatch to try the time-only pattern first (dated only when the time-only
   misses — the realistic reordering) makes it red:
   `assert datetime(2026, 9, 6, 15, 10, UTC) == datetime(2026, 9, 12, 11, 0, UTC)`,
   `1 failed, 28 passed`. The test's own comment claiming "trying the dated
   pattern second would also pass every other test in this file today" is
   confirmed by that 28-passed count.

The test's fixture also encodes the real motivating shape (a `/usage` listing
with a session line above a weekly line), so the pin is on the case that would
actually occur rather than a synthetic one.

## New breakage introduced by the fix diff

**None found (no Critical, no Important).**

- `limits.py`: comment/docstring only, proven by the AST comparison above — zero
  behavioral surface.
- `test_limits.py`: two additive tests, no edits to existing ones.
- `docs/superpowers/plans/2026-09-05-usage-pacing-phase2.md`: a new "Rulings
  applied during execution" section (R1–R4). Documentation for later tasks;
  no effect on Task 1's code. Its content is out of this re-review's scope
  and was not audited against source.
- Full suite in the worktree: `./.venv/bin/python -m pytest -q` →
  **1749 passed, 7 deselected** in 6.02s. `git status --porcelain` in the
  worktree is empty; nothing was left changed behind me.

## Deferred minors (not loop material)

- `test_limits.py:233-235` — three blank lines between the two new tests instead
  of two (PEP8 E303). Cosmetic; the repo configures no linter (no ruff/flake8
  config in any `pyproject.toml` or at the root), so nothing flags it.
- The `Feb 29` and `Sep 31` assertions in the I1 test both exercise the same
  `except ValueError` arm, so one is redundant as a pin. Harmless — they
  document two distinct real-world shapes (leap-year and out-of-range day).

## Verdict

**Both findings addressed; no new breakage. Task 1 is clear from this
reviewer's side.** No commits were made and nothing under the worktree was
modified.
