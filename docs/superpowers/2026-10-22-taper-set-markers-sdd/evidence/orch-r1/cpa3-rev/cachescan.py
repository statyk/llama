import json, sys, re
from pathlib import Path
from llama import taper
n=0; hits=[]
for p in sorted(Path('~/.llama/cache').expanduser().glob('md_*.json')):
    try: md=json.loads(p.read_text())
    except Exception: continue
    meta=md.get('metadata',md)
    if not isinstance(meta,dict): continue
    for f in ('description','notes'):
        t=taper._field_text(meta.get(f))
        if not t: continue
        n+=1
        tt=taper.read_taper_structure(t)
        if not tt.asserts or tt.set_like: continue
        its=tt.items
        for i,it in enumerate(its):
            if it.set!='encore' and it.title.strip(taper._ITEM_DECOR).lower()=='set':
                prev=its[i-1].title if i else ''
                hits.append((p.name,f,prev,it.set,[x.set for x in its].count('3')>0))
print('texts',n); print('asserting texts with a bare Set item',len(hits))
for h in hits: print(h)
