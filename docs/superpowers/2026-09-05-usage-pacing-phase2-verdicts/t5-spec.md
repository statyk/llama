# Task 5 — SPEC-COMPLIANCE review (`5739217..f980ebe`)

## Verdict: **Spec ✅**

The diff implements exactly Task 5, plus exactly the R9 ruling, and nothing else.
The whole-file diff between the brief's mandated implementation and the shipped
`pacing_state.py` is *three hunks*: `import math`, `_valid_persisted_delta`, and the
`read_state` body/docstring. `PacingState`, `EWMA_ALPHA`, `STATE_NAME`, `_five`,
`observe`, `record` and the module docstring are byte-for-byte the brief's text.

## Requirement checklist

| Requirement | Status |
| --- | --- |
| Produces `PacingState(per_show_delta, samples)` | ✅ frozen dataclass, defaults `None`/`0` |
| Produces `observe(before, after, state)` | ✅ verbatim |
| Produces `read_state(root)` | ✅ (per R9, see below) |
| Produces `record(root, before, after)` | ✅ verbatim |
| Produces `EWMA_ALPHA` | ✅ `= 0.4`, verbatim |
| Files: creates `pacing_state.py` + `test_pacing_state.py` only | ✅ stat shows exactly those two, 286 insertions, 0 deletions |
| Rollover guard `b.resets_at != a.resets_at` present and load-bearing | ✅ present; **and now actually pinned** — see M1 below |
| Boundary contributes only when both readings succeeded | ✅ `_five` + `b is None or a is None`; test covers `None`, `None`, and a reading with `five_hour=None` |
| Negative delta contributes nothing | ✅ `if delta < 0: return state` |
| `record` takes the advisory `file_lock` | ✅ present at `pacing_state.py:105` — but unpinned, see Finding 3 |
| `EWMA_ALPHA` not swept/retuned | ✅ still `0.4`; a new test pins the literal |
| Nothing from Task 6+ | ✅ `grep -rn pacing_state packages/ --include=*.py` outside its own two files returns exactly **one** hit: a docstring mention at `pacing.py:204`. No `_execute` change, no CLI wiring, no `shows_that_fit` |
| `llama` may import `herder`, not the reverse | ✅ `pacing_state.py` imports only stdlib + `llama.locks` + `llama.workspace` (duck-types the reading via `getattr`); the *test* imports `herder.usage`, the allowed direction |
| `openrouter.py` untouched | ✅ not in the diff |
| No `--batch` / `--force` / `trust_age` | ✅ absent |
| Tests offline and deterministic | ✅ `NOW` is a datetime literal; no wall clock, no `$HOME`, no subprocess, no sleep; all IO under `tmp_path` |
| Commit message | ✅ `cb87790` matches the brief's mandated string exactly |

## The R9 ruling — followed, and both boundaries respected

**Core requirement met.** A persisted `per_show_delta` that is not a non-negative real
number degrades to `PacingState(None, 0)` inside `read_state`'s existing never-raises
contract. No clamping, no coercion of a bad value, no repair.

**Boundary 1 — scope is `per_show_delta`'s value only: RESPECTED.**
- The `except` tuple is **unchanged**: still `(OSError, ValueError, TypeError, AttributeError)`.
- `samples` still goes through bare `int(data.get("samples", 0))` — no per-field validation.
- **No test spends itself on a negative `samples`.** Confirmed by reading all 21 test names.
- I verified empirically that the ruling's claim about the already-covered paths is true:
  with `_valid_persisted_delta`'s gate deleted (mutant M4), the `"oops"`, `[1, 2]` and
  `samples: ["x"]` tests **still pass** via the except tuple — only the negative, bool and
  non-finite tests fail. The new check therefore adds coverage exactly where the ruling said
  coverage was missing, and nowhere else.

**Boundary 2 — ruling on `bool` and `NaN`/`Infinity`: BOTH WITHIN THE RULING, not scope creep.**
- **`NaN`/`Infinity`**: squarely inside the ruling's own wording. Neither is *a real number*,
  so "degrade anything that is not a non-negative real number" already covers them.
  `json.loads` accepts both literals by default, and `Infinity >= 0` is `True`, so without
  `math.isfinite` an infinite estimate reaches `decide()`. Correct to reject.
- **`bool`**: the ruling explicitly asked the implementer to make an explicit decision and
  pin whichever way it chose. It rejected, documented the reasoning in
  `_valid_persisted_delta`'s docstring (`observe` can never emit one), and pinned it with a
  test. That is precisely the instruction discharged. Not scope creep.

## The 14 extra tests: legitimate pinning, not scope creep

The brief's 7 tests are present **verbatim and in order** (diffed against the brief text;
only new tests are interleaved). Verdict on the other 14, backed by a mutation sweep run in
a private copy under `$D/work/t5-spec/` (PYTHONPATH-shadowed, import path proven to resolve
inside the copy; `python -B -m pytest -p no:cacheprovider`, `__pycache__` cleared per run,
stdin redirected; green baseline **21 passed** asserted before every mutant):

**Two of them are the only thing making a named binding constraint load-bearing.** Running
the brief's 7 tests *alone*:

| Mutant | Brief's 7 only | Full 21 |
| --- | --- | --- |
| M1 drop `or b.resets_at != a.resets_at` (the load-bearing rollover guard) | **7 passed — SURVIVES** | caught by `test_a_rollover_with_a_positive_delta_still_contributes_nothing` |
| M3 `delta < 0` → `delta <= 0` | **7 passed — SURVIVES** | caught by `test_a_zero_delta_is_folded_in_normally` |

