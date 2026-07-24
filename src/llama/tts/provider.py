from typing import Protocol, runtime_checkable

from llama.errors import LlamaError


class SpeechError(LlamaError):
    """A speech backend failed or is unusably configured (missing key/voice)."""


@runtime_checkable
class SpeechProvider(Protocol):
    def synthesize(self, text: str, fmt: str = "mp3") -> bytes: ...
    # fmt="mp3" (default): encoded MP3 audio bytes.
    # fmt="wav": PCM audio in a WAV container, used by the chunked-synthesis
    # path (package.py _synthesize_chunked) so callers can read raw PCM with
    # the stdlib `wave` module and concatenate sentences before a single MP3
    # encode.
