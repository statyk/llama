# Task 3 — scoped re-review of fix round 1 (`7b3e474..816d00a`)

**Verdict: F1 ADDRESSED. No new breakage. Approve.**

Scope: the one open finding plus breakage introduced by the fix diff. Not a re-review of
the task.

## Harness (proven before any result was trusted)

Private copy of `packages/herder/{src,tests}` at `$D/work/t3-rereview/`, imported via
`PYTHONPATH` shadowing. Proof, logged: a planted `REREVIEW_SENTINEL` read back, with
`herder.usage.__file__` and `herder.claude_cli.__file__` both resolving **inside the
copy**, not the worktree and not the main checkout. `python -B`, `-p no:cacheprovider`,
copied `__pycache__` removed. Runner is `/Users/shawn/projects/llama/.venv/bin/python -B
-m pytest` — never `.venv/bin/pytest`. Mutation driver asserts each anchor is **unique**
before applying, reverts after every mutation, and asserts SHA-256 byte-identity at the
end (it did).

Control and catch both shown, so the check is known to have looked:

```
CONTROL: (0, '42 passed in 0.12s')          # tests/test_usage.py + tests/test_claude_cli.py
M1 corrupt /usage arg: RED (caught) | 1 failed, 41 passed
```

The worktree was never written to, its suite was never run, no commits were made
(mandate 4 — a reviewer makes none; I needed none). The real `claude` binary was never
invoked.

## 1. F1 — ADDRESSED (`packages/herder/tests/test_usage.py:207-267`)

All ten named mutations re-run **by me** against the post-fix suite, plus an eleventh
(the other direction of the except-tuple narrowing). Every one goes red; nothing survives.

| # | Mutation of `usage.py:90-104` | Result |
|---|---|---|
| M1 | `"/usage"` → `"/usagex"` | RED |
| M2 | drop `--output-format json` | RED |
| M3 | drop `*ISOLATION_ARGS` | RED |
| M4 | `return proc.stdout` (drop `returncode == 0`) | RED |
| M5 | drop `timeout=timeout_s` | RED |
| M6 | `capture_output=False` | RED |
| M7 | drop `cwd=_neutral_cwd()` | RED |
| M8 | drop `env=_subprocess_env()` | RED |
| M9a | `except (SubprocessError, OSError)` → `except OSError` | RED |
| M9b | …→ `except subprocess.SubprocessError` | RED |
| M10 | drop `text=True` | RED |

Each failed exactly one test, 41 of 42 still passing — the pins are targeted, not
collateral. M9b was not on the implementer's list and is the direction that would let a
missing binary escape; `test_cli_runner_survives_a_missing_binary` catches it, so both
arms of the tuple are independently load-bearing. The silent-inertness failure mode the
finding describes (a dropped flag → `read_usage` returns `None` forever → phase 2's gate
never fires, with no error anywhere) is now impossible to introduce without a red suite.

Also newly pinned, closing part of prior minor F5(a): `binary`'s default (`cmd[0] ==
"claude"`) and `timeout_s`'s default (`seen["timeout"] == 60`).

## 2. No test spawns a real subprocess — proven, not assumed

All five new tests patch via function-scoped `monkeypatch.setattr(subprocess, "run", …)`
(auto-reverted); one additionally patches `claude_cli._neutral_cwd` / `_subprocess_env`,
which works because `_cli_runner`'s import of them is function-local (`usage.py:95`).

Stronger evidence than reading: I ran the **whole** herder suite with a `conftest.py`
bombing `subprocess.run`, `Popen`, `check_output`, `call` and `os.system` —
**131 passed**. Negative control confirming the bomb was live: a planted test calling
`subprocess.run(["/bin/echo","hi"])` failed with `REAL PROCESS SPAWN ATTEMPTED`. So no
herder test reaches a real binary, and the unpatched helpers the other four tests do call
(`_neutral_cwd` → `tempfile.mkdtemp`, `_subprocess_env` → a dict) touch only the
filesystem.

## 3. Pattern reuse, no weakening or duplication

The new tests follow `test_claude_cli.py`'s `patch_run`/`FakeProc` shape
(`test_claude_cli.py:11-21`) rather than inventing a parallel mechanism. `patch_run`
itself is deliberately *not* imported because it captures only `cmd` and `input`, while
M5-M8/M10 need the full `**kwargs` — a justified local fake, not a fork of the approach.
Nothing the sibling call site pins is duplicated or weakened: `test_claude_cli.py`
continues to pin `ISOLATION_ARGS`' **content** (`:122-123`,
`--strict-mcp-config` + `{"disableAllHooks": true}`) and the neutral cwd for
`ClaudeCLIProvider`, and the new test pins that `usage.py` **reuses that same constant**
(tail-slice identity) rather than re-deriving flags. Those are complementary, and the
by-reference comparison is not a hole precisely because the content is pinned next door.

## 4. M3/M4 (`if not raw`) left untouched — confirmed

`git diff --stat 7b3e474..816d00a` touches **one file**, `packages/herder/tests/
test_usage.py`; no source changed, and `if not raw:` still stands at `usage.py:120`. No
new test targets it. Re-verified the equivalence holds post-fix: deleting the two lines
leaves the full herder suite **131 passed** — still an equivalent mutant, as declared.

## 5. New breakage from the fix diff

**None.** No Critical, no Important. The diff is test-only; the full herder suite is green
in my copy (131 passed) and the mutation driver restored the file byte-identically.

## 6. Deferred minors (out of scope, not requested changes)

- `_FakeProc` (`test_usage.py:207`) re-declares `test_claude_cli.FakeProc`'s three lines
  instead of importing it. Harmless; the two files are independent by design.
- `import subprocess` was correctly added at the top, but prior minor **F3** stands —
  `import json` still sits mid-file at `test_usage.py:129`.
- Prior minors **F2** (`is_error` guard), **F4** (stale-banner case absent from
  `..._on_every_failure_shape`) and **F5(b)** (missing return annotations) were not part of
  this round and remain open.
- The argv assertion assumes `ISOLATION_ARGS` is the **tail** of `cmd`; appending a flag
  after it would fail this test rather than the intended one. It would fail loudly, so this
  is a naming/locality nit only.

## 7. Housekeeping

Worktree `/Users/shawn/projects/llama-wt-pacing2` verified **clean** at `816d00a`
(`git status --porcelain` empty) — unmodified by this review. The throwaway copy at
`$D/work/t3-rereview/` has been deleted. `$D/TAKEN_OVER` and `$D/taken-over/t3-rereview`
checked before each write batch; neither exists.

## Closing verdict

**F1 — ADDRESSED** (`packages/herder/tests/test_usage.py:207-267`). Independently
re-verified: 10/10 named mutations red, plus an eleventh the implementer did not claim.
No new Critical or Important breakage from the fix diff. Task 3 is clear to proceed.
