# Self-Contained `llama` Binaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship single-file, self-contained `llama` executables for linux-x86_64, linux-arm64, macos-arm64, and windows-x86_64, published to GitHub Releases on tag push.

**Architecture:** PyInstaller **onefile** build driven by one cross-platform spec (`packaging/llama.spec`) and one cross-platform Python driver (`packaging/build.py`, which injects the version, runs PyInstaller, smoke-tests the binary, and produces a per-target archive). A trimmed GitHub Actions workflow runs the driver on the existing self-hosted runner fleet (one job per target) and attaches the archives + `SHA256SUMS` to a GitHub Release. Reuses the *spec pattern* from the sibling `litcat` project; drops all of litcat's signing/installer/upload machinery.

**Tech Stack:** Python 3.11+ (dev host is 3.14), PyInstaller 6.21+, Typer, GitHub Actions, self-hosted runners, `gh` CLI.

## Global Constraints

- Design source of truth: `docs/superpowers/specs/2026-07-14-llama-binaries-design.md`. Every task's requirements implicitly include it.
- **onefile only** — a single executable per target (`EXE` with no `COLLECT`/`BUNDLE`). No installers, no icons, no `.app`/AppImage.
- **Unsigned** — no code signing, notarization, or entitlements anywhere.
- Targets and runner labels are fixed:
  | OS | Arch | Runner label | Archive `<os>-<arch>` | Archive ext |
  |----|------|--------------|-----------------------|-------------|
  | Linux | x86_64 | `[self-hosted, linux, x64]` | `linux-x86_64` | `.tar.gz` |
  | Linux | arm64 | `[self-hosted, linux, arm64]` | `linux-arm64` | `.tar.gz` |
  | macOS | arm64 | `[self-hosted, macos, arm64]` | `macos-arm64` | `.tar.gz` |
  | Windows | x86_64 | `[self-hosted, windows, x64]` | `windows-x86_64` | `.zip` |
- Archive filename format: `llama-<version>-<os>-<arch>.<ext>`, containing only the executable (`llama` / `llama.exe`).
- Version env var is `LLAMA_VERSION`; strict version charset is `^[A-Za-z0-9._+-]+$`.
- Package dist name is `llama-radio`; the importable package is `llama`; the console entry is `llama.cli:app`.
- Do **not** commit `build/`, `dist/`, `dist-release/`, or `src/llama/_version.py`.
- The dev host (macOS arm64) can build/verify only the `macos-arm64` target locally; PyInstaller does not cross-compile.

---

### Task 1: Version plumbing (`__version__` resolver + `--version` flag)

Make `llama.__version__` resolve from a build-generated `_version.py` when present, else from installed package metadata, else a sentinel; and add a `--version` flag to the CLI. `_version.py` does not exist yet (Task 4 generates it), so in dev the metadata path is what runs.

**Files:**
- Modify: `src/llama/__init__.py` (currently one line: `__version__ = "0.1.0"`)
- Modify: `src/llama/cli.py:35-37` (the `@app.callback()` / `def main`)
- Test: `tests/test_version.py` (create)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `llama.__version__` (str) resolved via the precedence `llama._version.__version__` → `importlib.metadata.version("llama-radio")` → `"0.0.0+unknown"`. Task 4's `build.py` relies on writing `src/llama/_version.py` with `__version__ = "<ver>"` to override it in the frozen binary.

- [ ] **Step 1: Write the failing test**

Create `tests/test_version.py`:

```python
from importlib.metadata import version as pkg_version

from typer.testing import CliRunner

import llama
from llama.cli import app

runner = CliRunner()


def test_version_resolves_from_installed_metadata():
    # Editable dev install exposes the dist as "llama-radio"; the resolver must
    # find it and must NOT fall through to the unknown sentinel.
    assert llama.__version__ == pkg_version("llama-radio")
    assert llama.__version__ != "0.0.0+unknown"


def test_version_flag_prints_version_and_exits():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == llama.__version__


def test_version_subcommand_matches_flag():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.output.strip() == llama.__version__
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_version.py -v`
Expected: `test_version_flag_prints_version_and_exits` FAILS (no `--version` option yet → non-zero exit / usage error). The other two may already pass.

