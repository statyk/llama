import json, numpy as np, os
S = os.path.dirname(os.path.abspath(__file__))
sample = json.load(open(f"{S}/sample.json")); L = json.load(open(f"{S}/labels.json"))
YM = L["yam_labels"].index("Music"); PS = L["panns_labels"].index("Speech")
def longest(b):
    best = cur = 0
    for x in b:
        cur = cur + 1 if x else 0; best = max(best, cur)
    return best
for g in ["song","space","longest15","longintro","midjunk","shortjunk"]:
    out = []
    for i, it in enumerate(sample):
        if it["group"] != g: continue
        z = np.load(f"{S}/feat/{i:03d}.npz"); ys = z["y_scores"][:, YM]; sp = z["p_clip"][:, PS]
        n = len(sp); fpw = len(ys) / max(n,1)
        yw = np.array([ys[int(k*fpw):int((k+1)*fpw)].mean() for k in range(n)])
        m = (yw > 0.5) & (sp < 0.3)
        run = longest(m) * 10
        out.append((run, m.mean(), it))
    for run, frac, it in sorted(out, key=lambda x: -x[0]):
        print(f"{g:10} {it['slug'][:38]:38} {it['title'][:14]:14} dur {it['dur']:4}  longest-music-run {run:4}s  music-frac {frac:.2f}")
    print()
