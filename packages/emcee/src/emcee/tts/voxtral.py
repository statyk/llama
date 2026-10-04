import base64
import hashlib
import os
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from emcee.tts.provider import SpeechBlocked, SpeechError

API_URL = "https://api.mistral.ai/v1/audio/speech"
DEFAULT_MODEL = "voxtral-mini-tts-2603"
# Mistral recommends <=~300 words / 2 min audio per request. Conservative
# char guard; chunk-and-concatenate is deliberately out of scope (see spec).
MAX_INPUT_CHARS = 2000
# One retry for failures that are plausibly transient. A guardrail block is a
# 403 and is deterministic (measured 7/7 on the same sentence), so it is never
# retried; nor is any other 4xx but 429.
RETRY_DELAY_S = 2.0


def _is_transient(status: int) -> bool:
    return status == 429 or status >= 500


def _guardrail_block(resp: httpx.Response, text: str) -> SpeechBlocked | None:
    """A SpeechBlocked for a guardrail-violation body, else None (the caller
    raises its ordinary SpeechError). Observed shape (2026-10-03):
    {"type": "guardrail_violation", "guardrails": [{"<moderator>":
    {"categories": {"sexual": {"violated": true}, ...}}}]}."""
    try:
        body = resp.json()
    except ValueError:
        return None
    if not isinstance(body, dict) or body.get("type") != "guardrail_violation":
        return None
    categories: list[str] = []
    for entry in body.get("guardrails") or []:
        if not isinstance(entry, dict):
            continue
        for moderator in entry.values():
            cats = moderator.get("categories") if isinstance(moderator, dict) else None
            for name, verdict in (cats or {}).items():
                if isinstance(verdict, dict) and verdict.get("violated") and name not in categories:
                    categories.append(name)
    return SpeechBlocked("voxtral", text=text, categories=categories)


class VoxtralProvider:
    def __init__(
        self,
        voice: str | None = None,
        clone_ref: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout_s: int = 120,
        transport: httpx.BaseTransport | None = None,
        retry_delay_s: float = RETRY_DELAY_S,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not voice and not clone_ref:
            raise SpeechError("Voxtral needs a preset voice or a clone reference: "
                              "set [tts] voice or [tts] voice_clone")
        self.model = model or DEFAULT_MODEL
        # Env wins over the config key, matching ELEVENLABS_API_KEY handling.
        self.api_key = os.environ.get("MISTRAL_API_KEY") or api_key
        if not self.api_key:
            raise SpeechError("Mistral API key missing: "
                              "set MISTRAL_API_KEY or [tts] api_key")
        if clone_ref:
            try:
                ref_bytes = Path(clone_ref).read_bytes()
            except OSError as e:
                raise SpeechError(f"voice_clone reference unreadable: {e}") from e
            if not ref_bytes:
                raise SpeechError(f"voice_clone reference is empty: {clone_ref}")
            self._ref_b64 = base64.b64encode(ref_bytes).decode()
            self._preset = None
            self.voice = "clone:" + hashlib.sha256(ref_bytes).hexdigest()[:16]
        else:
            self._ref_b64 = None
            self._preset = voice
            self.voice = voice
        self._retry_delay_s = retry_delay_s
        self._sleep = sleep
        self._client = httpx.Client(timeout=timeout_s, transport=transport)

    def _body(self, text: str, fmt: str) -> dict:
        body = {"model": self.model, "input": text, "response_format": fmt}
        if self._ref_b64 is not None:
            body["ref_audio"] = self._ref_b64
        else:
            body["voice_id"] = self._preset
        return body

    def synthesize(self, text: str, fmt: str = "mp3", *,
                   previous_text: str | None = None,
                   next_text: str | None = None) -> bytes:
        """fmt="wav" requests response_format="wav" instead of "mp3", for the
        chunked-synthesis path (package.py _synthesize_chunked): callers get
        PCM-in-a-WAV-container bytes they can read with stdlib `wave` and
        concatenate before one MP3 encode. Confirmed against a live Voxtral
        call: it returns the same base64 `audio_data` JSON envelope as the
        mp3 path, just with WAV bytes inside.

        previous_text/next_text are accepted for interface parity but ignored:
        Mistral's /v1/audio/speech has no context/continuation field, so each
        chunk is unavoidably synthesized cold (verified against Mistral's TTS
        API docs, 2026-07). Cross-chunk prosody conditioning is ElevenLabs-only.
        """
        if len(text) > MAX_INPUT_CHARS:
            raise SpeechError(f"DJ segment too long for Voxtral "
                              f"({len(text)} > {MAX_INPUT_CHARS} chars)")
        for attempt in (1, 2):
            try:
                resp = self._client.post(
                    API_URL, json=self._body(text, fmt),
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            except httpx.TransportError as e:  # includes timeouts
                if attempt == 1:
                    self._sleep(self._retry_delay_s)
                    continue
                raise SpeechError(f"voxtral request failed: {e}") from e
            except httpx.HTTPError as e:
                raise SpeechError(f"voxtral request failed: {e}") from e
            if attempt == 1 and _is_transient(resp.status_code):
                self._sleep(self._retry_delay_s)
                continue
            break
        if resp.status_code != 200:
            blocked = _guardrail_block(resp, text)
            if blocked is not None:
                raise blocked
            raise SpeechError(f"voxtral returned {resp.status_code}: {resp.text[:500]}")
        try:
            audio_b64 = resp.json().get("audio_data")
        except ValueError as e:
            raise SpeechError(f"voxtral returned non-JSON: {resp.text[:200]}") from e
        if not audio_b64:
            raise SpeechError("voxtral returned no audio_data")
        return base64.b64decode(audio_b64)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "VoxtralProvider":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
