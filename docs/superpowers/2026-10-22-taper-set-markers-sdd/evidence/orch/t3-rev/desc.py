import sys, json, re
from pathlib import Path
sys.path.insert(0, "scripts")
import taper_probe as tp
from llama import taper
B = Path("~/.llama-harness/t3/bundles").expanduser(); R = Path("~/.llama").expanduser()
EV = Path("docs/superpowers/2026-10-22-taper-set-markers-evidence")
cl = {r["slug"]: r for r in tp.read_jsonl(EV/"classified.jsonl")}
for slug in sys.argv[1:]:
    sj, tracks = tp.parse_bundle(B/f"{slug}.md")
    meta = tp.load_meta(R, sj["identifier"])
    d = tp.decide(tracks, meta, sj.get("artist"), [t.set for t in tracks])
    c = cl[slug]
    print("=====", slug, sj["identifier"], "| quote:", c.get("marker_quote"), "| note:", (c.get("note") or "")[:300])
    print("decision:", d.source, d.reason)
    for fld in ("description","notes"):
        t = taper._field_text(meta.get(fld))
        if not t: continue
        print(f"--- {fld} ---")
        lines = taper._preprocess(t)
        for ln in lines:
            if re.search(r"(?i)set|enc|disc|^e\b", ln): print("   |", ln[:160])
