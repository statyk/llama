# Phase B verdict-file audit — copy-based mutation testing shadow-defect

Read-only inventory of `/private/tmp/claude-501/-Users-shawn-projects-llama/e82f7960-4d8a-417d-83fc-8132225b6186/scratchpad/sdd-phaseb/verdicts/`
(62 files). No test was run, no file outside this report/log was written, and
`/Users/shawn/projects/llama/.worktrees/sibling-transfer` was never touched.

Legend: SOUND-S1 (`-m pytest`/direct interpreter), SOUND-S2 (`PYTHONPATH` at
the copy, no sentinel shown), SOUND-S3 (sentinel/`__file__` shadow proof),
IN-PLACE (mutate-and-restore inside the worktree — different hazard, not this
defect), UNVERIFIED (copy-based, no S1/S2/S3 evidence), INDETERMINATE (text
doesn't establish method at all).

## Table

| # | File | Claim | Invocation (verbatim) | Class | Reasoning |
|---|------|-------|------------------------|-------|-----------|
| 1 | `final-review.md` | **Whole-branch behaviour-preservation**: "1,639 items x 2 formats, 98,856 runs, 104,078 adoptions, 0 differences" for `adopt_gap_titles`'s extraction | Method stmt only: "All mutation work was done in a shadow copy at `scratchpad/work/finalrev/repo`, whose shadowing of the installed package was proved with a planted sentinel before any result was trusted: `module file: .../scratchpad/work/finalrev/repo/packages/llama/src/llama/correspondence.py` / `sentinel: FINALREV_SHADOW_OK`" | SOUND-S3 (qualified) | The file states the shadow copy used for the whole review was sentinel-proved and reproduced the exact baseline suite (1554 passed). The comparison script itself ("I imported the pre-branch `structure.py` ... and ran both ... over the real metadata cache") is never quoted as a literal command — no `PYTHONPATH=`/`-m pytest`/interpreter path is shown for *this specific* script, only prose. I classify SOUND-S3 on the strength of the file's blanket shadow-proof statement covering "all mutation work," but this is the one load-bearing claim where the exact invocation for the specific measurement is not independently quotable. |
| 2a | `c1-fix-report.md` | **C1 staleness guard**, end-to-end BEFORE/AFTER reproduction | "Shadow copy lives outside the worktree at `/private/tmp/.../scratchpad/work/c1before/` (extracted via `git archive 77e75b6 -- packages/llama/src/llama`), sentinel-verified before use (`SHADOW_SENTINEL_PREFIX` present only when `PYTHONPATH` points at it, and `inspect.getsource` on `_propose_titles_for_show` confirmed the C1 staleness check text is absent in that copy)" | SOUND-S3 | Sentinel + source-inspection proof, both before trusting BEFORE-state output. AFTER ran against the real worktree HEAD directly (not a copy) — no shadow risk there. |
| 2b | `c1-fix-report.md` | **C1**, unit-level mutation (guard block reverted in shadow) | "copied `packages/llama/src/llama/cli.py` (post-fix) to `/private/tmp/.../scratchpad/work/c1fix/llama/` ... planted a sentinel in `llama/__init__.py`, confirmed the shadow both via plain `python -c` and via `pytest` (both showed `cli.__file__` pointing at the shadow and the sentinel present)" | SOUND-S3 | Explicit dual confirmation (`python -c` and `pytest` both) that the shadow, not the worktree, is under test. |
| 2c | `final-rereview.md` | **C1**, independent re-verification | planted `SENTINEL_RRF` in the copy's `correspondence.py` -> printed `llama file:`/`corr file:`/`cli file:`/`herder file:` all under `.../work/rerevfinal/...` plus `SENTINEL: shadow-proof`. "(The editable installs in the worktree venv are plain-path `.pth` entries, so `PYTHONPATH` shadows them cleanly; no meta-path finder to fight.)" | SOUND-S3 | This is the file named in the task prompt as an "already-established data point" — confirmed accurate verbatim: it does print resolved `__file__`s under the copy, does record `SENTINEL: shadow-proof`, and does give the plain-path-`.pth` reasoning for why `PYTHONPATH` works here. Mutation on the guard (`if kept_names != track_names:` -> `if False:`) then shown red. |
| 3a | `c1-fix-report.md` | **I2 `runs[:1]` fail-open pin** | "Reverted `unresolved_runs` in a fresh shadow copy (`return runs[:1] # MUTATION`) at `/private/tmp/.../scratchpad/work/c1fix/llama/structure.py`, sentinel re-verified, `__pycache__` purged in both worktree and shadow" -> `FAILED ...test_every_unresolved_run_is_checked_not_just_the_first` | SOUND-S3 | Same shadow copy/sentinel apparatus as 2b, re-verified before this mutation. |
| 3b | `final-rereview.md` | **I2**, independent re-run | "Mutation re-run by me — `structure.py:1009` `return runs` -> `return runs[:1]`, caches purged" -> `FAILED ...test_every_unresolved_run_is_checked_not_just_the_first` | SOUND-S3 | Same sentinel-proved shadow copy as row 2c. Two independent SOUND-S3 confirmations of this exact pin. |
| 4a-i | `task-5-review.md` | Hollow-pin discovery #1 (JSON round-trip test never calls `propose_titles`) — **original discovery** | "Mutation experiments were run on **copies outside the worktree** (`scratchpad/review5-work/`)." ... "I copied `correspondence.py` outside the worktree and reverted just the row construction to the round-1 encoding ... Ran the shipped test file against it: **7 passed.**" | **UNVERIFIED** | No `PYTHONPATH`, no `-m pytest`, no sentinel, no `__file__` check anywhere in this file for the mutation work. Only a single source file is described as copied ("copied `correspondence.py`"), and it's never shown how the test run actually resolved that copy over the installed editable package. This is exactly the shape of run the audited defect targets. Does not mean the finding was wrong — see fix/reverify rows below, all of which independently reproduced the same conclusion under S2/S3. |
| 4a-ii | `task-5-report.md` | Fix round 3 self-verification of the same two mutations | "copied `packages/llama/src/llama/` to `/private/tmp/.../scratchpad/mutation-check/pkgroot/llama` ... ran the (also copied) test file against it via `PYTHONPATH=.../pkgroot ./.venv/bin/pytest .../test_correspondence.py -q`. Sanity check first: the unmutated copy reproduces 9/9 green" | SOUND-S2 | Per the audit's own S2 rule, `PYTHONPATH` pointing at the copy is sufficient here (plain-path `.pth` install). No sentinel was planted, only an "unmutated copy = 9 green" sanity check — the next reviewer (task-5-rereview.md) explicitly calls this insufficient to distinguish shadowing from silently testing the worktree, even though S2 alone technically qualifies as SOUND under the audit's stated criteria. Flagging the tension rather than resolving it silently. |
| 4a-iii | `task-5-rereview.md` | Independent re-verification of 4a-i/4a-ii, plus explicit critique of 4a-ii's proof standard | "Before running any mutation I proved pytest imports the scratch copy by planting a sentinel (changing the infeasible `reason` string in the copy only): that run went red ... The implementer's own sanity check (unmutated copy = 9 green) could not have distinguished shadowing from silently testing the worktree." | SOUND-S3 | Confirms both mutations still caught, with sentinel proof this time. This is the review that also *discovers hollow-pin #2* (see 4b-i below). |
| 4a-iv | `task-5-rereview2.md` | Further re-verification (round 4/5) | "Runner: the worktree's own `./.venv/bin/pytest` with `PYTHONPATH=$S/src`. ... that was proved, not assumed — via a deliberate sentinel in the *scratch* copy only — `evidence=\"filler\"` -> `evidence=\"SENTINEL\"` ... re-ran the same pytest invocation" -> `AssertionError: assert 'SENTINEL' == 'filler'` | SOUND-S3 | Clean S1+S2+S3 combination (`./.venv/bin/pytest` + `PYTHONPATH` + sentinel). |
| 4b-i | `task-5-rereview.md` | Hollow-pin discovery #2 (trichotomy pin filler-blind) — **original discovery**, "Mutation 3" | Same method stmt as 4a-iii above (sentinel proved before any mutation trusted) — "Mutation 3 (added by me, probing the I3 gap) — filler rows constructed with `forced=True` ... PASSES — 9 passed, NOT CAUGHT." | SOUND-S3 | Discovered under the same sentinel-proved shadow copy as row 4a-iii. |
| 4b-ii | `task-5-rereview2.md` | Fix verification for the trichotomy gap | Same PYTHONPATH+sentinel apparatus as row 4a-iv | SOUND-S3 | -- |
| 4b-iii | `task-8-report.md` | Trichotomy pin exercised again (`_format_proposal_row` refactor) | "planted `raise RuntimeError(\"SCRATCH_SHADOW_PROOF\")` at the top of the scratch copy's `_format_proposal_row`, then ran the trichotomy test against the scratch copy via `PYTHONPATH=<scratch>/packages/llama/src:<scratch>/packages/herder/src <worktree>/.venv/bin/python -m pytest tests/test_cli.py -q -k trichotomy`" | SOUND-S3 (also S1+S2) | Triple coverage: `-m pytest` form, `PYTHONPATH`, and a planted sentinel, all in one invocation. |
| 4c-i | `task-6-review.md` | Hollow-pin discovery #3 (`sibling_item_durations` body -> `return None`, 10 tests stay green) — **original discovery** | "All mutation work was done in a copy outside the worktree at `.../scratchpad/work/review6-mut/`, shadowed via `PYTHONPATH` ... **Shadowing was proved before any mutation was trusted**: a `raise RuntimeError(\"SENTINEL-SHADOW-PROOF\")` planted in the scratch `build_canonical` turned both new tests red with the traceback pointing at the scratch path, not the worktree." | SOUND-S3 | The file's Method section (stated once, up top) covers every mutation reported in it, including I1's `return None` result. |
| 4c-ii | `task-6-report.md` | Fix verification, mutation (a) `return None` re-run | "`cp -R packages/llama <shadow>/llama` into `$D/task6-work/mutation-shadow` ... `PYTHONPATH=\"<shadow>/llama/src\" ./.venv/bin/pytest ...` ... `raise RuntimeError(\"SENTINEL-SHADOW-PROOF\")` as the first line of the shadow copy's `sibling_item_durations`. Confirmed `import llama.correspondence` under the shadowed `PYTHONPATH` resolved to the shadow copy's file path (printed `c.__file__`)" | SOUND-S3 | -- |
| 4c-iii | `task-6-rereview.md` | Independent re-verification of 4c-ii | "`PYTHONPATH=<copy>/packages/llama/src <worktree>/.venv/bin/python -m pytest <copy>/packages/llama/tests -q -p no:cacheprovider`" + planted `SENTINEL-SHADOW-PROOF-CORRESPONDENCE`/`-GATHER` sentinels, both `__file__`-confirmed | SOUND-S3 (also S1+S2) | "I reproduced all of it independently (own copy, own sentinel in both modules) and every claim held." |
| 4d-i | `task-8-review.md` | Hollow-pin discovery #4 (A1's 3-line exclude filter deleted, MUT4) — **original discovery** | "**Shadowing proof first.** Copied `packages/` (not a git clone) to the scratch dir, planted `raise RuntimeError(\"SCRATCH_SHADOW_PROOF\")` at the top of the scratch copy's ... `PYTHONPATH=<scratch>/packages/llama/src:<scratch>/packages/herder/src` and cwd `<scratch>/packages/llama`. It failed with exactly that `RuntimeError`" -> "MUT4 | A1's three-line exclude filter deleted | **1099 passed, 1 skipped — nothing catches it.**" | SOUND-S3 | Shadow proved before the 1099-tests-pass result was trusted. |
| 4d-ii | `task-8-report.md` (Fix round 1, "I1 -- A1 is now pinned") | Fix verification for MUT4 | "planted `raise RuntimeError(\"SCRATCH_SHADOW_PROOF_A1\")` at the top of the scratch copy's `_propose_titles_for_show`, ran the new test via `PYTHONPATH=<scratch>/packages/llama/src:<scratch>/packages/herder/src <worktree>/.venv/bin/python -m pytest tests/test_cli.py -q -k drops_excluded`" | SOUND-S3 (also S1+S2) | Sentinel fails first (proving shadow), sentinel reverted, real mutation (delete 3-line filter) reapplied and reproduces the reviewer's predicted failure exactly. |
| 4d-iii | `task-8-rereview.md` | Independent re-verification of 4d-ii | "`import llama, herder` resolves to the snapshot's `packages/*/src` paths ... **Sentinel:** inserted `raise RuntimeError(\"SENTINEL_SHADOW_PROOF\")` as the first statement of `_propose_titles_for_show` in the *snapshot*. Six tests went red" -> mutation re-run: deleted 3-line filter -> `FAILED ...test_suggest_titles_drops_excluded_files_from_kept` | SOUND-S3 | Third independent confirmation of this pin. |
| 5a | `guard-report.md`, `m3-doc-report.md`, `m3-rerun-report.md`, `i3-strip-report.md`, `orchestrator-finish-report.md` | Suite/CLI runs used to support various PASS verdicts (accountability guard acceptance table, M3 gate re-run, footnote-strip differential, final suite counts) | e.g. "`cd /Users/shawn/projects/llama/.worktrees/title-correspondence` / `./.venv/bin/python scripts/footnote_strip_diff.py --selftest --out <workdir>`"; "`./.venv/bin/llama fix <slug> --suggest-titles --no-run </dev/null`" — all run directly in the worktree, no copy | IN-PLACE | These are not copy-based mutation tests at all — they execute the worktree's own console scripts against the worktree's own tree. Not exposed to the shebang/shadow defect (they carry the *different*, disclosed hazard of a concurrent reader, which none of these files report as a concern since nothing else was running against these worktrees at the time per each file's own `git status --porcelain` checks). |
| 5b | `sibling-diagnosis.md` | Diagnostic trace of `sibling_item_durations` returning `None` on 4/4 (background for Task 6, not itself one of the five, included for completeness) | "`PYTHONPATH=<work>/snap/packages/llama/src:<work>/snap/packages/herder/src /Users/shawn/projects/llama/.worktrees/title-correspondence/.venv/bin/python <work>/diag.py`" + `SENTINEL_MARKER` + `c.__file__` check | SOUND-S3 (also S1+S2) | Direct interpreter invocation, `PYTHONPATH`, and sentinel/`__file__` proof together. |

## Verdicts on the five load-bearing claims

1. **Whole-branch behaviour-preservation (1,639 items x 2 formats, 98,856 runs, 104,078 adoptions, 0 differences).**
   SOUND-S3, but with a caveat worth flagging to whoever relies on this the most:
   the file's sentinel proof (`FINALREV_SHADOW_OK`) is stated as covering "all
   mutation work" in that shadow copy, and the baseline-suite reproduction
   (1554 passed) is confirmed under it — but the comparison script that produced
   the 1,639/98,856/104,078/0 numbers is never itself shown as a literal
   command (no `PYTHONPATH=`, no interpreter path, no per-script sentinel
   check quoted). A re-verification, if anyone wants belt-and-suspenders on
   the single most important number in the phase, would need to: (a) find or
   recreate the comparison script, (b) confirm it loads the pre-branch and
   post-branch `structure.py` by explicit file path (e.g.
   `importlib.util.spec_from_file_location`) rather than by package import
   through `sys.path`/site-packages, which would sidestep the shebang defect
   entirely, or (c) re-run it with an explicit `PYTHONPATH`/`-m pytest`-style
   invocation and a planted sentinel the way every other measurement in this
   review does. As written, I do not downgrade this to UNVERIFIED — the
   file's own stated method is S3 for the copy it worked in — but it is the
   one claim where the specific invocation is not independently quotable.

2. **C1 staleness guard before/after.** SOUND-S3, doubly confirmed
   (`c1-fix-report.md` originally, `final-rereview.md` independently). No
   re-verification needed.

3. **I2 `runs[:1]` fail-open pin.** SOUND-S3, doubly confirmed
   (`c1-fix-report.md` and `final-rereview.md`, both with sentinel proof and
   `__pycache__` purge discipline). No re-verification needed.

4. **The four hollow-pin discoveries.** Three of the four (trichotomy,
   `return None`, exclude-filter/1099-tests) were SOUND-S3 from their very
   first discovery and remained SOUND-S3 through every fix and re-review. The
   fourth — the JSON round-trip pin — has an UNVERIFIED *original* discovery
   in `task-5-review.md` (copy-based, no PYTHONPATH/sentinel/`-m pytest`
   shown at all), but every subsequent step (the round-3 self-fix at
   SOUND-S2, and two independent rereviews at SOUND-S3) reproduced the exact
   same conclusion. This does not mean the original finding was wrong — it
   means the *first* piece of evidence for it doesn't stand on its own, and
   the safety-relevant final state (the pin now exists and is
   mutation-verified as binding) rests on the SOUND-S3 rereview evidence, not
   on the original UNVERIFIED discovery. No re-verification is needed going
   forward since the SOUND-S3 rounds already did it; this is a note about the
   discovery's provenance, not a live gap.

5. **Other mutation results used to justify a PASS.** Overwhelmingly SOUND-S3
   throughout Tasks 5-8 and the C1 fix/final-review/final-rereview chain. The
   project's reviewers converged on a consistent, disciplined pattern
   (shadow copy -> plant sentinel -> prove red -> revert -> apply real mutation
   -> confirm result) well before the end of the phase, and several reviewers
   explicitly call out and correct weaker proofs from earlier rounds (e.g.
   task-5-rereview.md on task-5-report.md's PYTHONPATH-only sanity check).
   The one systematic exception is `task-5-review.md`'s original two
   findings, UNVERIFIED as filed but superseded by SOUND-S3 re-verification.

## Alarming findings

Nothing alarming in the sense of "a merged safety claim is unsupported."
The one genuine gap — `task-5-review.md`'s original round-trip/margin
findings being UNVERIFIED as filed — was independently re-discovered and
properly re-verified (SOUND-S3) twice over before the branch merged, so the
shipped state is not at risk. The single item worth a maintainer's attention
is claim #1: the highest-stakes number in the whole phase (0 differences
across 98,856 runs) rests on a script whose own invocation was never quoted
verbatim, only the shadow copy's general sentinel proof. I did not find
counter-evidence that it ran unshadowed — I simply could not find a positive,
independently-quotable command proving it did not.

---

# Addendum: `.pth`-repointing contamination check (requested mid-task by sdd-orchestrator)

A second, orthogonal contamination mechanism was flagged after the main audit
was underway: an agent editing a worktree venv's `_editable_impl_*.pth`
files directly (rather than using the non-destructive `PYTHONPATH` env-var
override) to shadow a scratch copy. Unlike the shebang defect, this mutates
**shared, persistent, global state** — every concurrent process importing
through that venv is silently redirected until the `.pth` file is repaired,
and `git status` never shows it (the venv is outside the worktree's git
tree).

**Method:** grepped all 62 Phase B verdict files for `.pth`, `_editable_impl`,
`site-packages`, and verb patterns (`repoint`, `sed -i.*pth`, `> ... .pth`)
that would indicate an agent editing rather than merely discussing these
files.

**Finding: no Phase B verdict file describes any agent editing, repointing,
or `sed`-ing a `.pth` file — of either the copy or the shared worktree venv.**
Every one of the six `.pth` mentions across Phase B (`final-rereview.md:22`,
`task-6-review.md:19`, `task-5-rereview.md:62`, `task-5-rereview2.md:64`,
`task-6-rereview.md:25-26`) is explanatory prose about *why* `PYTHONPATH`
successfully shadows the installed package here — e.g. "the editable installs
in the worktree venv are plain-path `.pth` entries, so `PYTHONPATH` shadows
them cleanly; no meta-path finder to fight" — never a description of an
action taken on a `.pth` file itself. Every shadowing mechanism documented in
Phase B uses the `PYTHONPATH` environment variable, set per-invocation on the
command line, which is non-destructive, process-local, and requires no
restore step (and none is claimed).

**Consequences for the ordering/overlap question:** since no Phase B file
reports repointing the shared venv, there is no window in Phase B's own
record where the shared worktree venv was contaminated, and therefore no
overlap to flag among Phase B's SOUND-S1/SOUND-S3 runs on that basis. I want
to be precise about what this claim rests on: it is an absence-of-evidence
finding, scoped strictly to what the 62 Phase B verdict files say happened.
It does not (and cannot, from a read-only text audit) rule out an unlogged
`.pth` edit that no file mentions, and it says nothing about Phase C, where
the orchestrator reports the contamination actually occurred. If a
`.pth`-repointing incident is later found to have touched the
`title-correspondence` worktree's venv during the Phase B window, every
Phase B run in this audit — including the ones classified SOUND-S1 and
SOUND-S3 above — would need re-examination for whether it fell inside that
window; nothing in the Phase B files themselves establishes that it did.
