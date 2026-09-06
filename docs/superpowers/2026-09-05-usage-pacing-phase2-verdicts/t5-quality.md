# Task 5 — CODE-QUALITY review (`pacing_state.py`)

**Verdict: Changes requested.** The pure core (`observe`, `_valid_persisted_delta`)
is well made and genuinely well pinned. The problems are all in `record`/`read_state`:
the docstrings there make three load-bearing claims — never raises, read-modify-write,
under a lock — and **not one of the three is pinned by a test**. One of them is
outright false.

Paths below are `packages/llama/src/llama/{pacing_state.py}` and
`packages/llama/tests/test_pacing_state.py` in `/Users/shawn/projects/llama-wt-pacing2`.

---

## Sweep verification (I re-derived it and went well past it)

Private copy at `$D/work/t5-quality/copy`, PYTHONPATH-shadowed, import path proven by a
planted sentinel test that asserts `llama.__file__`/`herder.__file__`/`pacing_state.__file__`
all resolve inside the copy. `python -B -m pytest -p no:cacheprovider` with
`PYTHONDONTWRITEBYTECODE=1` and `__pycache__` cleared before every run; harness sanity-checked
in both directions (a no-op edit reports SURVIVED, `EWMA_ALPHA 0.4→0.5` reports CAUGHT); every
run's summary line asserted to contain `passed`/`failed`; source restored and diffed
byte-identical against the worktree after the sweep. The worktree is untouched
(`git status --porcelain` empty). No commits made.

**44 mutations: 30 caught, 14 survived** — 5 equivalent, **9 real gaps**.

