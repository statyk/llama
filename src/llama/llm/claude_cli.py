import json
import subprocess

from llama.llm.provider import LLMError

# complete() must be pure text->text; research() may search the web and nothing else.
COMPLETE_DISALLOWED = "Bash,Edit,Write,Read,Glob,Grep,WebSearch,WebFetch"
RESEARCH_ALLOWED = "WebSearch,WebFetch"


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
                cmd, input=prompt, capture_output=True, text=True, timeout=self.timeout_s
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            raise LLMError(f"claude invocation failed: {e}") from e
        if proc.returncode != 0:
            raise LLMError(f"claude exited {proc.returncode}: {proc.stderr[:500]}")
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
        return self._run(brief, ["--allowedTools", RESEARCH_ALLOWED])
