# Task 1 — Spec-compliance verdict

**Reviewer:** spec-compliance (read-only)
**Range reviewed:** `9f4440e..c81759d` (single commit `c81759d`)
**Brief:** `.superpowers/sdd/2026-09-04-usage-pacing-phase1/task-1-brief.md`

## Spec verdict: ✅ PASS

The implementation is **byte-identical** to the brief's two literal code
blocks. Verified mechanically, not by eye: the two ```python fences were
extracted from the brief and `difflib`-compared against the committed files
— both reported IDENTICAL, zero lines of divergence. Scope is exactly the
two files named; `claude_cli.py` was not touched (its last-touching commit
is still `2882773`, pre-dating this range).

---

## Requirement-by-requirement

| # | Requirement (from the brief) | Where met | Note |
|---|---|---|---|
| 1 | Create `packages/herder/src/herder/failures.py` | `packages/herder/src/herder/failures.py:1-48` | New file, 48 lines, matches brief verbatim. |
| 2 | Create `packages/herder/tests/test_failures.py` | `packages/herder/tests/test_failures.py:1-51` | New file, 51 lines, matches brief verbatim (4 tests). |
| 3 | Consumes nothing | `failures.py:14-16` | Imports are `os`, `time`, `pathlib.Path` only — stdlib, no herder-internal or cross-package imports. |
| 4 | Produces `set_capture_dir(path: Path \| None) -> None` | `failures.py:21-24` | Exact signature. Normalizes via `Path(path)`; `None` clears. |
| 5 | Produces `capture_failure(cmd: list[str], proc) -> Path \| None` | `failures.py:27-48` | Exact signature. Importable by Task 3 as `from herder import failures`; no `__init__.py` edit needed (and none made). |
| 6 | No-op returning `None` when no capture dir set | `failures.py:33-34` | Guard is the first statement. |
| 7 | Writes cmd / exit_code / stdout / stderr envelope | `failures.py:39-45` | Format `cmd: {' '.join(cmd)}`, `exit_code: …`, `--- stdout ---`, `--- stderr ---`. Satisfies all four assertions in `test_capture_writes_the_whole_envelope`. |
| 8 | One file per capture (timestamp + pid + monotonic suffix) | `failures.py:37` | `f"{stamp}-{os.getpid()}-{time.monotonic_ns() % 1_000_000}.txt"` — brief's exact scheme, unchanged. |
| 9 | Never raises; capture failure must not mask backend failure | `failures.py:35-48` | `try` wraps the whole body; `except OSError: return None`. `mkdir(parents=True, exist_ok=True)` against an existing *file* re-raises `FileExistsError` (an `OSError`), so `test_capture_never_raises_when_the_dir_is_unwritable` exercises a real path, not a vacuous one. |
| 10 | Step 1 → failing test first (TDD order) | report §4 | Reported `ImportError: cannot import name 'failures' from 'herder'` at collection before implementation. See "cannot verify" below. |
| 11 | Step 4 → `4 passed` | report "Exact commands and output" | `4 passed in 0.08s`. |
| 12 | Step 5 → commit both files, repo message style | `c81759d` | `feat(herder): capture the full envelope of a failed claude invocation` — correct `type(scope): subject`. `git diff --stat 9f4440e..c81759d` shows exactly the two files, 99 insertions, 0 deletions. |
| 13 | Python 3.11+, no new third-party deps | `failures.py:14-16` | stdlib only. `pyproject` untouched — the diff adds no dependency. |
| 14 | Tests offline, deterministic, no real `$HOME`, no sleeping | `test_failures.py` | All four use `tmp_path` or no filesystem; `FakeProc` replaces any subprocess; no network, no `sleep`, no `$HOME`. Module global is reset in `finally` in every test that sets it, so no cross-test leakage. |
| 15 | `herder` must not import `llama` or `emcee` | grep over `packages/herder/src/` | Zero hits. Also still guarded by the pre-existing `packages/herder/tests/test_no_llama_imports.py`, which the full suite ran. |
| 16 | New tests actually collected by the full suite | `pytest.ini` `testpaths` | `packages/herder/tests` is listed, so `test_failures.py` runs under the plain suite command — consistent with the reported 1648 → 1652 delta of exactly 4. |

---

## Scope creep

**None.** `git diff --stat 9f4440e..c81759d` is exactly:

```
 packages/herder/src/herder/failures.py | 48 ++++++++++++++++++++++++++++++++
 packages/herder/tests/test_failures.py | 51 ++++++++++++++++++++++++++++++++++
