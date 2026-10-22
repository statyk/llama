import json, sys
from pathlib import Path
from llama import taper, jerrybase
from llama.models import Track
from llama.songs import GD_SHORTHAND
ROOT=Path("~/.llama").expanduser()
def load(slug):
    sj=json.loads((ROOT/"shows"/slug/"show.json").read_text())
    md=json.loads((ROOT/"cache"/f"md_{sj['identifier']}.json").read_text()); meta=md.get("metadata",md)
    tracks=[Track.model_validate(t) for t in sj["tracks"]]
    al=GD_SHORTHAND if jerrybase.is_family_artist(sj.get("artist") or "") else {}
    return sj, meta, tracks, al
def dec(tracks, meta, al):
    d=taper.decide_taper(tracks, meta, aliases=al, today_sets=[t.set for t in tracks])
    return d
def show(slug, edit=None):
    sj,meta,tracks,al=load(slug)
    d=dec(tracks,meta,al)
    def fmt(d):
        if not d.placement: return f"NOT OWNED ({d.reason})"
        s=d.placement.sets; return "OWNED "+str([f"{i}:{s[i-1]}>{s[i]}" for i in range(1,len(s)) if s[i]!=s[i-1]])
    print(slug, "stored:", [f"{i}:{tracks[i-1].set}>{tracks[i].set}" for i in range(1,len(tracks)) if tracks[i].set!=tracks[i-1].set])
    print("  base:", fmt(d), "src", d.source)
    if edit:
        m2=dict(meta); text,src=taper.taper_text_for(meta)
        old,new=edit
        assert old in text, "edit not found"
        m2[src]=text.replace(old,new)
        print("  edit:", fmt(dec(tracks,m2,al)))
    return sj,meta,tracks,al,d
if __name__=="__main__":
    slug=sys.argv[1]
    edit=(sys.argv[2],sys.argv[3]) if len(sys.argv)>3 else None
    sj,meta,tracks,al,d=show(slug,edit)
    if "-v" in sys.argv:
        for t in tracks: print("   ",t.index,t.set,t.title,t.title_source)
