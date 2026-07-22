# Error-handling cleanup — design spec

**Date:** 2026-07-21
**Status:** approved (pending user spec review)

## Problem

Uncaught exceptions in the CLI print an ugly Rich traceback panel followed by
the PyInstaller bootloader line `[PYI-...:ERROR] Failed to execute script
'__main__' due to unhandled exception!`. The reported reproduction:

```
$ llama find --limit 120 "Grateful Dead"
╭─────── Traceback (most recent call last) ───────╮
│ in find:240 ... in __init__:23                  │
╰─────────────────────────────────────────────────╯
LLMError: OpenRouter API key missing: set OPENROUTER_API_KEY
[PYI-51069:ERROR] Failed to execute script '__main__' due to unhandled exception!
```

The error itself is *correct and user-actionable* (a missing API key), but it
is presented as if the program crashed.

### Root causes

1. **Rich pretty-tracebacks are on.** `app = typer.Typer(...)` leaves
   `pretty_exceptions_enable=True`, so any exception not caught inside a command
   renders the panel. The PyInstaller line follows because the frozen bootloader
   sees an unhandled exception propagate out of `__main__`.
2. **No common exception base.** The five custom exceptions —
   `IAError` (`ia_client.py`), `CatalogError` (`catalog.py`), `LLMError` +
   subclasses `ResearchNotSupported`/`TaskFailed` (`llm/provider.py`) — share no
   base, so each command must remember to catch each type. Coverage is
   inconsistent: `find`→`make_providers`→`provider_ladder` catches nothing (the
   bug), while other commands catch ad-hoc subsets.
3. **User-input errors typed as generic `ValueError`.** `resolve_artists`
   (`artist_index.py`) raises `ValueError` for empty / no-match / ambiguous
   artist names — user-actionable failures wearing a generic type.

### Non-issues (leave alone)

- Three broad `except Exception` are intentional and must stay: `setlistfm.py:97`
  (best-effort enrichment), `jerrybase.py:122` (absence must never raise),
  `audio.py:37` (probe fallback). The audit will only confirm each still logs
  what it swallowed.
- Internal-invariant errors are bugs, not user input, and should keep raising
  plain exceptions so they surface as tracebacks: `llm/tasks.py` empty-ladder and
  unfilled-placeholder `ValueError`s, `llm/fake.py` `AssertionError`s.

## Design

### 1. Central error taxonomy — `src/llama/errors.py`

New module with the base class:

```python
class LlamaError(Exception):
    """Base for expected, user-actionable failures. Its str() is a complete,
    actionable sentence; `details` carries optional indented follow-up lines."""

    def __init__(self, message: str, details: list[str] | None = None):
        super().__init__(message)
        self.details = details or []
```

Re-parent the existing exceptions onto it (behaviour otherwise unchanged so all
existing `pytest.raises(IAError|CatalogError|LLMError|TaskFailed)` still pass):

- `ia_client.IAError(LlamaError)`
- `catalog.CatalogError(LlamaError)` — its existing `matches` list is exposed to
  the boundary as `details` (set `self.details = self.matches` in `__init__`, or
  make `details` an alias; keep `matches` as the public attribute other code
  reads).
- `llm/provider.LLMError(LlamaError)`; `ResearchNotSupported`, `TaskFailed`
  unchanged (already subclass `LLMError`).

To avoid an import cycle, `errors.py` imports nothing from the rest of the
package; the exception-defining modules import `LlamaError` from it.

### 2. Reclassify user-input errors

`artist_index.resolve_artists` raises a new `LlamaError` subclass (e.g.
`ArtistResolutionError(LlamaError)`, defined in `errors.py`) with **self-contained
messages** — no reliance on a caller adding a prefix:

- empty name → `cannot pin artist: empty name in <names>`
- no match → `cannot pin artist: no LMA match for '<name>'`
- ambiguous → `cannot pin artist: '<name>' is ambiguous on the LMA: <options>`

Leave the corrupt-index `except (json.JSONDecodeError, KeyError, ValueError)`
handlers in `load_or_build`/`build_index` untouched — those catch unrelated
JSON-parse `ValueError`s.

### 3. Single error boundary at the CLI entry

Add a testable wrapper in `cli.py`, called from `__main__.py`:

```python
def run() -> None:
    try:
        app()
    except LlamaError as e:
        print(f"error: {e}", file=sys.stderr)
        for d in e.details:
            print(f"  {d}", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        raise SystemExit(130)
    except BrokenPipeError:
        raise SystemExit(0)
```

Any other `Exception` is caught by an outer clause that prints a **plain Python
traceback** and exits 1 — this is the chosen behaviour for genuine bugs, and
printing it ourselves (rather than letting it propagate) suppresses the
PyInstaller `Failed to execute script` line:

```python
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
```

`SystemExit`/`typer.Exit` raised by commands must pass through untouched (do not
catch `SystemExit`).

`__main__.py` changes from `app()` to `from llama.cli import run; run()`.

Set `pretty_exceptions_enable=False` on **every** Typer instance (`app`,
`profile_app`, `ledger_app`, `config_app`) so no Rich panel leaks from within
Click's own exception handling.

### 4. Sweep redundant per-command handling

Now that the boundary renders every `LlamaError` uniformly (message + indented
`details`) and command-specific prefixes are being dropped (per approval), remove
the now-redundant local handling and make each exception message self-contained:

- **Collapse** `_resolve_run_or_exit` / `_resolve_show_or_exit` (cli.py:372–393):
  drop the `try/except CatalogError`; return `resolve_run(...)` /
  `resolve_show(...)` directly and let the boundary print `CatalogError.details`.
- **Drop** the profile-add `except ValueError` (cli.py:686) — `resolve_artists`
  now raises a self-contained `LlamaError`.
- **Drop** the `artists` command `except IAError` prefix (cli.py:267); ensure the
  `IAError` messages raised in `ia_client.py`/`artist_index.build_index` are
  complete on their own.
- **Audit remaining raise sites** for message quality: each `raise IAError(...)`,
  `raise CatalogError(...)`, `raise LLMError(...)` should read as a complete,
  actionable sentence (what failed + what the user can do). Fix any that only
  made sense with a caller-supplied prefix.

**Keep** (do NOT remove): the profile-*run* `except (TaskFailed, LLMError,
IAError)` at cli.py:186 — this is per-show resilience inside the show loop
(logs `FAILED <id>`, continues to the next show), not top-level error display.
Its behaviour is orthogonal to the boundary and must be preserved.

## Testing

- **New `tests/test_cli_errors.py`** exercising the boundary via a small helper
  that invokes `run()` against a stub `app` (or by refactoring the four handler
  clauses into a callable the test can drive directly):
  - `LlamaError("msg")` → stderr `error: msg`, exit code 1, no traceback text.
  - `CatalogError("no match", matches=["a", "b"])` → indented `  a` / `  b`.
  - `KeyboardInterrupt` → exit 130, no traceback.
  - generic `RuntimeError("boom")` → traceback present on stderr, exit 1, and
    **no** `Failed to execute script` text.
- **Update** `tests/test_artist_index.py:245,248` from
  `pytest.raises(ValueError, ...)` to the new `LlamaError` subclass (or
  `pytest.raises(LlamaError, match=...)`). Messages tightened per §2.
- All other exception tests remain green because the classes are unchanged apart
  from their base.
- Full `pytest -q` must pass.

## Out of scope

- Restructuring logging/verbosity (`status.py`).
- Retry/backoff policy changes.
- Any behaviour change to the three intentional defensive `except Exception`
  blocks beyond confirming they log.
