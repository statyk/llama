# Task 6 — CODE-QUALITY review

**Verdict: Approved.** The change is correct, minimal, and its region boundaries are
pinned where they are observable. Two Important findings below are one-liners that
should land before merge; nothing Critical.

## Sweep verification (independent, not accepted from the report)

Private copy at `$D/work/t6-quality/repo`, shadowed by `PYTHONPATH` over the worktree's
venv and **proven** by a planted `MUTATION_SENTINEL_T6Q` reading back `'copy'` with
`llama.cli.__file__` resolving under the copy. Guards: `rsync --delete` + `cmp`
byte-identity before every mutant, green-baseline assertion requiring `passed` in the
summary line, `NO-OP-MUTANT` and `ANCHOR-NOT-UNIQUE` assertions, `python -B
-p no:cacheprovider`, `PYTHONDONTWRITEBYTECODE=1`, `__pycache__` cleared per run,
`</dev/null` everywhere. Scored against the whole `packages/llama/tests` dir
(1347 passed, 6 s baseline), not just the touched file. Worktree `git status` clean and
untouched after the sweep; copy restored byte-identical.

Three of my own mutant generators produced SyntaxErrors or an unintended mutant on first
try and were scored `CAUGHT-ERROR`/investigated rather than banked — m12/m13/m14 needed
line-wise re-indentation, and my first `r04` silently re-indented the `if not shortlist:`
block into the *handler* body rather than the try body, which is a different mutant
entirely. All were re-run correctly.

**All 17 of the implementer's mutants reproduce: 16 CAUGHT, m15 SURVIVED.** The report is
accurate. (Failure counts differ slightly from the report for m01 — 5 not 7 — because my
arm-reversal inserts a re-raising `except HerderError` rather than whatever shape the
implementer used; verdict is the same.)

**m15 equivalence adjudicated and upheld.** `sessions._write` normalizes at
`packages/llama/src/llama/sessions.py:28` (`"failures": failures or []`), and
`mark_paused` (`sessions.py:59-67`) passes straight through with nothing in between. I
re-ran the mechanical proof myself under the copy: both spellings produce byte-identical
JSON with `updated_at` removed. No observable state distinguishes them; genuinely
equivalent, correctly not chased.

**13 additional mutants of my own.** CAUGHT: note→stderr, `paused:`→stdout,
`mark_paused`→`mark_incomplete`, `if not pace.wait` instead of `pace.enabled`,
`when.isoformat()`→`str(when)`, `raise typer.Exit(1)` after checkpointing, dropping the
`note=` kwarg at the call site, `raise`→`return` under `--no-pacing`. SURVIVED:
`when is not None` (equivalent — datetimes are always truthy), `getattr` default
(finding 3), `str(limited)`→`repr(limited)` (finding 2), and extending the try over the
`if not shortlist:` block (finding 0 — **the implementer's Concern 2 is honest**; I
confirmed that boundary is genuinely unobservable, so declining to manufacture a test for
it was the right call).

## Control-flow checks (all pass)

- `try` starts at `artists = None` and closes immediately after `run_winnow` — the
  `if not shortlist:` / `_print_shortlist` / `plan` / `choose_entries` region is outside,
  correctly.
- `mark_complete`/`return` paths *inside* the region (`cli.py:228`, `cli.py:240-241`) are
  not swallowed or double-handled: neither `typer.prompt` nor `mark_complete` can raise
  `RateLimited`, and a `return` from inside a `try` with only an `except` (no `finally`)
  exits cleanly. `test_get_fuzzy_query_interactive_prune` and
  `test_empty_winnow_still_marks_complete` cover both and stayed green.
- No interaction with `_process`'s `except (TaskFailed, HerderError, IAError)`
  (`cli.py:315`): the new try closes before the show loop, and `_process` catches
  `RateLimited` first itself.
- `return` after checkpointing leaves a consistent session: **all five `_execute` call
  sites** (`cli.py:445, 462, 669, 703, 2097`) do nothing after it returns, so the paused
  marker is the last write and the process exits 0.
- `--no-pacing`: bare `raise` re-raises unchanged; `RateLimited` subclasses `HerderError`
  so `main_cli` (`cli.py:2682`) prints `error: <msg>` and exits 1 — the test docstring's
  claim is accurate. Pinned by `test_pacing_disabled_lets_a_run_level_limit_propagate`
  and by two mutants (drop the guard, invert it).
- `when` that already includes skew vs one that does not: `when or resume_at(...)` is
  correct in both directions and pinned by m07/`test_checkpoint_pause_keeps_a_precomputed_instant_verbatim`.

## Findings

**Important**

