"""ONNX parity, TF side (Task 3). Runs in the throwaway TF venv (scripts/export_yamnet_onnx.py).

Decodes each parity track ONCE, as the spike did (librosa 32 kHz mono, then resample to
16 kHz), runs TF Hub YAMNet on it, and saves the 16 kHz waveform and the TF frame scores
to OUT/<key>.npz, so the ONNX side (onnx_parity_onnx.py, llama's own venv) scores the very
same samples: the comparison isolates the model, not the decoder.

    <tfvenv>/bin/python -I onnx_parity_tf.py OUT
"""
import json, os, sys
import numpy as np, librosa, tensorflow_hub as hub

D = "/Volumes/media/lma-radio/delivered"
TRACKS = [  # (key, label, station path); labels from sample.json / population2.tsv
    ("song", "song", None),
    ("space", "space", None),
    ("tuning", "tuning", None),
    ("crowd", "crowd", None),
    ("atbar", "song (at bar)", f"{D}/smashingpumpkins-2008-08-12/audio/01 - Intro.mp3"),
]
S = os.path.dirname(os.path.abspath(__file__))
sample = json.load(open(f"{S}/sample.json"))
PICK = {"song": ("charlieparr-2003-01-10", "Yo-Yo Blues"), "space": ("gratefuldead-1983-10-08", "Space"),
        "tuning": ("furthur-2010-09-25", "Tuning"), "crowd": ("gratefuldead-1977-05-28", "Crowd")}

def path_for(key, default):
    if key in PICK:
        slug, title = PICK[key]
        return next(x["path"] for x in sample if x["slug"] == slug and x["title"] == title)
    return default

out = sys.argv[1]; os.makedirs(out, exist_ok=True)
yam = hub.load("https://tfhub.dev/google/yamnet/1")
for key, label, p in TRACKS:
    p = path_for(key, p)
    y32, _ = librosa.load(p, sr=32000, mono=True)
    y16 = librosa.resample(y32, orig_sr=32000, target_sr=16000).astype(np.float32)
    scores, _, _ = yam(y16)
    np.savez(f"{out}/{key}.npz", wave16k=y16, tf_scores=scores.numpy(), label=label, path=p)
    print(key, label, p, len(y16) / 16000, scores.shape, flush=True)