- [ ] **Step 3: Rewrite `src/llama/__init__.py`**

Replace the entire file with:

```python
"""llama-radio: Live Music Archive -> automated radio station pipeline."""

try:
    # Written by packaging/build.py at freeze time; absent in dev checkouts.
    from llama._version import __version__
except ImportError:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _pkg_version

    try:
        __version__ = _pkg_version("llama-radio")
    except PackageNotFoundError:  # not installed (raw checkout, no metadata)
        __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
```

- [ ] **Step 4: Add the `--version` flag in `src/llama/cli.py`**

Replace the existing callback (lines 35-37):

```python
@app.callback()
def main() -> None:
    """Find, vet, research, and package LMA concerts for broadcast."""
```

with:

```python
def _version_callback(value: bool) -> None:
    if value:
        import llama

        typer.echo(llama.__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Print the llama version and exit.",
    ),
) -> None:
    """Find, vet, research, and package LMA concerts for broadcast."""
```

Leave the existing `@app.command() def version()` (lines ~40-45) unchanged — it shares the same `llama.__version__` source.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_version.py -v`
Expected: all three PASS.

- [ ] **Step 6: Run the full suite (no regressions)**

Run: `pytest -q`
Expected: PASS (same as before, plus the 3 new tests).

- [ ] **Step 7: Commit**

```bash
git add src/llama/__init__.py src/llama/cli.py tests/test_version.py
git commit -m "feat: --version flag and build-injectable __version__ resolver"
```

---

### Task 2: Packaging dependency + gitignore

Add PyInstaller to the dev extra and ignore build outputs. Small enabler; Task 3 needs PyInstaller installed and Tasks 1/3/4 produce ignorable files.

**Files:**
- Modify: `pyproject.toml:18-19` (the `[project.optional-dependencies]` block)
- Modify: `.gitignore` (append)

**Interfaces:**
- Consumes: nothing.
- Produces: `pyinstaller` importable in the dev environment.

- [ ] **Step 1: Add PyInstaller to the dev extra**

In `pyproject.toml`, change:

```toml
[project.optional-dependencies]
dev = ["pytest>=8"]
```

to:

```toml
[project.optional-dependencies]
dev = ["pytest>=8", "pyinstaller>=6.21"]
```

- [ ] **Step 2: Append build outputs to `.gitignore`**

Append these lines to `.gitignore`:

```
build/
dist/
dist-release/
src/llama/_version.py
```

- [ ] **Step 3: Install and verify PyInstaller is available**

Run:
```bash
pip install -e ".[dev]"
python -c "import PyInstaller; print('PyInstaller', PyInstaller.__version__)"
```
Expected: prints `PyInstaller 6.21.0` (or newer).

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml .gitignore
git commit -m "build: add pyinstaller dev dep; ignore build outputs"
```

---

### Task 3: PyInstaller spec + `__main__.py` entry point

Create the frozen-binary entry point and the cross-platform spec. Verify a real onefile build on the dev host (macos-arm64).

**Files:**
- Create: `src/llama/__main__.py`
- Create: `packaging/llama.spec`

**Interfaces:**
- Consumes: `llama.cli:app` (existing Typer app); `llama.__version__` (Task 1).
- Produces: `dist/llama` (onefile executable) from `LLAMA_VERSION=<ver> pyinstaller packaging/llama.spec --clean --noconfirm`. Task 4 invokes this spec.

- [ ] **Step 1: Create the entry point**

`src/llama/__main__.py`:

```python
"""Entry point for the frozen binary and `python -m llama`."""

from llama.cli import app

if __name__ == "__main__":
    app()
```

- [ ] **Step 2: Verify the entry point runs**

Run: `python -m llama --version`
Expected: prints the dev version (e.g. `0.1.0`), exit 0. (Confirms `app()` is actually invoked.)

- [ ] **Step 3: Create `packaging/llama.spec`**

