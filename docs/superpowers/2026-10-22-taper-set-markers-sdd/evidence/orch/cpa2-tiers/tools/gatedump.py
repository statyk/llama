import json, sys, re, html
from pathlib import Path
sys.path.insert(0, "scripts")
import taper_probe as tp
from llama import taper
from llama.structure import is_filler
root = Path("~/.llama").expanduser(); bundles = Path("~/.llama-harness/t3/bundles").expanduser()
ev = Path("docs/superpowers/2026-10-22-taper-set-markers-evidence")
sort1 = {r["slug"]: r for r in json.loads((ev / "sort1.json").read_text())}
n = int(sys.argv[1])
for slug in sys.argv[2:]:
    sj, tracks = tp.parse_bundle(bundles/f"{slug}.md")
    meta = tp.load_meta(root, sj["identifier"])
    today = [t.set for t in tracks]
    d = tp.decide(tracks, meta, sj.get("artist"), today)
    s1 = sort1.get(slug, {}); tb, te = s1.get("t_breaks"), s1.get("t_enc")
    tgt = tp.target_labels(len(tracks), tb, te) if (tb is not None or te is not None) else ["?"]*len(tracks)
    text, src = taper.taper_text_for(meta)
    text = html.unescape(re.sub(r"<br\s*/?>|</div>|</p>", "\n", text, flags=re.I)); text = re.sub(r"<[^>]+>", "", text); text = re.sub(r"\n\s*\n+", "\n", text)
    print("="*90); print(slug, sj["identifier"], "src=", src, "reason=", d.reason, "renum=", s1.get("renum"), "t_breaks=", tb, "t_enc=", te)
    print("--- TEXT"); print(text[:n])
    print("--- ITEMS:", " | ".join(f"{i.set}:{i.title}" for i in d.taper.items)[:1500])
    labs = d.placement.sets if d.placement else ["-"]*len(tracks)
    for i, t in enumerate(tracks):
        m = ("*" if today[i] != labs[i] else " ") + ("!" if tgt[i] not in ("?", labs[i]) else " ")
        print(f"{m}{t.index:3d} today={today[i]:7s} taper={labs[i]:7s} target={tgt[i]:7s} {t.title_source:12s} {'F' if is_filler(t.title) else ' '} {t.title}")
