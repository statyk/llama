# SDD ledger — plan: docs/superpowers/plans/2026-09-06-pacing-loose-ends.md

Spec: `docs/superpowers/specs/2026-09-06-pacing-loose-ends-design.md`
Worktree: `/Users/shawn/projects/llama-wt-pacing-loose-ends`, branch `pacing-loose-ends`, base `660f588`
Test command (the ONLY valid one): `cd /Users/shawn/projects/llama-wt-pacing-loose-ends && ./.venv/bin/python -m pytest -q`
Baseline: 1871 passed, 7 deselected.

## Pre-flight conflict scan (2026-09-06 13:54 EDT)

Every symbol, helper and file the plan names was checked against the real tree before Task 1.

### Cross-task shared surfaces

| Tasks | Shared surface | Producer says | Consumer says | Finding |
|---|---|---|---|---|
| 3 → 6 | `CountingProvider` in `test_sessions.py` | T3 defines it | T6 "do not define a second copy" | Consistent; T6 must run after T3 |
| 4 → 5,6,7 | `RunWorkspace.request` + request.json shape | T4 adds `self.request` beside `self.criteria` (workspace.py:119 confirmed) | T5 reads it in `run_resume`; T6 gates after its write; T7 needs `iter_sessions` fallback for `info.query` | Consistent |
| 5 → 7 | `_interpret_and_stamp(config, ws, req)` | T5 creates it | T7 wraps its call in the RateLimited loop | Consistent |
| 6 → 7 | `PF_NOW` module constant in `test_sessions.py` | T6 Step 1 adds it | T7 uses it | Consistent; T7 must run after T6 |
| 4,5,6,7 | `_get_query` body | Edit order: request.json write (T4) → preflight gate (T6) → interpret loop (T5 then T7) | — | Sequential, non-overlapping regions. No conflict |
| 6 | `_execute` preflight vs `_get_query` preflight | T6 gates both | — | Two meter reads at query-mode start; spec accepts explicitly ("Accepted cost, stated rather than engineered away") |

### Per-task self-consistency

| Task | Tests vs code it specifies | Files created vs later touched | Finding |
|---|---|---|---|
| 1 | 3 tests; 2 drive the loop, 1 pins `decide()` untouched | cli.py `_pacing_line` at 295; insert point after `seven_day` block confirmed present | Agrees |
| 2 | 1 new test + 1 retired (`test_default_config_template_documents_every_pacing_knob`, confirmed at test_config.py:188) | needs `import re` — confirmed ABSENT, plan says add it | Agrees |
| 3 | 1 test, non-empty precondition before the equality | `fake_providers`/`FakeIA`/`JB_OFF` imported at test_sessions.py:21 | Agrees |
| 4 | 3 tests | `cli.py` has no module-level `import json` — confirmed (only `_json` inside `run_list`); plan says add it | Agrees |
| 5 | 3 tests; `read_model`, `Criteria`, `mark_paused`, `iter_sessions`, `write_artifact` all imported at test_sessions.py:9-16 | `run_resume`'s `if not ws.criteria.exists():` block confirmed verbatim at cli.py:939 | Agrees |
| 6 | 1 test; `cli.read_usage` is a module-level name (cli.py:16) so the monkeypatch resolves | `_execute`'s `slept = False` / `while True:` block confirmed verbatim at cli.py:346 | Agrees |
| 7 | 2 tests; `LimitedProvider(resets_at, times=1, then=None)` with `.calls` confirmed at test_sessions.py:328-343 | `_get_query`'s T6b comment block confirmed at cli.py:667-670 — T7 Step 6 must also fix CLAUDE.md | Agrees |

### Rulings from the scan

Ruling: the plan's Global Constraints name baseline `main @ 45f009b`, the spec names `origin/main @ 2386eb9`, and the worktree base is `660f588`. All three name the SAME measured baseline (1871 passed / 7 deselected), which I verified resolves inside the worktree. Treating the SHA divergence as cosmetic bookkeeping and proceeding. — Cost if wrong: the expected per-task test-count deltas (1874/1874/1875/1878/1881/1882/1884) would be offset by a constant, which the first task's full-suite run would surface immediately.

