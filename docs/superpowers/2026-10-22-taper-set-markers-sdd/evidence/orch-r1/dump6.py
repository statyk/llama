import json, os, sys
from llama.taper import decide_taper, read_taper_structure
from llama.models import Track
from llama.songs import GD_SHORTHAND
SL = {"thedead-2009-04-25":"thedead2009-04-25.jwmod.akg.469.v2.sd722.suraci.sbeok.flac16",
"gratefuldead-1974-07-19":"gd1974-07-19.sbd.miller.32634.sbeok.flac16",
"ryanadams-2008-01-21":"ryanadams2008-01-21.sbd.flac16",
"localh-2004-12-31":"localh2004-12-31-live2cd.flac16",
"neworleanssuspects-2012-08-02":"NOS2012-08-02.NOS2012-08-02",
"motherhips-1995-08-06":"mh1995-08-06"}
H=os.path.expanduser("~/.llama")
for slug, ident in SL.items():
    show=json.load(open(f"{H}/shows/{slug}/show.json"))
    md=json.load(open(f"{H}/cache/md_{ident}.json")); md=md.get("metadata",md)
    trs=show["tracks"]
    titles=[t["title"] for t in trs]; sets=[t["set"] for t in trs]; srcs=[t.get("title_source") for t in trs]
    tracks=[Track(index=i+1,set=s,title=t,filename=f"t{i+1:02d}.mp3",title_source=src) for i,(t,s,src) in enumerate(zip(titles,sets,srcs))]
    d=decide_taper(tracks, md, aliases=GD_SHORTHAND, today_sets=sets)
    print("=====",slug, d.source, d.reason, d.placement and d.placement.boundaries)
    print("TITLES", titles); print("TODAY", sets); print("SRC", set(srcs))
    print("ITEMS", [(i.title,i.set) for i in d.taper.items])
