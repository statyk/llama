# Signed macOS + Windows Release Binaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sign the macOS release binary (Developer ID + hardened runtime + notarization) and the Windows release binary (Azure Trusted Signing) so Gatekeeper/SmartScreen accept them, with no signing secrets in the repo or CI — all credentials stay machine-side on the runners.

**Architecture:** All signing logic goes into `packaging/build.py` (Python), which already is the single cross-platform build orchestrator run identically on every fleet leg. On darwin it codesigns + notarizes the bare onefile Mach-O (no stapling — impossible for a bare executable; Gatekeeper checks online on first run). On win32 it Authenticode-signs the onefile `.exe` with the x64 `signtool.exe` + `Azure.CodeSigning.Dlib.dll` driven by `packaging/metadata.json`. Pure decision helpers are unit-tested offline; the subprocess-driven signing bodies get on-hardware verification. `packaging/llama.spec` is unchanged. A `--skip-sign` flag preserves today's unsigned build for local/dev use.

**Tech Stack:** Python 3.11+ (stdlib `subprocess`/`plistlib`/`json`/`shutil`/`tempfile`/`re`), PyInstaller, pytest. macOS: `codesign`, `xcrun notarytool`, `ditto`, `spctl`, `security`. Windows: `signtool.exe`, `Azure.CodeSigning.Dlib.dll`, `az`.

**Spec:** `docs/superpowers/specs/2026-07-17-signed-binaries-design.md`

## Global Constraints

- All tests offline and deterministic (`pytest -q` must pass with no network); the existing 418-test suite stays green.
- Never commit audio files.
- No signing secrets in the repo or GitHub; credentials are machine-side on the runners.
- `packaging/llama.spec` stays unchanged (signing is explicit in `build.py`).
- Signing/notarization failure must fail the leg (non-zero exit, no artifact); signing runs after the smoke test and before packaging.
- Commit messages end with:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_01KZjRuTv8v58qy5izqvxiFF`

**Operator-owned open questions (do not block implementation; the guarded template + defaults let the plan proceed):**
1. `packaging/metadata.json` real Azure values (`CodeSigningAccountName` / `CertificateProfileName` / `Endpoint`) — committed as a placeholder-guarded template; the operator fills real values once.
2. macOS notary profile — code defaults to `llama-notary`; operator either creates that profile once or sets `LLAMA_NOTARY_PROFILE=litcat-notary` to reuse the existing one.

---

### Task 1: macOS signing + notarization in `build.py`

**Files:**
- Create: `packaging/llama.entitlements`
- Modify: `packaging/build.py` (add imports, constants, helpers, `macos_sign`, CLI options, `main()` dispatch + dry-run plan)
- Test: `tests/test_packaging.py` (create)

**Interfaces:**
- Consumes: existing `packaging/build.py` (`PROJECT_ROOT`, `DIST`, `exe_name`, `os_slug`, `arch_slug`, `write_version_file`, `run_pyinstaller`, `smoke_test`, `package`, `main`).
- Produces (Task 2 and later rely on these exact names in `packaging/build.py`):
  - `ENTITLEMENTS: Path`, `METADATA: Path` module constants.
  - `resolve_codesign_identity(explicit: str | None, env: dict, find_identity_output: str) -> str`
  - `resolve_notary_auth(env: dict, profile: str, keychain: str | None, identity: str | None) -> tuple[list[str], str]`
  - `wants_dedicated_keychain(env: dict) -> bool`
  - `codesign_cmd(binary: Path, identity: str, entitlements: Path) -> list[str]`
  - `macos_sign(binary: Path, identity: str | None, notary_profile: str, env: dict | None = None) -> None`
  - `_print_sign_plan(args) -> None`
  - `main()` gains `--skip-sign`, `--identity`, `--notary-profile` and a `sys.platform == "darwin"` signing dispatch.

- [ ] **Step 1: Write the entitlements file**

Create `packaging/llama.entitlements` (exactly the two keys a hardened-runtime PyInstaller onefile needs; llama is a headless CLI, so no camera/TCC keys):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <!-- PyInstaller's onefile bootloader maps the embedded Python as
         executable memory; the hardened runtime blocks that without this. -->
    <key>com.apple.security.cs.allow-unsigned-executable-memory</key>
    <true/>
    <!-- Bundled .so/.dylib extension modules carry their own signatures that
         differ from the outer Developer ID; allow them under hardened runtime. -->
    <key>com.apple.security.cs.disable-library-validation</key>
    <true/>
</dict>
</plist>
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_packaging.py`:

