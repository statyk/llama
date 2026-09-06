# Task 5 — scoped RE-REVIEW of fix round 1 (`f980ebe..ef6ad14`)

**Verdict: all three findings ADDRESSED. No new Critical or Important breakage.
Recommend accepting the fix round.**

Scope: the fix diff only. I did not re-review the task.

---

## Method / harness integrity

Private copy at `$D/work/t5-rereview/copy` (`src/llama` + `tests/test_pacing_state.py`
copied from the worktree), PYTHONPATH-shadowed and run with the worktree venv's
`python -B -m pytest -p no:cacheprovider` under `PYTHONDONTWRITEBYTECODE=1`, `__pycache__`
cleared before every run, stdin redirected from `/dev/null`.

- **Import path proven, not assumed.** A sentinel test asserts `llama.__file__` and
  `llama.pacing_state.__file__` both start with the copy's `src/` prefix, *and* asserts a
  **planted `_REREVIEW_SENTINEL` marker** that only exists in the copy — so the file pytest
  imports is provably the file the harness mutates, not the editable install pointing at the
  worktree.
- **Every run's summary line is asserted to contain `passed`/`failed`**; anything else is
  reported `HARNESS-BROKEN`, never scored. A failed string substitution is reported
  `MUTATION-APPLY-FAILED`, never scored as CAUGHT.
- **Harness sanity-checked in both directions**: a no-op run reports SURVIVED (26 passed);
  `EWMA_ALPHA 0.4→0.5` reports CAUGHT; a non-matching mutation reports MUTATION-APPLY-FAILED.
- Source restored after every run and verified byte-identical to the worktree afterwards
  (modulo the planted sentinel line). **Worktree untouched** — `git status --porcelain` empty
  before and after. **No commits made.** The suite was never run in the worktree.

Baseline: **26 passed** = 24 in `test_pacing_state.py` + 2 sentinel.

---

## 1. The six mutations, re-run independently — 6/6 CAUGHT

| # | Mutation | Result | Caught by |
| --- | --- | --- | --- |
| I1 | `except (…, OverflowError)` → narrowed back to the old 4-tuple | **CAUGHT** | `test_overflow_samples_degrades_to_empty` |
| M37 | `observe(before, after, read_state(root))` → `observe(before, after, PacingState(None, 0))` | **CAUGHT** | `test_record_folds_into_the_persisted_estimate` **and** `test_record_reads_and_writes_inside_the_lock` |
| M35 | delete the `with file_lock(...)` entirely (body dedented) | **CAUGHT** | `test_record_reads_and_writes_inside_the_lock` |
| M36 | `file_lock(root / (STATE_NAME + ".lock"))` → `file_lock(root / STATE_NAME)` | **CAUGHT** | `test_record_reads_and_writes_inside_the_lock` |
| M38 | hoist the read *outside* the lock | **CAUGHT** | `test_record_reads_and_writes_inside_the_lock` |
| M43 | hoist the write *outside* the lock | **CAUGHT** | `test_record_reads_and_writes_inside_the_lock` |

The implementer's 6/6 claim is confirmed on my own harness. Note M37 is caught **twice** —
by the RMW test on value and by the lock test on ordering — which is genuine redundancy of a
useful kind, not padding.

---

## Findings

**I1 — ADDRESSED** (`packages/llama/src/llama/pacing_state.py:92`, test at
`packages/llama/tests/test_pacing_state.py:176-184`).
`OverflowError` added to the except tuple; narrowing it back flips the new test red.

**The fix is exactly one exception class wider and nothing more.** The complete
source-side diff over `f980ebe..ef6ad14` is a single line, one identifier added:

```
-    except (OSError, ValueError, TypeError, AttributeError):
+    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
```

`git diff --numstat` for the range is `1 1 pacing_state.py` / `37 0 test_pacing_state.py`
— one source line changed, zero test lines deleted. **No validation of `samples`' value
crept in**, confirmed by direct behavioral probe of the shipped code:

```
{"samples": Infinity} -> PacingState(None, 0)      # degrades, no raise  <- the fix
{"samples": 1e309}    -> PacingState(None, 0)      # degrades, no raise  <- the fix
{"samples": -3}       -> PacingState(4.0, -3)      # still unvalidated
{"samples": true}     -> PacingState(4.0, 1)       # still unvalidated
{"samples": "7"}      -> PacingState(4.0, 7)       # still unvalidated
{"samples": 3.9}      -> PacingState(4.0, 3)       # still truncating
```

The `-3`/`true`/`"7"`/`3.9` rows are exactly the Minor-4 looseness you ruled out fixing, and
they are untouched. The change is contract-only (no raise), not semantics.

**I2 — ADDRESSED** (`packages/llama/tests/test_pacing_state.py:187-191`).
`test_record_folds_into_the_persisted_estimate` calls `record` twice and asserts both the
returned state and the re-read state equal `PacingState(4.0 + ALPHA*(10.0-4.0), 2)`. The
expectation is written from independent literals, not computed by calling the
implementation, so it is not tautological. M37 flips it red.

**I3 — ADDRESSED** (`packages/llama/tests/test_pacing_state.py:194-208`).
One test catches all four lock mutations (M35/M36/M38/M43), verified individually.

---

## 3. Judgment on the lock test's strength — **meaningfully strong, not a re-description**

The concern is fair to raise and I checked it specifically. My answer is that the test is
stronger than a pure ordering spy, for three concrete reasons:

