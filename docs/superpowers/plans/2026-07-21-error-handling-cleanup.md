# Error-handling Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make expected, user-actionable CLI failures (e.g. a missing API key) print a clean `error: <message>` instead of a Rich traceback panel and the PyInstaller `Failed to execute script` line.

**Architecture:** Introduce a common `LlamaError` base for expected failures, re-parent the existing custom exceptions onto it, and add a single error boundary at the CLI entry (`cli.run`) that catches `LlamaError` (clean message + indented details, exit 1), `KeyboardInterrupt` (quiet exit 130), and any other `Exception` (plain traceback, exit 1 — printed by us so the PyInstaller line is suppressed). Rich pretty-tracebacks are disabled on every Typer app. Redundant per-command `try/except` blocks are then swept.

**Tech Stack:** Python, Typer/Click, pytest. No new dependencies — stdlib `sys` and `traceback` only.

## Global Constraints

- No new third-party dependencies; stdlib only for the new code.
- `errors.py` imports nothing from the rest of the `llama` package (stay import-cycle-free).
- All existing `pytest.raises(IAError | CatalogError | LLMError | TaskFailed)` must keep passing — the classes keep their names and stay `Exception` subclasses; only their base changes.
- The full suite (`pytest -q`) must be green at the end of every task.
- Do **not** remove or alter the profile-*run* per-show `except (TaskFailed, LLMError, IAError)` loop at `cli.py:186` — it is per-show resilience (logs `FAILED <id>`, continues), not top-level error display.
- Do **not** touch the three intentional defensive `except Exception` blocks (`setlistfm.py:97`, `jerrybase.py:122`, `audio.py:37`).
- Internal-invariant errors stay plain exceptions (they are bugs, must surface as tracebacks): `llm/tasks.py` empty-ladder / unfilled-placeholder `ValueError`, `llm/fake.py` `AssertionError`.

---

## File Structure

- **Create** `src/llama/errors.py` — the exception taxonomy: `LlamaError` base + `ArtistResolutionError`.
- **Modify** `src/llama/ia_client.py` — re-parent `IAError` onto `LlamaError`.
- **Modify** `src/llama/catalog.py` — re-parent `CatalogError`; expose `matches` as `details`.
- **Modify** `src/llama/llm/provider.py` — re-parent `LLMError` onto `LlamaError`.
- **Modify** `src/llama/cli.py` — add `run()` boundary; `pretty_exceptions_enable=False` on all four Typer apps; sweep redundant catches; reclassify handling.
- **Modify** `src/llama/__main__.py` — call `run()` instead of `app()`.
- **Modify** `src/llama/artist_index.py` — reclassify `resolve_artists` `ValueError`s to `ArtistResolutionError`.
- **Create** `tests/test_errors.py` — taxonomy tests.
- **Create** `tests/test_cli_errors.py` — boundary tests.
- **Modify** `tests/test_artist_index.py` — update the two `resolve_artists` error assertions.

---

## Task 1: Exception taxonomy + re-parenting

**Files:**
- Create: `src/llama/errors.py`
- Modify: `src/llama/ia_client.py:15-17`
- Modify: `src/llama/catalog.py:15-20`
- Modify: `src/llama/llm/provider.py:4-5`
- Test: `tests/test_errors.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `llama.errors.LlamaError(message: str, details: list[str] | None = None)` with attribute `.details: list[str]`.
  - `llama.errors.ArtistResolutionError(LlamaError)`.
  - `IAError`, `CatalogError`, `LLMError` (and its existing subclasses `ResearchNotSupported`, `TaskFailed`) are now subclasses of `LlamaError`.
  - `CatalogError(message, matches)` keeps its `.matches` attribute AND exposes the same list as `.details`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_errors.py`:

