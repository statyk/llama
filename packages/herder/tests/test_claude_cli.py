import json
import subprocess

import pytest

from herder import HerderError
from herder.claude_cli import ClaudeCLIProvider


class FakeProc:
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr


def patch_run(monkeypatch, proc: FakeProc, seen: dict):
    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["input"] = kwargs.get("input")
        return proc

    monkeypatch.setattr(subprocess, "run", fake_run)


def test_complete_locks_down_tools_and_parses_result(monkeypatch):
    seen = {}
    patch_run(monkeypatch, FakeProc(stdout=json.dumps({"result": "hello"})), seen)
    p = ClaudeCLIProvider(model="claude-sonnet-5")
    assert p.complete("say hello") == "hello"
    cmd = seen["cmd"]
    assert cmd[:2] == ["claude", "-p"]
    assert "--output-format" in cmd and "json" in cmd
    assert "--model" in cmd and "claude-sonnet-5" in cmd
    disallowed = cmd[cmd.index("--disallowedTools") + 1]
    for tool in ("Bash", "Task", "Agent", "Skill", "Workflow"):
        assert tool in disallowed
    assert seen["input"] == "say hello"


def test_research_allows_web_tools_but_no_delegation(monkeypatch):
    seen = {}
    patch_run(monkeypatch, FakeProc(stdout=json.dumps({"result": "found"})), seen)
    assert ClaudeCLIProvider().research("dig") == "found"
    cmd = seen["cmd"]
    allowed = cmd[cmd.index("--allowedTools") + 1]
    assert "WebSearch" in allowed and "WebFetch" in allowed
    # Background/delegation tools end the headless turn with narration while
    # the work runs elsewhere; the caller would capture narration as output.
    disallowed = cmd[cmd.index("--disallowedTools") + 1]
    for tool in ("Task", "Agent", "Skill", "Workflow", "Bash"):
        assert tool in disallowed
    assert "Web" not in disallowed


def test_nonzero_exit_raises(monkeypatch):
    patch_run(monkeypatch, FakeProc(returncode=1, stderr="boom"), {})
    with pytest.raises(HerderError, match="boom"):
        ClaudeCLIProvider().complete("x")


def test_nonzero_exit_falls_back_to_stdout_detail(monkeypatch):
    # claude reports auth/usage failures on stdout with an empty stderr;
    # the error must carry that detail instead of a bare exit code
    patch_run(monkeypatch, FakeProc(returncode=1, stdout="Invalid API key - run /login\n"), {})
    with pytest.raises(HerderError, match="Invalid API key"):
        ClaudeCLIProvider().complete("x")


def test_frozen_binary_restores_loader_path_for_subprocess(monkeypatch):
    import sys
    from herder import claude_cli

    seen = {}

    def fake_run(cmd, **kwargs):
        seen["env"] = kwargs.get("env")
        return FakeProc(stdout=json.dumps({"result": "ok"}))

    monkeypatch.setattr(subprocess, "run", fake_run)

    # unfrozen: inherit the environment untouched
    ClaudeCLIProvider().complete("x")
    assert seen["env"] is None

    # frozen: PyInstaller's bundled-library loader path must not leak to claude
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEIxyz/lib")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/lib/real")
    monkeypatch.setenv("DYLD_LIBRARY_PATH", "/tmp/_MEIxyz/lib")  # no _ORIG saved
    ClaudeCLIProvider().complete("x")
    assert seen["env"]["LD_LIBRARY_PATH"] == "/usr/lib/real"
    assert "LD_LIBRARY_PATH_ORIG" not in seen["env"]
    assert "DYLD_LIBRARY_PATH" not in seen["env"]


def test_bad_json_and_error_payload_raise(monkeypatch):
    patch_run(monkeypatch, FakeProc(stdout="not json"), {})
    with pytest.raises(HerderError):
        ClaudeCLIProvider().complete("x")
    patch_run(monkeypatch, FakeProc(stdout=json.dumps({"is_error": True, "result": "quota"})), {})
    with pytest.raises(HerderError):
        ClaudeCLIProvider().complete("x")


# --- subprocess isolation -------------------------------------------------
# A headless llama call wants a pure text->text turn. Left to itself the CLI
# loads the operator's interactive setup: SessionStart hooks inject skill
# instructions telling the model to go invoke skills (which llama disallows),
# and MCP servers add tool schemas that --allowedTools does not shrink away.
# Measured on 2026-08-06 against 2.1.223: ~1,355 tokens of the ~7,449-token
# uncached prefix, per call, on top of the behavioural risk.
# --bare would remove more (it also skips CLAUDE.md) but is NOT usable: it
# reads auth strictly from ANTHROPIC_API_KEY/apiKeyHelper, so an OAuth login
# fails outright. Same for isolating CLAUDE_CONFIG_DIR - the credentials live
# there. These two flags are the auth-safe subset.


