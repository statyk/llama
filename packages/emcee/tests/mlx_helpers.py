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

    Speech requests are recorded in `speech_bodies` and answered with a
    plausible silent WAV; `down=True` raises ConnectError for every request
    (counted in `connect_attempts`)."""

    def __init__(self, *, down: bool = False):
        self.down = down
        self.speech_bodies: list[dict] = []
        self.transcriptions: list[httpx.Request] = []
        self.deletes: list[dict] = []
        self.connect_attempts = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            self.connect_attempts += 1
            raise httpx.ConnectError("connection refused", request=request)
        if request.url.path == "/v1/audio/speech":
            body = json.loads(request.content)
            self.speech_bodies.append(body)
            return httpx.Response(200, content=wav_bytes(plausible_seconds(body["input"])))
        return httpx.Response(404, text=f"no route {request.method} {request.url.path}")

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


def install_mlx(monkeypatch, server: MlxServer) -> None:
    """Route the factory's MlxAudioProvider through `server`: no real HTTP,
    no retry sleep."""
    from functools import partial

    from emcee.tts.mlx_audio import MlxAudioProvider
    monkeypatch.setattr("emcee.tts.MlxAudioProvider",
                        partial(MlxAudioProvider, transport=server.transport(),
                                sleep=lambda s: None))
