# Task 6 — SPEC-COMPLIANCE review

## Verdict: **Spec ✅**

The diff implements the brief exactly, touches only the two named files, and contains
nothing from Task 7 onward (independently grepped the range for `_meter`, `decide(`,
`shows_that_fit`, `--batch`, `--force`, `trust_age`, `openrouter`, `PauseUntil`,
`read_usage`, `pacing_state`: **no hits**). No findings above Minor in the code.

---

## THE RULING: is uncovered `interpret` a spec gap Task 6 failed to close?

**No. It is correctly outside this task's scope, and outside the spec's Goal as
written.** Three independent lines of evidence:

**1. The spec's own Integration section is the operative instruction, and it names
the three functions, not the stage word.** Line 268-270: *"A reactive catch around
the three run-level stages. New. `except RateLimited` wrapping `run_discover` /
`run_search` / `run_winnow`, converting to the same `PauseUntil` a boundary check
produces. This closes phase 1's stated exit-1 gap."* That is precisely what landed.
The Goals line — *"anywhere on the `_execute` path"* — is satisfied: after this diff
there is no `RateLimited` escape left on that path. `run_interpret` is called at
`cli.py:431`, inside `_get_query`, **before** `_execute` is entered at `cli.py:445`.

**2. The conflation is real, it is inherited, and phase 1's spec writes it out
literally.** `/Users/shawn/projects/llama-wt-pacing2/docs/superpowers/specs/2026-09-04-usage-pacing-design.md:346-348`:
*"a `RateLimited` raised during `interpret` (`run_discover`), `search` (`run_search`)
or `winnow` (`run_winnow`)"* — the parenthetical maps `interpret` → `run_discover`
explicitly. Phase 2's Problem bullet (lines 22-25) is that sentence carried forward,
and it immediately re-states the three as `run_discover`/`run_search`/`run_winnow`.
CLAUDE.md's phase-1 boundary paragraph carries the same mapping. **So yes: phase 1's
spec is the origin of the confusion, and it is a naming collision, not a missed
requirement.** The collision is genuine — `_PIPELINE_RUN_STAGES = ["interpret",
"search", "winnow"]` (`cli.py:1177`) is the user-facing triple, and `run_discover`
is *not* in it, so "interpret/search/winnow" and
"`run_discover`/`run_search`/`run_winnow`" are two different triples that the specs
have been treating as one.

**3. Wrapping `run_interpret` would produce an UNRESUMABLE checkpoint — it needs
design, not a catch.** `run_interpret` (`stages/interpret.py`) writes `ws.criteria`
only on success. `run_resume` (`cli.py:698-701`) hard-refuses with exit 1 when
`ws.criteria` does not exist, and the query string lives only in argv — nothing
persists it. A `_checkpoint_pause` there would write a `paused` session that
`llama run resume` cannot resume: strictly worse than today's exit 1, because it
also parks a zombie on `run list`'s attention list. Making it work needs a new
persisted artifact (or a resume path that re-interprets), which is new design.

**Disposition I recommend: accept-and-document, plus a wording fix.** Cost of the
residual gap is one `interpret` call, at the first LLM call of the run, with zero
prior spend and nothing written to disk — the operator re-runs the identical
`llama get` command after the reset and loses nothing. It is also `llama get
"<query>"`-only: `_get_profile` never calls `run_interpret`, and `llama artists`
uses a throwaway scratch workspace. Not worth widening Task 6.

Concretely:
- **Amend the commit subject** (branch is unmerged, so this is free): `fix(cli): a
  limit during interpret/search/winnow now checkpoints` overstates what landed.
  Suggest `fix(cli): a limit during discovery/search/winnow now checkpoints`, or
  `...during the run-level stages...`.
- **One line in the phase-2 spec** (and, at merge, in CLAUDE.md's phase-1 boundary
  paragraph) recording that `interpret` in that prose means `run_discover`, and that
  `run_interpret` stays uncovered — cheap to lose, unresumable if checkpointed.

---

## Requirement checklist

