import json, sys
from pathlib import Path
W=Path('/Users/shawn/projects/llama/.claude/worktrees/taper-markers')
sys.path.insert(0, str(W/'scripts'))
import taper_probe as tp
from llama import taper
root=Path('~/.llama').expanduser()
lib={json.loads(l)['slug']:json.loads(l) for l in open(Path('~/.llama-harness/piece2/gate4/library_rows.jsonl').expanduser())}
for slug in sys.argv[1:]:
    p=root/'shows'/slug/'show.json'
    if p.exists():
        sj=json.loads(p.read_text()); tracks=[t['title'] for t in sj['tracks']]
    else:
        sj,tr=tp.parse_bundle(tp.DEFAULT_BUNDLES/f'{slug}.md'); tracks=[t.title for t in tr]
    meta=tp.load_meta(root, sj['identifier'])
    text,source=taper.taper_text_for(meta)
    print('=====',slug,source, lib.get(slug,{}).get('status'))
    print(text[:2500])
    r=lib.get(slug)
    if r and r.get('stored'):
        for i,(t,a,b) in enumerate(zip(tracks,r['stored'],r['taper'])):
            print('  %2d %-8s %-8s %s %s'%(i+1,a,b,t,'  <<' if a!=b else ''))
