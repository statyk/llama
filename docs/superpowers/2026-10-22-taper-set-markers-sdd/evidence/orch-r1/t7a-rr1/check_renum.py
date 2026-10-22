import json, sys, collections
from pathlib import Path
sys.path.insert(0, "scripts")
import taper_probe as tp
from replay_holds import STRIPPED_KEYS
E = Path("docs/superpowers/2026-10-22-taper-set-markers-evidence")
cls = {json.loads(l)["slug"]: json.loads(l) for l in (E/"classified.jsonl").read_text().splitlines() if l.strip()}
s1 = json.loads((E/"sort1.json").read_text())
shows = Path.home()/".llama/shows"
cnt = collections.Counter(); types = collections.Counter(); miss = []
for r in s1:
    if not r.get("renum"): continue
    c = cls.get(r["slug"], {})
    te = c.get("taper_explicit")
    if te not in ("yes", "partial"): cnt["not yes/partial"] += 1; continue
    ov = shows/r["slug"]/"overrides.json"
    stripped = {}
    if ov.is_file():
        d = json.loads(ov.read_text())   # read only
        for k in STRIPPED_KEYS:
            if k in d:
                stripped[k] = d[k]; types[(k, type(d[k]).__name__)] += 1
    ok = tp._fix_applied(stripped, r.get("t_breaks"), r.get("t_enc"))
    cnt[(te, ok)] += 1
    if not ok: miss.append((r["slug"], stripped, r.get("t_breaks"), r.get("t_enc"), sorted(d.keys()) if ov.is_file() else None))
print(cnt); print(types)
for m in miss: print(m)
