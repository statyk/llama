# `overrides.include` — review ledger and verdicts (2026-09-07)

Preserved in-repo because `.superpowers/` is **gitignored**: this directory was
the only copy of the run's ledger, and a previous cycle lost one that way.

Spec: `docs/superpowers/specs/2026-09-07-overrides-include-design.md`
(its "Corrections made during implementation" section is normative — seven
entries, each recording a place the approved text was wrong or was
deliberately departed from).
Plan: `docs/superpowers/plans/2026-09-07-overrides-include.md`.

## What is here

- `progress.md` — the running ledger: 27 rulings, each with a "cost if wrong",
  and 13 durable findings.
- `pyc-audit.md` — the stale-bytecode audit of Tasks 1-3's mutation evidence.
- `task-N-brief.md` / `-report.md` / `-review.md` / `-spec-review.md` /
  `-quality-review.md` / `-rereview.md` — per-task dispatch, implementation
  report, and reviewer verdicts. Tasks 1 and 5 used one combined reviewer;
  Tasks 2-4 used two independent seats.
- `symmetry-review.md` — review of the post-run symmetry fix.
- `whole-branch-spec-review.md`, `whole-branch-quality-review.md` — the two
  independent final reviews over all 19 commits at once.

**Not preserved:** the `review-<a>..<b>.diff` files. They are exactly
reproducible from history now that the branch is merged — `git diff <a>..<b>`
with the SHAs each verdict names — so keeping them would duplicate the object
store.

## The three findings worth reading first

1. **A test can pass against the exact mutation it names.** Four of the plan's
   supplied assertions did, and all four were found by mutation rather than by
   reading. One compared two calls to the same function; one measured a
   different column than it claimed. Reading an assertion cannot tell you what
   it pins — naming the mutant you expect it to catch, and running it, can.

2. **A stated constraint with no test is indistinguishable from an accident.**
   An instruction issued in prose was complied with and pinned by nothing;
   mutating it left 182 CLI tests green while real pre-feature data would
   `KeyError`. Prose from a supervisor is exactly as unpinned as prose from a
   plan.

3. **A mutation harness can score a false `CAUGHT`.** CPython validates a
   `.pyc` against the source's mtime-in-whole-seconds plus its size, so two
   same-size mutants written inside one second run the first one's bytecode
   under the second's label. Fix: a unique `PYTHONPYCACHEPREFIX` per mutant.
   The timing argument two of us expected to rule this out was refuted by the
   artifacts — the batteries were scripted, with runs of 0.19-1.10 s.

Both whole-branch reviewers independently found the same Important defect
(`--suggest-titles` permanently declining on any show with an effective
`overrides.include`) at a call site that belonged to none of the five tasks —
the one place a per-task diff review structurally could not look.