```python
"""Offline unit tests for packaging/build.py signing helpers.

build.py is a script under packaging/ (not an importable package), so we load
it by path once for the whole module.
"""
import importlib.util
import json
import plistlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("llama_build", ROOT / "packaging" / "build.py")
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)

FIND_ONE = '  1) ABCDEF "Developer ID Application: Jane Roe (TEAM123456)"\n     1 valid identities found\n'


# --- entitlements config ----------------------------------------------------

def test_entitlements_has_exactly_the_required_keys():
    data = plistlib.loads((ROOT / "packaging" / "llama.entitlements").read_bytes())
    assert data == {
        "com.apple.security.cs.allow-unsigned-executable-memory": True,
        "com.apple.security.cs.disable-library-validation": True,
    }


# --- codesign identity resolution ------------------------------------------

def test_identity_explicit_wins():
    assert build.resolve_codesign_identity("X", {"LLAMA_CODESIGN_IDENTITY": "Y"}, FIND_ONE) == "X"


def test_identity_env_used_when_no_flag():
    assert build.resolve_codesign_identity(None, {"LLAMA_CODESIGN_IDENTITY": "Y"}, "") == "Y"


def test_identity_autodetects_sole_match():
    got = build.resolve_codesign_identity(None, {}, FIND_ONE)
    assert got == "Developer ID Application: Jane Roe (TEAM123456)"


def test_identity_none_raises():
    with pytest.raises(SystemExit):
        build.resolve_codesign_identity(None, {}, "0 valid identities found")


def test_identity_ambiguous_raises():
    two = '"Developer ID Application: A (T1)"\n"Developer ID Application: B (T2)"'
    with pytest.raises(SystemExit):
        build.resolve_codesign_identity(None, {}, two)


# --- notary auth resolution -------------------------------------------------

def test_notary_api_key_path():
    env = {"LLAMA_NOTARY_KEY": "/k.p8", "LLAMA_NOTARY_KEY_ID": "KID", "LLAMA_NOTARY_ISSUER": "ISS"}
    args, kind = build.resolve_notary_auth(env, "llama-notary", None, None)
    assert args == ["--key", "/k.p8", "--key-id", "KID", "--issuer", "ISS"]
    assert "API key" in kind


def test_notary_apple_id_team_from_env():
    env = {"LLAMA_NOTARY_APPLE_ID": "me@x.com", "LLAMA_NOTARY_PASSWORD": "pw", "LLAMA_NOTARY_TEAM_ID": "T9"}
    args, _ = build.resolve_notary_auth(env, "llama-notary", None, None)
    assert args == ["--apple-id", "me@x.com", "--password", "pw", "--team-id", "T9"]


def test_notary_apple_id_team_parsed_from_identity():
    env = {"LLAMA_NOTARY_APPLE_ID": "me@x.com", "LLAMA_NOTARY_PASSWORD": "pw"}
    args, _ = build.resolve_notary_auth(env, "llama-notary", None, "Developer ID Application: X (TEAM42)")
    assert args[-2:] == ["--team-id", "TEAM42"]


def test_notary_apple_id_without_team_raises():
    env = {"LLAMA_NOTARY_APPLE_ID": "a", "LLAMA_NOTARY_PASSWORD": "b"}
    with pytest.raises(SystemExit):
        build.resolve_notary_auth(env, "p", None, None)


def test_notary_profile_with_keychain():
    args, kind = build.resolve_notary_auth({}, "llama-notary", "/kc.db", None)
    assert args == ["--keychain-profile", "llama-notary", "--keychain", "/kc.db"]
    assert "llama-notary" in kind


def test_notary_profile_without_keychain():
    args, _ = build.resolve_notary_auth({}, "llama-notary", None, None)
    assert args == ["--keychain-profile", "llama-notary"]


# --- misc mac helpers -------------------------------------------------------

def test_wants_dedicated_keychain():
    assert build.wants_dedicated_keychain({"LLAMA_SIGNING_P12": "/x.p12"}) is True
    assert build.wants_dedicated_keychain({}) is False


def test_codesign_cmd_argv():
    cmd = build.codesign_cmd(Path("/d/llama"), "Developer ID Application: X (T)", Path("/e.ent"))
    assert cmd == [
        "codesign", "--force", "--options", "runtime",
        "--entitlements", "/e.ent",
        "--sign", "Developer ID Application: X (T)", "/d/llama",
    ]


# --- main() dispatch + dry-run plan ----------------------------------------

def test_main_dry_run_prints_plan(monkeypatch, capsys):
    monkeypatch.setattr(build.sys, "argv", ["build.py", "--version", "1.2.3", "--dry-run"])
    build.main()
    assert "dry-run: would build and package" in capsys.readouterr().out


def test_main_dry_run_skip_sign_notes_skip(monkeypatch, capsys):
    monkeypatch.setattr(build.sys, "argv", ["build.py", "--version", "1.2.3", "--dry-run", "--skip-sign"])
    build.main()
    assert "SKIPPED" in capsys.readouterr().out


def test_main_skip_sign_does_not_call_sign(monkeypatch):
    calls = []
    monkeypatch.setattr(build, "write_version_file", lambda v: None)
    monkeypatch.setattr(build, "run_pyinstaller", lambda v: None)
    monkeypatch.setattr(build, "smoke_test", lambda v: None)
    monkeypatch.setattr(build, "package", lambda v: calls.append("package"))
    monkeypatch.setattr(build, "macos_sign", lambda *a, **k: calls.append("macos_sign"))
    monkeypatch.setattr(build.sys, "argv", ["build.py", "--version", "1.0.0", "--skip-sign"])
    build.main()
    assert calls == ["package"]


def test_main_darwin_signs_then_packages(monkeypatch):
    calls = []
    monkeypatch.setattr(build, "write_version_file", lambda v: None)
    monkeypatch.setattr(build, "run_pyinstaller", lambda v: None)
    monkeypatch.setattr(build, "smoke_test", lambda v: None)
    monkeypatch.setattr(build, "package", lambda v: calls.append("package"))
    monkeypatch.setattr(build, "macos_sign", lambda *a, **k: calls.append("macos_sign"))
    monkeypatch.setattr(build.sys, "platform", "darwin")
    monkeypatch.setattr(build.sys, "argv", ["build.py", "--version", "1.0.0"])
    build.main()
    assert calls == ["macos_sign", "package"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_packaging.py -q`
