import sys, json
from pathlib import Path
sys.path.insert(0, "scripts")
import taper_probe as tp
from llama import taper
from pathlib import Path
B = Path("~/.llama-harness/t3/bundles").expanduser(); R = Path("~/.llama").expanduser()
EV = Path("docs/superpowers/2026-10-22-taper-set-markers-evidence")
s1 = {r["slug"]: r for r in json.loads((EV/"sort1.json").read_text())}
cl = {r["slug"]: r for r in tp.read_jsonl(EV/"classified.jsonl")}
for slug in sys.argv[1:]:
    sj, tracks = tp.parse_bundle(B/f"{slug}.md")
    meta = tp.load_meta(R, sj["identifier"])
    d = tp.decide(tracks, meta, sj.get("artist"), [t.set for t in tracks])
    c = cl[slug]; r = s1.get(slug, {})
    print("=====", slug, sj["identifier"], "artist:", sj.get("artist"), "family:", bool(tp.aliases_for(sj.get("artist"))))
    print("class:", c.get("primary"), c.get("taper_explicit"), "quote:", (c.get("marker_quote") or "")[:200])
    print("target:", r.get("t_breaks"), r.get("t_enc"), "renum", r.get("renum"))
    print("decision:", d.source, d.reason, "asserts", d.taper.asserts, "has_enc", d.taper.has_encore)
    print("items:", [(i.set, i.title) for i in d.taper.items])
    for t, lab in zip(tracks, d.placement.sets if d.placement else [None]*len(tracks)):
        print(f"  {t.index:3d} {t.set:7s} {str(lab):7s} {t.title_source:14s} {t.matched!s:5s} {t.title}")
    if d.placement and r.get("t_breaks") is not None or r.get("t_enc") is not None:
        if d.placement:
            print("target labels:", tp.target_labels(len(tracks), r.get("t_breaks"), r.get("t_enc")))
            print("match:", tp.compare(list(d.placement.sets), tp.target_labels(len(tracks), r.get("t_breaks"), r.get("t_enc")), tracks))
