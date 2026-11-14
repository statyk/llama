import json, numpy as np, os
S = os.path.dirname(os.path.abspath(__file__))
sample = json.load(open(f"{S}/sample.json")); L = json.load(open(f"{S}/labels.json")); H = json.load(open(f"{S}/human_labels.json"))
YL = L["yam_labels"]; YM = YL.index("Music"); YS = [YL.index(x) for x in ("Speech",)]
YD = [YL.index(x) for x in ("Drum kit","Drum","Percussion","Snare drum","Bass drum","Drum roll")]
def longest(b):
    best = cur = 0
    for x in b: cur = cur+1 if x else 0; best = max(best, cur)
    return best
def meas(i, sp_t=0.3):
    z = np.load(f"{S}/feat/{i:03d}.npz"); ys = z["y_scores"]
    n = max(1, int(round(len(ys)*0.48/10))); fpw = len(ys)/n
    w = np.array([ys[int(j*fpw):int((j+1)*fpw)].mean(0) for j in range(n)])
    m = ((w[:,YM] > 0.5) | (w[:,YD].max(1) > 0.3)) & (w[:,YS].max(1) < sp_t)
    return longest(m)*10, m.mean()
lab = lambda i: H.get(f"{i:03d}",{}).get("label") or {"song":"song*","space":"space*"}.get(sample[i]["group"])
res = [(lab(i), *meas(i), sample[i]) for i in range(len(sample))]
order = {"song":0,"song*":1,"space*":2,"junk":3}
for l, run, frac, it in sorted(res, key=lambda r:(order.get(r[0],9), -r[1])):
    flag = "MUSIC" if run >= 120 and frac >= 0.7 else "-"
    print(f"{l:7} {flag:5} run {run:4}s frac {frac:.2f}  {it['slug'][:36]:36} {it['title'][:14]:14} {it['dur']}s")