```python
# PyInstaller spec for llama. Cross-platform: same file on macOS, Linux, Windows.
#
# Build:   LLAMA_VERSION=<ver> pyinstaller packaging/llama.spec --clean --noconfirm
# Output:  dist/llama         (single self-contained executable)
#          dist/llama.exe     (on Windows)
#
# ruff: noqa
# (loaded as Python by PyInstaller; lint is not useful here)

import os
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

PROJECT_ROOT = Path(SPECPATH).parent  # type: ignore[name-defined]  # SPECPATH injected by PyInstaller

# Version is injected via LLAMA_VERSION (set by packaging/build.py from the git
# tag). Defaults to 0.0.0 for a plain spec run. Affects only the Windows
# file-version resource; the binary's own --version comes from _version.py.
LLAMA_VERSION = os.environ.get("LLAMA_VERSION", "0.0.0")


def _version_tuple(v):
    m = re.match(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\.(\d+))?", v or "")
    parts = [int(g) if g else 0 for g in (m.groups() if m else ())]
    parts += [0] * (4 - len(parts))
    return tuple(parts[:4])


# Windows file-version resource (Windows only). Failures must not break the
# build — fall back to no resource with a warning.
_win_version_file = None
if sys.platform == "win32":
    try:
        from PyInstaller.utils.win32.versioninfo import (
            FixedFileInfo,
            StringFileInfo,
            StringStruct,
            StringTable,
            VarFileInfo,
            VarStruct,
            VSVersionInfo,
        )

        _vt = _version_tuple(LLAMA_VERSION)
        _vsinfo = VSVersionInfo(
            ffi=FixedFileInfo(filevers=_vt, prodvers=_vt, mask=0x3F, flags=0x0,
                              OS=0x40004, fileType=0x1, subtype=0x0),
            kids=[
                StringFileInfo([StringTable("040904B0", [
                    StringStruct("CompanyName", "llama"),
                    StringStruct("FileDescription", "llama-radio"),
                    StringStruct("FileVersion", LLAMA_VERSION),
                    StringStruct("ProductName", "llama"),
                    StringStruct("ProductVersion", LLAMA_VERSION),
                    StringStruct("OriginalFilename", "llama.exe"),
                ])]),
                VarFileInfo([VarStruct("Translation", [1033, 1200])]),
            ],
        )
        _vfile = PROJECT_ROOT / "build" / "llama_version_info.txt"
        _vfile.parent.mkdir(parents=True, exist_ok=True)
        _vfile.write_text(str(_vsinfo), encoding="utf-8")
        _win_version_file = str(_vfile)
    except Exception as exc:  # noqa: BLE001
        print(f"[llama.spec] WARNING: could not build Windows version resource: {exc}")

# The one mandatory bundling step: prompt templates are loaded at runtime via
# importlib.resources.files("llama.prompts").
datas = collect_data_files("llama.prompts")

a = Analysis(  # type: ignore[name-defined]
    [str(PROJECT_ROOT / "src" / "llama" / "__main__.py")],
    pathex=[str(PROJECT_ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)  # type: ignore[name-defined]

exe = EXE(  # type: ignore[name-defined]
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="llama",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=_win_version_file,  # Windows resource (None elsewhere)
)
```

- [ ] **Step 4: Build the onefile binary on the dev host**

Run: `LLAMA_VERSION=9.9.9 pyinstaller packaging/llama.spec --clean --noconfirm`
Expected: completes without error; `dist/llama` exists and is a single file.
Check: `test -f dist/llama && file dist/llama`

- [ ] **Step 5: Smoke-test the built binary**

Run: `./dist/llama --help`
Expected: exit 0, prints the Typer help (the command list). This proves the import graph, Typer/Click, and pydantic-core all bundled correctly.

Note: `./dist/llama --version` here prints `0.0.0+unknown` — no `_version.py` was generated (Task 4 does that) and package metadata is not bundled. That is expected at this task; the injected-version path is verified in Task 4.

- [ ] **Step 6: Commit**

```bash
git add src/llama/__main__.py packaging/llama.spec
git commit -m "build: PyInstaller onefile spec and __main__ entry point"
```

---

### Task 4: Cross-platform build driver `packaging/build.py`

One script that injects the version, runs PyInstaller, smoke-tests, and packages the per-target archive. Runnable locally and from CI.

**Files:**
- Create: `packaging/build.py`

