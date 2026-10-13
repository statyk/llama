"""Shared fixtures for the mlx_audio backend's tests.

TEST_MODEL / TEST_MODEL_B are test-only calibration entries: production's
CALIBRATED_MODELS is measured (implementation plan Task 12), and no test may
depend on its measured values. Register them per test with
`calibrate_test_model(monkeypatch)`.
"""
import io
import json
import wave

import httpx

from emcee.tts import calibration

TEST_MODEL = "test/mlx-tts-model"
TEST_MODEL_B = "test/mlx-tts-model-b"
TEST_CAL = calibration.ModelCalibration(
    frame_rate_hz=12.5, cap_floor_s=8.0, cap_s_per_char=0.12, max_floor_s=4.0,
    max_s_per_char=0.11, min_s_per_char=0.03, min_slack_s=1.0, cap_margin_s=1.0)


def calibrate_test_model(monkeypatch, *models: str) -> None:
    """Register TEST_CAL under `models` (default: TEST_MODEL) for one test."""
    for model in models or (TEST_MODEL,):
        monkeypatch.setitem(calibration.CALIBRATED_MODELS, model, TEST_CAL)


def wav_bytes(seconds: float, *, rate: int = 24000, channels: int = 1, width: int = 2) -> bytes:
    """A silent PCM WAV of `seconds`."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(bytes(int(seconds * rate) * channels * width))
    return buf.getvalue()


def plausible_seconds(text: str) -> float:
    """A duration TEST_CAL's guard accepts for `text` (0.06 s per character,
    at least 0.5 s)."""
    return max(0.5, 0.06 * len(" ".join(text.split())))


class MlxServer:
    """An httpx MockTransport handler standing in for mlx_audio.server.

    - speech: recorded in `speech_bodies`, answered with a plausible silent WAV,
      or `speech_status` when that is not 200 (an unknown/unloadable model);
    - transcription: recorded in `transcriptions`; answers `transcript(last)`
      where `last` is the last synthesized input (default: echo `last`), or
      `stt_status` when that is not 200;
    - DELETE /v1/models: recorded in `deletes`, 204.
    `down=True` raises ConnectError for every request, `stt_down=True` for
    transcription only (both counted in `connect_attempts`)."""

    def __init__(self, *, down: bool = False, stt_down: bool = False, transcript=None,
                 stt_status: int = 200, speech_status: int = 200):
        self.down = down
        self.stt_down = stt_down
        self.transcript = transcript
        self.stt_status = stt_status
        self.speech_status = speech_status
        self.speech_bodies: list[dict] = []
        self.transcriptions: list[httpx.Request] = []
        self.deletes: list[dict] = []
        self.connect_attempts = 0
        self._last_input = ""

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if self.down or (self.stt_down and path == "/v1/audio/transcriptions"):
            self.connect_attempts += 1
            raise httpx.ConnectError("connection refused", request=request)
        if path == "/v1/audio/speech":
            body = json.loads(request.content)
            self.speech_bodies.append(body)
            self._last_input = body["input"]
            if self.speech_status != 200:
                return httpx.Response(self.speech_status, text="Model could not be loaded")
            return httpx.Response(200, content=wav_bytes(plausible_seconds(body["input"])))
        if path == "/v1/audio/transcriptions":
            self.transcriptions.append(request)
            if self.stt_status != 200:
                return httpx.Response(self.stt_status, text="transcription failed")
            heard = self.transcript(self._last_input) if self.transcript else self._last_input
            return httpx.Response(200, json={"text": heard})
        if path == "/v1/models" and request.method == "DELETE":
            self.deletes.append(dict(request.url.params))
            return httpx.Response(204)
        return httpx.Response(404, text=f"no route {request.method} {path}")

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


def install_mlx(monkeypatch, server: MlxServer) -> None:
    """Route the factory's MlxAudioProvider and SttClient through `server`:
    no real HTTP, no retry sleep."""
    from functools import partial

    from emcee.tts.mlx_audio import MlxAudioProvider
    from emcee.tts.verify import SttClient
    monkeypatch.setattr("emcee.tts.MlxAudioProvider",
                        partial(MlxAudioProvider, transport=server.transport(),
                                sleep=lambda s: None))
    monkeypatch.setattr("emcee.tts.SttClient", partial(SttClient, transport=server.transport()))
