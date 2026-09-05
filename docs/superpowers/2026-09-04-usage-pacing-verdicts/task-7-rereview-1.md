# Task 7 — scoped re-review, round 1

Diff reviewed: `review-980e02b..8c98dc8.diff` (commits `3578fcb` fix, `8c98dc8` docs).
Report reviewed: `task-7-report.md` (fix round 1 section, lines 189-341).
Tree: `usage-pacing` branch, clean before, during (each mutation reverted), and after this review.

## Verdicts, one line per item

1. **`mark_paused(…, failures, …)` unpinned** — ADDRESSED. Both call sites,
   `packages/llama/src/llama/cli.py:349` (`except KeyboardInterrupt`) and `cli.py:358`
   (ordinary checkpoint), already pass `failures` in production code (unchanged by this
   diff — the defect was a missing test, not missing code). New test
   `test_a_checkpoint_carries_the_failures_the_run_had_already_taken`
   (`packages/llama/tests/test_pace_loop.py:243`) covers the non-interrupt path; the
   rewritten `test_an_interrupt_during_the_wait_checkpoints_rather_than_losing_the_run`
   (`test_pace_loop.py:187`) covers the Ctrl-C path. Independently re-verified: mutating
   `cli.py:358` alone to `[]` fails
   `test_a_checkpoint_carries_the_failures_the_run_had_already_taken`; mutating `cli.py:349`
   alone to `[]` fails `test_an_interrupt_during_the_wait_checkpoints_rather_than_losing_the_run`.
   Both call sites confirmed dead under mutation, independently of each other.

