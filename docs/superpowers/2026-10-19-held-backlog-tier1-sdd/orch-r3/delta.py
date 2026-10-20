# usage: delta.py OLD.json NEW.json  -> per-show field differences (every field, digests included)
import json,sys
L=lambda p:(lambda x:x if isinstance(x,dict) else {s['slug']:s for s in x})(json.load(open(p))['shows'])
a=L(sys.argv[1])
b=L(sys.argv[2])
print(f"only-old {sorted(set(a)-set(b))}\nonly-new {sorted(set(b)-set(a))}")
n=0
for k in sorted(set(a)&set(b)):
    d=[f for f in sorted(set(a[k])|set(b[k])) if a[k].get(f)!=b[k].get(f)]
    if d:
        n+=1; print(k, a[k].get('outcome'),'->',b[k].get('outcome'), d)
        for f in d:
            if f in('set_breaks','alignment','outcome','notes','gather_flags','set_changes'): print('   ',f,':',json.dumps(a[k].get(f))[:300],'=>',json.dumps(b[k].get(f))[:300])
print('changed shows:',n)
