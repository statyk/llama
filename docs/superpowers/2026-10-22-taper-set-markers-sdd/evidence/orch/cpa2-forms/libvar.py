"""Per library show: decide_taper under HEAD and each variant. Read-only."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import variants as V
from llama import taper, jerrybase
from llama.models import Track
from llama.songs import GD_SHORTHAND

ROOT = Path("~/.llama").expanduser()
OUT = Path(sys.argv[1])

def override(show, sj):
    if (sj.get("structure") or {}).get("source") == "override":
        return True
    p = show / "overrides.json"
    if p.exists():
        try:
            o = json.loads(p.read_text())
        except Exception:
            return True
        return o.get("set_breaks") is not None or o.get("encore_after") is not None
    return False

def sig(d):
    return [list(d.placement.sets) if d.placement else None, d.reason, d.source]

out = open(OUT, "w")
n = 0
for show in sorted((ROOT / "shows").glob("*/")):
    sjp = show / "show.json"
    if not sjp.exists():
        continue
    try:
        sj = json.loads(sjp.read_text())
        if override(show, sj):
            continue
        tracks = [Track.model_validate(t) for t in sj["tracks"]]
        if not tracks:
            continue
        md = json.loads((ROOT / "cache" / f"md_{sj['identifier']}.json").read_text())
    except Exception:
        continue
    meta = md.get("metadata", md)
    al = GD_SHORTHAND if jerrybase.is_family_artist(sj.get("artist") or "") else {}
    today = [t.set for t in tracks]
    row = {"slug": show.name, "ident": sj["identifier"], "artist": sj.get("artist"), "today": today}
    for v in V.VARIANTS:
        V.patch(v)
        row[v] = sig(taper.decide_taper(tracks, meta, aliases=al, today_sets=today))
    V.patch("head")
    n += 1
    if any(row[v] != row["head"] for v in V.VARIANTS):
        out.write(json.dumps(row) + "\n")
out.close()
print("evaluated", n)