Expected: FAIL — `FileNotFoundError`/`AttributeError` (helpers not defined) and, once the file exists, the entitlements test passes but the rest fail until Step 4/5.

- [ ] **Step 4: Add imports and constants to `build.py`**

In `packaging/build.py`, extend the stdlib imports (currently `argparse, os, platform, shutil, subprocess, sys` + `from pathlib import Path`) to also import `re` and `tempfile`:

```python
import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
```

After the existing path constants (`VERSION_FILE = ...`), add:

```python
ENTITLEMENTS = PROJECT_ROOT / "packaging" / "llama.entitlements"
METADATA = PROJECT_ROOT / "packaging" / "metadata.json"
```

- [ ] **Step 5: Add the macOS helpers and `macos_sign` to `build.py`**

Insert after `smoke_test` (before `package`):

```python
# --- macOS code signing + notarization -------------------------------------
# The mac artifact is a BARE onefile Mach-O (not a .app), so it is codesigned
# with the hardened runtime + entitlements and notarized, but CANNOT be stapled
# (stapler only staples bundles/DMGs/installers). Gatekeeper does an online
# notarization check on first run instead. The signed binary must ship UNCHANGED
# after submission — re-signing would change its cdhash and break that check.


def resolve_codesign_identity(explicit: str | None, env: dict, find_identity_output: str) -> str:
    """Developer ID Application identity. Precedence: explicit > env > sole match
    in `security find-identity -v -p codesigning`. Fail on zero / ambiguous."""
    ident = explicit or env.get("LLAMA_CODESIGN_IDENTITY")
    if ident:
        return ident
    names = sorted(set(re.findall(r'"(Developer ID Application:[^"]+)"', find_identity_output)))
    if not names:
        raise SystemExit(
            "no 'Developer ID Application' identity found in the login keychain.\n"
            "  Set LLAMA_CODESIGN_IDENTITY or pass --identity, or build with --skip-sign.\n"
            "  List identities: security find-identity -v -p codesigning"
        )
    if len(names) > 1:
        raise SystemExit(
            f"multiple Developer ID Application identities found: {names}\n"
            "  Disambiguate with LLAMA_CODESIGN_IDENTITY or --identity."
        )
    return names[0]


def _team_from_identity(identity: str | None) -> str:
    m = re.search(r"\(([A-Z0-9]+)\)\s*$", identity or "")
    return m.group(1) if m else ""


def resolve_notary_auth(env: dict, profile: str, keychain: str | None,
                        identity: str | None) -> tuple[list[str], str]:
    """notarytool auth args + human description. Precedence: API key >
    Apple-ID+password > keychain profile (pinned with --keychain)."""
    key, key_id, issuer = (env.get("LLAMA_NOTARY_KEY"), env.get("LLAMA_NOTARY_KEY_ID"),
                           env.get("LLAMA_NOTARY_ISSUER"))
    if key and key_id and issuer:
        return (["--key", key, "--key-id", key_id, "--issuer", issuer], f"API key ({key_id})")
    apple_id, password = env.get("LLAMA_NOTARY_APPLE_ID"), env.get("LLAMA_NOTARY_PASSWORD")
    if apple_id and password:
        team = env.get("LLAMA_NOTARY_TEAM_ID") or _team_from_identity(identity)
        if not team:
            raise SystemExit(
                "notary Apple-ID auth needs a team id: set LLAMA_NOTARY_TEAM_ID "
                "(or use a signing identity ending in '(TEAMID)')."
            )
        return (["--apple-id", apple_id, "--password", password, "--team-id", team],
                f"Apple ID ({apple_id}, team {team})")
    args = ["--keychain-profile", profile]
    if keychain:
        args += ["--keychain", str(keychain)]
    return (args, f"keychain profile '{profile}'")


def wants_dedicated_keychain(env: dict) -> bool:
    return bool(env.get("LLAMA_SIGNING_P12"))


def codesign_cmd(binary: Path, identity: str, entitlements: Path) -> list[str]:
    return ["codesign", "--force", "--options", "runtime",
            "--entitlements", str(entitlements), "--sign", identity, str(binary)]


def _user_keychains() -> list[str]:
    out = subprocess.run(["security", "list-keychains", "-d", "user"],
                         capture_output=True, text=True).stdout
    return [ln.strip().strip('"') for ln in out.splitlines() if ln.strip()]


def _setup_signing_keychain(env: dict):
    """Headless codesign: import LLAMA_SIGNING_P12 into a throwaway keychain we
    unlock ourselves (the login keychain's key is unusable from a background
    runner session). Returns a teardown callable."""
    p12 = env["LLAMA_SIGNING_P12"]
    p12_pw = env.get("LLAMA_SIGNING_P12_PASSWORD")
    kc_pw = env.get("LLAMA_SIGNING_KEYCHAIN_PASSWORD")
    if not Path(p12).exists():
        raise SystemExit(f"LLAMA_SIGNING_P12 not found: {p12}")
    if not p12_pw or not kc_pw:
        raise SystemExit("set LLAMA_SIGNING_P12_PASSWORD and LLAMA_SIGNING_KEYCHAIN_PASSWORD "
                         "alongside LLAMA_SIGNING_P12")
    tmp = str(Path(tempfile.gettempdir()) / f"llama-signing-{os.getpid()}.keychain-db")
    orig = _user_keychains()
    subprocess.run(["security", "create-keychain", "-p", kc_pw, tmp], check=True)
    subprocess.run(["security", "set-keychain-settings", tmp], check=True)
    subprocess.run(["security", "unlock-keychain", "-p", kc_pw, tmp], check=True)
    subprocess.run(["security", "import", p12, "-k", tmp, "-P", p12_pw,
                    "-T", "/usr/bin/codesign"], check=True)
    subprocess.run(["security", "set-key-partition-list", "-S",
                    "apple-tool:,apple:,codesign:", "-s", "-k", kc_pw, tmp], check=True)
    subprocess.run(["security", "list-keychains", "-d", "user", "-s", tmp, *orig], check=True)

    def teardown():
        subprocess.run(["security", "list-keychains", "-d", "user", "-s", *orig], check=False)
        subprocess.run(["security", "delete-keychain", tmp], check=False)

    return teardown


def macos_sign(binary: Path, identity: str | None, notary_profile: str,
               env: dict | None = None) -> None:
    env = os.environ if env is None else env
    if not ENTITLEMENTS.exists():
        raise SystemExit(f"entitlements file missing: {ENTITLEMENTS}")
    found = subprocess.run(["security", "find-identity", "-v", "-p", "codesigning"],
                           capture_output=True, text=True).stdout
    ident = resolve_codesign_identity(identity, env, found)
    teardown = _setup_signing_keychain(env) if wants_dedicated_keychain(env) else None
    try:
        print(f"codesign: {ident}")
        subprocess.run(codesign_cmd(binary, ident, ENTITLEMENTS), check=True)
        subprocess.run(["codesign", "--verify", "--strict", "--verbose=2", str(binary)], check=True)

        if "LLAMA_NOTARY_KEYCHAIN" in env:
            keychain = env["LLAMA_NOTARY_KEYCHAIN"] or None
        else:
            keychain = str(Path.home() / "Library" / "Keychains" / "login.keychain-db")
        auth, kind = resolve_notary_auth(env, notary_profile, keychain, ident)
        print(f"notarize: {kind}")
        zip_path = binary.with_suffix(".notarize.zip")
        if zip_path.exists():
            zip_path.unlink()
        subprocess.run(["ditto", "-c", "-k", str(binary), str(zip_path)], check=True)
        subprocess.run(["xcrun", "notarytool", "submit", str(zip_path), *auth, "--wait"], check=True)
        zip_path.unlink()
        # Bare Mach-O: no stapling. Best-effort Gatekeeper assessment (don't fail on it).
        subprocess.run(["spctl", "--assess", "--type", "exec", "--verbose=2", str(binary)], check=False)
        print(f"signed + notarized: {binary} (not stapled — Gatekeeper checks online on first run)")
    finally:
        if teardown:
            teardown()
```

