from typing import Protocol, runtime_checkable

from emcee.errors import EmceeError


class SpeechError(EmceeError):
    """A speech backend failed or is unusably configured (missing key/voice)."""


class SpeechBlocked(SpeechError):
    """The speech backend's content filter refused this text.

    `text` is exactly what was sent and refused; `categories` the violated
    category names (empty when the response doesn't say). `segment` (the DJ
    clip stem, e.g. "set2-intro") is filled in by the audio layer after the
    fact, so the message is computed in `__str__` rather than frozen here.
    `whole_passage` marks a passage whose every sentence passes on its own:
    the trigger only exists in context, and chunked synthesis avoids it.
    The full blocked text is always the first `details` line, which both CLI
    error boundaries print.
    """

    def __init__(self, backend: str, *, text: str, categories: list[str],
                 whole_passage: bool = False):
        super().__init__(f"{backend} content filter blocked", details=[f'blocked: "{text}"'])
        self.backend = backend
        self.text = text
        self.categories = list(categories)
        self.whole_passage = whole_passage
        self.segment: str | None = None

    def __str__(self) -> str:
        what = "a passage" if self.whole_passage else "a sentence"
        where = f" in {self.segment}" if self.segment else ""
        cats = f" ({', '.join(self.categories)})" if self.categories else ""
        msg = f"{self.backend} content filter blocked {what}{where}{cats}"
        if self.whole_passage:
            msg += ("; every sentence passes the content filter on its own, so "
                    "re-run with chunking on ([tts] chunk = true; for emcee say, "
                    "without --no-chunk)")
        return msg


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
