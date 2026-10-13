"""Local TTS through mlx-audio's OpenAI-style server (`python -m
mlx_audio.server`, mlx-audio 0.5.8). See spec section 2 and the probe
evidence in docs/superpowers/2026-10-12-mlx-audio-probe.md.

One HTTP dialect, model-agnostic: the model is a request field. Clone-only
(`ref_audio` is a local file path the SERVER reads, so it is always sent
absolute; `ref_text` is its transcript). Always requests WAV: the server
writes 16-bit PCM, read with stdlib `wave`; MP3 is encoded locally. There is
no content filter, so SpeechBlocked and the rephrase path never apply.
"""
import hashlib
import io
import struct
import time
import wave
from collections.abc import Callable
from pathlib import Path

import httpx

from emcee.tts.calibration import ModelCalibration, guard_problem, max_tokens_for
from emcee.tts.provider import SpeechDefect, SpeechError

SPEECH_PATH = "/v1/audio/speech"
SAMPLE_RATE = 24000          # only 24 kHz mlx models are supported (Qwen3-TTS is)
PREFLIGHT_TEXT = "Good evening, and welcome to the show."
PREFLIGHT_MAX_TOKENS = 200
CONNECT_RETRY_DELAY_S = 2.0
# Generation failures after the 200 arrive as an aborted chunked body
# (probe doc). Never retried: a timed-out request keeps running server-side.
_GENERATION_FAILURES = (httpx.RemoteProtocolError, httpx.ReadError, httpx.ReadTimeout)


def wav_to_mp3(wav: bytes) -> bytes:
    """Encode a 16-bit PCM WAV to MP3 with emcee's own encoder."""
    from emcee.audio import _encode_mp3  # lazy: emcee.audio imports emcee.tts
    with wave.open(io.BytesIO(wav), "rb") as w:
        return _encode_mp3(w.readframes(w.getnframes()), w.getframerate(), w.getnchannels())


class MlxAudioProvider:
    """`.voice` = "clone:" + sha256(clip bytes + b"\\0" + transcript)[:16]
    (Voxtral's pattern, plus the transcript: a corrected transcript
    invalidates cached clips); `.model` = the resolved model id. Both feed
    the render-cache key."""

    def __init__(self, *, url: str, model: str, clone_ref: str, clone_text: str | None,
                 calibration: ModelCalibration, timeout_s: float = 600.0,
                 transport: httpx.BaseTransport | None = None,
                 retry_delay_s: float = CONNECT_RETRY_DELAY_S,
                 sleep: Callable[[float], None] = time.sleep):
        transcript = (clone_text or "").strip()
        if not transcript:
            raise SpeechError("mlx_audio needs the reference clip's transcript "
                              "(voice_clone_text); it is empty")
        path = Path(clone_ref).expanduser().resolve()
        try:
            ref_bytes = path.read_bytes()
        except OSError as e:
            raise SpeechError(f"voice_clone reference unreadable: {e}") from e
        if not ref_bytes:
            raise SpeechError(f"voice_clone reference is empty: {path}")
        self.url = url.rstrip("/")
        self.model = model
        self.voice = "clone:" + hashlib.sha256(
            ref_bytes + b"\0" + transcript.encode()).hexdigest()[:16]
        self._ref_audio = str(path)
        self._ref_text = transcript
        self._cal = calibration
        self._retry_delay_s = retry_delay_s
        self._sleep = sleep
        self._client = httpx.Client(timeout=timeout_s, transport=transport)

    def synthesize(self, text: str, fmt: str = "mp3", *,
                   previous_text: str | None = None,
                   next_text: str | None = None) -> bytes:
        """previous_text/next_text are accepted for interface parity and
        ignored: the endpoint has no context field. The runaway guard runs on
        every clip; its SpeechDefect is never retried here."""
        max_tokens = max_tokens_for(self._cal, text)
        wav = self._post(text, max_tokens)
        problem = guard_problem(self._cal, text, self._read_wav(wav), max_tokens)
        if problem:
            raise SpeechDefect("mlx_audio", text=text, reason=problem)
        return wav if fmt == "wav" else wav_to_mp3(wav)

    def preflight(self) -> None:
        """One fixed sentence: a down server, an unknown or unloadable model,
        or a bad response fails here, before any LLM spend -- and the cold
        model load is absorbed, at no cost."""
        self.preflight_wav()

    def preflight_wav(self) -> bytes:
        """The preflight sentence's take, after the 16-bit mono 24 kHz and
        non-empty checks. The verified preflight (tts/quality.py) transcribes
        this same take rather than synthesizing a second one."""
        wav = self._post(PREFLIGHT_TEXT, PREFLIGHT_MAX_TOKENS)
        if self._read_wav(wav) <= 0:
            raise SpeechError(f"mlx-audio preflight returned no audio for {self.model!r}; "
                              "see the mlx-audio server log")
        return wav

    def close(self) -> None:
        self._client.close()

    def _post(self, text: str, max_tokens: int) -> bytes:
        body = {"model": self.model, "input": text, "response_format": "wav",
                "max_tokens": max_tokens, "ref_audio": self._ref_audio,
                "ref_text": self._ref_text}
        for attempt in (1, 2):
            try:
                resp = self._client.post(self.url + SPEECH_PATH, json=body)
            except httpx.ConnectError as e:
                if attempt == 1:
                    self._sleep(self._retry_delay_s)
                    continue
                raise SpeechError(f"mlx-audio server not reachable at {self.url} "
                                  "(is the launchd service running?)") from e
            except _GENERATION_FAILURES as e:
                raise SpeechError(f"mlx-audio generation failed mid-response "
                                  f"({type(e).__name__}: {e}); see the mlx-audio server log") from e
            except httpx.HTTPError as e:
                raise SpeechError(f"mlx-audio request failed: {e}") from e
            break
        if resp.status_code != 200:
            raise SpeechError(f"mlx-audio returned {resp.status_code}: {resp.text[:500]}")
        return resp.content

    def _read_wav(self, data: bytes) -> float:
        """Seconds of audio in a server WAV, after checking it is 16-bit mono
        24 kHz. Counted from the frames actually read, not the header."""
        if not data:
            raise SpeechError("mlx-audio returned an empty body; see the mlx-audio server log")
        try:
            with wave.open(io.BytesIO(data), "rb") as w:
                width, channels, rate = w.getsampwidth(), w.getnchannels(), w.getframerate()
                frames = w.readframes(w.getnframes())
        except (wave.Error, EOFError, struct.error) as e:
            raise SpeechError(f"mlx-audio returned a non-WAV body ({e}); "
                              "see the mlx-audio server log") from e
        if width != 2:
            raise SpeechError(f"mlx-audio returned {width * 8}-bit audio; emcee needs 16-bit PCM")
        if channels != 1:
            raise SpeechError(f"mlx-audio returned {channels}-channel audio; emcee needs mono")
        if rate != SAMPLE_RATE:
            raise SpeechError(f"mlx-audio model {self.model!r} returns {rate} Hz audio; "
                              "emcee supports only 24 kHz mlx models")
        return len(frames) / (width * channels * rate)
