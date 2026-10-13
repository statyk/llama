"""Opt-in: against a running mlx-audio server.

    EMCEE_MLX_URL=http://127.0.0.1:8000 EMCEE_MLX_STT_MODEL=<id> \\
        [EMCEE_MLX_REF=<clip.wav> EMCEE_MLX_REF_TEXT=<transcript.txt>] \\
        ./.venv/bin/pytest -m live packages/emcee/tests/test_mlx_live.py -q

Clones a real speaker's reference clip (default: Phil's evaluated excerpt,
~/tts-bakeoff/refs/phil_ex.wav and its transcript phil_ex.txt); skipped when
the clip or its transcript is absent."""
import io
import os
import wave
from pathlib import Path

import pytest

from emcee.tts.calibration import CALIBRATED_MODELS, QWEN3_TTS_1_7B_BASE
from emcee.tts.mlx_audio import MlxAudioProvider
from emcee.tts.quality import QualitySpeech
from emcee.tts.verify import SttClient, Verifier

pytestmark = pytest.mark.live
URL = os.environ.get("EMCEE_MLX_URL")
STT_MODEL = os.environ.get("EMCEE_MLX_STT_MODEL")
REF = Path(os.environ.get("EMCEE_MLX_REF", "~/tts-bakeoff/refs/phil_ex.wav")).expanduser()
REF_TEXT = Path(os.environ.get("EMCEE_MLX_REF_TEXT", "~/tts-bakeoff/refs/phil_ex.txt")).expanduser()


@pytest.mark.skipif(not (URL and STT_MODEL),
                    reason="set EMCEE_MLX_URL and EMCEE_MLX_STT_MODEL to a running mlx-audio server")
@pytest.mark.skipif(not (REF.is_file() and REF_TEXT.is_file()),
                    reason="set EMCEE_MLX_REF/EMCEE_MLX_REF_TEXT to a reference clip and its transcript")
def test_live_preflight_synthesis_and_verification():
    inner = MlxAudioProvider(url=URL, model=QWEN3_TTS_1_7B_BASE, clone_ref=str(REF),
                             clone_text=REF_TEXT.read_text(),
                             calibration=CALIBRATED_MODELS[QWEN3_TTS_1_7B_BASE])
    speech = QualitySpeech(inner, backend="mlx_audio",
                           verifier=Verifier(SttClient(url=URL, model=STT_MODEL)))
    try:
        speech.preflight()
        wav = speech.synthesize("Tonight we open the vault to the Grateful Dead in Rotterdam.", "wav")
    finally:
        speech.close()
    with wave.open(io.BytesIO(wav), "rb") as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (24000, 1, 2)
