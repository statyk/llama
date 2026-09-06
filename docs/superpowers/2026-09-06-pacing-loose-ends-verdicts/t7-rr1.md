# Task 7 — SCOPED RE-REVIEW, fix round 1 (Opus)

Scope: commit `c616304` only (`b7cc3a6..c616304`). Documentation-accuracy round;
no behaviour change. Central question: is every sentence now true?

**Suite: 1891 passed, 7 deselected, 26 warnings in 6.47s** — unchanged, as required.
Worktree clean at `c616304`. Every executable line in the diff is unchanged: both
`cli.py` hunks touch only `#` comments and a docstring; the other two files are docs.

---

## Verdicts

### Finding 1 (Important) — ADDRESSED

I re-measured all three claims myself rather than trusting either the old or the
new prose, in an rsync'd copy (no `.venv`/`.git`/`__pycache__`, no `.pyc`
carried), shadowed via `PYTHONPATH` and **proved** to be the tree under test by a
planted sentinel — checked both at bare import and under pytest
(`cli.__file__` resolved inside the copy; `T7RR1_SENTINEL == "copy"`).

| # | state | result | docstring says |
|---|-------|--------|----------------|
| M0 | unmutated, `times=99` | **passes 0.55s** | (baseline) |
| M1a | `stalled=stalled`→`stalled=False`, `times=99` | **FAILED in 0.45s, exit 1** | "lands as a RED TEST in under a second — no timeout needed" ✓ |
| M1b | same mutant, `times=10**9` | **exit 124** under `timeout 60` | "the same mutant then HANGS, exit 124 under `timeout 60`" ✓ |
| M1c | guard restored, `times=10**9` | **passes 0.45s** | "restoring the guard passes in 0.5s against that same unbounded provider" ✓ |

M1a's red is exactly the mechanism claimed: the spin exhausts the bound and the
101st call hits `then=None` (`AttributeError("'NoneType' object has no attribute
'complete'")` → `exit_code 1 != 0`). M1b/M1c together do establish the inference
"it is the guard, not the bound, that stops the spin" — the bound is held fixed
and only the guard varies.

The supporting mechanism claim is also true: `pacing.sleep_until` returns at
`remaining <= 0` **before** any `_sleep` call (`pacing.py:83-86`), so
"the spin never calls `_sleep` again" is accurate, and no sleep-budget assertion
can see the mutation.

**The new parenthetical about `_preflight_gate` is TRUE, and I verified it rather
than assuming.** `test_preflight_sleeps_at_most_once` drives
`monkeypatch.setattr(cli, "read_usage", _readings(99))`, and `_readings` "repeats
the last" reading forever — genuinely unbounded. Mutating `stalled=slept` →
`stalled=False` there hangs: **exit 124** under `timeout 60`. So `_preflight_gate`'s
"HANGS the suite" sentence is site-true, exactly as the ruling held.

**`_preflight_gate` was left alone** — verified: the `cli.py` diff has no hunk at
lines 340-370, and the shipped text still reads `stalled=slept`, "HANGS the suite
rather than reddening it", "running the pre-flight tests under a hard timeout".
Repo-wide there is now exactly ONE "HANGS the suite" occurrence (`cli.py:353`),
the true one.

The self-invalidating instruction is gone and replaced with its inverse ("do not
unbound the test to 'make the pin realistic'"), which is the correct correction:
the old text's action was the one measured to convert a pin into a hang.

### Finding 2 (Minor) — ADDRESSED

I counted the sites myself. Literal `run_interpret(` call expressions in shipped
source: `cli.py:695` (inside `_interpret_and_stamp`) and `cli.py:2975`
(`profile_add`). `_interpret_with_pause` has exactly two callers: `cli.py:805`
(`_get_query`) and `cli.py:1082` (`run_resume`). So the paths that reach
`run_interpret` are three, two of them in-run — which is what the new comment now
says: "at two IN-RUN call sites (`_get_query` and `run_resume`'s criteria-less
branch); `profile_add` is a third, outside any run."

"outside any run" verified at `cli.py:2972-2975`: `profile_add` interprets against
a `RunWorkspace` in a `tempfile.TemporaryDirectory()` — there is no session to
park. "Both in-run ones go through `_interpret_with_pause`" is true.

Nit, not a finding: the comment counts *paths that reach* `run_interpret` as "call
sites" (strictly, `_get_query`/`run_resume` call `_interpret_with_pause`). That is
the same convention `CLAUDE.md` uses two paragraphs away, so it is consistent
rather than newly false.

### Finding 3 (Minor) — ADDRESSED

All four clauses checked in source, not inferred:

1. "this catch [the interpret one] … re-raise[s]" — `cli.py:766`: `if not
   pace.enabled: raise`. ✓
2. "`_execute`'s run-level one" — `cli.py:490` (inside the `except RateLimited`
   arm): `if not pace.enabled: raise`. ✓
3. "the per-show loop records a per-show failure instead" — `cli.py:543-546`:
   `if not pace.enabled:` → `typer.echo(f"FAILED …", err=True)` +
   `failures.append({...})` + `return`. It does **not** re-raise. ✓