```python
from llama.errors import ArtistResolutionError, LlamaError
from llama.ia_client import IAError
from llama.catalog import CatalogError
from llama.llm.provider import LLMError, ResearchNotSupported, TaskFailed


def test_custom_exceptions_subclass_llama_error():
    for exc in (IAError, CatalogError, LLMError, ResearchNotSupported,
                TaskFailed, ArtistResolutionError):
        assert issubclass(exc, LlamaError)


def test_llama_error_details_default_empty():
    assert LlamaError("boom").details == []
    assert str(LlamaError("boom")) == "boom"


def test_catalog_error_details_mirror_matches():
    e = CatalogError("no run matches 'x'", ["run-a", "run-b"])
    assert e.matches == ["run-a", "run-b"]
    assert e.details == ["run-a", "run-b"]


def test_catalog_error_without_matches():
    e = CatalogError("boom")
    assert e.matches == []
    assert e.details == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_errors.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'llama.errors'`.

- [ ] **Step 3: Create `src/llama/errors.py`**

```python
"""Central exception taxonomy.

`LlamaError` is the base for expected, user-actionable failures. The CLI error
boundary (`llama.cli.run`) catches it and prints `error: <message>` plus any
indented `details`, instead of a traceback. Anything that is NOT a `LlamaError`
is treated as a bug and surfaces as a plain traceback.

This module imports nothing from the rest of the package to stay
import-cycle-free.
"""


class LlamaError(Exception):
    """Base for expected, user-actionable failures.

    `str(self)` must read as a complete, actionable sentence. `details` holds
    optional follow-up lines the boundary prints indented under the message
    (e.g. the candidate list for an ambiguous match).
    """

    def __init__(self, message: str, details: list[str] | None = None):
        super().__init__(message)
        self.details = details or []


class ArtistResolutionError(LlamaError):
    """A pinned or queried artist name could not be resolved to an LMA entry."""
```

- [ ] **Step 4: Re-parent `IAError`**

In `src/llama/ia_client.py`, add the import near the top of the module (with the other imports) and change the class. Replace:

```python
class IAError(Exception):
    pass
```

with:

```python
class IAError(LlamaError):
    pass
```

and add this import alongside the module's existing imports:

```python
from llama.errors import LlamaError
```

- [ ] **Step 5: Re-parent `CatalogError` and expose `details`**

In `src/llama/catalog.py`, add `from llama.errors import LlamaError` alongside the existing `from llama...` imports (after line 12), then replace lines 15-20:

```python
class CatalogError(Exception):
    """Resolution failure; matches lists the candidates (empty = no match)."""

    def __init__(self, message: str, matches: list[str] | None = None):
        super().__init__(message)
        self.matches = matches or []
```

with:

```python
class CatalogError(LlamaError):
    """Resolution failure; matches lists the candidates (empty = no match).

    The candidate list is exposed to the CLI error boundary as `details`.
    """

    def __init__(self, message: str, matches: list[str] | None = None):
        super().__init__(message, details=matches)
        self.matches = matches or []
```

- [ ] **Step 6: Re-parent `LLMError`**

In `src/llama/llm/provider.py`, replace:

```python
from typing import Protocol, runtime_checkable


class LLMError(Exception):
    pass
```

with:

```python
from typing import Protocol, runtime_checkable

from llama.errors import LlamaError


class LLMError(LlamaError):
    pass
```

(Leave `ResearchNotSupported(LLMError)` and `TaskFailed(LLMError)` unchanged — they inherit the new base transitively.)

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_errors.py -q`
Expected: PASS (4 passed).

- [ ] **Step 8: Run the exception-touching suites to confirm no regressions**

Run: `pytest tests/test_errors.py tests/test_catalog.py tests/test_ia_client.py tests/test_model_tiers.py tests/test_claude_cli.py tests/test_stage_research.py tests/test_artist_index.py -q`
Expected: PASS (all green — existing `pytest.raises(IAError|CatalogError|LLMError|TaskFailed)` still hold).

- [ ] **Step 9: Commit**

```bash
git add src/llama/errors.py src/llama/ia_client.py src/llama/catalog.py src/llama/llm/provider.py tests/test_errors.py
git commit -m "feat: add LlamaError base and re-parent custom exceptions"
```

---

## Task 2: CLI error boundary

**Files:**
- Modify: `src/llama/cli.py:1-6` (imports), `src/llama/cli.py:32,35,36,40` (Typer constructors), and append `run()` at end of file.
- Modify: `src/llama/__main__.py`
- Test: `tests/test_cli_errors.py`

**Interfaces:**
- Consumes: `llama.errors.LlamaError` (from Task 1); the module-level `app` in `cli.py`.
- Produces: `llama.cli.run() -> None` — the single CLI entry boundary. Calls `app()`; renders `LlamaError` cleanly (exit 1), `KeyboardInterrupt` (exit 130), `BrokenPipeError` (exit 0), and any other `Exception` as a plain traceback (exit 1). It looks up `app` from module globals at call time (so tests can monkeypatch `llama.cli.app`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli_errors.py`:

