import json,sys,collections
rows=[json.loads(l) for l in open("libvar.jsonl")]
def own(s): return s[0] is not None
for v in ["noB","noC","noB+noC","noItem","noPre"]:
    c=collections.Counter(); ex=collections.defaultdict(list)
    for r in rows:
        h,o=r["head"],r[v]
        if h==o: continue
        if own(h) and not own(o): k="HEAD owns, variant not"
        elif own(o) and not own(h): k="variant owns, HEAD not (HEAD owns less)"
        elif own(h) and own(o): k="both own, labels differ" if h[0]!=o[0] else "both own, same labels"
        else: k="neither owns, reason differs"
        c[k]+=1; ex[k].append(r["slug"])
    print("==",v, dict(c))
    for k,l in ex.items():
        if k!="neither owns, reason differs": print("  ",k,":", " ".join(l))
