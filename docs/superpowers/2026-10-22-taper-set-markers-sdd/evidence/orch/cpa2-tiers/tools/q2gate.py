import json, sys
from pathlib import Path
sys.path.insert(0, "scripts")
import taper_probe as tp
root = Path("~/.llama").expanduser(); bundles = Path("~/.llama-harness/t3/bundles").expanduser()
rows = [json.loads(l) for l in open(Path("~/.llama-harness/piece2/gate2/gate_rows.jsonl").expanduser())]
n = 0
for r in rows:
    if r.get("status") != "owned": continue
    n += 1
    sj, tracks = tp.parse_bundle(bundles/f"{r['slug']}.md")
    meta = tp.load_meta(root, sj["identifier"]); today = [t.set for t in tracks]
    d = tp.decide(tracks, meta, sj.get("artist"), today)
    labs = list(d.placement.sets)
    se = sum(x == "encore" for x in today); te = sum(x == "encore" for x in labs)
    if se > te:
        lost = [f"{t.index}:{t.title}" for t, a, b in zip(tracks, today, labs) if a == "encore" and b != "encore"]
        print(r["slug"], "today enc", se, "taper enc", te, "has_encore", d.taper.has_encore, "moved:", lost)
print("gate owned rows checked:", n)