- [ ] **Step 6: Wire signing into `main()` and add the dry-run plan**

Replace the `main()` function body's argument parser and build sequence. The new `main()` is:

```python
def _print_sign_plan(args) -> None:
    if args.skip_sign:
        print("  sign: SKIPPED (--skip-sign)")
        return
    if sys.platform == "darwin":
        print("  sign: codesign --options runtime --entitlements packaging/llama.entitlements")
        print("  notarize: xcrun notarytool submit --wait  (no stapling — online check on first run)")
    else:
        print("  sign: n/a (linux)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-sign", action="store_true",
                    help="produce an unsigned build (local/dev; the release workflow never passes this)")
    ap.add_argument("--identity",
                    help="macOS Developer ID Application identity "
                         "(default: auto-detect / LLAMA_CODESIGN_IDENTITY)")
    ap.add_argument("--notary-profile", default=os.environ.get("LLAMA_NOTARY_PROFILE", "llama-notary"),
                    help="notarytool keychain profile (default llama-notary / LLAMA_NOTARY_PROFILE)")
    args = ap.parse_args()

    ext = "zip" if sys.platform == "win32" else "tar.gz"
    planned = f"dist-release/llama-{args.version}-{os_slug()}-{arch_slug()}.{ext}"
    if args.dry_run:
        print(f"dry-run: would build and package {planned}")
        _print_sign_plan(args)
        return

    write_version_file(args.version)
    run_pyinstaller(args.version)
    smoke_test(args.version)
    if not args.skip_sign:
        binary = DIST / exe_name()
        if sys.platform == "darwin":
            macos_sign(binary, args.identity, args.notary_profile)
    package(args.version)
```

(Task 2 adds the `win32` branches to `_print_sign_plan` and `main`.)

- [ ] **Step 7: Run the packaging tests**

Run: `pytest tests/test_packaging.py -q`
Expected: all PASS (the Windows-specific tests arrive in Task 2).