Ruling: test-count arithmetic across all seven tasks is internally consistent from 1871 (+3, +1-1, +1, +3, +3, +1, +2 = 1884). Adopting these as hard gates: a task reporting a lower total than predicted has lost an existing test and is a finding, not a rounding error. — Cost if wrong: a false BLOCKED on a legitimate count change.

No conflicts found requiring a ruling against plan text.

## Progress

### Task 1 — render the `per_model` meter (render-only)

- Implementer: Sonnet. Spec reviewer: Opus. Code-quality reviewer: Opus. The two reviewers were dispatched in parallel with disjoint inputs (brief + implementer report + diff file); neither saw this ledger or the other's findings.
- Test command run, by implementer and independently reproduced by BOTH reviewers: `cd /Users/shawn/projects/llama-wt-pacing-loose-ends && ./.venv/bin/python -m pytest -q` → **1874 passed, 7 deselected** (predicted 1871 + 3, exact).
- Mutation checks, predictions named before application, both matching uniquely:
  - delete `sorted()` → predicted `test_per_model_meters_render_in_a_stable_order`, observed the same as the SOLE failure.
  - make `decide()` read `per_model` → predicted `test_decide_ignores_the_per_model_meter`, observed the same, with the concrete wrong verdict `PauseUntil(scope='five_hour', ...)`. This is the mutant that proves the render-only boundary is test-enforced rather than merely intended.
  - The quality reviewer re-ran both mutants against the FULL suite (the implementer had used `-k per_model`) in a scratch shadow tree with a proven `llama.cli.__file__` sentinel, leaving the worktree untouched — and confirmed each produced exactly one failure, the predicted one.
- Verdicts: **Spec ✅** (`$D/t1-spec/report.md`), **Task quality: Approved** (`$D/t1-qual/report.md`). No Critical or Important findings from either.
- Task 1: minor (deferred): the per-model segment renders a bare account label (`· Fable 42% ·`) with no scope word, beside a segment already labelled `weekly`; an operator could read it as a differently-scoped meter. Brief-specified and test-pinned, so a spec-level revisit rather than an implementation slip.
- Task 1: minor (deferred): `test_the_line_renders_the_per_model_meter` uses `startswith` where its neighbours assert full-line equality, so it cannot see content appended after `est`. Both reviewers raised this independently; the empty-`per_model` full-equality pin and mutant 1 already cover the realistic failure modes.
- Two ⚠️ Cannot-verify-from-diff items, both resolved by me: (1) `llama pacing`'s side of spec item 2 holds via the shared `_pacing_line` at cli.py:1521 — the quality reviewer independently confirmed both call sites share the one function, so there is no second render site; not a gap. (2) the spec's evidence bar for binding `per_model` later is explicitly future work and the code comment points at it, which is all the brief asked; not a gap.
- **Task 1: complete (commits cb5ff4e..8933fdb, review clean)**

### Tasks 2 + 3 — config-template key-set assertion, and "resume costs nothing"

Batched into ONE implementer dispatch (both single-file, test-only, same shape). Reviews were kept SEPARABLE, one verdict per task, on the coordinator's instruction: Task 3's brief tells the child to stop for a ruling if the resume test spends an LLM call, and a merged verdict is exactly where a finding like that goes quiet.

- Implementer (both tasks, and fix round 1): Sonnet. Spec reviewer: Opus. Code-quality reviewer: Opus. Scoped re-reviewer: Opus. The two task reviewers ran in parallel with disjoint inputs and never saw this ledger or each other's findings.
- Landed: `c462c0b` (Task 2) → 1874 passed / 7 deselected (+1 new, −1 retired, as predicted); `126bd72` (Task 3) → 1875 / 7. Command on every result: `cd /Users/shawn/projects/llama-wt-pacing-loose-ends && ./.venv/bin/python -m pytest -q`. Both reviewers reproduced both counts independently.
- Both tasks landed GREEN on their first run, which is the correct outcome — they are bit-rot protection, and the mutation is the only evidence either can fail.
- Task 2 initial mutation: predicted `test_the_template_documents_every_config_key` with message `{'pacing': ['five_hour_ceiling']}`, observed exactly that, and `test_default_config_template_matches_defaults` stayed green. The spec reviewer independently confirmed the asymmetry and added two further mutants proving the commented-key and nested-table-header extraction paths are each load-bearing.
- Verdicts: Task 2 spec ✅, Task 3 spec ✅ (`$D/t23-spec/report.md`); Task 2 quality **Changes requested**, Task 3 quality **Changes requested** (`$D/t23-qual/report.md`). Two Important findings, both originating in the plan's PRESCRIBED code rather than implementer improvisation.

