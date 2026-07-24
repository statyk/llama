import base64
import hashlib
import os
from pathlib import Path

import httpx

from llama.tts.provider import SpeechError

API_URL = "https://api.mistral.ai/v1/audio/speech"
DEFAULT_MODEL = "voxtral-mini-tts-2603"
# Mistral recommends <=~300 words / 2 min audio per request. Conservative
# char guard; chunk-and-concatenate is deliberately out of scope (see spec).
MAX_INPUT_CHARS = 2000


class VoxtralProvider:
    def __init__(
        self,
        voice: str | None = None,
        clone_ref: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout_s: int = 120,
        transport: httpx.BaseTransport | None = None,
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
        self._client = httpx.Client(timeout=timeout_s, transport=transport)

    def _body(self, text: str, fmt: str) -> dict:
        body = {"model": self.model, "input": text, "response_format": fmt}
        if self._ref_b64 is not None:
            body["ref_audio"] = self._ref_b64
        else:
            body["voice_id"] = self._preset
        return body

    def synthesize(self, text: str, fmt: str = "mp3") -> bytes:
        """fmt="wav" requests response_format="wav" instead of "mp3", for the
        chunked-synthesis path (package.py _synthesize_chunked): callers get
        PCM-in-a-WAV-container bytes they can read with stdlib `wave` and
        concatenate before one MP3 encode. Confirmed against a live Voxtral
        call: it returns the same base64 `audio_data` JSON envelope as the
        mp3 path, just with WAV bytes inside.
        """
        if len(text) > MAX_INPUT_CHARS:
            raise SpeechError(f"DJ segment too long for Voxtral "
                              f"({len(text)} > {MAX_INPUT_CHARS} chars)")
        try:
            resp = self._client.post(
                API_URL, json=self._body(text, fmt),
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        except httpx.HTTPError as e:
            raise SpeechError(f"voxtral request failed: {e}") from e
        if resp.status_code != 200:
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
