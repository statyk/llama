import json, sys
from pathlib import Path
sys.path.insert(0, 'scripts')
import taper_probe as tp
from llama.taper import taper_text_for, read_taper_structure
root = Path.home()/'.llama'
rows = [json.loads(l) for l in open(Path.home()/'.llama-harness/piece2/gate2/library_rows.jsonl')]
owned = [r for r in rows if r.get('status')=='owned']
print('owned', len(owned))
n=0
for r in owned:
    sj = json.loads((root/'shows'/r['slug']/'show.json').read_text())
    meta = tp.load_meta(root, sj['identifier'])
    text, src = taper_text_for(meta)
    t = read_taper_structure(text)
    its = [i for i in t.items if ',' in i.title]
    if its:
        n+=1
        # boundary items
        sets=[i.set for i in t.items]
        bidx=set()
        for k in range(len(sets)-1):
            if sets[k]!=sets[k+1]: bidx |= {k,k+1}
        print(r['slug'], r.get('tier'), [(i.title, i.set, 'B' if t.items.index(i) in bidx else '') for i in its])
print('rows with comma items', n)
