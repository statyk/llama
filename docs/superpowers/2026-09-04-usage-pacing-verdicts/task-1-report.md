# Task 1 report: Raw failure capture in herder

## Status: DONE

## What was done

Followed the brief at
`.superpowers/sdd/2026-09-04-usage-pacing-phase1/task-1-brief.md` exactly,
step by step (TDD order, verbatim code from the brief, no deviations, no
scope additions).

1. **Read the brief and CLAUDE.md** for conventions (test command,
   `./.venv/bin/python -m pytest`, commit message style).
2. **Confirmed clean working tree** on branch `usage-pacing`
   (`git status` → nothing to commit).
3. **Step 1 — wrote the failing test**: created
   `packages/herder/tests/test_failures.py` verbatim from the brief (4
   tests: writes-the-whole-envelope, no-op-with-no-dir,
   never-raises-when-unwritable, each-capture-gets-its-own-file).
4. **Step 2 — verified it fails**: ran
   `./.venv/bin/python -m pytest packages/herder/tests/test_failures.py -q`.
   Got a collection error — `ImportError: cannot import name 'failures'
   from 'herder'` (module doesn't exist yet). This is the expected failure
   mode; the brief's exact wording ("ModuleNotFoundError") differs
   slightly from what pytest surfaces (an `ImportError` wrapping the
   missing submodule) because `herder/__init__.py` exists as a package —
   same underlying cause (module not present), same effect (collection
   fails), so treated as the expected failing state.
5. **Step 3 — wrote the implementation**: created
   `packages/herder/src/herder/failures.py` verbatim from the brief —
   `set_capture_dir(path: Path | None) -> None` (module-level
   `_capture_dir`) and `capture_failure(cmd: list[str], proc) -> Path |
   None` (no-op when capture dir unset, writes
   `cmd`/`exit_code`/`stdout`/`stderr` to a timestamped file named
   `{stamp}-{pid}-{monotonic_ns() % 1_000_000}.txt`, catches `OSError` and
   returns `None` rather than raising).
6. **Step 4 — verified it passes**: ran the same test file command again →
   `4 passed in 0.08s`.
7. **Checked for takeover sentinels** (`TAKEN_OVER`,
   `taken-over/t1`) — neither existed. Proceeded.
8. **Ran the full suite** from repo root:
   `./.venv/bin/python -m pytest -q` → `1652 passed, 7 deselected, 26
   warnings in 5.64s`. Matches the expected 1648 (baseline) + 4 (new
   tests) = 1652 exactly.
9. **Committed** `packages/herder/src/herder/failures.py` and
   `packages/herder/tests/test_failures.py` only (nothing else touched —
   `claude_cli.py` was not opened or modified, per scope) as
   `c81759d6af62e5b53f8804bffd0ecf3a62e66913` on `usage-pacing`, with the
   verified test command and its result stated in the commit body.

## Exact commands and output

```
$ ./.venv/bin/python -m pytest packages/herder/tests/test_failures.py -q
# before implementation:
ImportError: cannot import name 'failures' from 'herder' (.../herder/__init__.py)
1 error in 0.11s

# after implementation:
....                                                                     [100%]
4 passed in 0.08s

$ ./.venv/bin/python -m pytest -q
........................................................................ [ 65%]
...
1652 passed, 7 deselected, 26 warnings in 5.64s
```

## Files touched

- `packages/herder/src/herder/failures.py` (new, 48 lines)
- `packages/herder/tests/test_failures.py` (new, 51 lines)

## Commit

`c81759d6af62e5b53f8804bffd0ecf3a62e66913` — `feat(herder): capture the
full envelope of a failed claude invocation`

## Surprises

- The brief's Step 2 says to expect `ModuleNotFoundError`; pytest actually
  reports it as an `ImportError` during test collection (since `herder` is
  a package and `failures` is the missing submodule). Same root cause, no
  functional difference — noted here for the record, not treated as a
  deviation worth stopping over.

## Concerns

- **Filename collision risk in `capture_failure`, as specified.** The
  brief's ambiguity note pre-authorizes keeping
  `time.monotonic_ns() % 1_000_000` verbatim, and I did not change it.
  Flagging per that note: the modulus gives a ~1-in-1,000,000 collision
  window (in monotonic-ns space) per process per second-resolution
  timestamp bucket. In the sole-writer-per-process, low-frequency-failure
  use case this targets (one `claude -p` failure being captured at a
  time, not a tight loop), this is very unlikely to bite in practice, but
  it is not collision-proof the way a uuid4 or an atomic counter would
  be. The brief's own test (`test_each_capture_gets_its_own_file`) only
  exercises two sequential calls, which is not enough to expose the
  window even if it existed. Not changed, per explicit instruction — just
  noted for whoever owns the pacing feature going forward.
- No other concerns. The implementation is exactly as specified, scope
  was held to the two named files, `claude_cli.py` was not touched, and
  `herder` still imports nothing from `llama`/`emcee` (this file has no
  imports beyond `os`, `time`, `pathlib`).

---

## Fix round 1 (code-quality findings 1 and 4)

**Status: DONE**

Verdict reviewed: `.superpowers/sdd/2026-09-04-usage-pacing-phase1/task-1-quality-verdict.md`.
Spec-compliance review had already passed with zero scope creep; this round
addressed only the two Important findings the orchestrator scoped in
(findings 1 and 4). Findings 2, 3, 5, 6 (Minor) were left untouched per
explicit instruction, including `time.monotonic_ns() % 1_000_000`, which
still stands exactly as specified in the original brief.

### Finding 1 — "never raises" was not actually true

Two escapes existed under the old `except OSError`:
- `path.write_text(...)` had no `encoding=`, so it used the locale
  encoding; non-ASCII backend output under a non-UTF-8 locale raises
  `UnicodeEncodeError` (a `ValueError`), which sails past `except OSError`.
- The narrow handler generally: any non-`OSError` escape (the reviewer
  also named `' '.join(cmd)`'s latent `TypeError` on a `PathLike` argv
  element) was unguarded.

Fix applied:
- `path.write_text(..., encoding="utf-8", errors="replace")` — matches the
  repo's `workspace.atomic_write_text` precedent, and `errors="replace"`
  covers stray surrogates from a mis-decoded subprocess read, not just
  plain non-ASCII text.
- Widened `except OSError` to `except Exception`, using the repo's
  existing defensive-noqa idiom from `packages/llama/src/llama/jerrybase.py:128`:
  `except Exception:  # noqa: BLE001 - defensive: a capture problem must
  never mask the backend failure being captured`.

### Finding 4 — the "never raises" test didn't test the write path

`test_capture_never_raises_when_the_dir_is_unwritable` blocks `mkdir` (an
`OSError`, the arm that already worked) and never reaches `write_text`, so
it passed unchanged even with the handler narrowed to
`except FileExistsError`.

Added `test_capture_never_raises_when_the_write_itself_fails` to
`packages/herder/tests/test_failures.py`: monkeypatches `Path.write_text`
to raise `ValueError("simulated encoding failure")`, then asserts
`capture_failure(...) is None` with no exception escaping.

**Verified the new test is load-bearing, per the orchestrator's
instruction**: manually narrowed `capture_failure`'s handler back to
`except OSError:` (via a temp backup + `sed`), re-ran the covering test
file, watched `test_capture_never_raises_when_the_write_itself_fails` fail
with `ValueError: simulated encoding failure` escaping from inside
`capture_failure` (the other 4 tests stayed green), then restored the
`except Exception` handler from the backup and re-ran — back to 5 passed.

### Exact commands and output

```
$ ./.venv/bin/python -m pytest packages/herder/tests/test_failures.py -q
.....                                                                    [100%]
5 passed in 0.37s

# handler manually narrowed back to `except OSError:` to prove the new test is load-bearing:
$ ./.venv/bin/python -m pytest packages/herder/tests/test_failures.py -q
...F.                                                                    [100%]
FAILED packages/herder/tests/test_failures.py::test_capture_never_raises_when_the_write_itself_fails
1 failed, 4 passed in 0.07s

# handler restored to `except Exception:  # noqa: BLE001 - ...`:
$ ./.venv/bin/python -m pytest packages/herder/tests/test_failures.py -q
.....                                                                    [100%]
5 passed in 0.34s

$ ./.venv/bin/python -m pytest -q
1653 passed, 7 deselected, 26 warnings in 5.40s
```

(1653 = prior 1652 baseline + 1 new test, matching the fix's scope exactly.)

### Files touched

- `packages/herder/src/herder/failures.py` (2 lines changed: `write_text`
  call gains `encoding`/`errors`, `except OSError` → `except Exception`
  with a noqa + comment)
- `packages/herder/tests/test_failures.py` (1 new import, 1 new test —
  17 lines added)

### Commit

`05d6279dbc467adb794f31400ed1b494b3c38052` — `fix(herder): make
capture_failure's "never raises" contract actually hold`

### Concerns

None. Diff reviewed before commit (`git diff`) and confirmed it touches
only the two fixes plus the one new test — no incidental changes to
findings 2, 3, 5, 6, and no changes outside the two named files.