#### Fix round 1/5 — 2 addressed, 0 open (commits 126bd72..639c6b0)

Ruling: **T2-1 — restore the reverse (phantom-key) direction.** The retired `[pacing]`-only test asserted set EQUALITY, so it caught a key in the template that the model does not have; the plan's prescribed replacement checks only `fields − documented`. `Config` sets no `model_config`, so pydantic's `extra="ignore"` means nothing else in the suite sees a phantom key either — measured, adding `reserve = 10` under `[pacing]` left test_config.py at 22 passed. Per `docs/superpowers/2026-09-05-usage-pacing-phase2-verdicts/t4.md:104` the retired test was itself introduced as the answer to a mutation gap, so this was a knowingly-won constraint being handed back. I ruled the finding beats the plan text because the SPEC (section 4) frames the work as *generalizing* that assertion, and dropping a direction is a narrowing, not a generalization. The inaccurate "subsumes it" wording in c462c0b's body is corrected in the new commit's body rather than by rewriting history. — Cost if wrong: a stricter test that could fail on a future template deliberately documenting a key ahead of the model having it; cheap and loud, versus a silently ignored operator knob.

Ruling: **T3-1 — pin re-entry, not merely a cheap resume.** Mutating `should_run` to `return True` left `test_resuming_a_packaged_run_costs_no_llm_calls` GREEN: the resume re-runs winnow, library dedup empties the shortlist, and `_execute` exits early on "No shows survived winnowing." having spent nothing — so the equality held for an entirely different reason and the show was never re-entered. The short-circuit route is precisely what survives the regression the test claims to guard. I ruled the fix in because the spec's item 3 asks for zero calls **"on re-entry"** — re-entry is the spec's own word, and a test that passes when re-entry never happens does not assert it. Fix: `assert "packaged:" in resumed.output` between the exit-code check and the equality. — Cost if wrong: one assertion coupled to a stage-banner string, which a rewording would break loudly and trivially.

- Fix mutation checks, predictions named before application, all MATCH: phantom `reserve = 10` → the new test, `phantom={'pacing': ['reserve']}`; forward `five_hour_ceiling` deletion re-verified → `missing={'pacing': ['five_hour_ceiling']}`; `should_run → return True` → the resume test failing at `test_sessions.py:477`, exactly the new assertion, with the three earlier assertions still passing so the new line is solely what catches it.
- The re-reviewer re-derived all four independently in a proven shadow copy (sentinel visible under pytest, `PYTHONPATH`-shadowed, `python -m pytest`, never a `.venv/bin/*` script from the copy, copy byte-identical to the worktree before and after) and added two more: a phantom top-level key and a phantom whole section, both caught — so the reverse check is live at the top level too, which is strictly more than the retired test could do.
- Re-review verdict: **T2-1 ADDRESSED, T3-1 ADDRESSED**, no new Critical/Important breakage, suite unchanged at 1875/7 (`$D/t23-rr1/report.md`).

Ruling: **keep `CountingProvider.calls` as-is** despite it shadowing `FakeProvider.calls` (int vs the prompt log). Task 6's prescribed code asserts `providers["interpret"].calls == 0`, so renaming would force an unplanned edit to a later task's plan text for a cosmetic gain, and the prompt log stays reachable as `.inner.calls`. — Cost if wrong: a future reader of `CountingProvider` expects a prompt log and gets an int; contained to tests.