- [ ] **Step 8: Run the full offline suite**

Run: `pytest -q`
Expected: all PASS (419+ tests).

- [ ] **Step 9: Commit**

```bash
git add packaging/llama.entitlements packaging/build.py tests/test_packaging.py
git commit -m "feat: sign + notarize the macOS release binary in build.py

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KZjRuTv8v58qy5izqvxiFF"
```

---

### Task 2: Windows Authenticode signing in `build.py`

**Files:**
- Create: `packaging/metadata.json`
- Modify: `packaging/build.py` (constants, Windows helpers, `windows_sign`, `_print_sign_plan` + `main()` win32 dispatch)
- Test: `tests/test_packaging.py` (append)

**Interfaces:**
- Consumes: `METADATA` constant and `main()`/`_print_sign_plan` from Task 1.
- Produces (used by nothing later, but the release workflow relies on the behavior):
  - `discover_signtool(fixed_path: Path, kits_bin_dir: Path) -> Path`
  - `signtool_sign_cmd(signtool, dlib, metadata, timestamp, digest, files) -> list[str]`
  - `ensure_az_on_path(env: dict, candidate_dirs=..., which=shutil.which) -> dict`
  - `check_metadata_not_placeholder(text: str) -> None`
  - `windows_sign(binary: Path, env: dict | None = None) -> None`
  - `main()` gains a `sys.platform == "win32"` signing dispatch.

- [ ] **Step 1: Write the metadata template**

