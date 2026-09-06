# Task 3 — SPEC-COMPLIANCE review (`read_usage`, range `6901427..7b3e474`)

## Verdict: **Spec ✅**

The diff implements Task 3's brief verbatim — `_cli_runner` and `read_usage` are
byte-identical to the code the brief mandated, the three mandated tests are
present verbatim, and nothing from Task 4+ appears. The three added tests are
legitimate pinning, not scope creep. One **Important** finding remains, and it is
a gap in the *brief*, not in the implementation.

## Requirement checklist

| Requirement | Status | Evidence |
|---|---|---|
| Produces `usage.read_usage(runner=None, now=None) -> UsageReading \| None` | ✅ | `usage.py:107` — exact signature |
| `runner` is a zero-arg callable returning `str \| None` | ✅ | called as `runner()` at `usage.py:117`; `_cli_runner()` takes only defaulted args |
| Private `_cli_runner` produced | ✅ | `usage.py:90` |
| Never raises: missing binary | ✅ | `except (subprocess.SubprocessError, OSError)` at `usage.py:102` (FileNotFoundError ⊂ OSError) |
| Never raises: non-zero exit | ✅ | `usage.py:104` |
| Never raises: malformed envelope | ✅ | `usage.py:122-125` |
| Never raises: `result` not a string / absent | ✅ | `usage.py:126-128`; `.get` returns None when absent |
| Never raises: unrecognizable prose | ✅ | delegated to `parse_usage_text` (Task 2), which returns None |
| Never raises: stale banner | ✅ | via `parse_usage_text`'s `STALE_MARKER` check (`usage.py:67`) — read_usage owns no stale logic of its own, correctly |
| Never raises: runner that throws | ✅ | bare `except Exception` at `usage.py:118`; pinned by `test_read_usage_never_raises_when_the_runner_explodes` |
| No test spawns a real subprocess | ✅ | every `read_usage` call in `test_usage.py` injects a runner; the default-runner test monkeypatches `usage._cli_runner`, never `subprocess` |
| `_cli_runner` uses `ISOLATION_ARGS`, `_subprocess_env()`, `_neutral_cwd()` | ✅ in code, ❌ unenforced by tests | `usage.py:96-101`; see Finding 1 |
| `claude_cli` import stays inside the function | ✅ | `usage.py:96` |
| Nothing from Task 4+ (`decide()`, `pacing_state`, CLI wiring) | ✅ | `git diff --name-status 6901427..7b3e474` = 2 files, both Task 3's |
| `herder` does not import from `llama` | ✅ | grep over `packages/herder/src` returns nothing |
| `openrouter.py` untouched | ✅ | not in the diff |
| No constant swept or retuned | ✅ | Task 2's constants unchanged; `timeout_s=60` is new, not a retune (and is right for a measured 0.5–3 s call vs `claude_cli`'s 900 s inference timeout) |

Spec cross-check (`…phase2-design.md:123-155`): the four documented `None`
conditions (non-zero exit, unparseable/missing `result`, no `Current session:`
line, stale banner) are all reachable and all covered. `read_usage(runner, now)`
matches the spec's declared shape.

## Implemented beyond the brief

Three tests + an explanatory comment block in `test_usage.py`
(`test_read_usage_defaults_to_the_module_level_cli_runner`,
`…degrades_to_none_on_malformed_envelope_shapes`, `…passes_now_through_to_the_parser`).
**Legitimate pinning, not scope creep**: each closes a surviving mutation on
`read_usage`'s own failure ladder, no production code was altered to accommodate
them, and they stay inside Task 3's surface. I re-ran the implementer's sweep
independently against a private copy (`$D/work/t3-spec/`, shadowing verified with
a planted sentinel; the worktree was never modified — `git status` clean) and
reproduced its post-fix table exactly: M1/M2/M5/M6/M7/M8/M9 CAUGHT, M3/M4
SURVIVED.

Nit (Minor, no action needed): `test_read_usage_degrades_to_none_on_malformed_envelope_shapes`
feeds `lambda: 12345`, violating the declared `str | None` runner contract. It is
defensible — it is the only input that exercises the `TypeError` arm of the
`json.loads` except tuple (mutation M6), which is otherwise dead code.

## Findings

### 1. Important — `_cli_runner` is entirely unpinned, and a subprocess-free seam exists (`usage.py:90-104`)

**This is a gap in the brief, not an acceptable limitation.** Answering the
question directly: the brief's own binding constraint is that `_cli_runner` use
`ISOLATION_ARGS`, `_subprocess_env()` and `_neutral_cwd()` so the operator's
hooks/MCP/CLAUDE.md cannot alter the output. The code satisfies it; *nothing in
the suite holds it there.* I swept seven mutations of `_cli_runner`'s body
against the shipped tests — **all seven survived**:

| Mutation | Result |
|---|---|
| M10 `except (SubprocessError, OSError)` → `except OSError` | SURVIVED |
| M11 drop the `returncode == 0` check | SURVIVED |
| M12 drop `*ISOLATION_ARGS` from `cmd` | SURVIVED |
| M13 drop `cwd=_neutral_cwd()` | SURVIVED |
| M14 drop `--output-format json` | SURVIVED |
| M15 drop `timeout=timeout_s` | SURVIVED |
| M16 drop `env=_subprocess_env()` | SURVIVED |