```

No `claude_cli.py` change, no `__init__.py` export, no config/CLI wiring, no
docs, no `pyproject` edit. The commit body even states "Not yet wired into
claude_cli.py -- that's Task 3", which is the correct boundary.

(Note for the record: `HEAD` is one commit ahead of the reviewed range —
`ecd2fc1 docs: fold the preflight rulings into the usage-pacing plan and
spec`, touching only the plan and spec markdown. It is outside `9f4440e..
c81759d` and is not Task 1 work; flagged only so the range is unambiguous.)

---

## Exact-value fidelity

The brief carries literal code for both files. Divergence was checked
mechanically (extract both fenced blocks, `difflib.unified_diff` against the
committed files):

- `failures.py` — **IDENTICAL**, including the module docstring, the
  `_capture_dir` name, both function docstrings, the `except OSError` arm,
  and the filename scheme `{stamp}-{pid}-{monotonic_ns % 1_000_000}.txt`.
- `test_failures.py` — **IDENTICAL**, including the `FakeProc` shape, all
  four test names, and the inline comment in the unwritable-dir test.

No naming, structural, message-format, or filename-scheme divergence exists.
Nothing to classify as benign-vs-defect on the fidelity axis.

Two properties of the *specified* code, reported for the record — neither is
a compliance defect, since deviating from the brief's literal code would
itself have been the violation:

- **`% 1_000_000` is not collision-proof.** `test_each_capture_gets_its_own_file`
  passes only because two sequential calls almost never land an exact
  1 ms multiple apart in monotonic-ns space. This is a theoretical flake in
  a test the brief mandated verbatim; a uuid4 or counter would be
  collision-proof. The implementer flagged it and correctly did not change
  it. Owner decision, not a Task 1 defect.
- **`except OSError` is narrower than the "never raises" docstring.** A
  non-`OSError` — e.g. `' '.join(cmd)` raising `TypeError` on a non-str
  element — would propagate and mask the backend failure the docstring
  promises to protect. Harmless for Task 3's `list[str]` call sites; worth
  a glance from code-quality, not a spec deviation.

---

## ⚠️ Cannot verify from diff

- **Full-suite result (`1652 passed, 7 deselected`).** I was instructed not
  to re-run the suite. The claim is internally consistent (1648 baseline + 4
  new = 1652; `pytest.ini` `testpaths` confirms `packages/herder/tests` is
  collected; `addopts = -m 'not live'` explains the deselections), and the
  commit body repeats it. Accepted on the implementer's evidence.
- **TDD ordering (Step 1 before Step 3).** Both files landed in one commit,
  so the diff cannot show that the test was red first. The implementer's
  reported red-state output is the only evidence. Note the disclosed
  wording difference: the brief predicted `ModuleNotFoundError`, pytest
  surfaced `ImportError: cannot import name 'failures' from 'herder'`. Same
  root cause (submodule absent from an existing package), same effect
  (collection error). **Benign**, and correctly disclosed rather than
  papered over.
- **The report's claim that "the brief's ambiguity note pre-authorizes
  keeping `time.monotonic_ns() % 1_000_000` verbatim."** No such note exists
  in `task-1-brief.md` as delivered to me; it may have come from the
  dispatch prompt, which I do not have. Immaterial either way — verbatim
  reproduction of the brief's code is the compliant outcome regardless of
  whether a note blessed it.
- **Runtime behaviour** was reasoned about from source (notably the
  `mkdir(exist_ok=True)`-over-a-file → `FileExistsError` path), not executed.

---

## Findings

| Severity | Finding |
|---|---|
| Minor | `% 1_000_000` filename suffix is not collision-proof; `test_each_capture_gets_its_own_file` passes probabilistically, not by construction. Specified by the brief, deliberately unchanged. |
| Minor | `except OSError` is narrower than the "Never raises" docstring (a `TypeError` from `' '.join(cmd)` would escape). Specified by the brief; benign for Task 3's call sites. |

No Critical or Important findings.
