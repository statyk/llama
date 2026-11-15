import hashlib
from pathlib import Path

import numpy as np
import pytest

from llama.audio_check import model
from llama.errors import LlamaError


def test_model_file_sha256_pinned():
    assert hashlib.sha256(model.MODEL_FILE.read_bytes()).hexdigest() == model.MODEL_SHA256


@pytest.mark.real_model
def test_frame_scores_shape_on_tone():  # skipped if onnxruntime missing
    wave = 0.1 * np.sin(2 * np.pi * 440 * np.arange(16000 * 3) / 16000).astype(np.float32)
    s = model.load().frame_scores(wave)
    assert s.shape[1] == 521 and 5 <= s.shape[0] <= 7


@pytest.mark.real_model
def test_frame_scores_float32_in_unit_range():
    wave = np.zeros(16000 * 2, dtype=np.float32)
    s = model.load().frame_scores(wave)
    assert s.dtype == np.float32
    assert float(s.min()) >= 0.0 and float(s.max()) <= 1.0


def test_load_failure_is_classifier_unavailable(monkeypatch):
    monkeypatch.setattr(model, "MODEL_FILE", Path("/nonexistent.onnx"))
    with pytest.raises(model.ClassifierUnavailable):
        model.load()


def test_runtime_import_failure_is_classifier_unavailable(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def no_ort(name, *a, **k):
        if name == "onnxruntime" or name.startswith("onnxruntime."):
            raise ImportError("no onnxruntime here")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_ort)
    with pytest.raises(model.ClassifierUnavailable):
        model.load()


def test_classifier_unavailable_is_llama_error():
    assert issubclass(model.ClassifierUnavailable, LlamaError)


def test_model_module_import_is_light():
    import subprocess
    import sys

    code = (
        "import sys; import llama.audio_check.model as m; "
        "assert m.CLASS_NAMES and m.MODEL_FILE; "
        "print(sorted(k for k in ('numpy', 'onnxruntime') if k in sys.modules))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"
