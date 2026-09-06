# Task 4 — SPEC-COMPLIANCE review

## Verdict: **Spec ✅**

Every mandated interface is present, at the mandated semantics, with nothing
from Task 5+ leaked in. The one deviation from the brief (`cli.py::_pace`) is
the deviation ruling **R1** required. Four tests beyond the brief are legitimate
mutation-driven pinning, all inside this task's own surface.

Verified independently, not taken from the implementer's report: a private copy
at `$D/work/t4-spec/tree` (rsync of `packages/`, no `.git`/`.venv`), imported via
`PYTHONPATH` shadowing with a `__MUT_SENTINEL__` + `herder.usage.__file__`
assertion inside every run, run as
`/Users/shawn/projects/llama-wt-pacing2/.venv/bin/python -B -m pytest -q -p no:cacheprovider`
(never `./.venv/bin/pytest`). Baseline over
`test_pacing_decide test_pacing test_config test_pace_loop` + sentinel: **78
passed**. The worktree was never edited and no test was run there.

## Requirement checklist

| Requirement | Status | Where |
| --- | --- | --- |
| `pacing.Proceed()` | ✅ | `pacing.py:145-147` |
| `pacing.PauseUntil(when, scope, reason)` | ✅ | `pacing.py:150-154` |
| `pacing.Progress(per_show_delta)` | ✅ | `pacing.py:157-163` |
| `decide(now, reading, progress, opts) -> Proceed \| PauseUntil` | ✅ | `pacing.py:179-203` |
| `decide()` pure — no clock, no IO | ✅ | only reads `now`, `reading`, `opts`; `_pause` likewise (`pacing.py:166-177`). No `_now()`, no `datetime.now`, no imports added to `pacing.py` |
| Weekly ceiling checked BEFORE the session gate | ✅ | `pacing.py:199-202`; docstring states the reason. **Mutation-verified by me**: swapping the two `_pause` calls fails 2 tests |
| Session gate on the projection, not the bare percent | ✅ | `pacing.py:171` (`meter.percent + projected`); pinned by `test_session_gate_fires_on_the_projection_not_the_bare_percent` |
| Missing reading proceeds | ✅ | `pacing.py:196` |
| Disabled pacing never gates | ✅ | `pacing.py:196` + `pace_options` folding `no_pacing` into `enabled` (`pacing.py:117`) |
| `PaceOptions` gains both ceilings, stays frozen | ✅ | `pacing.py:101-102`; `@dataclass(frozen=True)` unchanged at `:87` |
| `pace_options` gains `no_pacing`, passes both ceilings | ✅ | `pacing.py:105-123` |
| `PacingConfig` gains two float ceilings, **not** in the duration `field_validator` | ✅ | `config.py:117-118`; validator at `:120` still lists only the three duration keys |
| `DEFAULT_CONFIG_TOML` gains the matching block | ✅ | `config.py:266-271` |
| `test_default_config_template_matches_defaults` still green | ✅ | passes; parsed == default |
| Ruling **R1** followed (keep `typer.echo` + `raise typer.Exit(1)`; change only the construction; drop `dataclasses.replace`) | ✅ | `cli.py:161-170`; `from dataclasses import replace` removed. No bare `replace` Name remains — the four textual hits are `datetime.replace`, `str.replace`, and the English word in help/echo text (`cli.py:536, 840, 1770, 2472`) |
| Nothing from Task 5+ | ✅ | no `pacing_state`, no `_execute` gate wiring, no `shows_that_fit`, no forecast line, no `llama pacing` command. `decide`/`Progress` have zero non-test callers |
| `openrouter.py` untouched; no `--batch`/`--force`/`trust_age`; no `herder`→`llama` import | ✅ | diff touches 5 files only; `pacing.py` imports nothing from `herder` (the reading is duck-typed) |
| The two ceilings not swept/retuned | ✅ | both 90, as specified |

## Independent mutation checks (3, all caught)

Run in the private copy, reverted after each, baseline re-asserted green at the
end. I required the pytest summary to contain `passed`/`failed`, per the warning.

1. **Delete `five_hour_ceiling` from `DEFAULT_CONFIG_TOML`** → 1 failed
   (`test_default_config_template_documents_every_pacing_knob`). The M18 gap the
   implementer found is genuinely closed; without the new test this mutation
   survives.
2. **Swap the rule order** (session before weekly) → 2 failed
   (`test_weekly_ceiling_outranks_the_session_gate`,
   `test_the_pause_reason_names_the_window_and_the_estimate`). The ordering is
   pinned by execution, not just by docstring.