1. **`run_interpret` still escapes, and the commit subject says otherwise.**
   `cbaad44`'s subject is *"a limit during interpret/search/winnow now checkpoints"*, but
   `run_interpret` runs at `cli.py:431` (and again at `cli.py:2547`) **before** `_execute`
   is called and is not wrapped; meanwhile `run_discover`, which *is* covered, is not
   named. The note text at `cli.py:262-263` ("limit hit before any show ran") inherits the
   over-claim. The implementer flagged this as Concern 3 and correctly did not widen
   scope. Not wrapping it is defensible on the merits: `run_interpret` writes
   `criteria.json` only on success (`stages/interpret.py:13`), and `run resume` refuses a
   session without one (`cli.py:700-702`), so a checkpoint there would be unresumable.
   **Suggested change:** reword the subject to *"a limit during discover/search/winnow now
   checkpoints"*, and add one line at `cli.py:431`:
   `# run_interpret is deliberately outside the pause region: it writes criteria.json`
   `# only on success, and run resume refuses a session without one.`
   Worth also correcting `CLAUDE.md`'s phase-1 note, which calls `run_discover`
   "interpret" and is the source of the confusion.

2. **`pause_reason`'s content is asserted by substring, and a real mutant survives it.**
   `test_pace_loop.py:416` and `:522` both assert `"session limit" in
   marker["pause_reason"]`. Changing `cli.py:196` from `str(limited)` to `repr(limited)`
   **survives the whole suite** — the operator-facing reason could become
   `RateLimited("You've hit your session limit")` with nothing noticing. The exact string
   is available; use it.
   **Suggested change:** at `test_pace_loop.py:522`,
   `assert marker["pause_reason"] == "You've hit your session limit"`.

**Minor**

3. `cli.py:196` — `getattr(limited, "scope", None)`'s default is unreachable:
   `RateLimited.__init__` always sets `self.scope` (`herder/limits.py:114-118`). Mutating
   the default to `"five_hour"` survives. Either annotate `limited: RateLimited` and use
   `limited.scope`, or add half a sentence to the docstring saying the `getattr` is there
   for Task 7's non-`RateLimited` caller. As shipped, `limited` is the one unannotated
   parameter in an otherwise fully annotated signature.

4. `cli.py:191` — `when = when or resume_at(limited, pace)` tests truthiness of a
   `datetime`. Equivalent today (datetimes are always truthy; mutant confirms), but the
   intent is "not supplied". Prefer `when = resume_at(limited, pace) if when is None else when`.

5. `cli.py:195` — `failures or []` is redundant given `sessions._write` already
   normalizes, and it differs from the loop's own call shape (`cli.py:400` passes
   `failures` bare). Harmless; drop it or keep it, but it is the source of the one
   surviving mutant and could just go away.

6. `test_pace_loop.py:462` — `test_run_level_ratelimited_is_caught_before_herdererror`
   promises more than its body checks. There is no `except HerderError` on that try, so
   the body (`search=_boom`, assert `STATE_PAUSED`) really pins "search is inside the
   region", duplicating m14's coverage. The actual ordering killer is
   `test_an_ordinary_stage_failure_is_not_turned_into_a_pause`, which is present and
   correct. Brief-verbatim, so leave the body; a one-line comment pointing at the real
   killer would stop a future reader trusting the name.

7. `cli.py:173-189` — the docstring says "the run-level pause sites" (plural; there is
   exactly one) and documents a `when=` caller that does not exist until Task 7. Three of
   six parameters (`outcome`, `failures`, `when`) have no production caller; `when` has a
   test-only one. Acceptable if Task 7 lands — if it does not, they are dead weight and
   should be deleted with the docstring paragraph.

8. `cli.py:192` vs `:193/:198` — the pause renders across two streams: `paused: <reason>`
   on **stderr**, note and resume hint on **stdout**. The per-show loop puts its entire
   pause block on stdout (`cli.py:381, 401`). Both streams are pinned by
   `test_a_run_level_pause_says_what_a_resume_will_redo`, so this is deliberate, but an
   operator piping stdout gets "resume with: …" with no statement of why. Suggest putting
   all three on the same stream.

9. There is no `CliRunner`-level test for the run-level pause matching phase 1's
   `test_sessions.py:346` (which pins `exit_code == 0` end to end). The property is
   transitively pinned — a `raise typer.Exit(1)` after checkpointing is CAUGHT, because
   the direct-drive tests require `_execute` to return normally — so this is symmetry, not
   a hole. Worth one test only if the orchestrator wants the pair to look alike.

## No findings on

Duplication with the per-show loop (R2's ruling is honored, and the docstring names the
reason rather than hand-waving); the "recoverable, not cheap" comment at `cli.py:254-257`,
which is accurate and earns its place; `_drive`'s two new overrides, which are exactly the
two the brief specified and nothing more; scope (two files, no proactive-gate or
openrouter bleed).
