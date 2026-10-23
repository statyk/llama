import json,re,sys,glob
from pathlib import Path
H=Path.home()/".llama-harness/piece3"
__file__=str(H/"census/census.py")
src=open(__file__).read().splitlines(keepends=True)
exec("".join(src[:104]+src[340:356]))
from llama.models import Track
from llama.setlist import ParsedSetlist, SetlistItem
from llama.songs import normalize_song
from llama.structure import align, is_filler
from llama.jerrybase import is_family_artist
from llama.songs import GD_SHORTHAND
pop=json.load(open(H/"untagged_cm.json"))
# verdicts
ver={}
for f in glob.glob(str(H/"handcheck/U*/rows.jsonl"))+glob.glob("/Users/shawn/projects/llama/docs/superpowers/2026-10-22-title-hygiene-evidence/handcheck/U*/rows.jsonl"):
    for line in open(f):
        try: d=json.loads(line)
        except: continue
        if 'show_verdict' in d: ver[d.get('slug')]=d['show_verdict']
DUR=re.compile(r"\s*[\[(]?\d{1,2}:\d{2}(?::\d{2})?[\])]?\s*$")
LEAD=re.compile(r"^\s*\(?\d{1,2}:\d{2}(?::\d{2})?\)?\s*(?:-\s*)?")
def clean(s):
    s=s.replace('\t',' ')
    s=DUR.sub('',s); s=LEAD.sub('',s)
    s=re.sub(r"(?:\s*(?:->|>|\*|@|#|\^|\$))+\s*$","",s)
    s=re.sub(r"^\s*(?:e|en|enc|encore|filler)\s*:\s*","",s,flags=re.I)
    return s.strip().strip('"').strip()
for slug in pop:
    r=by[slug]; tr,_=basis(r); n=len(tr)
    nl=numbered_lines(r.get('description') or ''); op=r.get('own_parse') or []
    lst=nl if len(nl)==n else op
    cs=r.get('canonical_source'); can=r.get('canonical') or []
    if cs in (None,'chosen') or not can: 
        print(f"{slug:45s} {ver.get(slug,'?'):22s} canon={cs} (no agreement check)"); continue
    al=GD_SHORTHAND if is_family_artist(r.get('artist','')) else {}
    tracks=[Track(index=i+1,set='1',title=clean(lst[i]) or 'x',filename=t['file'],duration_sec=t.get('dur'),segue=False,title_source='tags') for i,t in enumerate(tr)]
    ps=ParsedSetlist(items=[SetlistItem(title=c['title'],normalized=normalize_song(c['title']),set=c.get('set','1')) for c in can],confidence='high')
    res=align(tracks,ps,aliases=al)
    sl=[m for t,m in zip(tracks,res.matched) if not is_filler(t.title)]
    cov=sum(sl)/len(sl) if sl else 0
    miss=[t.title for t,m in zip(tracks,res.matched) if not m and not is_filler(t.title)][:5]
    print(f"{slug:45s} {ver.get(slug,'?'):22s} canon={cs} cov={cov:.2f} {'DECLINE' if cov<0.8 else ''} miss={miss}")
