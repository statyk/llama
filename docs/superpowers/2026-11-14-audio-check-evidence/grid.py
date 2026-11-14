import json, numpy as np, os, itertools
S = os.path.dirname(os.path.abspath(__file__))
L = json.load(open(f"{S}/labels.json")); YL, PL = L["yam_labels"], L["panns_labels"]
YM = YL.index("Music"); YS = [YL.index(x) for x in ("Speech","Conversation","Chatter","Hubbub, speech noise, speech babble","Crowd","Cheering","Applause")]
YD = [YL.index(x) for x in ("Drum kit","Drum","Percussion","Snare drum","Bass drum","Drum roll")]
PS = PL.index("Speech"); PD=[PL.index(x) for x in ("Drum kit","Drum","Percussion")]
items = []  # (label, npz)
s1 = json.load(open(f"{S}/sample.json")); h1 = json.load(open(f"{S}/human_labels.json"))
for i, it in enumerate(s1):
    lab = h1.get(f"{i:03d}",{}).get("label") or {"song":"song","space":"space"}.get(it["group"])
    items.append((lab, f"{S}/feat/{i:03d}.npz", it))
s2 = json.load(open(f"{S}/sample2.json")); h2 = json.load(open(f"{S}/human_labels2.json")); A = json.load(open(f"{S}/all.json"))
pidx = {a["path"]: j for j, a in enumerate(A)}
for k, h in h2.items():
    it = s2[int(k)]; items.append((h["label"], f"{S}/feat_all/{pidx[it['path']]:03d}.npz", it))
def longest(b):
    best = cur = 0
    for x in b: cur = cur+1 if x else 0; best = max(best, cur)
    return best
W = []
for lab, p, it in items:
    z = np.load(p); ys = z["y_scores"]; pc = z["p_clip"]; n = len(pc); fpw = len(ys)/n
    w = np.array([ys[int(j*fpw):int((j+1)*fpw)].mean(0) for j in range(n)])
    W.append((lab, w, pc, it))
def score(fn):
    tp=fp=fn_=0; fps=[]; fns=[]
    for lab, w, pc, it in W:
        if lab not in ("song","junk"): continue
        f = fn(w, pc)
        if f and lab=="song": tp+=1
        elif f and lab=="junk": fp+=1; fps.append(it["slug"])
        elif not f and lab=="song": fn_+=1; fns.append(it["slug"])
    return tp, fp, fn_, fps, fns
def rule(m, run, frac): return longest(m)*10 >= run and m.mean() >= frac
print("combined:", score(lambda w,pc: rule(((w[:,YM]>0.5)|(pc[:,PD].max(1)>0.5))&(pc[:,PS]<0.3), 120, 0.7))[:3])
best=[]
for mt, st, run, frac, agg in itertools.product((0.5,0.6,0.7),(0.05,0.1,0.15,0.2,0.3),(120,150,180),(0.7,0.8,0.9),("speech","broad")):
    sidx = YS[:1] if agg=="speech" else YS
    r = score(lambda w,pc: rule(((w[:,YM]>mt)|(w[:,YD].max(1)>0.3))&(w[:,sidx].max(1)<st), run, frac))
    best.append((r[1]+r[2], r[1], r[2], (mt,st,run,frac,agg), r[3], r[4]))
best.sort(key=lambda x:(x[0], x[1]))
for b in best[:8]: print(b[:4]); 
print("best FP:", best[0][4]); print("best FN:", best[0][5])
f6 = lambda w,pc: rule(((w[:,YM]>0.6)|(w[:,YD].max(1)>0.3))&(w[:,YS[:1]].max(1)<0.3), 120, 0.7)
print("space flagged as music:", sum(f6(w,pc) for lab,w,pc,it in W if lab=="space"), "of", sum(1 for x in W if x[0]=="space"))
print("unsure flagged:", [(it['slug'], f6(w,pc)) for lab,w,pc,it in W if lab=="unsure"])
hits=[]
for j,a in enumerate(A):
    z=np.load(f"{S}/feat_all/{j:03d}.npz"); ys=z["y_scores"]; pc=z["p_clip"]; n=len(pc); fpw=len(ys)/n
    w=np.array([ys[int(k*fpw):int((k+1)*fpw)].mean(0) for k in range(n)])
    if f6(w,pc) and a["title"].lower()!="silence": hits.append(a)
print("population: tracks", len(hits), "shows", len({a['slug'] for a in hits}), "already size-held", len({a['slug'] for a in hits if a['held']=='True'}))
