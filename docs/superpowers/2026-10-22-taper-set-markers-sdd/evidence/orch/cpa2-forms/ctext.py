import json,sys,re
from pathlib import Path
from llama import taper as T
R=Path("~/.llama").expanduser()
pat=re.compile(sys.argv[1],re.I)
for ident in sys.argv[2:]:
    meta=json.loads((R/"cache"/f"md_{ident}.json").read_text())["metadata"]
    text,src=T.taper_text_for(meta)
    r=T.read_taper_structure(text)
    ls=[l for l in T._preprocess(text) if l]
    print("=====",ident,src,r.reason,"enc",r.has_encore)
    for i,l in enumerate(ls):
        if pat.search(l): print("   ",i, " || ".join(ls[max(0,i-1):i+3])[:250])
