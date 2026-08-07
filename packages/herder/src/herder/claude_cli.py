import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile

from herder.provider import HerderError

# complete() must be pure text->text; research() may search the web and nothing else.
# --allowedTools only auto-approves; it does not shrink the toolset, so delegation
# and background tools (subagents, skills, workflows) must be disallowed explicitly:
# they end the headless turn with narration while the work runs elsewhere, and the
# caller would capture that narration as the output.
_DELEGATION = "Task,Agent,Skill,Workflow,SlashCommand,TodoWrite"
COMPLETE_DISALLOWED = "Bash,Edit,Write,Read,Glob,Grep,WebSearch,WebFetch," + _DELEGATION
RESEARCH_ALLOWED = "WebSearch,WebFetch"
RESEARCH_DISALLOWED = "Bash,Edit,Write,Read,Glob,Grep," + _DELEGATION

# A headless call wants a pure text->text turn, but the CLI otherwise loads the
# operator's whole interactive setup. Two pieces of that are worth refusing:
# SessionStart hooks (which inject skill instructions telling the model to go
# invoke skills llama disallows) and MCP servers (whose tool schemas
# --allowedTools does not shrink away - it only auto-approves).
# Measured 2026-08-06 against CLI 2.1.223: ~1,355 tokens per call of a
# ~7,449-token uncached prefix.
# --bare removes more - it also skips CLAUDE.md - but is unusable here: it
# reads auth strictly from ANTHROPIC_API_KEY/apiKeyHelper and never OAuth or
# the keychain, so a subscription login fails outright. Pointing
# CLAUDE_CONFIG_DIR at an empty dir fails the same way (credentials live
# there). CLAUDE.md therefore still loads; these flags are the auth-safe
# subset, verified live against an OAuth login on both complete() and
# research() (--strict-mcp-config leaves the built-in web tools alone).
ISOLATION_ARGS = ["--strict-mcp-config", "--settings", '{"disableAllHooks":true}']


def _subprocess_env() -> dict | None:
    """Environment for the claude subprocess.

    The frozen (PyInstaller) binary points LD_LIBRARY_PATH at its own bundled
    libraries; a dynamically-linked child loading those can crash on startup.
    Restore the loader path the bootloader saved. None = inherit unchanged.
    """
    if not getattr(sys, "frozen", False):
        return None
    env = os.environ.copy()
    for var in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
        orig = env.pop(f"{var}_ORIG", None)
        if orig is not None:
            env[var] = orig
        else:
            env.pop(var, None)
    return env


_neutral_dir: str | None = None


def _neutral_cwd() -> str:
    """An empty directory with no CLAUDE.md anywhere above it.

    claude discovers CLAUDE.md by walking up from its cwd, so a subprocess
    inheriting the caller's cwd silently pulls the *project's* CLAUDE.md into
    every prompt - for llama that is a repo architecture document, injected
    into every briefing. Measured 2026-08-06 on CLI 2.1.223: 19,908 uncached
    prefix tokens per call from the repo vs 6,094 from a neutral dir.
    The user-level ~/.claude/CLAUDE.md still loads; only --bare skips that,
    and --bare cannot authenticate an OAuth login (see ISOLATION_ARGS).
    Created once per process and reused, so the prefix stays cache-stable.
    """
    global _neutral_dir
    if _neutral_dir is None:
        _neutral_dir = tempfile.mkdtemp(prefix="herder-cwd-")
        atexit.register(shutil.rmtree, _neutral_dir, ignore_errors=True)
    return _neutral_dir


def _message_or(data: dict, fallback: str) -> str:
    """The human-readable message out of a claude JSON envelope, else fallback."""
    msg = data.get("result")
    return msg.strip() if isinstance(msg, str) and msg.strip() else fallback


def _error_detail(proc) -> str:
    """The most informative 500 chars available about a failed run.

    A failure envelope leads with is_error, timings and a zeroed usage block
    and carries the actual message in `result`, well past 500 chars - so
    truncating the raw JSON from the front reliably prints everything except
    the diagnosis. The observed dropped-connection failure surfaced as a wall
    of zeroes with the cause ("API Error: Connection closed mid-response")
    nowhere in the message.
    """
    stdout, stderr = (proc.stdout or "").strip(), (proc.stderr or "").strip()
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        message = _message_or(data, "")
        if message:
            return message[:500]
    # claude also reports plain-text failures (auth, bad flags) on stdout
    return (stderr or stdout)[:500]


class ClaudeCLIProvider:
    def __init__(self, model: str | None = None, binary: str = "claude", timeout_s: int = 900):
        self.model = model
        self.binary = binary
        self.timeout_s = timeout_s

    def _run(self, prompt: str, extra_args: list[str]) -> str:
        cmd = [self.binary, "-p", "--output-format", "json", *ISOLATION_ARGS, *extra_args]
        if self.model:
            cmd += ["--model", self.model]
        try:
            proc = subprocess.run(
                cmd, input=prompt, capture_output=True, text=True, timeout=self.timeout_s,
                env=_subprocess_env(), cwd=_neutral_cwd(),
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            raise HerderError(f"claude invocation failed: {e}") from e
        if proc.returncode != 0:
            raise HerderError(f"claude exited {proc.returncode}: {_error_detail(proc)}")
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise HerderError(f"claude output was not JSON: {proc.stdout[:200]}") from e
        if data.get("is_error"):
            raise HerderError(f"claude reported an error: {_message_or(data, str(data))[:500]}")
        result = data.get("result")
        if not isinstance(result, str):
            raise HerderError("claude output has no string 'result' field")
        return result

    def complete(self, prompt: str) -> str:
        return self._run(prompt, ["--disallowedTools", COMPLETE_DISALLOWED])

    def research(self, brief: str) -> str:
        return self._run(brief, ["--allowedTools", RESEARCH_ALLOWED,
                                 "--disallowedTools", RESEARCH_DISALLOWED])