4. "the pre-flight gate simply never reads a meter (a missing reading proceeds)" —
   `_meter_applies` returns `pace.enabled and backend == "claude_cli"`
   (`cli.py:262`), so under `--no-pacing` it is False; `_meter` short-circuits to
   `None` (`cli.py:272-274`); and `pacing.decide` returns `Proceed()` on
   `not opts.enabled or reading is None` (`pacing.py:223-224`). ✓ Doubly so, in
   fact — the gate is dead by both the None reading *and* `opts.enabled`.

The implementer's fourth clause is therefore correct and was worth adding: a
sentence whose subject is "every other site" would otherwise have left one site
unaccounted for. The umbrella claim it sits under ("`--no-pacing` restores the
pre-pacing behaviour") also holds at each of the four.

Antecedent check: "this catch" is disambiguated by the very clause that contrasts
it with "`_execute`'s run-level one", so it reads unambiguously as the interpret
catch despite the paragraph opening on `_execute`.

### Finding 4 (Minor) — ADDRESSED

The heading is now `### Known gap: run_interpret is not covered — SUPERSEDED, it
is (T6b, built)` (spec line 42), so a heading/TOC scan meets the correction rather
than the false claim. The SUPERSEDED block at the end of the section is unchanged
and consistent with it.

---

## New Critical/Important breakage introduced by the fix diff

**None.** No executable line changed; the suite count is identical (1891/7); the
one docstring the ruling protected is byte-for-byte intact; and every replacement
sentence I checked is true against source or measurement.

---

## The implementer's two self-criticisms — my read

**(a) The cross-reference to `_preflight_gate` could go stale.** Accept it as
shipped. It is the opposite failure mode from the one Finding 1 removed: the old
sentence was *self-invalidating* (following it broke the guard silently); this one
is *self-checking* — it names the exact condition that would falsify it ("its
tests do not bound the refusal"), which I confirmed is currently true and which a
reader can verify in one grep. The residual risk is also benign in direction: a
stale version would mislead about which *evidence* exists at a sibling site, not
about whether the guard is load-bearing — nobody deletes `stalled=slept` on the
strength of it.

One improvement worth considering at final review (a suggestion, not a finding,
and out of this round's ruling since it touches `_preflight_gate`): the pointer
only exists at one end. A reader who lands on `_preflight_gate` first still meets
an unqualified "HANGS the suite" with no hint that the sibling measured otherwise.
Adding a site-scoping clause there ("at THIS site — its tests do not bound the
refusal") would make the pair symmetric and remove the maintenance burden from the
one-way reference.

**(b) Finding 3's sentence is now four clauses and the least readable in its
paragraph.** Agreed on the diagnosis, agreed on the trade. Accuracy was the right
call for an accuracy round, and each clause carries distinct, load-bearing
information (four sites, four different meanings of "restores pre-pacing
behaviour"). It is genuinely compressible without loss — a colon-introduced list
would read better than the subordinate chain — but that is prose polish for the
final review, not a blocker. Do not compress it by dropping a site: the fourth
clause is the one that makes the "every other site" claim complete.

---

## Out of scope (recorded, deferred — not verdicted here)

1. **Same class as Finding 1, but predating this diff.** `CLAUDE.md`'s (c)
   paragraph still ends: "and no sleep-budget guard in a test can see it (**it
   hangs rather than failing**)", asserted over "the run-level sites". The
   interpret catch *is* a run-level site that re-decides after a nap and sleeps at
   most once, and its mutant now measurably **reddens in 0.45s** rather than
   hanging. The inner enumeration names only the pre-flight and `_execute` catch,
   so the sentence is defensible-but-ambiguous rather than flatly false — but it is
   the same generalisation Finding 1 was about. Introduced by `b7cc3a6`/main, not
   by `c616304`; flagging for the final review.
2. The phase-2 spec's superseded section **body** still opens "A `RateLimited`
   raised by `run_interpret` still exits 1 with no checkpoint, and phase 2
   deliberately leaves it that way", and names only two call sites. It is a dated
   historical record now bracketed by SUPERSEDED at both the heading and the end,
   which is the repo's convention; noted only for completeness.
3. **Source→test-name coupling:** the new docstring cites
   `test_a_limit_during_interpret_sleeps_at_most_once` by name; a rename would
   strand it. Low risk — the test's own docstring carries the same measurement, so
   the pair is mutually reinforcing.
4. Deferred items confirmed untouched, as instructed:
   `plans/2026-09-05-usage-pacing-phase2.md:1160`'s dated "T6b (FILED, NOT
   IMPLEMENTED)"; the interpret pause's unpinned operator note; the request dict
   spelled twice; `config` untyped in the new signature. The spec's 1(c)
   `scope="interpret"` line is likewise untouched — agreed it is the spec, not the
   code, that needs correcting at ratification.

---

## Method / evidence

- Mutation ran in `…/scratchpad/t7rr1-copy` (rsync, `--exclude .venv/.git/__pycache__`),
  never in the worktree. Copy verified as the tree under test by a planted
  sentinel at import time **and** under pytest, then deleted.
- Every hot-spin mutant run under `timeout 60`; `exit=124` treated as CAUGHT.
- Worktree suite run only as `cd /Users/shawn/projects/llama-wt-pacing-loose-ends
  && ./.venv/bin/python -m pytest -q`; no file in the worktree modified
  (`git status --porcelain` empty). No commits made.
- Log: `$D/t7-rr1/t7-rr1.log`.
