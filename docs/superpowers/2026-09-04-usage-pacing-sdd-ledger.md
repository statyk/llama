# SDD ledger — plan: docs/superpowers/plans/2026-09-04-usage-pacing-phase1.md

> ## ⚠️ UNREVIEWED WORK ON THE BRANCH — READ BEFORE ANY OTHER ACTION
>
> **Tasks 5 and 6 are IMPLEMENTED AND COMMITTED BUT NOT REVIEWED.**
> Commits `f894b34` (task 5, `[pacing]` config + duration/sleep helpers) and
> `f403239` (task 6, `paused` session state). No spec-compliance review, no
> code-quality review, no fix round. The suite is green at 1694, and green is
> NOT review — every other task on this branch that looked green was changed
> by review, twice by mutation testing that found the tests decorative.
>
> **The next action in the fresh window is the Opus review pair over
> `19a4aa9..f403239`, before Task 7 or anything else.** Do not build Task 7 on
> top of unreviewed foundations: Task 7 consumes `parse_duration`,
> `format_delta`, `sleep_until`, `PacingConfig` and `mark_paused` directly, so
> a defect in either task propagates into the largest task in the plan.


Spec: docs/superpowers/specs/2026-09-04-usage-pacing-design.md (read; phase 1 = reactive half only)
Branch: usage-pacing, base 9f4440e (no worktree — repo-root .venv is editable against this checkout)
Baseline suite at 9f4440e: `./.venv/bin/python -m pytest -q` -> 1648 passed, 7 deselected, 5.56s
(The plan says "green at 1440+"; the measured number is 1648. Use 1648.)

## Preflight scan

### Cross-task rows (pairs sharing a file or an interface)

| A -> B | produced / consumed | finding |
|---|---|---|
| T1 -> T3 | `set_capture_dir`/`capture_failure`; T3 asserts exactly 1 file containing stderr "boom" | OK — T1 writes stderr into the body and calls capture once per failure branch |
| T2 -> T3 | `classify`, `RateLimited` | OK — T3 calls `classify(message)` with no `now`; message text carries the reset |
| T2 -> T4 | `RateLimited` in the no-retry tuple | OK — `_with_transport_retry` is the only retry point; the ladder in `run_json_task`/`run_research_task` puts no try/except around it, so RateLimited propagates past the escalation ladder (verified tasks.py:76-100,102-135) |
| T2 -> T7 | `RateLimited(msg, scope=, resets_at=)` constructed directly in T7's test | OK — signature matches T2's `__init__` |
| T2 -> T8 | mutations 3 and 4 target `MAX_RESET_AHEAD_S` and `_SIGNATURES` | OK — both trace to a real red |
| T5 -> T7 | `parse_duration`/`format_delta`/`sleep_until`/`_now`/`_sleep`; T7 appends `PaceOptions`/`pace_options`/`resume_at` to the same file | OK — T7 appends, does not rewrite; `sleep_until(when, echo=...)` matches T5's `(when, echo, chunk_s=900)` |
| T5 -> T7 | clock indirection | OK — T7 mandates `from llama import pacing as _pacing` + `_pacing._now()`, which is what keeps `monkeypatch.setattr(pacing,"_now",...)` effective |
| T6 -> T7 | `mark_paused(ws, outcome, failures, resume_after, scope, reason)` | OK — T7's call site matches arity and order |
| T6 -> T7 | both modify `cli.py` | OK — disjoint regions (`_print_sessions`+imports vs `_execute`+command signatures) |
| T6 -> T7 | both append to `test_sessions.py` | OK — sequential; T6 adds the `STATE_PAUSED`/`attention_sessions` imports T7 reuses |
| T7 -> T8 | mutation 1 targets T7's `except RateLimited` ordering | OK |

### Per-task self-consistency rows

| Task | own tests vs own code | finding |
|---|---|---|
| T1 | 4 tests; impl writes cmd/exit_code/stdout/stderr; `FileExistsError` is an `OSError` so the unwritable-dir test passes | OK. Deferred minor: filename uniqueness leans on `time.monotonic_ns() % 1_000_000`. |
| T2 | traced all 10 tests by hand against the impl, incl. the 5.5h bound, the DST case (2026-11-01 07:30 NY is already EST), and the caller-in-UTC case | OK |
| T3 | `FakeProc`/`patch_run`/`CLOSED_MID` all exist in test_claude_cli.py (lines 10,15,138); `CLOSED_MID` there is a dict, T2's same-named constant is a local string in a different file | OK |
| T4 | `pytest`, `tasks`, `Answer` already in test_llm_tasks.py | OK |
| T5 | traced `parse_duration` rejects ""/"6"/"-2h"/"6x"/"soon"; `format_delta(90)`->"1m"; `sleep_until` 1h @900s -> exactly 3 echoes | OK |
| T6 | tests trace | **FINDING R5** — plan touches `_print_sessions` but not `_ATTENTION_LABELS`/`_ATTENTION_HINTS` (cli.py:2178-2179) |
| T7 | | **FINDINGS R1, R2, R3, R4** — see rulings |
| T8 | mutations 1-4 each trace to a real red | **FINDING R6** — mutation 1's SyntaxError claim is wrong |

### Noted, not ruled on
- A `RateLimited` raised during `run_winnow`'s opening burst (`light_research`, `score_reviews`) propagates out of `_execute` uncaught — winnow has no `except` at all. This is not a regression (it propagated before too, just after 3 wasted retries); pre-flight pacing is explicitly phase 2. Leave it.

## Rulings

Ruling R1 (Task 7, load-bearing): The plan's show loop drops the show that hit the limit. `if limited: unprocessed.extend(pending[idx:])` sits at the TOP of the for body, so it fires on the iteration AFTER the one that set `limited` — the interrupted entry is never re-queued, and after a sleep-and-continue the run calls `mark_complete` having silently skipped it. Move the check to AFTER the `try/except Locked` block so `pending[idx:]` includes the interrupted entry; same in the deferred pass. — Why: the spec requires the partially processed show to be redone on re-entry, not dropped. — Cost if wrong: a show is processed twice within one run (cheap: stage-level `should_run` skips completed artifacts).

Ruling R2 (Task 7): `test_a_usage_limit_within_max_wait_sleeps_and_then_finishes` passes even under R1's bug — with one show in the fixture, dropping it still yields STATE_COMPLETE, failures==[] and an advanced clock. Strengthen it to assert the show actually packaged (`info.outcome == "1 packaged"` and `providers["brief"].calls >= 2`). — Why: repo lesson "green suite != pinned"; a test that cannot fail on the bug it names is not a test. — Cost if wrong: none, it is strictly stricter.

Ruling R3 (Task 7): The `while pending:` loop can sleep forever if the backend keeps refusing within `max_wait`. Add a no-progress guard: if a pause cycle ends having processed no show since the previous pause, checkpoint via `mark_paused` instead of sleeping again. — Why: an unattended process that naps indefinitely is worse than the failure being fixed. — Cost if wrong: a legitimate second consecutive pause checkpoints instead of sleeping; the operator resumes by hand. Safe direction.

Ruling R4 (Task 7): `stages/gather.py:992` catches `(TaskFailed, HerderError)` around the `align_structure` fallback, and `RateLimited` subclasses `HerderError` — so a limit hit there is swallowed, gather completes with a `low-confidence structure alignment` flag, that flag persists on disk, and `should_run` means the resume never recomputes it. Add `except RateLimited: raise` ahead of it, with a test. — Why: the spec's guarantee is "a limit hit is not a show failure — nothing about the show is wrong"; a permanent bogus review flag violates it. — Cost if wrong: one more code path can pause a run, which is the intended behaviour.

Ruling R5 (Task 6): Also add `STATE_PAUSED: "paused"` to `_ATTENTION_LABELS` and `STATE_PAUSED: "llama run resume {id}"` to `_ATTENTION_HINTS` (cli.py:2178-2179). — Why: without them a paused run renders with a raw state string and no resume hint on `llama status`. — Cost if wrong: cosmetic.

Ruling R6 (Task 8): Mutation 1's note that reordering `except` clauses makes Python "raise SyntaxError" is wrong — Python permits it and the clause is simply unreachable. Take the "if it does not error outright" branch as the expected path. — Cost if wrong: none.

Ruling R7 (baseline): Baseline is 1648 passed / 7 deselected, not the plan's "1440+". — Cost if wrong: none.


## Execution

Plan amendments (author-approved, landed as `ecd2fc1 docs: fold the preflight rulings into the usage-pacing plan and spec`):
- R4 promoted to its own **Task 4b** ("Stop `gather` swallowing a rate limit as an alignment failure"), with its own test and a fifth mutation in Task 8. Task order is now 1, 2, 3, 4, 4b, 5, 6, 7, 8.
- R1/R2/R3 folded into Task 7's code and test blocks; R6 corrected in Task 8's mutation 1.
- Spec gained a "cli.py is not the only ordering hazard" note under Integration, an audit of every `except HerderError` on the `_execute` path, and a fourth entry in its mutation list.
- Deviation from the author's instruction, recorded rather than hidden: the amendment commit was to land BEFORE Task 1's code commit, but Task 1's implementer had already landed `c81759d` by the time the instruction arrived. History was not rewritten; the docs commit sits on top. No content consequence — Task 1 touches neither amended area.

