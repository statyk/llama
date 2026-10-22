import json, sys
from pathlib import Path
sys.path.insert(0,'/Users/shawn/projects/llama/.claude/worktrees/taper-markers/scripts')
import taper_probe as tp
root=Path('~/.llama').expanduser()
rows=[json.loads(l) for l in open(Path('~/.llama-harness/piece2/gate4/gate_rows.jsonl').expanduser())]
n=0;lost=[];fewer=[]
for r in rows:
    if r.get('status')!='owned': continue
    sj,tracks=tp.parse_bundle(tp.DEFAULT_BUNDLES/f"{r['slug']}.md")
    meta=tp.load_meta(root,sj['identifier']); today=[t.set for t in tracks]
    d=tp.decide(tracks,meta,sj.get('artist'),today); n+=1
    assert d.placement is not None
    new=list(d.placement.sets)
    if 'encore' in today and 'encore' not in new: lost.append(r['slug'])
    elif new.count('encore')<today.count('encore'): fewer.append((r['slug'],today.count('encore'),new.count('encore')))
print('owned gate rows',n,'lost encore',lost,'fewer',fewer)