- Task 2: minor (deferred): a wholly commented-out block reads as "documented" — the extractor cannot distinguish seeded from example.
- Task 2: minor (deferred): `_TEMPLATE_KEY` accepts any prose comment shaped like `# ident =`; no current false positive.
- Task 2: minor (deferred): only one nesting level is checked, so `LineageEra`'s own fields are unasserted in either direction.
- Task 2: minor (deferred): local `from pydantic import BaseModel` despite a module-level pydantic import; `get(...) + [name]` instead of `setdefault(...).append(...)`.
- Task 3: minor (deferred): the fresh-run mutant reddens the exit-code assertion, not the final equality — single-item FakeProvider queues mean any re-spend crashes first, so the equality itself has no demonstrated red. Both reviewers found this independently. Deepening the queues is what would demonstrate it.
- Task 3: minor (deferred): 639c6b0's docstring parenthetical "(`run_winnow` runs again, the stages walk from the top)" is ambiguous — true as "is invoked again", false as "re-executes its work".
- Deferred and filed OUTSIDE these tasks, for the final review to triage: `Config` sets no `model_config`, so pydantic's `extra="ignore"` silently drops a typo'd key in a real operator `config.toml` at load time. The new test guards the shipped TEMPLATE only. `extra="forbid"` is the durable fix and is a production behaviour change well outside this plan — filed, deliberately not smuggled in.
- Process note recorded, nothing in doubt: the implementer ran its mutants in the WORKTREE with `git checkout` restore rather than in a copy. The re-reviewer re-derived every one in a proven copy and all matched, and the worktree was clean at each commit — but a copy is the safer default when another agent may share the worktree. Task 4's dispatch will say so.
- **Task 2: complete (commits 35a4694..c462c0b + fix 9d010ef, review clean after 1 fix round)**
- **Task 3: complete (commits c462c0b..126bd72 + fix 639c6b0, review clean after 1 fix round)**

### Task 4 — persist the request at run-claim time (T6b groundwork)

- Implementer (and fix round 1): Sonnet. Spec reviewer: Opus. Code-quality reviewer: Opus. Scoped re-reviewer: Opus. Task reviewers ran in parallel on disjoint inputs.
- Landed `2b42172` → 1878 passed / 7 deselected, as predicted. All three tests were genuinely RED first (`FileNotFoundError` on the missing `request.json`, `AttributeError: 'RunWorkspace' object has no attribute 'request'`). The spec reviewer reproduced red-first independently in a copy AND isolated each source edit — reverting `sessions.py` alone gave 2 failed / 1 passed, reverting `cli.py` alone gave 1 failed / 2 passed — so each of the three source changes has a test that reddens without it.
- `_session_json` needed no change: it is a pure projection of `SessionInfo`. Both the implementer and the spec reviewer confirmed this rather than assuming it, as the brief demanded.
- Verdicts: **Spec ✅** (`$D/t4-spec/report.md`); **Task quality: Changes requested** (`$D/t4-qual/report.md`), two Important findings.

#### Fix round 1/5 — 3 addressed, 0 open (commits 2b42172..a15ff4a)

Ruling: **QF-1 — pin the write-before-interpret ordering.** `test_get_persists_the_request_before_interpreting` asserted only that the artifact exists after a SUCCESSFUL run; moving `write_artifact` below `run_interpret`, or even below `_execute`, left all 1878 tests green while destroying the single property T6b rests on. The test's own name asserted an ordering it did not check, and because the brief assigned this task no mutation step, the red-first evidence was the only stand-in — and `FileNotFoundError` is equally consistent with a write placed anywhere in `_get_query`. I ruled the fix in on the spec's wording ("immediately after `claim_run_dir`, before any LLM call"): a checkpoint written after the call it is meant to survive is worthless. This is precisely the project's standing "green suite ≠ pinned" rule, at the base of a four-task sequence. — Cost if wrong: one ~8-line test whose only failure mode is being redundant with Task 7's pause test.