Ruling R8 (protocol): the harness refuses a subagent's `Write` to a scratchpad file named `report.md` ("Subagents should return findings as text, not write report files"). Task 1's implementer hit this and correctly wrote the authoritative report to the project workspace path, then touched the sentinel. Dropping the scratchpad-copy clause from every later dispatch: report-to-workspace-path then sentinel is the contract. — Cost if wrong: none; the workspace report is the one that mattered.

Task 1: complete pending review (commit c81759d, suite `./.venv/bin/python -m pytest -q` -> 1652 passed, 7 deselected; baseline 1648 + 4 new)
Task 1: implementer Sonnet; spec-compliance reviewer Opus; code-quality reviewer Opus (both in flight)
Task 1: minor (deferred): capture filename uniqueness rests on `time.monotonic_ns() % 1_000_000` — implementer flagged it as a concern; kept verbatim per the brief.

Task 1: spec verdict ✅ PASS (task-1-spec-verdict.md, sha256 9f8f4f0347c33b91591757b96db1b8aa68dfaeb09d4ccc16ee21cf9fead6e15c). Fidelity checked mechanically — the brief's two python blocks difflib-compared against the committed files, IDENTICAL. Zero scope creep; claude_cli.py untouched.
Task 1: quality verdict Changes requested (task-1-quality-verdict.md, sha256 e8e7b3264d9b8c924e3759c48f78fbe4a1b105b4cf9e46baec4a460f3d0f6592) — 2 Important, 4 Minor.

Ruling R9 (Task 1, plan-mandated code vs review finding): quality findings 1 and 4 are Important and I am fixing them, even though the offending lines are the plan's own literal code. The plan mandates `except OSError` and a bare `path.write_text(...)`, but the same block's docstring states the contract "Never raises ... a capture problem must never mask the backend failure being captured", and the spec's intent is that capture make a failure MORE diagnosable, never less. `write_text` without `encoding=` raises `UnicodeEncodeError` (a ValueError, not an OSError) on non-ASCII output under a non-UTF-8 locale — and `capture_failure` is called from `claude_cli._run` immediately before the real error is raised, so an escaping exception destroys the exact diagnosis the module exists to preserve. Finding 4 is the matching test gap: the "never raises" test blocks `mkdir` and so never reaches `write_text`, leaving the contract green but unpinned — the repo's own "green suite != pinned" lesson. Fix: `encoding="utf-8", errors="replace"`, widen the handler to `except Exception` with the defensive `# noqa: BLE001` comment this repo already uses at `jerrybase.py:128` for an identical must-never-raise guard, and add a test that fails on the WRITE rather than the mkdir. — Why: the plan's literal code does not implement the plan's own stated contract, and the spec backs the contract. — Cost if wrong: a genuinely unexpected exception class is swallowed inside capture; the backend error it was masking still propagates, which is the pre-existing behaviour.
Task 1: minor (deferred): filename collision (~1e-6, same second + same pid) silently overwrites the earlier capture.
Task 1: minor (deferred): capture stamp is unmarked local time and appears only in the filename, not the body.
Task 1: minor (deferred): test_each_capture_gets_its_own_file pins the uniquifier only probabilistically (passes without it when calls straddle a second boundary).
Task 1: minor (deferred): `proc` parameter unannotated, its duck type undocumented.
Task 1: fix round 1/5 (2 addressed, 0 open — "never raises" contract made true with encoding="utf-8", errors="replace" + widened handler; new test pins it; commits c81759d..05d6279)
Task 1: re-review clean (task-1-rereview-1.md) — both findings ADDRESSED, no new breakage, scope confined to the two intended files. The implementer proved the new test load-bearing by narrowing the handler back to `except OSError`, watching it go red, and restoring; the re-reviewer independently traced that ValueError is not an OSError and confirmed the claim is mechanically consistent.
Task 1: complete (commits 9f4440e..05d6279, review clean, 4 minors deferred)
Task 1 dispatches: implementer Sonnet; spec-compliance reviewer Opus; code-quality reviewer Opus; fix round 1 resumed the same Sonnet implementer; scoped re-review Sonnet.
Suite after Task 1: `./.venv/bin/python -m pytest -q` -> 1653 passed, 7 deselected.

Ruling R10 (process): scoped re-reviews of small fix diffs run on Sonnet, not Opus. The SDD skill puts them at "cheap-to-mid tier" explicitly, and the coordinator's "both reviewers on Opus every task" binds the TASK review (spec-compliance + code-quality), which is the gate. Flagged upward at the Task 1 boundary so the coordinator can overrule. — Cost if wrong: a small fix diff gets a cheaper pair of eyes; the Opus task review still gates the task.

Ruling R11 (batching, author-approved): the remaining tasks run as 5 review pairs, not 7 — Task 2 standalone (in flight), Tasks 3+4+4b batched (one change wearing three hats: "RateLimited must not be swallowed", at three call sites; note 4b is llama-side gather.py, not herder), Tasks 5+6 batched (small, additive, no shared file), Task 7 standalone with an Opus implementer, Task 8 standalone. Option (c) — dropping spec-compliance to Sonnet — was REFUSED by the author as a policy change not theirs to grant; do not re-raise. If the runway forces a choice, PARK at the stop band rather than thin the review. — Cost if wrong: a batched diff hides a per-task defect from a reviewer judging the group.
Orchestrator agentId for child BLOCKED escalations: a343f27a9dee60e99.
Task 2: DONE (commit baf633d, `./.venv/bin/python -m pytest -q` -> 1663 passed, 7 deselected; 1653 + 10 new). Implementer Sonnet. Reviewers Opus x2 in flight.
Task 2: spec verdict ✅ PASS (task-2-spec-verdict.md, sha256 e13b16b14d8dbb5b4affde0d82de82fb6a3d2578ad8b939ab39291932c569471) — files byte-identical to the brief, U+00B7 confirmed as C2 B7 in the committed blob, zero scope creep. 3 minors.
Task 2: quality verdict Changes requested (task-2-quality-verdict.md, sha256 d34510c8b9ccde3f43106d6f06e39e297fec696a80296e9f7f007240ece638a0) — 0 Critical, 4 Important, 7 Minor. The reviewer built a live mutation harness and found 7 of 8 one-line mutations SURVIVED the 10 shipped tests.