The implementer's claim that the brief "gives no seam short of monkeypatching
`subprocess.run` globally" is not quite right: `usage.py` does `import subprocess`
at module scope, so `monkeypatch.setattr(usage.subprocess, "run", fake)` is a
local, auto-reverted seam that **spawns no process** and violates no global
constraint. I wrote a 20-line test using it and re-ran the same sweep: **all
seven mutants go red**, with the rest of the herder suite still green. Proof of
concept in `$D/work/t3-spec/copy/tests/test_probe_runner.py` (private copy — not
added to the worktree).

Why this matters beyond coverage hygiene: `read_usage`'s outer `except Exception`
contains any *crash* in `_cli_runner`, so the risk is not a failure — it is
**silent inertness**. Drop `--output-format json` or the returncode check and
`read_usage` returns `None` forever; phase 2's proactive gate then never fires
and the run behaves exactly as phase 1, with no error anywhere. That is the same
class of silent regression this project's memory flags repeatedly. Recommend the
orchestrator add this test — as a Task 3 follow-up or folded into a later test
task — rather than closing the phase with the isolation constraint unpinned.
Not a blocker for Task 3: the brief prescribed the implementation verbatim and
the implementer was right not to invent a seam it did not ask for. It flagged the
gap in its own report, which is the correct behavior.

### 2. Not a finding — M3/M4 are genuinely inert (answering the second question)

The implementer's reasoning is **correct**, and stronger than it claimed. The
runner contract is `str | None`, so the only falsy values in-contract are `None`
and `""`; `json.loads(None)` raises `TypeError` and `json.loads("")` raises
`JSONDecodeError`, both caught two lines below with the identical net result.
I checked exhaustively rather than by argument, over every falsy builtin
**including off-contract ones** — `None, "", 0, 0.0, False, [], {}, set(), (),
b"", bytearray(b"")` — and every one lands in the `(JSONDecodeError, TypeError)`
tuple. `json.loads` accepts only str/bytes/bytearray, and no falsy member of
those three parses. So no input distinguishes `if not raw: return None` from its
absence: M3/M4 are behavior-equivalent mutants, **not a test gap**, and no test
should be written to "close" them. The check is harmless defensive redundancy and
should stay as the brief wrote it (removing it would be a gratuitous deviation
from a verbatim mandate). Note M5 (`return raw`) *is* caught — the check's
*return value* is pinned even though its *presence* is not, which is the right
place for the line to be drawn.

### 3. Minor — `_cli_runner` does not close the child's stdin (`usage.py:99`)

The modeled call site (`claude_cli.py:121`) passes `input=prompt`, which closes
the child's stdin; `_cli_runner` passes the prompt positionally and supplies no
`input=`/`stdin=`, so the child inherits the parent's stdin. Under an unattended
run whose stdin is a pipe that never closes, `claude` could block until the 60 s
timeout. Consequence is bounded and safe — `TimeoutExpired` ⊂ `SubprocessError`
→ `None` → pacing degrades — so this is a latency nit, not a correctness bug.
`stdin=subprocess.DEVNULL` would remove it. Brief-mandated code; report, don't
unilaterally change.

### 4. Minor — `import json` at `test_usage.py:127`, mid-file (E402)

Brief-mandated verbatim. The repo ships no ruff/flake8 config and CI runs no lint
(`.github/workflows/` has only `release.yml`), so this is cosmetic only. Worth a
one-line cleanup at phase end; not worth deviating from the brief now.

## Could not verify from the diff

- **The full-suite result.** Per the isolation mandate I did not run the suite in
  the worktree; the implementer's `1766 passed, 7 deselected` is unverified by me.
  I ran only `packages/herder/tests/` against a private copy: **17 passed** in
  `test_usage.py` (11 from Task 2 + 6), 126 across the herder package.
- **`_cli_runner`'s real-world behavior.** No live `claude` invocation was made.
  The command shape (`claude -p /usage --output-format json …`) was checked by
  reading it against the spec's measured transcript (`…phase2-design.md:43-56`)
  and against `claude_cli.py:117-124`; it agrees with both. Whether the real
  binary honors a positional prompt beside `--output-format json` is asserted by
  the spec's measurement, not re-measured here.
- **`binary`/`timeout_s` configurability.** `_cli_runner` hardcodes `"claude"`.
  I confirmed this is not a regression — `resolve.py:65` constructs
  `ClaudeCLIProvider(model=model)` and never passes `binary`, so no configured
  binary path exists to honor. If Task 4+ introduces one, this becomes a defect.

## Process notes

- No commits made; the worktree was read-only throughout (`git status --porcelain`
  empty at HEAD `7b3e474`). All experiments ran against a private copy under
  `$D/work/t3-spec/`, with shadowing proven by a planted sentinel before any
  result was trusted, and the copy restored byte-identical afterward.
- Mandate 4 asks a reviewer to commit incrementally while also noting a reviewer
  should make no commits. **Finding:** I made none — the mandate's parenthetical
  governs. Nothing in a spec review produces a committable artifact.
