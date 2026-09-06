# Code-quality review — Tasks 2 & 3 (pacing-loose-ends), Opus

Reviewed: briefs, `review-35a4694..126bd72.diff`, implementer report, and the
worktree read-only. All mutation work of my own was done in a COPY at
`$SCRATCH/qcopy`, shadowed via `PYTHONPATH` and proved with a planted sentinel
(`llama.__file__` resolved inside the copy, under `python -c` AND under pytest,
and `inspect.getsource(should_run)` showed the mutant live). The worktree was
never modified: `git status --porcelain` empty before and after.

Independent suite run:
`cd /Users/shawn/projects/llama-wt-pacing-loose-ends && ./.venv/bin/python -m pytest -q`
-> **1875 passed, 7 deselected**, matching the Task-3 gate. Preflight
`./.venv/bin/python -c "import llama; print(llama.__file__)"` resolved inside the
worktree. The implementer named its command on every reported result; auditable.

---

## Task 2 quality: **Changes requested**

The design is sound and the mutation evidence is the strongest kind: I
reproduced it exactly. But retiring the old test dropped an assertion direction
the commit message claims was subsumed, and I verified the resulting blind spot.

### T2-1 (Important) — the retirement is not a subsumption; the reverse direction is now uncovered
The retired `test_default_config_template_documents_every_pacing_knob` asserted
`set(block) == set(PacingConfig.model_fields)` — an **equality**, so it caught a
key in the template that the model does **not** have, as well as one it does.
The new test computes only `set(ann.model_fields) - documented`, i.e. one
direction. `Config` sets no `model_config`, so pydantic's default `extra="ignore"`
applies (verified: `Config.model_validate({'pacing': {'bogus': 1}})` returns
cleanly), which means `test_default_config_template_matches_defaults` cannot see
it either.

Measured in the copy — mutant B, adding a phantom knob to the template:
```
[pacing]
...
seven_day_ceiling = 90

# a knob that no longer exists in PacingConfig
reserve = 10
```
`pytest packages/llama/tests/test_config.py -q` -> **22 passed**. An operator who
sets `reserve` in their seeded config gets no effect and no error, and nothing in
the suite notices. The retired test caught exactly this for `[pacing]` — and per
`docs/superpowers/2026-09-05-usage-pacing-phase2-verdicts/t4.md:104` it was
*introduced* as the answer to a mutation gap, so this is a knowingly-won
constraint being given back.

The commit body states "the new test subsumes it as the `[pacing]`-only special
case." That is inaccurate: it generalizes one direction and drops the other.

