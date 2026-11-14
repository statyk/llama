import json, numpy as np, os
S = os.path.dirname(os.path.abspath(__file__))
sample = json.load(open(f"{S}/sample.json")); L = json.load(open(f"{S}/labels.json")); H = json.load(open(f"{S}/human_labels.json"))
YM = L["yam_labels"].index("Music"); PS = L["panns_labels"].index("Speech"); DR=[L["panns_labels"].index(x) for x in ("Drum kit","Drum","Percussion")]
def longest(b):
    best = cur = 0
    for x in b: cur = cur+1 if x else 0; best = max(best, cur)
    return best
rows=[]
for k,h in H.items():
    i=int(k); it=sample[i]; z=np.load(f"{S}/feat/{k}.npz"); ys=z["y_scores"][:,YM]; sp=z["p_clip"][:,PS]; dr=z["p_clip"][:,DR].max(1)
    n=len(sp); fpw=len(ys)/n; yw=np.array([ys[int(j*fpw):int((j+1)*fpw)].mean() for j in range(n)])
    m=((yw>0.5)|(dr>0.5))&(sp<0.3)
    rows.append((h.get("label"), longest(m)*10, m.mean(), it, h.get("note","")))
order={"song":0,"mixed":1,"unsure":2,"junk":3,None:4}
for lab,run,frac,it,note in sorted(rows,key=lambda r:(order[r[0]],-r[1])):
    print(f"{str(lab):7} run {run:4}s frac {frac:.2f}  {it['group']:9} {it['slug'][:36]:36} {it['title'][:14]:14} {it['dur']:4}s  {note}")
print(len(rows),"labelled")
