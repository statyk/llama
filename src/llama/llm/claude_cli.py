import json
import os
import subprocess
import sys

from llama.llm.provider import LLMError

# complete() must be pure text->text; research() may search the web and nothing else.
# --allowedTools only auto-approves; it does not shrink the toolset, so delegation
# and background tools (subagents, skills, workflows) must be disallowed explicitly:
# they end the headless turn with narration while the work runs elsewhere, and the
# caller would capture that narration as the output.
_DELEGATION = "Task,Agent,Skill,Workflow,SlashCommand,TodoWrite"
COMPLETE_DISALLOWED = "Bash,Edit,Write,Read,Glob,Grep,WebSearch,WebFetch," + _DELEGATION
RESEARCH_ALLOWED = "WebSearch,WebFetch"
RESEARCH_DISALLOWED = "Bash,Edit,Write,Read,Glob,Grep," + _DELEGATION


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


class ClaudeCLIProvider:
    def __init__(self, model: str | None = None, binary: str = "claude", timeout_s: int = 900):
        self.model = model
        self.binary = binary
        self.timeout_s = timeout_s

    def _run(self, prompt: str, extra_args: list[str]) -> str:
        cmd = [self.binary, "-p", "--output-format", "json", *extra_args]
        if self.model:
            cmd += ["--model", self.model]
        try:
            proc = subprocess.run(
                cmd, input=prompt, capture_output=True, text=True, timeout=self.timeout_s,
                env=_subprocess_env(),
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            raise LLMError(f"claude invocation failed: {e}") from e
        if proc.returncode != 0:
            # claude often reports failures (auth, bad flags) on stdout
            detail = (proc.stderr.strip() or proc.stdout.strip())[:500]
            raise LLMError(f"claude exited {proc.returncode}: {detail}")
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise LLMError(f"claude output was not JSON: {proc.stdout[:200]}") from e
        if data.get("is_error"):
            raise LLMError(f"claude reported an error: {str(data)[:500]}")
        result = data.get("result")
        if not isinstance(result, str):
            raise LLMError("claude output has no string 'result' field")
        return result

    def complete(self, prompt: str) -> str:
        return self._run(prompt, ["--disallowedTools", COMPLETE_DISALLOWED])

    def research(self, brief: str) -> str:
        return self._run(brief, ["--allowedTools", RESEARCH_ALLOWED,
                                 "--disallowedTools", RESEARCH_DISALLOWED])
