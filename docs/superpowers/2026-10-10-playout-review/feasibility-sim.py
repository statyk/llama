import json,glob,random,sys,collections
R="/Users/shawn/Documents/llama/delivered"
shows=[]
for m in glob.glob(R+"/*/manifest.json"):
    j=json.load(open(m)); d=j.get('total_duration_sec')
    if d: shows.append(((j.get('source') or {}).get('profile'), d/60+4))  # +4 min DJ clips approx
def run(win, seed):
    rnd=random.Random(seed)
    # anchors: (day, start_min_of_day, profile)  7am/7pm dead daily, noon bluegrass daily, sat 21:00 funk, sun 15:00 dead-family
    anchors=[]
    for day in range(7):
        anchors+= [(day*1440+7*60,'dead'),(day*1440+12*60,'bluegrass'),(day*1440+19*60,'dead')]
    anchors+= [(5*1440+22*60+30,'funk'),(6*1440+15*60,'dead-family')]
    anchors.sort()
    used=set(); t=anchors[0][0]; fails=0; fills=[]; ok=0
    pool=[i for i,(p,_) in enumerate(shows)]
    for k,(a,prof) in enumerate(anchors):
        # play anchor
        cands=[i for i in pool if shows[i][0]==prof and i not in used]
        if not cands: cands=[i for i in pool if shows[i][0]==prof]
        i=rnd.choice(cands); used.add(i); t=max(t,a); t+=shows[i][1]
        if k+1==len(anchors): break
        nxt=anchors[k+1][0]; lo,hi=nxt,nxt+win
        if t>hi: fails+=1000; continue
        # fill from non-anchor-profile shows via random DFS
        fp=[j for j in pool if shows[j][0] not in ('dead','dead-family','funk') and j not in used]
        best=None
        for _ in range(4000):
            rnd.shuffle(fp); s=t; pick=[]
            for j in fp:
                if s>=lo: break
                if s+shows[j][1]<=hi: pick.append(j); s+=shows[j][1]
            if lo<=s<=hi: best=pick; break
        if best is None: fails+=1; t=lo
        else:
            used.update(best); t=s if False else t+sum(shows[j][1] for j in best); fills.append(len(best)); ok+=1
    return fails, len(anchors)-1, ok
for win in (60,30,15,5):
    tot=f=0
    for seed in range(50):
        a,b,_=run(win,seed); f+=a; tot+=b
    print(f"window {win:>2} min: {f}/{tot} gaps unfillable ({100*f/tot:.1f}%)")
print(len(shows),"shows")