Create `packaging/metadata.json` (placeholder-guarded — `windows_sign` refuses to sign until the operator fills real values; account/profile/endpoint are open question #1):

```json
{
  "Endpoint": "https://eus.codesigning.azure.net/",
  "CodeSigningAccountName": "<my-account-name>",
  "CertificateProfileName": "<my-profile-name>",
  "ExcludeCredentials": [
    "ManagedIdentityCredential",
    "InteractiveBrowserCredential"
  ]
}
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_packaging.py`:

```python
# --- metadata config --------------------------------------------------------

def test_metadata_has_expected_keys():
    data = json.loads((ROOT / "packaging" / "metadata.json").read_text())
    assert set(data) >= {"Endpoint", "CodeSigningAccountName",
                         "CertificateProfileName", "ExcludeCredentials"}


def test_check_metadata_placeholder_raises():
    with pytest.raises(SystemExit):
        build.check_metadata_not_placeholder('{"CodeSigningAccountName": "<my-account-name>"}')


def test_check_metadata_real_passes():
    build.check_metadata_not_placeholder('{"CodeSigningAccountName": "llama"}')  # no raise


# --- signtool discovery -----------------------------------------------------

def test_discover_signtool_prefers_fixed(tmp_path):
    fixed = tmp_path / "fixed" / "signtool.exe"
    fixed.parent.mkdir(parents=True)
    fixed.write_text("")
    assert build.discover_signtool(fixed, tmp_path) == fixed


def test_discover_signtool_picks_newest_x64(tmp_path):
    missing = tmp_path / "missing.exe"
    for ver in ("10.0.19041.0", "10.0.28000.0"):
        d = tmp_path / "bin" / ver / "x64"
        d.mkdir(parents=True)
        (d / "signtool.exe").write_text("")
    got = build.discover_signtool(missing, tmp_path / "bin")
    assert got.parent.parent.name == "10.0.28000.0"


def test_discover_signtool_none_raises(tmp_path):
    with pytest.raises(SystemExit):
        build.discover_signtool(tmp_path / "x.exe", tmp_path / "empty")


# --- signtool argv ----------------------------------------------------------

def test_signtool_sign_cmd_argv():
    cmd = build.signtool_sign_cmd(
        Path("/s/signtool.exe"), Path("/d/dlib.dll"), Path("/m/metadata.json"),
        "http://ts", "SHA256", [Path("/x/llama.exe")],
    )
    assert cmd == [
        "/s/signtool.exe", "sign", "/v", "/debug", "/fd", "SHA256",
        "/tr", "http://ts", "/td", "SHA256",
        "/dlib", "/d/dlib.dll", "/dmdf", "/m/metadata.json", "/x/llama.exe",
    ]


# --- az PATH healing --------------------------------------------------------

def test_ensure_az_noop_when_present():
    env = {"PATH": "/x"}
    assert build.ensure_az_on_path(env, which=lambda *a, **k: "/usr/bin/az") is env


def test_ensure_az_prepends_wbin(tmp_path):
    (tmp_path / "az.cmd").write_text("")
    out = build.ensure_az_on_path({"PATH": "/x"}, candidate_dirs=[str(tmp_path)],
                                  which=lambda *a, **k: None)
    assert out["PATH"].startswith(str(tmp_path))


def test_ensure_az_noop_when_absent(tmp_path):
    env = {"PATH": "/x"}
    out = build.ensure_az_on_path(env, candidate_dirs=[str(tmp_path / "nope")],
                                  which=lambda *a, **k: None)
    assert out == env


# --- main() win32 dispatch --------------------------------------------------

def test_main_win32_signs_then_packages(monkeypatch):
    calls = []
    monkeypatch.setattr(build, "write_version_file", lambda v: None)
    monkeypatch.setattr(build, "run_pyinstaller", lambda v: None)
    monkeypatch.setattr(build, "smoke_test", lambda v: None)
    monkeypatch.setattr(build, "package", lambda v: calls.append("package"))
    monkeypatch.setattr(build, "windows_sign", lambda *a, **k: calls.append("windows_sign"))
    monkeypatch.setattr(build.sys, "platform", "win32")
    monkeypatch.setattr(build.sys, "argv", ["build.py", "--version", "1.0.0"])
    build.main()
    assert calls == ["windows_sign", "package"]


def test_main_dry_run_win32_plan(monkeypatch, capsys):
    monkeypatch.setattr(build.sys, "platform", "win32")
    monkeypatch.setattr(build.sys, "argv", ["build.py", "--version", "1.2.3", "--dry-run"])
    build.main()
    assert "signtool" in capsys.readouterr().out
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_packaging.py -q -k "metadata or signtool or ensure_az or win32"`
Expected: FAIL — helpers/`win32` dispatch not yet defined (`AttributeError` / assertion failures).

- [ ] **Step 4: Add the Windows constants and helpers to `build.py`**

After the `ENTITLEMENTS`/`METADATA` constants, add:

```python
TIMESTAMP_URL = "http://timestamp.acs.microsoft.com"
FILE_DIGEST = "SHA256"
SIGNTOOL_FIXED = Path(r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.28000.0\x64\signtool.exe")
SIGNTOOL_KITS_BIN = Path(r"C:\Program Files (x86)\Windows Kits\10\bin")
AZ_WBIN_DIRS = (
    r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin",
    r"C:\Program Files (x86)\Microsoft SDKs\Azure\CLI2\wbin",
)
```

Insert the Windows helpers after `macos_sign` (before `package`):

```python
# --- Windows Authenticode signing (Azure Trusted Signing) ------------------
# One `signtool sign` call on the onefile .exe, using the x64 signtool.exe +
# Azure.CodeSigning.Dlib.dll driven by packaging/metadata.json. Azure auth is
# the machine-side `az` login on the runner — no CI secret.


def check_metadata_not_placeholder(text: str) -> None:
    if "<my-account-name>" in text or "<my-profile-name>" in text:
        raise SystemExit(
            "packaging/metadata.json still has placeholder values — set "
            "CodeSigningAccountName / CertificateProfileName / Endpoint before signing."
        )


def discover_signtool(fixed_path: Path, kits_bin_dir: Path) -> Path:
    if fixed_path.exists():
        return fixed_path
    cands = sorted((p for p in kits_bin_dir.glob("**/x64/signtool.exe")),
                   key=str, reverse=True)
    if cands:
        return cands[0]
    raise SystemExit(
        f"no x64 signtool.exe found under {kits_bin_dir}. "
        "Install the Windows SDK Signing Tools."
    )


def signtool_sign_cmd(signtool: Path, dlib: Path, metadata: Path,
                      timestamp: str, digest: str, files: list) -> list[str]:
    return [str(signtool), "sign", "/v", "/debug", "/fd", digest,
            "/tr", timestamp, "/td", digest, "/dlib", str(dlib),
            "/dmdf", str(metadata), *[str(f) for f in files]]


def ensure_az_on_path(env: dict, candidate_dirs=AZ_WBIN_DIRS, which=shutil.which) -> dict:
    """The dlib's credential shells out to `az`; a runner whose PATH predates the
    az install won't find it. Prepend az's wbin dir for the sign subprocess."""
    if which("az", path=env.get("PATH")):
        return env
    for d in candidate_dirs:
        if (Path(d) / "az.cmd").exists():
            return {**env, "PATH": d + os.pathsep + env.get("PATH", "")}
    return env


def windows_sign(binary: Path, env: dict | None = None) -> None:
    env = dict(os.environ if env is None else env)
    dlib = (Path(env.get("LOCALAPPDATA", "")) / "Microsoft"
            / "MicrosoftArtifactSigningClientTools" / "Azure.CodeSigning.Dlib.dll")
    if not dlib.exists():
        raise SystemExit(f"Azure.CodeSigning.Dlib.dll not found at {dlib}. "
                         "Is ArtifactSigningClientTools installed?")
    if not METADATA.exists():
        raise SystemExit(f"signing metadata missing: {METADATA}")
    check_metadata_not_placeholder(METADATA.read_text(encoding="utf-8"))
    signtool = discover_signtool(SIGNTOOL_FIXED, SIGNTOOL_KITS_BIN)
    env = ensure_az_on_path(env)
    print(f"signtool: {signtool}")
    subprocess.run(signtool_sign_cmd(signtool, dlib, METADATA, TIMESTAMP_URL,
                                     FILE_DIGEST, [binary]), check=True, env=env)
    verify = subprocess.run([str(signtool), "verify", "/pa", "/q", str(binary)])
    if verify.returncode != 0:
        print(f"WARNING: signtool verify returned {verify.returncode} for {binary} "
              "(signed, but verify was non-zero)")
    else:
        print(f"signed + verified: {binary}")
```

- [ ] **Step 5: Add the win32 branches to `_print_sign_plan` and `main()`**

In `_print_sign_plan`, replace the `else` linux branch with a win32 branch plus linux:

```python
    if sys.platform == "darwin":
        print("  sign: codesign --options runtime --entitlements packaging/llama.entitlements")
        print("  notarize: xcrun notarytool submit --wait  (no stapling — online check on first run)")
    elif sys.platform == "win32":
        print("  sign: signtool sign /dlib Azure.CodeSigning.Dlib /dmdf packaging/metadata.json")
    else:
        print("  sign: n/a (linux)")
```

In `main()`, extend the signing dispatch:

```python
    if not args.skip_sign:
        binary = DIST / exe_name()
        if sys.platform == "darwin":
            macos_sign(binary, args.identity, args.notary_profile)
        elif sys.platform == "win32":
            windows_sign(binary)
```

- [ ] **Step 6: Run the packaging tests**

Run: `pytest tests/test_packaging.py -q`
Expected: all PASS.

- [ ] **Step 7: Run the full offline suite**

Run: `pytest -q`
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add packaging/metadata.json packaging/build.py tests/test_packaging.py
git commit -m "feat: Authenticode-sign the Windows release binary in build.py

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KZjRuTv8v58qy5izqvxiFF"
```

---

### Task 3: Workflow comment + release/signing documentation

**Files:**
- Modify: `.github/workflows/release.yml` (header comment only)
- Create: `docs/releasing.md`
- Modify: `README.md` (one note about signed binaries)

**Interfaces:**
- Consumes: the `build.py` signing behavior and `--skip-sign` flag from Tasks 1–2.
- Produces: docs only. No code.

- [ ] **Step 1: Correct the workflow header comment**

In `.github/workflows/release.yml`, replace the top comment block (lines 3–5, currently):

```yaml
# Build llama's four self-contained binaries across the self-hosted fleet and
# attach them to a GitHub Release. Unsigned: no on-box secrets, GITHUB_TOKEN only.
# PyInstaller does not cross-compile, so each artifact is built on native hardware.
```

with:

```yaml
# Build llama's four self-contained binaries across the self-hosted fleet and
# attach them to a GitHub Release. The macOS and Windows binaries are signed by
# packaging/build.py using credentials that live ON the runners (Developer ID
# keychain + notarytool profile on the Mac mini; Azure Trusted Signing on ITCHY)
# and never enter GitHub — GITHUB_TOKEN is the only secret. Linux is unsigned
# (verify via SHA256SUMS). PyInstaller does not cross-compile, so each artifact
# is built on native hardware. See docs/releasing.md for per-box setup.
```

No other workflow change is needed: the matrix already runs
`python packaging/build.py --version "$VER"` on every leg, and `build.py` now
signs on mac/windows by itself.

- [ ] **Step 2: Write `docs/releasing.md`**

Create `docs/releasing.md`:

```markdown
# Releasing signed binaries

`llama` ships four PyInstaller onefile binaries per `v*` tag, built on the
self-hosted fleet by `.github/workflows/release.yml` → `packaging/build.py`.
The **macOS** and **Windows** binaries are code-signed; Linux is not (verify it
via `SHA256SUMS`). No signing secrets live in the repo or GitHub — every
credential is machine-side on the runner that uses it.

## What `build.py` does per platform

- **macOS** (`Shawns-Mac-mini`): codesign the onefile with the hardened runtime
  + `packaging/llama.entitlements`, then notarize a zip of it with
  `xcrun notarytool submit --wait`. The binary is **not stapled** — a bare
  Mach-O can't carry a stapled ticket, so Gatekeeper does an **online**
  notarization check the first time a downloaded copy runs (the machine must be
  online for that first launch). This is the accepted state of the art for a
  bare notarized CLI. The signed binary ships unchanged after submission.
- **Windows** (`ITCHY`): Authenticode-sign the onefile `.exe` with the x64
  `signtool.exe` + `Azure.CodeSigning.Dlib.dll`, driven by
  `packaging/metadata.json`, timestamped via Azure Trusted Signing.
- **Linux**: no signing.

`build.py --skip-sign` produces an unsigned build for local/dev use or a
machine without the toolchain. The release workflow never passes it. Any
signing/notarization failure fails the leg — we never silently ship unsigned.

## One-time machine setup

### Mac mini (macOS runner)

- A **Developer ID Application** certificate in the login keychain (shared with
  the litcat runner on the same box). `build.py` auto-detects the sole such
  identity; override with `LLAMA_CODESIGN_IDENTITY` or `--identity`.
- A **notarytool credential**. Either create a llama profile once:

  ```bash
  xcrun notarytool store-credentials "llama-notary" \
    --apple-id you@example.com --team-id XXXXXXXXXX \
    --password <app-specific-password> \
    --keychain "$HOME/Library/Keychains/login.keychain-db"
  ```

  (Pin `--keychain` to the login keychain — notarytool otherwise stores the
  profile in the data-protection keychain, which a runner session can't read.)
  Or reuse the existing `litcat-notary` profile by setting
  `LLAMA_NOTARY_PROFILE=litcat-notary` in the runner env. Headless alternatives
  (any one, keychain-free) via runner env: `LLAMA_NOTARY_KEY`/`_KEY_ID`/`_ISSUER`
  (App Store Connect API key) or `LLAMA_NOTARY_APPLE_ID`/`_PASSWORD`/`_TEAM_ID`.
- If the runner session can't use the login keychain's private key
  (`errSecInternalComponent`), provide the identity as a `.p12` via
  `LLAMA_SIGNING_P12` (+ `LLAMA_SIGNING_P12_PASSWORD`,
  `LLAMA_SIGNING_KEYCHAIN_PASSWORD`); `build.py` imports it into a throwaway
  keychain it manages itself.

### ITCHY (Windows runner)

- Install **Microsoft.Azure.ArtifactSigningClientTools** (provides
  `Azure.CodeSigning.Dlib.dll` under `%LOCALAPPDATA%`) and the Windows SDK
  Signing Tools (x64 `signtool.exe`).
- `az login` (or a service-principal credential the dlib's credential chain can
  use) so signing reaches your Azure Trusted Signing account with no CI secret.
- Fill `packaging/metadata.json` with your real `Endpoint`,
  `CodeSigningAccountName`, and `CertificateProfileName` (the committed file is a
  placeholder-guarded template; `build.py` refuses to sign until it is edited).

## Verifying a signed build

- macOS (runnable on the Mac mini itself):

  ```bash
  codesign --verify --strict --verbose=2 dist/llama
  spctl --assess --type exec --verbose=2 dist/llama
  xcrun notarytool history --keychain-profile llama-notary \
    --keychain "$HOME/Library/Keychains/login.keychain-db"
  ```

- Windows (on ITCHY, after a build):

  ```powershell
  signtool verify /pa /v dist\llama.exe
  ```
```

- [ ] **Step 3: Add the README note**

In `README.md`, add a short note about the signed binaries. Find the line that
introduces the pip install / setup (`pip install -e ".[dev]"` context near
line 12) is dev-only; instead place the note where releases/binaries are most
discoverable — append this paragraph at the end of the Setup section (before the
`## Use` heading; if there is no such heading, append after the install
instructions):

```markdown
Release binaries (attached to each GitHub Release) are signed: the macOS build
is Developer ID-signed and notarized (Gatekeeper-clean; because it is a bare
executable it can't be stapled, so first run does an online notarization check),
and the Windows build is Authenticode-signed via Azure Trusted Signing. The
Linux builds are unsigned — verify them against `SHA256SUMS`.
```

- [ ] **Step 4: Verify docs render and the suite still passes**

Run: `pytest -q` and confirm `docs/releasing.md` exists with the setup sections.
Expected: suite PASS; doc present.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/release.yml docs/releasing.md README.md
git commit -m "docs: document signed-binary release + per-box signing setup

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KZjRuTv8v58qy5izqvxiFF"
```

---

### Task 4: On-hardware signing verification (manual — not offline-testable)

This task is executed on the fleet hardware, not by the offline suite. It proves
the subprocess-driven `macos_sign` / `windows_sign` bodies work end to end. The
dev host **is** the macOS runner hardware, so the macOS half is runnable during
implementation; the Windows half needs a runner build.

**Files:** none (verification only; capture evidence in the task report).

- [ ] **Step 1: macOS local signed build (on the Mac mini)**

Ensure the login-keychain Developer ID + a `llama-notary` profile (or
`LLAMA_NOTARY_PROFILE=litcat-notary`) are present, then:

```bash
python packaging/build.py --version 0.0.0-verify
```

Expected: PyInstaller builds `dist/llama`; `codesign` succeeds; `codesign
--verify --strict` passes; `notarytool submit --wait` returns
`status: Accepted`; the script prints "signed + notarized … (not stapled …)";
`dist-release/llama-0.0.0-verify-macos-arm64.tar.gz` is produced.

- [ ] **Step 2: macOS Gatekeeper + notarization evidence**

```bash
codesign --verify --strict --verbose=2 dist/llama
spctl --assess --type exec --verbose=2 dist/llama
xcrun notarytool history --keychain-profile llama-notary \
  --keychain "$HOME/Library/Keychains/login.keychain-db" | head
dist/llama --version   # signed binary still runs
```

Expected: codesign verify passes; notarytool history shows the Accepted
submission; the signed binary runs and prints the version. Capture the output as
evidence.

- [ ] **Step 3: `--skip-sign` still produces an unsigned build**

```bash
python packaging/build.py --version 0.0.0-verify --skip-sign
codesign -dv dist/llama 2>&1 | head   # expect: code object is not signed / adhoc
```

Expected: build + package succeed with no notarization step.

- [ ] **Step 4: Windows verification (on ITCHY — needs a runner build)**

Fill `packaging/metadata.json` with real Azure values, ensure `az login` and the
signing tools are installed, then trigger the release workflow with
`workflow_dispatch` (`dry_run: false`) on a throwaway tag, or run locally on
ITCHY:

```bash
python packaging/build.py --version 0.0.0-verify
```

Expected: `signtool sign` reports success; `signtool verify /pa /v dist\llama.exe`
shows the Azure Trusted Signing chain and timestamp; the release attaches
`llama-0.0.0-verify-windows-x86_64.zip`. **Residual risk:** the Windows path
cannot be exercised offline or on the mac dev host; its first real proof is a
runner build. Flag any failure here to the operator.

- [ ] **Step 5: Record evidence**

Summarize the macOS evidence (runnable now) and the Windows status (runner-
gated) in the task report / progress ledger. No commit — this task changes no
files.
```

