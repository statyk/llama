import json, sys
from pathlib import Path
from llama import taper, jerrybase
from llama.models import Track
from llama.songs import GD_SHORTHAND
from llama.structure import is_filler
root = Path("~/.llama").expanduser()
def aliases(a): return GD_SHORTHAND if a and jerrybase.is_family_artist(a) else {}
maxtext = int(sys.argv[1]); slugs = sys.argv[2:]
for slug in slugs:
    sj = json.loads((root/"shows"/slug/"show.json").read_text())
    md = json.loads((root/"cache"/f"md_{sj['identifier']}.json").read_text())
    meta = md.get("metadata", md)
    tracks = [Track.model_validate(t) for t in sj["tracks"]]
    today = [t.set for t in tracks]
    d = taper.decide_taper(tracks, meta, aliases=aliases(sj.get("artist")), today_sets=today)
    text, src = taper.taper_text_for(meta)
    st = sj.get("structure") or {}
    print("="*100); print(slug, sj["identifier"], "src=", src, "reason=", d.reason, "align=", st.get("alignment"), "ssrc=", st.get("source"), "needs_review=", sj.get("needs_review"))
    print("--- TEXT"); print(text[:maxtext])
    print("--- READER items:", " | ".join(f"{i.set}:{i.title}" for i in d.taper.items))
    print("has_encore", d.taper.has_encore, "encore_like", d.taper.encore_like)
    print("--- TRACKS (stored | taper)")
    for t, tp in zip(tracks, d.placement.sets if d.placement else ["-"]*len(tracks)):
        mark = "*" if t.set != tp else " "
        print(f"{mark}{t.index:3d} {t.set:7s} {tp:7s} {t.title_source:14s} {'F' if is_filler(t.title) else ' '} {t.title}")
