import json, sys, os, time, tempfile, numpy as np, librosa, soundfile as sf, warnings
warnings.filterwarnings("ignore")
S = os.path.dirname(os.path.abspath(__file__))
sample = json.load(open(f"{S}/all.json"))
OUT = f"{S}/feat_all"; os.makedirs(OUT, exist_ok=True)
WIN = 10.0
import torch
from panns_inference import AudioTagging, labels as PL
at = AudioTagging(checkpoint_path=None, device="cpu")
import tensorflow as tf, tensorflow_hub as hub
yam = hub.load("https://tfhub.dev/google/yamnet/1")
ycls = [l.split(",",2)[2].strip().strip('"') for l in open(yam.class_map_path().numpy().decode()).read().splitlines()[1:]]
json.dump({"panns_labels": PL, "yam_labels": ycls}, open(f"{S}/labels_all.json","w"))
LIMIT=int(os.environ.get('LIMIT','9999'))
for i, it in enumerate(sample[:LIMIT]):
    key = f"{i:03d}"
    if os.path.exists(f"{OUT}/{key}.npz"): continue
    t0 = time.time()
    y32, _ = librosa.load(it["path"], sr=32000, mono=True)
    n = max(1, int(len(y32) // (WIN*32000)))
    wins = np.stack([y32[int(k*WIN*32000):int((k+1)*WIN*32000)] for k in range(n)]) if len(y32) >= WIN*32000 else np.pad(y32,(0,int(WIN*32000)-len(y32)))[None]
    clip, emb = [], []
    for b in range(0, len(wins), 16):
        c, e = at.inference(wins[b:b+16]); clip.append(c); emb.append(e)
    p_clip, p_emb = np.concatenate(clip), np.concatenate(emb)
    y16 = librosa.resample(y32, orig_sr=32000, target_sr=16000)
    ys, ye, _ = yam(y16.astype(np.float32)); ys, ye = ys.numpy(), ye.numpy()
    # pulse clarity per window: max normalized autocorr of onset envelope at 0.3-2s lags
    pulse = []
    for w in wins:
        oe = librosa.onset.onset_strength(y=w, sr=32000)
        oe = oe - oe.mean(); ac = np.correlate(oe, oe, "full")[len(oe)-1:]
        hop = 512/32000; lo, hi = int(0.3/hop), int(2.0/hop)
        pulse.append(float(ac[lo:hi].max()/ac[0]) if ac[0] > 0 else 0.0)
    rms = librosa.feature.rms(y=y32, frame_length=32000, hop_length=32000)[0]
    np.savez_compressed(f"{OUT}/{key}.npz", p_clip=p_clip, p_emb=p_emb, y_scores=ys, y_emb=ye, pulse=np.array(pulse), rms=rms)
    print(key, it["group"], it["slug"], it["title"], f"{time.time()-t0:.1f}s", flush=True)
json.dump({"panns_labels": PL, "yam_labels": ycls}, open(f"{S}/labels_all.json","w"))
