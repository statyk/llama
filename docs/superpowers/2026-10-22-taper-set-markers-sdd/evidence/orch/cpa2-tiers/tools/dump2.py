# compact: text (head/tail configurable), only tracks within 2 of a difference
import json, sys, re, html
from pathlib import Path
from llama import taper, jerrybase
from llama.models import Track
from llama.songs import GD_SHORTHAND
from llama.structure import is_filler
root = Path("~/.llama").expanduser()
def aliases(a): return GD_SHORTHAND if a and jerrybase.is_family_artist(a) else {}
mode = sys.argv[1]  # e.g. "tail:1500" or "all:4000"
kind, n = mode.split(":"); n = int(n)
for slug in sys.argv[2:]:
    sj = json.loads((root/"shows"/slug/"show.json").read_text())
    md = json.loads((root/"cache"/f"md_{sj['identifier']}.json").read_text())
    meta = md.get("metadata", md)
    tracks = [Track.model_validate(t) for t in sj["tracks"]]
    today = [t.set for t in tracks]
    d = taper.decide_taper(tracks, meta, aliases=aliases(sj.get("artist")), today_sets=today)
    text, src = taper.taper_text_for(meta)
    text = html.unescape(re.sub(r"<br\s*/?>|</div>|</p>", "\n", text, flags=re.I)); text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    st = sj.get("structure") or {}
    print("="*90); print(slug, sj["identifier"], "src=", src, "reason=", d.reason, "align=", st.get("alignment"), "ssrc=", st.get("source"))
    t = text if kind=="all" else text[-n:]
    print("--- TEXT"); print(t[:n])
    print("--- ITEMS:", " | ".join(f"{i.set}:{i.title}" for i in d.taper.items))
    print("has_encore", d.taper.has_encore, "encore_like", d.taper.encore_like)
    labs = d.placement.sets if d.placement else ["-"]*len(tracks)
    diff = [i for i,(a,b) in enumerate(zip(today, labs)) if a!=b]
    show = set()
    for i in diff: show |= set(range(max(0,i-2), min(len(tracks), i+3)))
    if kind=="full": show = set(range(len(tracks)))
    prev=None
    for i in sorted(show):
        if prev is not None and i!=prev+1: print("   ...")
        tr=tracks[i]; mark="*" if today[i]!=labs[i] else " "
        print(f"{mark}{tr.index:3d} {today[i]:7s} {labs[i]:7s} {tr.title_source:14s} {'F' if is_filler(tr.title) else ' '} {tr.title}")
        prev=i
    print(f"   ({len(tracks)} tracks)")