The brief's own rollover test uses `90 → 2`, a *negative* delta, so the negative-delta guard
alone satisfies it — the guard the dispatch brief calls load-bearing was **not pinned by the
brief's own tests**. The extra test is the fix, not decoration.

Full sweep (all 21 tests): M1 caught, M2 (accept negatives) caught, M3 caught, M4 (drop the
delta validation) caught ×3, M5 (`>= 0` → `> 0`) caught, M6 (drop bool rejection) caught,
M7 (drop `isfinite`) caught, M9 (`EWMA_ALPHA` → 0.5) caught. **M8 (drop `file_lock`)
SURVIVES.** **M10 (drop `root.mkdir`) SURVIVES — genuinely equivalent** (verified:
`locks.py:23` does `path.parent.mkdir(parents=True, exist_ok=True)` *before* the
non-POSIX branch, so it runs on every platform; the implementer's claim is correct, and
keeping the brief-mandated line is the compliant choice).

Classification of the 14: **3 earned** (`rollover-with-positive-delta`, `zero-delta-folded`,
`EWMA_ALPHA` literal pin — the last is directly warranted by "EWMA_ALPHA is policy, not
swept"); **6 mandated by R9** (negative, non-numeric, list, bool, non-finite, null-sentinel);
**2 reasonable boundary pins** (`null-preserves-samples`, `zero-accepted` — the `>=`/`>`
boundary, proven by M5); **3 low-value but harmless** (Finding 4). **None of the 14 drives
any production behavior the brief did not want**, which is the scope-creep test that matters.

## Findings

**Critical: none.**

**Important**

1. **`record`'s `file_lock` is unpinned — mutant M8 survives the whole 21-test suite**
   (`packages/llama/src/llama/pacing_state.py:105`). The lock *is* present, so this is **not
   a spec violation** — the requirement is met and the brief mandated no such test. But the
   dispatch brief names the lock a binding constraint ("two concurrent runs would otherwise
   last-writer-wins over a shared estimate"), and nothing in the suite would notice its
   removal. Cheap deterministic fix if wanted: monkeypatch `pacing_state.file_lock` with a
   recording context manager and assert `record` entered it with `root/"pacing-state.json.lock"`.
   No real concurrency needed. Recommend for the quality reviewer or a follow-up minor.

**Minor**

2. **`float(delta)` is a coercion the ruling's literal text excluded**
   (`pacing_state.py:91`). The ruling said "no clamping, no coercion, no repair"; the shipped
   `read_state` returns `float(delta) if delta is not None else None` where the brief returned
   the raw value. It coerces an *already-valid* value's type, not a bad one, so it is type
   normalization rather than repair — and it matches the `float | None` annotation and what
   `observe` produces. **No observable behavioral effect** (`PacingState(4, 1) == PacingState(4.0, 1)`
   is `True`, and `record` re-floats via `observe` before writing). Flagged for the record;
   I would not ask for a change.
3. **A test comment is inaccurate**
   (`test_pacing_state.py`, `test_non_finite_persisted_delta_degrades_to_empty`): "NaN >= 0
   is False in a way that would silently pass a naive sign-only check." Under the code's
   actual `value >= 0` form, `NaN` is *rejected* by the sign check alone; the trap it
   describes only exists for a `not (value < 0)` formulation. `Infinity` — not `NaN` — is
   the value a sign-only check actually admits. The test itself is correct and load-bearing
   (M7 caught); only the comment's reasoning is wrong.
4. **Three of the 14 extra tests are redundant, not wrong**:
   `test_top_level_json_array_degrades_to_empty` and `test_non_convertible_samples_degrades_to_empty`
   exercise the pre-existing `except` tuple that the ruling explicitly named as already
   covered; `test_positive_persisted_delta_round_trips_as_float` pins the Finding-2 coercion.
   Harmless regression pins on a fast pure-function module; no production code added for them.
5. **Two commits where the brief's Step 5 scripted one.** Both are Task-5-only and the first
   carries the brief's exact mandated message. No constraint says "exactly one commit."
6. **Informational, deliberately NOT fixed here (correctly):** `pacing.py:204` still reads
   "`pacing_state.observe` is the sole producer and the guarantor." After R9, `read_state` is
   a second guarantor of the same precondition. Editing `pacing.py` would have been Task 4's
   file and out of Task 5's stated scope, so leaving it is the right call — but the docstring
   should be reconciled in a later pass so the two files do not drift on who guarantees what.

## Cannot verify from the diff

- **Full-suite green (the report's 1803 passed / 7 deselected).** I did not run the suite —
  the isolation rules reserve that for the orchestrator. I verified only
  `test_pacing_state.py`: **21 passed**, from a private copy, never in the worktree.
- **Actual multi-process safety of `record`.** The lock is present and correctly scoped
  (`read_state` → `observe` → `write_artifact` all inside the `with`), but no test exercises
  two concurrent writers, so correctness under real contention rests on `locks.file_lock`'s
  own existing tests, not on anything added here.
- **That `decide()` will consume `read_state`'s output as intended** — that wiring is Task 6
  and is correctly absent.

## Isolation compliance

Worktree read-only throughout: `git status --porcelain` empty and `HEAD` still `f980ebe`
after every experiment. All mutation work ran in `$D/work/t5-spec/copy` (deleted after the
sweep), never via `./.venv/bin/pytest`, never invoking the real `claude` binary. No commits
made; none needed.
