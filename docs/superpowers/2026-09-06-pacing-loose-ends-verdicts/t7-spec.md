# Task 7 — SPEC-COMPLIANCE review (Opus)

## Verdict: **Spec ✅**

The diff implements the brief plus exactly the three deviation classes named
by the parent (the `run_resume` catch, the documentation corrections, and the
`--no-pacing` guard I rule in below). No unrelated scope. Every finding below
is Minor except one Important documentation defect.

Test command used, the only one:

    cd /Users/shawn/projects/llama-wt-pacing-loose-ends && ./.venv/bin/python -m pytest -q
    -> 1891 passed, 7 deselected, 26 warnings in 6.38s

Venv proved first: `./.venv/bin/python -c "import llama; print(llama.__file__)"`
-> `/Users/shawn/projects/llama-wt-pacing-loose-ends/packages/llama/src/llama/__init__.py`.

---

## 1. Counts and test-loss check — VERIFIED, nothing lost

I did not take the counts on trust. I extracted the baseline with
`git archive a7839dc | tar -x` into a clean tree (0 `.pyc`), proved
`PYTHONPATH` shadowing resolved into that tree, and diffed collected node IDs.

| | |
|---|---|
| baseline `a7839dc` collected | **1886** (7 deselected) |
| HEAD `b7cc3a6` collected/passed | **1891** (7 deselected) |
| `comm -23 base head` (removed) | **empty** |
| `comm -13 base head` (added) | exactly 5, all in `test_sessions.py` |