Ruling R12 (Task 2, plan-mandated code vs review finding): fixed all four Important findings even though the offending code is the brief's verbatim text. The module docstring commits to "a false positive is worse than a false negative — the patterns are narrow" and MAX_RESET_AHEAD_S's comment says "parsing must never be able to manufacture a day-long sleep"; neither was pinned. Measured: the largest ACCEPTED delta across the shipped tests was 4.17h and the smallest REJECTED 23.17h, so a bound of 20h passed the whole suite — exactly the day-long sleep forbidden. Also widened `_RESET_RE`'s zone group (production change), because the original demanded exactly one `/` and no digits and so missed `UTC`, the likeliest zone on the unattended headless host this feature targets. Folded in minors 5 and 10 (both reviewers flagged 10; 5 is the same noqa idiom Task 1 just adopted). — Cost if wrong: the widened zone group admits a zone-shaped string that ZoneInfo then rejects, which still yields None.
Task 2: fix round 1/5 (6 addressed, 0 open — 11 pinning tests added, zone regex widened, patterns labelled; commits baf633d..8433771)
Task 2: re-review clean (task-2-rereview-1.md) — all 7 previously-surviving mutations independently re-traced and confirmed KILLED; bound now bracketed 5.1667h accepted / 6.1667h rejected, a 1h gap around 5.5h.
Task 2: complete (commits 05d6279..8433771, review clean, 5 minors deferred)
Task 2 dispatches: implementer Sonnet; spec-compliance reviewer Opus; code-quality reviewer Opus; fix round 1 resumed the same Sonnet implementer; scoped re-review Sonnet.
Task 2: minor (deferred): no hour range guard — `25:10am` silently becomes 1:10am while `11:75am` is rejected.
Task 2: minor (deferred): a naive injected `now` reads as machine-local, making a supposedly deterministic function host-dependent.
Task 2: minor (deferred): nonexistent (spring-forward) wall times resolve 1h late; the ambiguous fall-back case is correct only by `fold=0` accident, undocumented.
Task 2: minor (deferred): exact-equality rollover returns `now` rather than `None` — now pinned, but the choice is undocumented.
Task 2: minor (deferred): `re.Pattern` should be `re.Pattern[str]`; `now = now or ...` where `is None` is meant; generic top-level `herder.classify` export.
Plan synced to the reviewed implementation in 4b5a2d2 (zone regex + a note that the brief's original ten tests killed only 1 of 8 mutations).

## HAZARD for Task 8 (the mutation pass) — carry this into its dispatch

Task 2's implementer hit a real instrument failure during mutate/restore: rapid in-place rewrites within the same mtime-second left a stale `__pycache__/*.pyc` that was reused despite the source changing, producing one FALSE RED. It caught it and redid the sequence cleanly. Task 8 is nothing but mutate/restore cycles against this venv, so its dispatch must require `find . -name __pycache__ -prune -exec rm -rf {} +` (or `PYTHONDONTWRITEBYTECODE=1`) between every mutation and its restore, and must treat any red it cannot reproduce after clearing the cache as an instrument artifact rather than a finding. A false red here would be read as "the constraint is pinned" when it is not — the exact inversion the mutation pass exists to prevent.

## PARKED — run state as of 2026-09-04

Parked deliberately at the coordinator's instruction: the 5-hour window is shared with another dev job and ad-hoc chatbot use, and continuing risked taking those down — the exact cross-session kill this feature exists to prevent. Stop band was lowered 70% -> 60% mid-run. Every task committed; nothing in flight; working tree clean.

DONE: Task 1 (raw failure capture), Task 2 (RateLimited classification + reset parsing). Both reviewed clean.
NEXT DISPATCH: the Tasks 3 + 4 + 4b batch — one Sonnet implementer over all three, then ONE Opus review pair over the combined diff. Briefs already generated at task-3-brief.md, task-4-brief.md, task-4b-brief.md. BASE for that review package is the branch head at dispatch time.
THEN: Tasks 5 + 6 batched (one Sonnet implementer, one Opus review pair); Task 7 standalone with an OPUS implementer (it restructures _execute's show loop and carries rulings R1/R2/R3); Task 8 standalone (mutation pass — see the HAZARD note above).
Open findings carried forward: none blocking. 9 deferred minors listed above, to be triaged by the final whole-branch review.
Do NOT reuse the task names t1, t2, t1fix1, t2fix1, t1rr1, t2rr1, t1spec, t1qual, t2spec, t2qual — task names are single-use.

## RESUMED 2026-09-04 (post-park)

Coordinator lifted the park: the other session on the account is paused until the 21:10 reset, so the window is ours. Stop band raised 60% -> **88%**, meter read between every dispatch rather than only at task boundaries. Two standing constraints for this stretch: (a) if the meter is at or above 80% when the review pair returns, DO NOT start a fix round — ledger the findings and park with the task reviewed-but-unfixed, which is a legitimate resting state; (b) do NOT start Tasks 5+6 tonight regardless of how cheap this batch comes in.

Ruling R13 (measurement discipline, standing): do not derive per-task cost from meter deltas and do not project a burn rate from them. The account is shared with other consumers whose activity changes the apparent rate for reasons unrelated to any dispatch here — the other session going quiet at the park is exactly such a change. Report the level and the reset instant; report nothing computed from their difference. This supersedes the projection I offered at the Task 1 boundary, which was unsound for this reason. — Cost if wrong: I lose a forecasting aid I was not entitled to anyway; the hard ceiling still binds.

Batch 3+4+4b dispatched. BASE 4b5a2d2. Meter at dispatch: 5h 63%, resets 21:09 EDT. Implementer Sonnet, task dir b34b.
Framing given to the implementer, and to be given to the reviewers: these three are ONE invariant — "a RateLimited must not be swallowed or retried" — at three call sites, because RateLimited subclasses HerderError and every broad `except HerderError` is somewhere it can vanish. Tasks 3 and 4 are herder-side transcription; 4b is llama-side (stages/gather.py) and carries the only real judgment, namely finding a test path that actually reaches the align_structure fallback.
The __pycache__ false-red hazard was carried into the batch dispatch (4b requires a delete/restore proof), not held back for Task 8.
Batch 3+4+4b: DONE. Three commits, one per task as required: e4c0786 (task 3, raise RateLimited + capture raw output), cb0b5ff (task 4, no-retry), 682240d (task 4b, gather re-raise). Suite green at EVERY commit: 1678 -> 1680 -> 1681 passed, 7 deselected, from a 1674 baseline (+7 tests: 4/2/1). Implementer Sonnet. Meter after implementer, before reviewers: 5h 68%, resets 21:10 EDT.
Batch 3+4+4b: reviewers Opus x2 dispatched over the COMBINED diff (4b5a2d2..682240d), both told to judge it as one invariant at three call sites and to trace the refusal end to end rather than diffing three briefs. Quality reviewer additionally asked to mutation-test four constraints and to prove the tree clean afterwards.

PLAN DEFECT (found by the implementer, needs a docs fix): task-4b's brief names `packages/llama/tests/test_gather.py`. No such file exists anywhere in the tree — the file that actually exercises `run_gather` is `packages/llama/tests/test_stage_gather.py`, and that is where the test landed. The defect is mine: I wrote Task 4b during the preflight amendment and guessed the test filename from the source filename instead of checking. Correct the plan once the review pair is clear of the worktree (deferring the edit so an uncommitted change cannot disturb the quality reviewer's `git status --porcelain` cleanliness check mid-mutation).
Batch 3+4+4b: spec verdict ✅ PASS (task-3-4-4b-spec-verdict.md) — all three tasks, 6 minors. The reviewer traced the invariant end to end and confirmed the only remaining swallow site on the path is cli.py:237, which is Task 7's job. It also verified the 4b test cannot pass for the wrong reason (align_provider has exactly one call site; a missed branch would raise no RateLimited and pytest.raises would fail) and that it doubles as a cross-task pin on Task 4 — a single queued FakeProvider response means a retry would have raised AssertionError, not RateLimited.
Batch 3+4+4b: quality verdict APPROVED (task-3-4-4b-quality-verdict.md) — 1 Important (test-only), 7 Minor. The reviewer mutation-tested 8 constraints with PYTHONDONTWRITEBYTECODE=1: 6 killed, and the 2 survivors were both on capture_failure, a diagnostic with no production caller until Task 7. All five BEHAVIOURAL constraints pinned. Tree verified clean afterwards.
Batch 3+4+4b: fix round 1/5 (4 addressed, 0 open — pinned M6/M7, added the missing capture on the no-string-result branch, documented the deliberate classify omission, corrected the gather comment's forward reference; commit 59ddbb4)
Batch 3+4+4b: re-review clean (task-3-4-4b-rereview-1.md) — all four ADDRESSED, each pinning test independently confirmed to kill its target, no new breakage, scope held to three files.
Batch 3+4+4b: complete (commits 4b5a2d2..59ddbb4, review clean, 8 minors deferred)
Batch dispatches: implementer Sonnet (3 commits); spec-compliance reviewer Opus; code-quality reviewer Opus; fix round 1 resumed the same Sonnet implementer; scoped re-review Sonnet.

Ruling R14 (batch fix round, meter-gated): the coordinator's rule was "if the meter is at or above 80% when the review pair returns, do not start a fix round". Reading was 74%, so the round ran. It was also the cheapest possible shape — one Important, test-only, plus three one-liners — and it closed the only two surviving mutations in the batch. — Cost if wrong: two meter points spent on diagnostics pinning rather than on Task 7.

Ruling R15 (scoped re-review under the ceiling): ran the scoped re-review at 76% rather than parking the fix unreviewed. The 80% gate governs STARTING a fix round; leaving a landed fix unreviewed is the failure mode the skill names outright ("unreviewed fixes are how regressions land"), and a Sonnet scoped re-review is the cheapest dispatch in the cycle. — Cost if wrong: a small spend that could have gone to Task 7, against an unreviewed commit sitting on the branch overnight.

Plan defect corrected in 4bd2b6f: task-4b named packages/llama/tests/test_gather.py in six places, including Task 8's mutation-5 command. No such file exists. Worth noting WHY this one was dangerous rather than merely wrong: the mutation step's EXPECTED result is a failure, so a pytest invocation against a nonexistent path would have errored and been read as "the mutation worked" — a false confirmation in the one step of the plan whose whole purpose is to distrust green.

Deferred minors from this batch, for the final whole-branch review to triage:
- Batch: minor (deferred): `_run`'s TimeoutExpired branch is uncaptured, though TimeoutExpired duck-types with .stdout/.stderr/.returncode so capture_failure(cmd, e) would work; a 900s hang is otherwise undiagnosable.
- Batch: minor (deferred): the three raise sites in `_run` are near-identical; a `_fail(cmd, proc, message) -> NoReturn` helper would have structurally prevented both gaps this review found.
- Batch: minor (deferred): gather.py imports RateLimited from herder.limits while the line above imports from herder, which re-exports it. Cosmetic; herder-internal modules MUST use the submodule (circular import), gather.py need not.
- Batch: minor (deferred): continuation indent at test_stage_gather.py:288. No linter configured.
- Batch: minor (deferred, INFORMATIONAL, matters for the phase summary): the invariant is claude_cli-SPECIFIC. openrouter.py:37 raises a plain HerderError on any non-200, so an HTTP 429 there is still retried 3x and then fails the show. Correct for this phase (the design targets the Claude subscription window) but it must be stated as a caveat whenever this phase is summarized.
- Batch: minor (deferred): the spec's own audit note misidentifies cli.py:2505 as belonging to fix/triage; it is main_cli, the global boundary that wraps _execute too. Harmless today (prints `error:`, exits 1, persists nothing) but TASK 7 MUST NOT TRUST THAT LINE VERBATIM — carry this into Task 7's dispatch.
- Batch: minor (deferred): cli.py:1902 (the batch `redo` loop) still burns one limit hit per show. Outside _execute, so outside phase 1's guarantee; real residual for the backlog.

## PARKED (second park) — 2026-09-04

Parked at the coordinator's instruction: Tasks 5+6 are explicitly NOT to start tonight; the next move is a park, then a resume after the 21:10 reset. Every task committed, nothing in flight, tree clean.
DONE so far: Task 1, Task 2, Task 3, Task 4, Task 4b — all reviewed clean.
NEXT: Tasks 5+6 batched (one Sonnet implementer, one Opus review pair) — briefs already at task-5-brief.md, task-6-brief.md. Then Task 7 standalone on an OPUS implementer (carries rulings R1/R2/R3, and must not trust the spec's cli.py:2505 attribution). Then Task 8 (mutation pass; carries the __pycache__ false-red hazard).
Task names used and now single-use: t1 t2 b34b, t1spec t1qual t2spec t2qual b34bspec b34bqual, t1fix1 t2fix1 b34bfix1, t1rr1 t2rr1 b34brr1.

## RESUMED for one bounded dispatch — Tasks 5+6 implementer ONLY

Coordinator's window rules: Sonnet implementer over 5+6 batched; NO reviewer dispatches at all this window (the Opus pair does not fit in the remaining budget, and a review pair killed halfway is the one outcome worth avoiding); hard stop 95%; do NOT start Task 7. Meter at dispatch: 5h 80%, resets 21:10 EDT. BASE 19a4aa9. Task dir b56.
Carried into the dispatch on top of the briefs: ruling R5 (add STATE_PAUSED to `_ATTENTION_LABELS` and `_ATTENTION_HINTS` at cli.py:~2178, which Task 6's brief omits), plus explicit fences that PaceOptions/pace_options/resume_at and every `_execute` change belong to Task 7 and must not be built early.

## CARRY INTO TASK 8's DOCS STEP — both verified against source by the coordinator

1. **The invariant is claude_cli-specific, and the spec must say so rather than imply it.** `packages/herder/src/herder/openrouter.py:37` raises a plain `HerderError` on any non-200, so an HTTP 429 on that backend is still retried three times by `_with_transport_retry` and then fails the show. Phase 1's guarantee — "a usage-window refusal pauses the run instead of failing every remaining show" — holds for `claude_cli` ONLY. State it in the spec and in CLAUDE.md's LLM-layer bullet as an explicit caveat.

2. **Task 8's mutation-5 step must prove it ran a test, not merely that a command failed.** The corrected path is `packages/llama/tests/test_stage_gather.py`; confirm that is what the step actually invokes. Then make the step assert it saw a REAL test failure rather than a collection error: a pytest run against a bad path errors, and since the mutation step's EXPECTED outcome is a failure, an errored run is indistinguishable from a killed mutation — it would certify the constraint as pinned while never executing a single test. Require the step to check the failure names the specific test function, or to check pytest's exit code is 1 (tests ran, some failed) rather than 4 (usage/collection error). This is the same defect class as the run's standing rule that a check returning nothing and a check that never looked produce identical output.

## PARKED (third park) — Tasks 5+6 implemented, UNREVIEWED

Parked on the implementer's sentinel exactly as instructed; no reviewer was dispatched this window. Meter at park: 5h 83%, resets 21:10 EDT — never approached the 95% stop.

Tasks 5+6: DONE, two commits as required — f894b34 (task 5), f403239 (task 6). Suite green at BOTH: 1691 after task 5, 1694 after task 6, from a 1684 baseline (+10 tests: 7 and 3). Implementer Sonnet. **NO REVIEW YET — see the banner at the top of this file.**
Scope verified by me after the fact, not merely claimed: `git diff 19a4aa9..HEAD --stat` shows exactly 6 files, +212/-9. Task 7's territory is untouched — `PaceOptions`, `pace_options` and `resume_at` are all absent from `pacing.py` and `cli.py` (grep-confirmed), and the cli.py diff is only the STATE_PAUSED import, two lines in `_print_sessions`, and the two `_ATTENTION_*` dicts.
Ruling R5 landed correctly: `_ATTENTION_LABELS` gained `STATE_PAUSED: "paused"` and `_ATTENTION_HINTS` gained `STATE_PAUSED: "llama run resume {id}"` (cli.py:2180-2183) — the addition the brief omitted.

Order for the fresh window, in this sequence and no other:
1. Opus spec-compliance + Opus code-quality pair over `19a4aa9..f403239`. Tell the quality reviewer to mutation-test — that is what caught the decorative suites in Tasks 1 and 2, and both these tasks are full of exactly the one-line constants that invite it (the `[pacing]` defaults, `MAX`-style thresholds, the `sleep_until` chunk arithmetic, `_write`'s wholesale-rewrite erasure).
2. Fix round if needed.
3. Task 7 — OPUS implementer. Carries rulings R1 (re-queue the show that hit the limit), R2 (strengthen the sleeps-and-finishes test, which passes under R1's bug), R3 (no-progress guard against an unbounded pause loop). Must NOT trust the spec's attribution of `cli.py:2505` to fix/triage — it is `main_cli`, the global boundary that wraps `_execute` too.
4. Task 8 — mutation pass + docs. Carries the `__pycache__` false-red hazard, the openrouter 429 caveat, and the mutation-5 exit-code check (both recorded above under CARRY INTO TASK 8).

Task names used and now single-use: t1 t2 b34b b56, t1spec t1qual t2spec t2qual b34bspec b34bqual, t1fix1 t2fix1 b34bfix1, t1rr1 t2rr1 b34brr1.

## RESUMED after the window reset — 5h 2%, resets Sep 5 02:10 EDT; weekly 10%

Stop band this window is **75%** (not 88 or 95): the other session on the account may be working again, and the coordinator is not claiming the whole window on its behalf. Fix-round gate correspondingly lowered to **65%**.

Ruling R16 (STANDING, all remaining code-quality dispatches): every code-quality reviewer from here on MUST mutation-test rather than read. The coordinator generalized my Task-5+6 request into a standing rule, and the evidence is one-sided: reading has not once found what mutation found on this branch, while mutation found 7 survivors in Task 2's green ten-test suite and 2 more in the 3+4+4b batch, including the `is_error` capture branch that is the single site `failures.py` exists to serve. Every such dispatch also carries the `__pycache__` clearing requirement and a `git status --porcelain` cleanliness proof. — Cost if wrong: reviewers spend longer and touch the worktree; mitigated by the restore-and-prove requirement.

Review pair for Tasks 5+6 dispatched over 19a4aa9..f403239 (2 commits, the previously UNREVIEWED work). Both Opus. Meter at dispatch: 5h 2%. Task dirs b56spec, b56qual.
The quality reviewer was aimed at named targets rather than left to browse: sleep_until's chunk arithmetic and exact echo count, format_delta's 60s floor, parse_duration's `any(m.groups())` guard and anchors, each PacingConfig default one at a time, deleting the field_validator outright, narrowing the validator's field list, _write merging instead of replacing, removing STATE_PAUSED from _state_of's whitelist, and removing the _ATTENTION_* entries.
The spec reviewer was told that ruling R5's `_ATTENTION_*` additions are authorized and NOT scope creep, but asked to verify them against the dicts' real call sites — I specified them from the definitions alone.
Tasks 5+6: spec verdict ✅ PASS both (task-5-6-spec-verdict.md) — programmatically diffed byte-identical to the briefs, R5's `_ATTENTION_*` addition verified correct at every call site, no phase-2 groundwork smuggled in. 5 minors. The reviewer also PROBED rather than assumed the template test: a planted `max_wait = "7h"` makes the comparison unequal, so it genuinely covers the new block.
Tasks 5+6: quality verdict Changes requested (task-5-6-quality-verdict.md) — 6 Important, 11 Minor. **55 mutations run** with PYTHONDONTWRITEBYTECODE=1, __pycache__ cleared each side, a 90s hang-timeout, and the harness smoke-tested first: 28 KILLED, 1 HANG, 26 SURVIVED of which 4 provably equivalent => **22 genuine survivors**. Tree verified clean afterwards (`git status --porcelain` empty, `git diff HEAD` empty over all six files, suite re-run 1694). Implementation judged CORRECT on every reachable input; every finding is coverage.
The single most damning line: `git checkout 19a4aa9 -- packages/llama/src/llama/cli.py` leaves the suite at **1694 passed** — the whole cli.py half of Task 6 is invisible to the tests. R16 (mutate, don't read) paid for itself again; no amount of reading would have produced that sentence.

Ruling R17 (I6, naive-datetime contract): `sleep_until` raises a bare TypeError on a naive `when`. Fixing by raising a legible ValueError, NOT by coercing to UTC. Coercion would silently shift the wake time by the local UTC offset, and since the value is a sleep duration that is a multi-hour error nobody would ever see; an explicit refusal makes Task 7's contract loud instead. Task 7 reads `resume_after` back out of the marker where Task 6 stores it as a STRING, so this is a real cross-task trap, not a hypothetical. — Cost if wrong: Task 7 must pass an aware datetime, which it already has one of.

Ruling R18 (TOML comments left alone deliberately): the `[pacing]` block's comments describe behaviour and a `--max-wait` flag that do not exist at this commit. The reviewer classed it transient and said promote to Important only if these commits could ship without Task 7. Leaving them: Task 7 lands next and makes them true, and rewording now would mean rewording twice. Recorded as a MUST-CHECK for the final whole-branch review — if Task 7 does not land, these comments are a live falsehood in a user-facing config template. — Cost if wrong: a shipped config template briefly documents a flag that does not exist.

Tasks 5+6: fix round 1 dispatched, resumed the same Sonnet implementer. Meter at dispatch: 5h 24%, well under the 65% fix gate. Six Important fixes, all coverage except I6.
Deferred minors from 5+6 for the final review: a backward wall-clock step never terminates in `sleep_until`; `chunk_s<=0` busy-spins; `format_delta(-3600)=="1m"`; the echo TEXT is unpinned (`echo("")` passes); `pause_scope` is write-only so far; `_session_json` omits `resume_after`/`pause_reason` so `run list --json` shows a paused run with no resume time while the human table shows it (TASK 7 SHOULD DECIDE THIS DELIBERATELY — carry into its dispatch); the config template test pins values but not presence, so deleting a whole block would still pass (pre-existing, affects every block equally); `pytest.raises(Exception)` is over-broad; typing/style nits.
Also noted by the quality reviewer and worth keeping: the `remaining <= 0` guard IS load-bearing — weakening it to `< 0` sends the suite into an infinite spin, detected only as a hang rather than a failure. And `_write`'s wholesale-rewrite discipline IS properly pinned once mutated realistically; the reviewer's first merge mutation was an equivalent mutant and it caught its own error rather than reporting a false survivor.
Tasks 5+6: fix round 1/5 (6 addressed + the comment fix; commit 42d90a4; suite 1694 -> 1703, +9 tests). Only ONE production change was needed — I6's naive-datetime guard in pacing.py — plus a one-line comment in sessions.py. config.py and cli.py needed no permanent change at all: every finding in those two was a coverage gap in already-correct code, and both files were restored byte-identical after their mutation proofs. Verified by me: `git diff 19a4aa9..HEAD --stat` still shows cli.py at +10/-3 and config.py at +47, i.e. unchanged by this round.

Worth recording as a run lesson, self-caught by the implementer: its first draft of the two new CLI tests named the workspace `s-paused` / `2026-09-04-paused`, so `assert "paused" in output` was trivially true from the run-id substring no matter what the label said. It found this while proving mutation M48 (label -> "zzz") — only the direct-dict test went red — and renamed to `*-onhold` with exact label-column assertions before treating any of it as evidence. This is the same defect class as the run's standing rule that a check returning nothing and a check that never looked are indistinguishable: here the fixture name silently satisfied the assertion. The re-reviewer has been asked to verify the shipped tests really are clean of it.
Second subtlety the implementer surfaced and the re-reviewer must confirm: `_ATTENTION_LABELS.get(state, default)` and `_ATTENTION_HINTS.get(state, default)` have fallback text that COINCIDES with the values chosen for STATE_PAUSED, so output-only assertions cannot distinguish "entry present" from "entry deleted" — which is why a direct dict-index test was added to kill M43/M44.
Tasks 5+6: scoped re-review dispatched (Sonnet), range f403239..42d90a4. Meter at dispatch: 5h 36%.
Tasks 5+6: re-review clean (task-5-6-rereview-1.md) — all six Important plus the comment fix ADDRESSED, each verified by APPLYING the cited mutation, confirming RED, restoring, and diff-confirming byte-identical. No new breakage. Tree clean throughout.
Both scrutiny items I flagged came back confirmed, and both mattered:
 1. The dict-fallback coincidence is REAL. The re-reviewer reproduced the blindness directly: deleting STATE_PAUSED from both dicts left BOTH output-only CLI tests passing, and only the direct-index test went red. So `_ATTENTION_LABELS.get(s.state, s.state)` returning the raw state string, and `_ATTENTION_HINTS`'s literal default, both happen to render exactly what the correct entries render — an output assertion literally cannot see the difference. The direct-index test is necessary, not belt-and-braces.
 2. The run-id substring bug is genuinely fixed as shipped: every id avoids the substring "paused", and label assertions index the exact column (`.split()[1] == "paused"`) rather than substring-matching.
Tasks 5+6: complete (commits 19a4aa9..42d90a4, review clean, 11 minors deferred)
Tasks 5+6 dispatches: implementer Sonnet (2 commits); spec-compliance reviewer Opus; code-quality reviewer Opus (55 mutations); fix round 1 resumed the same Sonnet implementer; scoped re-review Sonnet.
Suite after Tasks 5+6: `./.venv/bin/python -m pytest -q` -> 1703 passed, 7 deselected.

## EVIDENCE NOTE — the two findings that justify the mutation rule (carry into Task 8's ledger entry VERBATIM)

The coordinator asked that these be recorded as their own note rather than buried as findings, because they are the strongest evidence for why review costs what it costs. Both are cases where a green suite pinned nothing, and neither is reachable by reading a diff.

**1. The whole `cli.py` half of Task 6 was invisible to the test suite.** Measured by the Opus code-quality reviewer, 2026-09-04, with this command:

    git checkout 19a4aa9 -- packages/llama/src/llama/cli.py
    ./.venv/bin/python -m pytest -q
    # -> 1694 passed, 7 deselected

Reverting every line the task added to `cli.py` — the `STATE_PAUSED` import, the `resumes <iso>` render line, and both `_ATTENTION_*` entries — changed nothing the suite could see. The feature was shipped, committed, and completely unpinned. No amount of reading the diff produces that sentence; only running it does.

**2. The subtler cousin: correct entries and DELETED entries render identical output.** `_ATTENTION_LABELS.get(s.state, s.state)` falls back to the raw state string, which is `"paused"` — exactly the label the correct entry supplies. `_ATTENTION_HINTS`'s literal default coincides with `"llama run resume {id}"` the same way. So an output assertion is satisfied by the ABSENCE of the thing it is testing. Reproduced independently by the re-reviewer: with `STATE_PAUSED` deleted from both dicts, both output-only CLI tests still passed and only a direct dict-index test (`cli._ATTENTION_LABELS[STATE_PAUSED]`) went red.

Together: (1) is a test suite that never looked, (2) is a test that looked and could not tell. Both produce a green run, and both were found only by mutation.

Ruling R19 (`_session_json`, ruled by the coordinator, recorded verbatim): **YES — `_session_json` carries `resume_after` and `pause_reason`.** Reasoning as given: `run list --json` exists for scripting, and the single most script-relevant fact about a paused run is when it may resume; a `--json` consumer that sees `state: "paused"` but not the resume instant must shell out to the human-readable output to get it, which is precisely the asymmetry the flag exists to remove. `SessionInfo` already carries both fields, so this surfaces existing state rather than inventing it, and it is additive so no consumer breaks. Null for every non-paused state, matching the marker. If it falls outside Task 7's natural diff, it lands as its own small commit rather than stretching the task.

Handling note: Task 7's implementer was dispatched BEFORE this ruling arrived and was asked to decide the question itself. I deliberately did NOT message it mid-task — it is demonstrably alive and writing, and `SendMessage` into a live writer to change its requirements is how a task acquires a second author. If its report shows it added the fields, the ruling is satisfied; if not, this becomes its own commit, exactly as the coordinator sanctioned.

Task 7: DONE_WITH_CONCERNS. Four commits, incremental as required: 8d6ca73 (PaceOptions/pace_options/resume_at), 08bf139 (the pause/resume loop), 636aa1c (JSON views + hint fix), 980e02b (pins for two constraints its own mutation pass found unpinned). Suite 1703 -> **1736 passed, 7 deselected** (+33). Implementer OPUS. Meter after: 5h 57%.

R19 satisfied inside Task 7 rather than needing its own commit: `_session_json` now emits `resume_after` and `pause_reason`, always present and null off a pause, matching `outcome`'s shape. `pause_scope` deliberately not added — it is not on `SessionInfo`. `test_status_cmd.py`'s exact key-set assertion caught the change and was updated, which is a small piece of evidence that the 5+6 CLI tests are now doing real work.

**The cli.py:2505 misattribution is confirmed and it mattered.** It is `main_cli`, the single global error boundary, NOT fix/triage as the spec's audit note claims. Consequence the implementer established by running it: a `RateLimited` escaping `_execute` hits `except (LlamaError, HerderError)` and exits 1 with NO pause marker, while a `typer.Exit` passes through untouched. That settled a design point rather than merely correcting a comment — the eager `--max-wait` validation had to be `typer.Exit`, not a raised `LlamaError`, or a typo'd duration would have exited 1 through the wrong arm.

**PLAN DEFECT found by the implementer, and a good one: the brief's checkpoint hint printed a command that would not run.** `format_delta` emits `2h 0m`, and `parse_duration` REJECTS `2h 0m` — so the plan's literal `--max-wait {format_delta(wait_s)}` suffix produced a resume command that fails on the user's next invocation. Fixed with a new `pacing.duration_arg`. This is the second time the plan's own literal code has failed its own stated contract (Task 1's "never raises", Task 2's unpinned bound), and the first time it would have been visible to an operator.

Second deliberate departure, also correct: `resume_at` now declines a naive `resets_at` and falls back to `unknown_reset_wait` rather than handing `sleep_until` a value that R17's new guard refuses — otherwise the pause path would crash at exactly the moment it exists to handle.

Task 7 self-mutation evidence: 14 mutants applied and reverted, all killed — including the ORIGINAL R1 defect verbatim (check at the top of the loop), `pending[idx+1:]`, `deferred[idx+1:]`, guard removal, and the rebound-`_now` trap. Its first pass found TWO survivors (deferred shows dropped when a limit lands mid-pass; `set_capture_dir` never called) and 980e02b is what closes them. A 3-show `test_pace_loop.py` driving `_execute` with a scripted `process_show` is what makes the drop-vs-retry distinction observable at all — exactly the multi-show fixture the dispatch asked for.

Task 7 concerns to carry forward (from the implementer, all scope observations rather than defects): (1) a RateLimited from `interpret`/`search`/`winnow` still loses the run with exit 1 and no checkpoint — the pause machinery does not cover the PRE-LOOP stages, which is phase-2 territory but should be a filed follow-up; (2) `set_capture_dir` is a process-global set per `_execute` call; (3) the no-progress guard bounds a stuck run, not a slow one, by design; (4) `run approve` validates its pacing flags before printing the shortlist.
Task 7: review pair dispatched (Opus x2) over 42d90a4..980e02b, 4 commits. Meter at dispatch: 5h 57%. Quality reviewer told to mutate the loop's unprocessed bookkeeping specifically, to go BEYOND the implementer's own 14 mutants rather than re-run them (a mutation set authored by the agent that wrote the tests shares their blind spots), and to use a timeout because a known mutation in this area hangs rather than fails. Spec reviewer asked to adjudicate the two deliberate departures from the brief's literal code.

Task 7: spec verdict ✅ PASS (task-7-spec-verdict.md, sha256 39e6f2a90b6639e5b5ba59340e497fb5d1a1a1eb98240509ed35a14df4674934) — 1 Important (needs a ruling, not code), 4 Minor. Both deliberate departures ADJUDICATED JUSTIFIED, and verified by execution rather than reading: `sleep_until(naive)` really does raise, and `format_delta(7200) == '2h 0m'` while `parse_duration('2h 0m')` really does reject. Catch ordering, no-limit-in-failures[], max_wait as the gate, all three flags on all three commands with eager validation, Ctrl-C clean checkpoint, and `_session_json` all confirmed. The clock is read as `_pacing._now()` — the import-time rebinding trap is avoided. No scope creep.
Task 7: quality verdict Changes requested (task-7-quality-verdict.md, sha256 b8f8aff086d3f2c84f9ff83ac66dc012cf49cfbdc7f62fe63a5f106c17b689dc) — 3 Important (one filed-not-a-regression), 10 Minor. **70 mutants: 54 KILLED, 14 SURVIVED, 1 INVALID, 1 HANG.** Tree verified empty at finish; suite 1736.
Decisive result: **every mutation on the known-dangerous list is DEAD** — `pending[idx+1:]`, `deferred[idx+1:]`, the `if limited:` check back at the top of the body (the original R1 defect verbatim), dropping `unprocessed.extend(deferred)`, removing AND inverting `stalled`, reordering `except RateLimited`, appending the limit to `failures[]`, the import-time `_now` rebinding, and the `pace.wait`/`max_wait` boundary. R1/R2/R3 are pinned. All 14 survivors are OUTSIDE the implementer's own 14-mutant set, which is exactly why the dispatch told this reviewer to go beyond that list rather than re-run it.
The reviewer also drove `_execute` through eight uncovered scenarios (limit on the last first-pass entry with a lock-deferred show, on the only entry, in the deferred pass, on the last deferred entry, failure+limit on both branches, held+limit, alternating refuse/succeed): no show dropped, none processed twice, all terminated. It confirmed the pause happens OUTSIDE `file_lock` — so a multi-hour sleep does not block other llama processes on that show — and that `resume_after` is display-only, so nothing naive can reach `sleep_until`.
Sharpest structural lesson from it: mutant P19 (`limited` never cleared) HANGS rather than fails, and the reason matters — `stalled` is NOT the termination bound. Termination rests on `limited = None` plus entries leaving the queue only by completing. Anyone later "simplifying" the guard should know it is not what stops the loop.

## OPEN — Task 7 findings recorded but NOT fixed

Per the coordinator's standing rule for this window, the meter was read before starting a fix round: **5h 69%, at or above the 65% gate, so NO fix round was started.** Findings recorded here instead; Task 8 also not started. Tree clean, suite 1736 passed / 7 deselected, nothing in flight.

Two Important pins for the fix round (both test-only; the shipped code is correct):
1. `cli.py:341` — `mark_paused(…, failures, …)` is unpinned: replacing `failures` with `[]` leaves the whole suite green. Reachable (a run loses a show to a real error, then pauses) and it destroys the only durable record of why. Needs a test with BOTH a failure and a pause.
2. `cli.py:328` — two of three terms in the no-progress guard are unpinned: dropping `held` or `len(failures)` from `done_now` both survive. Either causes a PREMATURE CHECKPOINT, which is the same operator-visible harm as a dropped show.

Ruling R20 (spec "Rendering a pause" row 3 — annotate as phase 2, do NOT change the exit code): the spec's third rendering row says "no show has run yet -> refuse to start, exit non-zero", and phase 1 does the opposite (limit on the very first show checkpoints and exits 0, pinned by test). Ruling: the row describes REFUSING TO START, which requires knowing before starting — that is the pre-flight check, and pre-flight pacing is explicitly phase 2. Phase 1 can only discover a limit by attempting a show, and at that point the session is checkpointed, resumable, and on the attention list, so exit 0 is not a false success claim. Decisive: the spec ITSELF requires exit 0 for the Ctrl-C checkpoint "so an interrupted wait resumes with exactly the same command as a planned one" — making the near-identical first-show case exit non-zero would contradict it, and would make unattended `--auto` runs look failed when they are merely paused. Action: amend the spec row to mark it phase 2, no code change. — Cost if wrong: an operator scripting on exit codes cannot distinguish "paused having done nothing" from "paused having done some" without reading the marker, which `run list --json` now exposes anyway.

Ruling R21 (spec doc drift, amend): the spec's "`max_wait` is the **single** mechanism governing whether a pause is waited out. No rule overrides `--wait`" is now false — the approved no-progress guard is a second gate. The code is right and the guard is deliberate; the sentence is stale. Amend it so a future reader does not delete the guard in good faith. — Cost if wrong: none, it is a doc correction.

Ruling R22 (fold the spec-reviewer's Minor into the fix round): `cli.py:356-357` prints `exceeds --max-wait 6h 0m` one line above a copy-pasteable `--max-wait 26h13m`. `6h 0m` is exactly the string `parse_duration` rejects, printed directly after the flag name — the very hazard `duration_arg` was created to remove, reintroduced one line up. Use `duration_arg` there too. — Cost if wrong: trivial.

Deferred Task 7 minors for the final whole-branch review: `cli.py:334` `<=` boundary unpinned; `pacing.py:106-107` `reset_skew`/`unknown_reset_wait` exercised only at defaults; `cli.py:349` hint-suffix condition unpinned; `cli.py:265` `--no-pacing`'s FAILED line unpinned; `pacing.py:47` `duration_arg` floor unpinned; `pacing.py:105` `""` treated as "flag not given"; `cli.py:180` `pace=None` default unpinned; `cli.py:337` vs `:568` print the same instant local-vs-UTC; `pacing.py:126` fallback is scope-blind so a `seven_day` pause records a wrong `resume_after`; `test_pace_loop.py:236,246` vacuous `assert held == {"b"}`.
FILED FOLLOW-UP (both reviewers, independently): a `RateLimited` from `interpret`/`search`/`winnow` still loses the whole run — exit 1, no marker. Identical to pre-change behaviour, out of Task 7's scope, and phase-2 territory since the fix is the pre-flight check. Should be filed rather than left implied.

## PARKED (fourth park) — Task 7 reviewed, findings open

NEXT, in order: (1) Task 7 fix round — the two Important pins, R22's `duration_arg` fix, and the R20/R21 spec amendments; (2) scoped re-review; (3) Task 8 (mutation pass + docs, carrying the __pycache__ hazard, the openrouter 429 caveat, the mutation-5 exit-code check, and the EVIDENCE NOTE above); (4) final whole-branch review.
Task names used and now single-use: t1 t2 b34b b56 t7, t1spec t1qual t2spec t2qual b34bspec b34bqual b56spec b56qual t7spec t7qual, t1fix1 t2fix1 b34bfix1 b56fix1, t1rr1 t2rr1 b34brr1 b56rr1.

## RESUMED for one unit — Task 7 fix round + scoped re-review, then park

Coordinator lifted the 65% fix-round gate FOR THIS DISPATCH ONLY (it existed to protect Task 7's headroom, and Task 7 is landed). Hard stop 92%. Task 8 explicitly NOT to start — and the reason is worth recording, because it is a hazard class nothing else in this plan has: **Task 8 killed mid-cycle leaves a deliberately-broken source file in the working tree, indistinguishable from ordinary work-in-progress.** Every other task's worst case is an unfinished edit; Task 8's worst case is a sabotaged one that looks finished. It must run attended, in a window with room to complete.
Meter at fix dispatch: 5h 72%. Fix round resumed the ORIGINAL Task 7 implementer (Opus), task dir t7fix1.

Ruling R20 RATIFIED with a condition (author): the phase-2 annotation must state the ALTERNATIVE and why it was deferred, not merely that it was. The author's point, recorded because it is the stronger half of the argument: a cron-driven run that packages nothing and exits 0 is indistinguishable from a successful no-op, which is a real operational problem rather than an oversight. It loses today only because the spec itself mandates exit 0 for the Ctrl-C checkpoint "so an interrupted wait resumes with exactly the same command as a planned one", and the first-show case is near-identical. Phase 2 revisits it deliberately.
Ruling R21 RATIFIED (author): the "single mechanism / no rule overrides --wait" sentence is the author's own and is now false; the no-progress guard is a second gate. Amend so nobody deletes the guard in good faith on the strength of the spec.
Ruling R22 RATIFIED AND WIDENED by the author, and the widening is the better fix: rather than only changing the printed string, **`parse_duration` now tolerates internal whitespace so `6h 0m` parses** (humans type spaces; the hint is meant to be pasted), **plus a ROUND-TRIP PROPERTY TEST** that `parse_duration(format_delta(x))` succeeds and round-trips to the same minute across a spread of durations. Fixing the printed string closes the instance; the round-trip closes the class. Constraint carried into the dispatch: this must not weaken the `$` anchor a previous review specifically pinned — `"6h banana"`, `"5h30m!"`, `"6s30m"`, `""`, `"6"`, `"-2h"`, `"6x"` and a whitespace-only string must all still raise. — Cost if wrong: a looser duration grammar accepts a form nobody intended; bounded by the retained rejection tests.

## HARD RULE FOR TASK 8 — put this in its dispatch VERBATIM

**Never mutate a file that has uncommitted work in it.** Task 7's implementer hit this: its first proof run ended `RESTORED -> 3 failed`, because the `parse_duration` fix was still uncommitted when the mutation script ran, so `git checkout --` reverted the mutation AND the fix together. It was caught only by the bracketing RESTORED run — nothing else would have shown it.

Task 8 is nothing but mutate/restore against files that may have just been edited, so the dispatch must require, in order:
1. Commit (or stash) everything first.
2. Confirm `git status --porcelain` is EMPTY before the first mutation.
3. Bracket the entire mutation set with a BASELINE run and a RESTORED run, and treat any discrepancy between them as an instrument failure rather than a finding.

The reason this outranks the `__pycache__` hazard: a stale `.pyc` produces a wrong RESULT, which is bad but visible as an implausible number. A restore that silently reverts real work produces a **plausible tree** — the suite is green, the files look finished, and the work is simply gone. That is the worse failure because nothing downstream looks wrong.

## STATED PHASE-1 LIMITATION — the run-level stages are unprotected (author-owned, do NOT fix tonight)

A `RateLimited` raised during `interpret`, `search` or `winnow` escapes `_execute` entirely: exit 1, no checkpoint, no `paused` state, no resume time. The operator sees a failure, not a pause. Both reviewers found this independently and both correctly scoped it out of Task 7.

**The spec is actively misleading about it, and that is the part to fix in Task 8's docs step.** The design says the pre-flight check "covers the opening burst that show-boundary checks would miss" — winnow's `light_research` once per shortlisted candidate and its batched `score_reviews`. But that pre-flight check IS the proactive gate, which is phase 2. Phase 1's reactive path wraps only `process_show`, so the entire opening burst is unprotected while the spec reads as though it is not. Amend the spec to say plainly: **in phase 1, a limit during the run-level stages fails the run; only the per-show loop pauses.**

This is real scope, not a typo. It belongs to a follow-up task or phase 2, and it is to be written down accurately rather than closed in a hurry. It goes into Task 8's spec/CLAUDE.md step ALONGSIDE the openrouter 429 caveat — the two are the same shape: a stated boundary of what phase 1's guarantee actually covers, one by backend and one by pipeline stage.

Noted for later, explicitly NO action: the `_checkpoint(when, scope, reason)` closure that would stop the two `mark_paused` call sites drifting. Good instinct — the second call site is exactly what the mutation found unpinned — but it is a refactor, and refactors do not land at the end of a window.
Task 7: fix round 1/5 (5 items addressed, 0 open; commits 3578fcb code + 8c98dc8 spec, kept separate as required). Suite 1736 -> 1741 passed, 7 deselected. Fix round ran on the ORIGINAL Opus implementer. 7 mutants applied, all 7 KILLED, bracketed by BASELINE and RESTORED runs, __pycache__ cleared each cycle, 180s timeout on every run.
Notable: item 1 had a SECOND unpinned call site the finding did not name — the same `failures` argument inside the `except KeyboardInterrupt` block. Its mutant SURVIVED the first pass and was closed by rewriting the existing interrupt test's fixture so a real failure precedes the pause. A finding that names one line is not a bound on the defect.
Item 5a implemented as a `re.sub` on whitespace BEFORE the match, so the `$` anchor is byte-identical rather than relaxed — and an extra mutant (F5a2) exists specifically to prove the anchor's tests still bind if someone later "fixes" this by loosening the regex instead. `format_delta` kept in the prose (it parses now) and `duration_arg` kept on the copy-pasteable command, where the load-bearing property is rounding UP rather than spacing.
Task 7: re-review PASS (task-7-rereview-1.md) — all five items ADDRESSED, all three scrutiny points confirmed by the re-reviewer's own mutations rather than by reading: both mark_paused call sites independently pinned, the anchor confirmed untouched, and the round-trip test confirmed to target `format_delta` and not a relabelled `duration_arg` test. No new Critical/Important breakage. Tree clean before, during and after.
Task 7: complete (commits 42d90a4..8c98dc8, review clean, 11 minors deferred)
Task 7 dispatches: implementer Opus; spec-compliance reviewer Opus; code-quality reviewer Opus (70 mutants); fix round 1 resumed the same Opus implementer; scoped re-review Sonnet.
Task 7: minor (deferred, new in the fix diff): the blanket `re.sub(r"\s+", "", ...)` strips whitespace ANYWHERE, so `"6 h"` and `"  6 h 5 m  "` parse too — wider than required, values still correct, no required-to-reject case violated.

## PARKED (fifth park) — Tasks 1-7 all complete and reviewed clean

Meter at park: 5h 79%, resets Sep 5 02:10 EDT, hard stop this window was 92%. Tree clean, suite 1741 passed / 7 deselected, nothing in flight. The user has not decided whether to resume at the reset, so nothing is queued past this point.

DONE AND REVIEWED CLEAN: Tasks 1, 2, 3, 4, 4b, 5, 6, 7. Branch spans 9f4440e..8c98dc8, 15 commits.
REMAINING: **Task 8 only** (mutation pass + docs), then the final whole-branch review.

Task 8's dispatch must carry, all already written up in this ledger:
 - the HARD RULE FOR TASK 8 section (commit first, prove `git status --porcelain` empty, bracket with BASELINE/RESTORED) — verbatim;
 - the `__pycache__` false-red hazard;
 - the mutation-5 exit-code check (exit 1 = tests ran and failed, vs exit 4 = collection error) and the corrected `test_stage_gather.py` path;
 - the EVIDENCE NOTE (the two findings that justify the mutation rule);
 - the STATED PHASE-1 LIMITATION section (run-level stages unprotected) for the spec/CLAUDE.md step;
 - the openrouter 429 caveat for the same step.
Task 8 also carries a hazard no other task has: killed mid-cycle it leaves a deliberately-broken source file in the tree looking like ordinary work-in-progress. It must run attended, in a window with room to finish.
Task names used and now single-use: t1 t2 b34b b56 t7, t1spec t1qual t2spec t2qual b34bspec b34bqual b56spec b56qual t7spec t7qual, t1fix1 t2fix1 b34bfix1 b56fix1 t7fix1, t1rr1 t2rr1 b34brr1 b56rr1 t7rr1.

## RESUMED — Task 8, then the final whole-branch review. Aim to finish the phase.

Window reset: 5h 3%, resets 07:10 EDT; weekly 19%.

Ruling R23 (STANDING, supersedes every earlier stop band — user's explicit instruction): the fixed stop bands (60/70/75/88/92%) are REPLACED by a per-dispatch fit test, `level + estimate*1.5 < 100`. Below 70%, dispatch without deliberation; at or above 70%, caution rather than stop — prefer smaller units, read the meter between EVERY dispatch, and do not begin a unit whose likely fix round would be forced past the wall. The old model was wrong in a measurable way: it parked three times with 15-30 points unspent, and unused capacity evaporates at the reset. — Cost if wrong: a dispatch lands closer to the wall than a fixed band would have allowed; bounded by the 1.5x margin.

Ruling R24 (ABSOLUTE, budget-independent): never START a mutation cycle that cannot be finished. A killed mutation agent leaves deliberately-broken source in the tree that looks exactly like ordinary work-in-progress. This is a CORRECTNESS rule, not an economy one — it binds at 10% as hard as at 90%, and it is the one rule the fit test does not override.

Task 8 dispatched (Sonnet). Meter at dispatch: 5h 3%; fit test 3 + 10*1.5 = 18 < 100, comfortable. Task dir t8.
**Caught before dispatch: `task-8-brief.md` was STALE and still contained the `test_gather.py` path.** The brief was generated after the ecd2fc1 amendment but BEFORE the 19a4aa9 path fix, so `scripts/task-brief` had cached the defective text. Regenerated and verified the corrected `test_stage_gather.py` path is present at brief line 51 before dispatching. This is a generated-artifact staleness trap worth remembering: fixing the plan does NOT fix briefs already extracted from it, and the one place it would have bitten is the exact step whose expected outcome is a failure.
Dispatch carried all four non-negotiables verbatim: commit-first + BASELINE/RESTORED bracketing (with the reason it outranks the pycache rule), __pycache__ clearing, the mutation-5 exit-code-1-not-4 assertion, and the two phase-1 boundary statements for the docs step. Mandate 3 was strengthened for this task specifically: if a takeover flag appears mid-mutation, RESTORE THE FILE FIRST, then report.
Task 8: DONE (commit a17b647 docs; plus my follow-up 8ac1e3c correcting the plan). BASELINE and RESTORED both **1741 passed, 7 deselected** — instrument sound, no discrepancy. All 5 mutations KILLED (red is the pass condition; no unpinned constraint found). Implementer Sonnet. Meter after: 5h 9%.

**Ordering check — the concern was raised, and the log clears it.** The coordinator observed `M CLAUDE.md` and `M docs/workflow.md` uncommitted and flagged the hard rule. Verified against the teed log rather than the report's own claim: BASELINE 02:15:04, mutations 1-5 ran 02:15:32 -> 02:18:20, RESTORED (pre-docs) 02:18:29, docs edited only afterwards, commit 02:20:58. So the ENTIRE mutation set ran on a clean tree, and `git status --porcelain` was empty at start and again after the pass. The observation was a true sighting sampled during the docs-writing phase, not an ordering violation. Recording the distinction because "the rule was honored" and "the tree looked dirty at some moment" are both true and only the first matters.

**Second plan defect found in this same task, same class as the first.** Mutation 1's literal command `-k rate_limit` over `packages/llama/tests` selects exactly ONE test — `test_stage_gather.py::test_gather_rate_limit_during_llm_alignment_propagates_and_does_not_flag`, which is mutation 5's target and is unaffected by the cli.py catch ordering. It passes. Since the step's expected outcome is a FAILURE, a green run reads as "constraint not pinned": a false ALARM. The constraint is genuinely pinned — 17 of the 48 tests in `test_pace_loop.py` + `test_sessions.py` fail under the mutation. The implementer caught this itself, ran the correct files, and flagged the brief rather than silently substituting. I verified the selection independently (`--collect-only` -> `1/1311 tests collected`) and corrected the plan in 8ac1e3c.
The generalization now recorded in the plan: **a command whose expected result is a failure must be checked for selecting the RIGHT tests, not merely for failing.** Both directions are wrong in the same way — a run that fails for the wrong reason certifies nothing, and a run that passes for the wrong reason alarms on nothing. Two instances in one task (the `test_gather.py` path, and this) is the evidence that this step needed the exit-code and selection checks the dispatch demanded.
Task 8 docs: both phase-1 boundaries landed and verified present by grep — the openrouter 429 gap and the interpret/search/winnow gap, in the spec and CLAUDE.md, plus docs/workflow.md.
Task 8: complete (commits 8c98dc8..a17b647, mutation pass clean, 5/5 killed)
Final whole-branch review dispatched: both Opus, over 9f4440e..8ac1e3c (22 commits, 171787 bytes). Meter at dispatch 5h 9%; fit test 9 + 30*1.5 = 54 < 100. Task dirs finalspec, finalqual. Both were handed deferred-minors.md (extracted from this ledger with prior verdicts stripped) and told to rule on EVERY item — fix-before-merge or deliberate — and to name anything merge-blocking. Quality reviewer aimed at whole-branch seams only (cross-module RateLimited seam, the end-to-end promise, interfaces built and never consumed such as pause_scope, PacingConfig.enabled) rather than re-running per-task mutations.

Ruling R25 (PROCESS ERROR, mine — record so it is not repeated): I dispatched the final spec reviewer (read-only) and the final code-quality reviewer (mutating) IN PARALLEL against the same checkout. The spec reviewer observed the quality reviewer's transient mutations twice — `pacing.py` `enabled=cfg.enabled` -> `enabled=True`, then `gather.py` — self-reverting within seconds, and correctly identified them as another agent's rather than its own. Its own suite run completed BEFORE the mutation pass began, so its verdict stands; but that was luck of ordering, not design. The sdd-delegation skill names this exactly: "a reader sharing a worktree with a mutating agent is a hazard", and the subtle failure is that a mutate-and-restore window makes the file briefly wrong and correct again, so a start-and-end hash check passes on both samples while anything imported inside the window measured mutated code. I had run every previous review pair in parallel safely only because none of the SPEC reviewers ran a suite while the quality reviewer mutated. Correct pattern for any future pair: run the mutating reviewer alone, or give the reader a materialized snapshot (`git archive <commit> <path>` into a separate directory). — Cost of the error here: none observed, and the spec reviewer's self-report is what makes that assessable rather than assumed.

## FINAL WHOLE-BRANCH REVIEW

Final spec verdict: **✅ PASS** (final-spec-verdict.md) — every phase-1 commitment delivered, 8 Minor findings, none Critical/Important, none merge-blocking. Both late-added limitations verified TRUE AGAINST CODE rather than prose: `openrouter.py:36-37` raises a bare HerderError on any non-200 and calls `classify` nowhere; `run_discover`/`run_search`/`run_winnow` are called bare with no pre-flight, so a RateLimited there reaches `main_cli:2643` -> `error:` -> exit 1 with no marker. It also re-audited every broad `except` on the `_execute` path independently and confirmed the four `except Exception` sites contain no provider call.
Final quality verdict: **Changes requested** (final-quality-verdict.md) — 2 Important, several Minor, ~a dozen lines, no behaviour change. **28 mutations, 25 KILLED, 3 SURVIVED (89%)** — materially better than this branch's earlier rounds (7 and 22 survivors), and the kills land on tests whose names describe the mutated arithmetic.
Coherence verdict worth recording: it reads as ONE designed feature, not eight tasks stapled together — module per concern, one `_pace` helper giving three commands an identical flag block, herder->llama direction clean, and no phase-2 leakage (EWMA, usage cache, percent thresholds, fixed rail, `llama pacing` all grep-confirmed absent).
Notable non-finding, and the honest one: **the end-to-end promise is proven by composition, not by any single test.** Neutering `classify` kills 7 tests, ALL herder-side — no llama test notices, because the end-to-end fixtures inject a constructed `RateLimited` at the provider object rather than letting `claude_cli` classify raw text. The reviewer could not construct a whole-path break that stayed green, and every link is separately pinned, so it filed the ~15-line seam test as a Minor rather than a blocker. Recording it because "each hop is pinned" and "the path is pinned" are different claims and only the first is true.

Both reviewers independently reached the SAME three fix-before-merge items (the gather comment, the spec's cli.py:2505 misattribution, the dead herder export), which is the strongest signal available that they are real.
Final fix wave dispatched (Sonnet, ONE wave for all findings per the skill — not one fixer per finding). Meter at dispatch 5h 17%; fit 17 + 15*1.5 = 40 < 100. Task dir finalfix. Seven items: gather comment (Important), pin RateLimited's base class (Important), delete the dead herder re-export, remove the dead pace default, and three doc corrections (spec audit note, spec status header, run list docstring). Everything else on the deferred list was triaged 'deliberate, leave it' by BOTH reviewers and explicitly fenced off in the dispatch.

## Ruling R26 — the most important lesson of this run. A SURVIVING MUTATION MEANS "UNTESTED", NOT "UNREACHABLE".

Final-review item 4 asked to delete `cli.py:180-181`'s `if pace is None: pace = pace_options(config)` and make the parameter required. The premise, stated independently by BOTH Opus final reviewers, was "all four call sites pass a resolved `PaceOptions`", resting on mutation M27 having SURVIVED (making the branch raise left the suite green at 1741).

**The premise was false and I verified it myself rather than taking the fixer's word.** `grep -n '_execute(' packages/llama/src/llama/*.py` returns **five** call sites, not four. The fifth, `_redo_run_level` at `cli.py:2055`, does NOT pass `pace=` — it relies on exactly that default. Making the parameter required would have raised `TypeError` on `llama redo --run`, a real user-facing command.

And the suite would have stayed GREEN while shipping it, because M27 surviving is precisely the evidence that **no test covers `redo --run`'s pacing path**. Both reviewers read "the mutation survived" as "the branch is dead" when it actually meant "nothing tests this branch". Those two readings are opposite in consequence: one says delete the code, the other says the code is the only thing holding an untested path up.

This inverts the rule the whole run has leaned on. Mutation testing has been the most valuable instrument here by a distance — 7, 22 and 3 survivors found across the phase, and two shipped-but-unpinned features. But a survivor is a statement about the TESTS, never about the CODE. Reading it as dead code is how a green suite ships a crash.

Credit where due: the fix-wave implementer was told to verify item 4's claim before acting, did so, found five call sites, and DECLINED the item rather than following two Opus reviewers off a cliff. The instruction to verify before acting is what saved it; without that line it would have made the change and every gate downstream would have passed.

Backlog item this exposes: `llama redo --run` has no test coverage of its pacing path at all, and no `--wait`/`--max-wait`/`--no-pacing` flags either (the spec claims three commands funnel into `_execute`; there are five call sites and four funnels). Filed, not fixed.

Final fix wave: 5 commits, 6 of 7 items applied, item 4 correctly declined. 8587499 (gather comment), f67a6d2 (pin RateLimited's base class, +1 test), a72e42f (drop the dead re-export), a8349d5 (run list docstring), 8ab8dd7 (spec status line + stale audit note). Suite 1741 -> **1742 passed, 7 deselected**. Tree clean.

## FINAL RE-REVIEW: PASS — PHASE COMPLETE

final-rereview.md: 6 of 7 items ADDRESSED and verified TRUE OF THE CODE (not merely changed); item 4 CORRECTLY DECLINED, independently confirmed. No new breakage, scope held to 5 files, tree clean before and after, suite 1742.
The re-reviewer independently reproduced item 2's RED/GREEN, grepped `packages/` itself for item 3's dead export, enumerated all 5 `_execute` call sites itself for item 4, and checked items 5's corrected line numbers against the working tree. It also answered the R26 question correctly and unprompted: the branch is REACHABLE via `redo --run`, so the surviving mutation means no test covers pacing on that path — and it proved it (`test_redo_cmd.py` has zero `RateLimited` references, `test_pace_loop.py` has zero `redo` references).
One flagged imprecision, no code change, worth carrying to the backlog: gather.py's new comment says a limit is "not recorded as a per-show failure", which is true only when `pace.enabled`. The `if not pace.enabled:` branch at `cli.py:264-267` still records one. Accurate for the default path, incomplete for `--no-pacing`.

WORKSPACE IS NOT DELETED. The SDD skill says to delete it when the final review is clean AND its fixes are merged; nothing is merged, and the coordinator owns ratification, merge, tag and push. The verdicts and their hashes are the ratification evidence and must outlive this session.
**Warning for the coordinator: `.superpowers/` is gitignored.** This entire ledger, every verdict file and every hash lives outside git. A `git clean -fdx` destroys all of it. If any of it should survive, copy it into the repo proper before cleaning.
