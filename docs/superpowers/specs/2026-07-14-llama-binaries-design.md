# Self-contained `llama` binaries — design spec

**Date:** 2026-07-14
**Status:** Approved (pending spec review)

## Goal

Ship self-contained, single-file `llama` executables for the four targets the
in-house radio station runs on, published to GitHub Releases on tag push. No
Python install required on the target host.

Targets:

| OS      | Arch    | Runner label                    |
|---------|---------|---------------------------------|
| Linux   | x86_64  | `[self-hosted, linux, x64]`     |
| Linux   | arm64   | `[self-hosted, linux, arm64]`   |
| macOS   | arm64   | `[self-hosted, macos, arm64]`   |
| Windows | x86_64  | `[self-hosted, windows, x64]`   |

Explicitly **not** in scope (deliberate contrast with the sibling `litcat`
project, whose packaging is heavy because it is a distributed consumer GUI):
code signing / notarization, macOS Intel slice, `.app`/AppImage/Inno installers,
icons, R2 upload / update-check manifest.

## Context: what is and isn't reused from `litcat`

`litcat` is a PySide6 desktop app distributed to third parties. Its packaging is
correspondingly heavy: PyInstaller **onedir** bundles wrapped in native
installers per platform, Developer ID notarization + Azure Trusted Signing built
on a self-hosted runner fleet (credentials live on the boxes), uploaded to R2
with a signed update manifest.

`llama` is a pure `typer` CLI with light dependencies (`typer`, `pydantic`,
`httpx`, `mutagen`, `tomli-w`; only `pydantic-core` carries a compiled/Rust
wheel). The single real bundling concern is `src/llama/prompts/*.md`, loaded at
runtime via `importlib.resources.files("llama.prompts")`.

**Reused:** the PyInstaller *spec pattern* (env-var version injection, data-file
collection), the *shape* of the release workflow (per-OS matrix, strict version
validation, checksums), and the self-hosted runner labels.

**Dropped:** everything signing/installer/upload related. The result is far
smaller: one spec, one build driver, one workflow with no external secrets.

## Design decisions

- **Build tool: PyInstaller** (`>=6.10`). Proven in `litcat`; its bundled hooks
  handle `pydantic-core`, and `collect_data_files` handles the prompts. Nuitka
  was considered and rejected — smaller/faster output isn't worth its slower,
  fussier builds and zero reuse for an internal CLI.
- **Binary shape: onefile.** A single executable is the natural "self-contained
  binary" for a CLI. Cost: onefile extracts to a temp dir on launch (~0.1–0.3s
  cold-start overhead) — negligible here. (`litcat` uses onedir because a GUI
  benefits from a folder bundle + installer; that rationale does not apply.)
- **Publish to GitHub Releases** keyed to the pushed tag; no R2/manifest.
- **Runners: existing self-hosted fleet**, same labels as `litcat`. Unsigned, so
  there are no on-box secrets — GitHub-hosted runners would also work — but we
  reuse the fleet for consistency with `litcat` and to avoid hosted-arm64 cost.

## Components

### 1. `packaging/llama.spec`

One spec, all platforms. Structure (much smaller than `litcat.spec`):

- Reads `LLAMA_VERSION` env var (default `"0.0.0"`) — drives only the optional
  Windows version resource (`litcat`'s pattern; failures there warn, never break
  the build).
- `datas = collect_data_files("llama.prompts")` — bundles the `.md` prompt
  templates so `importlib.resources.files("llama.prompts")` resolves in the
  frozen binary. This is the one mandatory bundling step.
