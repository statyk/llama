import json, numpy as np, os, collections
S = os.path.dirname(os.path.abspath(__file__))
A = json.load(open(f"{S}/all.json")); L = json.load(open(f"{S}/labels_all.json"))
YL, PL = L["yam_labels"], L["panns_labels"]; YM = YL.index("Music"); YS = YL.index("Speech")
YD = [YL.index(x) for x in ("Drum kit","Drum","Percussion","Snare drum","Bass drum","Drum roll")]
PS = PL.index("Speech"); PD = [PL.index(x) for x in ("Drum kit","Drum","Percussion")]
def longest(b):
    best = cur = 0
    for x in b: cur = cur+1 if x else 0; best = max(best, cur)
    return best
res = []
for i, it in enumerate(A):
    p = f"{S}/feat_all/{i:03d}.npz"
    if not os.path.exists(p): continue
    z = np.load(p); ys = z["y_scores"]; pc = z["p_clip"]; n = len(pc); fpw = len(ys)/n
    w = np.array([ys[int(j*fpw):int((j+1)*fpw)].mean(0) for j in range(n)])
    my = ((w[:,YM]>0.5)|(w[:,YD].max(1)>0.3))&(w[:,YS]<0.3)
    mc = ((w[:,YM]>0.5)|(pc[:,PD].max(1)>0.5))&(pc[:,PS]<0.3)
    res.append(dict(it, y=bool(longest(my)*10>=120 and my.mean()>=0.7), c=bool(longest(mc)*10>=120 and mc.mean()>=0.7),
                    yrun=longest(my)*10, yfrac=float(my.mean())))
json.dump(res, open(f"{S}/scale.json","w"), indent=0)
print(len(res), "tracks scored")
for k in ("y","c"):
    hit = [r for r in res if r[k] and r["title"].lower()!="silence"]
    shows = {r["slug"] for r in hit}; already = {r["slug"] for r in hit if r["held"]=="True"}
    print(f"{'YAMNet-only' if k=='y' else 'YAMNet+PANNs'}: {len(hit)} tracks flagged as music, {len(shows)} shows ({len(already)} already held by size rule); by rule", dict(collections.Counter(r['rule'] for r in hit)))
both = {r["slug"] for r in res if r["y"]} ^ {r["slug"] for r in res if r["c"]}
print("shows where the two disagree:", len(both))
print("near-misses (YAMNet run>=90 or frac>=0.6, not flagged):", sum(1 for r in res if not r["y"] and (r["yrun"]>=90 or r["yfrac"]>=0.6)))
