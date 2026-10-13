"""Shared fixtures for the mlx_audio backend's tests.

TEST_MODEL / TEST_MODEL_B are test-only calibration entries: production's
CALIBRATED_MODELS is measured (implementation plan Task 12), and no test may
depend on its measured values. Register them per test with
`calibrate_test_model(monkeypatch)`.
"""
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
