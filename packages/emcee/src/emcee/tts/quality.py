"""The quality layer: sole owner of the quality retry (spec section 3).

Wraps every mlx_audio provider (the runaway guard, inside the provider,
raises SpeechDefect and never retries) and every provider whose backend is
listed in [tts.verify] backends, which also gets a transcript Verifier
(tts/verify.py): a verified attempt asks its inner provider for WAV,
transcribes it and fails on a gross mismatch. Per `synthesize` call: at
most two attempts; a second quality failure raises SpeechDefect, which fails
the package rather than airing the clip. The retried unit is whatever the
caller synthesizes: the chunk when chunked, the whole segment otherwise.

Keeps the inner `.voice`/`.model`, so cached clips are reused (never
re-verified) and enabling verification does not invalidate the cache.
SpeechBlocked and every other SpeechError pass straight through.
"""
from collections.abc import Callable

import typer

from emcee.tts import verify as verify_mod
from emcee.tts.mlx_audio import PREFLIGHT_TEXT, wav_to_mp3
from emcee.tts.provider import SpeechDefect, SpeechError


_NOTICE_CHARS = 80


def _quoted(text: str) -> str:
    """`text` for the retry notice: whole up to `_NOTICE_CHARS`, else cut
    short with "..." so a long segment stays one readable line."""
    text = " ".join(text.split())
    if len(text) <= _NOTICE_CHARS:
        return text
    return text[:_NOTICE_CHARS - 3] + "..."


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
            typer.echo(f"{self.backend} quality check failed on \"{_quoted(text)}\" "
                       f"({first.reason}); re-synthesizing once")
        try:
            return attempt()
        except SpeechDefect as second:
            raise SpeechDefect(second.backend, text=text,
                               reason=f"{second.reason} (failed twice)",
                               transcript=second.transcript) from second

    def _attempt(self, text: str, fmt: str, previous_text: str | None,
                 next_text: str | None) -> bytes:
        if self.verifier is None:
            return self.inner.synthesize(text, fmt, previous_text=previous_text,
                                         next_text=next_text)
        # Always WAV from the inner provider: verification transcribes it, and
        # an MP3 caller gets a local encode (so a hosted backend's unchunked
        # output changes only when that backend is listed).
        wav = self.inner.synthesize(text, "wav", previous_text=previous_text,
                                    next_text=next_text)
        self.verifier.check(wav, text, backend=self.backend)
        return wav if fmt == "wav" else wav_to_mp3(wav)

    def preflight(self) -> None:
        """Verification is never silently skipped: when it applies, the STT
        path is checked end to end here, before any LLM spend and before the
        manifest clear. mlx: ONE take of the preflight sentence (max_tokens
        200, the format/rate checks) is transcribed for the full comparison,
        with the single retry (synthesis is non-deterministic) -- so the
        inner preflight, which would synthesize a second take, is skipped.
        Hosted: the bundled clip must transcribe to a pass -- no hosted spend."""
        if self.verifier is None:
            self.inner.preflight()
            return
        if self.backend == "mlx_audio":
            def take() -> bytes:
                wav = self.inner.preflight_wav()
                self.verifier.check(wav, PREFLIGHT_TEXT, backend=self.backend)
                return wav
            self._retrying(PREFLIGHT_TEXT, take)
            return
        self.inner.preflight()
        try:
            self.verifier.check(verify_mod.preflight_clip_wav(), PREFLIGHT_TEXT,
                                backend=self.backend)
        except SpeechDefect as defect:
            raise SpeechError(
                "verification preflight failed: the speech-to-text model did not transcribe "
                f"emcee's check clip correctly ({defect.reason}); fix [tts.mlx_audio] "
                "stt_model or the server before voicing", details=defect.details) from defect

    def close(self) -> None:
        try:
            self.inner.close()
        finally:
            if self.verifier is not None:
                self.verifier.close()
