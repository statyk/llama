import json, numpy as np, os, sys
S = os.path.dirname(os.path.abspath(__file__))
sample = json.load(open(f"{S}/sample.json")); L = json.load(open(f"{S}/labels.json"))
PL, YL, PR = L["panns_labels"], L["yam_labels"], L["prompts"]
def ix(labels, names): return [labels.index(n) for n in names]
P_MUS, Y_MUS = ix(PL,["Music"]), ix(YL,["Music"])
P_DRUM = ix(PL,["Drum kit","Drum","Snare drum","Bass drum"]); P_CROWD = ix(PL,["Crowd","Cheering","Applause","Clapping"])
P_SPEECH = ix(PL,["Speech"])
def feats(i):
    z = np.load(f"{S}/feat/{i:03d}.npz")
    pc, ys, cl = z["p_clip"], z["y_scores"], z["clap"]
    pm = pc[:, P_MUS].max(1)
    clp = np.exp(cl*1.0); clp = clp/clp.sum(1, keepdims=True)  # sims already scaled by logit_scale? check range
    return dict(p_mus=pm.mean(), p_musfrac=(pm>0.5).mean(), p_drum=pc[:,P_DRUM].max(1).mean(),
                p_crowd=pc[:,P_CROWD].max(1).mean(), p_speech=pc[:,P_SPEECH].mean(),
                y_mus=ys[:,Y_MUS].mean(), pulse=z["pulse"].mean(),
                c_song=(cl.argmax(1)==0).mean(), c_tune=(cl.argmax(1)==1).mean(), c_crowd=(cl.argmax(1)==2).mean(),
                c_ambient=(cl.argmax(1)==5).mean(), simrange=float(cl.max()-cl.min()))
rows = []
for i, it in enumerate(sample):
    f = feats(i); f.update(i=i, **it); rows.append(f)
json.dump([{k:(float(v) if isinstance(v,(np.floating,)) else v) for k,v in r.items()} for r in rows], open(f"{S}/summary.json","w"), indent=1)
cols = ["p_mus","p_musfrac","p_drum","p_crowd","p_speech","y_mus","pulse","c_song","c_tune","c_crowd","c_ambient"]
print(f"{'grp':10} {'slug':38} {'title':14} {'dur':>4} " + " ".join(f"{c[:8]:>8}" for c in cols))
for g in ["song","space","longest15","longintro","midjunk","shortjunk"]:
    for r in sorted([r for r in rows if r["group"]==g], key=lambda r:-r["p_mus"]):
        print(f"{g:10} {r['slug'][:38]:38} {r['title'][:14]:14} {r['dur']:4} " + " ".join(f"{r[c]:8.2f}" for c in cols))
    print()