Fix (cheap, and I checked it passes on today's template at both levels): add the
reverse subset check for non-free-form sections and for `""`, e.g.
`stale = sections.get(name, set()) - set(ann.model_fields)`, and correct the
commit wording. Documented keys today are `{tapers, lineage_eras}` for
`selection`, all 7 for `pacing`, etc., and top-level documented keys are a strict
subset of `Config.model_fields` (only `tiers` is undocumented at top level and it
is already excluded), so the reverse check is green as-is.

Note this finding originates in the brief's prescribed code, not in implementer
improvisation — the implementer transcribed the brief faithfully.

### T2-2 (Minor) — a wholly commented-out block reads as "documented"
`_TEMPLATE_SECTION`/`_TEMPLATE_KEY` both accept a leading `#`, deliberately (the
path knobs and `[setlistfm]` are commented examples). The consequence is that
commenting out the entire live `[pacing]` block would leave both remaining config
tests green — the key test sees the comments, and the behaviour test still parses
to defaults. The extractor cannot distinguish "seeded live" from "shown as an
example". Accepted trade of the design; recording it so nobody assumes otherwise.

### T2-3 (Minor) — the key regex will accept prose that looks like an assignment
`^\s*#?\s*([A-Za-z_][A-Za-z0-9_]*)\s*=` matches any commented line whose first
token is an identifier followed by `=`. No current template line false-positives
(I checked the `lineage_eras = []` prose line — it does not match), but a future
prose comment could "document" a key that is not actually seeded. Over-permissive
by construction; worth a line in the docstring if it ever bites.

### T2-4 (Minor) — depth and annotation shape
Only one nesting level is checked: `LineageEra`'s `collection`/`date_from`/
`date_to`/`scores` are never asserted. And `isinstance(ann, type) and
issubclass(ann, BaseModel)` means a future `SomeConfig | None` field silently
degrades to the weaker top-level `name in sections[""]` check, which a bare
section header satisfies. Fine for today; a latent softening.

### T2-5 (Minor) — small readability nits
`from pydantic import BaseModel` is imported inside the test body although the
module already does `from pydantic import ValidationError` at the top; and
`undocumented["<top-level>"] = undocumented.get("<top-level>", []) + [name]`
would read better as `setdefault(...).append(name)`. Both are the brief's text.

### Mutation check (Task 2) — reproduced, exact match
Prediction was written first and named the test and the message. I re-ran it
independently in the copy: deleting `five_hour_ceiling = 90` from
`DEFAULT_CONFIG_TOML` gives
`AssertionError: keys missing from DEFAULT_CONFIG_TOML: {'pacing': ['five_hour_ceiling']}`
on `test_the_template_documents_every_config_key`, `1 failed, 21 passed`, and
`test_default_config_template_matches_defaults` stayed green. Predicted test,
predicted assertion, predicted message — the strongest grade of result. No
notes.

---

## Task 3 quality: **Changes requested**

The precondition is present and real, the commit is honest about the mutation
landing off-target, and the assertion was not weakened. But the property the test
names is not the property it pins, and I have a measured mutant proving it.

### T3-1 (Important) — a total break of `should_run` leaves this test GREEN
The docstring and commit say the property is `should_run`'s. Mutant, applied in
the copy to `packages/llama/src/llama/workspace.py`:
```python
def should_run(path: Path, force: bool) -> bool:
    return True  # MUTANT
```
`pytest packages/llama/tests/test_sessions.py::test_resuming_a_packaged_run_costs_no_llm_calls -q`
-> **1 passed**. (Mutant confirmed live in-process via
`inspect.getsource(llama.workspace.should_run)` inside pytest.)

Why: with `should_run` broken, `run resume` re-runs `run_winnow` from the top,
where the library dedup drops the one candidate
(`winnow: 1 candidates -> 0 after library+ledger`), the shortlist is empty, and
`_execute` returns early on "No shows survived winnowing." — having spent nothing.
So the equality holds for an entirely different reason, and the show is never
re-entered at all.

On the unmutated tree the resume genuinely does re-enter every stage — I captured
the second run of stage banners (`selecting recording / gathering / researching /
vetting research / briefing / packaging`) with all call counts unchanged, so the
documented behaviour is real. The test just cannot tell that route apart from the
short-circuit route, and the short-circuit is what survives the regression the
test claims to guard.

Fix (one line, verified): assert the resume took the real route, e.g.
`assert "packaged:" in resumed.output, resumed.output` after the exit-code check.
Measured: green unmutated; under the `should_run` mutant the resume output is
"No shows survived winnowing." so it goes red. That converts the test from
"a resume of a finished run is cheap" into "a resume re-enters the show and is
cheap", which is the claim in `CLAUDE.md`.

### T3-2 (Minor) — the mutant performed reddens an earlier assertion, so the final equality has no demonstrated red
Honestly reported by the implementer: swapping the resume for a fresh
`get --name cheap2` fails at `assert resumed.exit_code == 0` because the shared
`FakeProvider` queues (one canned response each, created once by
`fake_providers(None)`) are exhausted by the second full run. That is a real catch
but a weaker result than an exact prediction match, and it generalizes: in this
harness *any* re-spend exhausts the queue and crashes before the count equality is
evaluated, so the equality is close to unfalsifiable in isolation here. The
effective detectors are `assert spent > 0` and the exit-code assertion. Not
grounds for rejection on its own; the T3-1 fix is what adds real force. If a
future task wants the equality itself demonstrated red, deepen the queues so a
re-spend completes instead of crashing.

### T3-3 (Minor) — `CountingProvider.calls` shadows `FakeProvider.calls`, which matters for the Task 6 reuse
`FakeProvider.calls` is a `list[tuple[str, str]]` of (kind, prompt);
`CountingProvider.calls` is an `int`. Wrapping renames the attribute out from
under a reader who expects the prompt log, and Task 6 is instructed to reuse this
class. The prompt log is still reachable as `.inner.calls`, and no non-test code
touches anything but `complete`/`research` (`herder/tasks.py` uses only those via
`_as_ladder`), so nothing is broken — but `count`/`n_calls`, or a `__getattr__`
passthrough to `inner`, would be a better shape for a class designated for reuse.
Otherwise the shape is fit for purpose: it wraps one provider, counts both call
kinds, and composes over a dict comprehension exactly as Task 6 will need.

### Positives worth recording
- The non-empty precondition is present and load-bearing: I measured the first
  run spending 6 calls across 6 of the 8 providers, so `assert spent > 0` is a
  real gate on a real number, not decoration.
- The equality was not weakened to `>=` and was not scoped to a subset of
  providers; it sums over every provider.
- The Task-3 restoration incident (a `git checkout` that discarded the
  uncommitted test, re-applied and re-verified) was disclosed rather than hidden,
  and the re-applied code matches the brief byte-for-byte as far as the diff shows.

---

## Cross-cutting
- Commit style: both are lowercase `type(scope): subject` with why-bodies that
  name the test command and the mutation result. Good. The only defect is the
  factual "subsumes it" claim in c462c0b (T2-1).
- No measured constants were touched; no source files were touched at all —
  both commits are test-only.
- No lint tooling is configured in this repo, so no lint findings apply.
- No dangling references to the retired test name in live code; the remaining
  mentions are historical verdict docs and the plan, which are records.