1. **It takes a real lock.** `_lock` is not a stub — it captures `real_lock = ps.file_lock`
   *before* patching and does `with real_lock(path, **kw): yield`. A genuine `fcntl.flock`
   is acquired and released on the real sidecar path during the test. It is a *decorating*
   spy, not a replacing one.
2. **Its assertions are literals, not derived from the implementation.** The expected
   sequence `["enter:pacing-state.json.lock", "read", "write", "exit"]` hard-codes the
   sidecar filename and the operation order. Nothing in it is computed by re-running the
   code under test, which is the actual tautology failure mode.
3. **It kills the mutation the docstring exists to prevent.** M38 — the read hoisted out of
   the lock — *is* the lost-update TOCTOU, and it goes red. M36 kills the orphaned-inode
   footgun by the filename assertion.

What it honestly does **not** pin is **mutual exclusion** — no second process or thread
contends, so it cannot detect a `file_lock` that fails to exclude. That is the correct
layering rather than a gap: `packages/llama/tests/test_locks.py` already pins the primitive's
exclusion properties directly (`test_nonblocking_raises_when_held`,
`test_lock_auto_released_on_process_death`), and `test_concurrency.py` forks processes for the
end-to-end case. This test's job is "`record` calls *that* primitive, on *that* path, with
both the read and the write inside it" — and it does that job. The reviewer's own
recommendation was the cheap monkeypatch pattern over the fork, and I agree with it here.

Two residual weaknesses, both cosmetic, neither worth a change:
- The `events.append("exit")` sits after the inner `with`, so an exception raised inside
  `record`'s lock would record no `"exit"`. Only the happy path is covered — fine, that is
  the path under test.
- `events == [...]` pins exactly one read and one write. Mild over-specification; it is also
  what makes M37 fail here as well as in the RMW test.

---

## 4. Deferred Minors — all nine confirmed UNTOUCHED

Verified by reading the shipped source plus the behavioral probe above:

| Deferred item | State |
| --- | --- |
| Minor 4 — `samples` validated looser than `delta` | untouched (`:90` still `int(data.get("samples", 0))`; probe shows `-3`/`true`/`"7"`/`3.9` all pass through) |
| Minor 5 — `PacingState(None, samples>0)` produced and mishandled | untouched (`:91` unchanged; `{"samples": 3}` still yields `(None, 3)`) |
| Minor 6 — missing `per_show_delta` key | untouched and still unpinned (`:87` still bare `.get`); the reviewer's proposed 4th test was **not** taken |
| Minor 7 — `_five`'s dead None-guard and `getattr` default | untouched (`:34` verbatim) |
| Minor 8 — both-`None` `resets_at` no-op | untouched (`:46` verbatim) |
| Minor 9 — `record`'s docstring wording | untouched (`:99-102` verbatim) |
| the three redundant tests | untouched — the test diff is `37 insertions, 0 deletions` |
| `float(delta)` coercion | untouched (`:91` verbatim) |

The implementer took exactly the **three** tests corresponding to the three Important
findings and left the reviewer's **fourth** (Minor 6's) on the floor. That is the correct
discipline and worth noting explicitly.

---

## 5. Count sanity check

`grep -c '^def test_'` gives **21 at `f980ebe`, 24 at `ef6ad14`** — +3, matching the three
`+def test_` lines in the diff and matching the reported 24 in the file. A +3 module-level
addition with zero deletions anywhere in the range is consistent with the reported
**1803 → 1806** full-suite rise. (I did not run the full suite; you verify that.)

---

## New breakage from the fix diff

**Critical: none. Important: none.**

The source change is a one-identifier widening of an except tuple. It can only convert a
raise into the already-documented `PacingState(None, 0)` degradation; it cannot mask a
previously-caught condition (the four original classes are still listed) and it cannot
change any value the function returns on a non-raising path. The `PacingState(None, 0)`
return keeps `decide()`'s non-negative precondition intact.

The test-side change adds one import (`contextlib.contextmanager`) and three functions. The
monkeypatches are `monkeypatch.setattr`, so teardown is automatic and no module state leaks
to other tests. Post-sweep baseline re-verified green (26 passed).

### Out-of-scope observations (deferred minors, not for this round)

- `test_record_reads_and_writes_inside_the_lock`'s `lambda p, d` shims would break if
  `write_artifact` ever grew a keyword argument. Trivial; leave it.
- The same test hard-codes `"pacing-state.json.lock"` rather than deriving it from
  `ps.STATE_NAME`. Deliberate strictness; deriving would also have caught M36, so either is
  defensible. Leave it.
- Minor 6 (missing-delta-key defaulting to `0`) remains the one real gap of the nine and is
  still worth picking up in a later cleanup pass — a defaulted `0` is the "shows cost
  nothing → never pause" under-estimate. Deferred as ruled, not raised here.

---

## Closing verdict

**Fix round 1 is complete and correct. I1, I2, I3 all ADDRESSED, 6/6 mutations
independently re-confirmed CAUGHT, the I1 fix is precisely the one-word widening you ruled
in and nothing more, the lock test is genuinely load-bearing rather than a mirror of the
implementation, and no deferred Minor was fixed opportunistically. Ship it.**

Full log: `$D/t5-rereview/t5-rereview.log`. Harness: `$D/work/t5-rereview/copy/run.sh`.
