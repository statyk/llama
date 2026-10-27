"""campaign_gate's process parser (bulk-apply plan Task 5): rekey_overrides'
`llama_processes`/`_runs_llama`, ported with the tool name a parameter."""
from llama import campaign_gate, station_mark

SELF = "/x/.venv/bin/python scripts/rekey_overrides.py --apply"
MAC_PY = ("/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/"
          "Resources/Python.app/Contents/MacOS/Python")


def test_tool_processes_llama_reruns_the_rekey_cases():
    """The rekey script's own `test_process_check_matches`, re-run with tool="llama"
    (and the script's self-exclusion passed as `self_script`)."""
    match = [
        "601     1 /usr/local/bin/llama run resume --all",
        "602     1 /x/.venv/bin/llama get q",
        "603     1 /usr/bin/python3 -m llama status",
        "604     1 /bin/zsh -c while true; do llama run resume --all; sleep 600; done",
        '605     1 bash -c "llama deliver x"',
        "606     1 /x/.venv/bin/python scripts/replay_holds.py run --all",
        f"607     1 {MAC_PY} /x/.venv/bin/llama get q",
        f"608     1 {MAC_PY} -m llama status",
        "609     1 sh -c FOO=1 llama status",
        "610     1 zsh -c (llama status)",
        "611     1 zsh -c if true; then llama status; else true; fi",
        "612     1 zsh -c true || llama status",
        "613     1 zsh -c echo | llama status",
    ]
    other = [
        "1     0 /sbin/launchd",
        "300     1 /usr/local/bin/llama run resume --all",
        "400   300 zsh -c 'cd /Users/shawn/projects/llama && " + SELF + "'",
        "500   400 " + SELF,
        "701     1 " + SELF,
        "702     1 zsh -c 'cd /Users/shawn/projects/llama && " + SELF + "'",
        f"703     1 {MAC_PY} scripts/rekey_overrides.py --apply",
        "704     1 vim packages/llama/src/llama/junk.py",
        "705     1 -zsh",
        "706     1 python -m pytest",
        f"707     1 {MAC_PY} /x/.venv/bin/pytest -q",
        "708     1 /x/.venv/bin/emcee run",
        "709   500 ps -axo pid=,ppid=,command=",
        "",
        "garbage",
    ]
    got = campaign_gate.tool_processes(other[:4] + match + other[4:], "llama",
                                       self_pid=500, self_script="rekey_overrides.py")
    assert got == match


def test_tool_processes_emcee():
    match = [
        "601     1 emcee run",
        "602     1 /path/.venv/bin/emcee voice x",
        "603     1 python -m emcee status",
        f"604     1 {MAC_PY} /x/.venv/bin/emcee run --yes",
        f"605     1 {MAC_PY} -m emcee voice y",
        "606     1 zsh -c cd /x && emcee run --yes",
    ]
    other = [
        "1     0 /sbin/launchd",
        # The caller and its ancestors never match, even when they run emcee.
        "300     1 /x/.venv/bin/emcee run",
        "400   300 zsh -c 'emcee run'",
        "500   400 /x/.venv/bin/python scripts/bulk_apply.py mark --apply",
        "701     1 grep emcee",
        "702     1 vim emcee.toml",
        "703     1 /x/.venv/bin/llama deliver x",
        # A llama-repo script is not emcee (the check cannot see scripts that
        # import emcee: spec "No concurrent emcee").
        "704     1 /x/.venv/bin/python scripts/backfill_voiced_by.py --apply",
        "705     1 less /x/emcee/README.md",
        "",
    ]
    got = campaign_gate.tool_processes(other[:5] + match + other[5:], "emcee", self_pid=500)
    assert got == match


def test_emcee_running_reads_ps(monkeypatch):
    import os

    me = os.getpid()
    lines = [f"{me}     1 /x/.venv/bin/python -m pytest",
             "9001     1 /x/.venv/bin/emcee run --yes",
             "9002     1 grep emcee"]
    monkeypatch.setattr(campaign_gate, "ps_lines", lambda: lines)
    assert station_mark.emcee_running() == ["9001     1 /x/.venv/bin/emcee run --yes"]
    monkeypatch.setattr(campaign_gate, "ps_lines", lambda: lines[::2])
    assert station_mark.emcee_running() == []


def test_ps_lines_runs_ps(monkeypatch):
    import subprocess

    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="1 0 /sbin/launchd\n2 1 x\n")

    monkeypatch.setattr(campaign_gate.subprocess, "run", fake_run)
    assert campaign_gate.ps_lines() == ["1 0 /sbin/launchd", "2 1 x"]
    assert seen["cmd"] == ["ps", "-axo", "pid=,ppid=,command="]


# --- Task 12: version gate, pin, rekey retirement ---

import json as _json
import subprocess as _subprocess
import types as _types

import pytest

from llama.errors import LlamaError


