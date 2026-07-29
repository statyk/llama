from typing import Protocol, runtime_checkable


class HerderError(Exception):
    """Base for every failure herder raises.

    herder has no error taxonomy of its own beyond this; a consuming app
    is expected to catch it at its own error boundary, alongside whatever
    exceptions that app defines.
    """


class ResearchNotSupported(HerderError):
    pass


class TaskFailed(HerderError):
    def __init__(self, message: str, raw_output: str = ""):
        super().__init__(message)
        self.raw_output = raw_output


@runtime_checkable
class LLMProvider(Protocol):
    def complete(self, prompt: str) -> str: ...

    def research(self, brief: str) -> str: ...
