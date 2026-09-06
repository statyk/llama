# Task 4 — scoped re-review of fix round 1 (`c79d81d..5739217`)

Read-only. **No commits made, no suite run** (per instruction: the caller runs
the suite; I never invoked `pytest` or the real `claude` binary). Worktree
verified clean at `5739217` (`git status --porcelain` empty).

## Verdict on the open finding

**I1 — ADDRESSED** (`packages/llama/src/llama/pacing.py:1-14`).

Every claim in the new docstring checks out against the code as it now stands:

| Claim | Verified against | True? |
| --- | --- | --- |
| "Two halves, both of them here" | reactive: `resume_at` (:133), `sleep_until` (:69), `PaceOptions.wait/max_wait_s` (:102-105); proactive: `decide` (:185) | yes (see deferred d1) |
| reactive "learns the reset time from the backend's own refusal (herder.limits)" | `resume_at` reads `err.resets_at`; `herder/limits.parse_reset` is its only legitimate producer, per :138-143 | yes |
| proactive "is `decide()`: a pure policy" | no clock, no IO — `now` is a parameter (:185); module imports are math/re/time/dataclasses/datetime only | yes |
| "one ceiling per window" | `PaceOptions.five_hour_ceiling` / `seven_day_ceiling` (:107-108), one `_pause` call each (:212-215) | yes |
| "The reading comes from herder.usage, which takes a live `/usage` call" | `herder/usage.py:90-104` — `claude -p "/usage"`, isolated, live | yes |
| "deliberately NOT ~/.claude.json's cached utilization — write-throttled and measured serving an already-expired window" | `herder/usage.py:13-18`, near-verbatim, no embellishment | yes |
| backstop sentence | consistent with `decide`'s own :198-200 and with the reactive path in `cli.py` | yes |

No new false statement introduced. Critically, the sentence that made the old
docstring actively harmful — "reading Claude Code's usage cache" — is now
inverted into the explicit rejection, with the same two measured reasons
`herder/usage.py` gives. `pacing.py` still imports nothing from `herder`; the
two module references are prose only, so the cross-package claim costs no
coupling.

`PacingConfig`'s docstring (`config.py:98-107`) is also now true: the model
carries the five reactive knobs and the two ceilings (`config.py:118-119`), and
the untouched "durations are strings, validated at load time" paragraph remains
correct — the ceilings are floats and deliberately outside the
`field_validator` (`config.py:124-129`).

## Judging the rewrite-vs-suggested-text call

**The implementer was right to write its own text, but its stated reason is
half a rationalization.** The reviewer's suggested paragraph did not "drop" the
backstop sentence — no such sentence existed in the old module docstring; it
lives in `decide()`'s (:198-200), untouched. So this is new material, not
recovered material.

What the suggested text *did* leave standing is the real defect: it replaced
only "the second paragraph", leaving the summary line **"Waiting out a usage
window."** — a title that names the reactive half alone and would have kept the
file's first line misdescribing the module. The implementer's rewrite fixes
that, and the substance the reviewer asked for is all present. Right outcome,
imprecise justification; nothing to redo.

## The two hardenings

- **`_pause` annotation — landed** (`pacing.py:172`), `-> PauseUntil | None`,
  the exact contract `decide()`'s `or` chain rests on. `PauseUntil` is defined
  above it (:156), so the annotation resolves at runtime without
  `from __future__ import annotations`. Parameter annotations were left off,
  which the reviewer only listed as "ideally" — fine, and it keeps `Meter` out
  of the signature without importing `herder`.
- **Precondition sentence — landed** (`pacing.py:202-207`), and it names the
  right guarantor: task 5's brief creates `llama/pacing_state.py` with
  `observe(before, after, state)` whose `if delta < 0: return state` refuses a
  negative, pinned by `test_a_negative_delta_contributes_nothing`. The name,
  the module and the behaviour all match. The forward reference is to a
  not-yet-written module, which is normal in this sequence.
- **On ruling R9: I agree with it as a ruling.** A clamp in `decide()` would
  make `Progress(-3.0)` behave identically to `Progress(0.0)`, which is exactly
  the state in which a Task 5 sign regression stops being observable from the
  policy — while Task 5's own test still catches it, so the clamp buys nothing
  and costs the signal. Documenting keeps the cross-task dependency legible.
  One precision note for the *Task 5* reviewer, not for this diff: see d3.

## New breakage from the fix diff

**None — Critical or Important.** The diff is source-only, two files, +26/-9,
and every changed line but one is inside a docstring:

```
+def _pause(meter, ceiling, scope, projected, now, opts) -> PauseUntil | None:
```

is the *only* non-docstring line in the range (verified by filtering `-U0` for
lines carrying `def`/`return`/`import`/`=`). No test file is touched, no
behaviour is reachable from an annotation, so the reported suite figure
(1782 passed, 7 deselected, unchanged) is what this diff should produce.

## Scope discipline — clean

Every deferred Minor is still deferred, confirmed in the file rather than from
the report: `projected = progress.per_show_delta or 0.0` is unclamped (:211,
m2); `if projected` still suppresses the estimate at `0.0` (:181, m5-adjacent);
`reading` is still untyped (:185, m2/m6); no frozen-ness test exists (m3); the
`Progress()` default is still unexercised (:169, m4); the window label is still
`'weekly' if scope == 'seven_day' else '5h'` (:179, m5); the `float`-annotated
`90` int literals are untouched (`config.py:118-119`). Nothing was fixed
opportunistically.

## Deferred minors (out of scope, no action asked)

- **d1 — "Two halves, both of them here" is a mild overstatement, symmetrically
  so.** The reactive half's *execution* (catching `RateLimited`, choosing sleep
  vs checkpoint) is in `cli.py`; `pacing.py` holds its policy and its
  primitives. The same is true of `decide()`, whose caller is a later task. The
  sentence reads as "both policies live here", which is right. Not worth a word
  change.
- **d2 — the module-level backstop sentence (:11-13) near-duplicates
  `decide()`'s (:198-200).** Acceptable as a summary; the only cost is that a
  future edit to one can leave the other disagreeing.
- **d3 — for the Task 5 review, not this one:** `observe` is the sole
  *computer* of `per_show_delta`, but `read_state` deserializes it straight out
  of `pacing-state.json` with no sign or type check (`data.get("per_show_delta")`),
  so a corrupted or hand-edited state file could hand `decide()` a negative that
  `observe` never produced. "Sole producer and the guarantor" is true of the
  computed path only. This does not change ruling R9 — it points at where the
  guarantee should be enforced when Task 5 lands.

## Closing verdict

**Approved.** I1 is addressed with a docstring that is true line by line
against both `pacing.py` and `herder/usage.py`, both requested hardenings
landed and the precondition names the correct guarantor, the diff is
docstrings-plus-one-annotation with no test file touched, and nothing from the
deferred Minor list was slipped in. No new findings at Critical or Important.
