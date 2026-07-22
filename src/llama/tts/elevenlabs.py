import os

import httpx

from llama.tts.provider import SpeechError

API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
DEFAULT_MODEL = "eleven_multilingual_v2"


class ElevenLabsProvider:
    def __init__(
        self,
        voice: str,
        model: str | None = None,
        api_key: str | None = None,
        timeout_s: int = 120,
        transport: httpx.BaseTransport | None = None,
    ):
        self.voice = voice
        self.model = model or DEFAULT_MODEL
        # Env wins over the config key, matching SETLISTFM_API_KEY handling.
        self.api_key = os.environ.get("ELEVENLABS_API_KEY") or api_key
        if not self.api_key:
            raise SpeechError("ElevenLabs API key missing: "
                              "set ELEVENLABS_API_KEY or [tts] api_key")
        self._client = httpx.Client(timeout=timeout_s, transport=transport)

    def synthesize(self, text: str) -> bytes:
        try:
            resp = self._client.post(
                API_URL.format(voice_id=self.voice),
                json={"text": text, "model_id": self.model},
                headers={"xi-api-key": self.api_key, "accept": "audio/mpeg"},
            )
        except httpx.HTTPError as e:
            raise SpeechError(f"elevenlabs request failed: {e}") from e
        if resp.status_code != 200:
            raise SpeechError(f"elevenlabs returned {resp.status_code}: {resp.text[:500]}")
        if not resp.content:
            raise SpeechError("elevenlabs returned empty audio")
        return resp.content

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ElevenLabsProvider":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