| Brief requirement | Status |
| --- | --- |
| `_drive` gains `winnow=`/`search=`, and nothing else changes in it | ✅ diff shows exactly the signature + two `setattr` lines |
| `import json` at module scope | ✅ |
| `test_ratelimited_during_winnow_checkpoints_instead_of_exiting` verbatim | ✅ |
| `test_run_level_ratelimited_is_caught_before_herdererror` verbatim | ✅ |
| `_checkpoint_pause` placed immediately above `_execute` | ✅ `cli.py:173` |
| Signature matches brief (`outcome`, `failures`, `note`, `when`) | ✅ |
| Body matches brief byte-for-byte in ordering/rendering | ✅ `cli.py:191-196` |
| Docstring describes what the helper ACTUALLY shares (R2 override) | ✅ see below |
| `when = when or resume_at(...)` — no double skew for `RateLimited` callers | ✅ `cli.py:191`, pinned by two tests |
| One `try` from `artists = None` through the `run_winnow(...)` call | ✅ `cli.py:209-247` |
| `except RateLimited` before any `except HerderError` | ✅ `cli.py:250` — it is the **only** arm on that block; no `HerderError` arm exists to sit behind |
| `if not pace.enabled: raise` | ✅ `cli.py:258-259` |
| The "recoverable, not cheap" whole-stage comment at the catch | ✅ `cli.py:253-257` |
| `return` after the checkpoint | ✅ `cli.py:264` |
| `if not shortlist:` left OUTSIDE the try | ✅ |
| Commit of exactly the two files | ✅ `git diff --name-only` = the two files |
| Nothing from Task 7+ | ✅ grepped, no hits |
| `openrouter.py` untouched; no `--batch`/`--force`/`trust_age` | ✅ |
| Tests offline/deterministic | ✅ no `datetime.now`, `time.sleep`, `subprocess`, `Path.home`, `os.environ` in the added lines |

### R2 (the ruling that overrides the brief) — **followed**

`cli.py:178-183` reads *"What shares this is the run-level pause sites... The loop
deliberately keeps its own rendering: it also prints how many shows are left, and
carries the no-progress guard and the sleep branch."* It does **not** claim the
per-show loop as a caller. `git diff` shows **zero deletions** anywhere in the loop
region (`cli.py:305+`, `cli.py:360-403`) — the only deletions in the file are the
re-indented discovery-through-winnow block. `test_a_checkpoint_reports_how_many_shows_are_left`
and siblings are untouched.

---

## Beyond the brief (all judged justified, none a scope violation)

- **Six extra tests** past the brief's two. All are behavioural pins on this task's
  code (region boundaries, `--no-pacing` re-raise, `when=` verbatim, the note/hint
  rendering, and a negative: a plain `HerderError` still propagates and writes no
  marker). The negative one is load-bearing — it is what actually pins `except
  RateLimited` against widening to `except HerderError`, which the arm-ordering
  constraint alone does not cover since there is no second arm.
- **`HerderError` added to the existing `from herder import ...` line** — needed by
  that negative test. One token.
- `test_ratelimited_during_discover_checkpoints_too` bypasses `_drive` and drives
  `_execute` directly. Correct call: `_drive` hard-codes `Criteria(query="x")`, which
  has no `soft_preferences` and so can never reach `run_discover`, and widening
  `_drive` further was forbidden.

## Findings

- **Minor** — `packages/llama/tests/test_pace_loop.py:429` (pre-existing
  `test_a_limit_with_no_named_reset_waits_the_configured_default`) still has a local
  `import json` now that the module imports it. Dead but harmless; code-quality's call.
- **Minor / cross-task, not a Task 6 defect** — the run-level pause **never sleeps**,
  even when `pace.wait` is on and the reset fits under `--max-wait`; it always
  checkpoints. That is exactly what the brief prescribes and matches the spec's R20
  resolution ("the pre-flight gate therefore checkpoints and exits 0"), but it sits in
  mild tension with the Integration section's generic "Rendering a pause is unchanged
  from phase 1 — sleep if it fits under `max_wait`, else checkpoint". **Carry this to
  Task 7's review**, where the pre-flight gate makes the same choice with `PauseUntil`
  and where `--wait` semantics deserve a deliberate ruling.
- **Important (documentation only, code is correct)** — the commit subject overstates
  coverage; see the ruling's disposition above.
- Implementer's concern #4 (`outcome`/`failures`/`when` are unexercised by production
  code until Task 7) is **accurate and acceptable**: the brief specifies that exact
  signature, and `when=` now has a direct unit test.
- Implementer's `m15` survivor is genuinely equivalent (`sessions._write` already does
  `failures or []`). No action.

## Cannot verify from the diff

- **I did not run any tests.** Per isolation rules the suite is yours; the reported
  1814 passed / 7 deselected is the implementer's number, not mine.
- **I did not reproduce the 17-mutant sweep.** I verified its *claims* against the
  source (arm is the sole arm; region boundaries; per-show loop untouched; forbidden
  tokens absent) but not its execution.
- Whether the note text reads well to the operator in a real terminal (rendering
  judgement, not spec).
