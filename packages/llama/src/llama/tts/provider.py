from typing import Protocol, runtime_checkable

from llama.errors import LlamaError


class SpeechError(LlamaError):
    """A speech backend failed or is unusably configured (missing key/voice)."""


@runtime_checkable
class SpeechProvider(Protocol):
    def synthesize(self, text: str, fmt: str = "mp3", *,
                   previous_text: str | None = None,
                   next_text: str | None = None) -> bytes: ...
    # fmt="mp3" (default): encoded MP3 audio bytes.
    # fmt="wav": PCM audio in a WAV container, used by the chunked-synthesis
    # path (package.py _synthesize_chunked) so callers can read raw PCM with
    # the stdlib `wave` module and concatenate sentences before a single MP3
    # encode.
    #
    # previous_text/next_text: the surrounding chunks' text when synthesizing
    # one chunk of a longer passage (chunked mode). Backends that support it
    # (ElevenLabs) condition on them for prosodic continuity across chunk
    # boundaries; backends that don't (Voxtral's endpoint has no such field)
    # ignore them. Both are None on the whole-segment path.
