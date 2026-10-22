import json, os
H=os.path.expanduser("~/.llama")
CASES=[
 ("THEDEAD_2009_04_25","thedead-2009-04-25","thedead2009-04-25.jwmod.akg.469.v2.sd722.suraci.sbeok.flac16","description","Disc One/Set One:","E: Brokedown Palace"),
 ("GD_1974_07_19","gratefuldead-1974-07-19","gd1974-07-19.sbd.miller.32634.sbeok.flac16","description",None,None),
 ("RYAN_2008_01_21","ryanadams-2008-01-21","ryanadams2008-01-21.sbd.flac16","description","Ryan Solo CD 1","35:21"),
 ("LOCALH_2004_12_31","localh-2004-12-31","localh2004-12-31-live2cd.flac16","description",None,None),
 ("NOS_2012_08_02","neworleanssuspects-2012-08-02","NOS2012-08-02.NOS2012-08-02","description",None,"Oooh Poo Pah Doo>Big Chief<br />"),
 ("MH_1995_08_06","motherhips-1995-08-06","mh1995-08-06","notes","set one-(1:05:59)","Mother Hips\t4:35"),
 ("PAF_2006_07_03","philleshandfriends-2006-07-03","paf2006-07-03.neumann.clarke.35457.sbeok.flac16","description","disc 1 (set 1) \n",None),
]
out=[]
for name,slug,ident,fld,start,end in CASES:
    md=json.load(open(f"{H}/cache/md_{ident}.json")); md=md.get("metadata",md)
    text=md[fld]
    i=text.index(start) if start else 0
    j=(text.index(end,i)+len(end)) if end else len(text)
    ex=text[i:j]
    assert ex in text
    show=json.load(open(f"{H}/shows/{slug}/show.json"))
    trs=show["tracks"]
    out.append(f"# {slug}: md_{ident}.json ({fld}{', excerpt' if (start or end) else ''})")
    lines=ex.splitlines(keepends=True)
    out.append(f"{name} = (")
    for ln in lines: out.append(f"    {ln!r}")
    out.append(")")
    out.append(f"{name}_TRACKS = {[t['title'] for t in trs]!r}")
    out.append(f"{name}_TODAY = {[t['set'] for t in trs]!r}")
    srcs={t.get('title_source') for t in trs}
    if srcs!={'tags'}:
        out.append(f"{name}_SOURCES = {{{', '.join(f'{k+1}: {t.get(chr(116)+"itle_source")!r}' for k,t in enumerate(trs) if t.get('title_source')!='tags')}}}")
    out.append("")
print("\n".join(out))
