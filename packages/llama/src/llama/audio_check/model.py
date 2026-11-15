"""YAMNet: class map and the bundled ONNX runtime.

Importing this module loads neither numpy nor onnxruntime: both are imported inside
`load()`, only when a drop is actually checked. The model file is TF Hub
`google/yamnet/1` converted whole (log-mel front end included) by
`scripts/export_yamnet_onnx.py`; parity with TF Hub is recorded in
`docs/superpowers/2026-11-14-audio-check-evidence/onnx-parity.md`.
"""

from __future__ import annotations

import csv
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

from llama.errors import LlamaError

if TYPE_CHECKING:
    import numpy as np


def _load_class_names() -> tuple[str, ...]:
    path = resources.files("llama.data").joinpath("yamnet_class_map.csv")
    with path.open("r", encoding="utf-8", newline="") as fh:
        rows = sorted(csv.DictReader(fh), key=lambda r: int(r["index"]))
    return tuple(r["display_name"] for r in rows)


CLASS_NAMES: tuple[str, ...] = _load_class_names()

MODEL_FILE: Path = Path(str(resources.files("llama.data").joinpath("yamnet.onnx")))
# sha256 of the bundled yamnet.onnx; rule.VERSION is pinned together with it (a test).
MODEL_SHA256 = "f6715c8eea28e034b467756202d1adc1f9cd6cc9582ee76021c2824d44d791a9"

_INPUT = "waveform"
_OUTPUT = "output_0"


class ClassifierUnavailable(LlamaError):
    """The audio classifier's runtime or model file could not be loaded."""


class Model:
    """A loaded YAMNet session. Build it with `load()`."""

    def __init__(self, session) -> None:
        self._session = session

    def frame_scores(self, wave16k: "np.ndarray") -> "np.ndarray":
        """Per-frame class scores, shape (F, 521), for a 16 kHz mono float32 waveform.

        Frames are 0.96 s at a 0.48 s hop (YAMNet's own framing, padded as YAMNet pads).
        """
        import numpy as np

        wave = np.ascontiguousarray(np.asarray(wave16k, dtype=np.float32).reshape(-1))
        (scores,) = self._session.run([_OUTPUT], {_INPUT: wave})
        return np.asarray(scores, dtype=np.float32)


def load() -> Model:
    """Load the bundled model. Raises ClassifierUnavailable on any load failure."""
    try:
        import numpy  # noqa: F401  (frame_scores needs it; fail here, not mid-check)
        import onnxruntime as ort
    except Exception as exc:  # ImportError, or a broken wheel's own error
        raise ClassifierUnavailable(f"the audio classifier runtime cannot load: {exc}") from exc
    path = MODEL_FILE
    try:
        session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    except Exception as exc:
        raise ClassifierUnavailable(
            f"the audio classifier model cannot load from {path}: {exc}"
        ) from exc
    return Model(session)
