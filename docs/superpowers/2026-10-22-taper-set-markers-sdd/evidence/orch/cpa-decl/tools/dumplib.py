import json, sys
from pathlib import Path
from llama import taper, jerrybase
from llama.models import Track
from llama.songs import GD_SHORTHAND
from llama.setlist import parse_setlist
root = Path("~/.llama").expanduser()
def aliases(a): return GD_SHORTHAND if a and jerrybase.is_family_artist(a) else {}
for slug in sys.argv[1:]:
    sj = json.loads((root/"shows"/slug/"show.json").read_text())
    md = json.loads((root/"cache"/f"md_{sj['identifier']}.json").read_text())
    meta = md.get("metadata", md)
    tracks = [Track.model_validate(t) for t in sj["tracks"]]
    today = [t.set for t in tracks]
    d = taper.decide_taper(tracks, meta, aliases=aliases(sj.get("artist")), today_sets=today)
    text, src = taper.taper_text_for(meta)
    print("="*100); print(slug, sj["identifier"], "src=", src, "alignment=", (sj.get("structure") or {}).get("alignment"), "ssrc=",(sj.get("structure") or {}).get("source"))
    print("--- TEXT"); print(text[:6000])
    print("--- READER items:", " | ".join(f"{i.set}:{i.title}" for i in d.taper.items))
    print("has_encore", d.taper.has_encore, "encore_like", d.taper.encore_like)
    ps = parse_setlist(text)
    print("--- parse_setlist labels:", sorted({i.set for i in ps.items}))
    print("--- TRACKS (stored | taper)")
    for t, tp in zip(tracks, d.placement.sets if d.placement else ["-"]*len(tracks)):
        print(f"{t.index:3d} {t.set:7s} {tp:7s} {t.title_source:14s} {t.title}")
