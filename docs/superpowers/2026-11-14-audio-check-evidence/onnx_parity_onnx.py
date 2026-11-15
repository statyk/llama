"""ONNX parity, ONNX side (Task 3). Runs in llama's own venv (onnxruntime, no TF).

Reads OUT/<key>.npz from onnx_parity_tf.py, scores the same 16 kHz waveform with the
bundled model (llama.audio_check.model.load()), and prints the parity table: frames, max
abs diff over all classes and over Music/Speech/the six drum classes, and (run_sec, frac,
verdict) from llama.audio_check.rule for TF and for ONNX.

    .venv/bin/python onnx_parity_onnx.py OUT
"""
import sys
import numpy as np
from llama.audio_check import model, rule

KEYS = ["song", "space", "tuning", "crowd", "atbar"]
RULE = ["Music", "Speech", "Drum kit", "Drum", "Percussion", "Snare drum", "Bass drum", "Drum roll"]
idx = [model.CLASS_NAMES.index(n) for n in RULE]
m = model.load()
ok = True
print("| track | label | dur s | frames | max diff (all 521) | max diff (rule classes) | worst rule class | TF run_sec, frac, verdict | ONNX run_sec, frac, verdict |")
print("|---|---|---|---|---|---|---|---|---|")
for k in KEYS:
    z = np.load(f"{sys.argv[1]}/{k}.npz")
    wave, tf_s = z["wave16k"], z["tf_scores"]
    ox = m.frame_scores(wave)
    assert ox.shape == tf_s.shape, (k, ox.shape, tf_s.shape)
    d = np.abs(ox.astype(np.float64) - tf_s.astype(np.float64))
    per = d[:, idx].max(axis=0)
    dur = len(wave) / 16000
    mt, mo = rule.measure(tf_s, dur), rule.measure(ox, dur)
    vt, vo = rule.verdict(mt), rule.verdict(mo)
    ok &= vt == vo and float(per.max()) < 0.02
    print(f"| {k} | {z['label']} | {dur:.1f} | {ox.shape[0]} | {d.max():.2e} | {per.max():.2e} | "
          f"{RULE[int(per.argmax())]} | {mt.run_sec}, {mt.frac:.2f}, {vt} | {mo.run_sec}, {mo.frac:.2f}, {vo} |")
print("PASS" if ok else "FAIL")