```python
import pytest

import llama.cli as cli
from llama.catalog import CatalogError
from llama.errors import LlamaError


def _run_with(monkeypatch, boom):
    monkeypatch.setattr(cli, "app", boom)
    with pytest.raises(SystemExit) as excinfo:
        cli.run()
    return excinfo.value


def test_llama_error_prints_clean_message(monkeypatch, capsys):
    exc = _run_with(monkeypatch, lambda: (_ for _ in ()).throw(
        LlamaError("OpenRouter API key missing: set OPENROUTER_API_KEY")))
    err = capsys.readouterr().err
    assert exc.code == 1
    assert err.strip() == "error: OpenRouter API key missing: set OPENROUTER_API_KEY"
    assert "Traceback" not in err


def test_catalog_error_details_are_indented(monkeypatch, capsys):
    _run_with(monkeypatch, lambda: (_ for _ in ()).throw(
        CatalogError("'19' is ambiguous", ["run-a", "run-b"])))
    err = capsys.readouterr().err
    assert "error: '19' is ambiguous" in err
    assert "  run-a" in err
    assert "  run-b" in err


def test_keyboard_interrupt_exits_130(monkeypatch, capsys):
    exc = _run_with(monkeypatch, lambda: (_ for _ in ()).throw(KeyboardInterrupt()))
    assert exc.code == 130
    assert "Traceback" not in capsys.readouterr().err


def test_unexpected_error_shows_plain_traceback(monkeypatch, capsys):
    exc = _run_with(monkeypatch, lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    err = capsys.readouterr().err
    assert exc.code == 1
    assert "Traceback (most recent call last)" in err
    assert "RuntimeError: boom" in err
    assert "Failed to execute script" not in err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_errors.py -q`
Expected: FAIL — `AttributeError: module 'llama.cli' has no attribute 'run'`.

- [ ] **Step 3: Add stdlib imports to `cli.py`**

At the top of `src/llama/cli.py`, add `import sys` and `import traceback` to the existing stdlib import block (lines 1-5), e.g. after `import shutil`:

```python
import logging
import shutil
import sys
import textwrap
import traceback
from datetime import date, datetime, timezone
from pathlib import Path
```

- [ ] **Step 4: Disable Rich pretty-tracebacks on every Typer app**

In `src/llama/cli.py`, add `pretty_exceptions_enable=False` to all four `typer.Typer(...)` constructors:

- Line 32: `app = typer.Typer(help="Live Music Archive -> radio station pipeline", pretty_exceptions_enable=False)`
- Line 35: `profile_app = typer.Typer(help="Standing criteria profiles for recurring segments", pretty_exceptions_enable=False)`
- Line 36: `ledger_app = typer.Typer(help="Broadcast-history ledger", pretty_exceptions_enable=False)`
- Line 40: `config_app = typer.Typer(help="Config file utilities", pretty_exceptions_enable=False)`

- [ ] **Step 5: Append the `run()` boundary at the end of `cli.py`**

Add to the very end of `src/llama/cli.py`:

