from typing import Protocol, runtime_checkable

from llama.errors import LlamaError


class SpeechError(LlamaError):
    """A speech backend failed or is unusably configured (missing key/voice)."""


@runtime_checkable
class SpeechProvider(Protocol):
    def synthesize(self, text: str) -> bytes: ...  # encoded MP3 audio bytes
