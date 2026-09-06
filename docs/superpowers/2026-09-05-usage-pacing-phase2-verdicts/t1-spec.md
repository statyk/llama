# Spec-compliance review — Task 1 (dated reset parsing, per-call max-ahead bound)

**Verdict: Spec ✅**

Range reviewed: `ac7c428..9ee737b` (2 commits, 2 files, +131/−23). Worktree
`/Users/shawn/projects/llama-wt-pacing2`, branch `usage-pacing-phase2`, clean.
Note: worktree HEAD is `94f8c6c` (`docs(plan)`), one commit past the review
range; it touches only the plan document and is out of scope here.

The implementation is **verbatim** to the brief's Step 3 code. I diffed the
brief's two mandated blocks against `packages/herder/src/herder/limits.py:52-160`
character by character: `_MONTHS`, `_RESET_DATED_RE`, `_hour24`, `_dated_target`,
and the rewritten `parse_reset` body match with no renames, no regex edits, no
constant changes. The five test bodies at
`packages/herder/tests/test_limits.py:180-219` match the brief's verbatim too.

## Requirement checklist

- [x] `parse_reset(text, now=None, max_ahead_s=MAX_RESET_AHEAD_S) -> datetime | None`
      — `limits.py:116-117`. Signature exact.
- [x] Accepts the **time-only refusal** form — `limits.py:139-155` (the `else`
      branch, structurally the old body with `_hour24` factored out).
- [x] Accepts the **dated `/usage`** form — `_RESET_DATED_RE` at `limits.py:60-63`,
      tried first at `limits.py:134`.
- [x] Dated **minutes optional** (`7am`) — `(?::(\d{2}))?` at `limits.py:62`,
      defaulted at `limits.py:86`; pinned by
      `test_parse_reset_accepts_a_dated_form_with_no_minutes` (test_limits.py:187).
- [x] `MAX_RESET_AHEAD_S` **keeps its value and meaning** — `limits.py:26` is
      untouched (`5.5 * 3600`), now referenced as the default at `limits.py:117`.
      It was not removed, renamed, or widened.
- [x] Bound is **per-call**, applied at `limits.py:157-159` against the parameter
      rather than the constant; pinned by
      `test_parse_reset_bound_is_per_call_not_global` (test_limits.py:194), which
      asserts the same weekly text is rejected under the default and accepted
      under `7.5 * 86400`.
- [x] A **past dated date resolves to next year and then fails every bound** —
      `_dated_target`'s `for year in (local.year, local.year + 1)` loop
      (`limits.py:89-96`); pinned by
      `test_parse_reset_dated_rolls_to_next_year_then_fails_the_bound`
      (test_limits.py:202), which asserts both halves (Jan 2 → 2027 and returns;
      Dec 1 → 2027 and degrades to `None`). No path can produce a year-long sleep.
- [x] **Time-only path unchanged in behavior.** The only edits to it are
      mechanical: `hour` inlined as `_hour24(...)` (same expression), and
      `now = now or datetime.now(...)` moved above the zone/minute validation
      (unobservable — `now` is unused by those guards). The 22 pre-existing tests
      in `test_limits.py`, including both `MAX_RESET_AHEAD_S` edge tests at
      test_limits.py:109 and :115, still pass per the implementer's report, and
      `test_parse_reset_still_handles_the_refusal_form_unchanged`
      (test_limits.py:213) adds a direct pin.
- [x] **`herder` does not import `llama`** — no import lines were added at all;
      `grep` over `packages/herder/src` finds no `llama` import.
- [x] **`openrouter.py` untouched** — confirmed by the two-file stat.
- [x] **No constant swept or retuned** — the only numeric literals introduced are
      the month table and `0..59`/`%12`/`12` arithmetic. `7.5 * 86400` appears
      only inside test call sites, never as a module constant (the per-meter
      constants belong to Task 2's `usage.py`, per the spec's implementation order).