```python
def run() -> None:
    """CLI entry point with a single error boundary.

    Expected, user-actionable failures (`llama.errors.LlamaError`) print a clean
    `error: <message>` plus any indented details and exit 1. `KeyboardInterrupt`
    exits 130 quietly. Any other exception is a bug: we print a plain traceback
    ourselves and exit 1 — printing it here (rather than letting it propagate)
    suppresses the frozen bootloader's `Failed to execute script` line.
    `SystemExit`/`typer.Exit` from commands pass through untouched.
    """
    try:
        app()
    except LlamaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        for detail in exc.details:
            print(f"  {detail}", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        raise SystemExit(130)
    except BrokenPipeError:
        raise SystemExit(0)
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
```

Then add `LlamaError` to the existing errors/provider imports. In the import block, change line 16 area to also import the base — add:

```python
from llama.errors import LlamaError
```

(alongside `from llama.llm.provider import LLMError, TaskFailed`).

- [ ] **Step 6: Wire `__main__.py` to `run()`**

Replace the whole of `src/llama/__main__.py` with:

```python
"""Entry point for the frozen binary and `python -m llama`."""

from llama.cli import run

if __name__ == "__main__":
    run()
```

- [ ] **Step 7: Run the boundary tests to verify they pass**

Run: `pytest tests/test_cli_errors.py -q`
Expected: PASS (4 passed).

- [ ] **Step 8: Run the existing CLI suites to confirm no regressions**

Run: `pytest tests/test_cli.py tests/test_cli_commands.py tests/test_artists_cmd.py tests/test_version.py tests/test_pipeline.py -q`
Expected: PASS (all green — commands still raise `typer.Exit` and CliRunner still sees the same exit codes; `pretty_exceptions_enable=False` does not change CliRunner behavior).

- [ ] **Step 9: Commit**

```bash
git add src/llama/cli.py src/llama/__main__.py tests/test_cli_errors.py
git commit -m "feat: single CLI error boundary; disable Rich pretty-tracebacks"
```

---

## Task 3: Reclassify artist-resolution errors

**Files:**
- Modify: `src/llama/artist_index.py:131-151` (the three `raise ValueError` in `resolve_artists`) + import.
- Modify: `src/llama/cli.py:682-690` (remove the now-dead `except ValueError` around `resolve_artists`).
- Test: `tests/test_artist_index.py:225-249`

**Interfaces:**
- Consumes: `llama.errors.ArtistResolutionError` (from Task 1); the `run()` boundary (from Task 2) renders it.
- Produces: `resolve_artists` raises `ArtistResolutionError` with self-contained messages: `cannot pin artist: empty name in <names>`, `cannot pin artist: no LMA match for '<name>'`, `cannot pin artist: '<name>' is ambiguous on the LMA: <options>`.

- [ ] **Step 1: Update the failing test**

In `tests/test_artist_index.py`, add the import near the other imports at the top of `test_resolve_artists_exact_partial_and_errors` (or module top):

```python
from llama.errors import ArtistResolutionError
```

Then replace the two assertion blocks at lines 245-249:

```python
    with pytest.raises(ValueError, match="ambiguous"):
        resolve_artists(index, ["galac"])

    with pytest.raises(ValueError, match="no LMA artist"):
        resolve_artists(index, ["Phish Tribute Zebra"])
```

with:

```python
    with pytest.raises(ArtistResolutionError, match="ambiguous"):
        resolve_artists(index, ["galac"])

    with pytest.raises(ArtistResolutionError, match="no LMA match"):
        resolve_artists(index, ["Phish Tribute Zebra"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_artist_index.py::test_resolve_artists_exact_partial_and_errors -q`
Expected: FAIL — `resolve_artists` still raises `ValueError`, and the `match="no LMA match"` string does not match the current `"no LMA artist matches ..."` message.

- [ ] **Step 3: Reclassify the raises in `resolve_artists`**

In `src/llama/artist_index.py`, add to the imports:

```python
from llama.errors import ArtistResolutionError
```

Then in `resolve_artists`, replace the three raises:

```python
        if not want:
            raise ValueError(f"empty artist name in {names!r}")
```
→
```python
        if not want:
            raise ArtistResolutionError(f"cannot pin artist: empty name in {names!r}")
```

```python
        elif not partial:
            raise ValueError(f"no LMA artist matches {name!r}")
```
→
```python
        elif not partial:
            raise ArtistResolutionError(f"cannot pin artist: no LMA match for {name!r}")
```

