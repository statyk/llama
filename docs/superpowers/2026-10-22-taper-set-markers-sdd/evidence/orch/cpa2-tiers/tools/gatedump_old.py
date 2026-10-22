# gate dump using the 3d1c1e7.. pre-(d) version (2abad1e) to show what (d) turned off
import json, sys, importlib.util
from pathlib import Path
sys.path.insert(0, "scripts")
import taper_probe as tp
S = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("taper_pre_d", S/"versions"/"taper_2abad1e.py")
m = importlib.util.module_from_spec(spec); sys.modules[spec.name] = m; spec.loader.exec_module(m)
from llama.structure import is_filler
root = Path("~/.llama").expanduser(); bundles = Path("~/.llama-harness/t3/bundles").expanduser()
ev = Path("docs/superpowers/2026-10-22-taper-set-markers-evidence")
sort1 = {r["slug"]: r for r in json.loads((ev / "sort1.json").read_text())}
for slug in sys.argv[2:]:
    sj, tracks = tp.parse_bundle(bundles/f"{slug}.md")
    meta = tp.load_meta(root, sj["identifier"])
    today = [t.set for t in tracks]
    d = m.decide_taper(tracks, meta, aliases=tp.aliases_for(sj.get("artist")), today_sets=today)
    s1 = sort1.get(slug, {}); tb, te = s1.get("t_breaks"), s1.get("t_enc")
    tgt = tp.target_labels(len(tracks), tb, te) if (tb is not None or te is not None) else ["?"]*len(tracks)
    text, src = m.taper_text_for(meta)
    print("="*80); print(slug, "renum", s1.get("renum"), "t_breaks", tb, "t_enc", te, "pre-(d) reason", d.reason)
    import re
    hd = [ln for ln in text.splitlines() if re.search(r"set|encore|\bE\b|disc", ln, re.I)]
    print("  marker-ish lines:", " | ".join(h.strip()[:70] for h in hd[:14]))
    labs = d.placement.sets if d.placement else ["-"]*len(tracks)
    for i, t in enumerate(tracks):
        if today[i] != labs[i] or tgt[i] not in ("?", labs[i]) or today[i]=="encore":
            print(f"   {t.index:3d} today={today[i]:7s} pre-d-taper={labs[i]:7s} target={tgt[i]:7s} {'F' if is_filler(t.title) else ' '} {t.title}")
