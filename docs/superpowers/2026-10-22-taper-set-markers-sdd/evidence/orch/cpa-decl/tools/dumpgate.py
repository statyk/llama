import json, sys
sys.path.insert(0, "scripts")
from pathlib import Path
import taper_probe as tp
from llama import taper
from llama.setlist import _TRACK_PREFIX, _NUM_PREFIX, _enumerated_prefix, _NOISE
root = Path("~/.llama").expanduser(); bundles = Path("~/.llama-harness/t3/bundles").expanduser()
ev = Path("docs/superpowers/2026-10-22-taper-set-markers-evidence")
cl = {r["slug"]: r for r in tp.read_jsonl(ev/"classified.jsonl")}
for slug in sys.argv[1:]:
    sj, tracks = tp.parse_bundle(bundles/f"{slug}.md")
    meta = tp.load_meta(root, sj["identifier"])
    today = [t.set for t in tracks]
    d = tp.decide(tracks, meta, sj.get("artist"), today)
    print("="*90); print(slug, sj["identifier"], "artist", sj.get("artist"), "| src", d.source, "| REASON:", d.reason)
    c = cl[slug]; print("  quote:", (c.get("marker_quote") or "")[:300].replace("\n"," / "))
    for fld in ("description","notes"):
        text = taper._field_text(meta.get(fld))
        if not text: continue
        lines = taper._preprocess(text); en = _enumerated_prefix(lines)
        print(f"  --- {fld} (enumerated={en})")
        n=0
        for ln in lines:
            if not ln: continue
            n+=1
            if n>90: print("   ...(truncated)"); break
            core = _TRACK_PREFIX.sub("", ln)
            if en: core = _NUM_PREFIX.sub("", core)
            k = taper._classify(core)
            tag = {"set": f"SET{k[1]}{'c' if k[2] else ''}{'+E' if k[3] else ''}", "encore": "ENC"}.get(k[0], "")
            if not tag and _NOISE.search(ln): tag = "noise"
            print(f"   {tag:6s}| {ln[:110]}")
    print("  reader:", " | ".join(f"{i.set}:{i.title}" for i in d.taper.items)[:1500], "| enc", d.taper.has_encore, "enclike", d.taper.encore_like)
    print("  tracks:", " ; ".join(f"{t.index}[{t.set}]{'' if t.title_source in ('tags','sibling-format') else '('+t.title_source+')'} {t.title[:45]}" for t in tracks))
