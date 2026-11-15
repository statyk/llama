"""Export TF Hub YAMNet (google/yamnet/1) to the bundled ONNX model.

One-off. Runs ONLY in a throwaway venv outside the repo's own venv (TensorFlow must never
be installed into a llama venv or shipped in a binary). The pinned combination that
worked (2026-11-14, macOS arm64):

    uv venv -p 3.11 <work>/tfvenv
    uv pip install -p <work>/tfvenv/bin/python "tensorflow==2.15.1" \
        "tensorflow_hub==0.16.1" "tf2onnx==1.16.1" "numpy<2" "setuptools<70"

    <work>/tfvenv/bin/python -I scripts/export_yamnet_onnx.py \
        packages/llama/src/llama/data/yamnet.onnx

(`setuptools<70` because tensorflow_hub 0.16.1 imports `pkg_resources`.)

Branch A of the audio-check plan: the Hub waveform signature is converted whole, log-mel
front end included (opset 17 for the STFT), float32, not quantized. The ONNX graph takes
`waveform` float32 [N] (16 kHz mono, [-1, 1]) and returns `output_0` float32 [F, 521] (the scores).

It also checks the Hub model's class map equals the committed
`packages/llama/src/llama/data/yamnet_class_map.csv`, and prints the file's sha256 (pin
it as `llama.audio_check.model.MODEL_SHA256`). Parity against TF Hub is recorded in
`docs/superpowers/2026-11-14-audio-check-evidence/onnx-parity.md`.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLASS_MAP = REPO / "packages" / "llama" / "src" / "llama" / "data" / "yamnet_class_map.csv"
HUB_URL = "https://tfhub.dev/google/yamnet/1"
OPSET = 17


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    out = Path(argv[0])

    import tensorflow as tf
    import tensorflow_hub as hub
    import onnx
    import onnx.utils
    import tf2onnx

    path = hub.resolve(HUB_URL)
    yam = tf.saved_model.load(path)

    hub_map = Path(yam.class_map_path().numpy().decode()).read_bytes()
    if hub_map.replace(b"\r\n", b"\n") != CLASS_MAP.read_bytes().replace(b"\r\n", b"\n"):
        print(f"class map differs from {CLASS_MAP}", file=sys.stderr)
        return 1
    print("class map: equal to the committed yamnet_class_map.csv")

    # Convert the SavedModel's serving signature with tf2onnx's own saved-model loader
    # (it freezes the variables; tf2onnx.convert.from_function over a wrapper that calls
    # the signature left 27 resource tensors as graph inputs). Then keep only the scores
    # output (output_1 embeddings and output_2 log-mel patches are intermediates).
    with tempfile.TemporaryDirectory() as td:
        full = Path(td) / "full.onnx"
        subprocess.run(
            [sys.executable, "-m", "tf2onnx.convert", "--saved-model", path,
             "--signature_def", "serving_default", "--opset", str(OPSET),
             "--output", str(full)],
            check=True,
        )
        onnx.utils.extract_model(str(full), str(out), ["waveform"], ["output_0"])
    data = out.read_bytes()
    print(f"wrote {out}: {len(data)} bytes ({len(data) / 1e6:.2f} MB), opset {OPSET}")
    print(f"sha256 {hashlib.sha256(data).hexdigest()}")
    print(f"versions: tensorflow {tf.__version__}, tensorflow_hub {hub.__version__}, "
          f"tf2onnx {tf2onnx.__version__}, python {sys.version.split()[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
