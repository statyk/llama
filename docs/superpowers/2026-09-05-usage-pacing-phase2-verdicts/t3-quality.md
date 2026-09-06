# Task 3 — code-quality review (`read_usage`, the subprocess reader)

**Verdict: Changes requested** — one Important test gap (`_cli_runner`, 9/9 mutations
survive, and the seam the implementer says does not exist is already used four times in
this same package), plus four Minors. The implementer's own work is good: its 9-mutation
sweep reproduced exactly, its five fix-round closures are real, and its M3/M4 equivalence
argument holds under adversarial testing.

## Method (harness proven before any result was trusted)

Private copy at `$D/work/t3-quality/{src,tests}`, imported via `PYTHONPATH` shadowing;
proved with a planted `QUALITY_SENTINEL` read back from
`.../work/t3-quality/src/herder/usage.py` (logged). `python -B`, `-p no:cacheprovider`,
copied `__pycache__` deleted. Control run green (17 passed). Harness
`$D/work/t3-quality/mutate.py` asserts each anchor is unique, reverts after every
mutation, and asserts byte-identity at the end. The worktree was never written to and its
suite was never run; no commits were made (mandate 4 — a reviewer makes none).

## 1. The implementer's sweep: verified, not trusted

All nine re-run against the post-fix test file. Result is identical to its table —
M1, M2, M5, M6, M7, M8, M9 **caught**; M3, M4 **survive**. Five more of my own on
`read_usage`, all **caught**: dropping `JSONDecodeError` from the except tuple; the key
typo `result` → `results`; ignoring the injected `runner`; returning a non-`str` `text`
instead of `None`; and short-circuiting `parse_usage_text` to `return None`. The three
fix-round tests are load-bearing, not decorative, and `read_usage`'s ladder is now well
pinned.

## 2. M3/M4 adjudication — equivalent mutants, no finding

The claim holds, and holds against more than the declared contract. I enumerated every
falsy Python value against `json.loads`: `None`/`0`/`0.0`/`False`/`[]`/`{}`/`set()`/`()`
raise `TypeError`; `""`/`b""`/`bytearray(b"")` raise `JSONDecodeError`. Both arms are
already caught at `usage.py:124` with the identical net result. **No value that
`_cli_runner` can return** — `proc.stdout`, a plain `str` under `text=True` — and no value
permitted by the documented `str | None` runner contract distinguishes `if not raw` from
its absence. The single distinguishing input is a `str` subclass overriding `__bool__` to
`False`, which is unreachable. This is an equivalent mutant; chasing it would be wasted
work, and the implementer was right to report rather than "fix" it. **No change requested.**

## 3. Findings

### Important

**F1. `usage.py:90-104` — `_cli_runner` has zero test coverage, and the "no seam" premise
is wrong.** All nine mutations I applied **survive** the suite: corrupting the `/usage`
prompt, dropping `--output-format json`, dropping `*ISOLATION_ARGS`, dropping the
`returncode == 0` check, dropping `timeout=`, `capture_output=False`, dropping
`cwd=_neutral_cwd()`, narrowing the except tuple to `OSError`, and dropping `text=True`.
The report calls this unavoidable ("no seam short of monkeypatching `subprocess.run`
globally"). That is not so: `packages/herder/tests/test_claude_cli.py:14-21` defines
`patch_run(monkeypatch, proc, seen)` doing exactly this, and lines 149, 191 and 208 already
use it to pin `ISOLATION_ARGS` and the neutral cwd for the *other* call site. `monkeypatch`
is scoped and auto-reverted, spawns nothing, and is offline and deterministic — it violates
no global constraint. The isolation flags carry their own load-bearing comment
(`claude_cli.py:30-37`) and are pinned for `ClaudeCLIProvider` but not for this second
consumer of them.

Suggested: two tests in `test_usage.py` reusing that pattern —

```python
def test_cli_runner_uses_the_same_isolation_and_neutral_cwd(monkeypatch):
    seen = {}
    def fake_run(cmd, **kw):
        seen.update(cmd=cmd, **kw)
        return types.SimpleNamespace(stdout="OUT", stderr="", returncode=0)
    monkeypatch.setattr(usage.subprocess, "run", fake_run)
    assert usage._cli_runner() == "OUT"
    assert seen["cmd"][:5] == ["claude", "-p", "/usage", "--output-format", "json"]
    assert "--strict-mcp-config" in seen["cmd"]
    assert json.loads(seen["cmd"][seen["cmd"].index("--settings") + 1]) == {"disableAllHooks": True}
    assert seen["capture_output"] and seen["text"] and seen["timeout"] == 60
    assert seen["cwd"] is not None and not (Path(seen["cwd"]) / "CLAUDE.md").exists()

def test_cli_runner_discards_stdout_on_a_nonzero_exit(monkeypatch): ...  # returncode=1 -> None
```

That closes seven of the nine survivors. (`text=True` and the except tuple can be added
with a `TimeoutExpired`-raising fake if wanted.)

**Live confirmation, offered as evidence not as a test:** I ran the real `_cli_runner()`
once by hand. It returned a str in **1.69 s**, and `read_usage()` produced
`five_hour=Meter(46, 2026-09-06T02:19Z)`, `seven_day=Meter(12, …)`,
`per_model={'Fable': …}`. So the argv is accepted as written (flags after a positional
prompt are fine), the envelope shape matches, and the 60 s timeout has ~35x headroom over
the measured call — **the code is correct; only its pinning is missing.** That also settles
the prompt's timeout question: 60 s is defensible (vs `claude_cli`'s 900 s, which covers
real inference; this is a 0-turn local read). Ignoring `stderr` is likewise right — an
exit-0 `claude` that chatters on stderr still yields its stdout envelope.

