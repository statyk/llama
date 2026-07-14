import json
import subprocess

import pytest

from llama.config import Config, LLMTaskConfig
from llama.llm import provider_for
from llama.llm.claude_cli import ClaudeCLIProvider
from llama.llm.provider import LLMError


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
    assert "--disallowedTools" in cmd
    assert seen["input"] == "say hello"


def test_research_allows_web_tools(monkeypatch):
    seen = {}
    patch_run(monkeypatch, FakeProc(stdout=json.dumps({"result": "found"})), seen)
    assert ClaudeCLIProvider().research("dig") == "found"
    i = seen["cmd"].index("--allowedTools")
    assert "WebSearch" in seen["cmd"][i + 1]


def test_nonzero_exit_raises(monkeypatch):
    patch_run(monkeypatch, FakeProc(returncode=1, stderr="boom"), {})
    with pytest.raises(LLMError, match="boom"):
        ClaudeCLIProvider().complete("x")


def test_bad_json_and_error_payload_raise(monkeypatch):
    patch_run(monkeypatch, FakeProc(stdout="not json"), {})
    with pytest.raises(LLMError):
        ClaudeCLIProvider().complete("x")
    patch_run(monkeypatch, FakeProc(stdout=json.dumps({"is_error": True, "result": "quota"})), {})
    with pytest.raises(LLMError):
        ClaudeCLIProvider().complete("x")


def test_provider_for_uses_task_config(monkeypatch):
    cfg = Config(llm={"default": LLMTaskConfig(model="m-default"),
                      "synthesize": LLMTaskConfig(model="m-big")})
    assert provider_for(cfg, "synthesize").model == "m-big"
    assert provider_for(cfg, "interpret").model == "m-default"
    with pytest.raises(LLMError):
        provider_for(Config(llm={"default": LLMTaskConfig(backend="nope")}), "interpret")