Ruling: **QF-2 — mirror the fallback into `_by_run_rollup`, MINIMALLY.** There are three query renderers, not two. The brief named `_session_json` (correctly needing nothing); it did not name `_by_run_rollup` (cli.py:2680-2686), which duplicates the criteria lookup, so `llama run list` showed the real query while `llama status --by-run` still showed `""` for exactly the parked-before-interpret run this task exists for — and the commit message claimed the broader property. I ruled the minimal mirrored `elif ws.request.exists()` fallback IN and the refactor-through-`iter_sessions` OUT: Tasks 5, 6 and 7 all edit `cli.py`, so a refactor now widens the conflict surface for no functional gain. The duplicated lookup is filed as a deferred minor for the final review. — Cost if wrong: three duplicated lines that the deferred refactor deletes anyway.

Ruling: **QF-3 — a Minor pulled INTO the loop rather than deferred.** `test_run_list_json_survives_a_session_with_no_criteria`'s docstring claimed "both paths are pinned"/"either renderer" while only `--json` was exercised. I ruled it fixed by adding the missing human-table assertion rather than by softening the words, because a claim of coverage the test does not deliver is the same defect class as QF-1 and this run has now hit that class three times. — Cost if wrong: one cheap assertion.

- Fix landed `a15ff4a` → **1880 passed, 7 deselected** (+2 new test functions; QF-3 extended an existing test rather than adding one).
- Mutation checks, predictions named before application, all re-derived independently by the re-reviewer in a proven shadow copy: moving the write below `run_interpret` → fails EXACTLY `test_request_is_written_even_when_interpret_fails` with the predicted `FileNotFoundError` (1 failed / 1879 passed), and the re-reviewer additionally probed that `result.exception` really is `RateLimited` so the non-zero exit is not accidental; deleting the new `elif` → fails exactly the new `--by-run` test, and its failure output proves the query does not leak from the attention block above the rollup, so the assertion measures `_by_run_rollup` alone; mutating `_session_criteria_str` to stop reading `s.query` → fails the new table assertion while the `--json` assert above still passes, which confirms QF-3's "passed on first run" was honest AND that the assertion can fail.
- Re-review verdict: **QF-1/QF-2/QF-3 all ADDRESSED**, no new Critical/Important breakage (`$D/t4-rr1/report.md`).
- Task 4: minor (deferred): the pre-existing comment at `cli.py:679-682` and `sessions.py:98`'s field comment both still say "the query lives only in argv", which this task falsified. Left deliberately — Tasks 6/7 rewrite that region and `CLAUDE.md` with it. **Task 7's dispatch must confirm this actually happened.**
- Task 4: minor (deferred): `_by_run_rollup` still duplicates the query lookup instead of routing through `SessionInfo`.
- Task 4: minor (deferred): the unguarded `json.loads(ws.request.read_text())` now has TWO call sites; a malformed `request.json` raises out of the read-only `run list` and `status --by-run` views, taking down the whole workspace sweep rather than one run dir. Low risk (atomic unique-temp + rename writes) and the existing criteria branch has identical exposure, so not a regression — but any eventual hardening must cover both sites.
- Task 4: minor (deferred): `write_artifact` already serializes dicts with `json.dumps(..., indent=2)`, so the explicit dumps and the new module-level `import json` were avoidable.
- Task 4: minor (deferred): `test_run_list_shows_the_query_of_a_run_with_no_criteria` uses positional `iter_sessions(tmp_path)[0]` where the file's convention two tests up is id-keyed.
- Confirmed, no change: `--limit` is `typer.Option(0, ...)`, so `request.json["limit"]` is `0` and never `null` despite the spec declaring `int|None`. Task 5's prescribed replay already tests it falsy (`if req.get("limit"):`), which is correct — carried into Task 5's dispatch so it is not "fixed" into `is not None`.
- Noted for Tasks 5-7: `--name` bypasses `claim_run_dir`, and both `request.json` tests pass `--name`. Harmless (the write follows `RunWorkspace(...)` on both paths) but worth knowing which path is under test.
- Process note, nothing in doubt: the implementer again mutated in the WORKTREE (committing first, reverting cleanly — worktree clean at `a15ff4a`, suite back to 1880) rather than in a copy. The re-reviewer re-derived every mutant in a proven copy and all matched. Task 5's dispatch repeats the copy instruction.
- **Task 4: complete (commits 28fbb9e..a15ff4a, review clean after 1 fix round)**