- No manual `hiddenimports` expected (typer/click, httpx+certifi, pydantic-core,
  mutagen, tomli-w are all covered by PyInstaller's built-in hooks). If the
  smoke test surfaces a missing dynamic import, add it here — mirroring how
  `litcat.spec` documents its alembic/`logging.config` hidden-import fix.
- Single `EXE` with `exclude_binaries=False` (onefile), `console=True`,
  `name="llama"`. No `COLLECT`, no `BUNDLE`, no icon, no codesign/entitlements.
- Windows-only: build a `VSVersionInfo` resource from `LLAMA_VERSION` (adapted
  from `litcat.spec`), wired via `EXE(..., version=...)`.

### 2. `packaging/build.py`

Cross-platform build driver (replaces `litcat`'s three per-OS shell scripts,
which are large only because of signing + installers). Runnable locally and from
CI. Responsibilities, in order:

1. Parse `--version <ver>` (required) and optional `--dry-run`.
2. Write `src/llama/_version.py` containing `__version__ = "<ver>"` (see §4).
3. Set `LLAMA_VERSION` in the environment and run
   `pyinstaller packaging/llama.spec --clean --noconfirm`.
4. **Smoke test:** run the produced binary with `--help`; require exit 0. This
   catches missing data files / hidden imports before anything is published —
   the failure class that is invisible to static analysis and only appears at
   runtime.
5. Detect OS + arch and package the binary into
   `dist-release/llama-<ver>-<os>-<arch>.<ext>`:
   - macOS / Linux → `.tar.gz` (preserves the executable bit)
   - Windows → `.zip`
   - `<os>` ∈ {`macos`, `linux`, `windows`}; `<arch>` ∈ {`x86_64`, `arm64`}
     (normalized from `platform.machine()`).

The archive contains just the executable (`llama` / `llama.exe`). `--dry-run`
prints the planned steps and the archive name, and skips PyInstaller + packaging.

### 3. `.github/workflows/release.yml`

Trimmed from `litcat`'s workflow.

- **Triggers:** push tag `v*`; `workflow_dispatch` with a `version` input and a
  `dry_run` boolean.
- **`permissions: contents: write`** (required to create the Release; no other
  scopes, no CF/signing secrets).
- **`prep` job** (any always-on self-hosted runner): resolve the version — from
  `${GITHUB_REF_NAME#v}` on tag push, or the `version` input on dispatch — and
  validate it against the strict charset `^[A-Za-z0-9._+-]+$` (retained verbatim
  from `litcat`, so a crafted tag name cannot inject into later shell steps).
  Emits `version` + `dry_run` outputs. Passes version to build jobs via `env` +
  quoted expansion, never string-interpolated into a `run:` body.
- **Four build jobs**, one per target, each on its `[self-hosted, <os>, <arch>]`
  runner: checkout → set up Python / project env → `python packaging/build.py
  --version "$VER"` → `upload-artifact` the `dist-release/` contents. (Windows
  job invokes the same `build.py` under `pwsh`/`python`.) A `dry_run` run passes
  `--dry-run` and skips the upload.
- **`release` job** (`needs:` all four; skipped on `dry_run`): download all
  artifacts, generate `SHA256SUMS` over the four archives, then
  `gh release create "v$VER"` (or `gh release upload` if it exists) attaching the
  four archives + `SHA256SUMS`. Uses the workflow's `GITHUB_TOKEN`.

Every job carries a generous `timeout-minutes` (fleet boxes can sleep), per
`litcat`'s convention.

### 4. Version wiring — `llama --version`

Goal: `--version` reports the injected build/tag version in the frozen binary,
while dev checkouts keep working and there is a single number to bump.

- **`src/llama/__init__.py`** resolves `__version__` as:
  1. `from llama._version import __version__` (the build-generated file), else
  2. `importlib.metadata.version("llama-radio")` (normal editable dev install →
     tracks `pyproject.toml`), else
  3. `"0.0.0+unknown"` fallback.
- **`src/llama/_version.py`** is generated by `build.py` (step 2) and
  **gitignored**. It is a normal module in the import graph, so PyInstaller
  bundles it with no special handling. Because it exists at freeze time,
  path (1) wins in the binary. In dev it is absent, so path (2) applies — no
  need to bundle package metadata into the binary.
- **`--version` flag:** add an eager `--version` `typer.Option` to the existing
  `@app.callback()` in `src/llama/cli.py` that prints `llama.__version__` and
  exits (`is_eager=True`, raises `typer.Exit()`). The existing `llama version`
  subcommand stays and shares the same `llama.__version__` source.

### 5. `pyproject.toml` / `.gitignore`

- `pyproject.toml`: add `pyinstaller>=6.10` to the `dev` optional-dependency
  group.
- `.gitignore`: add `build/`, `dist/`, `dist-release/`, and
  `src/llama/_version.py`.

## Runtime note (not a packaging concern)

The frozen binary bundles only `llama` and its Python deps. The LLM backend is
invoked at runtime, not bundled: the default `claude_cli` backend still expects a
`claude` executable on `PATH`, and `openrouter` still needs `OPENROUTER_API_KEY`.
The `fake` backend (used by the test suite) needs nothing. This is unchanged by
packaging and is called out only to set expectations for operators.

## Testing / verification

- **Build-time smoke test** (in `build.py`): frozen `llama --help` exits 0 on
  every platform, before publish.
- **Manual acceptance** (documented, not automated): on at least one target,
  run a `fake`-backend pipeline command end-to-end from the extracted binary to
  confirm the bundled prompts resolve (e.g. `llama --version` then a
  `fake`-backed `interpret`/`find` invocation).
- No change to the existing `pytest` suite; packaging adds no importable runtime
  code beyond the `_version.py` fallback, which is covered by exercising
  `llama --version`.

## Task breakdown (for the implementation plan)

1. Version plumbing: `__init__.py` resolver + `--version` flag in `cli.py`.
2. `packaging/llama.spec`.
3. `packaging/build.py` (incl. smoke test + archive naming).
4. `pyproject.toml` dev dep + `.gitignore` entries.
5. `.github/workflows/release.yml`.
6. Local verification on the dev host (macOS arm64): build, extract, run.
