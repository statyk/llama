import json, numpy as np, os
S=os.path.dirname(os.path.abspath(__file__))
L=json.load(open(f"{S}/labels_all.json")); YL=L["yam_labels"]; YM=YL.index("Music"); YS=YL.index("Speech")
YD=[YL.index(x) for x in ("Drum kit","Drum","Percussion","Snare drum","Bass drum","Drum roll")]
B=json.load(open(f"{S}/all2.json"))
H={}
for sf,hf in (("sample.json","human_labels.json"),("sample2.json","human_labels2.json")):
    s=json.load(open(f"{S}/{sf}")); h=json.load(open(f"{S}/{hf}"))
    for k,v in h.items(): H.setdefault(s[int(k)]["path"], v.get("label"))
def longest(b):
    best=cur=0
    for x in b: cur=cur+1 if x else 0; best=max(best,cur)
    return best
rows=[]
for j,a in enumerate(B):
    z=np.load(f"{S}/feat_all2/{j:03d}.npz"); ys=z["y_scores"]; n=len(z["p_clip"]); fpw=len(ys)/n
    w=np.array([ys[int(k*fpw):int((k+1)*fpw)].mean(0) for k in range(n)])
    lab=H.get(a["path"]) or ("song" if a["title"].lower()=="silence" else "")
    r={}
    for mt in (0.5,0.55,0.6):
        m=((w[:,YM]>mt)|(w[:,YD].max(1)>0.3))&(w[:,YS]<0.3); r[mt]=(longest(m)*10, float(m.mean()))
    rows.append((a,lab,r))
json.dump([dict(a, label=lab, **{f"run{mt}":r[mt][0] for mt in r}, **{f"frac{mt}":r[mt][1] for mt in r}) for a,lab,r in rows], open(f"{S}/rescored.json","w"))
for mt in (0.5,0.55,0.6):
  for run in (90,120):
    flag=[(a,lab) for a,lab,r in rows if r[mt][0]>=run and r[mt][1]>=0.7]
    songs={a["path"] for a,lab,r in rows if lab=="song"}
    caught={a["path"] for a,lab in flag if lab=="song"}
    fp=sum(1 for a,lab in flag if lab=="junk"); unl=sum(1 for a,lab in flag if lab=="")
    shows={a["slug"] for a,lab in flag if a["title"].lower()!="silence"}
    print(f"music>{mt} run>={run}: songs {len(caught)}/{len(songs)}  junk-FP {fp}  unlabelled-flagged {unl}  shows held {len(shows)}")
print("files labelled twice (one path):", len([p for p in H]) )
