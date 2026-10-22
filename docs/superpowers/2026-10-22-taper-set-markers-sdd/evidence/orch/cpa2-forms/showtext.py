import json,sys
from pathlib import Path
from llama import taper as T
R=Path("~/.llama").expanduser()
for slug in sys.argv[1:]:
    sj=json.loads((R/"shows"/slug/"show.json").read_text())
    meta=json.loads((R/"cache"/f"md_{sj['identifier']}.json").read_text())["metadata"]
    text,src=T.taper_text_for(meta)
    print("=====",slug,src)
    print("\n".join(l for l in T._preprocess(text) if l))
    print("TRACKS:"); [print("  ",t["index"],t["set"],t["title"],t.get("title_source")) for t in sj["tracks"]]
