import json, sys
from pathlib import Path
from llama.taper import _preprocess, _classify, _field_text
from llama.setlist import _TRACK_PREFIX, _NUM_PREFIX, _enumerated_prefix
out = []
for p in sorted((Path.home()/'.llama'/'cache').glob('md_*.json')):
    try: md = json.loads(p.read_text())
    except Exception: continue
    m = md.get('metadata', md)
    if not isinstance(m, dict): continue
    for f in ('description','notes'):
        t = _field_text(m.get(f))
        if not t or ('set' not in t.lower()): continue
        lines = _preprocess(t); en = _enumerated_prefix(lines)
        for ln in lines:
            if not ln: continue
            core = _TRACK_PREFIX.sub('', ln)
            if en: core = _NUM_PREFIX.sub('', core)
            k = _classify(core)
            if k[0] == 'set':
                out.append([p.name, ln, k[1], k[4]])
json.dump(out, open(sys.argv[1], 'w')); print(len(out))
