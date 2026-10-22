# For every owned library row: items containing the word "set" (set-like text left as a song item)
import json, re, sys
from pathlib import Path
from llama import taper, jerrybase
from llama.models import Track
from llama.songs import GD_SHORTHAND
root = Path("~/.llama").expanduser()
def aliases(a): return GD_SHORTHAND if a and jerrybase.is_family_artist(a) else {}
rows = [json.loads(l) for l in open(Path("~/.llama-harness/piece2/gate2/library_rows.jsonl").expanduser())]
own = [r for r in rows if r["status"] == "owned"]
rx = re.compile(r"\bsets?\b|\bset\d|\bdisc\b|\bdisk\b|\bcd\s*\d", re.I)
out = []
for r in own:
    slug = r["slug"]
    sj = json.loads((root/"shows"/slug/"show.json").read_text())
    md = json.loads((root/"cache"/f"md_{sj['identifier']}.json").read_text())
    meta = md.get("metadata", md)
    tracks = [Track.model_validate(t) for t in sj["tracks"]]
    today = [t.set for t in tracks]
    d = taper.decide_taper(tracks, meta, aliases=aliases(sj.get("artist")), today_sets=today)
    assert d.placement is not None and list(d.placement.sets) == r["taper"], slug
    hits = [(i, it.set, it.title) for i, it in enumerate(d.taper.items) if rx.search(it.title)]
    if hits:
        out.append({"slug": slug, "tier": r["tier"], "hits": hits, "n_items": len(d.taper.items)})
for o in out:
    print(o["slug"], o["tier"], o["n_items"])
    for h in o["hits"]: print("    ", h)
print(len(out), "of", len(own))