**Interfaces:**
- Consumes: `packaging/llama.spec` (Task 3); writes `src/llama/_version.py` consumed by the resolver in `src/llama/__init__.py` (Task 1).
- Produces: `dist-release/llama-<version>-<os>-<arch>.<ext>`. The GitHub workflow (Task 5) invokes `python packaging/build.py --version "<ver>"`.

- [ ] **Step 1: Create `packaging/build.py`**

```python
#!/usr/bin/env python3
"""Build a self-contained `llama` binary and package it as a release archive.

Usage:
    python packaging/build.py --version 1.2.3 [--dry-run]

Runs on macOS, Linux, and Windows. PyInstaller does not cross-compile, so this
builds only for the host's OS/arch. Output: dist-release/llama-<ver>-<os>-<arch>.<ext>
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SPEC = PROJECT_ROOT / "packaging" / "llama.spec"
DIST = PROJECT_ROOT / "dist"
DIST_RELEASE = PROJECT_ROOT / "dist-release"
VERSION_FILE = PROJECT_ROOT / "src" / "llama" / "_version.py"


def os_slug() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "win32":
        return "windows"
    raise SystemExit(f"unsupported platform: {sys.platform}")


def arch_slug() -> str:
    m = platform.machine().lower()
    if m in ("x86_64", "amd64"):
        return "x86_64"
    if m in ("arm64", "aarch64"):
        return "arm64"
    raise SystemExit(f"unsupported arch: {platform.machine()}")


def exe_name() -> str:
    return "llama.exe" if sys.platform == "win32" else "llama"


def write_version_file(version: str) -> None:
    VERSION_FILE.write_text(
        f'"""Generated by packaging/build.py — do not edit or commit."""\n'
        f'__version__ = "{version}"\n',
        encoding="utf-8",
    )


def run_pyinstaller(version: str) -> None:
    env = {**os.environ, "LLAMA_VERSION": version}
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", str(SPEC), "--clean", "--noconfirm"],
        cwd=PROJECT_ROOT,
        env=env,
        check=True,
    )


def smoke_test(version: str) -> None:
    binary = DIST / exe_name()
    if not binary.exists():
        raise SystemExit(f"build produced no binary at {binary}")
    help_res = subprocess.run([str(binary), "--help"], capture_output=True, text=True)
    if help_res.returncode != 0:
        raise SystemExit(f"smoke test failed: `llama --help` exited {help_res.returncode}\n{help_res.stderr}")
    ver_res = subprocess.run([str(binary), "--version"], capture_output=True, text=True)
    got = ver_res.stdout.strip()
    if ver_res.returncode != 0 or got != version:
        raise SystemExit(
            f"smoke test failed: `llama --version` returned {ver_res.returncode!r} / {got!r}, "
            f"expected {version!r}"
        )
    print(f"smoke test OK: llama --version -> {got}")


def package(version: str) -> Path:
    DIST_RELEASE.mkdir(parents=True, exist_ok=True)
    stem = f"llama-{version}-{os_slug()}-{arch_slug()}"
    # Stage the single binary in its own dir so the archive has a flat layout.
    stage = DIST_RELEASE / stem
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    shutil.copy2(DIST / exe_name(), stage / exe_name())
    fmt = "zip" if sys.platform == "win32" else "gztar"
    archive = shutil.make_archive(str(DIST_RELEASE / stem), fmt, root_dir=stage)
    shutil.rmtree(stage)
    print(f"packaged: {archive}")
    return Path(archive)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ext = "zip" if sys.platform == "win32" else "tar.gz"
    planned = f"dist-release/llama-{args.version}-{os_slug()}-{arch_slug()}.{ext}"
    if args.dry_run:
        print(f"dry-run: would build and package {planned}")
        return

    write_version_file(args.version)
    run_pyinstaller(args.version)
    smoke_test(args.version)
    package(args.version)


if __name__ == "__main__":
    main()
```

Note on the archive extension: `shutil.make_archive(..., "gztar")` yields a `.tar.gz` file, and `"zip"` yields `.zip`, matching `planned`.

- [ ] **Step 2: Run the driver end-to-end on the dev host**

Run: `python packaging/build.py --version 9.9.9`
Expected: PyInstaller runs; prints `smoke test OK: llama --version -> 9.9.9`; prints `packaged: .../dist-release/llama-9.9.9-macos-arm64.tar.gz`.