### Minor

**F2. `usage.py:126` — no `is_error` guard, unlike the sibling call site.** `claude_cli.py:139`
treats `is_error: true` at `returncode == 0` as a failure, and that shape is *measured real*
in this repo (`test_claude_cli.py`'s `CLOSED_MID`, exercised at `returncode=0`). `read_usage`
reads `result` from such an envelope unconditionally. In practice it is safe — I verified an
`API Error: …` result yields `None` because `_SESSION_RE` does not match — but the module
already refuses to trust exit-0 numbers when a banner says they are stale (`STALE_MARKER`),
and this is the same class of lie one condition away. Suggest either
`if data.get("is_error"): return None` after line 126, or one comment line recording that
the regexes fail closed and the guard is deliberately omitted.

**F3. `test_usage.py:129` — `import json` sits mid-file**, ~128 lines below the other
imports (E402 shape; no linter is configured, so nothing catches it). Move it to line 1-2
beside `from datetime import …`. Same for the `types`/`pathlib` imports F1 would add.

**F4. `test_usage.py:143` — the name promises more than the body checks.**
`test_read_usage_degrades_to_none_on_every_failure_shape` omits the stale banner, which
`read_usage`'s own docstring (`usage.py:112`) lists among the failures it collapses. I
verified the behaviour is right (`_envelope("Showing last-known usage\nCurrent session: 23%
used\n")` → `None`), so this is one tuple entry, not a bug — but as written the docstring
names a case no `read_usage` test exercises, and it is the one failure shape where the
command *succeeds*.

**F5. `usage.py:90, 107` — two small consistency nits.** (a) `_cli_runner`'s `binary` and
`timeout_s` parameters are never passed by any caller — `read_usage` invokes `runner()`
with no arguments — so they are YAGNI today; F1's test would at least pin their defaults.
(b) `_cli_runner` has no return annotation and `read_usage`'s `runner` has no type, while
the rest of the module is annotated: `def _cli_runner(...) -> str | None` and
`runner: Callable[[], str | None] | None = None`.

## 4. Checked and clean

Docstrings match behaviour (including the "stale banner" claim, verified through
`read_usage`, not just the parser). `except (subprocess.SubprocessError, OSError)` is
correctly *broader* than `claude_cli`'s, which is right under a never-raise contract; the
outer `except Exception` catches no `BaseException` so Ctrl-C still propagates, and its
`noqa` carries a reason. No duplication with `claude_cli` — the isolation primitives are
imported, not re-derived — and the function-local import is per the brief. No dead code
beyond F5(a); `json`/`subprocess`, imported unused in Task 2, are now used. No tautological
assertions among the six new tests; `test_read_usage_passes_now_through_to_the_parser`
genuinely pins the kwarg (M9 goes red without it).
