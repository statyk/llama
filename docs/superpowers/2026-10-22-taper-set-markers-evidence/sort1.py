import json,glob,re,shlex,collections,sys
from llama.setlist import parse_setlist
from llama.structure import align
from llama.models import Track
T3='/Users/shawn/.llama-harness/t3'; C='/Users/shawn/.llama/cache'
def target(v):
    br=enc=None; renum=False
    for st in v.get('action',{}).get('steps',[]):
        try: a=shlex.split(st.get('cmd',''))
        except ValueError: a=st.get('cmd','').split()
        for i,x in enumerate(a):
            if x=='--set-breaks': br=[int(n) for n in a[i+1].split(',') if n.strip()]
            if x=='--set-encore': enc=int(a[i+1])
            if x in('--include','--exclude','--unexclude','--untitled'): renum=True
    return br,enc,renum
def breaks_of(sets):
    out=[];enc=None
    for i in range(1,len(sets)):
        if sets[i]!=sets[i-1]:
            if sets[i]=='encore' and enc is None: enc=i
            else: out.append(i)
    return out,enc
rows=[]
for f in sorted(glob.glob(T3+'/verdicts/*.json')):
    v=json.load(open(f))
    rc=[r if isinstance(r,str) else r.get('tag') for r in (v.get('root_causes') or [])]
    if 'set-source-precedence' not in rc: continue
    b=open(f'{T3}/bundles/{v["slug"]}.md').read()
    m=re.search(r'## show.json.*?\n(\{.*?\n\})\n',b,re.S)
    sj=json.loads(m.group(1)) if m else None
    r=dict(slug=v['slug'],kind=v['action'].get('kind'))
    br,enc,renum=target(v); r.update(t_breaks=br,t_enc=enc,renum=renum)
    if not sj: r['err']='no show.json'; rows.append(r); continue
    st=sj.get('structure') or {}
    r.update(source=st.get('source'),alignment=st.get('alignment'))
    tm=re.search(r'tracks \(n \| set.*?\n((?:\d+ \|.*\n)+)',b)
    tracks=[]
    for ln in (tm.group(1).splitlines() if tm else []):
        p_=[x.strip() for x in ln.split(' | ')]
        mt={'True':True,'False':False}.get(p_[4])
        tracks.append(Track(index=int(p_[0]),set=p_[1],title=' | '.join(p_[2:-4]) if len(p_)>7 else p_[2],title_source=p_[-4] if len(p_)>7 else p_[3],matched=mt,duration_sec=float(p_[-2]) if p_[-2] not in('','None') else None,filename=p_[-1]))
    sb,se=breaks_of([t.set for t in tracks]); r.update(s_breaks=sb,s_enc=se)
    try: md=json.load(open(f'{C}/md_{sj["identifier"]}.json'))
    except Exception: r['err']='no md'; rows.append(r); continue
    meta=md.get('metadata',md); d=meta.get('description') or ''
    if isinstance(d,list): d='\n'.join(d)
    p=parse_setlist(d)
    labels=[i.set for i in p.items]; r['desc_labels']=sorted(set(labels)); r['desc_items']=len(p.items); r['desc_conf']=p.confidence
    fn=' '.join(t.filename for t in tracks)
    r['fn_marker']=bool(re.search(r'(?i)(set|s)[ _-]?0?[123][ _-]?(t|tk|tr|track|_)\d|set0?[123]',fn))
    r['tag_marker']=any(re.search(r'(?i)\bset\s*(1|2|3|i{1,3}|one|two)\b|\bencore\b',t.title or '') for t in tracks)
    r['raw_marker']=bool(re.search(r'(?im)^\W*(set\s*(1|2|3|i{1,3}|one|two|three)|encore|e:|disc\s*\d+\s*\(set)',d))
    if len(set(labels))>1:
        res=align(tracks,p)
        ab,ae=breaks_of(res.sets); r.update(a_breaks=ab,a_enc=ae,a_cov=round(res.coverage,2))
    rows.append(r)
json.dump(rows,open('/Users/shawn/.llama-harness/piece2/sort1.json','w'),indent=1)
