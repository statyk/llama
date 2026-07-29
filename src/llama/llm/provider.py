from typing import Protocol, runtime_checkable


class LLMError(Exception):
    """Base for LLM-layer failures.

    Deliberately independent of llama.errors: this module is bound for
    extraction into the shared `herder` package and must not import llama.
    The CLI boundary catches this alongside LlamaError.
    """


class ResearchNotSupported(LLMError):
    pass


class TaskFailed(LLMError):
    def __init__(self, message: str, raw_output: str = ""):
        super().__init__(message)
        self.raw_output = raw_output


@runtime_checkable
class LLMProvider(Protocol):
    def complete(self, prompt: str) -> str: ...

    def research(self, brief: str) -> str: ...
