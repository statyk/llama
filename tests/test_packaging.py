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
    args, kind = build.resolve_notary_auth(env, "litcat-notary", None, None)
    assert args == ["--key", "/k.p8", "--key-id", "KID", "--issuer", "ISS"]
    assert "API key" in kind


def test_notary_apple_id_team_from_env():
    env = {"LLAMA_NOTARY_APPLE_ID": "me@x.com", "LLAMA_NOTARY_PASSWORD": "pw", "LLAMA_NOTARY_TEAM_ID": "T9"}
    args, _ = build.resolve_notary_auth(env, "litcat-notary", None, None)
    assert args == ["--apple-id", "me@x.com", "--password", "pw", "--team-id", "T9"]


def test_notary_apple_id_team_parsed_from_identity():
    env = {"LLAMA_NOTARY_APPLE_ID": "me@x.com", "LLAMA_NOTARY_PASSWORD": "pw"}
    args, _ = build.resolve_notary_auth(env, "litcat-notary", None, "Developer ID Application: X (TEAM42)")
    assert args[-2:] == ["--team-id", "TEAM42"]


def test_notary_apple_id_without_team_raises():
    env = {"LLAMA_NOTARY_APPLE_ID": "a", "LLAMA_NOTARY_PASSWORD": "b"}
    with pytest.raises(SystemExit):
        build.resolve_notary_auth(env, "p", None, None)


def test_notary_profile_with_keychain():
    args, kind = build.resolve_notary_auth({}, "litcat-notary", "/kc.db", None)
    assert args == ["--keychain-profile", "litcat-notary", "--keychain", "/kc.db"]
    assert "litcat-notary" in kind


def test_notary_profile_without_keychain():
    args, _ = build.resolve_notary_auth({}, "litcat-notary", None, None)
    assert args == ["--keychain-profile", "litcat-notary"]


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
