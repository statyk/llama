import json,collections,sys
sys.argv=['x']
__file__='/Users/shawn/.llama-harness/piece3/census/census.py'
src=open(__file__).read().splitlines(keepends=True)
exec("".join(src[:104]+src[340:356]))
from llama.structure import is_filler
IND={'tags','sibling-format','override','sibling-align'}
c=collections.Counter(); pop=[]
for r in rows:
    tr,_=basis(r)
    if not tr: continue
    ind=sum(1 for t in tr if t['src'] in IND and not is_filler(t['title']))
    n=len(tr)
    nl=len(numbered_lines(r.get('description') or ''))
    op=len(r.get('own_parse') or [])
    cm=(nl==n) or (op==n)
    held=bool(r.get('flags') if r.get('replayed') else r.get('stored_flags'))
    c['all']+=1
    if ind<2:
        c['untagged']+=1
        c['untagged_held' if held else 'untagged_ships']+=1
        if cm:
            c['untagged_countmatched']+=1; pop.append(r['slug'])
            c['untagged_cm_held' if held else 'untagged_cm_ships']+=1
            c['untagged_cm_canon:'+(r.get('canonical_source') or 'none')[:10]]+=1
        else:
            nn=max(nl,op)
            c['untagged_list_off_by_1' if abs(nn-n)==1 else ('untagged_list_off_more' if nn else 'untagged_no_list')]+=1
for k,v in sorted(c.items()): print(f'{k:32s} {v:5d}  {100*v/c["all"]:.1f}%')
json.dump(pop,open('/Users/shawn/.llama-harness/piece3/untagged_cm.json','w'))
print([x['identifier'] for x in rows if x['slug']=='billystrings-2023-06-10'])
