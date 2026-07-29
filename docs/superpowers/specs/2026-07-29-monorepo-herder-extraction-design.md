# Sub-project 1: monorepo restructure + herder extraction

**Date:** 2026-07-29
**Status:** Spec for the first sub-project of the approved split architecture
(`2026-07-28-split-architecture-design.md`). Purely mechanical: at the end, llama
behaves identically, the full suite is green, and the shared LLM layer lives in its
own package named **herder**.

## Goal

Restructure the repo into a monorepo of independent Python packages and extract
`src/llama/llm/` into `herder`, de-llama-ified per the umbrella spec. No behavior
change, no new features, no CLI/UX change. The persona tool package does not exist
yet (sub-project 3); this step creates the structure it will drop into.

## Repo layout (after)

```
packages/
  herder/
    pyproject.toml          # name=herder, GPL-3.0-or-later, deps: pydantic, httpx
    src/herder/
      __init__.py           # public API re-exports
      provider.py           # LLMProvider protocol, HerderError, TaskFailed, ResearchNotSupported
      claude_cli.py         # moved from llama/llm/
      openrouter.py         # moved from llama/llm/
      fake.py               # moved from llama/llm/ (test backend is part of the lib)
      resolve.py            # tier tables, resolve/ladder/escalation (from llama/llm/__init__.py)
      tasks.py              # render, extract_json, run_json_task, run_research_task
    tests/                  # the llm-layer tests, moved from tests/
  llama/
    pyproject.toml          # unchanged deps + `herder` as a path/workspace dependency
    src/llama/              # everything current except llm/
    tests/                  # all remaining tests, moved from tests/
scripts/                    # stays at root (repo utilities); paths inside updated as needed
docs/                       # stays at root
pyproject.toml              # REMOVED from root (see Setup below)
pytest.ini (or root-level [tool.pytest] carrier)  # so `pytest -q` at root collects both packages
```

- Moves use `git mv` so history follows files.
- Editable dev setup becomes:
  `pip install -e packages/herder -e "packages/llama[dev]"`
  (README, CLAUDE.md, and docs updated; no root meta-package — one extra `-e` is
  cheaper than maintaining a fake aggregator project).
- `pytest -q` from the repo root still runs everything (root pytest config sets
  `testpaths = packages/herder/tests packages/llama/tests`). Single-test invocation
  paths in docs updated accordingly.

## herder: package boundary

**herder owns** (all current behavior preserved verbatim unless listed under
de-couplings): the `LLMProvider` protocol (`complete`/`research`), the three
backends, `render`/`extract_json`, `run_json_task`/`run_research_task` with the
retry-with-validation-feedback loop, the shipped backend tier tables
(`TIER_MODELS` — knowledge about the backends herder ships), tier resolution,
the provider ladder, and `ESCALATE` (final-attempt escalation; pins never
escalate).

**llama keeps**: `DEFAULT_TIERS` (task-name vocabulary), its prompt files
(`llama/prompts/`), all task schemas, `Config` parsing, and the `llm-failure.txt`
handling around `TaskFailed`.

### The three de-couplings (the only intentional API changes)

1. **Prompts.** `load_prompt` (hardcoded to `llama.prompts`) moves *to llama*
   (e.g. `llama/prompt_loader.py`). herder's task runners take the template text as
   a required `template:` keyword instead of loading it themselves; call sites
   change from `run_json_task(p, "interpret", Schema, **inputs)` to
   `run_json_task(p, "interpret", Schema, template=load_prompt("interpret"),
   **inputs)` (~9 call sites, mechanical). The task *name* stays a parameter for
   error messages.
2. **Config.** herder's resolution functions stop taking llama's `Config`. herder
   defines a small settings type (per-task backend/model/tier + per-backend tier
   table overlays); llama's `Config` gains a thin adapter that builds it from
   `[llm]`/`[llm.tiers.*]` + `DEFAULT_TIERS`. Resolution semantics are unchanged:
   explicit model > explicit tier > task default > medium; unknown backend/tier
   errors preserved verbatim (tests moved, not rewritten).
3. **Errors.** herder defines `HerderError` as its own base (with `TaskFailed`,
   `ResearchNotSupported` under it), no import of `llama.errors`. llama's
   `main_cli` error boundary catches `HerderError` alongside `LlamaError` and
   renders it the same way. Stage code that today catches `TaskFailed` catches
   herder's.

herder imports nothing from llama (enforced by a test: no `llama` import anywhere
under `packages/herder/src/`).

## Explicitly out of scope

- `claude -p --json-schema` adoption (behavior change; deferred so this sub-project
  stays mechanical — earmarked for sub-project 2 or a standalone follow-up).
- The persona tool package, briefing, manifest v3 (sub-projects 2–3).
- Any pipeline/stage/CLI behavior change. `llama.llm`'s public surface simply
  relocates; stage code updates imports and threads templates/settings through.

## CI / release / docs updates (part of this sub-project)

- **CI test workflow**: install both packages editable; `pytest -q` at root.
- **Release workflow**: PyInstaller build paths point into `packages/llama/`;
  release artifacts unchanged (still just llama binaries — herder ships inside
  them; no separate herder release, it is internal and unpublished by design).
- **Docs**: README + CLAUDE.md setup/test commands, `docs/releasing.md` paths,
  and a short note in CLAUDE.md's architecture section that the LLM layer is the
  shared `herder` package under `packages/`.

## Verification

- Full suite green from repo root: `pytest -q` (all existing tests pass with only
  import-path/mechanical updates; herder's tests are the moved llm tests plus the
  no-llama-import guard).
- `grep -r "from llama.llm\|import llama.llm" packages/` → empty.
- Fresh-venv editable install per the new README instructions; `llama --help`,
  `llama pipeline`, and an offline `llama get` smoke against the fake backend all
  behave identically.
- CI and release workflows updated in the same branch (release workflow verified
  by inspection/dry-run only — no release is cut for this change).
