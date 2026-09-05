# Task 1 — code-quality verdict: `herder/failures.py`

**Verdict: Changes requested** (small, precisely bounded: two one-line source
fixes plus one test). The design is right, the module is the right size, it
fits the package, and nothing in it is speculative. What blocks a clean
approval is that the *one* promise this function makes — "Never raises" — is
not actually kept on every path, and the test that claims to prove it only
exercises the arm that already works.

Scope reviewed: commit `c81759d`, files
`packages/herder/src/herder/failures.py` (48 lines) and
`packages/herder/tests/test_failures.py` (51 lines). Read-only review; no
edits, no commits, suite not re-run (judged from the implementer's report).

First, a note on the review prompt: it flags `time.monotunic_ns()` as a
possible typo. **The diff spells it `time.monotonic_ns()` correctly** — there
is no typo, and the module is importable (the report's `4 passed` and the
1652-test full suite corroborate).

---

## Correctness

### Finding 1 — `capture_failure` can raise, and does so on a realistic path. (Important)

The docstring says "Never raises" without qualification; the handler is
`except OSError`. Everything inside the `try` was checked statement by
statement. Two escapes:

**(a) `path.write_text(...)` has no `encoding=`, so it uses the locale
encoding.** Python 3.11 resolves `encoding=None` to `locale.getencoding()`.
The payload here is arbitrary `claude -p` output, which routinely contains
non-ASCII (curly quotes, em dashes, "…", occasionally emoji). Under a
non-UTF-8 locale — `LC_ALL=C` with `PYTHONCOERCECLOCALE=0`, a latin-1
`LANG`, a stripped-down container or launchd/cron environment — that raises
`UnicodeEncodeError`, which is a `ValueError`, **not** an `OSError`. It sails
straight through the handler.

The consequence is exactly the one the module's own docstring says must never
happen: the exception escapes from inside the backend's failure path and
masks (or at minimum buries, mid-`except`) the `HerderError` being captured.
An operator debugging a session-limit refusal would get a Unicode traceback
instead of the refusal.

This is also a divergence from the repo's own idiom:
`llama/workspace.py:atomic_write_text` pins UTF-8 explicitly
(`text.encode()`). (`llama/cli.py:241`'s `failure_path.write_text(...)` does
not — so the precedent is mixed — but that one is not documented as
never-raising, and it is not called from inside an exception handler in a
long-running station process.)

Fix: `path.write_text(..., encoding="utf-8", errors="replace")`. `errors`
matters as much as `encoding` here: a capture is a diagnostic dump of
untrusted bytes, and a lone surrogate from a mis-decoded subprocess read
would still raise under a bare `encoding="utf-8"`.

**(b) `' '.join(cmd)` raises `TypeError` if any argv element is not a `str`.**
`subprocess` accepts `PathLike` in argv, so a caller that passes
`ClaudeCLIProvider(binary=Path(...))` — legal today, the parameter is only
annotated `str` — would make every capture blow up. `TypeError` is not an
`OSError` either. Today's single call site
(`claude_cli.py:115`) builds an all-`str` list, so this is latent rather
than live, but it costs nothing to close.

**Recommended shape** — keep the narrow handler for the expected case if you
like, but the absolute claim needs an absolute guard:

```python
    except Exception:
        return None
```

A blanket `except Exception` is normally a smell; here it is the
specification. The function's entire contract is "a capture problem must
never mask the backend failure being captured", and any narrower handler is
a list of the failure modes someone thought of. If a narrow handler is
preferred for readability, `except (OSError, ValueError, TypeError)` covers
every escape I could identify — but I'd argue the blanket form plus a comment
saying *why* it is blanket is the more honest code, and it is what the
docstring already promises.

### Non-issues, checked and cleared

- `_capture_dir.mkdir(parents=True, exist_ok=True)` — `FileExistsError`,
  `NotADirectoryError`, `PermissionError` are all `OSError`. Covered.
- `time.strftime("%Y%m%dT%H%M%S")` — cannot raise here.
- `getattr(proc, 'stdout', '') or ''` — the `or ''` correctly normalizes
  `None` (which is what `subprocess.TimeoutExpired.stdout` and a
  non-`capture_output` run give you). If a future caller passes bytes, the
  f-string renders `b'...'` — ugly, not an exception.
- `set_capture_dir(Path(path))` can raise `TypeError` on a nonsense argument,
  but that is a startup-time configuration error and failing loudly there is
  correct. No finding.
- `herder` imports nothing from `llama`/`emcee` (stdlib only). Constraint met.
- No new third-party dependency. Constraint met.

---

## Filename uniqueness

### Finding 2 — collisions are possible and silently destructive. (Minor)

`f"{stamp}-{os.getpid()}-{time.monotonic_ns() % 1_000_000}.txt"`. The modulus
throws away every bit of `monotonic_ns` above 1 ms, so the uniquifier is
sub-millisecond phase, not a counter: two captures in the same second, in the
same process, whose monotonic clocks are congruent mod 1 ms produce the *same
filename*. Probability per pair is ~1e-6 under a uniform assumption.

Measured mitigations that already exist: llama's parallelism is
multi-process (flock), not threaded — no `ThreadPoolExecutor` anywhere in
`llama`/`emcee`, and the LLM call path is sequential — so concurrent captures
carry distinct pids. That keeps the real-world odds at the stated 1e-6, and I
agree with the implementer's judgement that this will very likely never bite.

What raises it above "ignore" is the **behaviour on collision**:
`write_text` overwrites, silently. The lost artifact is the earlier failure —
and preserving failure evidence is the module's only reason to exist. A
collision costs precisely the thing the feature buys. It would also make
`test_each_capture_gets_its_own_file` fail with a confusing message rather
than surfacing the real cause.

Cheapest fix that removes the class rather than shrinking it, using a
mechanism the repo already trusts:

```python
        path = _capture_dir / f"{stamp}-{os.getpid()}-{uuid.uuid4().hex[:8]}.txt"
```

or, if a no-clobber guarantee is wanted rather than more entropy,
`with path.open("x", encoding="utf-8") as f:` and let the `FileExistsError`
(an `OSError`) fall into the handler — that turns a silent overwrite into a
declined capture, which is the correct failure direction.

The implementer flagged this in the report and did not change it, per the
brief's explicit pre-authorization. That was the right call for an
implementer; I'm recording it as the reviewer so it is a decision someone
makes rather than a default nobody revisited.

### Finding 3 — the stamp is local time with no marker. (Minor)

`time.strftime` without a `gmtime` argument gives local time, and the
filename carries no offset. Captures collected across a DST boundary or from
machines in different zones sort wrongly against each other, and the body
carries no timestamp at all to disambiguate. Either use
`time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())` or add a
`captured_at:` line to the envelope. The body is the better home for it —
the envelope currently records *what* failed but not *when*, and the
filename is the only copy of that fact.

---

## Test hygiene

The four tests are real: each asserts something that fails if the code is
wrong (I checked by mentally mutating). Global state is handled — three tests
use `try/finally` to reset, and `test_capture_is_a_no_op_when_no_dir_is_set`
sets `None` itself rather than relying on a predecessor, so **file order does
not matter today** and nothing leaks into the rest of the 1652-test suite.
Good. Two gaps:

### Finding 4 — the "never raises" test does not test the claim it is named for. (Important)

`test_capture_never_raises_when_the_dir_is_unwritable` does not make a dir
unwritable; it puts a *file* where the dir should be. That fails at
`mkdir(...)` with `FileExistsError` — an `OSError`, the one arm already
covered. `write_text` is never reached, so the write arm's failure modes are
entirely unexercised, and no test in the file passes content that could
trigger Finding 1(a). This is the repo's own recorded lesson
(`green-suite-does-not-mean-pinned`) playing out: the suite is green and the
contract is not pinned.

The mutation that proves it: change `except OSError` to `except OSError`
guarding nothing new — all four tests still pass with the handler narrowed to
`except FileExistsError`, and all four still pass with it widened to
`except Exception`. The exception class is not pinned in either direction.

Concretely, add one test that reaches the write:

```python
def test_capture_never_raises_on_undecodable_content(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "write_text", _boom)   # raises ValueError
    ...
    assert failures.capture_failure(["claude"], FakeProc(returncode=1)) is None
```

or, without monkeypatching, capture a payload of non-ASCII text with
`encoding` forced narrow. Either one fails against the code as committed and
passes against the fix in Finding 1 — which is the definition of load-bearing.
Renaming the existing test to `..._when_the_dir_is_not_a_directory` would also
stop it overclaiming.

### Finding 5 — `test_each_capture_gets_its_own_file` pins the uniquifier only probabilistically. (Minor)

Delete the `% 1_000_000` term entirely and the test still passes whenever the
two calls straddle a second boundary, because the timestamp alone then
differs. It is a wall-clock-dependent assertion in a suite whose stated
constraint is determinism and no wall-clock reads in logic under test. It
won't flake in the failing direction (that needs a 1e-6 collision), but as
evidence it is weaker than it looks. Freezing `time.strftime` via monkeypatch
for the duration of the test would make it pin the uniquifier unconditionally
— and would be the natural place to also assert both files landed inside the
configured dir, which nothing currently checks.

---

## YAGNI / simplicity

Clean. 48 lines, two functions, no configuration surface, no formatting
options, no rotation/pruning logic, no cleverness. `getattr(proc, ...)` with
defaults is mild defensive duck-typing for a parameter that today only ever
receives a `CompletedProcess` — but it is what lets the tests use a 3-line
`FakeProc` without importing `subprocess`, and it happens to make a
`TimeoutExpired` object (no `returncode`, `stdout` possibly `None`) a legal
argument, which is genuinely useful when Task 3 wires this up. Keep it; just
say so, since `proc` is the one unannotated parameter in the module:
`proc` → "a `CompletedProcess`-like object (anything with
`returncode`/`stdout`/`stderr`)" in the docstring. (Minor.)