- [x] **Tests offline and deterministic** — every one of the five passes an
      explicit `now=`; no wall clock, no `$HOME`, no subprocess, no sleep. Zone
      resolution uses `zoneinfo` against the system tzdb, identical to the
      pre-existing tests.
- [x] `from herder import limits` added to the test imports (brief-required);
      `from datetime import datetime, timedelta, timezone` was already present.
- [x] `parse_reset` still always returns a **UTC-aware** instant
      (`limits.py:157`), which `llama/pacing.py:127-129`'s `resume_at` docstring
      relies on. The one downstream invariant outside herder is intact.

I independently recomputed all four dated assertions (EDT/EST offsets, the
year-roll arithmetic, and both bound comparisons) and they are correct as written.

## Scope creep

**None.** Nothing was implemented beyond the brief. The single addition not
literally in the Step 3 code block — the `from herder import limits` test import —
is explicitly required by the brief's Step 1. `classify()` is unchanged.

## Findings

- **Minor** — `packages/herder/src/herder/limits.py:134-137`: the dated branch has
  no fall-through. If `_RESET_DATED_RE` matches but `_dated_target` returns `None`
  (unknown month, bad zone, impossible date), `parse_reset` returns `None` without
  ever trying `_RESET_RE`. More pointedly, if a failure text ever carried *both* a
  dated clause and the measured time-only clause, the dated one wins and — failing
  the default 5.5 h bound — the session reset is silently lost, so `classify()`
  yields `resets_at=None` and the pause falls back to `unknown_reset_wait`. This is
  the brief's mandated structure and no observed text has both, so it is not a
  defect against the task. A one-line `if target is None: fall through to _RESET_RE`
  would close it without changing any current behavior. Flagging for your call, not
  asking the implementer to deviate.
- **Minor** — `packages/herder/src/herder/limits.py:169`: `classify()` still calls
  `parse_reset` with the default 5.5 h bound for *every* scope, including
  `seven_day`. That is pre-existing and spec-sanctioned ("the existing refusal path
  keeps the value it has today", spec:168-169) — recording it only so it is not
  later mistaken for something Task 1 should have done. The measured weekly refusal
  wording is still unobserved, so there is nothing to bind a wider bound to yet.
- **Minor** — `packages/herder/src/herder/limits.py:43-47`: the comment above
  `_RESET_RE` still says `"resets 11am" with no minutes ... correctly fail to match
  and yield None rather than guessing`. That remains true *of that regex*, but is
  now false of the module's parser, which accepts minute-less times in the dated
  form. A reader scanning for "does this parser take `7am`?" gets the wrong answer.
  One clause ("of this time-only form") would fix it.
- **Minor** — `packages/herder/tests/test_limits.py:213`: the
  "refusal form unchanged" pin does not exercise `max_ahead_s` on the refusal path
  at all, so the claim that the *bound* behaves as before on that path rests on the
  two pre-existing edge tests (test_limits.py:109, :115) rather than on the new
  test. Coverage is adequate in aggregate; the new test's name promises slightly
  more than it checks.

No Critical or Important findings.

## Not verifiable from the diff (yours to resolve, not mine)

1. **Suite green.** I was instructed not to run tests, so `1747 passed, 7
   deselected` and the pre-implementation red state are taken from the
   implementer's report, unverified by me. The report names its exact commands and
   is internally consistent (1742 baseline + 5 new = 1747).
2. **Venv discipline.** The report's `./.venv/bin/python -c "import llama"`
   resolution check leaves no artifact in the diff; I cannot confirm it from the
   commit range.
3. **DST-gap and ambiguous-hour behavior.** `datetime(y, m, d, h, mi, tzinfo=tz)`
   in a spring-forward gap does not raise, so a reset named inside a nonexistent
   local hour resolves to something arbitrary. Neither the old nor the new path has
   ever been tested there, and the brief did not ask for it. Not a regression;
   noting because the dated form widens the range of dates this arithmetic sees
   (a whole year rather than two adjacent days).
