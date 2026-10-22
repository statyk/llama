import json, sys
from pathlib import Path
from llama import taper, jerrybase
from llama.models import Track
from llama.songs import GD_SHORTHAND
from llama.setlist import _TRACK_PREFIX, _NUM_PREFIX, _enumerated_prefix
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
    lines = taper._preprocess(text); en = _enumerated_prefix(lines)
    marks = []
    for i, ln in enumerate(lines):
        if not ln: continue
        core = _TRACK_PREFIX.sub("", ln)
        if en: core = _NUM_PREFIX.sub("", core)
        k = taper._classify(core)[0]
        if k != "song":
            nxt = next((l for l in lines[i+1:] if l), "")
            marks.append(f"[{ln[:40]}]->{nxt[:30]}")
    print("="*90); print(slug, "src", src, "align", (sj.get("structure") or {}).get("alignment"), "ssrc", (sj.get("structure") or {}).get("source"))
    print("  markers:", " ; ".join(marks))
    # show reader group boundaries
    g=[]; 
    for it in d.taper.items:
        if not g or g[-1][0]!=it.set: g.append([it.set, it.title, it.title])
        else: g[-1][2]=it.title
    print("  reader groups:", " | ".join(f"{a}:{b}..{c}" for a,b,c in g))
    diff = [i for i,(a,b) in enumerate(zip(today, d.placement.sets)) if a!=b]
    lo, hi = max(0, min(diff)-2), min(len(tracks), max(diff)+3)
    for i in range(lo, hi):
        t = tracks[i]; mark = "*" if i in diff else " "
        print(f"  {mark}{t.index:3d} {today[i]:7s}{d.placement.sets[i]:7s} {t.title_source:10s} {t.title[:60]}")