- [ ] **Step 3: Verify the archive extracts and the binary reports the injected version**

Run:
```bash
mkdir -p /tmp/llama-verify && tar -xzf dist-release/llama-9.9.9-macos-arm64.tar.gz -C /tmp/llama-verify
/tmp/llama-verify/llama --version
```
Expected: prints `9.9.9`.

- [ ] **Step 4: Verify `_version.py` is untracked**

Run: `git status --porcelain src/llama/_version.py`
Expected: **no output** (it is gitignored per Task 2). If it shows up, the `.gitignore` entry is missing — fix before committing.

- [ ] **Step 5: (Recommended, manual) confirm prompt bundling**

`--help`/`--version` do not exercise the bundled prompts. On the dev host, run one offline `fake`-backend command that reads a prompt template and confirm there is no "prompt not found"/resource error (see the design spec's Testing section). This is the acceptance check for `collect_data_files("llama.prompts")`. If a prompt fails to resolve in the frozen binary, add `datas += collect_data_files("llama", includes=["prompts/*.md"])` handling or a hidden import as needed and rebuild.

- [ ] **Step 6: Clean up and commit**

```bash
rm -rf /tmp/llama-verify dist dist-release build src/llama/_version.py
git add packaging/build.py
git commit -m "build: cross-platform build driver with smoke test and archive packaging"
```

---

### Task 5: GitHub Actions release workflow

Build all four targets on the self-hosted fleet and publish a GitHub Release. This is the one task not fully verifiable on the dev host — validate YAML/structure locally and exercise via a `dry_run` dispatch once merged.

**Files:**
- Create: `.github/workflows/release.yml`

**Interfaces:**
- Consumes: `packaging/build.py --version <ver>` (Task 4) on each runner.
- Produces: a GitHub Release for tag `v<version>` with four archives + `SHA256SUMS`.

- [ ] **Step 1: Create `.github/workflows/release.yml`**

```yaml
name: release

# Build llama's four self-contained binaries across the self-hosted fleet and
# attach them to a GitHub Release. Unsigned: no on-box secrets, GITHUB_TOKEN only.
# PyInstaller does not cross-compile, so each artifact is built on native hardware.

on:
  push:
    tags:
      - 'v*'
  workflow_dispatch:
    inputs:
      version:
        description: "Version to build, e.g. 0.1.0 (required for manual runs)."
        required: false
        type: string
      dry_run:
        description: "Plan only — run build.py in dry-run mode; no artifacts, no release."
        type: boolean
        default: false

permissions:
  contents: write   # required to create the GitHub Release

concurrency:
  group: release-${{ github.ref }}
  cancel-in-progress: false

jobs:
  prep:
    runs-on: [self-hosted, linux, x64]
    timeout-minutes: 10
    outputs:
      version: ${{ steps.resolve.outputs.version }}
      dry_run: ${{ steps.resolve.outputs.dry_run }}
    steps:
      - id: resolve
        shell: bash
        env:
          EVENT_NAME: ${{ github.event_name }}
          REF_NAME: ${{ github.ref_name }}
          IN_VERSION: ${{ inputs.version }}
          IN_DRY: ${{ inputs.dry_run }}
        run: |
          set -euo pipefail
          if [ "$EVENT_NAME" = "push" ]; then
            ver="${REF_NAME#v}"; dry="false"
          else
            ver="$IN_VERSION"; dry="${IN_DRY:-false}"
          fi
          if [ -z "$ver" ]; then
            echo "::error::version is required (push a v* tag or pass the version input)"; exit 1
          fi
          # Strict allowlist — neutralises shell metacharacters a crafted tag could carry.
          if ! printf '%s' "$ver" | grep -Eq '^[A-Za-z0-9._+-]+$'; then
            echo "::error::version '$ver' contains disallowed characters"; exit 1
          fi
          {
            echo "version=$ver"
            echo "dry_run=$dry"
          } >> "$GITHUB_OUTPUT"
          echo "Resolved: version=$ver dry_run=$dry"

  build:
    needs: prep
    strategy:
      fail-fast: false
      matrix:
        include:
          - { os: linux,   arch: x64,   labels: [self-hosted, linux, x64] }
          - { os: linux,   arch: arm64, labels: [self-hosted, linux, arm64] }
          - { os: macos,   arch: arm64, labels: [self-hosted, macos, arm64] }
          - { os: windows, arch: x64,   labels: [self-hosted, windows, x64] }
    runs-on: ${{ matrix.labels }}
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - name: Set up project
        shell: bash
        run: |
          set -euo pipefail
          python3 -m venv .venv
          . .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate
          python -m pip install --upgrade pip
          pip install -e ".[dev]"
      - name: Build
        shell: bash
        env:
          VER: ${{ needs.prep.outputs.version }}
          DRY: ${{ needs.prep.outputs.dry_run }}
        run: |
          set -euo pipefail
          . .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate
          if [ "$DRY" = "true" ]; then
            python packaging/build.py --version "$VER" --dry-run
          else
            python packaging/build.py --version "$VER"
          fi
      - uses: actions/upload-artifact@v4
        if: needs.prep.outputs.dry_run != 'true'
        with:
          name: ${{ matrix.os }}-${{ matrix.arch }}
          path: dist-release/*
          if-no-files-found: error

  release:
    needs: [prep, build]
    if: needs.prep.outputs.dry_run != 'true'
    runs-on: [self-hosted, linux, x64]
    timeout-minutes: 15
    env:
      GH_TOKEN: ${{ github.token }}
      VER: ${{ needs.prep.outputs.version }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          path: dist-release
          merge-multiple: true
      - name: Checksums
        shell: bash
        run: |
          set -euo pipefail
          cd dist-release
          shasum -a 256 llama-* > SHA256SUMS
          echo "=== SHA256SUMS ==="; cat SHA256SUMS
      - name: Create GitHub Release
        shell: bash
        run: |
          set -euo pipefail
          gh release create "v$VER" \
            --title "v$VER" \
            --notes "llama $VER — self-contained binaries. Verify with SHA256SUMS." \
            dist-release/llama-* dist-release/SHA256SUMS
```

- [ ] **Step 2: Validate the workflow YAML locally**

Run: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/release.yml')); print('yaml ok')"`
Expected: `yaml ok`. If `actionlint` is installed, also run `actionlint .github/workflows/release.yml` and expect no errors.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "ci: release workflow — four self-hosted binaries to GitHub Releases"
```

- [ ] **Step 4: (Post-merge, manual) exercise via dry-run then a real tag**

Once merged to a branch the fleet can see:
1. `gh workflow run release.yml -f version=0.1.0 -f dry_run=true` → confirm all four `build` jobs pass and print `dry-run: would build and package ...` with correct `<os>-<arch>` names.
2. For a real release: `git tag v0.1.0 && git push origin v0.1.0` → confirm the `release` job attaches four archives + `SHA256SUMS` to the `v0.1.0` release.

---

## Self-Review

**Spec coverage:**
- Targets/labels table → Global Constraints + Task 5 matrix. ✓
- PyInstaller onefile, `collect_data_files("llama.prompts")`, Windows version resource, no signing → Task 3 spec. ✓
- `build.py` (version inject, smoke test, archive naming) → Task 4. ✓
- Workflow (triggers, strict version validation, four jobs, SHA256SUMS, GitHub Release) → Task 5. ✓
- `--version` flag + `_version.py`/metadata resolver → Task 1. ✓
- `pyinstaller` dev dep + gitignore (incl. `_version.py`) → Task 2. ✓
- Local macos-arm64 verification → folded into Task 3 Step 4-5 and Task 4 Steps 2-5. ✓
- Runtime note (external `claude`/`OPENROUTER_API_KEY`) → design spec only; no code. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete content. Task 4 Step 5 and Task 5 Step 4 are explicitly manual/post-merge acceptance steps, not placeholders. ✓

**Type consistency:** `LLAMA_VERSION` (env), `llama.__version__` (resolver), `_version.py` `__version__` string, archive stem `llama-<version>-<os>-<arch>`, os slugs {macos,linux,windows}, arch slugs {x86_64,arm64} — consistent across Tasks 1, 3, 4, 5. `build.py` writes `_version.py` exactly where Task 1's resolver imports it (`src/llama/_version.py`). ✓