2. **No-progress guard's three terms** — ADDRESSED. `done_now = packaged + held +
   len(failures)` at `cli.py:336` (unchanged code). New tests
   `test_a_held_show_between_pauses_counts_as_progress` and
   `test_a_failed_show_between_pauses_counts_as_progress`
   (`test_pace_loop.py:267`, `:292`). Independently re-verified: dropping `held` from the
   sum fails the held-progress test; dropping `len(failures)` fails the failed-progress
   test. `packaged` was already pinned pre-round-1 (not re-mutated here, per instructions
   treating it as already confirmed).

3. **Spec amendment R20** — ADDRESSED. `docs/superpowers/specs/2026-09-04-usage-pacing-design.md`,
   "Rendering a pause" section: the third table row is struck through and marked
   "deferred to phase 2". All three required parts are present, each under its own
   labelled paragraph: (a) the real argument for a non-zero exit (cron run indistinguishable
   from a no-op), (b) why it loses in phase 1 (the spec's own Ctrl-C exit-0 rule, and the
   near-identity of a first-show vs. seventh-show limit), (c) an explicit instruction that
   phase 2 revisit it deliberately, plus the constraint that Ctrl-C and first-show paths
   must land on the same answer whatever phase 2 picks.

4. **Spec amendment R21** — ADDRESSED. Same section: the sentence now reads "`max_wait`
   (default 6 h) and the **no-progress guard** are the two mechanisms governing whether a
   pause is waited out; nothing else overrides `--wait`", followed by an amendment
   paragraph naming why the guard exists (a backend that keeps refusing inside the cap
   would otherwise nap indefinitely) and an explicit "**Do not delete it on the strength of
   an unamended reading of the sentence above.**"

5. **`parse_duration` whitespace tolerance + round-trip property test** — ADDRESSED, with
   one non-blocking observation (see below).
   - (a) `packages/llama/src/llama/pacing.py:33`:
     `m = _DURATION_RE.match(re.sub(r"\s+", "", text or ""))`. The `$` anchor at
     `pacing.py:15` is untouched (confirmed by reading — the regex literal is identical to
     the pre-round-1 version). Re-verified every required rejection still raises:
     `""`, `"6"`, `"-2h"`, `"6x"`, `"6h banana"`, `"5h30m!"`, `"6s30m"`, a whitespace-only
     string — all pass in the current `test_parse_duration_rejects_nonsense`
     (`packages/llama/tests/test_pacing.py:15`). Independently re-verified two mutations:
     reverting the tolerance to `.strip()` fails 3 tests (kills it); weakening the anchor
     (dropping the trailing `$` from `_DURATION_RE`) fails `test_parse_duration_rejects_nonsense`
     (kills it, proving the anchor-pinning tests still bind even though the diff didn't
     touch the anchor).
   - (b) `test_format_delta_output_always_parses_back` (`test_pacing.py:376`) is the
     round-trip property test, asserting
     `parse_duration(format_delta(x)) == 60 * (max(int(x), 60) // 60)` over 18 values
     including `0, 1, 59` (floor case) and non-round minutes (`61, 3601, 3660, 7250,
     5.5*3600`). This is exactly the `format_delta` property item 5b required, not a
     substitute measured against `duration_arg`.

## The three scrutiny points

1. **Second call site.** Confirmed genuinely fixed, not partially. Both `mark_paused`
   call sites (`cli.py:349`, `:358`) are independently pinned — I mutated each alone (not
   just together) and each failed a distinct test. The report's claim that "the same
   defect existed on the other [Ctrl-C] path and F1b survived" checks out: before this
   round only the non-interrupt test existed and the interrupt test's fixture had no
   failure to lose, so a `[]` mutation on the Ctrl-C call site was invisible. The rewritten
   interrupt-test fixture (`a` raises `TaskFailed`, `b` hits the limit) now closes that.
2. **Whitespace-before-match, anchor untouched.** Confirmed from the diff and by mutation
   that the `$` anchor is byte-identical and still enforced. One thing worth flagging: the
   blanket `re.sub(r"\s+", "", ...)` removes whitespace *anywhere* in the string, not just
   between duration components — so `"6 h"` and `"  6 h 5 m  "` now parse (confirmed:
   `parse_duration("6 h") == 21600`, `parse_duration("6 h 5 m") == 21900`), which is wider
   than "tolerate the shape `format_delta` emits" strictly requires. This does not produce
   any wrong value and every required-to-reject string in the spec's list still raises
   (`"6h 5h"` still raises — the leftover `"5h"` after consuming `"6h"` still fails the `$`
   anchor). It is unpinned by any test either way. I judge this non-blocking — it's a
   permissiveness widening, not a correctness bug — but it is new behavior introduced by
   this diff and untested, so I record it as a Minor rather than silently passing over it.
3. **Round-trip test placement.** Confirmed: `test_format_delta_output_always_parses_back`
   (new, `test_pacing.py:376`) round-trips `format_delta`, distinct from the pre-existing
   `test_duration_arg_round_trips_through_parse_duration` (`test_pacing.py:156`, unchanged
   by this diff, round-trips `duration_arg`). Item 5b is satisfied by the former, not a
   relabeling of the latter.

## New breakage in the fix diff

None found at Critical or Important severity. The fix diff touches only
`pacing.py`, `test_pace_loop.py`, `test_pacing.py`, and the spec doc — `cli.py` has zero
changes in this diff (items 1 and 2 were pure test-coverage gaps against already-correct
production code, confirmed via `git show --stat 3578fcb`). One Minor, non-blocking
observation carried over from scrutiny point 2 above (whitespace-anywhere acceptance of
`"6 h"`-shaped input, unpinned either way).

## Scope check

- Only `packages/llama/src/llama/pacing.py`, `packages/llama/tests/test_pace_loop.py`,
  `packages/llama/tests/test_pacing.py`, and
  `docs/superpowers/specs/2026-09-04-usage-pacing-design.md` changed (confirmed via the
  diff header and `git show --stat` on both commits). `cli.py` untouched in this round.
- Task 8 (mutation pass + `CLAUDE.md`/`docs/workflow.md` updates) confirmed NOT started:
  `git diff 980e02b..8c98dc8 -- CLAUDE.md docs/workflow.md` is empty.
- Full suite re-run independently: `1741 passed, 7 deselected` (matches the report exactly).
  `packages/llama/tests` subset: `1304 passed, 7 deselected` (matches the report's
  mutation-baseline number).
- `git status --porcelain` empty at the end of this review; every mutation applied during
  verification was reverted with `git checkout --` and confirmed clean before proceeding
  to the next one.

## Deferred (out of scope, does not change verdict)

- The ten previously-deferred Minors (untouched, as instructed): `<=` boundary at
  `cli.py:334`, `reset_skew`/`unknown_reset_wait` only exercised at defaults, the
  hint-suffix condition, `--no-pacing`'s FAILED line, `duration_arg`'s floor, `""` as
  "flag not given", `pace=None`'s default, local-vs-UTC instant rendering, `resume_at`'s
  scope-blind fallback, the vacuous `assert held == {"b"}` lines.
- The implementer's own suggestion (a shared `_checkpoint(...)` closure to unify the two
  `mark_paused` call sites) — explicitly out of scope for this round per instructions.
- The `RateLimited`-from-`interpret`/`search`/`winnow` gap noted in both report sections —
  pre-existing, not part of this fix diff, not one of the five open items.
- Whitespace-anywhere acceptance (`"6 h"`, `"  6 h 5 m  "`) — see scrutiny point 2 above;
  recorded there as a Minor rather than repeated here.

## Overall verdict

**PASS.** All five open items ADDRESSED, all three scrutiny points check out against the
actual diff and independent mutation, reported suite counts (1741 passed / 7 deselected)
reproduced exactly, task 8 confirmed not started, and no new Critical/Important breakage
found in the fix diff. Tree is clean.