| Survivor | What it does | Verdict |
| --- | --- | --- |
| M13 | EWMA rewritten as `α·d + (1−α)·prev` | equivalent (bit-identical here) |
| M16 | `_five` drops `if reading is not None` | **equivalent — the guard is dead code** |
| M23 | `_valid_persisted_delta` also accepts `str` | equivalent through the public surface (absorbed by `read_state`'s `except TypeError`) |
| M34 | drop `record`'s `root.mkdir` | **equivalent — implementer's adjudication CONFIRMED, see below** |
| M42 | `return read_state(root)` instead of `return state` | equivalent |
| M09 | seed branch `PacingState(delta, 1)` → `state.samples + 1` | real gap (finding 5) |
| M10 | seed condition narrowed to `... and state.samples == 0` | real gap (finding 5) |
| M17 | `getattr(reading, "five_hour", None)` → `reading.five_hour` | real gap (finding 7) |
| M28 | `data.get("per_show_delta")` → `.get(..., 0)` | real gap (finding 6) |
| M35 | **delete the `with file_lock(...)` entirely** | real gap (finding 3) |
| M36 | lock the state file itself instead of the `.lock` sidecar | real gap (finding 3) |
| M37 | **`observe(before, after, read_state(root))` → `observe(before, after, PacingState(None, 0))`** | real gap (finding 2) |
| M38 | move the read *outside* the lock (the exact TOCTOU the docstring warns about) | real gap (finding 3) |
| M43 | move the write *outside* the lock | real gap (finding 3) |

I wrote four small tests (verbatim text in the appendix) and re-ran the survivors: **8 of the
9 real gaps flip to CAUGHT**, suite stays green (26 passed). M17 is the ninth and is a
design point, not a missing assertion.

**Why the implementer's "0 unexplained survivors" was honestly arrived at and still wrong:**
all 14 of its mutations landed in `observe` / `_valid_persisted_delta` / `read_state`'s
validation — the parts the 21 tests were written against. `record`'s body was never mutated.
Every one of the four `record` mutations I tried survived.

### Adjudication of the claimed equivalent mutant (M34) — CONFIRMED equivalent

`llama/locks.py:22` runs `path.parent.mkdir(parents=True, exist_ok=True)` **before** the
`if fcntl is None` branch at line 23, so it holds on the non-POSIX degraded path too, and
`path.parent` for `root / (STATE_NAME + ".lock")` *is* `root`. `record`'s own `mkdir` at
`pacing_state.py:104` therefore cannot change any outcome, including the failure mode
(both raise the same error on an unwritable parent). Truly equivalent.
**Recommend leaving it in anyway**: `ledger.py:30` does the identical redundant mkdir one line
above its own `file_lock`, and `record`'s docstring explicitly claims to follow the ledger's
discipline. Matching the house pattern is worth more than deleting a no-op line.

---

## Findings

### Important

**1. `read_state` violates its own documented "Never raises" contract.**
`pacing_state.py:90` / `:92`. Measured, not theorised:

```
{"per_show_delta": 4.0, "samples": Infinity} -> !!! RAISED OverflowError
{"per_show_delta": 4.0, "samples": 1e309}    -> !!! RAISED OverflowError
{"per_show_delta": 4.0, "samples": NaN}      -> PacingState(None, 0)     # ValueError, caught
```

`int(float('inf'))` raises `OverflowError`, which is an `ArithmeticError` and so is not in the
`except (OSError, ValueError, TypeError, AttributeError)` tuple. The irony is precise: the
implementer hardened the *delta* field against exactly this non-standard JSON literal and wrote
`test_non_finite_persisted_delta_degrades_to_empty` for it, then left `samples` — parsed on the
very next line, out of the same decoded dict, reachable by the same corruption — to blow up.
Downstream this is called at `_execute`'s first line and in `llama pacing` (Task 7/8 briefs), so
it crashes a run before any work starts.

Fix (verified: raises→`PacingState(None, 0)`, 26 tests still green):
```python
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
```
plus a test alongside the existing non-finite one. A stricter alternative is to validate
`samples` symmetrically with `_valid_persisted_delta` — see finding 4, which the same change
would close.

**2. `record`'s read-modify-write — the reason it exists — is not pinned.**
`pacing_state.py:106`. M37 replaces `read_state(root)` with `PacingState(None, 0)` and all 21
tests pass. Under that mutant the EWMA never accumulates: every boundary re-seeds, `samples` is
permanently 1, and the "weighted toward recent shows without letting one outlier swing the gate"
property at line 23 is silently gone. `test_state_round_trips_through_disk` calls `record` once,
which is exactly the one call count that cannot see this.

Add (verified to catch it):
```python
def test_record_folds_into_the_persisted_estimate(tmp_path):
    ps.record(tmp_path, _r(10), _r(14))                 # seeds at 4.0
    out = ps.record(tmp_path, _r(14), _r(24))           # delta 10, smoothed onto 4.0
    assert out == ps.PacingState(4.0 + ps.EWMA_ALPHA * (10.0 - 4.0), 2)
    assert ps.read_state(tmp_path) == out
```

**3. The lock is not pinned at all — four separate mutations survive.**
`pacing_state.py:105`. Deleting the `with file_lock(...)` (M35), locking the data file instead of
the `.lock` sidecar (M36), hoisting the read out of the lock (M38), and dropping the write out of
it (M43) are all green against the 21 tests. Docstring lines 99-102 assert the discipline; nothing
enforces it. M38 is the sharpest: it *is* the lost-update race the docstring exists to prevent, and
M36 is a real footgun (`write_artifact` renames over that path, so the flock would be held on an
orphaned inode).

The repo already has both patterns for this — `test_pace_loop.py:251-259` monkeypatches
`cli.file_lock`, and `test_concurrency.py` forks four processes. The cheap one suffices; this
single test catches M35, M36, M38 **and** M43 (verified):
```python
def test_record_reads_and_writes_inside_the_lock(tmp_path, monkeypatch):
    events = []
    real_read, real_write, real_lock = ps.read_state, ps.write_artifact, ps.file_lock

    @contextmanager
    def _lock(path, **kw):
        events.append(f"enter:{path.name}")
        with real_lock(path, **kw):
            yield
        events.append("exit")

    monkeypatch.setattr(ps, "file_lock", _lock)
    monkeypatch.setattr(ps, "read_state", lambda root: (events.append("read"), real_read(root))[1])
    monkeypatch.setattr(ps, "write_artifact", lambda p, d: (events.append("write"), real_write(p, d))[1])
    ps.record(tmp_path, _r(10), _r(14))
    assert events == ["enter:pacing-state.json.lock", "read", "write", "exit"]
```

### Minor

**4. `samples` is validated far more loosely than `per_show_delta`, on the adjacent line.**
`pacing_state.py:90`. `int(data.get("samples", 0))` accepts `-3` (→ `samples=-3`), `true` (→ `1`,
the very `bool` coercion `_valid_persisted_delta` was written to refuse), `"7"` (→ `7`, the very
numeric string it refuses), and truncates `3.9` → `3`. All measured. Nothing consumes `samples`
today — `pacing.Progress` (`pacing.py:169`) carries only `per_show_delta` — so the blast radius is
currently zero, which is why this is Minor and not Important. But it is the same field whose
looseness produces finding 1, and the asymmetry reads as an oversight rather than a decision.
Either validate it symmetrically or add one line to the `read_state` docstring saying `samples` is
diagnostic-only and deliberately unvalidated.

**5. `PacingState(None, samples > 0)` is a state the module both produces and mishandles.**
`read_state` returns it (`:91`, deliberately, pinned by
`test_null_persisted_delta_preserves_the_samples_field`), and `observe`'s seed branch (`:52`) then
throws those samples away by hardcoding `1`. M09 (`→ state.samples + 1`) and M10 (narrowing the
seed condition so that state takes the smoothed branch and crashes on `None + ...`) both survive.
So the two functions disagree about what that state means and no test notices.
Cleanest resolution — and my recommendation — is to make the invariant
`per_show_delta is None ⟹ samples == 0` hold at the boundary, i.e. `read_state` returns
`PacingState(None, 0)` for a null delta regardless of the stored count (the state is then
unrepresentable and the seed branch is trivially correct); that inverts
`test_null_persisted_delta_preserves_the_samples_field`, whose own comment already concedes
`record()` never writes the combination. Failing that, pin the current behavior:
`assert ps.observe(_r(10), _r(14), ps.PacingState(None, 5)).samples == 1`.

**6. A state file missing the `per_show_delta` key is unpinned, in the dangerous direction.**
`pacing_state.py:87`. M28 (`data.get("per_show_delta", 0)`) survives — and a defaulted `0` is
precisely the "shows cost nothing → never pause" under-estimate the module docstring names as the
failure that walks a run into the wall. One line closes it:
```python
def test_a_state_file_without_the_delta_key_is_no_estimate(tmp_path):
    (tmp_path / "pacing-state.json").write_text('{"samples": 3}')
    assert ps.read_state(tmp_path) == ps.PacingState(None, 3)   # or (None, 0) per finding 5
```

**7. `_five`'s guard is dead and its `getattr` default is over-defensive.**
`pacing_state.py:33-34`. M16 proves `if reading is not None else None` cannot change an outcome —
`getattr(None, "five_hour", None)` is already `None`. M17 proves nothing exercises the `getattr`
default either: replacing the whole thing with `reading.five_hour` keeps all 21 tests green. On a
frozen dataclass (`herder.usage.UsageReading`) that default is not defence, it is a silencer — an
object of the wrong type becomes "no reading", and `observe` then declines the boundary quietly
instead of failing. Suggest `return reading.five_hour if reading is not None else None`, and
annotate `before`/`after` as `UsageReading | None` on `observe`/`record` (`:37`, `:96`) — `llama`
already depends on `herder`, and Task 7 imports `herder.usage` into `cli.py` anyway.

**8. The rollover guard silently does not apply when both readings have `resets_at is None`.**
`pacing_state.py:46`. `parse_reset` returns `None` on an unparseable reset clause
(`herder/usage.py:73`), and `None != None` is `False`, so two such readings straddling a real
window reset are folded in as an ordinary boundary. The error direction is an *over*-estimate,
which the module docstring names as the safe side (pauses early), so this is Minor — but it is an
unstated exception to a guard the docstring calls categorical. Either decline when either
`resets_at` is `None`, or add a sentence to the docstring saying the guard is best-effort and why
the residual is safe.

**9. `record`'s docstring misdescribes what the lock buys.** `pacing_state.py:100-102`: "two
concurrent runs would otherwise each fold the other's burn into the shared estimate" — that is the
account-wide-meter bias already documented at lines 6-10, and it happens with or without the lock.
What the lock actually prevents is a **lost update**: both runs read the same state, both write, and
one boundary vanishes. Suggest rewording to name the lost update, since a future reader who removes
the lock will check it against the wrong claim.

### Not findings — checked and clean

- **EWMA arithmetic.** Standard `prev + α(x − prev)`. Seed (`4.0`, `samples=1`), smoothed, zero
  delta (correctly folded, distinct from negative — good call, and pinned), delta equal to the
  current estimate (fixed point, follows from M11/M12 being caught), repeated application (covered
  once finding 2's test lands). `test_later_observations_are_smoothed` computes its expectation from
  independent literals (`4.0 + ALPHA * (10.0 - 4.0)`), not by calling the implementation — the
  formula mutations M11 and M12 are both caught, so it is not tautological.
  `samples` means "boundaries folded" on both branches, with the single exception in finding 5.
- **`_valid_persisted_delta` accepts exactly the right set.** Verified against `None` (accept),
  `0`/`0.0`/`-0.0` (accept), large int (accept), `4` → `4.0` coerced and pinned, numeric string
  (reject), `True`/`False` (reject — and the `isinstance(value, bool) or ...` ordering is the
  correct way to do it, not the `isinstance(x, (int, float))` trap), `NaN`/`Infinity` (reject),
  list/dict (reject). Mutations M18-M22 and M24 are all caught by one test each. **Both flagged
  judgment calls — the `bool` exclusion and the non-finite rejection — are correct and I would keep
  them**: `NaN >= 0` is `False` only by luck of IEEE ordering, and the docstring already records the
  reasoning.
- **Test hygiene.** No tautological assertions; no name promising more than its body. The four
  `except`-arm tests (`OSError`/`ValueError`/`TypeError`/`AttributeError`) each catch exactly their
  own arm — measured, not redundant. `test_ewma_alpha_is_pinned_at_point_4` is justified by the
  plan's "constants are policy, do not sweep". The only near-duplicate is
  `test_null_persisted_delta_is_the_valid_empty_sentinel`, largely subsumed by the samples-preserving
  test and by `test_state_round_trips_through_disk`'s first assertion; harmless, keep or drop. 21
  tests for a 110-line module is not padding here.
- Module docstring, `STATE_NAME`, atomic write via `write_artifact`, frozen dataclass, and the
  `import math`-for-`isfinite` are all appropriate. No dead code beyond findings 7 and the
  house-style mkdir.

---

## Appendix — reproducing

Harness: `$D/work/t5-quality/copy` (`run.sh <label> <old> <new>` mutates a pristine
`pacing_state.orig.py` into the copy, runs the suite, restores, and classifies).
Proposed tests: `$D/work/t5-quality/copy/tests/test_proposed_gaps.py`.
Full log: `$D/t5-quality/t5-quality.log`.
