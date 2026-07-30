import io
import os
import wave

import httpx

from emcee.tts.provider import SpeechError

API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
DEFAULT_MODEL = "eleven_multilingual_v2"

# Chunked synthesis needs raw PCM to concatenate cleanly (package.py
# _synthesize_chunked). ElevenLabs' pcm_* output_format returns headerless
# 16-bit little-endian mono PCM at the given rate, not a JSON envelope. This
# path has not been exercised against a live ElevenLabs call (Voxtral is the
# backend that has); if it misbehaves in practice, this is the first place
# to check.
CHUNK_PCM_RATE = 24000


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

    def synthesize(self, text: str, fmt: str = "mp3", *,
                   previous_text: str | None = None,
                   next_text: str | None = None) -> bytes:
        """fmt="wav" requests headerless PCM from ElevenLabs (output_format
        pcm_24000) and wraps it in a WAV container, for the chunked-synthesis
        path (package.py _synthesize_chunked) so callers can use the stdlib
        `wave` module uniformly across backends. See CHUNK_PCM_RATE above.

        previous_text/next_text (chunked mode): the adjacent chunks' text.
        ElevenLabs conditions synthesis on them so prosody flows across chunk
        boundaries instead of each chunk being spoken cold. A side that has no
        neighbor (first/last chunk) is left out of the body rather than sent as
        null.
        """
        params = {}
        headers = {"xi-api-key": self.api_key, "accept": "audio/mpeg"}
        if fmt == "wav":
            params["output_format"] = f"pcm_{CHUNK_PCM_RATE}"
            headers["accept"] = "audio/pcm"
        body = {"text": text, "model_id": self.model}
        if previous_text is not None:
            body["previous_text"] = previous_text
        if next_text is not None:
            body["next_text"] = next_text
        try:
            resp = self._client.post(
                API_URL.format(voice_id=self.voice),
                json=body,
                params=params,
                headers=headers,
            )
        except httpx.HTTPError as e:
            raise SpeechError(f"elevenlabs request failed: {e}") from e
        if resp.status_code != 200:
            raise SpeechError(f"elevenlabs returned {resp.status_code}: {resp.text[:500]}")
        if not resp.content:
            raise SpeechError("elevenlabs returned empty audio")
        if fmt == "wav":
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)  # 16-bit PCM
                w.setframerate(CHUNK_PCM_RATE)
                w.writeframes(resp.content)
            return buf.getvalue()
        return resp.content

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ElevenLabsProvider":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
