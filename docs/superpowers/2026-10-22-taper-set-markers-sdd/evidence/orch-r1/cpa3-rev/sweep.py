import json, sys, re
from pathlib import Path
W=Path('/Users/shawn/projects/llama/.claude/worktrees/taper-markers')
sys.path.insert(0, str(W/'scripts'))
import llama; print('llama from', llama.__file__, file=sys.stderr)
import taper_probe as tp
from llama import taper
from llama.models import Track
root=Path('~/.llama').expanduser(); bundles=tp.DEFAULT_BUNDLES; ev=tp.DEFAULT_EVIDENCE
H=Path('~/.llama-harness/piece2/gate4').expanduser()
out=[]
lib={json.loads(l)['slug']:json.loads(l) for l in open(H/'library_rows.jsonl')}
for slug,r in lib.items():
    if r['status']!='owned' and 'set-like' not in (r.get('reason') or ''): continue
    sj=json.loads((root/'shows'/slug/'show.json').read_text())
    meta=tp.load_meta(root, sj['identifier'])
    text,source=taper.taper_text_for(meta)
    tt=taper.read_taper_structure(text)
    out.append({'kind':'library','slug':slug,'status':r['status'],'source':source,'items':[(i.title,i.set) for i in tt.items],'set_like':tt.set_like,'has_encore':tt.has_encore})
gate={json.loads(l)['slug']:json.loads(l) for l in open(H/'gate_rows.jsonl')}
for slug,r in gate.items():
    if r.get('status')!='owned' and 'set-like' not in (r.get('reason') or ''): continue
    if slug in lib and lib[slug]['status']=='owned':
        pass
    sj,tracks=tp.parse_bundle(bundles/f'{slug}.md')
    meta=tp.load_meta(root, sj['identifier'])
    text,source=taper.taper_text_for(meta)
    tt=taper.read_taper_structure(text)
    out.append({'kind':'gate','slug':slug,'status':r['status'],'source':source,'items':[(i.title,i.set) for i in tt.items],'set_like':tt.set_like,'has_encore':tt.has_encore})
json.dump(out, open(sys.argv[1],'w'), indent=0)
print(len(out), file=sys.stderr)