```python
            options = ", ".join(a["identifier"] for a in partial[:8])
            raise ValueError(f"{name!r} is ambiguous on the LMA: {options}")
```
→
```python
            options = ", ".join(a["identifier"] for a in partial[:8])
            raise ArtistResolutionError(
                f"cannot pin artist: {name!r} is ambiguous on the LMA: {options}")
```

- [ ] **Step 4: Remove the now-dead `except ValueError` in the profile-add command**

In `src/llama/cli.py`, replace lines 682-690:

```python
    if artists:
        names = [n.strip() for n in artists.split(",") if n.strip()]
        index = load_or_build(ia, config.root / "cache")
        try:
            resolved = resolve_artists(index, names)
        except ValueError as e:
            typer.echo(f"cannot pin artists: {e}", err=True)
            raise typer.Exit(1)
        updates["artists"] = [a["identifier"] for a in resolved]
```

with:

```python
    if artists:
        names = [n.strip() for n in artists.split(",") if n.strip()]
        index = load_or_build(ia, config.root / "cache")
        resolved = resolve_artists(index, names)
        updates["artists"] = [a["identifier"] for a in resolved]
```

(`resolve_artists` now raises a self-contained `ArtistResolutionError`; the `run()` boundary prints it as `error: cannot pin artist: ...` and exits 1.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_artist_index.py -q`
Expected: PASS (all green).

- [ ] **Step 6: Commit**

```bash
git add src/llama/artist_index.py src/llama/cli.py tests/test_artist_index.py
git commit -m "refactor: raise ArtistResolutionError for unresolved artists"
```

---

## Task 4: Sweep remaining redundant CLI catches

**Files:**
- Modify: `src/llama/cli.py:265-269` (`artists` command `except IAError` prefix).
- Modify: `src/llama/cli.py:372-393` (the two resolve helpers) and their call sites at `304, 348, 405, 459, 510`.

**Interfaces:**
- Consumes: the `run()` boundary (Task 2) renders `IAError`/`CatalogError`.
- Produces: `_resolve_run(config, name) -> RunWorkspace` and `_resolve_show(config, ledger, name)` — thin delegators to `catalog.resolve_run`/`catalog.resolve_show` that no longer catch or exit (the boundary renders `CatalogError.details`).

- [ ] **Step 1: Confirm the current suite is green (safety baseline for the refactor)**

Run: `pytest -q`
Expected: PASS (whole suite green before refactor).

- [ ] **Step 2: Drop the `artists` command's `IAError` prefix catch**

In `src/llama/cli.py`, replace lines 264-269:

```python
    config, ia, _ = _setup(config_path)
    try:
        index = load_or_build(ia, config.root / "cache", refresh=refresh)
    except IAError as exc:
        typer.echo(f"artist index build failed: {exc}", err=True)
        raise typer.Exit(1)
```

with:

```python
    config, ia, _ = _setup(config_path)
    index = load_or_build(ia, config.root / "cache", refresh=refresh)
```

(The underlying `IAError` messages already name the failing URL/attempt; the boundary prints `error: <message>` and exits 1.)

- [ ] **Step 3: Reduce the resolve helpers to delegators and rename them**

In `src/llama/cli.py`, replace lines 372-393:

```python
def _resolve_run_or_exit(config, name: str) -> RunWorkspace:
    from llama.catalog import CatalogError, resolve_run

    try:
        return RunWorkspace(config.root, resolve_run(config.root, name))
    except CatalogError as err:
        typer.echo(str(err), err=True)
        for m in err.matches:
            typer.echo(f"  {m}", err=True)
        raise typer.Exit(1)


def _resolve_show_or_exit(config, ledger, name: str):
    from llama.catalog import CatalogError, resolve_show

    try:
        return resolve_show(config.root, ledger, name)
    except CatalogError as err:
        typer.echo(str(err), err=True)
        for m in err.matches:
            typer.echo(f"  {m}", err=True)
        raise typer.Exit(1)
```

with:

```python
def _resolve_run(config, name: str) -> RunWorkspace:
    from llama.catalog import resolve_run

    return RunWorkspace(config.root, resolve_run(config.root, name))


def _resolve_show(config, ledger, name: str):
    from llama.catalog import resolve_show

    return resolve_show(config.root, ledger, name)
```

(A `CatalogError` now propagates to the `run()` boundary, which prints the message and the indented `details`/matches.)

- [ ] **Step 4: Update the helper call sites**

In `src/llama/cli.py`, update the five call sites:

- Line 304: `ws = _resolve_run_or_exit(config, run_name)` → `ws = _resolve_run(config, run_name)`
- Line 348: `ws = _resolve_run_or_exit(config, run_name)` → `ws = _resolve_run(config, run_name)`
- Line 405: `entry = _resolve_show_or_exit(config, ledger, name)` → `entry = _resolve_show(config, ledger, name)`
- Line 459: `entry = _resolve_show_or_exit(config, ledger, name)` → `entry = _resolve_show(config, ledger, name)`
- Line 510: `entry = _resolve_show_or_exit(config, ledger, name)` → `entry = _resolve_show(config, ledger, name)`

(Verify no other references remain: `grep -n "_resolve_run_or_exit\|_resolve_show_or_exit" src/llama/cli.py` must return nothing.)

- [ ] **Step 5: Verify the boundary still renders `CatalogError` details (already covered)**

The `tests/test_cli_errors.py::test_catalog_error_details_are_indented` case (Task 2) already asserts a `CatalogError` with matches renders `error: ...` plus indented candidates through `run()`. No new test needed for the rendering; the sweep only removes duplicate handling.

- [ ] **Step 6: Run the full suite**

Run: `pytest -q`
Expected: PASS (whole suite green — no test asserted the old per-command stderr text; `test_catalog.py` still exercises `resolve_run`/`resolve_show` directly and they are unchanged).

- [ ] **Step 7: Confirm no stray references and no leftover redundant catches**

Run: `grep -n "_resolve_run_or_exit\|_resolve_show_or_exit\|artist index build failed" src/llama/cli.py`
Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add src/llama/cli.py
git commit -m "refactor: let the error boundary render IAError/CatalogError"
```

---

## Manual verification (post-implementation)

After Task 4, reproduce the original bug against the `fake`/no-key path to confirm the clean output. With no `OPENROUTER_API_KEY` set and a config selecting the openrouter backend:

Run: `python -m llama find --limit 5 "Grateful Dead"` (openrouter backend, key unset)
Expected: a single line `error: OpenRouter API key missing: set OPENROUTER_API_KEY` on stderr, exit code 1, **no** Rich panel and **no** `Failed to execute script` line.

---

## Self-Review

**Spec coverage:**
- §1 Central taxonomy (`errors.py`, re-parent) → Task 1. ✔
- §2 Reclassify `resolve_artists` → Task 3. ✔
- §3 Single boundary + `pretty_exceptions_enable=False` + `__main__` wiring → Task 2. ✔
- §4 Sweep redundant handling (resolve helpers, `artists` prefix, profile-add catch); keep profile-run loop → Task 3 (profile-add) + Task 4 (helpers, `artists`); profile-run loop explicitly untouched per Global Constraints. ✔
- Testing: new `test_errors.py` (Task 1), new `test_cli_errors.py` (Task 2), updated `test_artist_index.py` (Task 3), full-suite gate every task. ✔
- Out-of-scope items (logging, retry policy, defensive `except Exception`) — none touched. ✔

**Placeholder scan:** No TBD/TODO/"add error handling" placeholders; every code step shows complete code. ✔

**Type consistency:** `LlamaError(message, details)` / `.details` used identically in Tasks 1 and 2; `CatalogError.details == .matches` established in Task 1 and relied on in Task 2/4; `ArtistResolutionError` defined in Task 1, raised in Task 3, asserted in Task 3 test; helpers renamed `_resolve_run`/`_resolve_show` consistently in Task 4 definition and all five call sites. ✔