def _stub_tools(monkeypatch, tools: dict[str, list[tuple[str, str]]]):
    """Stub `which -a <tool>` and `<path> --version` in campaign_gate's subprocess."""
    versions = {p: v for found in tools.values() for p, v in found}

    def run(cmd, **kw):
        if cmd[:2] == ["which", "-a"]:
            paths = [p for p, _ in tools.get(cmd[2], [])]
            return _types.SimpleNamespace(returncode=0 if paths else 1,
                                          stdout="".join(p + "\n" for p in paths), stderr="")
        assert cmd[1] == "--version"
        return _types.SimpleNamespace(returncode=0, stdout=versions[cmd[0]] + "\n", stderr="")

    monkeypatch.setattr(campaign_gate.subprocess, "run", run)


def test_version_gate(monkeypatch):
    echoed = []
    ok = {"llama": [("/a/llama", "2.20.0")], "emcee": [("/a/emcee", "2.20.0")]}
    _stub_tools(monkeypatch, ok)
    campaign_gate.require_tools(echoed.append, pin=None)
    assert campaign_gate.version_ok("2.20.0", campaign_gate.CAMPAIGN_MIN_VERSION)
    assert campaign_gate.version_ok("2.21.0\n", "2.20.0")
    assert not campaign_gate.version_ok("2.9.0", "2.20.0")
    assert campaign_gate.version_newer("2.21.0", "2.20.0")
    assert not campaign_gate.version_newer("2.20.0", "2.20.0")
    assert not campaign_gate.version_newer("2.20.0rc1", "2.19.0")
    for bad in ("2.19.0", "0.1.0", "2.20.0rc1"):
        for tool in ("llama", "emcee"):
            tools = {"llama": [("/a/llama", "2.20.0")], "emcee": [("/a/emcee", "2.20.0")]}
            tools[tool] = [(f"/b/{tool}", bad)]
            _stub_tools(monkeypatch, tools)
            with pytest.raises(campaign_gate.GateRefused, match=f"/b/{tool}"):
                campaign_gate.require_tools(lambda _m: None, pin=None)
    # a tool not on PATH at all
    _stub_tools(monkeypatch, {"llama": [("/a/llama", "2.20.0")]})
    with pytest.raises(campaign_gate.GateRefused, match="emcee"):
        campaign_gate.require_tools(lambda _m: None, pin=None)
    # a pin of 2.20.0 with an installed 2.21.0 llama is refused, naming the path
    _stub_tools(monkeypatch, {"llama": [("/c/llama", "2.21.0")], "emcee": [("/a/emcee", "2.20.0")]})
    with pytest.raises(campaign_gate.GateRefused, match="/c/llama"):
        campaign_gate.require_tools(lambda _m: None, pin={"version": "2.20.0"})
    campaign_gate.require_tools(lambda _m: None, pin=None)       # no pin: newer is fine
    assert issubclass(campaign_gate.GateRefused, LlamaError)


def test_pin_roundtrip_and_replace(tmp_path):
    assert campaign_gate.read_pin(tmp_path) is None
    p = campaign_gate.write_pin(tmp_path, tag="v2.20.0", sha="abc", version="2.20.0",
                                worktree="/w", replace=False)
    assert campaign_gate.read_pin(tmp_path) == p
    assert set(p) == {"tag", "sha", "version", "worktree", "pinned_at"}
    assert (tmp_path / "campaign" / "pin.json").exists()
    with pytest.raises(campaign_gate.GateRefused):
        campaign_gate.write_pin(tmp_path, tag="v2.20.1", sha="def", version="2.20.1",
                                worktree="/w", replace=False)
    assert campaign_gate.read_pin(tmp_path)["tag"] == "v2.20.0"
    campaign_gate.write_pin(tmp_path, tag="v2.20.1", sha="def", version="2.20.1",
                            worktree="/w", replace=True)
    assert campaign_gate.read_pin(tmp_path)["tag"] == "v2.20.1"


def test_require_pinned_code(tmp_path, monkeypatch):
    with pytest.raises(campaign_gate.GateRefused, match="pin"):
        campaign_gate.require_pinned_code(tmp_path)
    campaign_gate.write_pin(tmp_path, tag="v2.20.0", sha="abc123", version="2.20.0",
                            worktree="/w", replace=False)
    monkeypatch.setattr("llama.replay.code_identity", lambda: "abc123")
    assert campaign_gate.require_pinned_code(tmp_path)["sha"] == "abc123"
    for ident in ("abc123-dirty", "def456", "version:2.20.0"):
        monkeypatch.setattr("llama.replay.code_identity", lambda i=ident: i)
        with pytest.raises(campaign_gate.GateRefused):
            campaign_gate.require_pinned_code(tmp_path)


def test_retire_is_idempotent(tmp_path):
    assert campaign_gate.retire_rekey_restore(tmp_path, by="x", at="t") is False
    assert not (tmp_path / "rekey-applied.json").exists()
    (tmp_path / "rekey-applied.json").write_text(
        _json.dumps({"snapshot": "s", "shows": []}, indent=2))
    assert campaign_gate.retire_rekey_restore(tmp_path, by="backfill", at="T1") is True
    rec = _json.loads((tmp_path / "rekey-applied.json").read_text())
    assert rec["retired"] == {"at": "T1", "by": "backfill"} and rec["snapshot"] == "s"
    before = (tmp_path / "rekey-applied.json").read_bytes()
    assert campaign_gate.retire_rekey_restore(tmp_path, by="mark", at="T2") is False
    assert (tmp_path / "rekey-applied.json").read_bytes() == before
