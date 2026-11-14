import json, numpy as np, librosa, os, sys, warnings; warnings.filterwarnings("ignore")
import tensorflow_hub as hub
S=os.path.dirname(os.path.abspath(__file__))
yam=hub.load("https://tfhub.dev/google/yamnet/1")
L=json.load(open(f"{S}/labels_all.json")); YL=L["yam_labels"]; YM=YL.index("Music"); YS=YL.index("Speech")
YD=[YL.index(x) for x in ("Drum kit","Drum","Percussion","Snare drum","Bass drum","Drum roll")]
items=[]
for sf,hf in (("sample.json","human_labels.json"),("sample2.json","human_labels2.json"),("sample3.json","human_labels3.json")):
    s=json.load(open(f"{S}/{sf}")); h=json.load(open(f"{S}/{hf}"))
    for k,v in h.items(): items.append((v.get("label"), s[int(k)]))
s1=json.load(open(f"{S}/sample.json"))
items += [("song" if x["group"]=="song" else "space", x) for x in s1 if x["group"] in ("song","space")]
for p in sorted({x["path"] for x in json.load(open(f"{S}/all2.json")) if x["title"].lower()=="silence"}): items.append(("song", {"path":p,"slug":p.split("/")[-3],"title":"Silence"}))
seen=set(); out=[]
def longest(b):
    best=cur=0
    for x in b: cur=cur+1 if x else 0; best=max(best,cur)
    return best
for lab, it in items:
    if it["path"] in seen: continue
    seen.add(it["path"])
    y,_=librosa.load(it["path"], sr=16000, mono=True)
    rms=np.sqrt(np.mean(y**2))+1e-9
    res={}
    for mode in ("raw","norm"):
        yy = y if mode=="raw" else np.clip(y*(0.1/rms), -1, 1)   # -20 dBFS RMS
        ys=yam(yy.astype(np.float32))[0].numpy(); n=max(1,int(len(y)/16000//10)); fpw=len(ys)/n
        w=np.array([ys[int(k*fpw):int((k+1)*fpw)].mean(0) for k in range(n)])
        res[mode]={}
        for mt in (0.5,0.55):
            m=((w[:,YM]>mt)|(w[:,YD].max(1)>0.3))&(w[:,YS]<0.3); res[mode][mt]=(longest(m)*10, float(m.mean()))
    out.append(dict(label=lab, slug=it["slug"], title=it["title"], path=it["path"], rms=float(rms), res=res))
    print(lab, it["slug"], it["title"], f"rms {rms:.3f}", res["raw"][0.55], res["norm"][0.55], flush=True)
json.dump(out, open(f"{S}/norm_test.json","w"))