def test_isolation_flags_are_passed(monkeypatch):
    seen = {}
    patch_run(monkeypatch, FakeProc(stdout=json.dumps({"result": "ok"})), seen)
    ClaudeCLIProvider().complete("x")
    cmd = seen["cmd"]
    assert "--strict-mcp-config" in cmd
    assert json.loads(cmd[cmd.index("--settings") + 1]) == {"disableAllHooks": True}


def test_isolation_flags_apply_to_research_too(monkeypatch):
    seen = {}
    patch_run(monkeypatch, FakeProc(stdout=json.dumps({"result": "ok"})), seen)
    ClaudeCLIProvider().research("x")
    assert "--strict-mcp-config" in seen["cmd"] and "--settings" in seen["cmd"]


# --- error detail ---------------------------------------------------------
# The failure envelope leads with is_error/timings/zeroed usage and carries the
# human-readable message in `result`, past any truncation. The observed
# dropped-connection failure printed 500 chars of that noise and nothing else.

CLOSED_MID = {
    "is_error": True, "duration_api_ms": 214710, "num_turns": 1,
    "stop_reason": "stop_sequence", "session_id": "cfaa832f", "total_cost_usd": 0.2099,
    "usage": {"input_tokens": 0, "cache_creation_input_tokens": 0, "output_tokens": 0,
              "server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 0},
              "service_tier": "standard", "inference_geo": "", "iterations": [],
              "speed": "standard"},
    "result": "API Error: Connection closed mid-response. The response above may be incomplete.",
}


def test_nonzero_exit_surfaces_the_message_not_the_envelope(monkeypatch):
    patch_run(monkeypatch, FakeProc(returncode=1, stdout=json.dumps(CLOSED_MID)), {})
    with pytest.raises(HerderError) as exc:
        ClaudeCLIProvider().complete("x")
    assert "Connection closed mid-response" in str(exc.value)
    assert "duration_api_ms" not in str(exc.value)


def test_is_error_payload_surfaces_the_message_not_the_envelope(monkeypatch):
    patch_run(monkeypatch, FakeProc(returncode=0, stdout=json.dumps(CLOSED_MID)), {})
    with pytest.raises(HerderError) as exc:
        ClaudeCLIProvider().complete("x")
    assert "Connection closed mid-response" in str(exc.value)
    assert "cache_creation_input_tokens" not in str(exc.value)


def test_error_detail_falls_back_to_raw_when_no_message(monkeypatch):
    # no `result` to surface: keep the old behaviour rather than losing the clue
    patch_run(monkeypatch, FakeProc(returncode=1, stdout=json.dumps({"is_error": True})), {})
    with pytest.raises(HerderError, match="is_error"):
        ClaudeCLIProvider().complete("x")


# --- neutral working directory -------------------------------------------
# claude discovers CLAUDE.md by walking up from its cwd, so a subprocess
# inheriting llama's cwd pulls the *project's* CLAUDE.md into every prompt.
# Measured 2026-08-06 on 2.1.223: running from the llama repo cost 19,908
# uncached prefix tokens per call vs 6,094 from a neutral dir - ~13.8k of
# repo architecture notes injected into every briefing. Running the provider
# somewhere with no CLAUDE.md above it is the entire fix.


def test_runs_in_a_neutral_directory(monkeypatch, tmp_path):
    import os
    from pathlib import Path

    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cwd"] = kwargs.get("cwd")
        return FakeProc(stdout=json.dumps({"result": "ok"}))

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "CLAUDE.md").write_text("project notes that must not leak")

    ClaudeCLIProvider().complete("x")
    cwd = seen["cwd"]
    assert cwd is not None, "must not inherit the caller's cwd"
    assert Path(cwd).is_dir()
    assert Path(cwd).resolve() != tmp_path.resolve()
    # nothing named CLAUDE.md anywhere from there up to the root
    for d in [Path(cwd).resolve(), *Path(cwd).resolve().parents]:
        assert not (d / "CLAUDE.md").exists(), f"CLAUDE.md discoverable at {d}"
    assert os.access(cwd, os.R_OK)


def test_neutral_directory_is_reused_across_calls(monkeypatch):
    seen = []
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **kw: (seen.append(kw.get("cwd")),
                                           FakeProc(stdout=json.dumps({"result": "ok"})))[1])
    p = ClaudeCLIProvider()
    p.complete("a")
    p.research("b")
    assert seen[0] == seen[1] and seen[0] is not None
