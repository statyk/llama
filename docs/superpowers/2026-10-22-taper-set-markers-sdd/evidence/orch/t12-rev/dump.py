import json, sys
from pathlib import Path
from llama.taper import read_taper_structure, _field_text
out = {}
for p in sorted((Path.home()/'.llama'/'cache').glob('md_*.json')):
    try:
        md = json.loads(p.read_text())
    except Exception:
        continue
    m = md.get('metadata', md)
    for f in ('description', 'notes'):
        t = _field_text(m.get(f))
        if not t or 'set' not in t.lower() and 'encore' not in t.lower():
            continue
        r = read_taper_structure(t)
        out[f'{p.name}|{f}'] = {'items': [[i.title, i.set] for i in r.items], 'asserts': r.asserts, 'reason': r.reason, 'enc': r.has_encore, 'like': r.encore_like}
json.dump(out, open(sys.argv[1], 'w'))
print(len(out))
