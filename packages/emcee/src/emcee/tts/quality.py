"""The quality layer: sole owner of the quality retry (spec section 3).

Wraps every mlx_audio provider (the runaway guard, inside the provider,
raises SpeechDefect and never retries) and -- from transcript verification
on -- every provider whose backend is listed in [tts.verify] backends. Per
`synthesize` call: at most two attempts; a second quality failure raises
SpeechDefect, which fails the package rather than airing the clip. The
retried unit is whatever the caller synthesizes: the sentence when chunked,
the whole segment otherwise.

Keeps the inner `.voice`/`.model`, so cached clips are reused (never
re-verified) and enabling verification does not invalidate the cache.
SpeechBlocked and every other SpeechError pass straight through.
"""
from collections.abc import Callable

import typer

from emcee.tts.provider import SpeechDefect


class QualitySpeech:
    def __init__(self, inner, *, backend: str, verifier=None):
        self.inner = inner
        self.backend = backend
        self.verifier = verifier
        self.voice = inner.voice
        self.model = inner.model

    def synthesize(self, text: str, fmt: str = "mp3", *,
                   previous_text: str | None = None,
                   next_text: str | None = None) -> bytes:
        return self._retrying(text, lambda: self._attempt(text, fmt, previous_text, next_text))

    def _retrying(self, text: str, attempt: Callable[[], bytes]) -> bytes:
        """At most two attempts of `attempt` for `text`: a second quality
        failure raises SpeechDefect."""
        try:
            return attempt()
        except SpeechDefect as first:
            typer.echo(f"{self.backend} quality check failed ({first.reason}); "
                       "re-synthesizing once")
        try:
            return attempt()
        except SpeechDefect as second:
            raise SpeechDefect(second.backend, text=text,
                               reason=f"{second.reason} (failed twice)",
                               transcript=second.transcript) from second

    def _attempt(self, text: str, fmt: str, previous_text: str | None,
                 next_text: str | None) -> bytes:
        return self.inner.synthesize(text, fmt, previous_text=previous_text,
                                     next_text=next_text)

    def preflight(self) -> None:
        self.inner.preflight()

    def close(self) -> None:
        self.inner.close()