No duplication with `llama/cli.py:241`'s `llm-failure.txt`, which I checked:
that writes a `TaskFailed.raw_output` into a show workspace, i.e. a
*validated-task* failure, per show. This captures the *subprocess envelope*,
one layer down, in a package that cannot import llama. Different layer,
different lifetime, and the whole point of Task 1 is that the envelope's
structured fields are gone by the time `cli.py` sees anything. Complementary,
not redundant. Worth one sentence in the docstring pointing at the other one
so a future reader doesn't "consolidate" them.

---

## Fit with the codebase

Good, and better than most new modules get:

- The module docstring carries *why* (the 500-char truncation, the
  `resolve.provider_ladder` threading problem), which is precisely the house
  style — cf. `correspondence.py`, `siblings.py`, `claude_cli.py`.
- No blank line between docstring and imports: matches `correspondence.py`
  and `siblings.py`.
- Module-level mutable state with a setter is an existing herder/llama idiom
  (`claude_cli._neutral_dir`, `jerrybase._INDEX`, `cli._config_path`,
  `status._current`), and the docstring justifies it rather than assuming it.
- `X | None` annotations, no `from __future__ import annotations` — correct
  for 3.11+ and consistent with the package (only two files repo-wide use it).
- Not exported from `herder/__init__.py`, which is right: Task 3 imports the
  submodule, and the `__init__` surface is the provider API.