3. **Apply the brief's `typer.BadParameter` version of `_pace`** → 3 failed,
   including `test_pace_loop.py::test_a_malformed_max_wait_fails_before_the_run_starts`.
   This confirms R1 was correct and that following the brief here would have
   broken shipped behaviour.

## Ruling on the two questions put to me

**1. `PauseUntil` truthiness carrying the rule order — flagging was the right
call. No change required.** Three reasons, in order of weight: (a) the property
is pinned by an executing test, which I re-verified myself — an inversion fails
immediately and loudly, so the risk is caught rather than latent; (b) the
inversion requires someone to give a three-field frozen dataclass `__bool__` or
`__len__`, which would be a redesign of the return type, not an incidental edit,
and such a redesign passes through the same test; (c) the brief mandated this
code verbatim, and restructuring into explicit `if`s trades a documented,
idiomatic short-circuit for two extra branches that the test already covers.
Verified: `PauseUntil.__dict__` has neither `__bool__` nor `__len__`. If you want
belt-and-braces at zero cost, the only change I would entertain is a half-line
comment on the `or` chain ("`_pause` returns None or a truthy PauseUntil") —
**Minor, optional, not a finding**.

**2. Scoping the key-set test to `[pacing]` is right, and the test is sound.**
Right, because widening it is a change to sections this task does not own and
the report's measurement is that some sections document a subset of their fields
deliberately — a widened test would fail today and its fix would be scope creep
into other features' config. Sound, because it is written over
`PacingConfig.model_fields` rather than a hardcoded pair, so it is bidirectional:
it catches a knob dropped from the template (verified above, both the new keys
and a pre-existing one) *and* a field added to the model without documentation.
The only judgement it bakes in is "every `PacingConfig` field must be documented
in the seeded file", which is the right rule for this section given the seeded
file is the only place an operator discovers a ceiling exists to lower.

## Extras beyond the brief — all legitimate, none scope creep

`test_pacing_decide.py`: `test_each_window_is_judged_against_its_own_ceiling`,
`test_a_missing_meter_is_skipped_rather_than_crashing`,
`test_the_pause_reason_names_the_window_and_the_estimate`.
`test_config.py:188`: `test_default_config_template_documents_every_pacing_knob`.
Each closes a specific surviving mutation on code this task introduced; none
tests behaviour outside `decide`/`pace_options`/`PacingConfig`; no production
code was added to accommodate them. The ceiling-pairing test is the most
valuable of the four — with both defaults at 90 the call-site pairing is
otherwise unobservable.

## Findings

**Critical: none. Important: none.**

- **Minor — `config.py:117-118`, cosmetic type asymmetry.** The defaults are int
  literals (`= 90`) under a `float` annotation, and pydantic does not validate
  defaults, so `Config().pacing.five_hour_ceiling` is `int` 90 while a
  config-file value is `float` 90.0. Harmless — `90 == 90.0`, so
  `test_default_config_template_matches_defaults` passes and every comparison and
  addition in `_pause` behaves identically — and the literal was mandated by the
  brief. Noting it only so a future reader does not mistake it for a bug.
- **Minor — `pacing.py:176`, `if projected` gates the estimate suffix.** A
  learned delta of exactly `0.0` omits ", est …%/show" from the reason. Correct
  and consistent with `progress.per_show_delta or 0.0` at `:198`, which already
  collapses `0.0` and `None`; recorded as understood, not as a defect.
- **Minor — `pacing.py:166`, `_pause` and `decide`'s `reading` parameter are
  untyped.** Deliberate in the brief (it keeps `llama.pacing` free of any
  `herder` import, so the allowed import direction is not even exercised), but it
  means a wrong-shaped reading fails at attribute access rather than at a
  boundary. Acceptable; the only producer is `herder.usage`.

## Stated non-verifications

- **The full suite.** I did not run it (worktree is yours to run; my copy has no
  installed console entry points). My evidence covers 78 tests across the four
  files that can bite on these three source files. The implementer's claim of
  **1782 passed, 7 deselected** is unverified by me.
- **The implementer's 24-mutation sweep** is unverified as a whole; I
  re-executed 3 of its claims (M18, M2, and the R1 counterfactual) and all 3
  reproduced as reported.
- **Runtime behaviour of the gate.** `decide()` has no production caller yet, by
  design, so nothing in this diff demonstrates the policy in a real run. That is
  Task 5+ and correctly absent here.

## Mandate note

No commits were made — a reviewer makes none, and nothing here needed one.
The private copy at `$D/work/t4-spec/tree` is scratch and can be deleted;
`git status` in the worktree was clean before and after (`c79d81d`).
