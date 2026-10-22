import json, re
from pathlib import Path
from llama import taper
rx=re.compile(r"\bset\s*[-#:.]\s*(?:no\.?\s*)?[123]\b|\bset\s*(?:#|no\.?)\s*[123]\b|\b(?:1st|2nd|3rd|first|second|third)\s+(?:half|show)\b|\bsets?\s+(?:break|one|two|three|1|2|3)\b|\bset\s*break\b|\bsetbreak\b",re.I)
hits=[]
for p in sorted(Path('~/.llama/cache').expanduser().glob('md_*.json')):
    try: md=json.loads(p.read_text())
    except Exception: continue
    meta=md.get('metadata',md)
    if not isinstance(meta,dict): continue
    for f in ('description','notes'):
        t=taper._field_text(meta.get(f))
        if not t: continue
        tt=taper.read_taper_structure(t)
        if not tt.asserts or tt.set_like: continue
        for it in tt.items:
            if it.set!='encore' and rx.search(it.title): hits.append((p.name,f,it.set,it.title[:90]))
print(len(hits))
for h in hits: print(h)