Added: `..._parks_a_resumable_session`, `..._within_max_wait_sleeps_and_finishes`
(the brief's two), `..._sleeps_at_most_once`, `..._while_resume_re_interprets_
parks_the_session_again`, `test_no_pacing_lets_a_limit_during_interpret_fail_
the_run` (the implementer's three). **No test was lost, renamed away, or
silently deselected.** The report's 1886/1891 numbers are exact.

## 2. The plan's "HANGS rather than reddening" claim — the implementer is RIGHT

Independently reproduced in an rsync copy (`--exclude .venv/.git/__pycache__`,
`find -name '*.pyc' | wc -l` = 0), `PYTHONPATH`-shadowed, proved live with a
planted `raise RuntimeError("SENTINEL-SPEC7-COPY-IS-LIVE")` whose traceback
resolved inside the copy. Copy baseline for `test_sessions.py`: 41 passed.

(One process note: my first M1 run reported 41 passed because I omitted
`PYTHONPATH` on the pytest invocation — the mutant was not live. Re-run
correctly below. Recording it because it is the exact false-UNCAUGHT the
method section warns about.)

| # | mutant | predicted red (named BEFORE applying) | observed |
|---|---|---|---|
| M1 | `stalled=stalled` -> `stalled=False` in `_interpret_with_pause` | `test_a_limit_during_interpret_sleeps_at_most_once` | **CAUGHT** — that test and only that test `FAILED`, `1 failed, 40 passed in 0.82s`, exit **1**, on `AttributeError("'NoneType' object has no attribute 'complete'")` |
| M1b | M1 + the test's `times=99` -> `times=10**9` | hot spin, exit 124 under `timeout 60` | **exit 124**, `Terminated: 15` |
| M1c | guard restored, `times=10**9` kept | passes fast | `1 passed in 0.18s`, exit 0 |

So: **the spec's constraint 2 and the brief are FALSE at this site as the test
is written** — the mutant reddens by name in under a second; it does not hang.
M1b/M1c together show it is the `stalled` guard, not `times=99`, that stops the
spin (production, unbounded, genuinely does hot-spin). The implementer's report
is accurate in every particular, including the exit codes, and correcting the
**test** docstring rather than switching to `times=10**9` was the right call:
a red test is strictly better than a hung CI, and the pin is real either way.

Note this is site-specific and does **not** refute constraint 2 in general —
Task 6's `_preflight_gate` site does hang, and its docstring is untouched and
still correct.

### **Important — the SOURCE docstring still carries the refuted claim**

`cli.py:737-743`, inside `_interpret_with_pause`, still says:

> "...the pause becomes a hot spin, **which HANGS the suite rather than
> reddening it. No sleep-budget assertion can see that mutation; it is caught
> only by running these tests under a hard timeout and reading the exit
> code.**"

Measured false for this site's shipped test: M1 caught it as an ordinary red
test in 0.8s, by name. The implementer corrected the *test* docstring in
`b7cc3a6` and left this one — inherited verbatim from `_preflight_gate`, where
it IS true. Two consequences: the branch ships a comment asserting the opposite
of a measurement made in the same branch (the project's own named defect class,
and the stated reason the test docstring was rewritten), and it misdirects the
next reader into believing only a timeout run can see the mutation. **Fix: two
sentences, in `_interpret_with_pause`'s last paragraph only.** The commit body
of `7b2e0be` repeats the same claim, but that is immutable history and I would
not rewrite it.

## 3. `CLAUDE.md` — was anything TRUE deleted? **No.**

I diffed the before/after paragraph line by line rather than reading the
report's summary of it.

**Boundary (a): byte-for-byte identical.** `claude_cli`-specific,
`openrouter.py:37`, the three `_with_transport_retry` attempts, "deliberately
left untouched" — all present, unchanged. The thing that was fixed once before
for exactly this reason survived.

**The `profile_add` carve-out: kept and strengthened** — now stated as the
*only* `run_interpret` call the pause guarantee does not reach, with the reason
(scratch workspace, no session to park). The `llama get --profile` clarifier
survives too. Matches the loose-ends spec's "Out of scope" section verbatim in
substance.

Everything removed was made false by Tasks 4-7 and I checked each:

- "It does **not** cover `run_interpret`, which has **two call sites**...
  `_get_query` and `profile_add`" — Task 5 added a third (`run_resume`), so the
  count was already false. Correctly removed; both in-run sites are enumerated
  in the replacement.
- "T6b, deliberately UNBUILT" / "`run resume` refuses a session without one" /
  "a checkpoint there would park an unresumable run" / "the query lives only in
  argv" / "A limit during interpret still exits 1" — all now false.
- "`run_interpret` writes `criteria.json` only on success" (still true) and
  "covering it is a resumability design ... persist the raw query and the flags
  stamped onto criteria at run-claim time" (still true) — **both preserved**,
  reworded from *why it was unbuilt* into *what was built*.
- The `interpret`-vs-`discover` warning, the `_PIPELINE_RUN_STAGES` note, the
  `except HerderError` ordering rule, the whole-stage-granularity resume-cost
  sentence, and the whole of boundary (c)'s T7b tail — all verbatim.

**Only true fact dropped:** the parenthetical "(the run dir itself already
exists — `claim_run_dir` makes it)". Still true, but it existed solely to
qualify "written no artifacts", which is now false because `request.json` *is*
written there. Losing it is correct, not collateral. **Minor / no action.**

### "three pause sites -> four" in two places — ACCURATE

`grep -n "_render_pause("` gives exactly four call sites: 367 (`_preflight_gate`),
491 (`_execute`'s run-level catch), 664 (the show loop), 752 (`_interpret_with_
pause`). Boundary (c) and `_render_pause`'s own docstring both now say four and
name the interpret catch. Not overreach.

### The gate-sites sentence — ACCURATE

`_preflight_gate` has three call sites (393 `_execute`, 787 `_get_query`, 1060
`run_resume`), plus the separate per-show gate. CLAUDE.md's new list — `_execute`
top, each show's lock, and "ahead of `run_interpret` at both of its in-run call
sites" — matches the code exactly.

### Phase 2 spec `Progress` marker and the SUPERSEDED paragraph — ACCURATE

The counters marker now reads "**CLOSED as won't-build**, not pending", citing
the loose-ends spec's "Closed as won't-build" section — which does exist and
does say precisely that. The T6b SUPERSEDED note's four factual claims
(`request.json` at run-claim time, `run resume` re-interprets, `_interpret_with_
pause` gates and catches, `profile_add` still exits 1) all check out against the
code. Not overreach.

## 4. The INVERTED test — necessary, and it still pins its original property

`test_request_is_written_even_when_interpret_fails` previously asserted
`exit_code != 0` with a docstring saying `_get_query` "deliberately does not
catch it". That is precisely the behaviour Task 7 reverses, so the inversion is
**necessary, not convenient** — there is no version of this task under which the
old assertion can survive.

Does it still pin write-before-interpret? I mutated for it rather than reading:

- **MR1 (mine)**: move the `write_artifact(ws.request, ...)` block from above
  `_preflight_gate` to below `_interpret_with_pause`. Predicted red:
  `test_request_is_written_even_when_interpret_fails`, on `FileNotFoundError`.
  Observed: **exactly that**, `FileNotFoundError: ... /runs/req2/request.json`,
  plus `test_the_preflight_gate_runs_before_interpret_is_paid_for`,
  `..._parks_a_resumable_session` and `..._no_pacing_lets_a_limit...`.
- **M4 (implementer's)**: delete `_get_query`'s `if criteria is None: return`.
  Predicted red: the three named in the report. Observed: exactly those three.

So the property survives the inversion intact, and the `--no-wait` the
implementer added is load-bearing, not cosmetic: the injected `RateLimited`
names no reset, so `resume_at` falls back to the 1h `unknown_reset_wait`, which
is inside the 6h cap — under the default `--wait` this test would have slept a
real hour. That is a real trap correctly defused, and it is documented in the
docstring.

## 5. The `run_resume` catch and the shared helper — SOUND

The parent ruled the catch in and asked whether one shared helper is sound. It is.

- **Scope is the one branch.** `git show 7b2e0be -- cli.py` touches only the six
  lines inside the criteria-less branch. `run_resume` is otherwise untouched.
- **Both sites are genuinely covered, and independently pinned.** M3 (revert
  `run_resume` to bare `_interpret_and_stamp`) reddens
  `..._while_resume_re_interprets_parks_the_session_again` and nothing else.
  **MR2 (mine)**: delete *only* `run_resume`'s `if criteria is None: return`,
  keeping the helper — predicted the same test, observed exactly that. So the
  second call site's plumbing is pinned, not merely inherited.
- **The helper's contract mirrors `_preflight_gate`'s** (`None` / `proceed=False`
  => caller returns), so both call sites read identically, and the `stalled`
  invariant — whose failure mode is a hot spin — exists in one copy rather than
  two. Given that this exact invariant is what M1b shows spins forever, one copy
  is the right call.
- Semantics are identical to the brief's inline snippet; `INTERPRET_NOTE` is the
  brief's note string verbatim.

Re-parking an already-`paused` session is correct: `mark_paused` rewrites
`resume_after` from the *new* refusal, and the test asserts the rewrite
(`2026-09-07T14:02`, replacing the `07:10` it was parked with) rather than
merely asserting `STATE_PAUSED`.

## 6. My read on the `--no-pacing` guard: **RULE IT IN**

The reasoning is right and the placement is correct.

**Right:** all three pre-existing sites restore pre-pacing behaviour under
`--no-pacing` — `_execute`'s run-level catch `raise`s (cli.py:489), the per-show
catch records an ordinary show failure (cli.py:544), and the proactive gate goes
dead because `_meter_applies` is gated on `pace.enabled` (cli.py:262). Without
the guard the new fourth site would be the *only* one that pauses under
`--no-pacing`, which falsifies CLAUDE.md's **pre-existing** sentence
"`--no-pacing` opts out of both halves". That makes the guard a defence of an
existing documented promise, not new scope — the narrowest possible reading of
"no more than the brief requires".

**Placed correctly:** first statement inside `except RateLimited`, before
`_render_pause` and therefore before any state is written — byte-identical in
shape to `_execute`'s sibling at cli.py:489. It restores exactly the pre-T6b
outcome (uncaught refusal, exit 1, `request.json` already on disk from Task 4),
so nothing is left half-written.

**Pinned:** M2 (delete the guard) reddens
`test_no_pacing_lets_a_limit_during_interpret_fail_the_run` and only that test —
predicted before applying, observed. Reverting it would be a two-line + one-test
change as the implementer says, but I would keep it.

One nit if you keep it (Minor): CLAUDE.md's new sentence "`--no-pacing`
re-raises here exactly as it does at the other sites" is imprecise — only
`_execute`'s catch literally re-raises; the show loop converts to a per-show
failure and the pre-flight gate simply goes blind. "restores the pre-pacing
behaviour at every site" (which is what the source docstring already says)
would be exact.

## Findings, by severity

- **Important** — `_interpret_with_pause`'s docstring (cli.py:737-743) still
  asserts the mutation "HANGS the suite rather than reddening it" and "is caught
  only by ... a hard timeout", which M1 measured false for this site's shipped
  test. Same defect class the branch corrected in the test docstring; two
  sentences to fix.
- **Minor** — `_execute`'s catch comment (cli.py:480-481) says `run_interpret`
  runs "at two call sites now (`_get_query` and `run_resume`'s criteria-less
  branch)". `run_interpret` actually has three call sites; the two named are the
  *in-run* ones. CLAUDE.md is careful here ("both of its **in-run** call sites");
  the code comment dropped the qualifier. Exactly the drift the paragraph two
  screens up warns about.
- **Minor** — CLAUDE.md: "`--no-pacing` re-raises here exactly as it does at the
  other sites" (see the nit in section 6).
- **Minor** — the phase 2 spec's SUPERSEDED marker sits at the *end* of the
  section, under the heading "### Known gap: `run_interpret` is not covered",
  which is itself now false and unmarked. A reader scanning headings still sees
  a live gap. Attaching the marker to the heading would fix it.
- **Minor** — `docs/superpowers/plans/2026-09-05-usage-pacing-phase2.md:1160`
  still reads "### Task T6b (FILED, NOT IMPLEMENTED)". Defensible (plans and
  ledgers are dated records, and the implementer deliberately left that class
  alone), but the same file class as the spec that *was* corrected, so the
  treatment is asymmetric. Your call; I would leave it.
- **Minor** — the spec's 1(c) says the checkpoint is `mark_paused(...,
  scope="interpret")`. The implementation passes the refusal's own scope
  (`five_hour`/`seven_day`) because `_render_pause` reads it off the exception
  and has no `scope` parameter. **The implementation is right and the spec line
  is wrong**: `pause_scope` means the usage window everywhere else in
  `sessions.py`, and "interpret" would be a category error. Worth a one-line
  spec correction at ratification, not a code change.
- **Minor / no action** — the one true sentence dropped from CLAUDE.md is the
  `claim_run_dir` parenthetical, whose only job was to qualify a claim that is
  now false. Correct to drop.

## Checks that passed with nothing to report

- `decide()` untouched (`git show --stat` lists no `pacing.py`); no measured
  constant retuned.
- Commit style: both are lowercase `type(scope): subject`; both bodies explain
  *why*, both cite the exact test command and result, both carry the trailers.
  Scope split (code / docs) is clean.
- No file outside `cli.py`, `sessions.py` (one comment), `test_sessions.py`,
  `CLAUDE.md` and the phase 2 spec was touched. `openrouter.py` untouched.
- SDD ledgers deliberately not rewritten — correct; they are dated records.
- Worktree clean at `b7cc3a6` before and after my review; I modified nothing in
  it (all mutation in `/private/tmp/.../scratchpad/spec7-mut`, deleted after).

## ⚠️ Cannot verify from diff

- **The KeyboardInterrupt contract at this specific site.** It is inherited
  through `_render_pause` and no test exercises Ctrl-C at the interpret site.
  Covered by construction — I read the shared renderer and there is no
  site-specific branch in it — but not by assertion. The implementer flags this
  himself (Concern 5) and I agree with the assessment; noting it so it is on the
  record rather than proposing a test.
- **The `stalled` guard at the `run_resume` site specifically.** Same helper,
  same code path, so a second test would only re-run `_interpret_with_pause`.
  MR2 confirms the branch's plumbing is pinned; the guard itself is pinned once,
  at the `_get_query` site. Reasonable, but it is an argument rather than a
  measurement, as the implementer says.
