# Task 5 — CODE-QUALITY review (Opus)

## Verdict

**Task quality: Approved.** No Critical or Important findings. Seven Minor
findings, recorded and deferred.

## Verification I ran myself

Suite, the mandated command only:

```
cd /Users/shawn/projects/llama-wt-pacing-loose-ends && ./.venv/bin/python -c "import llama; print(llama.__file__)"
  -> /Users/shawn/projects/llama-wt-pacing-loose-ends/packages/llama/src/llama/__init__.py
cd /Users/shawn/projects/llama-wt-pacing-loose-ends && ./.venv/bin/python -m pytest -q
  -> 1884 passed, 7 deselected, 26 warnings in 6.36s
```

Gate met exactly (1880 + 4). Worktree left untouched: `git status --porcelain`
empty, HEAD at `3317b0c`, and nothing of mine was written outside `$D/t5-qual`.

### Independent mutation, in a COPY, predictions named first

Copy at `scratchpad/t5qual-copy` (rsync minus `.venv`/`.git`/caches),
`PYTHONPATH`-shadowed, run with the worktree venv's **interpreter** (`python -m
pytest`, never a console script). Shadowing proved under pytest before any
mutant: renaming `def _interpret_and_stamp` in the copy reddened exactly the
three helper-reaching tests with `NameError: name '_interpret_and_stamp' is not
defined` (test 3, which never reaches the helper, stayed green — a correct
discriminating sentinel, not a blanket break). Copy deleted afterwards; the
copy's `cli.py` diffed byte-identical to the worktree's at each restore.

**Mutant A — `req["query"]` → a constant string.**
Predicted before applying: test 1 red *at the provider-calls assertion*, with
exit-code / `criteria.exists()` / `STATE_COMPLETE` all still passing; tests
2/3/4 green.
Observed: exactly that. `1 failed, 3 passed`, failing at
`test_sessions.py:612` on `assert any(kind == "complete" and "GD 1973" in
prompt ...)`, the traceback showing the interpret provider *was* called, with
the wrong query. So the implementer's added assertion is reachable and
discriminating — it pins interpretation of **this request's** query, not merely
that interpretation happened.

**Mutant B — `run_resume` never interprets** (replace the
`_interpret_and_stamp(...)` call with `Criteria(query=...)` +
`write_artifact`).
Predicted: test 1 red, test 2 red at `count == 3`, tests 3/4 green.
Observed: exactly that, and this is the finding that matters most for this
run's dominant-defect lens — under mutant B the run reached **exit 0, criteria
present, STATE_COMPLETE**, i.e. all three of the brief's prescribed assertions
passed, and the *only* thing that caught it was the assertion the implementer
added on its own initiative (`calls == []` at line 612). The brief's test as
written would have been green against a resume that never interprets. That gap
was real, was found by the implementer rather than by me, and is closed.

**Mutant C — delete the `if not ws.request.exists():` guard.**
Predicted: test 3 red because the command raises `FileNotFoundError` and "no
criteria.json" never reaches output; others green.
Observed: exactly that (`assert 'no criteria.json' in ''`, Result
`FileNotFoundError`). Test 3 is load-bearing, not a vacuous restatement of
pre-existing behaviour.

I did not re-run the implementer's mutants 1-3; its methodology (including the
`__pycache__`/`co_filename` trap it documented) is sound and its predictions
were named before application. Its **self-correction** on concern 1 — retracting
an unmeasured "the suite would stay green" claim after the mutant showed 22
failures — is exactly the discipline this project's memory says goes missing,
and it retained the test for the right, restated reason (diagnosis at the fork
vs. 21 collateral failures that name nothing).

## Correctness and control flow

- `run_resume`'s new three-way is sound: criteria present → `read_model`
  (unchanged); criteria absent + request absent → the original message and
  exit 1; criteria absent + request present → re-interpret. No path falls
  through with `criteria` unbound.
- **Fit for Task 7, checked deliberately.** `_interpret_and_stamp` contains no
  pause/wait/pacing logic and touches no session state — it is purely
  interpret-and-stamp, so wrapping the *call* in a `RateLimited` retry loop is
  clean. It is also safe to call repeatedly: `run_interpret` gates on
  `should_run(ws.criteria)`, so a second call after a successful interpret
  costs zero LLM calls and returns the stamped criteria, while a call after a
  `RateLimited` genuinely re-runs (criteria is written only on success). The
  update block is idempotent — re-applying the same `model_copy` to an
  already-stamped criteria is a no-op.
- A `RateLimited` escaping the new re-interpret today does not produce a
  traceback: it subclasses `HerderError` and the top-level handler
  (`cli.py:3002`) prints `error: <message>` and exits 1, leaving the session
  `paused` with `request.json` intact — still resumable. The new path degrades
  correctly even before Task 7.
- The duplicated request dict at the `_get_query` call site (rather than
  re-reading `request.json`) is right and matches the brief's reasoning: the
  file is the checkpoint, not the parameter channel.
- Values checked against the model, not assumed: `Criteria` defaults are
  `count=1`, `artist_cap=1/3`, `min_quality_score=6.0`, and the `CRITERIA`
  fixture sets `count=1` and omits the other two — so test 2's chosen 3 / 0.5 /
  7.5 are genuinely distinct from both defaults and fixture, as its comment
  claims.
- Commit messages: correct `type(scope): subject` form, bodies explain *why*,
  each records the test command and count. `3317b0c` is test-only and says so.

## Findings (all Minor)

1. **Minor — `request.json`'s `auto` and `plan` are persisted but never
   consumed.** `run_resume` passes neither to `_execute`, so `plan` defaults to
   `False`. Reachable consequence: `llama get --plan "..."` that dies during
   interpret and is later resumed performs a **full acquisition** — downloads,
   packages, writes the ledger — instead of stopping at the shortlist with
   `mark_awaiting` (`cli.py:477`). This is pre-existing resume semantics for
   every session, and the brief scoped Task 5 to the four criteria flags, so I
   am not calling it Important; but Task 5 is the first point at which the data
   to honour `plan` exists on that path, and leaving two fields in a persisted
   on-disk shape with no consumer invites the drift the helper's docstring is
   about. Either consume them or record why they are carried.

2. **Minor — `request.json` is the only artifact read raw.** Everything else
   goes through `read_model(path, Model)` with pydantic validation; here it is
   `json.loads(ws.request.read_text())` and then duck-typed (`req["query"]`
   hard, the rest `.get`). A truncated or hand-mangled file surfaces as a
   `JSONDecodeError`/`KeyError` through the catch-all at `cli.py:3011`, not as
   a clean `error:` line. Consistent with Task 4's plain-dict design, so this
   is a note on the shape rather than on this task's execution.

3. **Minor — the `get`-path half of the stamp is pinned only transitively.**
   The implementer's mutant 1 (drop the `artist_cap` clause) reddened *only*
   the new resume test; no pre-existing test covers `--artist-cap` /
   `--min-score` / `--year-cap` stamping on the `llama get` path. That coverage
   now exists solely because both entry points share the helper — so if
   `_get_query` ever grows its own copy, the coverage vanishes with the shared
   function rather than failing loudly. Pre-existing debt, newly load-bearing.
   (This is also the honest, bounded form of the implementer's concern 2:
   "one function" is not itself pinned, but the *behaviour* is, on the resume
   side.)

4. **Minor — monkeypatch inconsistency across the four new tests.** Test 1 uses
   the shared-instance pattern (`providers = fake_providers(None)` /
   `lambda config: providers`); tests 2 and 4 kept the brief's
   `lambda config: fake_providers(None)`, which hands out a **fresh** provider
   dict per `make_providers` call. Fine for what they assert, but it means those
   two cannot observe call counts or prompts at all, and the fixture's
   one-deep queues can never be exhausted — a duplicated stage call would be
   invisible to them. Worth aligning if anyone extends them.

5. **Minor (nit) — test 4's inline comment is looser than its assertion.**
   "The interpret fixture's own count, left alone — NOT the persisted 0" reads
   as if `count == 1` proved the value came from the fixture; the `Criteria`
   default is also 1, so the assertion discriminates only against the mutant's
   `0`. That *is* the constraint the docstring claims, so the test is sound and
   only the comment overreaches slightly — flagging it because this run's
   dominant defect is exactly comments claiming more than the assertion pins.

6. **Minor — on the two deliberately deferred comments (you asked for my
   view).** Deferring them is acceptable, but note what is being deferred: the
   comment block immediately above the `_interpret_and_stamp` call in
   `_get_query` now asserts something this commit makes **false** ("a checkpoint
   here would be unresumable — the query lives only in argv"), sitting three
   lines above the code that makes it resumable, in the exact region the
   feature exists for. This repo treats comments as the durable record, so a
   false one here is worse than average. Acceptable only if Task 7 lands on this
   branch; if Task 7 changes shape or slips, it needs its own commit. Same for
   `sessions.py`'s stale `query` field comment.

7. **Minor (informational) — ordering against the proactive gate.** A resumed
   criteria-less session now spends one interpret LLM call *before* `_execute`'s
   pre-flight pacing gate, which exists specifically to decide "before spending
   anything". This mirrors `_get_query` exactly and is acknowledged in
   `CLAUDE.md`, so it is symmetric rather than a regression — but Task 7's
   reactive retry does not change the ordering, and `run resume` is the command
   whose whole purpose is recovering from an exhausted window. Worth an
   explicit decision in Task 7 rather than an accident.

## On the deviations you told me were yours

- **The fourth test (`3317b0c`)** was the right call and is well built: it
  fails *at* the fork on a one-line assertion with a docstring naming the
  reason, where the 21 collateral failures name nothing. My sentinel run
  confirms it reaches the helper.
- **The added assertions** are correct, reachable, and — per mutant B — the
  entire difference between a test that pins T6b's branch and one that does
  not. The monkeypatch switch to the shared-instance pattern is what makes the
  provider assertion reachable at all; without it `providers["interpret"].calls`
  would have been a fresh, empty list and the assertion would have failed
  against the *correct* implementation. That was noticed and handled.
- **The `read_model` import correction** is right; the brief was wrong. Without
  it the two new tests would have failed on `NameError` and the Step 2
  red-first evidence would have meant nothing.