- Commit message follows `type(scope): subject`.

One divergence, already covered as Finding 1(a): the repo's write idiom
(`atomic_write_text`) pins UTF-8 and writes atomically via unique-temp +
rename. Atomicity I would *not* insist on here — a diagnostic dump truncated
by a crash is still evidence, and going through `workspace.atomic_write_text`
is impossible anyway since herder cannot import llama. The encoding half
should be matched.

---

## Summary of findings

| # | Severity | Finding |
|---|----------|---------|
| 1 | Important | "Never raises" is false: `write_text` without `encoding=` can raise `UnicodeEncodeError` (a `ValueError`) on non-ASCII output under a non-UTF-8 locale, and `' '.join(cmd)` can raise `TypeError` on a `PathLike` argv element — neither is an `OSError`. Fix: `encoding="utf-8", errors="replace"` and widen the handler. |
| 2 | Minor | Filename collision (~1e-6, same second + same pid) silently overwrites the earlier capture — losing the exact evidence the module exists to preserve. `uuid4().hex[:8]`, or `open("x")` so a collision declines instead of clobbering. |
| 3 | Minor | Timestamp is unmarked local time and appears only in the filename; the envelope body records no capture time. |
| 4 | Important | `test_capture_never_raises_when_the_dir_is_unwritable` blocks `mkdir`, never reaches `write_text`, and pins no exception class in either direction — the suite is green and the contract is unpinned. Add a test that fails on the write. |
| 5 | Minor | `test_each_capture_gets_its_own_file` still passes with the uniquifier deleted whenever the calls straddle a second boundary; wall-clock-dependent evidence in a suite that requires determinism. |
| 6 | Minor | `proc` is unannotated and its duck type undocumented; one docstring line, plus a pointer to `llama/cli.py`'s sibling `llm-failure.txt` capture. |

Findings 1 and 4 are the same defect seen from the source side and the test
side, and fixing them together is roughly a five-line diff. Everything else
can ship as-is or be folded in opportunistically. If the owner rules the
non-UTF-8-locale scenario out of scope for a macOS-only tool, Finding 1
collapses to Minor and this becomes an approval — but that should be an
explicit ruling, because the module's docstring currently promises otherwise.
